"""Provisional M21-01 reference truth and benchmark curator contracts.

M21-01 owns versioned reference data, controls, adjudication, endpoint
definitions, provenance, inclusion, challenge sets and lock procedures for
complex-activity benchmarks. The ABI is provisional pending Quality
engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m21_01.canonical import (
    canonical_request_digest,
    package_lock_digest,
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

# PROVISIONAL ABI: inferred solely from the M21-01 dossier slice.
M2101_MODULE_ID: Final = "GLIO-PROTEOGEN-M21-01"
M2101_OPERATION: Final = "curate_complex_activity_reference_truth"
M2101_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2101_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-01+json"
M2101_PARENT: Final = "complex activity"
M2101_OWNER: Final = "Quality engineering"
M2101_SAFETY_CLASS: Final = "S3"
M2101_GATE: Final = "G0"
M2101_PROVISIONAL_ABI: Final = True
M2101_MAX_REFERENCES: Final = 256
M2101_MAX_CONTROLS: Final = 128
M2101_MAX_ADJUDICATIONS: Final = 256
M2101_MAX_CHALLENGE_SET: Final = 128
M2101_MAX_EVIDENCE: Final = 64
M2101_MAX_FINDINGS: Final = 64
M2101_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2101_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2101_EVIDENCE_CLAIM: Final = (
    "Caller-declared M21-01 reference, endpoint, inclusion, adjudication, "
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
    target: Literal["complex activity"] = M2101_PARENT
    definition: NonEmptyStr
    metric: NonEmptyStr
    acceptance_tolerance: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2101_MAX_EVIDENCE)


class ReferenceEntry(FrozenModel):
    """One immutable reference/control item with inclusion and provenance."""

    reference_id: Identifier
    kind: ReferenceKind
    artifact: ArtifactReference
    expected_label: NonEmptyStr
    inclusion_reason: NonEmptyStr
    provenance_artifact: ArtifactReference
    challenge_set: bool = False
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2101_MAX_EVIDENCE)


class InclusionDecision(FrozenModel):
    reference_id: Identifier
    included: bool
    rationale: NonEmptyStr
    leakage_audit: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2101_MAX_EVIDENCE)


class AdjudicationRecord(FrozenModel):
    reference_id: Identifier
    status: AdjudicationStatus
    reviewer_tokens: tuple[Identifier, ...] = Field(min_length=2, max_length=8)
    agreement_statement: NonEmptyStr
    disagreement_statement: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2101_MAX_EVIDENCE)

    @model_validator(mode="after")
    def disagreement_is_visible(self) -> AdjudicationRecord:
        if len(self.reviewer_tokens) != len(set(self.reviewer_tokens)):
            raise ValueError("adjudication reviewer tokens must be unique")
        if self.status is AdjudicationStatus.REJECTED:
            if self.disagreement_statement is None:
                raise ValueError("rejected adjudication requires a disagreement statement")
        elif self.disagreement_statement is not None:
            raise ValueError("only rejected adjudication may carry disagreement")
        return self


class BenchmarkConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    parent_target: Literal["complex activity"] = M2101_PARENT
    require_controls: Literal[True] = True
    require_adjudication: Literal[True] = True
    require_leakage_audit: Literal[True] = True
    require_locked_package: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2101_MAX_EVIDENCE)


class ReferenceTruthPackage(FrozenModel):
    """Versioned, locked benchmark/truth package with explicit challenge set."""

    package_id: Identifier
    version: SemanticVersion
    endpoint: EndpointDefinition
    references: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2101_MAX_REFERENCES)
    controls: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2101_MAX_CONTROLS)
    inclusions: tuple[InclusionDecision, ...] = Field(min_length=1, max_length=M2101_MAX_REFERENCES)
    adjudications: tuple[AdjudicationRecord, ...] = Field(
        min_length=1, max_length=M2101_MAX_ADJUDICATIONS
    )
    challenge_set_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M2101_MAX_CHALLENGE_SET
    )
    configuration: BenchmarkConfiguration
    lock_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2101_MAX_EVIDENCE)

    @model_validator(mode="after")
    def package_is_closed(self) -> ReferenceTruthPackage:  # noqa: PLR0912 - closure matrix
        references = tuple(item.reference_id for item in self.references)
        controls = tuple(item.reference_id for item in self.controls)
        all_ids = (*references, *controls)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("reference and control ids must be globally unique")
        if any(
            item.kind
            not in {
                ReferenceKind.CALIBRATOR,
                ReferenceKind.SPIKE_IN,
                ReferenceKind.CHALLENGE_SET,
            }
            for item in self.references
        ):
            raise ValueError("references may only be calibrators, spike-ins, or challenge sets")
        if any(
            (item.kind is ReferenceKind.CHALLENGE_SET) is not item.challenge_set
            for item in self.references
        ):
            raise ValueError("challenge-set kind and challenge-set flag must agree")
        if any(
            item.kind not in {ReferenceKind.POSITIVE_CONTROL, ReferenceKind.NEGATIVE_CONTROL}
            or item.challenge_set
            for item in self.controls
        ):
            raise ValueError("controls must be positive/negative controls and not challenge items")
        all_id_set = set(all_ids)
        inclusion_ids = tuple(item.reference_id for item in self.inclusions)
        adjudication_ids = tuple(item.reference_id for item in self.adjudications)
        if len(inclusion_ids) != len(set(inclusion_ids)) or set(inclusion_ids) != all_id_set:
            raise ValueError("inclusion decisions must classify every reference and control")
        if (
            len(adjudication_ids) != len(set(adjudication_ids))
            or set(adjudication_ids) != all_id_set
        ):
            raise ValueError("adjudications must cover every reference and control")
        challenge_ids = {item.reference_id for item in self.references if item.challenge_set}
        if len(self.challenge_set_ids) != len(set(self.challenge_set_ids)):
            raise ValueError("challenge set ids must be unique")
        if set(self.challenge_set_ids) != challenge_ids:
            raise ValueError("challenge set ids must exactly match challenge references")
        if self.configuration.version != self.version:
            raise ValueError("package and locked configuration versions must match")
        if self.configuration.parent_target != self.endpoint.target:
            raise ValueError("locked configuration must target the package endpoint")
        adjudications = {item.reference_id: item for item in self.adjudications}
        inclusions = {item.reference_id: item for item in self.inclusions}
        if any(
            adjudications[item_id].status
            in {AdjudicationStatus.PENDING, AdjudicationStatus.REVIEWED}
            for item_id in all_id_set
        ):
            raise ValueError(
                "locked package cannot contain pending or merely reviewed adjudications"
            )
        if any(
            adjudications[item_id].status is AdjudicationStatus.REJECTED
            and inclusions[item_id].included
            for item_id in all_id_set
        ):
            raise ValueError("rejected adjudications must be excluded from a locked package")
        if self.lock_digest != package_lock_digest(self):
            raise ValueError("package lock digest does not match canonical package contents")
        return self


class CurationFinding(FrozenModel):
    finding_id: Identifier
    code: CurationFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2101_MAX_EVIDENCE)


class CurateComplexActivityReferenceTruthRequest(FrozenModel):
    """Provisional request for reference truth and benchmark curation."""

    operation: Literal["curate_complex_activity_reference_truth"] = M2101_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2101_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    endpoint: EndpointDefinition
    references: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2101_MAX_REFERENCES)
    controls: tuple[ReferenceEntry, ...] = Field(min_length=1, max_length=M2101_MAX_CONTROLS)
    inclusions: tuple[InclusionDecision, ...] = Field(min_length=1, max_length=M2101_MAX_REFERENCES)
    adjudications: tuple[AdjudicationRecord, ...] = Field(
        min_length=1, max_length=M2101_MAX_ADJUDICATIONS
    )
    configuration: BenchmarkConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2101_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> CurateComplexActivityReferenceTruthRequest:
        ids = tuple(item.reference_id for item in (*self.references, *self.controls))
        if len(ids) != len(set(ids)):
            raise ValueError("request reference and control ids must be unique")
        if any(
            item.kind
            not in {
                ReferenceKind.CALIBRATOR,
                ReferenceKind.SPIKE_IN,
                ReferenceKind.CHALLENGE_SET,
            }
            for item in self.references
        ):
            raise ValueError("request references may not be control items")
        if any(
            (item.kind is ReferenceKind.CHALLENGE_SET) is not item.challenge_set
            for item in self.references
        ):
            raise ValueError("challenge-set kind and challenge-set flag must agree")
        if any(
            item.kind not in {ReferenceKind.POSITIVE_CONTROL, ReferenceKind.NEGATIVE_CONTROL}
            or item.challenge_set
            for item in self.controls
        ):
            raise ValueError("request controls must be positive/negative controls")
        known = set(ids)
        inclusion_ids = tuple(item.reference_id for item in self.inclusions)
        adjudication_ids = tuple(item.reference_id for item in self.adjudications)
        if len(inclusion_ids) != len(set(inclusion_ids)) or set(inclusion_ids) != known:
            raise ValueError("request inclusions must classify every item")
        if len(adjudication_ids) != len(set(adjudication_ids)) or set(adjudication_ids) != known:
            raise ValueError("request adjudications must cover every item")
        challenge_ids = {item.reference_id for item in self.references if item.challenge_set}
        if not challenge_ids:
            raise ValueError("request must include at least one challenge-set item")
        return self


class ComplexActivityReferenceTruthResult(FrozenModel):
    """Versioned benchmark/truth result with explicit safe abstention."""

    output_type: Literal["complex_activity_reference_truth"] = "complex_activity_reference_truth"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2101_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: CurateComplexActivityReferenceTruthRequest
    status: CurationStatus
    package: ReferenceTruthPackage | None = None
    findings: tuple[CurationFinding, ...] = Field(default=(), max_length=M2101_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2101_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2101_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityReferenceTruthResult:  # noqa: PLR0912 - closure matrix
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id must be deterministically bound to the request")
        if self.status is CurationStatus.CURATED:
            if (
                self.package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("curated result requires a supported truth package")
            if self.package.endpoint != self.request.endpoint:
                raise ValueError("curated package endpoint must equal the request endpoint")
            if self.package.references != self.request.references:
                raise ValueError("curated package references must equal the request references")
            if self.package.controls != self.request.controls:
                raise ValueError("curated package controls must equal the request controls")
            if self.package.inclusions != self.request.inclusions:
                raise ValueError("curated package inclusions must equal the request decisions")
            if self.package.adjudications != self.request.adjudications:
                raise ValueError("curated package adjudications must equal the request records")
            if self.package.configuration != self.request.configuration:
                raise ValueError(
                    "curated package configuration must equal the request configuration"
                )
        elif (
            self.package is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no package and safe status")
        if len(self.findings) != len({finding.finding_id for finding in self.findings}):
            raise ValueError("result finding ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2101_CONTRACT_VERSION",
    "M2101_EVIDENCE_CLAIM",
    "M2101_GATE",
    "M2101_MAX_ADJUDICATIONS",
    "M2101_MAX_CANONICAL_REQUEST_BYTES",
    "M2101_MAX_CANONICAL_RESULT_BYTES",
    "M2101_MAX_CHALLENGE_SET",
    "M2101_MAX_CONTROLS",
    "M2101_MAX_EVIDENCE",
    "M2101_MAX_FINDINGS",
    "M2101_MAX_REFERENCES",
    "M2101_MODULE_ID",
    "M2101_OPERATION",
    "M2101_OUTPUT_MEDIA_TYPE",
    "M2101_OWNER",
    "M2101_PARENT",
    "M2101_PROVISIONAL_ABI",
    "M2101_SAFETY_CLASS",
    "AdjudicationRecord",
    "AdjudicationStatus",
    "BenchmarkConfiguration",
    "ComplexActivityReferenceTruthResult",
    "CurateComplexActivityReferenceTruthRequest",
    "CurationFinding",
    "CurationFindingCode",
    "CurationStatus",
    "EndpointDefinition",
    "InclusionDecision",
    "ReferenceEntry",
    "ReferenceKind",
    "ReferenceTruthPackage",
]
