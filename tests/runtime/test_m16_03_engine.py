"""Adversarial and replay coverage for M16-03."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m16_03 import (
    M1603_M1602_INPUT_MEDIA_TYPE,
    DisagreementRecord,
    DisagreementStatus,
    FuseProteinRnaDiscordanceEvidenceRequest,
    FusionConfiguration,
    FusionFindingCode,
    FusionStatus,
    ReliabilityBand,
    SignedPropagationRecord,
    SourceContribution,
    SourceKind,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.modules.c16_kinophos_object_consumer import (
    m16_03_fusion_aggregation_engine as m1603,
)

_CONTRIBUTION_COUNT = 4


def _digest(label: str) -> str:
    return sha256_digest({"m1603-test": label})


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1603.{label}",
        version="1.0.0",
        digest=_digest(label),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(label),
        role="evidence",
        claim="Caller-declared M16-03 test evidence.",
    )


def _context() -> ExecutionContext:
    def decision(role: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.m1603",
        actor_id="actor.test",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_digest("identity-binding"),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _contribution(
    source_id: str,
    kind: SourceKind,
    *,
    score: float = 0.9,
    band: ReliabilityBand = ReliabilityBand.HIGH,
) -> SourceContribution:
    return SourceContribution(
        source_id=source_id,
        kind=kind,
        artifact=_artifact(source_id),
        claim=f"Caller-declared {kind.value} contribution.",
        reliability_score=score,
        reliability_band=band,
        uncertainty_note="Source values remain opaque at this boundary.",
        evidence=(_evidence(f"evidence-{source_id}"),),
    )


def _request() -> FuseProteinRnaDiscordanceEvidenceRequest:
    contributions = (
        _contribution("source.proteome", SourceKind.MASS_SPECTROMETRY_PROTEOME),
        _contribution("source.genome", SourceKind.GENOME, score=0.85),
        _contribution("source.transcriptome", SourceKind.TRANSCRIPTOME, score=0.8),
        _contribution("source.ptm", SourceKind.PTM_ANNOTATION, score=0.78),
    )
    disagreements = (
        DisagreementRecord(
            disagreement_id="disagreement.m1603.transcript-protein",
            source_ids=("source.proteome", "source.transcriptome"),
            description="Caller-declared transcript-protein discordance remains open.",
            status=DisagreementStatus.OPEN,
            evidence=(_evidence("disagreement"),),
        ),
    )
    propagation = (
        SignedPropagationRecord(
            propagation_id="propagation.m1603.complex",
            source_id="source.proteome",
            target_id="target.complex",
            signature_digest=_digest("propagation-signature"),
            assertion="Caller-declared component propagation for review.",
            evidence=(_evidence("propagation"),),
        ),
    )
    configuration = FusionConfiguration(
        configuration_id="configuration.m1603",
        version="1.0.0",
        reliability_threshold=0.75,
        evidence=(_evidence("configuration-evidence"),),
    )
    return FuseProteinRnaDiscordanceEvidenceRequest(
        request_id="request.m1603",
        context=_context(),
        alignment_result=ArtifactReference(
            artifact_id="upstream.m1602",
            version="0.1.0-provisional",
            digest=_digest("alignment"),
            media_type=M1603_M1602_INPUT_MEDIA_TYPE,
        ),
        contributions=contributions,
        disagreements=disagreements,
        propagation=propagation,
        configuration=configuration,
        source_artifacts=(_artifact("source-manifest"),),
    )


def test_integrated_replay_preserves_attribution_conflict_and_propagation() -> None:
    service = m1603.M1603Service()
    result = service.execute(_request())
    assert result.status is FusionStatus.INTEGRATED
    assert result.integrated_evidence is not None
    assert len(result.integrated_evidence.contributions) == _CONTRIBUTION_COUNT
    assert result.integrated_evidence.disagreements[0].status is DisagreementStatus.OPEN
    assert result.integrated_evidence.propagation[0].signature_digest.startswith("sha256:")
    assert result.findings[1].code is FusionFindingCode.SOURCE_DISAGREEMENT
    assert result.parent_target == "protein-RNA discordance"
    assert result.emits_parent is False
    assert result.human_review_required is True
    assert service.verify(result).result_digest == result.result_digest


def test_low_reliability_abstains_without_negative_conversion() -> None:
    request = _request()
    low = request.contributions[0].model_copy(
        update={"reliability_score": 0.2, "reliability_band": ReliabilityBand.LOW}
    )
    result = m1603.M1603Service().execute(
        request.model_copy(update={"contributions": (low, *request.contributions[1:])})
    )
    assert result.status is FusionStatus.ABSTAINED
    assert result.integrated_evidence is None
    assert result.abstention_reason is not None
    assert any(item.code is FusionFindingCode.LOW_RELIABILITY for item in result.findings)


def test_not_evaluable_source_abstains_and_denied_control_fails_closed() -> None:
    request = _request()
    unsafe = request.contributions[0].model_copy(
        update={"reliability_score": 0.0, "reliability_band": ReliabilityBand.NOT_EVALUABLE}
    )
    result = m1603.M1603Service().execute(
        request.model_copy(update={"contributions": (unsafe, *request.contributions[1:])})
    )
    assert result.status is FusionStatus.ABSTAINED
    assert any(item.code is FusionFindingCode.UNSUPPORTED_INPUT for item in result.findings)
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    with pytest.raises(m1603.M1603AuthorizationError):
        m1603.M1603Service().execute(request.model_copy(update={"context": denied_context}))


def test_upstream_boundary_and_tampered_replay_reject() -> None:
    request = _request()
    wrong = request.model_copy(
        update={
            "alignment_result": request.alignment_result.model_copy(
                update={"media_type": "application/json"}
            )
        }
    )
    with pytest.raises(ValueError, match="M16-02"):
        m1603.M1603Service().construct(wrong)
    result = m1603.M1603Service().execute(request)
    tampered = result.model_copy(update={"human_review_required": False})
    with pytest.raises(m1603.M1603ReplayVerificationError):
        m1603.M1603Service().verify(tampered)
    changed = result.model_copy(update={"human_review_required": False})
    changed = changed.model_copy(update={"result_digest": result_payload_digest(changed)})
    with pytest.raises(m1603.M1603ReplayVerificationError):
        m1603.M1603Service().verify(changed)
    forged = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    with pytest.raises(m1603.M1603ReplayVerificationError):
        m1603.M1603Service().verify(forged, replay=False)


def test_mapping_plugin_and_descriptor_paths() -> None:
    request = _request()
    service = m1603.M1603Service()
    mapping = request.model_dump(mode="python")
    assert service.validate_request(request).request_id == request.request_id
    assert service.construct(mapping).status is FusionStatus.INTEGRATED
    plugin = m1603.M1603Plugin(service)
    validated = plugin.validate(request.model_dump_json())
    assert plugin.validate(request).request.request_id == request.request_id
    result = plugin.run(validated)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M16-03"
    assert plugin.verify(result, replay=False).result_id == result.result_id
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="strict request"):
        service.validate_request(object())


def test_invalid_candidate_and_mapping_boundary_fail_closed() -> None:
    request = _request()

    class Candidate:
        context = request.context

    with pytest.raises(TypeError, match="strict request"):
        m1603.M1603Service().construct(Candidate())

    class Broken:
        @property
        def context(self) -> object:
            raise RuntimeError

    with pytest.raises(m1603.M1603AuthorizationError):
        m1603.preflight_m1603_authorization(Broken())
