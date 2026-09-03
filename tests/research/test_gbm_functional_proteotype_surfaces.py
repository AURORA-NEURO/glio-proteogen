from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from glio_proteogen.research.gbm_functional_proteotype.canonical import (
    canonical_request_digest,
    computational_request_digest,
    objective_trace_digest,
    sha256_digest,
)
from glio_proteogen.research.gbm_functional_proteotype.catalog import (
    functional_proteotype_catalog,
)
from glio_proteogen.research.gbm_functional_proteotype.contracts import (
    AXIS_ORDER,
    AnalysisSupport,
    AxisClassification,
    AxisEvidenceCounts,
    ConstrainedAxisCoordinate,
    FunctionalProteotypeAxis,
    FunctionalProteotypeRequest,
    ObjectiveTraceStep,
    ProteinEvidence,
    ProteinEvidenceState,
    ReplayVerificationRequest,
    SolverDiagnostics,
    SolverTermination,
    SourceCohortPathwayContext,
    UnverifiedFunctionalProteotypeResult,
)
from glio_proteogen.research.gbm_functional_proteotype.demo import (
    DEMO_ID,
    demo_request_digest,
    synthetic_demo_request,
)
from glio_proteogen.research.gbm_functional_proteotype.profile import (
    EXPECTED_NUMPY_VERSION,
    algorithm_profile,
    random_stream_profile_digest,
)
from glio_proteogen.research.gbm_functional_proteotype.service import (
    analyze_functional_proteotype,
    verify_replay,
)


def _digest(label: str) -> str:
    return sha256_digest({"label": label})


def _observation(
    gene_symbol: str,
    *,
    state: ProteinEvidenceState = ProteinEvidenceState.OBSERVED,
    observation_id: str = "obs.one",
) -> ProteinEvidence:
    active = state in {
        ProteinEvidenceState.OBSERVED,
        ProteinEvidenceState.LEFT_CENSORED,
    }
    return ProteinEvidence(
        observation_id=observation_id,
        gene_symbol=gene_symbol,
        state=state,
        standardized_effect=0.75 if active else None,
        standard_error=0.30 if active else None,
        quality_weight=0.90 if active else 0.0,
        provenance_digest=_digest(observation_id),
    )


def _request(*observations: ProteinEvidence) -> FunctionalProteotypeRequest:
    return FunctionalProteotypeRequest(
        sample_id="synthetic.sample",
        observations=observations,
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_reference_id="synthetic.reference",
    )


def test_evidence_states_preserve_values_censoring_and_absence() -> None:
    gene = functional_proteotype_catalog().axes["GPM"][0].gene_symbol
    observed = _observation(gene)
    censored = _observation(
        functional_proteotype_catalog().axes["GPM"][1].gene_symbol,
        state=ProteinEvidenceState.LEFT_CENSORED,
        observation_id="obs.censored",
    )
    assert observed.standardized_effect == 0.75
    assert censored.standardized_effect == 0.75

    with pytest.raises(ValidationError, match="cannot carry numeric values"):
        ProteinEvidence(
            observation_id="obs.missing",
            gene_symbol=gene,
            state=ProteinEvidenceState.MISSING,
            standardized_effect=0.0,
            quality_weight=0.0,
            provenance_digest=_digest("missing"),
        )
    with pytest.raises(ValidationError, match="must have zero quality"):
        ProteinEvidence(
            observation_id="obs.unsupported",
            gene_symbol="NOTINSOURCE",
            state=ProteinEvidenceState.UNSUPPORTED,
            quality_weight=0.5,
            provenance_digest=_digest("unsupported"),
        )
    with pytest.raises(ValidationError):
        ProteinEvidence.model_validate(
            {
                "observation_id": "obs.coerced",
                "gene_symbol": gene,
                "state": "observed",
                "standardized_effect": "0.75",
                "standard_error": 0.3,
                "quality_weight": 1.0,
                "provenance_digest": _digest("coerced"),
            }
        )


def test_requests_reject_duplicates_and_unresolved_active_genes() -> None:
    gene = functional_proteotype_catalog().axes["GPM"][0].gene_symbol
    with pytest.raises(ValidationError, match="gene symbols must be unique"):
        _request(
            _observation(gene, observation_id="obs.a"),
            _observation(gene, observation_id="obs.b"),
        )
    with pytest.raises(ValidationError, match="must resolve"):
        _request(_observation("NOTINSOURCE"))

    unsupported = _observation(
        "NOTINSOURCE",
        state=ProteinEvidenceState.UNSUPPORTED,
    )
    assert _request(unsupported).observations[0].state is ProteinEvidenceState.UNSUPPORTED


def test_canonical_request_retains_absence_while_numerical_identity_ignores_it() -> None:
    genes = functional_proteotype_catalog().axes["GPM"][:2]
    first = _observation(genes[0].gene_symbol, observation_id="obs.first")
    second = _observation(
        genes[1].gene_symbol,
        state=ProteinEvidenceState.MISSING,
        observation_id="obs.second",
    )
    forward = _request(first, second)
    reverse = _request(second, first)
    assert canonical_request_digest(forward) == canonical_request_digest(reverse)
    assert forward.request_digest == reverse.request_digest

    random_profile_digest = _digest("random-profile")
    missing_digest = computational_request_digest(
        forward,
        random_profile_digest=random_profile_digest,
    )
    unsupported_payload = forward.model_dump(mode="json")
    unsupported_payload["observations"][1]["state"] = "unsupported"
    unsupported = FunctionalProteotypeRequest.model_validate_json(json.dumps(unsupported_payload))
    assert canonical_request_digest(unsupported) != canonical_request_digest(forward)
    assert (
        computational_request_digest(
            unsupported,
            random_profile_digest=random_profile_digest,
        )
        == missing_digest
    )


def test_solver_trace_binds_raw_candidate_and_damped_monotone_trial() -> None:
    step = ObjectiveTraceStep(
        iteration=1,
        baseline_objective=10.0,
        candidate_objective=2.0,
        accepted_objective=4.0,
        damping=0.5,
        accepted=True,
    )
    coordinates = (
        ConstrainedAxisCoordinate(axis=FunctionalProteotypeAxis.GPM, estimate=0.9),
        ConstrainedAxisCoordinate(axis=FunctionalProteotypeAxis.MTC, estimate=0.3),
        ConstrainedAxisCoordinate(axis=FunctionalProteotypeAxis.NEU, estimate=-0.4),
        ConstrainedAxisCoordinate(axis=FunctionalProteotypeAxis.PPR, estimate=-0.8),
    )
    diagnostics = SolverDiagnostics(
        converged=False,
        termination=SolverTermination.MAXIMUM_ITERATIONS,
        iterations=1,
        intercept=0.1,
        axis_coordinates=coordinates,
        sum_to_zero_residual=math.fsum(item.estimate for item in coordinates),
        initial_objective=10.0,
        final_objective=4.0,
        final_gradient_norm=0.2,
        maximum_coordinate_change=0.9,
        objective_trace=(step,),
        objective_trace_digest=objective_trace_digest((step,)),
    )
    assert diagnostics.objective_trace_digest == objective_trace_digest((step,))

    with pytest.raises(ValidationError, match="zero accepted damping"):
        ObjectiveTraceStep(
            iteration=1,
            baseline_objective=10.0,
            candidate_objective=12.0,
            accepted_objective=10.0,
            damping=0.5,
            accepted=False,
        )


def test_counts_and_source_pathway_context_are_non_inferential() -> None:
    counts = AxisEvidenceCounts(
        declared_signature_proteins=4,
        observed_signature_proteins=2,
        left_censored_signature_proteins=1,
        missing_signature_proteins=1,
        unsupported_signature_proteins=0,
        unreported_signature_proteins=146,
        observed_background_proteins=20,
        active_signature_fraction=3 / 150,
    )
    assert counts.observed_signature_proteins == 2
    context = SourceCohortPathwayContext(
        axis=FunctionalProteotypeAxis.GPM,
        source_rank=1,
        pathway_name="GO_CYTOSOLIC_PART",
        source_logit_nes=1.49,
        source_p_value=1e-9,
        source_q_value=2e-8,
    )
    assert context.sample_inference_status == "not_evaluated"
    with pytest.raises(ValidationError):
        SourceCohortPathwayContext.model_validate(
            {
                **context.model_dump(mode="json"),
                "sample_inference_status": "evaluated",
            }
        )


def test_profile_binds_workbook_catalog_algorithms_and_demo() -> None:
    catalog = functional_proteotype_catalog()
    first = algorithm_profile()
    second = algorithm_profile()
    assert first == second
    assert first.numpy_version == EXPECTED_NUMPY_VERSION
    assert first.catalog_content_digest == catalog.content_digest
    assert first.catalog_artifact_digest == catalog.artifact_digest
    assert first.signature_catalog_digest == catalog.signature_catalog_digest
    assert first.pathway_catalog_digest == catalog.pathway_catalog_digest
    assert tuple(item.axis for item in first.axes) == AXIS_ORDER
    assert tuple(item.pathway_count for item in first.axes) == (243, 107, 272, 204)
    assert first.demo_request_digest == demo_request_digest()
    assert first.constants.location_solver == "huber_irls_kkt_sum_to_zero_v1"
    assert first.constants.axis_ridge_penalty != first.constants.intercept_ridge_penalty

    random_identity = random_stream_profile_digest(first)
    source_only_change = first.model_copy(update={"engine_source_digest": _digest("source")})
    assert random_stream_profile_digest(source_only_change) == random_identity
    numerical_change = first.model_copy(
        update={"constants": first.constants.model_copy(update={"huber_delta": 1.5})}
    )
    assert random_stream_profile_digest(numerical_change) != random_identity


def test_demo_uses_only_exact_catalog_genes_and_explicit_states() -> None:
    catalog = functional_proteotype_catalog()
    request = synthetic_demo_request()
    assert request.sample_id == DEMO_ID
    assert request.bootstrap_replicates == 64
    assert request.permutation_replicates == 256
    assert len(request.observations) == 108
    assert all(item.gene_symbol in catalog.by_gene_symbol for item in request.observations)
    state_counts = {
        state: sum(item.state is state for item in request.observations)
        for state in ProteinEvidenceState
    }
    assert state_counts == {
        ProteinEvidenceState.OBSERVED: 96,
        ProteinEvidenceState.LEFT_CENSORED: 4,
        ProteinEvidenceState.MISSING: 4,
        ProteinEvidenceState.UNSUPPORTED: 4,
    }
    assert demo_request_digest() == request.request_digest


def test_demo_analyze_and_exact_replay_lifecycle() -> None:
    payload = synthetic_demo_request().model_dump(mode="json")
    payload["bootstrap_replicates"] = 16
    payload["permutation_replicates"] = 64
    request = FunctionalProteotypeRequest.model_validate_json(json.dumps(payload))
    result = analyze_functional_proteotype(request)
    assert tuple(item.axis for item in result.axis_evidence) == AXIS_ORDER
    assert result.research_use_only is True
    assert result.emits_subtype_classification is False
    reversed_request = FunctionalProteotypeRequest(
        sample_id=request.sample_id,
        observations=tuple(reversed(request.observations)),
        bootstrap_replicates=request.bootstrap_replicates,
        permutation_replicates=request.permutation_replicates,
        effect_reference_id=request.effect_reference_id,
    )
    assert analyze_functional_proteotype(reversed_request).result_digest == result.result_digest

    verification = verify_replay(ReplayVerificationRequest(request=request, result=result))
    assert verification.verified is True
    assert verification.solver_trace_match is True

    forged = UnverifiedFunctionalProteotypeResult.model_validate_json(
        json.dumps({**result.model_dump(mode="json"), "result_digest": _digest("forged")})
    )
    rejected = verify_replay(ReplayVerificationRequest(request=request, result=forged))
    assert rejected.verified is False
    assert rejected.result_digest_match is False


def test_missing_and_unsupported_only_request_abstains_without_running_nulls() -> None:
    gene = functional_proteotype_catalog().axes["GPM"][0].gene_symbol
    request = _request(
        _observation(
            gene,
            state=ProteinEvidenceState.MISSING,
            observation_id="obs.missing",
        ),
        _observation(
            "NOTINSOURCE",
            state=ProteinEvidenceState.UNSUPPORTED,
            observation_id="obs.unsupported",
        ),
    )
    result = analyze_functional_proteotype(request)
    assert result.solver.termination is SolverTermination.INSUFFICIENT_EVIDENCE
    assert result.solver.objective_trace == ()
    assert all(item.support is AnalysisSupport.ABSTAINED for item in result.axis_evidence)
    assert all(item.latent is None and item.rank is None for item in result.axis_evidence)
    assert result.axis_evidence[0].evidence_counts.missing_signature_proteins == 1
    assert result.provenance.bootstrap_replicates_used == 0
    assert result.provenance.permutation_replicates_used == 0


def test_output_vocabulary_never_uses_winner_probabilities() -> None:
    assert {item.value for item in AxisClassification} == {
        "source_aligned",
        "source_opposed",
        "neutral",
        "indeterminate",
        "not_estimable",
    }
    assert {item.value for item in AnalysisSupport} == {
        "supported",
        "limited",
        "abstained",
    }
