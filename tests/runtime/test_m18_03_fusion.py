"""Runtime and adversarial coverage for provisional M18-03 fusion."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m18_03 import (
    AggregationConfiguration,
    DisagreementRecord,
    DisagreementStatus,
    FuseBiomarkerPanelEvidenceRequest,
    FusionFindingCode,
    FusionStatus,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
)
from glio_proteogen.contracts.m18_03.canonical import result_payload_digest
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_03_fusion_aggregation as m1803,
)

EXPECTED_CONTRIBUTIONS = 2


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1803:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared M18-03 source evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.synthetic.m1803",
        actor_id="actor.synthetic.m1803",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1803.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _request(
    *,
    reliability_band: ReliabilityBand = ReliabilityBand.HIGH,
    reliability_score: float = 0.9,
    disagreement_status: DisagreementStatus | None = None,
    claim: str = "component-specific abundance evidence",
    alignment_media_type: str = "application/vnd.glio-proteogen.m18-02+json",
) -> FuseBiomarkerPanelEvidenceRequest:
    source_evidence = (_evidence(_artifact("source-evidence")),)
    contributions = (
        SourceContribution(
            source_id="source.proteome",
            kind=SourceKind.MASS_SPECTROMETRY_PROTEOME,
            owner="Proteomics team",
            artifact=_artifact("proteome"),
            claim=claim,
            reliability_score=reliability_score,
            reliability_band=reliability_band,
            uncertainty_note="Synthetic reliability declaration.",
            evidence=source_evidence,
        ),
        SourceContribution(
            source_id="source.genome",
            kind=SourceKind.GENOME,
            owner="Genomics team",
            artifact=_artifact("genome"),
            claim="component-specific genomic context evidence",
            reliability_score=0.85,
            reliability_band=ReliabilityBand.HIGH,
            uncertainty_note="Synthetic reliability declaration.",
            evidence=source_evidence,
        ),
    )
    disagreements: tuple[DisagreementRecord, ...] = ()
    if disagreement_status is not None:
        disagreements = (
            DisagreementRecord(
                disagreement_id="disagreement.synthetic",
                source_ids=("source.proteome", "source.genome"),
                description="Synthetic cross-source difference.",
                status=disagreement_status,
                resolution=(
                    "Reviewed by synthetic owner"
                    if disagreement_status is DisagreementStatus.RESOLVED
                    else None
                ),
                evidence=source_evidence,
            ),
        )
    return FuseBiomarkerPanelEvidenceRequest(
        request_id="request.synthetic.m1803",
        context=_context(),
        alignment_result=_artifact("alignment", alignment_media_type),
        contributions=contributions,
        disagreements=disagreements,
        aggregate_values=("integrated_signal=0.84", "source_count=2"),
        configuration=AggregationConfiguration(
            configuration_id="configuration.synthetic.m1803",
            version="1.0.0",
            method="reliability_weighted_component_aggregation",
            reliability_threshold=0.7,
            evidence=source_evidence,
        ),
        source_artifacts=(_artifact("source-manifest"),),
    )


def test_attributable_fusion_integrates_and_replays() -> None:
    result = m1803.M1803Engine().adapt(_request())

    assert result.status is FusionStatus.INTEGRATED
    assert result.integrated_evidence is not None
    assert len(result.integrated_evidence.contributions) == EXPECTED_CONTRIBUTIONS
    assert result.integrated_evidence.contributions[0].source_id == "source.proteome"
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert m1803.M1803Engine().replay(result) == result


def test_resolved_disagreement_is_preserved_in_integrated_object() -> None:
    result = m1803.M1803Engine().adapt(_request(disagreement_status=DisagreementStatus.RESOLVED))

    assert result.status is FusionStatus.INTEGRATED
    assert result.integrated_evidence is not None
    assert result.integrated_evidence.disagreements[0].status is DisagreementStatus.RESOLVED


def test_open_disagreement_abstains_without_erasing_conflict() -> None:
    result = m1803.M1803Engine().adapt(_request(disagreement_status=DisagreementStatus.OPEN))

    assert result.status is FusionStatus.ABSTAINED
    assert result.integrated_evidence is None
    assert any(item.code is FusionFindingCode.SOURCE_DISAGREEMENT for item in result.findings)
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_low_reliability_abstains() -> None:
    result = m1803.M1803Engine().adapt(
        _request(reliability_band=ReliabilityBand.LOW, reliability_score=0.2)
    )

    assert result.status is FusionStatus.ABSTAINED
    assert any(item.code is FusionFindingCode.LOW_RELIABILITY for item in result.findings)


def test_forbidden_ownership_claim_abstains() -> None:
    result = m1803.M1803Engine().adapt(_request(claim="all-omics treatment recommendation"))

    assert result.status is FusionStatus.ABSTAINED
    assert any(item.code is FusionFindingCode.OWNERSHIP_UNCLEAR for item in result.findings)


def test_control_denial_precedes_source_traversal() -> None:
    request = _request().model_copy(
        update={
            "context": _context().model_copy(
                update={
                    "references": _context().references.model_copy(
                        update={
                            "consent": _context().references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )

    with pytest.raises(m1803.M1803AuthorizationError, match="consent"):
        m1803.M1803Engine().adapt(request)


def test_upstream_media_type_is_strict() -> None:
    with pytest.raises(ValueError, match="M18-02"):
        m1803.M1803Engine().adapt(_request(alignment_media_type="application/json"))


def test_tampered_result_digest_is_rejected() -> None:
    result = m1803.M1803Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})

    with pytest.raises(m1803.M1803ReplayError, match="payload digest"):
        m1803.M1803Engine().replay(tampered)


def test_self_rehashed_semantic_tamper_is_rejected_by_replay() -> None:
    engine = m1803.M1803Engine()
    result = engine.adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(m1803.M1803ReplayError, match="deterministic replay"):
        engine.replay(tampered)
