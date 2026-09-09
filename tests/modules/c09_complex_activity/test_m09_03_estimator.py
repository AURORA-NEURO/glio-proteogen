"""Focused M09-03 estimator lifecycle and safety coverage."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

import glio_proteogen.modules.c09_complex_activity.m09_03_mature_baseline_estimator.engine as engine_module  # noqa: E501
from glio_proteogen.contracts.m09_03 import (
    BaselineMethod,
    BaselineRunConfiguration,
    ComplexActivityBaselineEstimate,
    EstimateComplexActivityBaselineRequest,
    GliomaBaselineEvidenceState,
    GliomaBaselineObservation,
    GliomaBaselineProgram,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c09_complex_activity import (
    m09_03_mature_baseline_estimator as m0903,
)

_DIGEST = "sha256:" + ("a" * 64)
_M0902_MEDIA_TYPE = "application/vnd.glio-proteogen.m09-02+json"


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}.artifact",
        version="1.0.0",
        digest=_DIGEST,
        media_type=media_type,
    )


def _context(*, consent: ConsentState = ConsentState.GRANTED) -> ExecutionContext:
    evidence = _artifact("control")
    accepted = UpstreamDecisionReference(
        decision_id="decision.accepted",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=evidence,
    )
    return ExecutionContext(
        request_id="request.m0903",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=accepted,
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_DIGEST,
                evidence=evidence,
            ),
            provenance=accepted,
            consent=ConsentReference(
                decision_id="decision.consent",
                state=consent,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=accepted,
            support=accepted,
            intended_use=accepted,
        ),
    )


def _request(*, marker: str | None = None) -> EstimateComplexActivityBaselineRequest:
    suffix = marker or "valid"
    return EstimateComplexActivityBaselineRequest(
        request_id="request.m0903",
        context=_context(),
        representation_result=_artifact(f"representation.{suffix}", _M0902_MEDIA_TYPE),
        configuration=BaselineRunConfiguration(
            configuration_id="configuration.locked",
            version="1.0.0",
            method=BaselineMethod.STATISTICAL_RULE_BASED,
            preprocessing_artifact=_artifact("preprocessing"),
            tuning_artifact=_artifact("tuning"),
            uncertainty_artifact=_artifact("uncertainty"),
            benchmark_artifact=_artifact("benchmark"),
            evidence=(
                EvidenceReference(
                    reference=_artifact("configuration.evidence"),
                    role="evidence",
                    claim="locked configuration evidence",
                ),
            ),
        ),
        source_artifacts=(_artifact(f"proteome.{suffix}"),),
    )


def _typed_observations() -> tuple[GliomaBaselineObservation, ...]:
    return (
        GliomaBaselineObservation(
            observation_id="observation.egfr",
            feature_id="protein.egfr",
            program=GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
            evidence_state=GliomaBaselineEvidenceState.OBSERVED,
            standardized_effect=1.2,
            standard_error=0.2,
        ),
        GliomaBaselineObservation(
            observation_id="observation.tp53",
            feature_id="protein.tp53",
            program=GliomaBaselineProgram.P53_DNA_REPAIR,
            evidence_state=GliomaBaselineEvidenceState.OBSERVED,
            standardized_effect=-0.7,
            standard_error=0.3,
        ),
        GliomaBaselineObservation(
            observation_id="observation.ccnd1",
            feature_id="protein.ccnd1",
            program=GliomaBaselineProgram.CELL_CYCLE,
            evidence_state=GliomaBaselineEvidenceState.LEFT_CENSORED,
            censoring_limit=0.1,
            standard_error=0.2,
        ),
    )


def test_estimator_is_deterministic_and_replay_bound() -> None:
    engine = m0903.M0903BaselineEstimator()
    first = engine.construct(_request())
    second = engine.construct(_request())
    assert first.canonical_bytes == second.canonical_bytes
    assert first.result.status.value == "estimated"
    assert first.result.estimate is not None
    assert engine.verify(first.result, first.canonical_bytes)
    assert first.result.uncertainty.transport.state.value == "estimated"


def test_typed_glioma_baseline_fits_program_relations_and_bootstrap() -> None:
    request = _request().model_copy(update={"typed_observations": _typed_observations()})
    engine = m0903.M0903BaselineEstimator()
    first = engine.construct(request)
    second = engine.construct(request)
    assert first.canonical_bytes == second.canonical_bytes
    assert first.result.status.value == "estimated"
    assert first.result.estimate is not None
    assert first.result.estimate.model_family == "glioma-complex-baseline-huber/1.0.0"
    assert first.result.estimate.evidence_count == len(_typed_observations())
    assert first.result.estimate.lower_bound is not None
    assert first.result.estimate.upper_bound is not None
    assert first.result.estimate.top_drivers
    assert first.result.estimate.ablation_effects
    assert first.result.optimization_diagnostics[0].status.value == "converged"
    assert first.result.optimization_diagnostics[0].objective_trace_digest is not None
    assert engine.verify(first.result, first.canonical_bytes, request)


def test_typed_baseline_is_input_order_invariant_and_missing_is_neutral() -> None:
    observations = _typed_observations()
    request = _request().model_copy(update={"typed_observations": observations})
    reordered = _request().model_copy(update={"typed_observations": tuple(reversed(observations))})
    engine = m0903.M0903BaselineEstimator()
    assert engine.construct(request).canonical_bytes == engine.construct(reordered).canonical_bytes
    missing = GliomaBaselineObservation(
        observation_id="observation.missing",
        feature_id="protein.missing",
        evidence_state=GliomaBaselineEvidenceState.MISSING,
        quality_weight=0.0,
    )
    with_missing = _request().model_copy(update={"typed_observations": (*observations, missing)})
    baseline = engine.construct(request).result
    neutral = engine.construct(with_missing).result
    assert baseline.estimate is not None
    assert neutral.estimate is not None
    assert baseline.estimate.score == neutral.estimate.score
    assert neutral.estimate.evidence_count == baseline.estimate.evidence_count


def test_typed_initialization_uses_observed_effects_and_censor_bounds() -> None:
    observed = _typed_observations()[0].model_copy(
        update={"program": GliomaBaselineProgram.CELL_CYCLE}
    )
    censored = _typed_observations()[2]
    high_bound = censored.model_copy(update={"censoring_limit": -0.2})

    assert engine_module._initial_typed_state((observed, high_bound)) == pytest.approx(-0.2)


def test_typed_censor_only_initialization_is_neutral_when_bound_is_positive() -> None:
    censored = _typed_observations()[2]

    assert engine_module._initial_typed_state((censored,)) == pytest.approx(0.0)


def test_typed_censor_influence_is_zero_when_state_is_feasible() -> None:
    observed = _typed_observations()[0]
    censored = observed.model_copy(
        update={
            "evidence_state": GliomaBaselineEvidenceState.LEFT_CENSORED,
            "censoring_limit": 0.2,
        }
    )

    assert engine_module._typed_censor_activation(0.0, censored) == pytest.approx(0.0)
    assert engine_module._typed_censor_activation(0.3, censored) == pytest.approx(1.0)


def test_typed_baseline_abstains_when_program_support_is_insufficient() -> None:
    observations = (
        GliomaBaselineObservation(
            observation_id="observation.egfr.1",
            feature_id="protein.egfr",
            program=GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
            evidence_state=GliomaBaselineEvidenceState.OBSERVED,
            standardized_effect=1.2,
            standard_error=0.2,
        ),
        GliomaBaselineObservation(
            observation_id="observation.egfr.2",
            feature_id="protein.erbb2",
            program=GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
            evidence_state=GliomaBaselineEvidenceState.OBSERVED,
            standardized_effect=0.8,
            standard_error=0.2,
        ),
        GliomaBaselineObservation(
            observation_id="observation.egfr.3",
            feature_id="protein.erbb3",
            program=GliomaBaselineProgram.RTK_PI3K_AKT_MTOR,
            evidence_state=GliomaBaselineEvidenceState.OBSERVED,
            standardized_effect=1.0,
            standard_error=0.2,
        ),
    )
    result = (
        m0903.M0903BaselineEstimator()
        .construct(_request().model_copy(update={"typed_observations": observations}))
        .result
    )
    assert result.status.value == "abstained"
    assert result.estimate is None
    assert result.optimization_diagnostics[0].status.value == "not_evaluable"
    assert result.human_review_required is True


@pytest.mark.parametrize("marker", ["missing", "unsupported", "ood", "not_evaluable", "conflict"])
def test_unsupported_or_quality_markers_abstain_without_negative_estimate(marker: str) -> None:
    result = m0903.M0903BaselineEstimator().construct(_request(marker=marker)).result
    assert result.status.value == "abstained"
    assert result.estimate is None
    assert result.findings
    assert result.support_decision.status.value == "review_required"
    assert result.human_review_required is True
    uncertainty_values = result.uncertainty.model_dump().values()
    assert all(
        item["state"] == "not_estimable"
        for item in uncertainty_values
        if isinstance(item, dict) and "state" in item
    )


def test_tamper_is_rejected_without_mutating_result() -> None:
    engine = m0903.M0903BaselineEstimator()
    built = engine.construct(_request())
    tampered = deepcopy(built.result.model_dump(mode="python"))
    assert tampered["estimate"] is not None
    tampered["estimate"]["score"] = 0.0
    assert not engine.verify(tampered, built.canonical_bytes)
    assert built.result.estimate is not None
    assert built.result.estimate.score != 0.0


def test_preflight_rejects_withheld_consent_and_rejected_quality() -> None:
    request = _request().model_copy(update={"context": _context(consent=ConsentState.WITHHELD)})
    with pytest.raises(m0903.M0903AuthorizationError):
        m0903.M0903BaselineEstimator().construct(request)
    context = _context()
    rejected = context.references.quality.model_copy(update={"state": "rejected"})
    denied = context.model_copy(
        update={"references": context.references.model_copy(update={"quality": rejected})}
    )
    with pytest.raises(m0903.M0903AuthorizationError):
        m0903.M0903BaselineEstimator().construct(_request().model_copy(update={"context": denied}))


def test_request_rejects_handoff_duplication_and_config_artifact_collision() -> None:
    request = _request()
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (request.representation_result,)
    with pytest.raises(ValueError, match="must not be duplicated"):
        EstimateComplexActivityBaselineRequest(**payload)
    with pytest.raises(ValueError, match="distinct identities"):
        BaselineRunConfiguration(
            configuration_id="configuration.duplicate",
            version="1.0.0",
            method=BaselineMethod.STATISTICAL_RULE_BASED,
            preprocessing_artifact=_artifact("same"),
            tuning_artifact=_artifact("same"),
            uncertainty_artifact=_artifact("uncertainty"),
            benchmark_artifact=_artifact("benchmark"),
            evidence=(
                EvidenceReference(
                    reference=_artifact("evidence"),
                    role="evidence",
                    claim="locked configuration evidence",
                ),
            ),
        )


def test_service_and_result_seal_reject_digest_or_byte_drift() -> None:
    service = m0903.M0903Service()
    built = service.execute(_request())
    assert service.verify(built.result, built.canonical_bytes)
    with pytest.raises(m0903.M0903InputError, match="digest"):
        m0903.BuiltM0903Result(
            result=built.result.model_copy(update={"result_digest": "sha256:" + ("0" * 64)}),
            canonical_bytes=built.canonical_bytes,
        )
    with pytest.raises(m0903.M0903InputError, match="canonical"):
        m0903.BuiltM0903Result(result=built.result, canonical_bytes=b"{}")
    assert not service.verify(built.result, "not-bytes")  # type: ignore[arg-type]
    assert not service.verify(built.result, b"x" * (8 * 1024 * 1024 + 1))


def test_free_function_and_non_request_preflight_are_bounded() -> None:
    m0903.preflight_m0903_authorization(object())
    built = m0903.estimate_complex_activity_baseline(_request())
    assert built.result.status.value == "estimated"


def test_prohibited_claim_is_rejected_by_estimate_contract() -> None:
    with pytest.raises(ValueError, match="prohibited"):
        ComplexActivityBaselineEstimate(
            predicted_activity="kinase_activity",
            score=0.5,
            calibration_reference=_artifact("calibration"),
        )
