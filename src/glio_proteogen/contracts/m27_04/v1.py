"""Provisional M27-04 API, SDK and CLI gateway contracts.

M27-04 owns the typed access surface beneath the Search/quant workflow:
authorization, idempotency, asynchronous jobs, errors, audit and compatibility.
The ABI is provisional pending Clinical science owner confirmation.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m27_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 9528-9568.
M2704_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-04"
M2704_OPERATION: Final = "publish_complex_activity_access_surface"
M2704_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2704_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-04+json"
M2704_PARENT: Final = "complex activity"
M2704_OWNER: Final = "Clinical science"
M2704_SAFETY_CLASS: Final = "S3"
M2704_GATE: Final = "G2"
M2704_PROVISIONAL_ABI: Final = True
M2704_AUTHORITY_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
M2704_AUTHORITY_SLICE: Final = "9528-9568"
M2704_MAX_OPERATIONS: Final = 128
M2704_MAX_COMPATIBILITY_RULES: Final = 256
M2704_MAX_AUTHORIZATIONS: Final = 256
M2704_MAX_JOBS: Final = 256
M2704_MAX_ERRORS: Final = 128
M2704_MAX_AUDIT_EVENTS: Final = 512
M2704_MAX_FINDINGS: Final = 64
M2704_MAX_EVIDENCE: Final = 64
M2704_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2704_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2704_EVIDENCE_CLAIM: Final = (
    "Caller-declared M27-04 operation, authorization, job, error, audit and "
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)


class AuthorizationRecord(FrozenModel):
    authorization_id: Identifier
    operation_id: Identifier
    principal_id: Identifier
    scope: NonEmptyStr
    decision: AuthorizationDecision
    policy_version: SemanticVersion
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)


class IdempotencyRecord(FrozenModel):
    idempotency_id: Identifier
    operation_id: Identifier
    key_digest: Sha256Digest
    request_digest: Sha256Digest
    replay_safe: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)


class AsyncJobRecord(FrozenModel):
    job_id: Identifier
    operation_id: Identifier
    status: JobStatus
    idempotency: IdempotencyRecord
    result_artifact: ArtifactReference | None = None
    error_code: Identifier | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)

    @model_validator(mode="after")
    def terminal_job_has_outcome(self) -> AsyncJobRecord:
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)


class GatewayError(FrozenModel):
    error_id: Identifier
    code: Identifier
    message: NonEmptyStr
    retryable: bool
    safe_to_expose: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2704_MAX_EVIDENCE)


class AuditEvent(FrozenModel):
    event_id: Identifier
    operation_id: Identifier
    principal_id: Identifier
    event_type: NonEmptyStr
    outcome: NonEmptyStr
    request_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)


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
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2704_MAX_EVIDENCE)

    @model_validator(mode="after")
    def protocols_are_unique(self) -> GatewayConfiguration:
        if len(self.supported_protocols) != len(set(self.supported_protocols)):
            raise ValueError("supported gateway protocols must be unique")
        return self


class AccessSurface(FrozenModel):
    """Documented, versioned and auditable gateway surface."""

    surface_id: Identifier
    version: SemanticVersion
    operations: tuple[GatewayOperation, ...] = Field(min_length=1, max_length=M2704_MAX_OPERATIONS)
    authorizations: tuple[AuthorizationRecord, ...] = Field(
        min_length=1, max_length=M2704_MAX_AUTHORIZATIONS
    )
    idempotency_records: tuple[IdempotencyRecord, ...] = Field(
        min_length=1, max_length=M2704_MAX_JOBS
    )
    jobs: tuple[AsyncJobRecord, ...] = Field(min_length=1, max_length=M2704_MAX_JOBS)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(
        min_length=1, max_length=M2704_MAX_COMPATIBILITY_RULES
    )
    errors: tuple[GatewayError, ...] = Field(min_length=1, max_length=M2704_MAX_ERRORS)
    audit_events: tuple[AuditEvent, ...] = Field(min_length=1, max_length=M2704_MAX_AUDIT_EVENTS)
    configuration: GatewayConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2704_MAX_EVIDENCE)

    @model_validator(mode="after")
    def surface_is_closed(self) -> AccessSurface:
        _validate_gateway_components(
            operations=self.operations,
            authorizations=self.authorizations,
            idempotency_records=self.idempotency_records,
            jobs=self.jobs,
            compatibility_rules=self.compatibility_rules,
            errors=self.errors,
            audit_events=self.audit_events,
            configuration=self.configuration,
        )
        return self


class GatewayFinding(FrozenModel):
    finding_id: Identifier
    code: GatewayFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2704_MAX_EVIDENCE)


class PublishComplexActivityAccessSurfaceRequest(FrozenModel):
    """Provisional request for publishing a documented gateway surface."""

    operation: Literal["publish_complex_activity_access_surface"] = M2704_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2704_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    operations: tuple[GatewayOperation, ...] = Field(min_length=1, max_length=M2704_MAX_OPERATIONS)
    authorizations: tuple[AuthorizationRecord, ...] = Field(
        min_length=1, max_length=M2704_MAX_AUTHORIZATIONS
    )
    idempotency_records: tuple[IdempotencyRecord, ...] = Field(
        min_length=1, max_length=M2704_MAX_JOBS
    )
    jobs: tuple[AsyncJobRecord, ...] = Field(min_length=1, max_length=M2704_MAX_JOBS)
    compatibility_rules: tuple[CompatibilityRule, ...] = Field(
        min_length=1, max_length=M2704_MAX_COMPATIBILITY_RULES
    )
    errors: tuple[GatewayError, ...] = Field(min_length=1, max_length=M2704_MAX_ERRORS)
    audit_events: tuple[AuditEvent, ...] = Field(min_length=1, max_length=M2704_MAX_AUDIT_EVENTS)
    configuration: GatewayConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2704_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> PublishComplexActivityAccessSurfaceRequest:
        _validate_gateway_components(
            operations=self.operations,
            authorizations=self.authorizations,
            idempotency_records=self.idempotency_records,
            jobs=self.jobs,
            compatibility_rules=self.compatibility_rules,
            errors=self.errors,
            audit_events=self.audit_events,
            configuration=self.configuration,
        )
        artifact_ids = [artifact.artifact_id for artifact in self.source_artifacts]
        artifact_digests = [artifact.digest for artifact in self.source_artifacts]
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("source artifact ids must be unique")
        if len(set(artifact_digests)) != len(artifact_digests):
            raise ValueError("source artifact digests must be unique")
        return self


class ComplexActivityAccessSurfaceResult(FrozenModel):
    """Published access surface with typed errors and safe abstention."""

    output_type: Literal["complex_activity_access_surface"] = "complex_activity_access_surface"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2704_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: PublishComplexActivityAccessSurfaceRequest
    status: GatewayStatus
    access_surface: AccessSurface | None = None
    findings: tuple[GatewayFinding, ...] = Field(default=(), max_length=M2704_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2704_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2704_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityAccessSurfaceResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request_digest):
            raise ValueError("result id does not bind request identity")
        if self.status is GatewayStatus.PUBLISHED:
            surface = self.access_surface
            if (
                surface is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("published result requires a supported access surface")
            surface_bindings = (
                (
                    "surface id",
                    surface.surface_id,
                    f"m2704.surface.{self.request.configuration.configuration_id}",
                ),
                ("surface version", surface.version, self.request.configuration.version),
                ("operations", surface.operations, self.request.operations),
                ("authorizations", surface.authorizations, self.request.authorizations),
                (
                    "idempotency records",
                    surface.idempotency_records,
                    self.request.idempotency_records,
                ),
                ("jobs", surface.jobs, self.request.jobs),
                (
                    "compatibility rules",
                    surface.compatibility_rules,
                    self.request.compatibility_rules,
                ),
                ("errors", surface.errors, self.request.errors),
                ("audit events", surface.audit_events, self.request.audit_events),
                ("configuration", surface.configuration, self.request.configuration),
                ("evidence", surface.evidence, self.evidence),
            )
            for label, actual, expected in surface_bindings:
                if actual != expected:
                    raise ValueError(f"published result {label} does not bind the request")
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


def _require_unique(values: Sequence[str], label: str) -> set[str]:
    unique = set(values)
    if len(unique) != len(values):
        raise ValueError(f"{label} ids must be unique")
    return unique


def _validate_gateway_components(  # noqa: PLR0912, PLR0913 - explicit graph closure.
    *,
    operations: tuple[GatewayOperation, ...],
    authorizations: tuple[AuthorizationRecord, ...],
    idempotency_records: tuple[IdempotencyRecord, ...],
    jobs: tuple[AsyncJobRecord, ...],
    compatibility_rules: tuple[CompatibilityRule, ...],
    errors: tuple[GatewayError, ...],
    audit_events: tuple[AuditEvent, ...],
    configuration: GatewayConfiguration,
) -> None:
    """Close the cross-record gateway graph before runtime traversal."""

    operation_ids = _require_unique(
        tuple(operation.operation_id for operation in operations), "gateway operation"
    )
    authorization_ids = _require_unique(
        tuple(authorization.authorization_id for authorization in authorizations),
        "authorization",
    )
    idempotency_ids = _require_unique(
        tuple(record.idempotency_id for record in idempotency_records), "idempotency"
    )
    _require_unique(tuple(job.job_id for job in jobs), "async job")
    _require_unique(tuple(rule.rule_id for rule in compatibility_rules), "compatibility rule")
    _require_unique(tuple(error.error_id for error in errors), "gateway error")
    _require_unique(tuple(event.event_id for event in audit_events), "audit event")
    authorization_shapes = tuple(
        (item.operation_id, item.principal_id, item.scope) for item in authorizations
    )
    if len(set(authorization_shapes)) != len(authorization_shapes):
        raise ValueError("authorization bindings must be unique")
    idempotency_keys = tuple(record.key_digest for record in idempotency_records)
    if len(set(idempotency_keys)) != len(idempotency_keys):
        raise ValueError("idempotency keys must be unique")
    compatibility_shapes = tuple(
        (rule.operation_id, rule.from_version, rule.to_version) for rule in compatibility_rules
    )
    if len(set(compatibility_shapes)) != len(compatibility_shapes):
        raise ValueError("compatibility transitions must be unique")
    if not authorization_ids:
        raise ValueError("gateway requires authorization records")
    for authorization in authorizations:
        if authorization.operation_id not in operation_ids:
            raise ValueError("authorization references unknown operation")
    for record in idempotency_records:
        if record.operation_id not in operation_ids:
            raise ValueError("idempotency references unknown operation")
    for job in jobs:
        if job.operation_id not in operation_ids:
            raise ValueError("async job references unknown operation")
        if job.idempotency.idempotency_id not in idempotency_ids:
            raise ValueError("async job references unknown idempotency record")
        if job.idempotency.operation_id != job.operation_id:
            raise ValueError("async job idempotency operation mismatch")
    for rule in compatibility_rules:
        if rule.operation_id not in operation_ids:
            raise ValueError("compatibility rule references unknown operation")
    for event in audit_events:
        if event.operation_id not in operation_ids:
            raise ValueError("audit event references unknown operation")
    operation_by_id = {operation.operation_id: operation for operation in operations}
    for job in jobs:
        if not operation_by_id[job.operation_id].asynchronous_supported:
            raise ValueError("async job references operation without async support")
    if any(operation.protocol not in configuration.supported_protocols for operation in operations):
        raise ValueError("operation protocol is not enabled by gateway configuration")
    if any(
        authorization.operation_id not in {operation.operation_id for operation in operations}
        for authorization in authorizations
    ):
        raise ValueError("authorization operation closure failed")


__all__ = [
    "M2704_AUTHORITY_SHA256",
    "M2704_AUTHORITY_SLICE",
    "M2704_CONTRACT_VERSION",
    "M2704_EVIDENCE_CLAIM",
    "M2704_GATE",
    "M2704_MAX_AUDIT_EVENTS",
    "M2704_MAX_AUTHORIZATIONS",
    "M2704_MAX_CANONICAL_REQUEST_BYTES",
    "M2704_MAX_CANONICAL_RESULT_BYTES",
    "M2704_MAX_COMPATIBILITY_RULES",
    "M2704_MAX_ERRORS",
    "M2704_MAX_EVIDENCE",
    "M2704_MAX_FINDINGS",
    "M2704_MAX_JOBS",
    "M2704_MAX_OPERATIONS",
    "M2704_MODULE_ID",
    "M2704_OPERATION",
    "M2704_OUTPUT_MEDIA_TYPE",
    "M2704_OWNER",
    "M2704_PARENT",
    "M2704_PROVISIONAL_ABI",
    "M2704_SAFETY_CLASS",
    "AccessProtocol",
    "AccessSurface",
    "AsyncJobRecord",
    "AuditEvent",
    "AuthorizationDecision",
    "AuthorizationRecord",
    "CompatibilityRule",
    "CompatibilityStatus",
    "ComplexActivityAccessSurfaceResult",
    "GatewayConfiguration",
    "GatewayError",
    "GatewayFinding",
    "GatewayFindingCode",
    "GatewayOperation",
    "GatewayStatus",
    "IdempotencyRecord",
    "JobStatus",
    "OperationStatus",
    "PublishComplexActivityAccessSurfaceRequest",
]
