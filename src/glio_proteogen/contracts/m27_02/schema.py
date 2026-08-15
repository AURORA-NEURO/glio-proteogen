"""JSON Schema 2020-12 exports for provisional M27-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m27_02.v1 import (
    M2702_CONTRACT_VERSION,
    M2702_GATE,
    M2702_M2701_INPUT_MEDIA_TYPE,
    M2702_MAX_CANONICAL_REQUEST_BYTES,
    M2702_MODULE_ID,
    M2702_OUTPUT_MEDIA_TYPE,
    M2702_OWNER,
    M2702_PARENT,
    M2702_PROVISIONAL_ABI,
    M2702_SAFETY_CLASS,
    ComplexActivityLineageResult,
    LineageEdge,
    LineageFinding,
    LineageGraph,
    LineageNode,
    ReproducibilityBundle,
    ResolveComplexActivityLineageRequest,
    SafeFailureReport,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M27-02:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2702_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "graph",
    "node",
    "edge",
    "bundle",
    "finding",
    "safe-failure",
]
_CONTRACTS: Final = {
    "request": ResolveComplexActivityLineageRequest,
    "output": ComplexActivityLineageResult,
    "graph": LineageGraph,
    "node": LineageNode,
    "edge": LineageEdge,
    "bundle": ReproducibilityBundle,
    "finding": LineageFinding,
    "safe-failure": SafeFailureReport,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M27-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2702_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2702_OWNER,
        "safetyClass": M2702_SAFETY_CLASS,
        "gate": M2702_GATE,
        "strict": True,
        "provisionalAbi": M2702_PROVISIONAL_ABI,
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
        "parentTarget": M2702_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2702_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2702_M2701_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration_mixed_effects_cohort_model",
        "alternateArchitecture": (
            "modular_monolith_strict_boundaries_transcript_protein_residual_model"
        ),
        "fallbackArchitecture": "offline_signed_release_bundles_cn_to_protein_regression",
        "immutableLineageRequired": True,
        "queryableGraphRequired": True,
        "exactVersionTraceabilityRequired": True,
        "reproducibilityBundleRequired": True,
        "brokenLinkRejectionRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2702_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M27-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
