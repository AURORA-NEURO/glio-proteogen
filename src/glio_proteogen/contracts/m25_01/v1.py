"""Provisional M25-01 reference truth and benchmark curator contracts.

M25-01 owns versioned reference data, controls, adjudication, endpoint
definitions, provenance, inclusion, challenge sets, and lock procedures
beneath Cross-instrument transport. The ABI is provisional pending Data
engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m25_01.canonical import (
    canonical_request_digest,
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

# PROVISIONAL ABI: inferred solely from dossier lines 8676-8716.
M2501_MODULE_ID: Final = "GLIO-PROTEOGEN-M25-01"
M2501_OPERATION: Final = "curate_proteotype_reference_truth"
M2501_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2501_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-01+json"
M2501_PARENT: Final = "proteotype"
M2501_OWNER: Final = "Scientific engineering"
M2501_SAFETY_CLASS: Final = "S3"
M2501_GATE: Final = "G0"
M2501_PROVISIONAL_ABI: Final = True
M2501_MAX_REFERENCES: Final = 256
M2501_MAX_CONTROLS: Final = 128
M2501_MAX_ADJUDICATIONS: Final = 256
M2501_MAX_CHALLENGE_SET: Final = 128
M2501_MAX_EVIDENCE: Final = 64
M2501_MAX_FINDINGS: Final = 64
M2501_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2501_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2501_EVIDENCE_CLAIM: Final = (
    "Caller-declared M25-01 reference, endpoint, inclusion, adjudication, "
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
    target: Literal["proteotype"] = M2501_PARENT
    definition: NonEmptyStr
    metric: NonEmptyStr
    acceptance_tolerance: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2501_MAX_EVIDENCE)


class ReferenceEntry(FrozenModel):
    reference_id: Identifier
    kind: ReferenceKind
    artifact: ArtifactReference
    expected_label: NonEmptyStr
    inclusion_reason: NonEmptyStr
    provenance_artifact: ArtifactReference
    challenge_set: bool = False
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2501_MAX_EVIDENCE)


class InclusionDecision(FrozenModel):
    reference_id: Identifier
    included: bool
    rationale: NonEmptyStr
    leakage_audit: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2501_MAX_EVIDENCE)


class AdjudicationRecord(FrozenModel):
    reference_id: Identifier
    status: AdjudicationStatus
    reviewer_tokens: tuple[Identifier, ...] = Field(min_length=2, max_length=8)
    agreement_statement: NonEmptyStr
    disagreement_statement: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2501_MAX_EVIDENCE)

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
    parent_target: Literal["proteotype"] = M2501_PARENT
    require_controls: Literal[True] = True
    require_adjudication: Literal[True] = True
    require_leakage_audit: Literal[True] = True
    require_locked_package: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2501_MAX_EVIDENCE)


class ReferenceTruthPackage(FrozenModel):
    package_id: Identifier
    version: SemanticVersion
    endpoint: EndpointDefinition
    references: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2501_MAX_REFERENCES)
    controls: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2501_MAX_CONTROLS)
    inclusions: tuple[InclusionDecision, ...] = Field(min_length=1, max_length=M2501_MAX_REFERENCES)
    adjudications: tuple[AdjudicationRecord, ...] = Field(
        min_length=1, max_length=M2501_MAX_ADJUDICATIONS
    )
    challenge_set_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M2501_MAX_CHALLENGE_SET
    )
    configuration: BenchmarkConfiguration
    lock_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2501_MAX_EVIDENCE)

    @model_validator(mode="after")
    def package_is_closed(self) -> ReferenceTruthPackage:
        references = tuple(item.reference_id for item in self.references)
        controls = tuple(item.reference_id for item in self.controls)
        if len(references) != len(set(references)) or len(controls) != len(set(controls)):
            raise ValueError("reference and control ids must be unique")
        all_ids = set(references) | set(controls)
        if {item.reference_id for item in self.inclusions} != all_ids:
            raise ValueError("inclusion decisions must classify every reference and control")
        if {item.reference_id for item in self.adjudications} != all_ids:
            raise ValueError("adjudications must cover every reference and control")
        if not set(self.challenge_set_ids) <= set(references):
            raise ValueError("challenge set must reference known entries")
        if len(self.challenge_set_ids) != len(set(self.challenge_set_ids)):
            raise ValueError("challenge set identifiers must be unique")
        challenge_entries = {item.reference_id for item in self.references if item.challenge_set}
        if set(self.challenge_set_ids) != challenge_entries:
            raise ValueError("challenge set identifiers must match marked references")
        return self


class CurationFinding(FrozenModel):
    finding_id: Identifier
    code: CurationFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2501_MAX_EVIDENCE)


class CurateProteotypeReferenceTruthRequest(FrozenModel):
    operation: Literal["curate_proteotype_reference_truth"] = M2501_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2501_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    endpoint: EndpointDefinition
    references: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2501_MAX_REFERENCES)
    controls: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2501_MAX_CONTROLS)
    inclusions: tuple[InclusionDecision, ...] = Field(min_length=1, max_length=M2501_MAX_REFERENCES)
    adjudications: tuple[AdjudicationRecord, ...] = Field(
        min_length=1, max_length=M2501_MAX_ADJUDICATIONS
    )
    configuration: BenchmarkConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2501_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> CurateProteotypeReferenceTruthRequest:
        ids = tuple(item.reference_id for item in (*self.references, *self.controls))
        if len(ids) != len(set(ids)):
            raise ValueError("request reference and control ids must be unique")
        known = set(ids)
        if {item.reference_id for item in self.inclusions} != known:
            raise ValueError("request inclusions must classify every item")
        if {item.reference_id for item in self.adjudications} != known:
            raise ValueError("request adjudications must cover every item")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifact identifiers must be unique")
        if self.configuration.parent_target != M2501_PARENT:
            raise ValueError("configuration parent target must be proteotype")
        if self.endpoint.target != M2501_PARENT:
            raise ValueError("endpoint target must be proteotype")
        return self


class ProteotypeReferenceTruthResult(FrozenModel):
    output_type: Literal["proteotype_reference_truth"] = "proteotype_reference_truth"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2501_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: CurateProteotypeReferenceTruthRequest
    status: CurationStatus
    package: ReferenceTruthPackage | None = None
    findings: tuple[CurationFinding, ...] = Field(default=(), max_length=M2501_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M2501_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2501_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeReferenceTruthResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.status is CurationStatus.CURATED:
            if (
                self.package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("curated result requires a supported truth package")
        elif (
            self.package is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no package and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        if self.result_id != result_identifier(self.request, self.status.value):
            raise ValueError("result identifier does not bind request, status, and payload")
        return self


__all__ = [
    "M2501_CONTRACT_VERSION",
    "M2501_EVIDENCE_CLAIM",
    "M2501_GATE",
    "M2501_MAX_ADJUDICATIONS",
    "M2501_MAX_CANONICAL_REQUEST_BYTES",
    "M2501_MAX_CANONICAL_RESULT_BYTES",
    "M2501_MAX_CHALLENGE_SET",
    "M2501_MAX_CONTROLS",
    "M2501_MAX_EVIDENCE",
    "M2501_MAX_FINDINGS",
    "M2501_MAX_REFERENCES",
    "M2501_MODULE_ID",
    "M2501_OPERATION",
    "M2501_OUTPUT_MEDIA_TYPE",
    "M2501_OWNER",
    "M2501_PARENT",
    "M2501_PROVISIONAL_ABI",
    "M2501_SAFETY_CLASS",
    "AdjudicationRecord",
    "AdjudicationStatus",
    "BenchmarkConfiguration",
    "CurateProteotypeReferenceTruthRequest",
    "CurationFinding",
    "CurationFindingCode",
    "CurationStatus",
    "EndpointDefinition",
    "InclusionDecision",
    "ProteotypeReferenceTruthResult",
    "ReferenceEntry",
    "ReferenceKind",
    "ReferenceTruthPackage",
]
