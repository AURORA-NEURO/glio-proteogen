"""Focused contract/schema smoke for provisional M27-04."""

import pytest

from glio_proteogen.contracts.m27_04 import (
    M2704_AUTHORITY_SHA256,
    M2704_AUTHORITY_SLICE,
    M2704_OUTPUT_MEDIA_TYPE,
    M2704_PROVISIONAL_ABI,
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
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

_SCHEMA_COUNT = 12
_SHA256_HEX_LENGTH = 64


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


def test_provisional_schemas_preserve_gateway_boundaries() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values())
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["variantPeptideGraphAvailable"]
        and schema["x-glio-contract"]["ptmAwareStateModelAvailable"]
        and schema["x-glio-contract"]["proteoformProbabilisticModelRequired"]
        and schema["x-glio-contract"]["typedOperationsRequired"]
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
        schema["x-glio-contract"]["parentTarget"] == "complex activity"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2704_OUTPUT_MEDIA_TYPE
    assert M2704_PROVISIONAL_ABI is True


def test_operation_is_typed_and_audited() -> None:
    operation = GatewayOperation(
        operation_id="read-complex-activity",
        name="Read complex activity",
        version="0.1.0-provisional",
        protocol=AccessProtocol.SDK,
        request_media_type="application/json",
        response_media_type="application/vnd.glio-proteogen.m27-04+json",
        authorization_scope="complex-activity:read",
        status=OperationStatus.ACTIVE,
        asynchronous_supported=True,
        evidence=(_evidence(),),
    )
    assert operation.protocol is AccessProtocol.SDK
    assert operation.idempotency_required is True
    assert operation.audit_required is True


def _surface(*, asynchronous: bool = True) -> AccessSurface:
    evidence = (_evidence(),)
    operation = GatewayOperation(
        operation_id="read-complex-activity",
        name="Read complex activity",
        version="0.1.0-provisional",
        protocol=AccessProtocol.SDK,
        request_media_type="application/json",
        response_media_type="application/vnd.glio-proteogen.m27-04+json",
        authorization_scope="complex-activity:read",
        status=OperationStatus.ACTIVE,
        asynchronous_supported=asynchronous,
        evidence=evidence,
    )
    authorization = AuthorizationRecord(
        authorization_id="authorization-1",
        operation_id=operation.operation_id,
        principal_id="principal-1",
        scope=operation.authorization_scope,
        decision=AuthorizationDecision.ALLOW,
        policy_version="0.1.0",
        evidence=evidence,
    )
    idempotency = IdempotencyRecord(
        idempotency_id="idempotency-1",
        operation_id=operation.operation_id,
        key_digest="sha256:" + "b" * 64,
        request_digest="sha256:" + "c" * 64,
        evidence=evidence,
    )
    job = AsyncJobRecord(
        job_id="job-1",
        operation_id=operation.operation_id,
        status=JobStatus.SUCCEEDED,
        idempotency=idempotency,
        result_artifact=ArtifactReference(
            artifact_id="result-1",
            version="0.1.0",
            digest="sha256:" + "d" * 64,
            media_type="application/json",
        ),
        evidence=evidence,
    )
    return AccessSurface(
        surface_id="surface-1",
        version="0.1.0",
        operations=(operation,),
        authorizations=(authorization,),
        idempotency_records=(idempotency,),
        jobs=(job,),
        compatibility_rules=(
            CompatibilityRule(
                rule_id="compatibility-1",
                operation_id=operation.operation_id,
                from_version="0.1.0",
                to_version="0.1.0",
                status=CompatibilityStatus.COMPATIBLE,
                migration_statement="No migration required.",
                evidence=evidence,
            ),
        ),
        errors=(
            GatewayError(
                error_id="error-1",
                code="invalid_request",
                message="Invalid request.",
                retryable=False,
            ),
        ),
        audit_events=(
            AuditEvent(
                event_id="audit-1",
                operation_id=operation.operation_id,
                principal_id="principal-1",
                event_type="publish",
                outcome="allowed",
                request_digest="sha256:" + "e" * 64,
                evidence=evidence,
            ),
        ),
        configuration=GatewayConfiguration(
            configuration_id="configuration-1",
            version="0.1.0",
            supported_protocols=(AccessProtocol.SDK,),
            evidence=evidence,
        ),
        evidence=evidence,
    )


def test_gateway_graph_closure_binds_operation_records() -> None:
    surface = _surface()
    assert surface.operations[0].operation_id == surface.jobs[0].operation_id
    assert surface.jobs[0].idempotency.idempotency_id == "idempotency-1"


def test_gateway_graph_rejects_async_job_for_sync_operation() -> None:
    with pytest.raises(ValueError, match="without async support"):
        _surface(asynchronous=False)


def test_authority_identity_is_explicitly_provisional() -> None:
    assert len(M2704_AUTHORITY_SHA256) == _SHA256_HEX_LENGTH
    assert M2704_AUTHORITY_SLICE == "9528-9568"
