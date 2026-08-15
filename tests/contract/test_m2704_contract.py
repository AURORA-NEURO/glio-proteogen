"""Focused contract/schema smoke for provisional M27-04."""

from glio_proteogen.contracts.m27_04 import (
    M2704_OUTPUT_MEDIA_TYPE,
    M2704_PROVISIONAL_ABI,
    AccessProtocol,
    GatewayOperation,
    OperationStatus,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, EvidenceReference

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
