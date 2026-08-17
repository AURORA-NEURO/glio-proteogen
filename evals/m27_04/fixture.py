"""Public representative M27-04 request builder for eval and benchmarks."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from glio_proteogen.contracts.m27_04 import (
    M2704_OUTPUT_MEDIA_TYPE,
    AccessProtocol,
    AsyncJobRecord,
    AuditEvent,
    AuthorizationDecision,
    AuthorizationRecord,
    CompatibilityRule,
    CompatibilityStatus,
    GatewayConfiguration,
    GatewayError,
    GatewayOperation,
    IdempotencyRecord,
    JobStatus,
    OperationStatus,
    PublishComplexActivityAccessSurfaceRequest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2704.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type="application/json",
    )


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact("evidence"),
        role="evidence",
        claim="Caller-declared M27-04 gateway evidence.",
    )


def _context(request_id: str) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2704.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2704.actor.gateway",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2704.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2704.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def build_request(
    request_id: str = "m2704.request.gateway",
) -> PublishComplexActivityAccessSurfaceRequest:
    """Build the frozen representative request used by executable evidence."""

    evidence = (_evidence(),)
    operation = GatewayOperation(
        operation_id="m2704.operation.read",
        name="Read complex activity access surface",
        version="1.0.0",
        protocol=AccessProtocol.API,
        request_media_type="application/json",
        response_media_type=M2704_OUTPUT_MEDIA_TYPE,
        authorization_scope="complex-activity:read",
        status=OperationStatus.ACTIVE,
        asynchronous_supported=True,
        evidence=evidence,
    )
    authorization = AuthorizationRecord(
        authorization_id="m2704.authorization.read",
        operation_id=operation.operation_id,
        principal_id="m2704.principal.reader",
        scope=operation.authorization_scope,
        decision=AuthorizationDecision.ALLOW,
        policy_version="1.0.0",
        evidence=evidence,
    )
    idempotency = IdempotencyRecord(
        idempotency_id="m2704.idempotency.read",
        operation_id=operation.operation_id,
        key_digest=sha256_digest({"key": "m2704-key"}),
        request_digest="sha256:" + "b" * 64,
        evidence=evidence,
    )
    job = AsyncJobRecord(
        job_id="m2704.job.read",
        operation_id=operation.operation_id,
        status=JobStatus.SUCCEEDED,
        idempotency=idempotency,
        result_artifact=_artifact("job-result"),
        evidence=evidence,
    )
    compatibility = CompatibilityRule(
        rule_id="m2704.compatibility.read",
        operation_id=operation.operation_id,
        from_version="1.0.0",
        to_version="1.0.0",
        status=CompatibilityStatus.COMPATIBLE,
        migration_statement="No migration required.",
        evidence=evidence,
    )
    audit = AuditEvent(
        event_id="m2704.audit.read",
        operation_id=operation.operation_id,
        principal_id=authorization.principal_id,
        event_type="access",
        outcome="allowed",
        request_digest="sha256:" + "c" * 64,
        evidence=evidence,
    )
    configuration = GatewayConfiguration(
        configuration_id="m2704.configuration.gateway",
        version="1.0.0",
        supported_protocols=(AccessProtocol.API, AccessProtocol.SDK, AccessProtocol.CLI),
        evidence=evidence,
    )
    sources = (_artifact("mass-spectrometry"), _artifact("genome-transcriptome"), _artifact("ptm"))
    return PublishComplexActivityAccessSurfaceRequest(
        request_id=request_id,
        context=_context(request_id),
        mass_spectrometry_proteome=sources[0],
        genome_transcriptome=sources[1],
        ptm_annotations=sources[2],
        operations=(operation,),
        authorizations=(authorization,),
        idempotency_records=(idempotency,),
        jobs=(job,),
        compatibility_rules=(compatibility,),
        errors=(
            GatewayError(
                error_id="m2704.error.denied",
                code="authorization_denied",
                message="The operation is not authorized.",
                retryable=False,
                evidence=evidence,
            ),
        ),
        audit_events=(audit,),
        configuration=configuration,
        source_artifacts=sources,
    )


__all__ = ["build_request"]
