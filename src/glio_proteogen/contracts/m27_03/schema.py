"""JSON Schema 2020-12 exports for provisional M27-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_03.v1 import (
    M2703_CONTRACT_VERSION,
    M2703_GATE,
    M2703_M2702_INPUT_MEDIA_TYPE,
    M2703_MAX_CANONICAL_REQUEST_BYTES,
    M2703_MODULE_ID,
    M2703_OUTPUT_MEDIA_TYPE,
    M2703_OWNER,
    M2703_PARENT,
    M2703_PROVISIONAL_ABI,
    M2703_SAFETY_CLASS,
    ComplexActivityPipelineResult,
    ExecutionRecord,
    OrchestrateComplexActivityPipelineRequest,
    ReproducibleResultPackage,
    SafeFailureReport,
    WorkflowDAG,
    WorkflowEdge,
    WorkflowNode,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M27-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2703_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "dag",
    "node",
    "edge",
    "execution",
    "package",
    "safe-failure",
]
_CONTRACTS: Final = {
    "request": OrchestrateComplexActivityPipelineRequest,
    "output": ComplexActivityPipelineResult,
    "dag": WorkflowDAG,
    "node": WorkflowNode,
    "edge": WorkflowEdge,
    "execution": ExecutionRecord,
    "package": ReproducibleResultPackage,
    "safe-failure": SafeFailureReport,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M27-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2703_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2703_OWNER,
        "safetyClass": M2703_SAFETY_CLASS,
        "gate": M2703_GATE,
        "strict": True,
        "provisionalAbi": M2703_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2703_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2703_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2703_M2702_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration_protein_complex_graph",
        "alternateArchitecture": "modular_monolith_strict_boundaries_stoichiometric_factorization",
        "fallbackArchitecture": "offline_signed_release_bundles_protein_complex_graph",
        "workflowDagRequired": True,
        "containerDigestRequired": True,
        "deterministicExecutionRequired": True,
        "retryAndCheckpointRequired": True,
        "environmentCaptureRequired": True,
        "reproducibleResultPackageRequired": True,
        "safeRecoveryRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2703_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M27-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
