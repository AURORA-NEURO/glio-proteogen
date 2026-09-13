"""Scientific and adversarial oracles for functional-proteotype inference."""

from __future__ import annotations

import json

import pytest

from glio_proteogen.research.gbm_functional_proteotype import (
    AXIS_CLASSIFICATION_THRESHOLD,
    AXIS_ORDER,
    AblationKind,
    AnalysisSupport,
    AxisClassification,
    FunctionalProteotypeAxis,
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    ProteinEvidence,
    ProteinEvidenceState,
    ReplayVerificationRequest,
    analyze_functional_proteotype,
    functional_proteotype_catalog,
    verify_replay,
)
from glio_proteogen.research.gbm_functional_proteotype.canonical import (
    bootstrap_computational_digest,
    computational_request_digest,
    permutation_computational_digest,
    sha256_digest,
)
from glio_proteogen.research.gbm_functional_proteotype.profile import (
    algorithm_profile,
    random_stream_profile_digest,
)
from glio_proteogen.research.gbm_functional_proteotype.statistics import (
    benjamini_hochberg,
)

PROVENANCE_DIGEST = sha256_digest({"test": "gbm-functional-proteotype-engine"})
PLANTED_COORDINATES = {
    FunctionalProteotypeAxis.GPM: 1.50,
    FunctionalProteotypeAxis.MTC: 0.50,
    FunctionalProteotypeAxis.NEU: -0.50,
    FunctionalProteotypeAxis.PPR: -1.50,
}
# Five proteins from every source-rank quartile make the permutation null and
# rank-quartile ablations exercise the complete, fixed source design.
PLANTED_SOURCE_INDICES = (
    *range(5),
    *range(38, 43),
    *range(76, 81),
    *range(114, 119),
)


def _planted_request(
    *,
    sample_id: str = "functional.oracle.planted",
    offset: float = 0.0,
    source_indices: tuple[int, ...] = PLANTED_SOURCE_INDICES,
    include_inactive: bool = False,
    include_nonbinding_censor: bool = False,
) -> FunctionalProteotypeRequest:
    catalog = functional_proteotype_catalog()
    observations: list[ProteinEvidence] = []
    for axis in AXIS_ORDER:
        rows = catalog.axes[axis.value]
        planted = PLANTED_COORDINATES[axis]
        observations.extend(
            ProteinEvidence(
                observation_id=f"oracle.{axis.value}.{row.source_rank:03d}",
                gene_symbol=row.gene_symbol,
                state=ProteinEvidenceState.OBSERVED,
                standardized_effect=offset + planted * row.source_loading,
                standard_error=0.20 + 0.01 * (row.source_rank % 3),
                quality_weight=0.90,
                provenance_digest=PROVENANCE_DIGEST,
            )
            for row in (rows[index] for index in source_indices)
        )
        if include_inactive:
            missing = rows[5]
            unsupported = rows[6]
            observations.extend(
                (
                    ProteinEvidence(
                        observation_id=f"oracle.{axis.value}.missing",
                        gene_symbol=missing.gene_symbol,
                        state=ProteinEvidenceState.MISSING,
                        quality_weight=0.0,
                        provenance_digest=PROVENANCE_DIGEST,
                    ),
                    ProteinEvidence(
                        observation_id=f"oracle.{axis.value}.unsupported",
                        gene_symbol=unsupported.gene_symbol,
                        state=ProteinEvidenceState.UNSUPPORTED,
                        quality_weight=0.0,
                        provenance_digest=PROVENANCE_DIGEST,
                    ),
                )
            )
        if include_nonbinding_censor:
            censored = rows[7]
            observations.append(
                ProteinEvidence(
                    observation_id=f"oracle.{axis.value}.positive-upper-limit",
                    gene_symbol=censored.gene_symbol,
                    state=ProteinEvidenceState.LEFT_CENSORED,
                    standardized_effect=10.0,
                    standard_error=0.20,
                    quality_weight=0.90,
                    provenance_digest=PROVENANCE_DIGEST,
                )
            )
    return FunctionalProteotypeRequest(
        sample_id=sample_id,
        observations=tuple(observations),
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_reference_id="functional.oracle.reference",
    )


def _coordinates(
    result: FunctionalProteotypeResult,
) -> dict[FunctionalProteotypeAxis, float]:
    return {item.axis: item.estimate for item in result.solver.axis_coordinates}


@pytest.fixture(scope="module")
def planted_case() -> tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult]:
    request = _planted_request()
    return request, analyze_functional_proteotype(request)


@pytest.fixture(scope="module")
def offset_result() -> FunctionalProteotypeResult:
    return analyze_functional_proteotype(
        _planted_request(sample_id="functional.oracle.offset", offset=2.75)
    )


def test_joint_solver_recovers_planted_axis_coordinates(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    _request, result = planted_case
    coordinates = _coordinates(result)
    assert result.solver.converged
    assert result.solver.sum_to_zero_residual == pytest.approx(0.0, abs=1e-9)
    assert result.solver.final_objective <= result.solver.initial_objective + 1e-9
    for axis, truth in PLANTED_COORDINATES.items():
        assert coordinates[axis] == pytest.approx(truth, abs=0.03)
    assert coordinates[FunctionalProteotypeAxis.GPM] > coordinates[
        FunctionalProteotypeAxis.MTC
    ] > coordinates[FunctionalProteotypeAxis.NEU] > coordinates[
        FunctionalProteotypeAxis.PPR
    ]
    evidence = {item.axis: item for item in result.axis_evidence}
    assert all(item.support is not AnalysisSupport.ABSTAINED for item in evidence.values())
    assert evidence[FunctionalProteotypeAxis.GPM].classification is (
        AxisClassification.SOURCE_ALIGNED
    )
    assert evidence[FunctionalProteotypeAxis.PPR].classification is (
        AxisClassification.SOURCE_OPPOSED
    )


def test_joint_axis_coordinates_are_invariant_to_global_effect_offset(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    offset_result: FunctionalProteotypeResult,
) -> None:
    _request, baseline = planted_case
    baseline_coordinates = _coordinates(baseline)
    shifted_coordinates = _coordinates(offset_result)
    for axis in AXIS_ORDER:
        assert shifted_coordinates[axis] == pytest.approx(
            baseline_coordinates[axis],
            abs=2e-5,
        )
    assert offset_result.solver.intercept - baseline.solver.intercept == pytest.approx(
        2.75,
        abs=2e-5,
    )
    for baseline_axis, shifted_axis in zip(
        baseline.axis_evidence,
        offset_result.axis_evidence,
        strict=True,
    ):
        assert baseline_axis.rank is not None and shifted_axis.rank is not None
        assert shifted_axis.rank.u_statistic == baseline_axis.rank.u_statistic
        assert shifted_axis.rank.rank_biserial == baseline_axis.rank.rank_biserial
        assert shifted_axis.rank.tie_correction == baseline_axis.rank.tie_correction


def test_input_order_replay_and_bootstrap_are_exactly_deterministic(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    request, expected = planted_case
    reordered = request.model_copy(update={"observations": tuple(reversed(request.observations))})
    actual = analyze_functional_proteotype(reordered)
    assert reordered.request_digest == request.request_digest
    assert actual == expected
    assert actual.provenance.bootstrap_seed == expected.provenance.bootstrap_seed
    assert actual.provenance.permutation_seed == expected.provenance.permutation_seed
    assert tuple(item.latent for item in actual.axis_evidence) == tuple(
        item.latent for item in expected.axis_evidence
    )
    assert all(
        item.latent is not None
        and item.latent.bootstrap_replicates_used == request.bootstrap_replicates
        for item in actual.axis_evidence
    )
    verification = verify_replay(
        ReplayVerificationRequest(request=reordered, result=expected)
    )
    assert verification.verified
    assert verification.request_digest_match
    assert verification.result_digest_match
    assert verification.solver_trace_match
    assert verification.semantic_match


def test_missing_and_unsupported_declarations_do_not_enter_numeric_inference(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    _request, baseline = planted_case
    extended_request = _planted_request(include_inactive=True)
    extended = analyze_functional_proteotype(extended_request)
    assert extended.provenance.computational_digest == baseline.provenance.computational_digest
    assert extended.provenance.bootstrap_seed == baseline.provenance.bootstrap_seed
    assert extended.provenance.permutation_seed == baseline.provenance.permutation_seed
    for axis in AXIS_ORDER:
        assert _coordinates(extended)[axis] == pytest.approx(
            _coordinates(baseline)[axis],
            abs=1e-9,
        )
    for baseline_axis, extended_axis in zip(
        baseline.axis_evidence,
        extended.axis_evidence,
        strict=True,
    ):
        assert extended_axis.evidence_counts.missing_signature_proteins == 1
        assert extended_axis.evidence_counts.unsupported_signature_proteins == 1
        assert extended_axis.evidence_counts.observed_signature_proteins == (
            baseline_axis.evidence_counts.observed_signature_proteins
        )
        assert extended_axis.evidence_counts.observed_background_proteins == (
            baseline_axis.evidence_counts.observed_background_proteins
        )
        assert baseline_axis.rank is not None and extended_axis.rank is not None
        assert extended_axis.latent == baseline_axis.latent
        assert extended_axis.rank == baseline_axis.rank
        assert all(
            driver.evidence_state is ProteinEvidenceState.OBSERVED
            for driver in extended_axis.top_drivers
        )


def test_random_stream_identities_use_only_the_evidence_each_stream_consumes() -> None:
    request = _planted_request()
    random_profile_digest = random_stream_profile_digest(algorithm_profile())
    payload = request.model_dump(mode="json")
    payload["bootstrap_replicates"] = 32
    payload["permutation_replicates"] = 128
    expanded = FunctionalProteotypeRequest.model_validate_json(json.dumps(payload))

    inactive_payload = request.model_dump(mode="json")
    inactive_payload["observations"].append(
        {
            "observation_id": "oracle.unresolved.unsupported",
            "gene_symbol": "UNMAPPED1",
            "state": "unsupported",
            "standardized_effect": None,
            "standard_error": None,
            "quality_weight": 0.0,
            "provenance_digest": PROVENANCE_DIGEST,
        }
    )
    inactive = FunctionalProteotypeRequest.model_validate_json(json.dumps(inactive_payload))

    rank_irrelevant_payload = request.model_dump(mode="json")
    rank_irrelevant_payload["observations"][0]["standard_error"] = 0.75
    rank_irrelevant_payload["observations"][0]["quality_weight"] = 0.55
    rank_irrelevant = FunctionalProteotypeRequest.model_validate_json(
        json.dumps(rank_irrelevant_payload)
    )

    bootstrap_digest = bootstrap_computational_digest(
        request,
        random_profile_digest=random_profile_digest,
    )
    permutation_digest = permutation_computational_digest(
        request,
        random_profile_digest=random_profile_digest,
    )
    for numerically_identical in (expanded, inactive):
        assert (
            computational_request_digest(
                numerically_identical,
                random_profile_digest=random_profile_digest,
            )
            == computational_request_digest(
                request,
                random_profile_digest=random_profile_digest,
            )
        )
        assert (
            bootstrap_computational_digest(
                numerically_identical,
                random_profile_digest=random_profile_digest,
            )
            == bootstrap_digest
        )
        assert (
            permutation_computational_digest(
                numerically_identical,
                random_profile_digest=random_profile_digest,
            )
            == permutation_digest
        )

    assert (
        bootstrap_computational_digest(
            rank_irrelevant,
            random_profile_digest=random_profile_digest,
        )
        != bootstrap_digest
    )
    assert (
        permutation_computational_digest(
            rank_irrelevant,
            random_profile_digest=random_profile_digest,
        )
        == permutation_digest
    )


def test_positive_left_censor_limits_cannot_manufacture_negative_evidence(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    _request, baseline = planted_case
    censored = analyze_functional_proteotype(
        _planted_request(include_nonbinding_censor=True)
    )
    for baseline_axis, censored_axis in zip(
        baseline.axis_evidence,
        censored.axis_evidence,
        strict=True,
    ):
        assert censored_axis.evidence_counts.left_censored_signature_proteins == 1
        assert censored_axis.latent is not None and baseline_axis.latent is not None
        assert censored_axis.latent.estimate == pytest.approx(
            baseline_axis.latent.estimate,
            abs=1e-9,
        )
        assert all(
            driver.evidence_state is ProteinEvidenceState.OBSERVED
            for driver in censored_axis.top_drivers
        )


def test_below_exploratory_axis_support_abstains_without_estimates() -> None:
    request = _planted_request(
        sample_id="functional.oracle.insufficient",
        source_indices=tuple(PLANTED_SOURCE_INDICES[:5]),
    )
    result = analyze_functional_proteotype(request)
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.axis_evidence)
    assert all(
        item.classification is AxisClassification.NOT_ESTIMABLE
        and item.latent is None
        and item.rank is None
        and not item.top_drivers
        and not item.ablations
        and item.abstention_reasons
        for item in result.axis_evidence
    )


def test_interval_classification_and_four_axis_bh_are_coherent(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
) -> None:
    _request, result = planted_case
    p_values: list[float] = []
    q_values: list[float] = []
    for evidence in result.axis_evidence:
        latent = evidence.latent
        rank = evidence.rank
        assert latent is not None and rank is not None
        threshold = AXIS_CLASSIFICATION_THRESHOLD
        if latent.lower_bound > threshold:
            expected = AxisClassification.SOURCE_ALIGNED
        elif latent.upper_bound < -threshold:
            expected = AxisClassification.SOURCE_OPPOSED
        elif latent.lower_bound >= -threshold and latent.upper_bound <= threshold:
            expected = AxisClassification.NEUTRAL
        else:
            expected = AxisClassification.INDETERMINATE
        assert evidence.classification is expected
        assert latent.lower_bound <= latent.estimate <= latent.upper_bound
        p_values.append(rank.empirical_p_value)
        q_values.append(rank.q_value)
        assert rank.q_value >= rank.empirical_p_value
    assert len(p_values) == len(AXIS_ORDER) == 4
    assert tuple(q_values) == pytest.approx(
        benjamini_hochberg(tuple(p_values)),
        abs=2e-6,
    )


def test_ablations_are_complete_and_pathway_rows_never_become_sample_inference(
    planted_case: tuple[FunctionalProteotypeRequest, FunctionalProteotypeResult],
    offset_result: FunctionalProteotypeResult,
) -> None:
    _request, result = planted_case
    catalog = functional_proteotype_catalog()
    assert not result.source_cohort_pathway_inference
    assert not offset_result.source_cohort_pathway_inference
    for evidence, shifted in zip(
        result.axis_evidence,
        offset_result.axis_evidence,
        strict=True,
    ):
        assert {item.kind for item in evidence.ablations} == set(AblationKind)
        assert len({(item.kind, item.target) for item in evidence.ablations}) == len(
            evidence.ablations
        )
        assert evidence.source_cohort_pathway_context == (
            shifted.source_cohort_pathway_context
        )
        expected_rows = catalog.source_cohort_pathway_context[evidence.axis.value][
            : len(evidence.source_cohort_pathway_context)
        ]
        for context, source in zip(
            evidence.source_cohort_pathway_context,
            expected_rows,
            strict=True,
        ):
            assert context.sample_inference_status == "not_evaluated"
            assert context.interpretation == "source_cohort_pathway_context_only"
            assert context.pathway_name == source.pathway
            assert context.source_rank == source.source_rank
            assert context.source_logit_nes == round(source.logit_nes, 6)
            assert context.source_p_value == source.p_value
            assert context.source_q_value == source.q_value
            assert set(context.model_dump()) == {
                "axis",
                "interpretation",
                "pathway_name",
                "sample_inference_status",
                "source_logit_nes",
                "source_p_value",
                "source_q_value",
                "source_rank",
            }
