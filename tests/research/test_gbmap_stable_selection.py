"""Independent oracles for fold-local GBmap stable-gene selection."""

from __future__ import annotations

import math
from typing import Any, cast
from unittest.mock import patch

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution import selection as selection_module
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
    largest_remainder_scale,
)
from glio_proteogen.research.gbmap_deconvolution.errors import GbmapInputError
from glio_proteogen.research.gbmap_deconvolution.selection import (
    MAD_SCALE,
    MAX_GENES_PER_LABEL,
    MAX_UNION_GENES,
    MIN_DONOR_POSITIVE_FRACTION,
    MIN_LABEL_MARGIN,
    MIN_MEDIAN_DETECTION_FRACTION,
    MIN_MEDIAN_LOG2_ENRICHMENT,
    MIN_STUDY_POSITIVE_MEDIAN_FRACTION,
    SELECTION_PSEUDOCOUNT,
    StableGeneSelection,
    _build_reference_selection_cache,
    _select_fold_stable_genes_precomputed,
    select_fold_stable_genes,
    stable_gene_passes_gates,
    stable_gene_score,
)

_DIGEST_A = "sha256:" + "a" * 64
_DIGEST_B = "sha256:" + "b" * 64
_DIGEST_C = "sha256:" + "c" * 64


def _record(  # noqa: PLR0913 - compact fold-selection fixture factory.
    donor: str,
    study: str,
    label: str,
    counts: tuple[int, ...],
    *,
    detected: tuple[int, ...] | None = None,
    cells: int = 100,
) -> DonorLabelAggregate:
    gene_counts = np.asarray(counts, dtype=np.int64)
    detected_counts = np.asarray(
        detected if detected is not None else tuple(min(value, 80, cells) for value in counts),
        dtype=np.int32,
    )
    return DonorLabelAggregate(
        donor_key=donor,
        study_key=study,
        modeled_label=label,
        source_labels=(f"{label}-source",),
        cell_count=cells,
        gene_counts=gene_counts,
        detected_cell_counts=detected_counts,
        total_umis=sum(counts),
    )


def _reference(
    feature_ids: tuple[str, ...],
    records: tuple[DonorLabelAggregate, ...],
) -> AggregateReference:
    return AggregateReference(
        feature_ids=feature_ids,
        gene_symbols=tuple(f"SYMBOL_{feature_id}" for feature_id in feature_ids),
        records=records,
        source_file_sha256=_DIGEST_A,
        source_bytes=8_975_644_082,
        taxonomy_digest=_DIGEST_B,
        extraction_recipe_digest=_DIGEST_C,
    )


def _oracle_reference(*, include_held: bool = False) -> tuple[AggregateReference, tuple[str, ...]]:
    features = (
        "A_STABLE",
        "B_STABLE",
        "C_STABLE",
        "A_ONE_STUDY",
        "A_LOW_DETECTION",
        "A_LOW_MARGIN",
        "FILLER",
    )
    records: list[DonorLabelAggregate] = []
    training_donors: list[str] = []
    for index in range(13):
        donor = f"train-{index:02d}"
        training_donors.append(donor)
        study = "study-1" if index < 10 else f"study-{index - 8}"
        confounded = 5_000 if study == "study-1" else 200
        a_counts = (4_000, 400, 400, confounded, 4_000, 3_000, 0)
        a_counts = (*a_counts[:-1], 20_000 - sum(a_counts[:-1]))
        b_counts = (400, 4_000, 400, 1_000, 200, 2_600, 11_400)
        c_counts = (400, 400, 4_000, 1_000, 200, 100, 13_900)
        a_detected = tuple(min(value, 80) for value in a_counts)
        a_detected = (*a_detected[:4], 5, *a_detected[5:])
        records.extend(
            (
                _record(donor, study, "lineage-a", a_counts, detected=a_detected),
                _record(donor, study, "lineage-b", b_counts),
                _record(donor, study, "lineage-c", c_counts),
            )
        )
    if include_held:
        records.extend(
            (
                _record(
                    "held-extreme",
                    "study-held",
                    "lineage-a",
                    (100, 100, 100, 19_000, 100, 100, 400),
                ),
                _record(
                    "held-extreme",
                    "study-held",
                    "lineage-b",
                    (100, 100, 100, 10, 100, 100, 19_490),
                ),
                _record(
                    "held-extreme",
                    "study-held",
                    "lineage-c",
                    (100, 100, 100, 10, 100, 100, 19_490),
                ),
            )
        )
    return _reference(features, tuple(records)), tuple(training_donors)


def _label(selection: StableGeneSelection, label: str) -> tuple[str, ...]:
    item = next(value for value in selection.by_label if value.modeled_label == label)
    return tuple(gene.feature_id for gene in item.genes)


def test_source_oracle_rejects_one_study_confounding_detection_and_margin() -> None:
    reference, donors = _oracle_reference()
    studies = ("study-1", "study-2", "study-3", "study-4")

    selection = select_fold_stable_genes(
        reference,
        training_donor_keys=donors,
        training_study_keys=studies,
    )

    assert "A_STABLE" in _label(selection, "lineage-a")
    assert "B_STABLE" in _label(selection, "lineage-b")
    assert "C_STABLE" in _label(selection, "lineage-c")
    assert "A_ONE_STUDY" not in selection.union_feature_ids
    assert "A_LOW_DETECTION" not in selection.union_feature_ids
    assert "A_LOW_MARGIN" not in selection.union_feature_ids
    a_stable = next(
        gene for item in selection.by_label for gene in item.genes if gene.feature_id == "A_STABLE"
    )
    expected_median = math.log2((4_000 + 32) / (400 + 32))
    assert a_stable.median_log2_enrichment == pytest.approx(expected_median, abs=1e-15)
    assert a_stable.donor_positive_fraction == 1.0
    assert a_stable.study_positive_median_fraction == 1.0
    assert a_stable.median_detection_fraction == 0.8
    assert a_stable.mad_log2_enrichment == 0.0


def test_held_records_cannot_enter_and_partition_order_is_invariant() -> None:
    training_only, donors = _oracle_reference()
    with_held, held_training_donors = _oracle_reference(include_held=True)
    studies = ("study-1", "study-2", "study-3", "study-4")
    before = tuple(record.gene_counts.copy() for record in with_held.records)

    baseline = select_fold_stable_genes(
        training_only,
        training_donor_keys=donors,
        training_study_keys=studies,
    )
    key_reordered = select_fold_stable_genes(
        with_held,
        training_donor_keys=tuple(reversed(held_training_donors)),
        training_study_keys=tuple(reversed(studies)),
    )
    admitted_records = tuple(
        record for record in with_held.records if record.donor_key in set(donors)
    )
    record_reordered = select_fold_stable_genes(
        with_held,
        training_records=tuple(reversed(admitted_records)),
    )

    assert key_reordered == baseline
    assert record_reordered == baseline
    assert "held-extreme" not in key_reordered.training_donor_keys
    for record, original in zip(with_held.records, before, strict=True):
        assert np.array_equal(record.gene_counts, original)
        assert not record.gene_counts.flags.writeable


def test_reference_cache_reuses_exact_transforms_without_held_fold_leakage() -> None:
    training_only, donors = _oracle_reference()
    with_held, held_training_donors = _oracle_reference(include_held=True)
    studies = ("study-1", "study-2", "study-3", "study-4")
    baseline = select_fold_stable_genes(
        training_only,
        training_donor_keys=donors,
        training_study_keys=studies,
    )
    admitted_records = tuple(
        record for record in with_held.records if record.donor_key in set(donors)
    )
    untyped_selection = cast("Any", selection_module)

    with patch.object(
        selection_module,
        "_largest_remainder_scale_prevalidated",
        wraps=untyped_selection._largest_remainder_scale_prevalidated,
    ) as scale:
        cache = _build_reference_selection_cache(with_held)
        construction_calls = scale.call_count
        key_result = _select_fold_stable_genes_precomputed(
            with_held,
            cache,
            training_donor_keys=tuple(reversed(held_training_donors)),
            training_study_keys=tuple(reversed(studies)),
        )
        record_result = _select_fold_stable_genes_precomputed(
            with_held,
            cache,
            training_records=tuple(reversed(admitted_records)),
        )

    assert construction_calls == len(cache.normalized)
    assert construction_calls == sum(record.eligible_for_reference for record in with_held.records)
    assert scale.call_count == construction_calls
    assert key_result == baseline
    assert record_result == baseline
    assert "held-extreme" not in key_result.training_donor_keys

    admitted = admitted_records[0]
    normalized = cache.normalized[id(admitted)]
    expected = np.asarray(
        largest_remainder_scale(admitted.gene_counts, with_held.feature_ids),
        dtype=np.float64,
    )
    assert np.array_equal(normalized, expected)
    assert not normalized.flags.writeable
    detection = cache.detections[id(admitted)]
    assert np.array_equal(
        detection,
        admitted.detected_cell_counts.astype(np.float64) / float(admitted.cell_count),
    )
    assert not detection.flags.writeable

    with pytest.raises(GbmapInputError, match="does not bind"):
        _select_fold_stable_genes_precomputed(
            training_only,
            cache,
            training_donor_keys=donors,
            training_study_keys=studies,
        )


def test_same_study_other_donor_fallback_is_equal_depth_and_training_only() -> None:
    features = ("A_MARK", "B_MARK", "FILLER")
    fallback_reference = _reference(
        features,
        (
            _record("a-only", "study-1", "lineage-a", (6_000, 500, 13_500)),
            _record("b-only", "study-1", "lineage-b", (500, 6_000, 13_500)),
            _record("held-b", "study-2", "lineage-b", (19_000, 100, 900)),
        ),
    )
    fallback = select_fold_stable_genes(
        fallback_reference,
        training_donor_keys=("a-only", "b-only"),
        training_study_keys=("study-1",),
    )

    matched_reference = _reference(
        features,
        (
            _record("matched", "study-1", "lineage-a", (6_000, 500, 13_500)),
            _record("matched", "study-1", "lineage-b", (500, 6_000, 13_500)),
        ),
    )
    matched = select_fold_stable_genes(
        matched_reference,
        training_donor_keys=("matched",),
        training_study_keys=("study-1",),
    )

    assert _label(fallback, "lineage-a") == ("A_MARK",)
    assert _label(fallback, "lineage-b") == ("B_MARK",)
    assert fallback.union_feature_ids == matched.union_feature_ids
    for fallback_label, matched_label in zip(fallback.by_label, matched.by_label, strict=True):
        for fallback_gene, matched_gene in zip(
            fallback_label.genes,
            matched_label.genes,
            strict=True,
        ):
            assert fallback_gene.feature_id == matched_gene.feature_id
            assert fallback_gene.score == matched_gene.score
            assert fallback_gene.median_log2_enrichment == (matched_gene.median_log2_enrichment)


def test_fixed_thresholds_are_inclusive_and_score_matches_independent_formula() -> None:
    threshold_values: dict[str, float] = {
        "median_log2_enrichment": MIN_MEDIAN_LOG2_ENRICHMENT,
        "donor_positive_fraction": MIN_DONOR_POSITIVE_FRACTION,
        "study_positive_median_fraction": MIN_STUDY_POSITIVE_MEDIAN_FRACTION,
        "median_detection_fraction": MIN_MEDIAN_DETECTION_FRACTION,
        "label_margin": MIN_LABEL_MARGIN,
    }
    assert stable_gene_passes_gates(**threshold_values)
    for name, value in threshold_values.items():
        below = {**threshold_values, name: float(np.nextafter(value, -np.inf))}
        assert not stable_gene_passes_gates(**below)

    score = stable_gene_score(
        median_log2_enrichment=1.25,
        donor_stability=0.8,
        study_stability=0.75,
        median_detection_fraction=0.36,
        mad_log2_enrichment=0.2,
    )
    expected = 1.25 * 0.8 * 0.75 * math.sqrt(0.36) / (1.0 + MAD_SCALE * 0.2)
    assert score == pytest.approx(expected, rel=0.0, abs=1e-15)
    assert SELECTION_PSEUDOCOUNT == 32.0

    invalid = (
        {**threshold_values, "median_log2_enrichment": True},
        {**threshold_values, "donor_positive_fraction": 1.01},
        {**threshold_values, "study_positive_median_fraction": float("nan")},
        {**threshold_values, "median_detection_fraction": -0.01},
        {**threshold_values, "label_margin": float("inf")},
    )
    for values in invalid:
        with pytest.raises(GbmapInputError):
            stable_gene_passes_gates(**values)


def test_per_label_and_union_caps_use_exact_feature_identifier_ties() -> None:
    labels = tuple(f"lineage-{index:02d}" for index in range(17))
    marker_ids = tuple(
        f"F{label_index:02d}_{marker_index:02d}"
        for label_index in range(len(labels))
        for marker_index in range(40)
    )
    features = (*marker_ids, "ZZ_FILLER")
    records: list[DonorLabelAggregate] = []
    for label_index, label in enumerate(labels):
        counts = [1] * len(marker_ids)
        start = label_index * 40
        for index in range(start, start + 40):
            counts[index] = 400
        counts.append(20_000 - sum(counts))
        detected = [min(value, 50) for value in counts]
        records.append(
            _record(
                "shared-donor",
                "shared-study",
                label,
                tuple(counts),
                detected=tuple(detected),
            )
        )
    reference = _reference(features, tuple(reversed(records)))

    selection = select_fold_stable_genes(
        reference,
        training_donor_keys=("shared-donor",),
        training_study_keys=("shared-study",),
    )

    assert sum(item.pre_union_selected_count for item in selection.by_label) == 17 * 32
    assert all(item.passing_gene_count == 40 for item in selection.by_label)
    assert all(item.pre_union_selected_count == MAX_GENES_PER_LABEL for item in selection.by_label)
    assert len(selection.union_feature_ids) == MAX_UNION_GENES
    expected = tuple(
        sorted(
            feature_id
            for label_index in range(17)
            for feature_id in marker_ids[label_index * 40 : label_index * 40 + 32]
        )[:MAX_UNION_GENES]
    )
    assert selection.union_feature_ids == expected
    assert _label(selection, "lineage-00") == tuple(f"F00_{index:02d}" for index in range(32))
    assert _label(selection, "lineage-16") == ()


def test_partition_and_comparator_inputs_are_strictly_validated() -> None:
    reference = _reference(
        ("A", "B", "FILLER"),
        (
            _record("d1", "s1", "a", (6_000, 500, 13_500)),
            _record("d1", "s1", "b", (500, 6_000, 13_500)),
            _record("d2", "s2", "a", (6_000, 500, 13_500)),
            _record("d3", "s3", "b", (500, 6_000, 13_500)),
        ),
    )
    with pytest.raises(GbmapInputError, match="either training_records"):
        select_fold_stable_genes(reference)
    with pytest.raises(GbmapInputError, match="either training_records"):
        select_fold_stable_genes(
            reference,
            training_donor_keys=("d1",),
        )
    with pytest.raises(GbmapInputError, match="either training_records"):
        select_fold_stable_genes(
            reference,
            training_donor_keys=("d1",),
            training_study_keys=("s1",),
            training_records=(reference.records[0],),
        )
    with pytest.raises(GbmapInputError, match="outside the reference"):
        select_fold_stable_genes(
            reference,
            training_donor_keys=("unknown",),
            training_study_keys=("s1",),
        )
    with pytest.raises(GbmapInputError, match="exactly match"):
        select_fold_stable_genes(
            reference,
            training_donor_keys=("d1",),
            training_study_keys=("s2",),
        )
    with pytest.raises(GbmapInputError, match="exact tuple"):
        select_fold_stable_genes(
            reference,
            training_donor_keys=cast("Any", ["d1"]),
            training_study_keys=("s1",),
        )

    cloned = _record("d1", "s1", "a", (6_000, 500, 13_500))
    with pytest.raises(GbmapInputError, match="outside the reference"):
        select_fold_stable_genes(reference, training_records=(cloned,))
    with pytest.raises(GbmapInputError, match="duplicate"):
        select_fold_stable_genes(
            reference,
            training_records=(reference.records[0], reference.records[0]),
        )
    with pytest.raises(GbmapInputError, match="at least two modeled labels"):
        select_fold_stable_genes(reference, training_records=(reference.records[0],))
    with pytest.raises(GbmapInputError, match="neither a same-donor comparator"):
        select_fold_stable_genes(
            reference,
            training_records=(reference.records[0], reference.records[3]),
        )


def test_ineligible_training_study_cannot_silently_enter_metrics() -> None:
    low_depth = _record("low", "study-low", "a", (10_000, 500, 8_500))
    reference = _reference(
        ("A", "B", "FILLER"),
        (
            _record("good", "study-good", "a", (6_000, 500, 13_500)),
            _record("good", "study-good", "b", (500, 6_000, 13_500)),
            low_depth,
        ),
    )
    with pytest.raises(GbmapInputError, match="every training study"):
        select_fold_stable_genes(
            reference,
            training_donor_keys=("good", "low"),
            training_study_keys=("study-good", "study-low"),
        )
