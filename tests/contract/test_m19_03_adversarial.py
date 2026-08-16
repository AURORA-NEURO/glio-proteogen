"""Adversarial closure tests for the M19-03 contract and replay spine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m19_03 import (
    AggregationConfiguration,
    DisagreementRecord,
    DisagreementStatus,
    FuseProteotypeEvidenceRequest,
    ReliabilityBand,
    SourceContribution,
    SourceKind,
    canonical_request_bytes,
    canonical_request_digest,
    verify_request_digest,
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

_HIGH_RELIABILITY_THRESHOLD = 0.8
_MODERATE_RELIABILITY_THRESHOLD = 0.5


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m1903.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1903:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M19-03 evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m1903.{role}",
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
        request_id="request.m1903.synthetic",
        actor_id="actor.m1903.synthetic",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m1903.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1903.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m1903.consent",
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
        source_id=f"source.m1903.{name}",
        kind=SourceKind.MASS_SPECTROMETRY_PROTEOME,
        owner="M19-03 source owner",
        artifact=artifact,
        claim="component-specific proteotype evidence",
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
    source_artifacts: tuple[ArtifactReference, ...] | None = None,
    disagreements: tuple[DisagreementRecord, ...] = (),
) -> FuseProteotypeEvidenceRequest:
    first = _contribution("proteome")
    second = _contribution("genome", 0.7)
    contributions = (first, second)
    if source_artifacts is None:
        source_artifacts = tuple(item.artifact for item in contributions)
    return FuseProteotypeEvidenceRequest(
        request_id="request.m1903.synthetic",
        context=_context(),
        alignment_result=_artifact("alignment", "application/vnd.glio-proteogen.m19-02+json"),
        contributions=contributions,
        disagreements=disagreements,
        aggregate_values=("integrated_signal=0.84", "source_count=2"),
        configuration=AggregationConfiguration(
            configuration_id="configuration.m1903.synthetic",
            version="1.0.0",
            method="reliability_weighted_component_aggregation",
            reliability_threshold=0.7,
            component_specific=True,
            preserve_source_identity=True,
            preserve_disagreement=True,
            locked=True,
        ),
        source_artifacts=source_artifacts,
    )


def test_reliability_band_cannot_overstate_numeric_score() -> None:
    artifact = _artifact("mismatch")
    with pytest.raises(ValueError, match="reliability band"):
        SourceContribution(
            source_id="source.m1903.mismatch",
            kind=SourceKind.GENOME,
            owner="M19-03 source owner",
            artifact=artifact,
            claim="component-specific genomic evidence",
            reliability_score=0.4,
            reliability_band=ReliabilityBand.HIGH,
            uncertainty_note="Synthetic declaration.",
            evidence=(_evidence(artifact),),
        )


def test_not_evaluable_contribution_cannot_carry_positive_score() -> None:
    artifact = _artifact("not-evaluable")
    with pytest.raises(ValueError, match="zero reliability score"):
        SourceContribution(
            source_id="source.m1903.not-evaluable",
            kind=SourceKind.GENOME,
            owner="M19-03 source owner",
            artifact=artifact,
            claim="component-specific genomic evidence",
            reliability_score=0.1,
            reliability_band=ReliabilityBand.NOT_EVALUABLE,
            uncertainty_note="No supported measurement.",
            evidence=(_evidence(artifact),),
        )


def test_request_rejects_unlisted_contribution_artifact() -> None:
    first = _contribution("proteome")
    with pytest.raises(ValueError, match="every contribution artifact"):
        _request(source_artifacts=(first.artifact,))


def test_request_rejects_duplicate_disagreement_ids() -> None:
    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m1903.same",
        source_ids=("source.m1903.proteome", "source.m1903.genome"),
        description="Synthetic disagreement.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("disagreement")),),
    )
    with pytest.raises(ValueError, match="disagreement ids"):
        _request(disagreements=(disagreement, disagreement))


def test_request_digest_is_stable_and_tamper_sensitive() -> None:
    request = _request()
    digest = canonical_request_digest(request)
    assert verify_request_digest(request, digest)
    assert canonical_request_bytes(request) == canonical_request_bytes(request)
    altered = request.model_copy(update={"aggregate_values": ("integrated_signal=0.85",)})
    assert not verify_request_digest(altered, digest)
