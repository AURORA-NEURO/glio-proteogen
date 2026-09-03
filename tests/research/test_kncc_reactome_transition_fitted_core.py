from __future__ import annotations

from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping

from glio_proteogen.research.longitudinal_gbm.contracts import (
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    sha256_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    AnalysisSupport,
    LongitudinalGbmReactomeTransitionRequest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.engine import (
    _active_pairs,
    infer_longitudinal_gbm_reactome_transition,
    semantic_result_projection,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.fitted_catalog import (
    EXPECTED_ARTIFACT_BYTES,
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CONTENT_DIGEST,
    reactome_conditional_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.solver import (
    SolverEvidence,
    solve_conditional_coordinates,
)


def test_fitted_catalog_locks_corrected_oracle_and_is_deeply_immutable() -> None:
    catalog = reactome_conditional_fitted_catalog()
    evaluation = catalog.evaluation

    assert catalog.artifact_bytes == EXPECTED_ARTIFACT_BYTES == 4_434_141
    assert catalog.artifact_byte_digest == EXPECTED_ARTIFACT_SHA256
    assert catalog.content_digest == EXPECTED_CONTENT_DIGEST
    assert evaluation["patient_count"] == 104
    assert evaluation["evaluation_count"] == 520
    assert evaluation["minimum_structural_gene_fold_count"] == 356
    assert evaluation["minimum_finite_held_gene_count"] == 310
    assert evaluation["minimum_finite_inference_gene_count"] == 1_279
    assert evaluation["zero_prediction_median_standardized_mae"] == 0.7108931329
    assert evaluation["global_only_median_standardized_mae"] == 0.5622984198
    assert evaluation["joint_median_standardized_mae"] == 0.5554163035
    assert evaluation["median_relative_mae_improvement"] == 0.0120459348
    assert evaluation["evaluation_improved_fraction"] == 0.6653846154
    roles = cast("Mapping[str, object]", evaluation["solver_nonconverged_by_role"])
    assert dict(roles) == {
        "full_patient": 0,
        "global_held_gene": 0,
        "joint_held_gene": 0,
        "leave_pathway_out": 0,
    }
    leave = cast("tuple[Mapping[str, object], ...]", evaluation["leave_pathway_out"])
    assert len(leave) == 10
    assert all(
        cast("float", item["q05"]) <= 0.0 <= cast("float", item["q95"])
        for item in leave
    )

    with pytest.raises(TypeError):
        evaluation["patient_count"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        leave[0]["q05"] = 1.0  # type: ignore[index]
    for array in (
        catalog.reference_design,
        catalog.bootstrap_draw(0).scale,
        catalog.bootstrap_draw(0).effect,
        catalog.pathways[0].conditional_loading,
        catalog.pathways[0].ordinary_conditional_loading,
        catalog.pathways[0].no_degree_conditional_loading,
    ):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.flat[0] = 0.0


def test_solver_matches_direct_small_exact_ridge_solution() -> None:
    design = np.asarray(
        [[1.0, 0.0], [0.5, 1.0], [-0.5, 1.0], [1.0, -1.0]],
        dtype=np.float64,
    )
    values = np.asarray([0.2, 0.1, -0.1, 0.3], dtype=np.float64)
    reliability = np.asarray([1.0, 0.8, 0.9, 0.7], dtype=np.float64)
    evidence = tuple(
        SolverEvidence(index, float(value), "exact_delta", float(weight))
        for index, (value, weight) in enumerate(
            zip(values, reliability, strict=True)
        )
    )
    result = solve_conditional_coordinates(design, evidence)
    penalty = np.diag([0.25, 1.0])
    direct = np.linalg.solve(
        design.T @ (reliability[:, None] * design) + penalty,
        design.T @ (reliability * values),
    )

    assert result.diagnostics.converged
    assert result.diagnostics.objective_monotone
    assert result.diagnostics.iterations < 200
    assert np.asarray(result.coordinates) == pytest.approx(direct, abs=1e-9)


def test_solver_preserves_one_sided_bounds() -> None:
    design = np.ones((1, 1), dtype=np.float64)
    upper = solve_conditional_coordinates(
        design,
        (SolverEvidence(0, 1.0, "upper_bound", 1.0),),
    )
    lower = solve_conditional_coordinates(
        design,
        (SolverEvidence(0, 1.0, "lower_bound", 1.0),),
    )

    assert upper.coordinates == pytest.approx((0.0,), abs=1e-12)
    assert lower.coordinates[0] > 0.0
    assert upper.diagnostics.upper_bound_count == 1
    assert lower.diagnostics.lower_bound_count == 1


def _observation(
    template: ProteinObservation,
    *,
    state: ProteinEvidenceState,
) -> ProteinObservation:
    active = state in {
        ProteinEvidenceState.OBSERVED,
        ProteinEvidenceState.LEFT_CENSORED,
    }
    return ProteinObservation(
        observation_id=template.observation_id,
        gene_symbol=template.gene_symbol,
        state=state,
        log_abundance=template.log_abundance if active else None,
        standard_error=template.standard_error if active else None,
        quality_weight=template.quality_weight if active else 0.0,
        provenance_digest=template.provenance_digest,
    )


def _sparse_censor_request() -> LongitudinalGbmReactomeTransitionRequest:
    demo = synthetic_demo_request()
    left_source = demo.time_points[0].observations[:5]
    right_source = demo.time_points[1].observations[:5]
    left_states = (
        ProteinEvidenceState.LEFT_CENSORED,
        ProteinEvidenceState.OBSERVED,
        ProteinEvidenceState.LEFT_CENSORED,
        ProteinEvidenceState.MISSING,
        ProteinEvidenceState.UNSUPPORTED,
    )
    right_states = (
        ProteinEvidenceState.OBSERVED,
        ProteinEvidenceState.LEFT_CENSORED,
        ProteinEvidenceState.LEFT_CENSORED,
        ProteinEvidenceState.OBSERVED,
        ProteinEvidenceState.OBSERVED,
    )
    left = demo.time_points[0].model_copy(
        update={
            "observations": tuple(
                _observation(item, state=state)
                for item, state in zip(left_source, left_states, strict=True)
            )
        }
    )
    right = demo.time_points[1].model_copy(
        update={
            "observations": tuple(
                _observation(item, state=state)
                for item, state in zip(right_source, right_states, strict=True)
            )
        }
    )
    return LongitudinalGbmReactomeTransitionRequest(
        series_id="reactome.sparse.censor.test",
        assay_compatibility=demo.assay_compatibility,
        normalization_reference=demo.normalization_reference,
        time_points=(left, right),
        bootstrap_replicates=32,
    )


def test_sparse_exact_censor_missing_and_unsupported_semantics() -> None:
    request = _sparse_censor_request()
    catalog = reactome_conditional_fitted_catalog()
    pairs = _active_pairs(request, 0, catalog)

    assert tuple(pair.semantics for pair in pairs) == ("lower_bound", "upper_bound")
    result = infer_longitudinal_gbm_reactome_transition(request)
    transition = result.transitions[0]
    assert transition.global_recurrence.support is AnalysisSupport.ABSTAINED
    assert transition.global_recurrence.shared_active_gene_count == 2
    assert all(path.support is AnalysisSupport.ABSTAINED for path in transition.pathways)
    assert all(
        path.request_reconstruction_evaluable_fold_count == 0
        and path.request_reconstruction_improved_fold_count == 0
        and path.request_reconstruction_median_relative_gain is None
        for path in transition.pathways
    )


def test_demo_engine_is_deterministic_order_invariant_and_oracle_bound() -> None:
    request = synthetic_demo_request()
    first = infer_longitudinal_gbm_reactome_transition(request)
    reordered = request.model_copy(
        update={
            "time_points": tuple(
                point.model_copy(update={"observations": tuple(reversed(point.observations))})
                for point in request.time_points
            )
        }
    )
    second = infer_longitudinal_gbm_reactome_transition(reordered)

    assert request.request_digest == reordered.request_digest
    assert first.result_digest == second.result_digest
    assert semantic_result_projection(first) == semantic_result_projection(second)
    assert (
        sha256_digest(semantic_result_projection(first))
        == EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
    )
    assert all(
        pathway.request_reconstruction_evaluable_fold_count == 5
        for transition in first.transitions
        for pathway in transition.pathways
    )
    assert all(
        pathway.support is AnalysisSupport.LIMITED
        for transition in first.transitions
        for pathway in transition.pathways
    )
    overlap_ablations = tuple(
        ablation
        for transition in first.transitions
        for pathway in transition.pathways
        for ablation in pathway.ablations.overlap
    )
    assert overlap_ablations
    assert all(ablation.removed_feature_count > 0 for ablation in overlap_ablations)
    assert all(
        transition.pathways[2].ablations.overlap for transition in first.transitions
    )
