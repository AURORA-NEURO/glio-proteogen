"""Runtime, replay, and adversarial coverage for provisional M06-08."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m06_08 import (
    M0608_M0607_RESULT_MEDIA_TYPE,
    M0608_OUTPUT_MEDIA_TYPE,
    EvidencePublicationStatus,
    PublisherAssumption,
    PublisherCounterEvidence,
    PublishProteinAbundanceEvidenceRequest,
    ReconstructionStep,
    canonical_request_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c06_protein_abundance.m06_08_evidence_explanation_publisher import (
    M0608EvidencePublisherAuthorizationError,
    M0608ReplayVerificationError,
    M0608Service,
)


def _artifact(name: str, fill: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"{name}.{fill}",
        version="0.1.0",
        digest=f"sha256:{fill * 64}",
        media_type=media_type,
    )


def _context() -> ExecutionContext:
    controls = _artifact("control", "a")
    identity = _artifact("identity", "b")
    return ExecutionContext(
        request_id="request.m0608",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=UpstreamDecisionReference(
                decision_id="decision.config",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=controls,
            ),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=identity.digest,
                evidence=identity,
            ),
            provenance=UpstreamDecisionReference(
                decision_id="decision.provenance",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("provenance", "c"),
            ),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent", "d"),
            ),
            quality=UpstreamDecisionReference(
                decision_id="decision.quality",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("quality", "e"),
            ),
            support=UpstreamDecisionReference(
                decision_id="decision.support",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("support", "f"),
            ),
            intended_use=UpstreamDecisionReference(
                decision_id="decision.intended",
                state=UpstreamDecisionState.ACCEPTED,
                policy_version="1.0.0",
                evidence=_artifact("intended", "0"),
            ),
        ),
    )


def request() -> PublishProteinAbundanceEvidenceRequest:
    upstream = _artifact("m0607.result", "1", M0608_M0607_RESULT_MEDIA_TYPE)
    source = _artifact("proteome.source", "2")
    evidence = _artifact("evidence.source", "3")
    return PublishProteinAbundanceEvidenceRequest(
        request_id="request.m0608",
        context=_context(),
        upstream_result=upstream,
        source_artifacts=(source,),
        assumptions=(
            PublisherAssumption(
                assumption_id="assumption.normalization",
                statement="Input intensity values use the approved normalized scale.",
                evidence=(),
            ),
        ),
        counter_evidence=(
            PublisherCounterEvidence(
                counter_evidence_id="counter.batch",
                statement="A batch effect remains possible.",
                impact="The claim must remain reviewable.",
                evidence=(),
            ),
        ),
        reconstruction_steps=(
            ReconstructionStep(
                sequence=1,
                operation="bind_upstream_result",
                input_digests=(upstream.digest, source.digest),
                output_digest=evidence.digest,
                evidence=(),
            ),
        ),
    )


def test_runtime_abstains_without_masquerading_as_negative() -> None:
    result = M0608Service().execute(request())
    assert result.status is EvidencePublicationStatus.ABSTAINED
    assert result.bundle is None
    assert result.explanation is None
    assert result.support_decision.status.value == "review_required"
    assert result.evidence
    assert result.human_review_required
    assert verify_result_digest(result)


def test_replay_verification_is_transitive_and_deterministic() -> None:
    service = M0608Service()
    first = service.execute(request())
    second = service.verify(first)
    assert second == first
    assert second.model_dump_json() == first.model_dump_json()
    assert canonical_request_digest(first.request) == first.request_digest


def test_tampered_digest_and_payload_are_rejected() -> None:
    service = M0608Service()
    result = service.execute(request())
    tampered = result.model_copy(update={"abstention_reason": "changed"})
    with pytest.raises(M0608ReplayVerificationError):
        service.verify(tampered)
    bad_digest = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises((M0608ReplayVerificationError, ValidationError)):
        service.verify(bad_digest)


def test_auth_controls_fail_closed_before_validation() -> None:
    candidate = {"context": {"references": {}}, "source_artifacts": []}
    with pytest.raises(M0608EvidencePublisherAuthorizationError):
        M0608Service().execute(candidate)


def test_duplicate_sources_and_invalid_media_are_rejected() -> None:
    base = request()
    source = base.source_artifacts[0]
    with pytest.raises(ValidationError):
        base.model_copy(update={"source_artifacts": (source, source)}).model_validate(
            base.model_copy(update={"source_artifacts": (source, source)}), strict=True
        )
    with pytest.raises(ValidationError):
        base.model_copy(update={"upstream_result": _artifact("wrong", "9")}).model_validate(
            base.model_copy(update={"upstream_result": _artifact("wrong", "9")}), strict=True
        )


def test_counter_evidence_role_is_not_silently_rewritten() -> None:
    with pytest.raises(ValidationError):
        PublisherCounterEvidence(
            counter_evidence_id="counter.invalid",
            statement="A conflicting signal exists.",
            impact="Requires review.",
            evidence=(
                {
                    "reference": _artifact("counter", "8"),
                    "role": "evidence",
                    "claim": "wrong role",
                },
            ),
        )


def test_output_media_type_is_not_an_upstream_claim() -> None:
    assert M0608_OUTPUT_MEDIA_TYPE.endswith("+json")
