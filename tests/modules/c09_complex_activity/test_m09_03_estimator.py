"""Focused M09-03 estimator lifecycle and safety coverage."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m09_03 import (
    BaselineMethod,
    BaselineRunConfiguration,
    ComplexActivityBaselineEstimate,
    EstimateComplexActivityBaselineRequest,
)
from glio_proteogen.contracts.m09_03.canonical import result_payload_digest
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


def test_estimator_is_deterministic_and_replay_bound() -> None:
    engine = m0903.M0903BaselineEstimator()
    first = engine.construct(_request())
    second = engine.construct(_request())
    assert first.canonical_bytes == second.canonical_bytes
    assert first.result.status.value == "estimated"
    assert first.result.estimate is not None
    assert engine.verify(first.result, first.canonical_bytes)
    assert first.result.uncertainty.transport.state.value == "estimated"


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


def test_replay_rejects_self_rehashed_estimate_mutation() -> None:
    engine = m0903.M0903BaselineEstimator()
    built = engine.construct(_request())
    assert built.result.estimate is not None
    forged_estimate = built.result.estimate.model_copy(update={"score": 0.0})
    forged = built.result.model_copy(update={"estimate": forged_estimate})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    assert not engine.verify(forged)


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
