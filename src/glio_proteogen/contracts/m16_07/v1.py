"""Provisional M16-07 downstream typed export contracts.

The dossier requires a versioned, immutable, consent-aware and support-aware
signed downstream contract with explicit ownership and compatibility semantics.
The ABI is not frozen; this contract emits only documented fields and retains
full uncertainty, provenance, support, and safe-abstention boundaries.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m16_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from dossier lines 5700-5743.
M1607_MODULE_ID: Final = "GLIO-PROTEOGEN-M16-07"
M1607_OPERATION: Final = "export_protein_rna_discordance_downstream_contract"
M1607_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1607_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-07+json"
M1607_M1604_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m16-04+json"
M1607_PARENT: Final = "protein_rna_discordance"
M1607_OWNER: Final = "Clinical science"
M1607_SAFETY_CLASS: Final = "S2"
M1607_GATE: Final = "G3"
M1607_PROVISIONAL_ABI: Final = True
M1607_MAX_FIELDS: Final = 128
M1607_MAX_EVIDENCE: Final = 64
M1607_MAX_FINDINGS: Final = 64
M1607_MAX_OWNERSHIP: Final = 32
M1607_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1607_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class ExportStatus(StrEnum):
    SIGNED = "signed"
    ABSTAINED = "abstained"


class CompatibilityStatus(StrEnum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    REVIEW_REQUIRED = "review_required"


class FieldSupportStatus(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    ABSTAINED = "abstained"


class ExportFindingCode(StrEnum):
    OWNERSHIP_MISMATCH = "ownership_mismatch"
    COMPATIBILITY_FAILED = "compatibility_failed"
    CONSENT_MISSING = "consent_missing"
    SUPPORT_MISSING = "support_missing"
    PROVENANCE_MISSING = "provenance_missing"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ExportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    method: NonEmptyStr
    signature_reference: ArtifactReference
    locked: Literal[True] = True
    consent_aware_required: Literal[True] = True
    support_aware_required: Literal[True] = True
    ownership_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1607_MAX_EVIDENCE)


class ExportPolicy(FrozenModel):
    consumer_id: Identifier
    allowed_owner: NonEmptyStr
    required_media_type: NonEmptyStr
    require_signature: Literal[True] = True
    require_consent: Literal[True] = True
    require_support: Literal[True] = True
    configuration: ExportConfiguration


class DownstreamField(FrozenModel):
    field_id: Identifier
    name: NonEmptyStr
    value_type: NonEmptyStr
    owner: NonEmptyStr
    support_status: FieldSupportStatus
    source_artifact: ArtifactReference
    consent_preserved: Literal[True] = True
    provenance_preserved: Literal[True] = True
    uncertainty_preserved: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1607_MAX_EVIDENCE)


class CompatibilityReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    status: CompatibilityStatus
    consumer_id: Identifier
    accepted_field_ids: tuple[Identifier, ...] = Field(default=(), max_length=M1607_MAX_FIELDS)
    reasons: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1607_MAX_FINDINGS)
    auditable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1607_MAX_EVIDENCE)


class SignedDownstreamContract(FrozenModel):
    contract_id: Identifier
    version: SemanticVersion
    producer_module: Literal["GLIO-PROTEOGEN-M16-07"] = M1607_MODULE_ID
    consumer_id: Identifier
    fields: tuple[DownstreamField, ...] = Field(min_length=1, max_length=M1607_MAX_FIELDS)
    ownership: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=M1607_MAX_OWNERSHIP)
    compatibility: CompatibilityReport
    signature: ArtifactReference
    signature_algorithm: NonEmptyStr
    consent_aware: Literal[True] = True
    support_aware: Literal[True] = True
    immutable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1607_MAX_EVIDENCE)

    @model_validator(mode="after")
    def contract_fields_are_closed(self) -> SignedDownstreamContract:
        ids = tuple(item.field_id for item in self.fields)
        if len(ids) != len(set(ids)):
            raise ValueError("downstream field ids must be unique")
        if self.compatibility.status is not CompatibilityStatus.COMPATIBLE:
            raise ValueError("signed contract requires compatible report")
        if set(self.compatibility.accepted_field_ids) != set(ids):
            raise ValueError("signed fields must match compatibility report")
        if self.compatibility.consumer_id != self.consumer_id:
            raise ValueError("compatibility report consumer must match signed contract")
        if not {item.owner for item in self.fields} <= set(self.ownership):
            raise ValueError("signed field ownership must be explicit")
        return self


class ExportFinding(FrozenModel):
    finding_id: Identifier
    code: ExportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1607_MAX_EVIDENCE)


class ExportProteinRnaDiscordanceDownstreamContractRequest(FrozenModel):
    """Provisional request for a signed, typed downstream contract."""

    operation: Literal["export_protein_rna_discordance_downstream_contract"] = M1607_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1607_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    intended_use_result: ArtifactReference
    policy: ExportPolicy
    fields: tuple[DownstreamField, ...] = Field(min_length=1, max_length=M1607_MAX_FIELDS)
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1607_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound_and_unique(self) -> ExportProteinRnaDiscordanceDownstreamContractRequest:
        if self.intended_use_result.media_type != M1607_M1604_RESULT_MEDIA_TYPE:
            raise ValueError("export request must bind the provisional M16-04 result")
        ids = tuple(item.field_id for item in self.fields)
        if len(ids) != len(set(ids)):
            raise ValueError("request downstream field ids must be unique")
        return self


class ProteinRnaDiscordanceDownstreamExportResult(FrozenModel):
    """Signed downstream contract with explicit ownership and safe abstention."""

    output_type: Literal["protein_rna_discordance_downstream_export"] = (
        "protein_rna_discordance_downstream_export"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1607_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ExportProteinRnaDiscordanceDownstreamContractRequest
    status: ExportStatus
    downstream_contract: SignedDownstreamContract | None = None
    compatibility_report: CompatibilityReport
    findings: tuple[ExportFinding, ...] = Field(default=(), max_length=M1607_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein_rna_discordance"] = M1607_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1607_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceDownstreamExportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if not self.evidence or any(item.role != "evidence" for item in self.evidence):
            raise ValueError("export result requires evidence references")
        finding_codes = tuple(item.code for item in self.findings)
        if len(finding_codes) != len(set(finding_codes)):
            raise ValueError("export finding codes must be unique")
        if self.status is ExportStatus.SIGNED:
            if (
                self.downstream_contract is None
                or self.compatibility_report.status is not CompatibilityStatus.COMPATIBLE
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("signed result requires a supported compatible contract")
        elif (
            self.downstream_contract is not None
            or self.abstention_reason is None
            or self.compatibility_report.status is CompatibilityStatus.COMPATIBLE
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no contract and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def expected_uncertainty(*, supported: bool) -> UncertaintyProfile:
    """Expose all seven uncertainty dimensions for downstream export."""

    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED if supported else EstimateState.NOT_ESTIMABLE,
        probability=0.9 if supported else None,
        rationale=(
            "Version, ownership, compatibility, consent, and support checks passed."
            if supported
            else "Export compatibility, ownership, consent, or support was not safely evaluable."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Version compatibility, consent preservation, support semantics, and ownership "
            "remain explicit at the downstream boundary.",
        ),
    )


def expected_provenance(
    request: ExportProteinRnaDiscordanceDownstreamContractRequest,
    request_digest: Sha256Digest,
) -> ProvenanceRecord:
    """Bind export fields, policy, and the seven caller-declared controls."""

    references = request.context.references
    controls = (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=references.approved_configuration.decision_id,
            state=references.approved_configuration.state.value,
            policy_version=references.approved_configuration.policy_version,
            evidence_digest=references.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=references.identity_lineage.decision_id,
            state=references.identity_lineage.state.value,
            policy_version=references.identity_lineage.policy_version,
            evidence_digest=references.identity_lineage.evidence.digest,
            subject_digest=references.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=references.provenance.decision_id,
            state=references.provenance.state.value,
            policy_version=references.provenance.policy_version,
            evidence_digest=references.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=references.consent.decision_id,
            state=references.consent.state.value,
            policy_version=references.consent.policy_version,
            evidence_digest=references.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=references.quality.decision_id,
            state=references.quality.state.value,
            policy_version=references.quality.policy_version,
            evidence_digest=references.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=references.support.decision_id,
            state=references.support.state.value,
            policy_version=references.support.policy_version,
            evidence_digest=references.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=references.intended_use.decision_id,
            state=references.intended_use.state.value,
            policy_version=references.intended_use.policy_version,
            evidence_digest=references.intended_use.evidence.digest,
        ),
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1607_MODULE_ID,
        module_version=M1607_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request_digest,
            request.intended_use_result.digest,
            *(item.source_artifact.digest for item in request.fields),
            *(item.digest for item in request.source_artifacts),
        ),
        configuration_digest=sha256_digest(request.policy.configuration.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


__all__ = [
    "M1607_CONTRACT_VERSION",
    "M1607_GATE",
    "M1607_M1604_RESULT_MEDIA_TYPE",
    "M1607_MAX_CANONICAL_REQUEST_BYTES",
    "M1607_MAX_CANONICAL_RESULT_BYTES",
    "M1607_MAX_EVIDENCE",
    "M1607_MAX_FIELDS",
    "M1607_MAX_FINDINGS",
    "M1607_MAX_OWNERSHIP",
    "M1607_MODULE_ID",
    "M1607_OPERATION",
    "M1607_OUTPUT_MEDIA_TYPE",
    "M1607_OWNER",
    "M1607_PARENT",
    "M1607_PROVISIONAL_ABI",
    "M1607_SAFETY_CLASS",
    "CompatibilityReport",
    "CompatibilityStatus",
    "DownstreamField",
    "ExportConfiguration",
    "ExportFinding",
    "ExportFindingCode",
    "ExportPolicy",
    "ExportProteinRnaDiscordanceDownstreamContractRequest",
    "ExportStatus",
    "FieldSupportStatus",
    "ProteinRnaDiscordanceDownstreamExportResult",
    "SignedDownstreamContract",
    "expected_provenance",
    "expected_uncertainty",
]
