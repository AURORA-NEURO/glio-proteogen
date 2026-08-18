"""Provisional M19-07 downstream typed export contracts.

M19-07 owns a versioned, immutable, consent-aware and support-aware export
beneath Immunopeptidomic evidence. The ABI is provisional because the dossier
provides behavior and acceptance requirements, not an owner-approved
production schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m19_07.canonical import (
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

# PROVISIONAL ABI: inferred solely from the M19-07 dossier slice.
M1907_MODULE_ID: Final = "GLIO-PROTEOGEN-M19-07"
M1907_OPERATION: Final = "export_proteotype_downstream_contract"
M1907_CONTRACT_VERSION: Final = "0.1.0-provisional"
M1907_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-07+json"
M1907_M1906_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m19-06+json"
M1907_PARENT: Final = "proteotype"
M1907_OWNER: Final = "Scientific engineering"
M1907_SAFETY_CLASS: Final = "S2"
M1907_GATE: Final = "G3"
M1907_PROVISIONAL_ABI: Final = True
M1907_MAX_FIELDS: Final = 128
M1907_MAX_EVIDENCE: Final = 64
M1907_MAX_FINDINGS: Final = 64
M1907_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M1907_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M1907_EVIDENCE_CLAIM: Final = (
    "Caller-declared M19-07 field, consent, support, ownership, compatibility "
    "and signature material; issuer authority is not authenticated."
)
M1907_PROHIBITED_CLAIM_TERMS: Final = (
    "all-omics",
    "multi-omics",
    "multiomics",
    "kinase activity",
    "kinophos",
    "treatment recommendation",
    "therapy recommendation",
    "identity inference",
    "infer identity",
    "consent inference",
    "infer consent",
    "mutation inference",
    "infer mutation",
    "protein inference",
    "proteoform",
    "isoform",
    "glioma-specific",
    "glioma specific biology",
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
    PROHIBITED_CLAIM_BOUNDARY = "prohibited_claim_boundary"


class ExportField(FrozenModel):
    """One documented, typed export field with an immutable source binding."""

    field_id: Identifier
    field_name: Identifier
    value_type: ExportFieldType
    field_version: SemanticVersion
    owner: NonEmptyStr
    documentation: NonEmptyStr
    value_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1907_MAX_EVIDENCE)

    @model_validator(mode="after")
    def field_identity_is_closed(self) -> ExportField:
        if self.field_id == self.field_name:
            raise ValueError("export field id and name must be distinct")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("export field evidence digests must be unique")
        return self


class ExportOwnershipBinding(FrozenModel):
    """Explicit owner and boundary for the downstream contract object."""

    owning_module: Identifier
    owner: NonEmptyStr
    ownership_statement: NonEmptyStr
    parent_target: Literal["proteotype"] = M1907_PARENT
    kinase_activity_owned_elsewhere: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1907_MAX_EVIDENCE)

    @model_validator(mode="after")
    def ownership_is_module_bound(self) -> ExportOwnershipBinding:
        if self.owning_module != M1907_MODULE_ID:
            raise ValueError("ownership binding must name M19-07")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("ownership evidence digests must be unique")
        return self


class SignedContractEnvelope(FrozenModel):
    """Signature binding for an immutable downstream contract projection."""

    signer_id: Identifier
    algorithm: NonEmptyStr
    signed_payload_digest: Sha256Digest
    signature_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1907_MAX_EVIDENCE)

    @model_validator(mode="after")
    def signature_digests_are_distinct(self) -> SignedContractEnvelope:
        if self.signed_payload_digest == self.signature_digest:
            raise ValueError("signed payload and signature digests must be distinct")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("signature evidence digests must be unique")
        return self


class DownstreamExportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    compatibility: CompatibilityMode
    parent_target: Literal["proteotype"] = M1907_PARENT
    documented_fields_only: Literal[True] = True
    immutable: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1907_MAX_EVIDENCE)

    @model_validator(mode="after")
    def configuration_evidence_is_unique(self) -> DownstreamExportConfiguration:
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("configuration evidence digests must be unique")
        return self


class DownstreamContractObject(FrozenModel):
    """Immutable typed export object with ownership, consent and signature."""

    contract_id: Identifier
    version: SemanticVersion
    media_type: Literal["application/vnd.glio-proteogen.m19-07+json"] = M1907_OUTPUT_MEDIA_TYPE
    parent_target: Literal["proteotype"] = M1907_PARENT
    fields: tuple[ExportField, ...] = Field(min_length=1, max_length=M1907_MAX_FIELDS)
    ownership: ExportOwnershipBinding
    consent: ConsentReference
    support_decision: SupportDecision
    configuration: DownstreamExportConfiguration
    signature: SignedContractEnvelope
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M1907_MAX_EVIDENCE)

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
        if self.ownership.owning_module != M1907_MODULE_ID:
            raise ValueError("ownership binding must name M19-07")
        if self.configuration.version != self.version:
            raise ValueError("export configuration and contract versions must match")
        if any(field.owner != self.ownership.owner for field in self.fields):
            raise ValueError("export fields must preserve the ownership binding")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("contract evidence digests must be unique")
        return self


class ExportFinding(FrozenModel):
    finding_id: Identifier
    code: ExportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1907_MAX_EVIDENCE)


class ExportProteotypeDownstreamContractRequest(FrozenModel):
    """Provisional request bound to the M19-06 upstream result."""

    operation: Literal["export_proteotype_downstream_contract"] = M1907_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M1907_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    fields: tuple[ExportField, ...] = Field(min_length=1, max_length=M1907_MAX_FIELDS)
    consent: ConsentReference
    support_decision: SupportDecision
    configuration: DownstreamExportConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M1907_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ExportProteotypeDownstreamContractRequest:
        if self.upstream_result.media_type != M1907_M1906_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M19-06 upstream result")
        field_ids = tuple(item.field_id for item in self.fields)
        field_names = tuple(item.field_name for item in self.fields)
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("request export field ids must be unique")
        if len(field_names) != len(set(field_names)):
            raise ValueError("request export field names must be unique")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must match request id")
        if self.consent != self.context.references.consent:
            raise ValueError("request consent must bind the context consent control")
        source_digests = tuple(item.digest for item in self.source_artifacts)
        if len(source_digests) != len(set(source_digests)):
            raise ValueError("request source artifact digests must be unique")
        field_evidence = tuple(
            evidence.reference.digest for field in self.fields for evidence in field.evidence
        )
        if len(field_evidence) != len(set(field_evidence)):
            raise ValueError("request field evidence digests must be unique")
        return self


class ProteotypeDownstreamExportResult(FrozenModel):
    """Typed export result with explicit consent, support and safe abstention."""

    output_type: Literal["proteotype_downstream_contract"] = "proteotype_downstream_contract"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M1907_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ExportProteotypeDownstreamContractRequest
    status: ExportStatus
    contract: DownstreamContractObject | None = None
    findings: tuple[ExportFinding, ...] = Field(default=(), max_length=M1907_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M1907_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M1907_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeDownstreamExportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        expected_result_id = f"result.{self.request_digest.removeprefix('sha256:')}"
        if self.result_id != expected_result_id:
            raise ValueError("result identifier must be derived from request digest")
        if self.provenance.module_id != M1907_MODULE_ID:
            raise ValueError("result provenance must identify M19-07")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("result evidence digests must be unique")
        if self.status is ExportStatus.EXPORTED:
            if (
                self.contract is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.request.consent.state is not ConsentState.GRANTED
                or self.request.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("exported result requires supported status and granted consent")
        elif (
            self.contract is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no contract and safe status")
        if self.status is ExportStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstained result requires human review")
        if self.contract is not None and (
            self.contract.fields != self.request.fields
            or self.contract.consent != self.request.consent
            or self.contract.support_decision != self.request.support_decision
            or self.contract.configuration != self.request.configuration
        ):
            raise ValueError(
                "export contract must bind request fields, consent, support and configuration"
            )
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M1907_CONTRACT_VERSION",
    "M1907_EVIDENCE_CLAIM",
    "M1907_GATE",
    "M1907_M1906_INPUT_MEDIA_TYPE",
    "M1907_MAX_CANONICAL_REQUEST_BYTES",
    "M1907_MAX_CANONICAL_RESULT_BYTES",
    "M1907_MAX_EVIDENCE",
    "M1907_MAX_FIELDS",
    "M1907_MAX_FINDINGS",
    "M1907_MODULE_ID",
    "M1907_OPERATION",
    "M1907_OUTPUT_MEDIA_TYPE",
    "M1907_OWNER",
    "M1907_PARENT",
    "M1907_PROHIBITED_CLAIM_TERMS",
    "M1907_PROVISIONAL_ABI",
    "M1907_SAFETY_CLASS",
    "CompatibilityMode",
    "DownstreamContractObject",
    "DownstreamExportConfiguration",
    "ExportField",
    "ExportFieldType",
    "ExportFinding",
    "ExportFindingCode",
    "ExportOwnershipBinding",
    "ExportProteotypeDownstreamContractRequest",
    "ExportStatus",
    "ProteotypeDownstreamExportResult",
    "SignedContractEnvelope",
]
