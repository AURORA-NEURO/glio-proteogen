"""Deep contract, closure, and authority tests for provisional M26-04."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_04 import (
    M2604_DOSSIER_SHA256,
    M2604_DOSSIER_SLICE,
    M2604_OUTPUT_MEDIA_TYPE,
    M2604_PROVISIONAL_ABI,
    AccessProtocol,
    AccessSurface,
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
    PublishProteinSubtypeAccessSurfaceRequest,
    contract_json_schemas,
)
from glio_proteogen.contracts.m26_04.canonical import canonical_request_digest
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

_SCHEMA_COUNT = 12


def _evidence() -> EvidenceReference:
    return EvidenceReference(
        reference=ArtifactReference(
            artifact_id="artifact-1",
            version="0.1.0",
            digest="sha256:" + "a" * 64,
            media_type="application/octet-stream",
        ),
        role="evidence",
        claim="Caller-declared gateway evidence.",
    )


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2604.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type="application/json",
    )


def _context(request_id: str) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2604.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2604.actor.gateway",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2604.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2604.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _request(
    request_id: str = "m2604.request.gateway",
) -> PublishProteinSubtypeAccessSurfaceRequest:
    evidence = (_evidence(),)
    operation = GatewayOperation(
        operation_id="m2604.operation.read",
        name="Read protein subtype access surface",
        version="1.0.0",
        protocol=AccessProtocol.API,
        request_media_type="application/json",
        response_media_type=M2604_OUTPUT_MEDIA_TYPE,
        authorization_scope="protein-subtype:read",
        status=OperationStatus.ACTIVE,
        asynchronous_supported=True,
        evidence=evidence,
    )
    authorization = AuthorizationRecord(
        authorization_id="m2604.authorization.read",
        operation_id=operation.operation_id,
        principal_id="m2604.principal.reader",
        scope=operation.authorization_scope,
        decision=AuthorizationDecision.ALLOW,
        policy_version="1.0.0",
        evidence=evidence,
    )
    idempotency = IdempotencyRecord(
        idempotency_id="m2604.idempotency.read",
        operation_id=operation.operation_id,
        key_digest=sha256_digest({"key": "m2604-key"}),
        request_digest="sha256:" + "b" * 64,
        evidence=evidence,
    )
    job = AsyncJobRecord(
        job_id="m2604.job.read",
        operation_id=operation.operation_id,
        status=JobStatus.SUCCEEDED,
        idempotency=idempotency,
        result_artifact=_artifact("job-result"),
        evidence=evidence,
    )
    compatibility = CompatibilityRule(
        rule_id="m2604.compatibility.read",
        operation_id=operation.operation_id,
        from_version="1.0.0",
        to_version="1.0.0",
        status=CompatibilityStatus.COMPATIBLE,
        migration_statement="No migration required.",
        evidence=evidence,
    )
    error = GatewayError(
        error_id="m2604.error.denied",
        code="authorization_denied",
        message="The operation is not authorized.",
        retryable=False,
        evidence=evidence,
    )
    audit = AuditEvent(
        event_id="m2604.audit.read",
        operation_id=operation.operation_id,
        principal_id=authorization.principal_id,
        event_type="access",
        outcome="allowed",
        request_digest="sha256:" + "c" * 64,
        evidence=evidence,
    )
    configuration = GatewayConfiguration(
        configuration_id="m2604.configuration.gateway",
        version="1.0.0",
        supported_protocols=(AccessProtocol.API, AccessProtocol.SDK, AccessProtocol.CLI),
        evidence=evidence,
    )
    sources = (
        _artifact("mass-spectrometry"),
        _artifact("genome-transcriptome"),
        _artifact("ptm-annotations"),
    )
    return PublishProteinSubtypeAccessSurfaceRequest(
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
        errors=(error,),
        audit_events=(audit,),
        configuration=configuration,
        source_artifacts=sources,
    )


def test_provisional_schemas_preserve_gateway_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["typedOperationsRequired"]
        and schema["x-glio-contract"]["authorizationRequired"]
        and schema["x-glio-contract"]["idempotencyRequired"]
        and schema["x-glio-contract"]["asynchronousJobsRequired"]
        and schema["x-glio-contract"]["errorTaxonomyRequired"]
        and schema["x-glio-contract"]["auditRequired"]
        and schema["x-glio-contract"]["compatibilityRequired"]
        and schema["x-glio-contract"]["signedReleaseBundleFallback"]
        and schema["x-glio-contract"]["humanReviewRequired"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2604_OUTPUT_MEDIA_TYPE
    assert M2604_PROVISIONAL_ABI is True


def test_operation_is_typed_and_audited() -> None:
    operation = GatewayOperation(
        operation_id="read-subtype",
        name="Read protein subtype",
        version="0.1.0-provisional",
        protocol=AccessProtocol.API,
        request_media_type="application/json",
        response_media_type="application/vnd.glio-proteogen.m26-04+json",
        authorization_scope="protein-subtype:read",
        status=OperationStatus.ACTIVE,
        asynchronous_supported=True,
        evidence=(_evidence(),),
    )
    assert operation.protocol is AccessProtocol.API
    assert operation.idempotency_required is True
    assert operation.audit_required is True


def test_authority_constants_and_request_closure_are_explicit() -> None:
    request = _request()
    assert M2604_DOSSIER_SHA256.endswith("da181")
    assert M2604_DOSSIER_SLICE.endswith(":9168-9208")
    assert request.context.request_id == request.request_id
    assert canonical_request_digest(request).startswith("sha256:")


def test_request_rejects_context_source_and_operation_drift() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="request ID"):
        type(request).model_validate(
            request.model_copy(update={"context": _context("m2604.request.other")})
        )
    duplicate_source = (*request.source_artifacts[:2], request.source_artifacts[0])
    with pytest.raises(ValidationError, match="unique artifact IDs"):
        type(request).model_validate(
            request.model_copy(update={"source_artifacts": duplicate_source})
        )
    duplicate_operation = request.operations[0].model_copy(
        update={"operation_id": "m2604.operation.other"}
    )
    with pytest.raises(ValidationError, match="unknown operation"):
        type(request).model_validate(
            request.model_copy(update={"operations": (duplicate_operation,)})
        )


def test_surface_rejects_unknown_idempotency_and_protocol() -> None:
    request = _request()
    surface = AccessSurface(
        surface_id="m2604.surface.gateway",
        version="1.0.0",
        operations=request.operations,
        authorizations=request.authorizations,
        idempotency_records=request.idempotency_records,
        jobs=request.jobs,
        compatibility_rules=request.compatibility_rules,
        errors=request.errors,
        audit_events=request.audit_events,
        configuration=request.configuration,
        evidence=(_evidence(),),
    )
    assert surface.configuration.locked is True
    foreign = request.idempotency_records[0].model_copy(
        update={"operation_id": "m2604.operation.foreign"}
    )
    with pytest.raises(ValidationError, match="idempotency record"):
        AccessSurface.model_validate(
            surface.model_copy(update={"idempotency_records": (foreign,)}).model_dump(mode="python")
        )
