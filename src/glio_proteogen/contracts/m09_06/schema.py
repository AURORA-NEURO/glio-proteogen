"""JSON Schema 2020-12 exports for provisional M09-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_06.v1 import (
    M0906_CONTRACT_VERSION,
    M0906_GATE,
    M0906_MAX_CANONICAL_REQUEST_BYTES,
    M0906_MODULE_ID,
    M0906_OUTPUT_MEDIA_TYPE,
    M0906_OWNER,
    M0906_PARENT,
    M0906_SAFETY_CLASS,
    ComplexActivityUncertaintyDecompositionResult,
    DecomposeComplexActivityUncertaintyRequest,
    SensitivityEnvelope,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyFinding,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M0906_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "component",
    "decomposition",
    "sensitivity-envelope",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": DecomposeComplexActivityUncertaintyRequest,
    "output": ComplexActivityUncertaintyDecompositionResult,
    "component": UncertaintyComponent,
    "decomposition": UncertaintyDecomposition,
    "sensitivity-envelope": SensitivityEnvelope,
    "policy": UncertaintyDecompositionPolicy,
    "finding": UncertaintyFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0906_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0906_OWNER,
        "safetyClass": M0906_SAFETY_CLASS,
        "gate": M0906_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0906_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0906_OUTPUT_MEDIA_TYPE,
        "integratorInputMediaType": "application/vnd.glio-proteogen.m09-05+json",
        "sevenUncertaintyDimensionsRequired": True,
        "nominalCoverage": 0.9,
        "coverageEnvelope": [0.85, 0.95],
        "sensitivityRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0906_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M09-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
