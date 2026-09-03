from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_neftel_transition.canonical import (
    sha256_digest,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.contracts import (
    AnalysisSupport,
    LongitudinalGbmNeftelTransitionRequest,
    NeftelProgramReplayVerificationRequest,
    ProteinEvidenceState,
    UnverifiedLongitudinalGbmNeftelTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.engine import (
    infer_longitudinal_gbm_neftel_transition,
    semantic_result_projection,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.fitted_catalog import (
    EXPECTED_ARTIFACT_BYTES,
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CONTENT_DIGEST,
    neftel_program_fitted_catalog,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.service import (
    analyze_longitudinal_gbm_neftel_transition,
    verify_longitudinal_gbm_neftel_transition_replay,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.solver import (
    SolverEvidence,
    solve_conditional_coordinates,
)


def test_fitted_catalog_is_exact_deidentified_and_read_only() -> None:
    fitted = neftel_program_fitted_catalog()

    assert fitted.profile_id == "kncc-neftel-program-transition/1.0.0"
    assert fitted.model_id == "kncc-neftel-program-transition-model/1.0.0"
    assert fitted.artifact_bytes == EXPECTED_ARTIFACT_BYTES
    assert fitted.artifact_byte_digest == EXPECTED_ARTIFACT_SHA256
    assert fitted.content_digest == EXPECTED_CONTENT_DIGEST
    assert fitted.program_count == 8
    assert fitted.union_feature_count == 256
    assert fitted.bootstrap_replicate_count == 128
    assert tuple(item.program_id for item in fitted.programs) == (
        "MES2",
        "MES1",
        "AC",
        "OPC",
        "NPC1",
        "NPC2",
        "G1/S",
        "G2/M",
    )
    assert fitted.evaluation["release_gate"] == (
        "limited_fitted_dictionary_not_preferred_to_equal_membership"
    )
    assert fitted.evaluation["individually_supported_program_ids"] == ()
    for array in (
        fitted.reference_design,
        fitted.membership_degree,
        fitted.programs[0].conditional_loading,
        fitted.bootstrap_draw(0).scale,
        fitted.bootstrap_draw(0).effect,
    ):
        assert not array.flags.writeable
        with pytest.raises(ValueError):
            array.flat[0] = 0.0


def test_profile_exposes_failed_equal_membership_comparator_and_claim_ceiling() -> None:
    profile = algorithm_profile()
    evaluation = profile.evaluation

    assert profile.profile_id == "kncc-neftel-program-transition/1.0.0"
    assert profile.counts.program_count == 8
    assert profile.counts.fitted_union_feature_count == 256
    assert profile.counts.marker_fold_count == 5
    assert profile.constants.marker_fold_salt == "kncc-neftel-marker-fold-v1"
    assert profile.constants.minimum_evidence_reliability == 0.05
    assert profile.claim_ceiling == (
        "paired_source_cohort_bulk_protein_program_transition_concordance_only"
    )
    assert evaluation.release_gate == (
        "limited_fitted_dictionary_not_preferred_to_equal_membership"
    )
    assert evaluation.joint_vs_global_median_relative_mae_gain == pytest.approx(0.0261168032)
    assert evaluation.patient_cluster_joint_vs_global_median_gain == pytest.approx(0.0248465156)
    assert evaluation.patient_cluster_joint_vs_global_median_gain_90_interval == (
        0.015326555,
        0.0380342956,
    )
    assert evaluation.joint_vs_equal_median_relative_mae_gain == pytest.approx(-0.105617713)
    assert evaluation.patient_cluster_joint_vs_equal_median_gain == pytest.approx(-0.0987176386)
    assert evaluation.patient_cluster_joint_vs_equal_median_gain_90_interval == (
        -0.1155036986,
        -0.0777444485,
    )
    assert not evaluation.joint_vs_equal_patient_cluster_interval_supports_positive_gain
    assert evaluation.individually_supported_program_count == 0
    assert evaluation.all_leave_program_q05_q95_intervals_cross_zero


def test_solver_matches_direct_small_exact_ridge_solution_and_one_sided_loss() -> None:
    design = np.asarray(
        [[1.0, 0.0], [0.5, 1.0], [-0.5, 1.0], [1.0, -1.0]],
        dtype=np.float64,
    )
    values = np.asarray([0.2, 0.1, -0.1, 0.3], dtype=np.float64)
    reliability = np.asarray([1.0, 0.8, 0.9, 0.7], dtype=np.float64)
    evidence = tuple(
        SolverEvidence(index, float(value), "exact_delta", float(weight))
        for index, (value, weight) in enumerate(zip(values, reliability, strict=True))
    )
    solved = solve_conditional_coordinates(design, evidence)
    direct = np.linalg.solve(
        design.T @ (reliability[:, None] * design) + np.diag([0.25, 1.0]),
        design.T @ (reliability * values),
    )
    assert solved.coordinates == pytest.approx(direct, abs=1e-9)
    assert solved.diagnostics.converged
    assert solved.diagnostics.objective_monotone

    upper = solve_conditional_coordinates(
        np.ones((1, 1), dtype=np.float64),
        (SolverEvidence(0, 1.0, "upper_bound", 1.0),),
    )
    lower = solve_conditional_coordinates(
        np.ones((1, 1), dtype=np.float64),
        (SolverEvidence(0, 1.0, "lower_bound", 1.0),),
    )
    assert upper.coordinates == pytest.approx((0.0,), abs=1e-12)
    assert lower.coordinates[0] > 0.0


def _with_observation_policy(
    *,
    right_state: ProteinEvidenceState,
    quality_weight: float,
) -> LongitudinalGbmNeftelTransitionRequest:
    source = synthetic_demo_request()
    points: list[dict[str, object]] = []
    for point_index, point in enumerate(source.time_points[:2]):
        point_document = point.model_dump(mode="python")
        observations: list[dict[str, object]] = []
        for item in point.observations:
            document = item.model_dump(mode="python")
            document["state"] = ProteinEvidenceState.OBSERVED if point_index == 0 else right_state
            document["quality_weight"] = quality_weight
            observations.append(document)
        point_document["observations"] = tuple(observations)
        points.append(point_document)
    document = source.model_dump(mode="python")
    document["series_id"] = f"neftel.guard.{right_state.value}"
    document["time_points"] = tuple(points)
    document["bootstrap_replicates"] = 32
    return LongitudinalGbmNeftelTransitionRequest.model_validate(document, strict=True)


def test_one_sided_only_evidence_never_yields_an_estimated_coordinate() -> None:
    request = _with_observation_policy(
        right_state=ProteinEvidenceState.LEFT_CENSORED,
        quality_weight=1.0,
    )
    result = analyze_longitudinal_gbm_neftel_transition(request)
    transition = result.transitions[0]

    assert transition.global_transition.support is AnalysisSupport.ABSTAINED
    assert "fewer than 16 exact observed-to-observed" in " ".join(
        transition.global_transition.abstention_reasons
    )
    assert all(item.support is AnalysisSupport.ABSTAINED for item in transition.programs)


def test_subthreshold_reliability_is_not_counted_or_serialized() -> None:
    request = _with_observation_policy(
        right_state=ProteinEvidenceState.OBSERVED,
        quality_weight=1.0e-300,
    )
    result = analyze_longitudinal_gbm_neftel_transition(request)
    transition = result.transitions[0]

    assert transition.global_transition.support is AnalysisSupport.ABSTAINED
    assert transition.global_transition.shared_active_gene_count == 0
    assert all(item.support is AnalysisSupport.ABSTAINED for item in transition.programs)
    assert all(item.active_feature_count == 0 for item in transition.programs)
    assert all(not item.top_contributions for item in transition.programs)


def test_demo_is_order_invariant_limited_and_replay_verifiable() -> None:
    request = synthetic_demo_request()
    first = infer_longitudinal_gbm_neftel_transition(request)
    reordered = request.model_copy(
        update={
            "time_points": tuple(
                point.model_copy(update={"observations": tuple(reversed(point.observations))})
                for point in request.time_points
            )
        }
    )
    second = infer_longitudinal_gbm_neftel_transition(reordered)

    assert request.request_digest == reordered.request_digest
    assert first.result_digest == second.result_digest
    assert semantic_result_projection(first) == semantic_result_projection(second)
    assert sha256_digest(semantic_result_projection(first)) == (
        EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
    )
    assert all(
        transition.global_transition.support is AnalysisSupport.LIMITED
        for transition in first.transitions
    )
    assert all(
        item.support is AnalysisSupport.LIMITED
        and any("equal-membership baseline" in reason for reason in item.abstention_reasons)
        for transition in first.transitions
        for item in transition.programs
    )

    verification = verify_longitudinal_gbm_neftel_transition_replay(
        NeftelProgramReplayVerificationRequest(request=request, result=first)
    )
    assert verification.verified
    assert verification.semantic_match


def test_replay_rejects_a_forged_result_receipt() -> None:
    request = synthetic_demo_request()
    result = infer_longitudinal_gbm_neftel_transition(request)
    document = deepcopy(result.model_dump(mode="python"))
    document["result_digest"] = "sha256:" + "f" * 64
    forged = UnverifiedLongitudinalGbmNeftelTransitionResult.model_construct(**document)
    verification = verify_longitudinal_gbm_neftel_transition_replay(
        NeftelProgramReplayVerificationRequest.model_construct(
            request=request,
            result=forged,
        )
    )
    assert not verification.verified
    assert not verification.result_digest_match
