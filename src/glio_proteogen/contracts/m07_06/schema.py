"""JSON Schema 2020-12 exports for provisional M07-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_06.v1 import (
    M0706_CONTRACT_VERSION,
    M0706_GATE,
    M0706_MAX_CANONICAL_REQUEST_BYTES,
    M0706_MODULE_ID,
    M0706_OUTPUT_MEDIA_TYPE,
    M0706_OWNER,
    M0706_PARENT,
    M0706_SAFETY_CLASS,
    CopyNumberDosageUncertaintyDecompositionResult,
    DecomposeCopyNumberDosageUncertaintyRequest,
    SensitivityEnvelope,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyFinding,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M0706_CONTRACT_VERSION
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
    "request": DecomposeCopyNumberDosageUncertaintyRequest,
    "output": CopyNumberDosageUncertaintyDecompositionResult,
    "component": UncertaintyComponent,
    "decomposition": UncertaintyDecomposition,
    "sensitivity-envelope": SensitivityEnvelope,
    "policy": UncertaintyDecompositionPolicy,
    "finding": UncertaintyFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M07-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0706_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0706_OWNER,
        "safetyClass": M0706_SAFETY_CLASS,
        "gate": M0706_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0706_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0706_OUTPUT_MEDIA_TYPE,
        "constraintInputMediaType": "application/vnd.glio-proteogen.m07-05+json",
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0706_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M07-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
