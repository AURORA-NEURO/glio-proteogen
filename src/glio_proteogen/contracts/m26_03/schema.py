"""JSON Schema 2020-12 exports for provisional M26-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_03.v1 import (
    M2603_CONTRACT_VERSION,
    M2603_GATE,
    M2603_MAX_CANONICAL_REQUEST_BYTES,
    M2603_MODULE_ID,
    M2603_OUTPUT_MEDIA_TYPE,
    M2603_OWNER,
    M2603_PARENT,
    M2603_PROVISIONAL_ABI,
    M2603_SAFETY_CLASS,
    EnvironmentCapture,
    ExecuteProteinSubtypeWorkflowRequest,
    ExecutionAttempt,
    ExecutionRecord,
    PipelineFinding,
    ProteinSubtypeExecutionResult,
    ReproducibleResultPackage,
    WorkflowDefinition,
    WorkflowStep,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M26-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M2603_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "step",
    "workflow",
    "environment",
    "attempt",
    "execution",
    "package",
    "finding",
]
_CONTRACTS: Final = {
    "request": ExecuteProteinSubtypeWorkflowRequest,
    "output": ProteinSubtypeExecutionResult,
    "step": WorkflowStep,
    "workflow": WorkflowDefinition,
    "environment": EnvironmentCapture,
    "attempt": ExecutionAttempt,
    "execution": ExecutionRecord,
    "package": ReproducibleResultPackage,
    "finding": PipelineFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M26-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2603_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2603_OWNER,
        "safetyClass": M2603_SAFETY_CLASS,
        "gate": M2603_GATE,
        "strict": True,
        "provisionalAbi": M2603_PROVISIONAL_ABI,
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
        "parentTarget": M2603_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2603_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
        "primaryMethod": "signed_pathway_propagation",
        "alternateMethod": "protein_complex_graph",
        "fallbackMethod": "protein_complex_graph",
        "workflowDagRequired": True,
        "deterministicExecutionRequired": True,
        "retryAndCheckpointRequired": True,
        "environmentCaptureRequired": True,
        "reproducibilityPackageRequired": True,
        "quarantineUnresolvedInputs": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2603_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M26-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
