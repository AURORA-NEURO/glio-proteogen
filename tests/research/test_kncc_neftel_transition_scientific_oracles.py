from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

import numpy as np
import pytest

from glio_proteogen.research.longitudinal_gbm_neftel_transition import fitted_catalog
from glio_proteogen.research.longitudinal_gbm_neftel_transition.contracts import (
    AnalysisSupport,
    GlobalTransitionClassification,
    LongitudinalGbmNeftelTransitionRequest,
    LongitudinalGbmNeftelTransitionResult,
    NeftelProgramReplayVerificationRequest,
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.demo import (
    EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
    synthetic_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.engine import (
    _active_pairs,
    _bootstrap_coordinates,
    _numerical_seed_digest,
    _solver_evidence,
    _uncertainty,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.errors import (
    NeftelConditionalModelIntegrityError,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.profile import (
    algorithm_profile,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.service import (
    analyze_longitudinal_gbm_neftel_transition,
    verify_longitudinal_gbm_neftel_transition_replay,
)
from glio_proteogen.research.longitudinal_gbm_neftel_transition.solver import (
    GLOBAL_RIDGE_MULTIPLIER,
    RIDGE_LAMBDA,
    SolverEvidence,
    solve_conditional_coordinates,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODEL_ARTIFACT = (
    REPOSITORY_ROOT
    / "src"
    / "glio_proteogen"
    / "research"
    / "longitudinal_gbm_neftel_transition"
    / "data"
    / "kncc_neftel_program_transition_model.v1.json"
)
PROGRAM_ORDER = ("MES2", "MES1", "AC", "OPC", "NPC1", "NPC2", "G1/S", "G2/M")


@pytest.fixture(scope="module")
def two_point_demo() -> LongitudinalGbmNeftelTransitionRequest:
    request = synthetic_demo_request()
    return request.model_copy(
        update={"time_points": request.time_points[:2], "bootstrap_replicates": 32}
    )


@pytest.fixture(scope="module")
def analyzed_two_point_demo(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
) -> LongitudinalGbmNeftelTransitionResult:
    return analyze_longitudinal_gbm_neftel_transition(two_point_demo)


def _rewrite_second_time_point(
    request: LongitudinalGbmNeftelTransitionRequest,
    *,
    state: ProteinEvidenceState | None = None,
    quality_weight: float | None = None,
) -> LongitudinalGbmNeftelTransitionRequest:
    points = list(request.time_points)
    rewritten: list[ProteinObservation] = []
    for observation in points[1].observations:
        document = observation.model_dump(mode="python")
        if state is not None:
            document["state"] = state
            if state in {ProteinEvidenceState.MISSING, ProteinEvidenceState.UNSUPPORTED}:
                document["log_abundance"] = None
                document["standard_error"] = None
                document["quality_weight"] = 0.0
        if quality_weight is not None:
            document["quality_weight"] = quality_weight
        rewritten.append(ProteinObservation.model_validate(document, strict=True))
    points[1] = points[1].model_copy(update={"observations": tuple(rewritten)})
    return request.model_copy(update={"time_points": tuple(points)})


def _rewrite_all_quality(
    request: LongitudinalGbmNeftelTransitionRequest,
    quality_weight: float,
) -> LongitudinalGbmNeftelTransitionRequest:
    points = []
    for point in request.time_points:
        observations = []
        for observation in point.observations:
            document = observation.model_dump(mode="python")
            document["quality_weight"] = quality_weight
            observations.append(ProteinObservation.model_validate(document, strict=True))
        points.append(point.model_copy(update={"observations": tuple(observations)}))
    return request.model_copy(update={"time_points": tuple(points)})


def _rewrite_one_gene(
    request: LongitudinalGbmNeftelTransitionRequest,
    gene_symbol: str,
    *,
    unsupported: bool,
) -> LongitudinalGbmNeftelTransitionRequest:
    points = []
    for point_index, point in enumerate(request.time_points):
        observations = []
        for observation in point.observations:
            document = observation.model_dump(mode="python")
            if observation.gene_symbol == gene_symbol:
                if unsupported:
                    document.update(
                        {
                            "state": ProteinEvidenceState.UNSUPPORTED,
                            "log_abundance": None,
                            "standard_error": None,
                            "quality_weight": 0.0,
                        }
                    )
                else:
                    document.update(
                        {
                            "state": ProteinEvidenceState.OBSERVED,
                            "log_abundance": -100.0 if point_index == 0 else 100.0,
                            "standard_error": 0.03,
                            "quality_weight": 0.049,
                        }
                    )
            observations.append(ProteinObservation.model_validate(document, strict=True))
        points.append(point.model_copy(update={"observations": tuple(observations)}))
    return request.model_copy(update={"time_points": tuple(points)})


def test_exact_eight_program_256_feature_inventory_and_claim_ceiling() -> None:
    catalog = fitted_catalog.neftel_program_fitted_catalog()
    profile = algorithm_profile()
    evaluation = profile.evaluation

    assert catalog.program_count == 8
    assert catalog.union_feature_count == 256
    assert catalog.reference_design.shape == (256, 9)
    assert tuple(program.program_id for program in catalog.programs) == PROGRAM_ORDER
    assert {
        position for program in catalog.programs for position in program.member_local_indices
    } == set(range(256))
    assert profile.counts.program_count == 8
    assert profile.counts.fitted_union_feature_count == 256
    assert profile.constants.minimum_evidence_reliability == 0.05
    assert evaluation.release_gate == (
        "limited_fitted_dictionary_not_preferred_to_equal_membership"
    )
    assert evaluation.individually_supported_program_count == 0
    assert evaluation.all_leave_program_q05_q95_intervals_cross_zero
    assert evaluation.joint_vs_global_patient_cluster_interval_supports_positive_gain
    assert not evaluation.joint_vs_equal_patient_cluster_interval_supports_positive_gain
    assert (
        evaluation.equal_membership_median_standardized_mae
        < evaluation.joint_median_standardized_mae
        < evaluation.global_only_median_standardized_mae
        < evaluation.zero_prediction_median_standardized_mae
    )
    assert evaluation.joint_vs_global_median_relative_mae_gain == 0.0261168032
    assert evaluation.joint_vs_equal_median_relative_mae_gain == -0.105617713
    assert evaluation.patient_cluster_joint_vs_global_median_gain_90_interval == (
        0.015326555,
        0.0380342956,
    )
    assert evaluation.patient_cluster_joint_vs_equal_median_gain_90_interval == (
        -0.1155036986,
        -0.0777444485,
    )
    assert profile.claim_ceiling == (
        "paired_source_cohort_bulk_protein_program_transition_concordance_only"
    )
    assert profile.maximum_evidence_grade == ("limited_same_cohort_without_external_validation")
    assert profile.demo_semantic_oracle_digest == EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST


def test_runtime_solver_matches_direct_weighted_ridge_oracle() -> None:
    design = np.asarray(
        [[1.0, 0.0], [0.5, 1.0], [-0.5, 1.0], [1.0, -1.0]],
        dtype=np.float64,
    )
    values = np.asarray([0.20, 0.10, -0.10, 0.30], dtype=np.float64)
    weights = np.asarray([0.9, 0.7, 0.8, 0.6], dtype=np.float64)
    evidence = tuple(
        SolverEvidence(
            feature_position=index,
            value=float(value),
            semantics="exact_delta",
            reliability_weight=float(weight),
        )
        for index, (value, weight) in enumerate(zip(values, weights, strict=True))
    )
    solved = solve_conditional_coordinates(design, evidence)
    penalty = np.diag([GLOBAL_RIDGE_MULTIPLIER, 1.0])
    expected = np.linalg.solve(
        design.T @ (weights[:, None] * design) + RIDGE_LAMBDA * penalty,
        design.T @ (weights * values),
    )

    assert solved.diagnostics.converged
    assert solved.diagnostics.objective_monotone
    assert solved.diagnostics.exact_evidence_count == 4
    assert solved.coordinates == pytest.approx(expected, abs=1.0e-9)


def test_observation_order_is_invariant_and_exact_replay_is_deterministic(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
    analyzed_two_point_demo: LongitudinalGbmNeftelTransitionResult,
) -> None:
    reversed_points = tuple(
        point.model_copy(update={"observations": tuple(reversed(point.observations))})
        for point in two_point_demo.time_points
    )
    reordered = two_point_demo.model_copy(update={"time_points": reversed_points})
    replayed = analyze_longitudinal_gbm_neftel_transition(two_point_demo)
    reordered_result = analyze_longitudinal_gbm_neftel_transition(reordered)

    assert reordered.request_digest == two_point_demo.request_digest
    assert replayed == analyzed_two_point_demo
    assert reordered_result == analyzed_two_point_demo
    verification = verify_longitudinal_gbm_neftel_transition_replay(
        NeftelProgramReplayVerificationRequest(
            request=two_point_demo,
            result=analyzed_two_point_demo,
        )
    )
    assert verification.verified
    assert verification.semantic_match


def test_failed_equal_membership_gate_prevents_supported_estimates(
    analyzed_two_point_demo: LongitudinalGbmNeftelTransitionResult,
) -> None:
    for transition in analyzed_two_point_demo.transitions:
        assert transition.global_transition.support is AnalysisSupport.LIMITED
        assert transition.global_transition.score is not None
        assert any(
            "same-cohort" in reason and "external validation" in reason
            for reason in transition.global_transition.abstention_reasons
        )
        assert all(program.support is AnalysisSupport.LIMITED for program in transition.programs)
        assert all(
            any("equal-membership baseline" in reason for reason in program.abstention_reasons)
            for program in transition.programs
        )


def test_one_sided_only_evidence_abstains_and_never_becomes_stable(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
) -> None:
    one_sided = _rewrite_second_time_point(
        two_point_demo,
        state=ProteinEvidenceState.LEFT_CENSORED,
    )
    result = analyze_longitudinal_gbm_neftel_transition(one_sided)
    transition = result.transitions[0]

    assert transition.global_transition.support is AnalysisSupport.ABSTAINED
    assert (
        transition.global_transition.classification is GlobalTransitionClassification.NOT_ESTIMABLE
    )
    assert any(
        "fewer than 16 exact observed-to-observed" in reason
        for reason in transition.global_transition.abstention_reasons
    )
    assert all(program.support is AnalysisSupport.ABSTAINED for program in transition.programs)
    assert all(program.score is None for program in transition.programs)


def test_missing_and_unsupported_are_excluded_not_negative(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
) -> None:
    missing = analyze_longitudinal_gbm_neftel_transition(
        _rewrite_second_time_point(two_point_demo, state=ProteinEvidenceState.MISSING)
    )
    unsupported = analyze_longitudinal_gbm_neftel_transition(
        _rewrite_second_time_point(two_point_demo, state=ProteinEvidenceState.UNSUPPORTED)
    )

    assert missing.transitions == unsupported.transitions
    for result in (missing, unsupported):
        transition = result.transitions[0]
        assert transition.global_transition.support is AnalysisSupport.ABSTAINED
        assert transition.global_transition.score is None
        assert all(program.support is AnalysisSupport.ABSTAINED for program in transition.programs)
        assert all(program.score is None for program in transition.programs)


def test_subthreshold_absolute_quality_abstains_without_serialization_failure(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
) -> None:
    tiny_quality = _rewrite_all_quality(two_point_demo, 1.0e-300)
    result = analyze_longitudinal_gbm_neftel_transition(tiny_quality)
    transition = result.transitions[0]

    assert transition.global_transition.support is AnalysisSupport.ABSTAINED
    assert transition.global_transition.shared_active_gene_count == 0
    assert all(program.support is AnalysisSupport.ABSTAINED for program in transition.programs)
    assert all(not program.top_contributions for program in transition.programs)


def test_subthreshold_evidence_cannot_influence_scores_bootstraps_or_explanations(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
) -> None:
    fitted_genes = set(fitted_catalog.neftel_program_fitted_catalog().union_gene_symbols)
    gene_symbol = next(
        observation.gene_symbol
        for observation in two_point_demo.time_points[0].observations
        if observation.gene_symbol in fitted_genes
        and observation.state is ProteinEvidenceState.OBSERVED
    )
    subthreshold = analyze_longitudinal_gbm_neftel_transition(
        _rewrite_one_gene(two_point_demo, gene_symbol, unsupported=False)
    )
    unsupported = analyze_longitudinal_gbm_neftel_transition(
        _rewrite_one_gene(two_point_demo, gene_symbol, unsupported=True)
    )

    assert subthreshold.provenance.numerical_seed_digest == (
        unsupported.provenance.numerical_seed_digest
    )
    assert subthreshold.transitions == unsupported.transitions
    assert subthreshold.request_digest != unsupported.request_digest
    assert subthreshold.provenance.caller_evidence_set_digest != (
        unsupported.provenance.caller_evidence_set_digest
    )


def test_maximum_bootstrap_request_is_fully_delivered(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
) -> None:
    result = analyze_longitudinal_gbm_neftel_transition(
        two_point_demo.model_copy(update={"bootstrap_replicates": 256})
    )
    transition = result.transitions[0]

    assert transition.global_transition.bootstrap_replicates_used == 256
    assert all(
        program.uncertainty.bootstrap_replicates_used == 256
        for program in transition.programs
        if program.support is not AnalysisSupport.ABSTAINED
    )


def test_paired_measurement_and_source_model_bootstrap_closure(
    two_point_demo: LongitudinalGbmNeftelTransitionRequest,
    analyzed_two_point_demo: LongitudinalGbmNeftelTransitionResult,
) -> None:
    catalog = fitted_catalog.neftel_program_fitted_catalog()
    active = _active_pairs(two_point_demo, 0, catalog)
    point = solve_conditional_coordinates(
        catalog.reference_design,
        _solver_evidence(active, catalog.reference_scale),
    )
    seed_digest = _numerical_seed_digest(two_point_demo, catalog)
    draws = _bootstrap_coordinates(
        active,
        catalog,
        seed_digest,
        0,
        two_point_demo.bootstrap_replicates,
        cancellation=None,
    )
    program = catalog.programs[0]
    column = program.program_index + 1
    scale = program.cross_fitted_mad_scale
    point_score = point.coordinates[column] / scale
    measurement = tuple(row[column] / scale for row in draws.measurement)
    source_model = tuple(row[column] / scale for row in draws.fitted_model)
    combined = tuple(row[column] / scale for row in draws.combined)
    computed, _, _ = _uncertainty(
        point_score,
        measurement,
        source_model,
        combined,
    )
    reported = analyzed_two_point_demo.transitions[0].programs[0].uncertainty

    measurement_se = float(np.std(np.asarray(measurement), ddof=1))
    source_model_se = float(np.std(np.asarray(source_model), ddof=1))
    combined_se = float(np.std(np.asarray(combined), ddof=1))
    covariance = float(
        np.cov(
            np.asarray(measurement) - point_score,
            np.asarray(source_model) - point_score,
            ddof=1,
        )[0, 1]
    )
    closure = abs(combined_se**2 - measurement_se**2 - source_model_se**2 - 2.0 * covariance)

    assert draws.successful_replicates == two_point_demo.bootstrap_replicates
    assert draws.failed_replicates == 0
    assert set(draws.selected_row_digests) <= set(catalog.bootstrap_row_digests)
    assert computed == reported
    assert reported.measurement_standard_error == pytest.approx(
        round(measurement_se, 8), abs=1.0e-8
    )
    assert reported.fitted_model_standard_error == pytest.approx(
        round(source_model_se, 8), abs=1.0e-8
    )
    assert reported.measurement_model_covariance == pytest.approx(round(covariance, 8), abs=1.0e-8)
    assert reported.combined_standard_error == pytest.approx(round(combined_se, 8), abs=1.0e-8)
    assert reported.variance_closure_residual == pytest.approx(round(closure, 8), abs=1.0e-8)
    assert cast("float", reported.variance_closure_residual) > 0.0


def test_fitted_artifact_contains_no_patient_level_payload() -> None:
    payload = MODEL_ARTIFACT.read_bytes()
    document = cast("dict[str, object]", json.loads(payload))
    forbidden_keys = {
        "patient_groups",
        "patient_ids",
        "patient_hashes",
        "fold_membership",
        "fold_assignments",
        "bootstrap_indices",
        "patient_measurements",
        "patient_scores",
        "patient_residuals",
    }

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            mapping = cast("dict[str, object]", value)
            return set(mapping) | set().union(*(keys(item) for item in mapping.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in cast("list[object]", value)))
        return set()

    assert not (keys(document) & forbidden_keys)
    assert re.search(rb"KNCC_GBM[_-]?\d+", payload, flags=re.IGNORECASE) is None
    assert document["privacy"] == {
        "bootstrap_resample_indices_bundled": False,
        "fold_membership_bundled": False,
        "patient_identifiers_or_hashes_bundled": False,
        "patient_measurements_bundled": False,
        "patient_scores_or_residuals_bundled": False,
    }


def test_fitted_artifact_tamper_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = bytearray(fitted_catalog._resource_bytes())
    payload[100] ^= 1
    fitted_catalog.neftel_program_fitted_catalog.cache_clear()
    with monkeypatch.context() as scoped:
        scoped.setattr(fitted_catalog, "_resource_bytes", lambda: bytes(payload))
        with pytest.raises(
            NeftelConditionalModelIntegrityError,
            match="byte digest mismatch",
        ):
            fitted_catalog.neftel_program_fitted_catalog()
    fitted_catalog.neftel_program_fitted_catalog.cache_clear()
    assert fitted_catalog.neftel_program_fitted_catalog().union_feature_count == 256
