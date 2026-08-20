"""Provisional M20-07 downstream typed export contracts.

M20-07 owns a versioned, immutable, consent-aware and support-aware export
beneath Biomarker-panel translation. The ABI is provisional because the
dossier provides behavior and acceptance requirements, not an owner-approved
production schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m20_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M20-07 dossier slice.
M2007_MODULE_ID: Final = "GLIO-PROTEOGEN-M20-07"
M2007_OPERATION: Final = "export_protein_subtype_downstream_contract"
M2007_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2007_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-07+json"
M2007_M2006_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m20-06+json"
M2007_PARENT: Final = "protein subtype"
M2007_OWNER: Final = "Computational biology"
M2007_SAFETY_CLASS: Final = "S2"
M2007_GATE: Final = "G3"
M2007_PROVISIONAL_ABI: Final = True
M2007_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2007_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7140-7180"
M2007_MAX_FIELDS: Final = 128
M2007_MAX_EVIDENCE: Final = 64
M2007_MAX_FINDINGS: Final = 64
M2007_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2007_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2007_EVIDENCE_CLAIM: Final = (
    "Caller-declared M20-07 field, consent, support, ownership, compatibility "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2007_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_is_unique(self) -> ExportField:
        digests = tuple(item.reference.digest for item in self.evidence)
        if len(digests) != len(set(digests)):
            raise ValueError("export field evidence must be unique")
        return self


class ExportOwnershipBinding(FrozenModel):
    """Explicit owner and boundary for the downstream contract object."""

    owning_module: Identifier
    owner: NonEmptyStr
    ownership_statement: NonEmptyStr
    parent_target: Literal["protein subtype"] = M2007_PARENT
    kinase_activity_owned_elsewhere: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2007_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_is_unique(self) -> ExportOwnershipBinding:
        digests = tuple(item.reference.digest for item in self.evidence)
        if len(digests) != len(set(digests)):
            raise ValueError("ownership evidence must be unique")
        return self


class SignedContractEnvelope(FrozenModel):
    """Signature binding for an immutable downstream contract projection."""

    signer_id: Identifier
    algorithm: NonEmptyStr
    signed_payload_digest: Sha256Digest
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2007_MAX_EVIDENCE)

    @model_validator(mode="after")
    def evidence_is_unique(self) -> SignedContractEnvelope:
        digests = tuple(item.reference.digest for item in self.evidence)
        if len(digests) != len(set(digests)):
            raise ValueError("signature evidence must be unique")
        return self


class DownstreamExportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    compatibility: CompatibilityMode
    parent_target: Literal["protein subtype"] = M2007_PARENT
    documented_fields_only: Literal[True] = True
    immutable: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2007_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_is_closed(self) -> DownstreamExportConfiguration:
        if not self.documented_fields_only or not self.immutable or not self.locked:
            raise ValueError(
                "downstream export configuration must be documented, immutable, and locked"
            )
        digests = tuple(item.reference.digest for item in self.evidence)
        if len(digests) != len(set(digests)):
            raise ValueError("configuration evidence must be unique")
        return self


class DownstreamContractObject(FrozenModel):
    """Immutable typed export object with ownership, consent and signature."""

    contract_id: Identifier
    version: SemanticVersion
    media_type: Literal["application/vnd.glio-proteogen.m20-07+json"] = M2007_OUTPUT_MEDIA_TYPE
    parent_target: Literal["protein subtype"] = M2007_PARENT
    fields: tuple[ExportField, ...] = Field(min_length=1, max_length=M2007_MAX_FIELDS)
    ownership: ExportOwnershipBinding
    consent: ConsentReference
    support_decision: SupportDecision
    configuration: DownstreamExportConfiguration
    signature: SignedContractEnvelope
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2007_MAX_EVIDENCE)

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
        if self.ownership.owning_module != M2007_MODULE_ID:
            raise ValueError("ownership binding must name M20-07")
        if (
            not self.configuration.documented_fields_only
            or not self.configuration.immutable
            or not self.configuration.locked
        ):
            raise ValueError("downstream contract configuration is not locked")
        return self


class ExportFinding(FrozenModel):
    finding_id: Identifier
    code: ExportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2007_MAX_EVIDENCE)


class ExportProteinSubtypeDownstreamContractRequest(FrozenModel):
    """Provisional request bound to the M20-06 upstream result."""

    operation: Literal["export_protein_subtype_downstream_contract"] = M2007_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2007_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    fields: tuple[ExportField, ...] = Field(min_length=1, max_length=M2007_MAX_FIELDS)
    consent: ConsentReference
    support_decision: SupportDecision
    configuration: DownstreamExportConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2007_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ExportProteinSubtypeDownstreamContractRequest:
        if self.upstream_result.media_type != M2007_M2006_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M20-06 upstream result")
        field_ids = tuple(item.field_id for item in self.fields)
        field_names = tuple(item.field_name for item in self.fields)
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("request export field ids must be unique")
        if len(field_names) != len(set(field_names)):
            raise ValueError("request export field names must be unique")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("request source artifact ids must be unique")
        if (
            self.consent.state is ConsentState.GRANTED
            and self.consent != self.context.references.consent
        ):
            raise ValueError("granted request consent must bind the context consent control")
        return self


class ProteinSubtypeDownstreamExportResult(FrozenModel):
    """Typed export result with explicit consent, support and safe abstention."""

    output_type: Literal["protein_subtype_downstream_contract"] = (
        "protein_subtype_downstream_contract"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2007_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ExportProteinSubtypeDownstreamContractRequest
    status: ExportStatus
    contract: DownstreamContractObject | None = None
    findings: tuple[ExportFinding, ...] = Field(default=(), max_length=M2007_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2007_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2007_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeDownstreamExportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("export finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("export result evidence digests must be unique")
        if self.status is ExportStatus.EXPORTED:
            if (
                self.contract is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.request.consent.state is not ConsentState.GRANTED
                or self.human_review_required
            ):
                raise ValueError("exported result requires supported status and granted consent")
        elif (
            self.contract is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or not self.human_review_required
        ):
            raise ValueError("abstained result requires no contract and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2007_CONTRACT_VERSION",
    "M2007_DOSSIER_SHA256",
    "M2007_DOSSIER_SLICE",
    "M2007_EVIDENCE_CLAIM",
    "M2007_GATE",
    "M2007_M2006_INPUT_MEDIA_TYPE",
    "M2007_MAX_CANONICAL_REQUEST_BYTES",
    "M2007_MAX_CANONICAL_RESULT_BYTES",
    "M2007_MAX_EVIDENCE",
    "M2007_MAX_FIELDS",
    "M2007_MAX_FINDINGS",
    "M2007_MODULE_ID",
    "M2007_OPERATION",
    "M2007_OUTPUT_MEDIA_TYPE",
    "M2007_OWNER",
    "M2007_PARENT",
    "M2007_PROVISIONAL_ABI",
    "M2007_SAFETY_CLASS",
    "CompatibilityMode",
    "DownstreamContractObject",
    "DownstreamExportConfiguration",
    "ExportField",
    "ExportFieldType",
    "ExportFinding",
    "ExportFindingCode",
    "ExportOwnershipBinding",
    "ExportProteinSubtypeDownstreamContractRequest",
    "ExportStatus",
    "ProteinSubtypeDownstreamExportResult",
    "SignedContractEnvelope",
]
