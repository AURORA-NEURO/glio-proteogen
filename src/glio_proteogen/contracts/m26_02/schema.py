"""JSON Schema 2020-12 exports for provisional M26-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_02.v1 import (
    M2602_CONTRACT_VERSION,
    M2602_GATE,
    M2602_MAX_CANONICAL_REQUEST_BYTES,
    M2602_MODULE_ID,
    M2602_OUTPUT_MEDIA_TYPE,
    M2602_OWNER,
    M2602_PARENT,
    M2602_PROVISIONAL_ABI,
    M2602_SAFETY_CLASS,
    BuildProteinSubtypeLineageRequest,
    LineageEdge,
    LineageFinding,
    LineageGraph,
    LineageNode,
    ProteinSubtypeLineageResult,
    ReproducibilityBundle,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M26-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M2602_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "node",
    "edge",
    "graph",
    "bundle",
    "finding",
]
_CONTRACTS: Final = {
    "request": BuildProteinSubtypeLineageRequest,
    "output": ProteinSubtypeLineageResult,
    "node": LineageNode,
    "edge": LineageEdge,
    "graph": LineageGraph,
    "bundle": ReproducibilityBundle,
    "finding": LineageFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M26-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2602_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2602_OWNER,
        "safetyClass": M2602_SAFETY_CLASS,
        "gate": M2602_GATE,
        "strict": True,
        "provisionalAbi": M2602_PROVISIONAL_ABI,
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
        "parentTarget": M2602_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2602_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
        "primaryMethod": "hierarchical_multilevel_regression",
        "alternateMethod": "mixed_effects_cohort_model",
        "fallbackMethod": "cn_to_protein_regression",
        "immutableLineageRequired": True,
        "exactVersionTraceabilityRequired": True,
        "reproducibilityBundleRequired": True,
        "brokenLinksBlocked": True,
        "quarantineUnresolvedInputs": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2602_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M26-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
