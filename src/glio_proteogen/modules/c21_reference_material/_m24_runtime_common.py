# ruff: noqa: INP001, PLR0913, PLR0917
"""Shared fail-closed helpers for the provisional M24 runtime family.

These helpers deliberately operate on caller-declared contracts only.  They
do not authenticate artifacts, infer identity, or turn an unsupported input
into a negative scientific finding.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageReference,
    IdentityLineageState,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import ArtifactReference, ExecutionContext


class AuthorizationError(ValueError):
    """Raised when one of the seven execution controls is not accepted."""

    def __init__(self, module_id: str) -> None:
        super().__init__(
            f"{module_id} requires accepted configuration, identity, provenance, "
            "consent, quality, support and intended-use controls"
        )


def member(candidate: object, name: str) -> object:
    """Read one field without traversing hostile mapping contents."""

    if isinstance(candidate, Mapping):
        return candidate.get(name)
    return getattr(candidate, name, None)


def state_value(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def preflight(candidate: object, module_id: str) -> None:
    """Fail closed before any module-specific caller material is inspected."""

    try:
        context = member(candidate, "context")
        references = member(context, "references")
        expected = {
            "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
            "identity_lineage": IdentityLineageState.RESOLVED.value,
            "provenance": UpstreamDecisionState.ACCEPTED.value,
            "consent": ConsentState.GRANTED.value,
            "quality": UpstreamDecisionState.ACCEPTED.value,
            "support": UpstreamDecisionState.ACCEPTED.value,
            "intended_use": UpstreamDecisionState.ACCEPTED.value,
        }
        accepted = all(
            state_value(member(member(references, role), "state")) == expected_state
            for role, expected_state in expected.items()
        )
    except Exception:  # noqa: BLE001 - hostile mappings must fail closed.
        raise AuthorizationError(module_id) from None
    if not accepted:
        raise AuthorizationError(module_id)


def uncertainty(module_id: str) -> UncertaintyProfile:
    def unavailable(dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale=f"{module_id} does not infer {dimension} uncertainty from caller material.",
        )

    return UncertaintyProfile(
        measurement=unavailable("measurement"),
        sampling=unavailable("sampling"),
        parameter=unavailable("parameter"),
        model_form=unavailable("model form"),
        identification=unavailable("identification"),
        support=unavailable("support"),
        transport=unavailable("transport"),
        sensitivity_notes=(
            "This provisional evaluator reports deterministic caller-declared material only.",
        ),
    )


def evidence(
    artifacts: Sequence[ArtifactReference],
    claim: str,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=claim)
        for artifact in artifacts
    )


def provenance(
    context: ExecutionContext,
    source_artifacts: Sequence[ArtifactReference],
    request_digest: str,
    module_id: str,
    version: str,
    configuration_digest: str,
) -> ProvenanceRecord:
    references = context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=str(decision.state.value),
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                decision.binding_digest if isinstance(decision, IdentityLineageReference) else None
            ),
        )
        for role, decision in controls
    )
    return ProvenanceRecord(
        activity_id=f"{module_id.lower()}.activity.{request_digest.removeprefix('sha256:')}",
        actor_id=context.actor_id,
        module_id=module_id,
        module_version=version,
        generated_at=context.occurred_at,
        input_digests=tuple(a.digest for a in source_artifacts),
        configuration_digest=configuration_digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def support(status: SupportStatus, reason: str, rationale: str) -> SupportDecision:
    return SupportDecision(status=status, reason_code=reason, rationale=rationale)


__all__ = [
    "AuthorizationError",
    "evidence",
    "member",
    "preflight",
    "provenance",
    "state_value",
    "support",
    "uncertainty",
]
