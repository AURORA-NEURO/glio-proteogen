"""Strict, immutable contracts shared by active modules.

The kernel is intentionally small. Every type in this file is exercised by M01-01 and
encodes a dossier-wide safety invariant: explicit support, explicit uncertainty, immutable
references, and no nullable shorthand for missing evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _non_blank_unpadded(value: str) -> str:
    if not value.strip() or value != value.strip():
        raise ValueError("text must be non-blank and have no surrounding whitespace")
    return value


NonEmptyStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512),
    AfterValidator(_non_blank_unpadded),
]
Identifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-zA-Z][a-zA-Z0-9._:-]{0,127}$"),
]
SemanticVersion = Annotated[
    str,
    StringConstraints(
        max_length=128,
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
        r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
    ),
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class FrozenModel(BaseModel):
    """Base class that forbids coercion, mutation, NaN, infinity, and unknown fields."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
        str_strip_whitespace=False,
    )


class ArtifactReference(FrozenModel):
    """Content-addressed reference to evidence owned outside the current module."""

    artifact_id: Identifier
    version: SemanticVersion
    digest: Sha256Digest
    media_type: NonEmptyStr


class ConsentState(StrEnum):
    GRANTED = "granted"
    WITHHELD = "withheld"
    REVOKED = "revoked"
    UNKNOWN = "unknown"


class ConsentReference(FrozenModel):
    """Consent decision supplied by an owning authority; this module never infers it."""

    decision_id: Identifier
    state: ConsentState
    policy_version: SemanticVersion
    evidence: ArtifactReference


class UpstreamDecisionState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class UpstreamDecisionReference(FrozenModel):
    """Typed caller-declared decision for an externally owned control artifact."""

    decision_id: Identifier
    state: UpstreamDecisionState
    policy_version: SemanticVersion
    evidence: ArtifactReference


class IdentityLineageState(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CONFLICTED = "conflicted"


class IdentityLineageReference(FrozenModel):
    """Typed identity-lineage decision bound to canonical identity-key evidence."""

    decision_id: Identifier
    state: IdentityLineageState
    policy_version: SemanticVersion
    binding_digest: Sha256Digest
    evidence: ArtifactReference


class ContextReferences(FrozenModel):
    """Required upstream control objects for every M01-01 operation."""

    approved_configuration: UpstreamDecisionReference
    identity_lineage: IdentityLineageReference
    provenance: UpstreamDecisionReference
    consent: ConsentReference
    quality: UpstreamDecisionReference
    support: UpstreamDecisionReference
    intended_use: UpstreamDecisionReference


class ExecutionContext(FrozenModel):
    """Auditable execution identity and immutable upstream references."""

    request_id: Identifier
    actor_id: Identifier
    occurred_at: AwareDatetime
    references: ContextReferences


class SupportStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"
    REVIEW_REQUIRED = "review_required"


class SupportDecision(FrozenModel):
    """Typed support result that prevents unsupported data from looking negative."""

    status: SupportStatus
    reason_code: Identifier
    rationale: NonEmptyStr


class EstimateState(StrEnum):
    ESTIMATED = "estimated"
    NOT_ESTIMABLE = "not_estimable"
    NOT_APPLICABLE = "not_applicable"


class UncertaintyEstimate(FrozenModel):
    """One uncertainty dimension with an explicit non-estimable state."""

    state: EstimateState
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def probability_matches_state(self) -> UncertaintyEstimate:
        if self.state is EstimateState.ESTIMATED and self.probability is None:
            raise ValueError("estimated uncertainty requires probability")
        if self.state is not EstimateState.ESTIMATED and self.probability is not None:
            raise ValueError("non-estimated uncertainty cannot carry probability")
        return self


class UncertaintyProfile(FrozenModel):
    """All seven uncertainty dimensions required by the dossier."""

    measurement: UncertaintyEstimate
    sampling: UncertaintyEstimate
    parameter: UncertaintyEstimate
    model_form: UncertaintyEstimate
    identification: UncertaintyEstimate
    support: UncertaintyEstimate
    transport: UncertaintyEstimate
    sensitivity_notes: tuple[NonEmptyStr, ...] = Field(default=(), max_length=256)


class EvidenceReference(FrozenModel):
    """Evidence or counter-evidence linked without copying or relabeling it."""

    reference: ArtifactReference
    role: Annotated[str, StringConstraints(pattern=r"^(evidence|counter_evidence)$")]
    claim: NonEmptyStr


class ControlRole(StrEnum):
    APPROVED_CONFIGURATION = "approved_configuration"
    IDENTITY_LINEAGE = "identity_lineage"
    PROVENANCE = "provenance"
    CONSENT = "consent"
    QUALITY = "quality"
    SUPPORT = "support"
    INTENDED_USE = "intended_use"


class ControlDecisionRecord(FrozenModel):
    """Privacy-minimized audit material for one caller-declared control decision."""

    role: ControlRole
    decision_id: Identifier
    state: Identifier
    policy_version: SemanticVersion
    evidence_digest: Sha256Digest
    subject_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def subject_binding_matches_role(self) -> ControlDecisionRecord:
        if (self.role is ControlRole.IDENTITY_LINEAGE) != (self.subject_digest is not None):
            raise ValueError("only identity lineage requires a subject binding digest")
        allowed_states = {
            ControlRole.APPROVED_CONFIGURATION: {state.value for state in UpstreamDecisionState},
            ControlRole.IDENTITY_LINEAGE: {state.value for state in IdentityLineageState},
            ControlRole.PROVENANCE: {state.value for state in UpstreamDecisionState},
            ControlRole.CONSENT: {state.value for state in ConsentState},
            ControlRole.QUALITY: {state.value for state in UpstreamDecisionState},
            ControlRole.SUPPORT: {state.value for state in UpstreamDecisionState},
            ControlRole.INTENDED_USE: {state.value for state in UpstreamDecisionState},
        }[self.role]
        if self.state not in allowed_states:
            raise ValueError("control decision state is invalid for its role")
        return self


class ProvenanceRecord(FrozenModel):
    """Module-local provenance derived from immutable source references."""

    activity_id: Identifier
    actor_id: Identifier
    module_id: Annotated[
        str,
        StringConstraints(pattern=r"^GLIO-PROTEOGEN-M\d{2}-\d{2}$"),
    ]
    module_version: SemanticVersion
    generated_at: AwareDatetime
    input_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=10_000)
    configuration_digest: Sha256Digest
    consent_decision_id: Identifier
    consent_state: ConsentState
    consent_policy_version: SemanticVersion
    consent_evidence_digest: Sha256Digest
    control_decisions: tuple[ControlDecisionRecord, ...] = Field(min_length=7, max_length=7)

    @field_validator("control_decisions")
    @classmethod
    def every_control_role_is_recorded(
        cls,
        decisions: tuple[ControlDecisionRecord, ...],
    ) -> tuple[ControlDecisionRecord, ...]:
        roles = {decision.role for decision in decisions}
        if roles != set(ControlRole):
            raise ValueError("provenance must record every upstream control role exactly once")
        return decisions


class Limitation(FrozenModel):
    """Machine-readable ceiling on interpretation or use."""

    code: Identifier
    statement: NonEmptyStr
