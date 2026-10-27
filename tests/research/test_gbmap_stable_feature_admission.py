"""Source-bound HGNC feature admission before ranking, caps and hierarchy fitting."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution import feature_identity as identity
from glio_proteogen.research.gbmap_deconvolution import selection, training
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError
from glio_proteogen.research.gbmap_deconvolution.splits import build_validation_split_plan


@pytest.fixture
def source_reference():
    """Real public feature names, entirely synthetic donor/count observations."""
    crosswalk = identity.production_feature_identity_crosswalk()
    features = tuple(entry.input_symbol for entry in crosswalk.entries)
    eligible = crosswalk.usable_feature_indices
    eligible_set = set(eligible)
    excluded = tuple(index for index in range(len(features)) if index not in eligible_set)
    markers_a, markers_b = eligible[:12], eligible[12:24]
    nuisance_a, nuisance_b = excluded[:2]
    filler = eligible[-1]
    records = []
    for study in range(4):
        for donor in range(3):
            for label in ("lineage-a", "lineage-b"):
                own, other = (
                    (markers_a, markers_b) if label == "lineage-a" else (markers_b, markers_a)
                )
                own_nuisance, other_nuisance = (
                    (nuisance_a, nuisance_b) if label == "lineage-a" else (nuisance_b, nuisance_a)
                )
                counts = np.zeros(5_000, dtype=np.int64)
                counts[list(own)] = 600
                counts[list(other)] = 50
                counts[own_nuisance] = 6_000
                counts[other_nuisance] = 100
                counts[filler] = 6_100
                assert int(counts.sum()) == 20_000
                records.append(
                    DonorLabelAggregate(
                        donor_key=f"synthetic-donor-{study}-{donor}",
                        study_key=f"synthetic-study-{study}",
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=100,
                        gene_counts=counts,
                        detected_cell_counts=np.minimum(counts, 80).astype(np.int32),
                        total_umis=20_000,
                    )
                )
    reference = AggregateReference(
        feature_ids=features,
        gene_symbols=(None,) * len(features),
        records=tuple(records),
        source_file_sha256=identity.GBMAP_SOURCE_SHA256,
        source_bytes=8_975_644_082,
        taxonomy_digest="sha256:" + "2" * 64,
        extraction_recipe_digest="sha256:" + "3" * 64,
    )
    return SimpleNamespace(
        reference=reference,
        eligible=eligible,
        excluded=excluded,
        markers_a=markers_a,
        markers_b=markers_b,
        nuisance_a=nuisance_a,
        nuisance_b=nuisance_b,
    )


def _forbidden(*_args, **_kwargs):
    pytest.fail("feature admission was bypassed before numerical work")


def test_exact_production_axis_admits_only_the_pinned_4923_unique_hgnc_features(source_reference):
    fixture = source_reference
    admitted = identity.model_eligible_feature_indices(
        fixture.reference.feature_ids, source_file_sha256=fixture.reference.source_file_sha256
    )
    assert admitted == fixture.eligible
    assert len(admitted) == len(set(admitted)) == 4_923
    assert admitted == tuple(sorted(admitted))
    assert len(fixture.excluded) == 77
    assert set(admitted).isdisjoint(fixture.excluded)


def test_production_admission_precedes_per_label_and_union_caps(monkeypatch, source_reference):
    fixture = source_reference
    reference = fixture.reference
    before = tuple(record.gene_counts.tobytes() for record in reference.records)
    monkeypatch.setattr(selection, "MAX_GENES_PER_LABEL", 12)
    monkeypatch.setattr(selection, "MAX_UNION_GENES", 24)
    result = selection.select_fold_stable_genes(reference, training_records=reference.records)
    assert len(result.union_feature_indices) == 24
    assert set(result.union_feature_indices) == {*fixture.markers_a, *fixture.markers_b}
    assert all(
        group.passing_gene_count == group.pre_union_selected_count == 12
        for group in result.by_label
    )
    assert all(len(group.genes) == 12 for group in result.by_label)
    assert fixture.nuisance_a not in result.union_feature_indices
    assert fixture.nuisance_b not in result.union_feature_indices
    assert len(reference.feature_ids) == 5_000
    assert all(record.gene_counts.shape == (5_000,) for record in reference.records)
    assert tuple(record.gene_counts.tobytes() for record in reference.records) == before
    assert all(not record.gene_counts.flags.writeable for record in reference.records)


def test_excluded_stronger_markers_never_reach_scoring(monkeypatch, source_reference):
    fixture = source_reference
    observed = []
    original = selection.stable_gene_score

    def score(**kwargs):
        observed.append(kwargs["median_log2_enrichment"])
        return original(**kwargs)

    monkeypatch.setattr(selection, "stable_gene_score", score)
    selection.select_fold_stable_genes(
        fixture.reference, training_records=fixture.reference.records
    )
    assert observed
    assert max(observed) < 4.0  # Excluded 6,000:100 features would score above log2(60).


def test_precomputed_and_public_selection_share_the_same_admitted_universe(source_reference):
    reference = source_reference.reference
    cache = selection._build_reference_selection_cache(reference)
    assert cache.eligible_feature_indices == source_reference.eligible
    private = selection._select_fold_stable_genes_precomputed(
        reference, cache, training_records=reference.records
    )
    public = selection.select_fold_stable_genes(reference, training_records=reference.records)
    assert private == public


@pytest.mark.parametrize("mutation", ["rotated", "truncated", "renamed"])
def test_bad_production_feature_axis_fails_before_normalization(
    monkeypatch, source_reference, mutation
):
    reference = source_reference.reference
    if mutation == "rotated":
        features = (*reference.feature_ids[1:], reference.feature_ids[0])
        changed = replace(reference, feature_ids=features)
    elif mutation == "renamed":
        changed = replace(
            reference, feature_ids=("synthetic-wrong-feature", *reference.feature_ids[1:])
        )
    else:
        records = tuple(
            replace(
                record,
                gene_counts=record.gene_counts[:-1],
                detected_cell_counts=record.detected_cell_counts[:-1],
                total_umis=int(record.gene_counts[:-1].sum()),
            )
            for record in reference.records
        )
        changed = replace(
            reference,
            feature_ids=reference.feature_ids[:-1],
            gene_symbols=reference.gene_symbols[:-1],
            records=records,
        )
    monkeypatch.setattr(selection, "_largest_remainder_scale_prevalidated", _forbidden)
    with pytest.raises(GbmapInputError, match="crosswalk order"):
        selection._build_reference_selection_cache(changed)


@pytest.mark.parametrize("mutation", ["all_features", "empty", "reversed", "missing_one"])
def test_precomputed_cache_cannot_replace_the_production_feature_policy(
    monkeypatch, source_reference, mutation
):
    reference = source_reference.reference
    cache = selection._build_reference_selection_cache(reference)
    choices = {
        "all_features": tuple(range(5_000)),
        "empty": (),
        "reversed": tuple(reversed(source_reference.eligible)),
        "missing_one": source_reference.eligible[1:],
    }
    forged = replace(cache, eligible_feature_indices=choices[mutation])
    monkeypatch.setattr(selection, "_label_metrics", _forbidden)
    with pytest.raises(GbmapInputError, match="feature eligibility"):
        selection._select_fold_stable_genes_precomputed(
            reference, forged, training_records=reference.records
        )


def test_caller_owned_reference_keeps_its_feature_universe(monkeypatch, source_reference):
    reference = replace(source_reference.reference, source_file_sha256="sha256:" + "1" * 64)
    monkeypatch.setattr(identity, "production_feature_identity_crosswalk", _forbidden)
    monkeypatch.setattr(selection, "MAX_GENES_PER_LABEL", 12)
    monkeypatch.setattr(selection, "MAX_UNION_GENES", 24)
    cache = selection._build_reference_selection_cache(reference)
    assert cache.eligible_feature_indices == tuple(range(5_000))
    result = selection.select_fold_stable_genes(reference, training_records=reference.records)
    assert source_reference.nuisance_a in result.union_feature_indices
    assert source_reference.nuisance_b in result.union_feature_indices
    assert len(result.union_feature_indices) == 24


@pytest.mark.parametrize(
    "mutation", ["excluded", "duplicate", "negative", "outside", "boolean", "one"]
)
def test_direct_fitter_cannot_bypass_feature_admission_before_count_slicing(
    monkeypatch, source_reference, mutation
):
    fixture = source_reference
    admitted = fixture.eligible[0]
    indices = {
        "excluded": (fixture.nuisance_a, admitted),
        "duplicate": (admitted, admitted),
        "negative": (-1, admitted),
        "outside": (5_000, admitted),
        "boolean": (True, admitted),
        "one": (admitted,),
    }[mutation]
    with monkeypatch.context() as guarded:
        guarded.setattr(training.np, "asarray", _forbidden)
        with pytest.raises(GbmapInputError, match="identity admission"):
            training._fit_label(
                fixture.reference.records,
                reference=fixture.reference,
                label="lineage-a",
                feature_indices=indices,
                background=None,
                shrinkage=1.0,
                configuration=training.DEFAULT_TRAINING_CONFIGURATION.hierarchy,
                cancellation=None,
            )


def test_direct_fitter_requires_reference_owned_records(monkeypatch, source_reference):
    reference = source_reference.reference
    foreign = replace(reference.records[0])
    monkeypatch.setattr(training, "fit_lineage_hierarchy", _forbidden)
    with pytest.raises(GbmapInputError, match="exact aggregate reference"):
        training._fit_label(
            (foreign,),
            reference=reference,
            label=foreign.modeled_label,
            feature_indices=source_reference.eligible[:2],
            background=np.asarray((0.5, 0.5)),
            shrinkage=1.0,
            configuration=training.DEFAULT_TRAINING_CONFIGURATION.hierarchy,
            cancellation=None,
        )


def test_direct_fitter_preserves_selected_source_index_order(monkeypatch, source_reference):
    fixture = source_reference
    selected = (fixture.markers_b[0], fixture.markers_a[0])
    observed = []
    sentinel = object()

    def fit(counts, studies, background, **_kwargs):
        observed.append((counts.copy(), studies, background.copy()))
        return sentinel

    monkeypatch.setattr(training, "fit_lineage_hierarchy", fit)
    actual = training._fit_label(
        fixture.reference.records,
        reference=fixture.reference,
        label="lineage-a",
        feature_indices=selected,
        background=np.asarray((0.5, 0.5)),
        shrinkage=1.0,
        configuration=training.DEFAULT_TRAINING_CONFIGURATION.hierarchy,
        cancellation=None,
    )
    assert actual is sentinel
    assert observed[0][0].shape == (12, 2)
    assert np.array_equal(observed[0][0], np.tile((50, 600), (12, 1)))
    assert all(record.gene_counts.shape == (5_000,) for record in fixture.reference.records)


def test_prepared_fold_carries_the_exact_reference_for_task_fitting(source_reference):
    reference = source_reference.reference
    plan = build_validation_split_plan(reference)
    fold = next(item for item in plan.folds if item.evaluable)
    prepared = training._prepare_fold(reference, plan, fold, None)
    assert isinstance(prepared, training._PreparedFold)
    assert prepared.reference is reference
    assert set(prepared.feature_indices) <= set(source_reference.eligible)
    assert len(prepared.feature_indices) == 24


def test_final_fit_rejects_injected_unadmitted_axis_before_background(
    monkeypatch, source_reference
):
    fixture = source_reference
    monkeypatch.setattr(
        training, "_selected_features", lambda *_: (fixture.nuisance_a, fixture.eligible[0])
    )
    monkeypatch.setattr(training, "_equal_label_study_background", _forbidden)
    with pytest.raises(GbmapInputError, match="identity admission"):
        training._final_fit(fixture.reference, 1.0, training.DEFAULT_TRAINING_CONFIGURATION, None)


def test_training_entry_rejects_wrong_production_axis_before_split_planning(
    monkeypatch, source_reference
):
    reference = source_reference.reference
    changed = replace(reference, feature_ids=tuple(reversed(reference.feature_ids)))
    monkeypatch.setattr(training, "build_validation_split_plan", _forbidden)
    with pytest.raises(GbmapInputError, match="crosswalk order"):
        training.train_development_candidate(changed)
