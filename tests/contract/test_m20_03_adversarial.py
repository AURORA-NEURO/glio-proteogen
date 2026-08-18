"""Adversarial and runtime coverage for M20-03."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from glio_proteogen.contracts.m20_03 import (
    AggregationConfiguration,
    DisagreementRecord,
    DisagreementStatus,
    FuseProteinSubtypeEvidenceRequest,
    FusionFindingCode,
    FusionStatus,
    ProteinSubtypeIntegratedEvidenceResult,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
    canonical_request_bytes,
    canonical_request_digest,
    canonical_result_payload_bytes,
    result_payload_digest,
    verify_request_digest,
    verify_result_digest,
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_03_fusion_aggregation import (
    M2003AuthorizationError,
    M2003Engine,
    M2003Plugin,
    M2003ReplayError,
    M2003Service,
)

_HIGH_RELIABILITY_THRESHOLD = 0.8
_MODERATE_RELIABILITY_THRESHOLD = 0.5


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2003.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2003:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M20-03 evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2003.{role}",
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
        request_id="request.m2003.synthetic",
        actor_id="actor.m2003.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2003.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2003.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2003.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _contribution(name: str, score: float = 0.9) -> SourceContribution:
    artifact = _artifact(name)
    return SourceContribution(
        source_id=f"source.m2003.{name}",
        kind=SourceKind.MASS_SPECTROMETRY_PROTEOME,
        owner="M20-03 source owner",
        artifact=artifact,
        claim="component-specific protein subtype evidence",
        reliability_score=score,
        reliability_band=(
            ReliabilityBand.HIGH
            if score >= _HIGH_RELIABILITY_THRESHOLD
            else ReliabilityBand.MODERATE
            if score >= _MODERATE_RELIABILITY_THRESHOLD
            else ReliabilityBand.LOW
        ),
        uncertainty_note="Synthetic declaration with explicit uncertainty.",
        evidence=(_evidence(artifact),),
    )


def _request(
    *,
    contributions: tuple[SourceContribution, ...] | None = None,
    disagreements: tuple[DisagreementRecord, ...] = (),
) -> FuseProteinSubtypeEvidenceRequest:
    contributions = contributions or (_contribution("proteome"), _contribution("genome", 0.7))
    return FuseProteinSubtypeEvidenceRequest(
        request_id="request.m2003.synthetic",
        context=_context(),
        alignment_result=_artifact("alignment", "application/vnd.glio-proteogen.m20-02+json"),
        contributions=contributions,
        disagreements=disagreements,
        aggregate_values=("integrated_signal=0.84", "source_count=2"),
        configuration=AggregationConfiguration(
            configuration_id="configuration.m2003.synthetic",
            version="1.0.0",
            method="reliability_weighted_component_aggregation",
            reliability_threshold=0.7,
        ),
        source_artifacts=tuple(item.artifact for item in contributions),
    )


def _self_rehashed(
    result: ProteinSubtypeIntegratedEvidenceResult,
    updates: dict[str, Any],
) -> ProteinSubtypeIntegratedEvidenceResult:
    forged = result.model_copy(update=updates)
    return type(result).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )


def test_supported_fusion_integrates_and_replays() -> None:
    result = M2003Engine().fuse(_request())
    assert result.status is FusionStatus.INTEGRATED
    assert result.integrated_evidence is not None
    assert result.parent_target == "protein subtype"
    assert result.emits_parent is False
    assert M2003Engine().replay(result) == result


def test_open_disagreement_abstains_and_remains_visible() -> None:
    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m2003.open",
        source_ids=("source.m2003.proteome", "source.m2003.genome"),
        description="Synthetic unresolved difference.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("open")),),
    )
    result = M2003Engine().fuse(_request(disagreements=(disagreement,)))
    assert result.status is FusionStatus.ABSTAINED
    assert result.integrated_evidence is None
    assert any(item.code is FusionFindingCode.SOURCE_DISAGREEMENT for item in result.findings)
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_low_reliability_and_forbidden_scope_abstain() -> None:
    low = _contribution("low", 0.2)
    forbidden = _contribution("forbidden").model_copy(update={"claim": "kinase treatment state"})
    result = M2003Engine().fuse(_request(contributions=(low, forbidden)))
    assert result.status is FusionStatus.ABSTAINED
    assert {item.code for item in result.findings} >= {
        FusionFindingCode.LOW_RELIABILITY,
        FusionFindingCode.OWNERSHIP_UNCLEAR,
    }


def test_control_denial_precedes_source_traversal() -> None:
    request = _request()
    denied = request.context.references.consent.model_copy(update={"state": "withheld"})
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"consent": denied})}
    )
    with pytest.raises(M2003AuthorizationError, match="consent"):
        M2003Engine().fuse(request.model_copy(update={"context": context}))


def test_upstream_media_type_is_strict() -> None:
    with pytest.raises(ValueError, match="M20-02"):
        M2003Engine().fuse(_request().model_copy(update={"alignment_result": _artifact("bad")}))


def test_tampering_is_rejected_and_canonical_helpers_are_stable() -> None:
    request = _request()
    digest = canonical_request_digest(request)
    assert verify_request_digest(request, digest)
    assert canonical_request_bytes(request) == canonical_request_bytes(request)
    result = M2003Engine().fuse(request)
    assert verify_result_digest(result, result.result_digest)
    assert canonical_result_payload_bytes(result) == canonical_result_payload_bytes(result)
    with pytest.raises(M2003ReplayError, match="payload digest"):
        M2003Engine().replay(result.model_copy(update={"human_review_required": True}))
    assert not verify_request_digest(
        request.model_copy(update={"aggregate_values": ("changed",)}), digest
    )
    assert not verify_result_digest(
        {**result.model_dump(mode="json"), "human_review_required": True}, result.result_digest
    )


@pytest.mark.parametrize(
    "updates",
    [
        pytest.param({"human_review_required": True}, id="review-flag"),
        pytest.param(
            {
                "support_decision": lambda result: result.support_decision.model_copy(
                    update={"rationale": "forged rationale"}
                )
            },
            id="support-rationale",
        ),
        pytest.param(
            {
                "limitations": lambda result: (
                    result.limitations[0].model_copy(update={"statement": "forged limitation"}),
                    *result.limitations[1:],
                )
            },
            id="limitation-statement",
        ),
        pytest.param(
            {
                "provenance": lambda result: result.provenance.model_copy(
                    update={"actor_id": "actor.forged"}
                )
            },
            id="provenance-actor",
        ),
        pytest.param(
            {
                "evidence": lambda result: (
                    result.evidence[0].model_copy(update={"claim": "forged claim"}),
                    *result.evidence[1:],
                )
            },
            id="evidence-claim",
        ),
        pytest.param(
            {
                "integrated_evidence": lambda result: result.integrated_evidence.model_copy(
                    update={"aggregate_claim": "forged aggregate"}
                )
            },
            id="integrated-claim",
        ),
    ],
)
def test_self_rehashed_semantic_mutations_are_rejected(updates: dict[str, Any]) -> None:
    result = M2003Engine().fuse(_request())
    resolved_updates = {
        name: value(result) if callable(value) else value for name, value in updates.items()
    }
    forged = _self_rehashed(result, resolved_updates)
    assert forged.result_digest == result_payload_digest(forged)
    with pytest.raises(M2003ReplayError, match="deterministic replay"):
        M2003Engine().replay(forged)


def test_service_plugin_parity_and_descriptor_boundaries() -> None:
    request = _request()
    service = M2003Service()
    plugin = M2003Plugin()
    assert service.validate_request(request) == request
    assert plugin.validate_request(request) == request
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M20-03"
    assert plugin.descriptor.parent_target == "protein subtype"
    assert plugin.run(request) == service.fuse(request)
