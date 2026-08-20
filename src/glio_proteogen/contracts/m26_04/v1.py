"""Provisional M26-04 API, SDK and CLI gateway contracts.

M26-04 owns the typed access surface beneath the Proteomics standards registry:
authorization, idempotency, asynchronous jobs, errors, audit and compatibility.
The ABI is provisional pending Quality engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m26_04.canonical import (
    canonical_request_digest,
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

# PROVISIONAL ABI: inferred solely from dossier lines 9168-9208.
M2604_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2604_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:9168-9208"
M2604_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-04"
M2604_OPERATION: Final = "publish_protein_subtype_access_surface"
M2604_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2604_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-04+json"
M2604_PARENT: Final = "protein subtype"
M2604_OWNER: Final = "Quality engineering"
M2604_SAFETY_CLASS: Final = "S3"
M2604_GATE: Final = "G2"
M2604_PROVISIONAL_ABI: Final = True
M2604_MAX_OPERATIONS: Final = 128
M2604_MAX_COMPATIBILITY_RULES: Final = 256
M2604_MAX_AUTHORIZATIONS: Final = 256
M2604_MAX_JOBS: Final = 256
M2604_MAX_ERRORS: Final = 128
M2604_MAX_AUDIT_EVENTS: Final = 512
M2604_MAX_FINDINGS: Final = 64
M2604_MAX_EVIDENCE: Final = 64
M2604_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2604_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2604_EVIDENCE_CLAIM: Final = (
    "Caller-declared M26-04 operation, authorization, job, error, audit and "
    "compatibility material; issuer authority is not authenticated."
)


class AccessProtocol(StrEnum):
    API = "api"
    SDK = "sdk"
    CLI = "cli"


class OperationStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class AuthorizationDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW_REQUIRED = "review_required"


class CompatibilityStatus(StrEnum):
    COMPATIBLE = "compatible"
    MIGRATION_REQUIRED = "migration_required"
    INCOMPATIBLE = "incompatible"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABSTAINED = "abstained"
    CANCELLED = "cancelled"


class GatewayStatus(StrEnum):
    PUBLISHED = "published"
    ABSTAINED = "abstained"


class GatewayFindingCode(StrEnum):
    OPERATION_UNAUTHORIZED = "operation_unauthorized"
    IDEMPOTENCY_MISSING = "idempotency_missing"
    ASYNC_JOB_UNBOUND = "async_job_unbound"
    COMPATIBILITY_UNRESOLVED = "compatibility_unresolved"
    AUDIT_MISSING = "audit_missing"
    ERROR_TAXONOMY_INCOMPLETE = "error_taxonomy_incomplete"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class GatewayOperation(FrozenModel):
    """One typed operation exposed through API, SDK and/or CLI."""

    operation_id: Identifier
    name: NonEmptyStr
    version: SemanticVersion
    protocol: AccessProtocol
    request_media_type: NonEmptyStr
    response_media_type: NonEmptyStr
    authorization_scope: NonEmptyStr
    status: OperationStatus
    idempotency_required: Literal[True] = True
    asynchronous_supported: bool
    audit_required: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)


class AuthorizationRecord(FrozenModel):
    authorization_id: Identifier
    operation_id: Identifier
    principal_id: Identifier
    scope: NonEmptyStr
    decision: AuthorizationDecision
    policy_version: SemanticVersion
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)


class IdempotencyRecord(FrozenModel):
    idempotency_id: Identifier
    operation_id: Identifier
    key_digest: Sha256Digest
    request_digest: Sha256Digest
    replay_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)


class AsyncJobRecord(FrozenModel):
    job_id: Identifier
    operation_id: Identifier
    status: JobStatus
    idempotency: IdempotencyRecord
    result_artifact: ArtifactReference | None = None
    error_code: Identifier | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def terminal_job_has_outcome(self) -> AsyncJobRecord:
        if self.idempotency.operation_id != self.operation_id:
            raise ValueError("async job idempotency must bind its operation")
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.ABSTAINED, JobStatus.CANCELLED}
        if self.status is JobStatus.SUCCEEDED and self.result_artifact is None:
            raise ValueError("succeeded async job requires a result artifact")
        if self.status in terminal - {JobStatus.SUCCEEDED} and self.result_artifact is not None:
            raise ValueError("non-success async job cannot carry a result artifact")
        if self.status is JobStatus.FAILED and self.error_code is None:
            raise ValueError("failed async job requires a typed error code")
        return self


class CompatibilityRule(FrozenModel):
    rule_id: Identifier
    operation_id: Identifier
    from_version: SemanticVersion
    to_version: SemanticVersion
    status: CompatibilityStatus
    migration_statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)


class GatewayError(FrozenModel):
    error_id: Identifier
    code: Identifier
    message: NonEmptyStr
    retryable: bool
    safe_to_expose: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2604_MAX_EVIDENCE)


class AuditEvent(FrozenModel):
    event_id: Identifier
    operation_id: Identifier
    principal_id: Identifier
    event_type: NonEmptyStr
    outcome: NonEmptyStr
    request_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)


class GatewayConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    supported_protocols: tuple[AccessProtocol, ...] = Field(min_length=1, max_length=3)
    typed_operations_required: Literal[True] = True
    authorization_required: Literal[True] = True
    idempotency_required: Literal[True] = True
    asynchronous_jobs_required: Literal[True] = True
    error_taxonomy_required: Literal[True] = True
    audit_required: Literal[True] = True
    compatibility_required: Literal[True] = True
    signed_release_bundle_fallback: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def protocols_are_unique(self) -> GatewayConfiguration:
        if len(self.supported_protocols) != len(set(self.supported_protocols)):
            raise ValueError("supported gateway protocols must be unique")
        return self


class AccessSurface(FrozenModel):
    """Documented, versioned and auditable gateway surface."""

    surface_id: Identifier
    version: SemanticVersion
    operations: tuple[GatewayOperation, ...] = Field(min_length=1, max_length=M2604_MAX_OPERATIONS)
    authorizations: tuple[AuthorizationRecord, ...] = Field(
        min_length=1, max_length=M2604_MAX_AUTHORIZATIONS
    )
    idempotency_records: tuple[IdempotencyRecord, ...] = Field(
        min_length=1, max_length=M2604_MAX_JOBS
    )
    jobs: tuple[AsyncJobRecord, ...] = Field(min_length=1, max_length=M2604_MAX_JOBS)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(
        min_length=1, max_length=M2604_MAX_COMPATIBILITY_RULES
    )
    errors: tuple[GatewayError, ...] = Field(min_length=1, max_length=M2604_MAX_ERRORS)
    audit_events: tuple[AuditEvent, ...] = Field(min_length=1, max_length=M2604_MAX_AUDIT_EVENTS)
    configuration: GatewayConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2604_MAX_EVIDENCE)

    @model_validator(mode="after")
    def surface_is_closed(self) -> AccessSurface:
        operation_ids = {operation.operation_id for operation in self.operations}
        if len(operation_ids) != len(self.operations):
            raise ValueError("gateway operation ids must be unique")
        if any(auth.operation_id not in operation_ids for auth in self.authorizations):
            raise ValueError("authorization references unknown operation")
        authorized_operation_ids = {auth.operation_id for auth in self.authorizations}
        if authorized_operation_ids != operation_ids:
            raise ValueError("every gateway operation requires authorization")
        if any(job.operation_id not in operation_ids for job in self.jobs):
            raise ValueError("async job references unknown operation")
        if any(record.operation_id not in operation_ids for record in self.idempotency_records):
            raise ValueError("idempotency record references unknown operation")
        if any(rule.operation_id not in operation_ids for rule in self.compatibility_rules):
            raise ValueError("compatibility rule references unknown operation")
        if any(event.operation_id not in operation_ids for event in self.audit_events):
            raise ValueError("audit event references unknown operation")
        if any(job.idempotency not in self.idempotency_records for job in self.jobs):
            raise ValueError("every async job idempotency record must be declared")
        if {record.operation_id for record in self.idempotency_records} != operation_ids:
            raise ValueError("every gateway operation requires idempotency coverage")
        if any(
            operation.protocol not in self.configuration.supported_protocols
            for operation in self.operations
        ):
            raise ValueError("operation protocol is not enabled by gateway configuration")
        return self


class GatewayFinding(FrozenModel):
    finding_id: Identifier
    code: GatewayFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2604_MAX_EVIDENCE)


class PublishProteinSubtypeAccessSurfaceRequest(FrozenModel):
    """Provisional request for publishing a documented gateway surface."""

    operation: Literal["publish_protein_subtype_access_surface"] = M2604_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2604_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    operations: tuple[GatewayOperation, ...] = Field(min_length=1, max_length=M2604_MAX_OPERATIONS)
    authorizations: tuple[AuthorizationRecord, ...] = Field(
        min_length=1, max_length=M2604_MAX_AUTHORIZATIONS
    )
    idempotency_records: tuple[IdempotencyRecord, ...] = Field(
        min_length=1, max_length=M2604_MAX_JOBS
    )
    jobs: tuple[AsyncJobRecord, ...] = Field(min_length=1, max_length=M2604_MAX_JOBS)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(
        min_length=1, max_length=M2604_MAX_COMPATIBILITY_RULES
    )
    errors: tuple[GatewayError, ...] = Field(min_length=1, max_length=M2604_MAX_ERRORS)
    audit_events: tuple[AuditEvent, ...] = Field(min_length=1, max_length=M2604_MAX_AUDIT_EVENTS)
    configuration: GatewayConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2604_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> PublishProteinSubtypeAccessSurfaceRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request ID must match the request")
        operation_ids = tuple(operation.operation_id for operation in self.operations)
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("gateway operation ids must be unique")
        known = set(operation_ids)
        references = (
            self.authorizations,
            self.idempotency_records,
            self.jobs,
            self.compatibility_rules,
            self.audit_events,
        )
        if any(item.operation_id not in known for group in references for item in group):
            raise ValueError("gateway material references an unknown operation")
        if {item.operation_id for item in self.authorizations} != known:
            raise ValueError("every gateway operation requires authorization")
        if any(job.idempotency not in self.idempotency_records for job in self.jobs):
            raise ValueError("every async job idempotency record must be declared")
        if {record.operation_id for record in self.idempotency_records} != known:
            raise ValueError("every gateway operation requires idempotency coverage")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifacts must have unique artifact IDs")
        required_sources = {
            self.mass_spectrometry_proteome.artifact_id,
            self.genome_transcriptome.artifact_id,
            self.ptm_annotations.artifact_id,
        }
        if not required_sources.issubset(source_ids):
            raise ValueError("source artifacts must bind every declared gateway modality")
        return self


class ProteinSubtypeAccessSurfaceResult(FrozenModel):
    """Published access surface with typed errors and safe abstention."""

    output_type: Literal["protein_subtype_access_surface"] = "protein_subtype_access_surface"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2604_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishProteinSubtypeAccessSurfaceRequest
    status: GatewayStatus
    access_surface: AccessSurface | None = None
    findings: tuple[GatewayFinding, ...] = Field(default=(), max_length=M2604_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2604_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2604_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeAccessSurfaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.status is GatewayStatus.PUBLISHED:
            if (
                self.access_surface is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("published result requires a supported access surface")
        elif (
            self.access_surface is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no access surface and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2604_CONTRACT_VERSION",
    "M2604_DOSSIER_SHA256",
    "M2604_DOSSIER_SLICE",
    "M2604_EVIDENCE_CLAIM",
    "M2604_GATE",
    "M2604_MAX_AUDIT_EVENTS",
    "M2604_MAX_AUTHORIZATIONS",
    "M2604_MAX_CANONICAL_REQUEST_BYTES",
    "M2604_MAX_CANONICAL_RESULT_BYTES",
    "M2604_MAX_COMPATIBILITY_RULES",
    "M2604_MAX_ERRORS",
    "M2604_MAX_EVIDENCE",
    "M2604_MAX_FINDINGS",
    "M2604_MAX_JOBS",
    "M2604_MAX_OPERATIONS",
    "M2604_MODULE_ID",
    "M2604_OPERATION",
    "M2604_OUTPUT_MEDIA_TYPE",
    "M2604_OWNER",
    "M2604_PARENT",
    "M2604_PROVISIONAL_ABI",
    "M2604_SAFETY_CLASS",
    "AccessProtocol",
    "AccessSurface",
    "AsyncJobRecord",
    "AuditEvent",
    "AuthorizationDecision",
    "AuthorizationRecord",
    "CompatibilityRule",
    "CompatibilityStatus",
    "GatewayConfiguration",
    "GatewayError",
    "GatewayFinding",
    "GatewayFindingCode",
    "GatewayOperation",
    "GatewayStatus",
    "IdempotencyRecord",
    "JobStatus",
    "OperationStatus",
    "ProteinSubtypeAccessSurfaceResult",
    "PublishProteinSubtypeAccessSurfaceRequest",
]
