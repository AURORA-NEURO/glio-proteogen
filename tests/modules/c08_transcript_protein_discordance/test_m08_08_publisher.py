"""Adversarial and replay tests for the provisional M08-08 publisher."""

# ruff: noqa: E501

import json
from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m08_08 import (
    M0808_CALIBRATION_MEDIA_TYPE,
    M0808_UNCERTAINTY_MEDIA_TYPE,
    EvidenceBundle,
    EvidenceRole,
    ExplanationAssumption,
    PublishedEvidenceItem,
    PublisherStatus,
    PublishTranscriptProteinEvidenceRequest,
    ReconstructionStatus,
    ReconstructionStep,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher import (
    M0808AuthorizationError,
    M0808EvidenceExplanationPublisher,
    M0808Plugin,
    M0808Service,
    ValidatedM0808Request,
    publish_transcript_protein_evidence_explanation,
)

_D1 = "sha256:" + ("1" * 64)
_D2 = "sha256:" + ("2" * 64)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="1.0.0",
        digest=_D1 if name.endswith("1") else _D2,
        media_type=media_type,
    )


def _decision(name: str) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{name}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=_artifact(f"evidence.{name}"),
    )


def _context() -> ExecutionContext:
    identity = IdentityLineageReference(
        decision_id="decision.identity",
        state=IdentityLineageState.RESOLVED,
        policy_version="1.0.0",
        binding_digest=_D1,
        evidence=_artifact("evidence.identity"),
    )
    return ExecutionContext(
        request_id="request.m08-08",
        actor_id="actor.test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration"),
            identity_lineage=identity,
            provenance=_decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("evidence.consent"),
            ),
            quality=_decision("quality"),
            support=_decision("support"),
            intended_use=_decision("intended_use"),
        ),
    )


def _request(*source_ids: str) -> PublishTranscriptProteinEvidenceRequest:
    return PublishTranscriptProteinEvidenceRequest(
        request_id="request.m08-08",
        context=_context(),
        calibration_result=_artifact("calibration.1", M0808_CALIBRATION_MEDIA_TYPE),
        uncertainty_result=_artifact("uncertainty.2", M0808_UNCERTAINTY_MEDIA_TYPE),
        evidence_bundle=EvidenceBundle(
            bundle_id="bundle.input",
            version="0.1.0-provisional",
            items=(
                PublishedEvidenceItem(
                    evidence_id="input.evidence.1",
                    role=EvidenceRole.INPUT,
                    artifact=_artifact(source_ids[0]),
                    claim="Input evidence.",
                ),
            ),
            assumptions=(
                ExplanationAssumption(
                    assumption_id="assumption.input.1",
                    statement="Input bundle is caller-declared.",
                    evidence_ids=("input.evidence.1",),
                ),
            ),
            counter_evidence=(
                PublishedEvidenceItem(
                    evidence_id="counter.evidence.1",
                    role=EvidenceRole.COUNTER_EVIDENCE,
                    artifact=_artifact("counter.1"),
                    claim="Counter-evidence.",
                ),
            ),
            reconstruction=(
                ReconstructionStep(
                    sequence=1,
                    operation="retain source evidence",
                    input_digests=(_D1,),
                    output_digest=_D2,
                    status=ReconstructionStatus.COMPLETE,
                    evidence_ids=("input.evidence.1",),
                ),
            ),
        ),
        source_artifacts=tuple(_artifact(name) for name in source_ids),
    )


def test_publish_is_deterministic_and_replay_verified() -> None:
    engine = M0808EvidenceExplanationPublisher()
    first = engine.publish(_request("source.1", "source.2"))
    second = engine.publish(_request("source.1", "source.2"))
    assert first.result.status is PublisherStatus.PUBLISHED
    assert first.result.evidence_bundle is not None
    assert first.result.explanation is not None
    assert first.result.support_decision.status is SupportStatus.SUPPORTED
    assert first.canonical_bytes == second.canonical_bytes
    assert engine.verify(first.result, first.canonical_bytes).verified


def test_unsupported_material_abstains_without_publishing() -> None:
    built = M0808Service().publish(_request("source.unsupported"))
    assert built.result.status is PublisherStatus.ABSTAINED
    assert built.result.evidence_bundle is None
    assert built.result.explanation is None
    assert built.result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert built.result.abstention_reason is not None


def test_consent_and_identity_fail_closed() -> None:
    request = _request("source.1")
    refs = request.context.references
    withheld = refs.consent.model_copy(update={"state": ConsentState.WITHHELD})
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": refs.model_copy(update={"consent": withheld})}
            )
        }
    )
    with pytest.raises(M0808AuthorizationError):
        M0808EvidenceExplanationPublisher().publish(denied)


def test_tamper_and_unissued_plugin_token_are_rejected() -> None:
    service = M0808Service()
    plugin = M0808Plugin(service)
    request = _request("source.1")
    built = service.publish(request)
    tampered = built.canonical_bytes.replace(b"source.1", b"source.x")
    assert not service.verify(built.result, tampered).verified
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0808Request(request=request, _seal=object()))
    token = plugin.validate(json.dumps(request.model_dump(mode="json")).encode())
    assert plugin.run(token).result.result_id == "result.request.m08-08"


def test_public_function_and_invalid_result_replay_boundary() -> None:
    request = _request("source.1")
    built = publish_transcript_protein_evidence_explanation(request)
    assert built.result.result_id == "result.request.m08-08"
    engine = M0808EvidenceExplanationPublisher()
    assert engine.verify(object()).verified is False
    with pytest.raises((TypeError, ValueError)):
        engine.publish(object())
