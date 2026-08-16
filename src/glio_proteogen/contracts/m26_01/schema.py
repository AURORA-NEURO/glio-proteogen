"""JSON Schema 2020-12 exports for provisional M26-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m26_01.v1 import (
    M2601_CONTRACT_VERSION,
    M2601_DOSSIER_SHA256,
    M2601_DOSSIER_SLICE,
    M2601_GATE,
    M2601_MAX_CANONICAL_REQUEST_BYTES,
    M2601_MODULE_ID,
    M2601_OUTPUT_MEDIA_TYPE,
    M2601_OWNER,
    M2601_PARENT,
    M2601_PROVISIONAL_ABI,
    M2601_SAFETY_CLASS,
    ActiveConfiguration,
    ConfigurationBinding,
    ProteinSubtypeRegistryResult,
    RegisterProteinSubtypeRegistryRequest,
    RegistryEntry,
    RegistryFinding,
    RegistryHistoryEvent,
    RegistryRecord,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M26-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M2601_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "entry",
    "history",
    "binding",
    "configuration",
    "registry",
    "finding",
]
_CONTRACTS: Final = {
    "request": RegisterProteinSubtypeRegistryRequest,
    "output": ProteinSubtypeRegistryResult,
    "entry": RegistryEntry,
    "history": RegistryHistoryEvent,
    "binding": ConfigurationBinding,
    "configuration": ActiveConfiguration,
    "registry": RegistryRecord,
    "finding": RegistryFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M26-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2601_MODULE_ID,
        "dossierSha256": M2601_DOSSIER_SHA256,
        "dossierSlice": M2601_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2601_OWNER,
        "safetyClass": M2601_SAFETY_CLASS,
        "gate": M2601_GATE,
        "strict": True,
        "provisionalAbi": M2601_PROVISIONAL_ABI,
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
        "parentTarget": M2601_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2601_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "service_mesh_workflow_orchestration",
        "alternateArchitecture": "modular_monolith_strict_package_boundaries",
        "fallbackArchitecture": "offline_signed_release_bundles",
        "primaryMethod": "consensus_clustering",
        "alternateMethod": "bayesian_factor_analysis",
        "fallbackMethod": "pca_ica_baseline",
        "registryKindsRequired": True,
        "immutableHistoryRequired": True,
        "activeConfigurationRequired": True,
        "strictPackageBoundaries": True,
        "unregisteredConfigurationBlocked": True,
        "quarantineUnresolvedInputs": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2601_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M26-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
