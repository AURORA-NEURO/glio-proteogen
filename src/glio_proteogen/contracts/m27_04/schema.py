"""JSON Schema 2020-12 exports for provisional M27-04 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_04.v1 import (
    M2704_CONTRACT_VERSION,
    M2704_GATE,
    M2704_MAX_CANONICAL_REQUEST_BYTES,
    M2704_MODULE_ID,
    M2704_OUTPUT_MEDIA_TYPE,
    M2704_OWNER,
    M2704_PARENT,
    M2704_PROVISIONAL_ABI,
    M2704_SAFETY_CLASS,
    AccessSurface,
    AsyncJobRecord,
    AuditEvent,
    AuthorizationRecord,
    CompatibilityRule,
    ComplexActivityAccessSurfaceResult,
    GatewayConfiguration,
    GatewayError,
    GatewayFinding,
    GatewayOperation,
    IdempotencyRecord,
    PublishComplexActivityAccessSurfaceRequest,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M27-04:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2704_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "operation",
    "authorization",
    "idempotency",
    "job",
    "compatibility",
    "error",
    "audit",
    "configuration",
    "surface",
    "finding",
]
_CONTRACTS: Final = {
    "request": PublishComplexActivityAccessSurfaceRequest,
    "output": ComplexActivityAccessSurfaceResult,
    "operation": GatewayOperation,
    "authorization": AuthorizationRecord,
    "idempotency": IdempotencyRecord,
    "job": AsyncJobRecord,
    "compatibility": CompatibilityRule,
    "error": GatewayError,
    "audit": AuditEvent,
    "configuration": GatewayConfiguration,
    "surface": AccessSurface,
    "finding": GatewayFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M27-04 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2704_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2704_OWNER,
        "safetyClass": M2704_SAFETY_CLASS,
        "gate": M2704_GATE,
        "strict": True,
        "provisionalAbi": M2704_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2704_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2704_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
        "variantPeptideGraphAvailable": True,
        "ptmAwareStateModelAvailable": True,
        "proteoformProbabilisticModelRequired": True,
        "typedOperationsRequired": True,
        "authorizationRequired": True,
        "idempotencyRequired": True,
        "asynchronousJobsRequired": True,
        "errorTaxonomyRequired": True,
        "auditRequired": True,
        "compatibilityRequired": True,
        "signedReleaseBundleFallback": True,
        "provenanceRequired": True,
        "uncertaintyRequired": True,
        "humanReviewRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2704_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all twelve provisional M27-04 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
