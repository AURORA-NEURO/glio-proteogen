"""Provisional M17-07 downstream typed export contracts.

M17-07 owns a versioned, immutable, consent-aware and support-aware export
beneath Metabolomic/lipidomic integration.  The ABI is intentionally
provisional because the dossier provides behavior and acceptance requirements,
not an owner-approved production schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m17_07.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
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
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from the M17-07 dossier slice.
M1707_MODULE_ID: Final = "GLIO-PROTEOGEN-M17-07"
M1707_OPERATION: Final = "export_variant_peptide_downstream_contract"
M1707_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1707_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-07+json"
M1707_M1706_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m17-06+json"
M1707_PARENT: Final = "variant peptide"
M1707_OWNER: Final = "Data engineering"
M1707_SAFETY_CLASS: Final = "S2"
M1707_GATE: Final = "G3"
M1707_PROVISIONAL_ABI: Final = True
M1707_MAX_FIELDS: Final = 128
M1707_MAX_EVIDENCE: Final = 64
M1707_MAX_FINDINGS: Final = 64
M1707_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1707_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1707_EVIDENCE_CLAIM: Final = (
    "Caller-declared M17-07 field, consent, support, ownership, compatibility "
    "and signature material; issuer authority is not authenticated."
)


class ExportStatus(StrEnum):
    EXPORTED = "exported"
    ABSTAINED = "abstained"


class CompatibilityMode(StrEnum):
    VERSIONED = "versioned"
    STRICT = "strict"
    REVIEW_REQUIRED = "review_required"


class ExportFieldType(StrEnum):
    BOOLEAN = "boolean"
    DECIMAL = "decimal"
    ENUM = "enum"
    IDENTIFIER = "identifier"
    REFERENCE = "reference"
    TEXT = "text"


class ExportFindingCode(StrEnum):
    FIELD_UNDOCUMENTED = "field_undocumented"
    CONSENT_WITHHELD = "consent_withheld"
    SUPPORT_BOUNDARY = "support_boundary"
    COMPATIBILITY_MISMATCH = "compatibility_mismatch"
    SIGNATURE_MISSING = "signature_missing"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class ExportField(FrozenModel):
    """One documented, typed export field with an immutable source binding."""

    field_id: Identifier
    field_name: Identifier
    value_type: ExportFieldType
    field_version: SemanticVersion
    owner: NonEmptyStr
    documentation: NonEmptyStr
    value_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1707_MAX_EVIDENCE)


class ExportOwnershipBinding(FrozenModel):
    """Explicit owner and boundary for the downstream contract object."""

    owning_module: Identifier
    owner: NonEmptyStr
    ownership_statement: NonEmptyStr
    parent_target: Literal["variant peptide"] = M1707_PARENT
    kinase_activity_owned_elsewhere: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1707_MAX_EVIDENCE)


class SignedContractEnvelope(FrozenModel):
    """Signature binding for an immutable downstream contract projection."""

    signer_id: Identifier
    algorithm: NonEmptyStr
    signed_payload_digest: Sha256Digest
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1707_MAX_EVIDENCE)


class DownstreamExportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    compatibility: CompatibilityMode
    parent_target: Literal["variant peptide"] = M1707_PARENT
    documented_fields_only: Literal[True] = True
    immutable: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1707_MAX_EVIDENCE)


class DownstreamContractObject(FrozenModel):
    """Immutable typed export object with ownership, consent and signature."""

    contract_id: Identifier
    version: SemanticVersion
    media_type: Literal["application/vnd.glio-proteogen.m17-07+json"] = M1707_OUTPUT_MEDIA_TYPE
    parent_target: Literal["variant peptide"] = M1707_PARENT
    fields: tuple[ExportField, ...] = Field(min_length=1, max_length=M1707_MAX_FIELDS)
    ownership: ExportOwnershipBinding
    consent: ConsentReference
    support_decision: SupportDecision
    configuration: DownstreamExportConfiguration
    signature: SignedContractEnvelope
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1707_MAX_EVIDENCE)

    @model_validator(mode="after")
    def contract_is_closed(self) -> DownstreamContractObject:
        field_ids = tuple(item.field_id for item in self.fields)
        field_names = tuple(item.field_name for item in self.fields)
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("export field ids must be unique")
        if len(field_names) != len(set(field_names)):
            raise ValueError("export field names must be unique")
        if self.consent.state is not ConsentState.GRANTED:
            raise ValueError("downstream contract requires granted consent")
        if self.support_decision.status is not SupportStatus.SUPPORTED:
            raise ValueError("downstream contract requires supported status")
        if self.ownership.owning_module != M1707_MODULE_ID:
            raise ValueError("ownership binding must name M17-07")
        if self.configuration.parent_target != M1707_PARENT:
            raise ValueError("export configuration parent target is invalid")
        if self.signature.signed_payload_digest == "sha256:" + ("0" * 64):
            raise ValueError("signed contract payload digest cannot be empty")
        field_evidence = {
            evidence.reference.digest for field in self.fields for evidence in field.evidence
        }
        if not field_evidence.issubset({evidence.reference.digest for evidence in self.evidence}):
            raise ValueError("contract evidence must include every field evidence reference")
        return self


class ExportFinding(FrozenModel):
    finding_id: Identifier
    code: ExportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1707_MAX_EVIDENCE)


class ExportVariantPeptideDownstreamContractRequest(FrozenModel):
    """Provisional request bound to the M17-06 adjudication result."""

    operation: Literal["export_variant_peptide_downstream_contract"] = M1707_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1707_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    adjudication_result: ArtifactReference
    fields: tuple[ExportField, ...] = Field(min_length=1, max_length=M1707_MAX_FIELDS)
    consent: ConsentReference
    support_decision: SupportDecision
    configuration: DownstreamExportConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1707_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ExportVariantPeptideDownstreamContractRequest:
        if self.adjudication_result.media_type != M1707_M1706_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M17-06 adjudication result")
        field_ids = tuple(item.field_id for item in self.fields)
        field_names = tuple(item.field_name for item in self.fields)
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("request export field ids must be unique")
        if len(field_names) != len(set(field_names)):
            raise ValueError("request export field names must be unique")
        context_consent = self.context.references.consent
        if (
            self.consent.decision_id != context_consent.decision_id
            or self.consent.state is not context_consent.state
            or self.consent.evidence.digest != context_consent.evidence.digest
        ):
            raise ValueError("request consent must bind the caller-declared consent control")
        if self.configuration.parent_target != M1707_PARENT:
            raise ValueError("request configuration parent target is invalid")
        source_digests = tuple(artifact.digest for artifact in self.source_artifacts)
        if len(source_digests) != len(set(source_digests)):
            raise ValueError("request source artifacts must be unique")
        if self.adjudication_result.digest not in source_digests:
            raise ValueError("adjudication result must be listed in source artifacts")
        for field in self.fields:
            if field.value_digest not in source_digests:
                raise ValueError("export field value must bind a request source artifact")
            if any(evidence.reference.digest not in source_digests for evidence in field.evidence):
                raise ValueError("export field evidence must bind request source artifacts")
        return self


class VariantPeptideDownstreamExportResult(FrozenModel):
    """Typed export result with explicit consent, support and safe abstention."""

    output_type: Literal["variant_peptide_downstream_contract"] = (
        "variant_peptide_downstream_contract"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1707_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ExportVariantPeptideDownstreamContractRequest
    status: ExportStatus
    contract: DownstreamContractObject | None = None
    findings: tuple[ExportFinding, ...] = Field(default=(), max_length=M1707_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant peptide"] = M1707_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1707_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideDownstreamExportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is ExportStatus.EXPORTED:
            if (
                self.contract is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.request.consent.state is not ConsentState.GRANTED
            ):
                raise ValueError("exported result requires supported status and granted consent")
        elif (
            self.contract is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no contract and safe status")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        finding_codes = tuple(finding.code for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("export finding ids must be unique")
        if len(finding_codes) != len(set(finding_codes)):
            raise ValueError("export finding codes must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1707_CONTRACT_VERSION",
    "M1707_EVIDENCE_CLAIM",
    "M1707_GATE",
    "M1707_M1706_INPUT_MEDIA_TYPE",
    "M1707_MAX_CANONICAL_REQUEST_BYTES",
    "M1707_MAX_CANONICAL_RESULT_BYTES",
    "M1707_MAX_EVIDENCE",
    "M1707_MAX_FIELDS",
    "M1707_MAX_FINDINGS",
    "M1707_MODULE_ID",
    "M1707_OPERATION",
    "M1707_OUTPUT_MEDIA_TYPE",
    "M1707_OWNER",
    "M1707_PARENT",
    "M1707_PROVISIONAL_ABI",
    "M1707_SAFETY_CLASS",
    "CompatibilityMode",
    "DownstreamContractObject",
    "DownstreamExportConfiguration",
    "ExportField",
    "ExportFieldType",
    "ExportFinding",
    "ExportFindingCode",
    "ExportOwnershipBinding",
    "ExportStatus",
    "ExportVariantPeptideDownstreamContractRequest",
    "SignedContractEnvelope",
    "VariantPeptideDownstreamExportResult",
]
