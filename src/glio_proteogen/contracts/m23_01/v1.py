"""Provisional M23-01 reference truth and benchmark curator contracts.

M23-01 owns versioned reference data, controls, adjudication, endpoint
definitions, provenance, inclusion, challenge sets, and lock procedures
beneath Cross-instrument transport. The ABI is provisional pending Data
engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m23_01.canonical import (
    canonical_request_digest,
    package_payload_digest,
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
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

# PROVISIONAL ABI: inferred solely from the permitted dossier slice.
M2301_MODULE_ID: Final = "GLIO-PROTEOGEN-M23-01"
M2301_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2301_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7956-7996"
M2301_OPERATION: Final = "curate_variant_peptide_reference_truth"
M2301_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2301_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m23-01+json"
M2301_PARENT: Final = "variant peptide"
M2301_OWNER: Final = "Data engineering"
M2301_SAFETY_CLASS: Final = "S3"
M2301_GATE: Final = "G0"
M2301_PROVISIONAL_ABI: Final = True
M2301_MAX_REFERENCES: Final = 256
M2301_MAX_CONTROLS: Final = 128
M2301_MAX_ADJUDICATIONS: Final = 256
M2301_MAX_CHALLENGE_SET: Final = 128
M2301_MAX_EVIDENCE: Final = 64
M2301_MAX_FINDINGS: Final = 64
M2301_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2301_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2301_EVIDENCE_CLAIM: Final = (
    "Caller-declared M23-01 reference, endpoint, inclusion, adjudication, "
    "challenge-set and lock material; issuer authority is not authenticated."
)


class ReferenceKind(StrEnum):
    CALIBRATOR = "calibrator"
    SPIKE_IN = "spike_in"
    POSITIVE_CONTROL = "positive_control"
    NEGATIVE_CONTROL = "negative_control"
    CHALLENGE_SET = "challenge_set"


class AdjudicationStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    LOCKED = "locked"
    REJECTED = "rejected"


class CurationStatus(StrEnum):
    CURATED = "curated"
    ABSTAINED = "abstained"


class CurationFindingCode(StrEnum):
    ENDPOINT_UNDEFINED = "endpoint_undefined"
    PROVENANCE_MISSING = "provenance_missing"
    CONTROL_MISSING = "control_missing"
    ADJUDICATION_PENDING = "adjudication_pending"
    LEAKAGE_AUDIT_MISSING = "leakage_audit_missing"
    LOCK_INCOMPLETE = "lock_incomplete"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class EndpointDefinition(FrozenModel):
    endpoint_id: Identifier
    name: NonEmptyStr
    target: Literal["variant peptide"] = M2301_PARENT
    definition: NonEmptyStr
    metric: NonEmptyStr
    acceptance_tolerance: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2301_MAX_EVIDENCE)


class ReferenceEntry(FrozenModel):
    reference_id: Identifier
    kind: ReferenceKind
    artifact: ArtifactReference
    expected_label: NonEmptyStr
    inclusion_reason: NonEmptyStr
    provenance_artifact: ArtifactReference
    challenge_set: bool = False
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2301_MAX_EVIDENCE)

    @model_validator(mode="after")
    def challenge_kind_matches_flag(self) -> ReferenceEntry:
        if (self.kind is ReferenceKind.CHALLENGE_SET) != self.challenge_set:
            raise ValueError("challenge-set kind and flag must agree")
        return self


class InclusionDecision(FrozenModel):
    reference_id: Identifier
    included: bool
    rationale: NonEmptyStr
    leakage_audit: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2301_MAX_EVIDENCE)


class AdjudicationRecord(FrozenModel):
    reference_id: Identifier
    status: AdjudicationStatus
    reviewer_tokens: tuple[Identifier, ...] = Field(min_length=2, max_length=8)
    agreement_statement: NonEmptyStr
    disagreement_statement: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2301_MAX_EVIDENCE)

    @model_validator(mode="after")
    def disagreement_is_visible(self) -> AdjudicationRecord:
        if len(self.reviewer_tokens) != len(set(self.reviewer_tokens)):
            raise ValueError("adjudication reviewer tokens must be unique")
        if self.status is AdjudicationStatus.REJECTED and self.disagreement_statement is None:
            raise ValueError("rejected adjudication requires a disagreement statement")
        return self


class BenchmarkConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["variant peptide"] = M2301_PARENT
    require_controls: Literal[True] = True
    require_adjudication: Literal[True] = True
    require_leakage_audit: Literal[True] = True
    require_locked_package: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2301_MAX_EVIDENCE)


class ReferenceTruthPackage(FrozenModel):
    package_id: Identifier
    version: SemanticVersion
    endpoint: EndpointDefinition
    references: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2301_MAX_REFERENCES)
    controls: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2301_MAX_CONTROLS)
    inclusions: tuple[InclusionDecision, ...] = Field(min_length=1, max_length=M2301_MAX_REFERENCES)
    adjudications: tuple[AdjudicationRecord, ...] = Field(
        min_length=1, max_length=M2301_MAX_ADJUDICATIONS
    )
    challenge_set_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M2301_MAX_CHALLENGE_SET
    )
    configuration: BenchmarkConfiguration
    lock_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2301_MAX_EVIDENCE)

    @model_validator(mode="after")
    def package_is_closed(self) -> ReferenceTruthPackage:
        references = tuple(item.reference_id for item in self.references)
        controls = tuple(item.reference_id for item in self.controls)
        if len(references) != len(set(references)) or len(controls) != len(set(controls)):
            raise ValueError("reference and control ids must be unique")
        if self.configuration.parent_target != M2301_PARENT or not self.configuration.locked:
            raise ValueError("package configuration must be locked to the parent target")
        all_ids = set(references) | set(controls)
        inclusion_ids = tuple(item.reference_id for item in self.inclusions)
        adjudication_ids = tuple(item.reference_id for item in self.adjudications)
        if len(inclusion_ids) != len(set(inclusion_ids)) or set(inclusion_ids) != all_ids:
            raise ValueError("inclusion decisions must classify every reference and control")
        if len(adjudication_ids) != len(set(adjudication_ids)) or set(adjudication_ids) != all_ids:
            raise ValueError("adjudications must cover every reference and control")
        if not set(self.challenge_set_ids) <= set(references):
            raise ValueError("challenge set must reference known entries")
        challenge_ids = {item.reference_id for item in self.references if item.challenge_set}
        if set(self.challenge_set_ids) != challenge_ids:
            raise ValueError("challenge set IDs must match flagged reference entries")
        if any(item.status is not AdjudicationStatus.LOCKED for item in self.adjudications):
            raise ValueError("locked package requires locked adjudications")
        if self.lock_digest != package_payload_digest(self):
            raise ValueError("package lock digest must bind the canonical package payload")
        return self


class CurationFinding(FrozenModel):
    finding_id: Identifier
    code: CurationFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2301_MAX_EVIDENCE)


class CurateVariantPeptideReferenceTruthRequest(FrozenModel):
    operation: Literal["curate_variant_peptide_reference_truth"] = M2301_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2301_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    endpoint: EndpointDefinition
    references: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2301_MAX_REFERENCES)
    controls: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2301_MAX_CONTROLS)
    inclusions: tuple[InclusionDecision, ...] = Field(min_length=1, max_length=M2301_MAX_REFERENCES)
    adjudications: tuple[AdjudicationRecord, ...] = Field(
        min_length=1, max_length=M2301_MAX_ADJUDICATIONS
    )
    configuration: BenchmarkConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2301_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> CurateVariantPeptideReferenceTruthRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request ID must match the request")
        ids = tuple(item.reference_id for item in (*self.references, *self.controls))
        if len(ids) != len(set(ids)):
            raise ValueError("request reference and control ids must be unique")
        known = set(ids)
        inclusion_ids = tuple(item.reference_id for item in self.inclusions)
        adjudication_ids = tuple(item.reference_id for item in self.adjudications)
        if len(inclusion_ids) != len(set(inclusion_ids)) or set(inclusion_ids) != known:
            raise ValueError("request inclusions must classify every item")
        if len(adjudication_ids) != len(set(adjudication_ids)) or set(adjudication_ids) != known:
            raise ValueError("request adjudications must cover every item")
        source_by_id = {item.artifact_id: item for item in self.source_artifacts}
        if len(source_by_id) != len(self.source_artifacts):
            raise ValueError("source artifacts must have unique artifact IDs")
        declared: list[ArtifactReference] = []
        for entry in (*self.references, *self.controls):
            declared.extend((entry.artifact, entry.provenance_artifact))
            declared.extend(item.reference for item in entry.evidence)
        declared.extend(item.reference for item in self.endpoint.evidence)
        declared.extend(
            evidence_item.reference
            for inclusion in self.inclusions
            for evidence_item in inclusion.evidence
        )
        declared.extend(
            evidence_item.reference
            for adjudication in self.adjudications
            for evidence_item in adjudication.evidence
        )
        declared.extend(item.reference for item in self.configuration.evidence)
        if any(source_by_id.get(item.artifact_id) != item for item in declared):
            raise ValueError("source artifacts must bind every declared artifact exactly")
        return self


class VariantPeptideReferenceTruthResult(FrozenModel):
    output_type: Literal["variant_peptide_reference_truth"] = "variant_peptide_reference_truth"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2301_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: CurateVariantPeptideReferenceTruthRequest
    status: CurationStatus
    package: ReferenceTruthPackage | None = None
    findings: tuple[CurationFinding, ...] = Field(default=(), max_length=M2301_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant peptide"] = M2301_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2301_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideReferenceTruthResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request_digest):
            raise ValueError("result identifier must bind the request digest")
        if self.status is CurationStatus.CURATED:
            if (
                self.package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("curated result requires a supported truth package")
            if self.package is not None and (
                self.package.endpoint != self.request.endpoint
                or self.package.references != self.request.references
                or self.package.controls != self.request.controls
                or self.package.inclusions != self.request.inclusions
                or self.package.adjudications != self.request.adjudications
                or self.package.configuration != self.request.configuration
            ):
                raise ValueError("curated package must bind the exact request declarations")
        elif (
            self.package is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no package and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2301_CONTRACT_VERSION",
    "M2301_DOSSIER_SHA256",
    "M2301_DOSSIER_SLICE",
    "M2301_EVIDENCE_CLAIM",
    "M2301_GATE",
    "M2301_MAX_ADJUDICATIONS",
    "M2301_MAX_CANONICAL_REQUEST_BYTES",
    "M2301_MAX_CANONICAL_RESULT_BYTES",
    "M2301_MAX_CHALLENGE_SET",
    "M2301_MAX_CONTROLS",
    "M2301_MAX_EVIDENCE",
    "M2301_MAX_FINDINGS",
    "M2301_MAX_REFERENCES",
    "M2301_MODULE_ID",
    "M2301_OPERATION",
    "M2301_OUTPUT_MEDIA_TYPE",
    "M2301_OWNER",
    "M2301_PARENT",
    "M2301_PROVISIONAL_ABI",
    "M2301_SAFETY_CLASS",
    "AdjudicationRecord",
    "AdjudicationStatus",
    "BenchmarkConfiguration",
    "CurateVariantPeptideReferenceTruthRequest",
    "CurationFinding",
    "CurationFindingCode",
    "CurationStatus",
    "EndpointDefinition",
    "InclusionDecision",
    "ReferenceEntry",
    "ReferenceKind",
    "ReferenceTruthPackage",
    "VariantPeptideReferenceTruthResult",
]
