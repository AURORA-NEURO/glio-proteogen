"""Provisional M28-04 API, SDK and CLI gateway contracts.

M28-04 owns the typed access surface beneath the Proteotype explanation report:
authorization, idempotency, asynchronous jobs, errors, audit and compatibility.
The ABI is provisional pending Data engineering owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m28_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 9888-9928.
M2804_MODULE_ID: Final = "GLIO-PROTEOGEN-M28-04"
M2804_OPERATION: Final = "publish_protein_rna_discordance_access_surface"
M2804_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2804_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m28-04+json"
M2804_PARENT: Final = "protein-RNA discordance"
M2804_OWNER: Final = "Data engineering"
M2804_SAFETY_CLASS: Final = "S3"
M2804_GATE: Final = "G2"
M2804_PROVISIONAL_ABI: Final = True
M2804_MAX_OPERATIONS: Final = 128
M2804_MAX_COMPATIBILITY_RULES: Final = 256
M2804_MAX_AUTHORIZATIONS: Final = 256
M2804_MAX_JOBS: Final = 256
M2804_MAX_ERRORS: Final = 128
M2804_MAX_AUDIT_EVENTS: Final = 512
M2804_MAX_FINDINGS: Final = 64
M2804_MAX_EVIDENCE: Final = 64
M2804_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2804_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2804_EVIDENCE_CLAIM: Final = (
    "Caller-declared M28-04 operation, authorization, job, error, audit and "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)


class AuthorizationRecord(FrozenModel):
    authorization_id: Identifier
    operation_id: Identifier
    principal_id: Identifier
    scope: NonEmptyStr
    decision: AuthorizationDecision
    policy_version: SemanticVersion
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)


class IdempotencyRecord(FrozenModel):
    idempotency_id: Identifier
    operation_id: Identifier
    key_digest: Sha256Digest
    request_digest: Sha256Digest
    replay_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)


class AsyncJobRecord(FrozenModel):
    job_id: Identifier
    operation_id: Identifier
    status: JobStatus
    idempotency: IdempotencyRecord
    result_artifact: ArtifactReference | None = None
    error_code: Identifier | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def terminal_job_has_outcome(self) -> AsyncJobRecord:
        terminal = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.ABSTAINED, JobStatus.CANCELLED}
        if self.idempotency.operation_id != self.operation_id:
            raise ValueError("async job idempotency must bind the same operation")
        if self.status is JobStatus.SUCCEEDED and self.result_artifact is None:
            raise ValueError("succeeded async job requires a result artifact")
        if self.status in terminal - {JobStatus.SUCCEEDED} and self.result_artifact is not None:
            raise ValueError("non-success async job cannot carry a result artifact")
        if self.status is JobStatus.FAILED and self.error_code is None:
            raise ValueError("failed async job requires a typed error code")
        if self.status is not JobStatus.FAILED and self.error_code is not None:
            raise ValueError("only failed async jobs may carry an error code")
        return self


class CompatibilityRule(FrozenModel):
    rule_id: Identifier
    operation_id: Identifier
    from_version: SemanticVersion
    to_version: SemanticVersion
    status: CompatibilityStatus
    migration_statement: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)


class GatewayError(FrozenModel):
    error_id: Identifier
    code: Identifier
    message: NonEmptyStr
    retryable: bool
    safe_to_expose: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2804_MAX_EVIDENCE)


class AuditEvent(FrozenModel):
    event_id: Identifier
    operation_id: Identifier
    principal_id: Identifier
    event_type: NonEmptyStr
    outcome: NonEmptyStr
    request_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def protocols_are_unique(self) -> GatewayConfiguration:
        if len(self.supported_protocols) != len(set(self.supported_protocols)):
            raise ValueError("supported gateway protocols must be unique")
        return self


def _validate_gateway_collections(  # noqa: PLR0912, PLR0913
    operations: tuple[GatewayOperation, ...],
    authorizations: tuple[AuthorizationRecord, ...],
    idempotency_records: tuple[IdempotencyRecord, ...],
    jobs: tuple[AsyncJobRecord, ...],
    compatibility_rules: tuple[CompatibilityRule, ...],
    audit_events: tuple[AuditEvent, ...],
    configuration: GatewayConfiguration,
) -> None:
    """Close every cross-reference before a surface can be published."""

    operation_ids = {operation.operation_id for operation in operations}
    if len(operation_ids) != len(operations):
        raise ValueError("gateway operation ids must be unique")
    if len({auth.authorization_id for auth in authorizations}) != len(authorizations):
        raise ValueError("authorization ids must be unique")
    if len({record.idempotency_id for record in idempotency_records}) != len(idempotency_records):
        raise ValueError("idempotency ids must be unique")
    if len({job.job_id for job in jobs}) != len(jobs):
        raise ValueError("async job ids must be unique")
    if len({rule.rule_id for rule in compatibility_rules}) != len(compatibility_rules):
        raise ValueError("compatibility rule ids must be unique")
    if len({event.event_id for event in audit_events}) != len(audit_events):
        raise ValueError("audit event ids must be unique")
    idempotency_ids = {record.idempotency_id for record in idempotency_records}
    if any(auth.operation_id not in operation_ids for auth in authorizations):
        raise ValueError("authorization references unknown operation")
    if any(record.operation_id not in operation_ids for record in idempotency_records):
        raise ValueError("idempotency record references unknown operation")
    if any(job.operation_id not in operation_ids for job in jobs):
        raise ValueError("async job references unknown operation")
    if any(job.idempotency.idempotency_id not in idempotency_ids for job in jobs):
        raise ValueError("async job references unknown idempotency record")
    if any(rule.operation_id not in operation_ids for rule in compatibility_rules):
        raise ValueError("compatibility rule references unknown operation")
    if any(event.operation_id not in operation_ids for event in audit_events):
        raise ValueError("audit event references unknown operation")
    if any(operation.protocol not in configuration.supported_protocols for operation in operations):
        raise ValueError("operation protocol is not enabled by gateway configuration")


class AccessSurface(FrozenModel):
    """Documented, versioned and auditable gateway surface."""

    surface_id: Identifier
    version: SemanticVersion
    operations: tuple[GatewayOperation, ...] = Field(min_length=1, max_length=M2804_MAX_OPERATIONS)
    authorizations: tuple[AuthorizationRecord, ...] = Field(
        min_length=1, max_length=M2804_MAX_AUTHORIZATIONS
    )
    idempotency_records: tuple[IdempotencyRecord, ...] = Field(
        min_length=1, max_length=M2804_MAX_JOBS
    )
    jobs: tuple[AsyncJobRecord, ...] = Field(min_length=1, max_length=M2804_MAX_JOBS)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(
        min_length=1, max_length=M2804_MAX_COMPATIBILITY_RULES
    )
    errors: tuple[GatewayError, ...] = Field(min_length=1, max_length=M2804_MAX_ERRORS)
    audit_events: tuple[AuditEvent, ...] = Field(min_length=1, max_length=M2804_MAX_AUDIT_EVENTS)
    configuration: GatewayConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2804_MAX_EVIDENCE)

    @model_validator(mode="after")
    def surface_is_closed(self) -> AccessSurface:
        _validate_gateway_collections(
            self.operations,
            self.authorizations,
            self.idempotency_records,
            self.jobs,
            self.compatibility_rules,
            self.audit_events,
            self.configuration,
        )
        return self


class GatewayFinding(FrozenModel):
    finding_id: Identifier
    code: GatewayFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2804_MAX_EVIDENCE)


class PublishProteinRnaDiscordanceAccessSurfaceRequest(FrozenModel):
    """Provisional request for publishing a documented gateway surface."""

    operation: Literal["publish_protein_rna_discordance_access_surface"] = M2804_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2804_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    operations: tuple[GatewayOperation, ...] = Field(min_length=1, max_length=M2804_MAX_OPERATIONS)
    authorizations: tuple[AuthorizationRecord, ...] = Field(
        min_length=1, max_length=M2804_MAX_AUTHORIZATIONS
    )
    idempotency_records: tuple[IdempotencyRecord, ...] = Field(
        min_length=1, max_length=M2804_MAX_JOBS
    )
    jobs: tuple[AsyncJobRecord, ...] = Field(min_length=1, max_length=M2804_MAX_JOBS)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(
        min_length=1, max_length=M2804_MAX_COMPATIBILITY_RULES
    )
    errors: tuple[GatewayError, ...] = Field(min_length=1, max_length=M2804_MAX_ERRORS)
    audit_events: tuple[AuditEvent, ...] = Field(min_length=1, max_length=M2804_MAX_AUDIT_EVENTS)
    configuration: GatewayConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2804_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> PublishProteinRnaDiscordanceAccessSurfaceRequest:
        _validate_gateway_collections(
            self.operations,
            self.authorizations,
            self.idempotency_records,
            self.jobs,
            self.compatibility_rules,
            self.audit_events,
            self.configuration,
        )
        return self


class ProteinRnaDiscordanceAccessSurfaceResult(FrozenModel):
    """Published access surface with typed errors and safe abstention."""

    output_type: Literal["protein_rna_discordance_access_surface"] = (
        "protein_rna_discordance_access_surface"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2804_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishProteinRnaDiscordanceAccessSurfaceRequest
    status: GatewayStatus
    access_surface: AccessSurface | None = None
    findings: tuple[GatewayFinding, ...] = Field(default=(), max_length=M2804_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein-RNA discordance"] = M2804_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2804_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceAccessSurfaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request_digest):
            raise ValueError("result id does not bind the exact request digest")
        if self.status is GatewayStatus.PUBLISHED:
            if (
                self.access_surface is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("published result requires a supported access surface")
            if any(
                finding.code
                in {
                    GatewayFindingCode.OPERATION_UNAUTHORIZED,
                    GatewayFindingCode.ASYNC_JOB_UNBOUND,
                    GatewayFindingCode.COMPATIBILITY_UNRESOLVED,
                }
                for finding in self.findings
            ):
                raise ValueError("published result cannot retain blocking gateway findings")
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
    "M2804_CONTRACT_VERSION",
    "M2804_EVIDENCE_CLAIM",
    "M2804_GATE",
    "M2804_MAX_AUDIT_EVENTS",
    "M2804_MAX_AUTHORIZATIONS",
    "M2804_MAX_CANONICAL_REQUEST_BYTES",
    "M2804_MAX_CANONICAL_RESULT_BYTES",
    "M2804_MAX_COMPATIBILITY_RULES",
    "M2804_MAX_ERRORS",
    "M2804_MAX_EVIDENCE",
    "M2804_MAX_FINDINGS",
    "M2804_MAX_JOBS",
    "M2804_MAX_OPERATIONS",
    "M2804_MODULE_ID",
    "M2804_OPERATION",
    "M2804_OUTPUT_MEDIA_TYPE",
    "M2804_OWNER",
    "M2804_PARENT",
    "M2804_PROVISIONAL_ABI",
    "M2804_SAFETY_CLASS",
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
    "ProteinRnaDiscordanceAccessSurfaceResult",
    "PublishProteinRnaDiscordanceAccessSurfaceRequest",
]
