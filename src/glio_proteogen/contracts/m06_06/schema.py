"""JSON Schema 2020-12 exports for provisional M06-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_06.v1 import (
    M0606_CONTRACT_VERSION,
    M0606_GATE,
    M0606_MAX_CANONICAL_REQUEST_BYTES,
    M0606_MODULE_ID,
    M0606_OUTPUT_MEDIA_TYPE,
    M0606_OWNER,
    M0606_PARENT,
    M0606_SAFETY_CLASS,
    DecomposeProteinAbundanceUncertaintyRequest,
    ProteinAbundanceUncertaintyDecompositionResult,
    SensitivityEnvelope,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyFinding,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M0606_CONTRACT_VERSION
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
    "request": DecomposeProteinAbundanceUncertaintyRequest,
    "output": ProteinAbundanceUncertaintyDecompositionResult,
    "component": UncertaintyComponent,
    "decomposition": UncertaintyDecomposition,
    "sensitivity-envelope": SensitivityEnvelope,
    "policy": UncertaintyDecompositionPolicy,
    "finding": UncertaintyFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M06-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0606_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0606_OWNER,
        "safetyClass": M0606_SAFETY_CLASS,
        "gate": M0606_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0606_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0606_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0606_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M06-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
