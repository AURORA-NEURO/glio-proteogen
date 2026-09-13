"""End-to-end oracles for the unfitted-release GBmap training protocol."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from functools import lru_cache
from typing import Any, cast
from unittest.mock import patch

import numpy as np
import pytest

from glio_proteogen.research.gbmap_deconvolution import training as training_module
from glio_proteogen.research.gbmap_deconvolution.aggregate import (
    AggregateReference,
    DonorLabelAggregate,
)
from glio_proteogen.research.gbmap_deconvolution.hierarchy import (
    HierarchySolverConfiguration,
)
from glio_proteogen.research.gbmap_deconvolution.training import (
    CandidateFoldEvaluation,
    DevelopmentTrainingResult,
    ShrinkageCandidateEvaluation,
    TrainingConfiguration,
    train_development_candidate,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
)


@lru_cache(maxsize=1)
def _reference() -> AggregateReference:
    feature_ids = tuple(f"ENSG{index:05d}" for index in range(24))
    malignant = np.asarray([1_500] * 12 + [166] * 11 + [174], dtype=np.int64)
    myeloid = np.asarray([166] * 11 + [174] + [1_500] * 12, dtype=np.int64)
    records: list[DonorLabelAggregate] = []
    for study_index in range(4):
        for donor_index in range(3):
            donor = f"donor-{study_index}-{donor_index:02d}"
            for label, counts in (("malignant", malignant), ("myeloid", myeloid)):
                records.append(
                    DonorLabelAggregate(
                        donor_key=donor,
                        study_key=f"study-{study_index}",
                        modeled_label=label,
                        source_labels=(label,),
                        cell_count=40,
                        gene_counts=counts,
                        detected_cell_counts=np.asarray([30] * 24, dtype=np.int32),
                        total_umis=20_000,
                    )
                )
    return AggregateReference(
        feature_ids=feature_ids,
        gene_symbols=feature_ids,
        records=tuple(records),
        source_file_sha256="sha256:" + "1" * 64,
        source_bytes=8_975_644_082,
        taxonomy_digest="sha256:" + "2" * 64,
        extraction_recipe_digest="sha256:" + "3" * 64,
    )


@lru_cache(maxsize=1)
def _trained() -> DevelopmentTrainingResult:
    hierarchy = HierarchySolverConfiguration(
        max_outer_iterations=6,
        max_study_sweeps=2,
        max_signature_iterations=20,
        max_golden_iterations=12,
        golden_log_tolerance=1e-4,
        kkt_tolerance=2e-6,
    )
    return train_development_candidate(
        _reference(),
        configuration=TrainingConfiguration(
            shrinkage_grid=(1.0,),
            minimum_whole_study_folds=1,
            minimum_within_study_donor_folds=1,
            hierarchy=hierarchy,
        ),
    )


def test_training_builds_one_reference_transform_cache() -> None:
    untyped_training = cast("Any", training_module)
    with patch.object(
        training_module,
        "_build_reference_selection_cache",
        wraps=untyped_training._build_reference_selection_cache,
    ) as build_cache:
        result = _trained()

    assert result.model.modeled_labels == ("malignant", "myeloid")
    assert build_cache.call_count == 1


def test_training_recovers_locked_lineage_marker_directions() -> None:
    result = _trained()
    malignant, myeloid = result.model.signature_matrix

    assert result.model.modeled_labels == ("malignant", "myeloid")
    assert len(result.model.feature_ids) == 24
    assert float(np.mean(malignant[:12])) > float(np.mean(malignant[12:]))
    assert float(np.mean(myeloid[12:])) > float(np.mean(myeloid[:12]))
    assert np.all(result.model.concentrations > 0.0)
    assert not result.model.signature_matrix.flags.writeable
    assert not result.model.concentrations.flags.writeable


def test_training_scores_both_validation_families() -> None:
    evaluation = _trained().summary.candidate_evaluations[0]

    assert evaluation.selectable
    assert evaluation.whole_study_fold_count == 4
    assert evaluation.within_study_donor_fold_count == 3
    assert evaluation.selection_score is not None
    assert math.isfinite(evaluation.selection_score)
    assert all(
        fold.state == "evaluated" and fold.evaluated_held_record_count >= 2
        for fold in evaluation.folds
    )


def test_candidate_and_summary_cannot_authorize_release_or_runtime() -> None:
    result = _trained()

    assert result.model.fit_state == "development_candidate_unadmitted"
    assert result.summary.fit_state == "development_candidate_unadmitted"
    assert result.model.production_artifact_permitted is False
    assert result.model.runtime_mount_permitted is False
    assert result.summary.production_artifact_permitted is False
    assert result.summary.runtime_mount_permitted is False


def test_retained_training_summary_has_no_donor_identifier_or_donor_hash() -> None:
    document = json.dumps(asdict(_trained().summary), sort_keys=True)

    assert "donor-0-00" not in document
    assert "donor_keys" not in document
    assert "donor_digest" not in document
    assert "aggregate_content_digest" not in document


def test_candidate_thresholds_can_abstain_with_family_scores_present() -> None:
    whole = CandidateFoldEvaluation(
        fold_id="whole-study-0001",
        kind="whole_study",
        shrinkage=1.0,
        state="evaluated",
        abstention_reason=None,
        eligible_lineage_count=2,
        selected_feature_count=24,
        evaluated_held_record_count=4,
        mean_per_count_nll=0.2,
    )
    within = CandidateFoldEvaluation(
        fold_id="within-study-donor-0001",
        kind="within_study_donor",
        shrinkage=1.0,
        state="evaluated",
        abstention_reason=None,
        eligible_lineage_count=2,
        selected_feature_count=24,
        evaluated_held_record_count=4,
        mean_per_count_nll=0.1,
    )

    value = ShrinkageCandidateEvaluation(
        shrinkage=1.0,
        folds=(whole, within),
        whole_study_fold_count=1,
        within_study_donor_fold_count=1,
        minimum_whole_study_folds=3,
        minimum_within_study_donor_folds=5,
        whole_study_mean_nll=0.2,
        within_study_donor_mean_nll=0.1,
        selection_score=None,
        selectable=False,
    )

    assert value.selectable is False


@pytest.mark.parametrize("grid", [(1.0, 1.0), (10.0, 1.0), (True,)])
def test_training_configuration_rejects_ambiguous_shrinkage_grids(
    grid: tuple[float, ...],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        TrainingConfiguration(shrinkage_grid=grid)


def test_training_honors_pre_cancelled_context() -> None:
    cancellation = CancellationContext()
    cancellation.cancel()

    with pytest.raises(InferenceCancelledError, match="cancelled"):
        train_development_candidate(_reference(), cancellation=cancellation)
