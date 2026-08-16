"""JSON Schema 2020-12 exports for provisional M08-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_06.v1 import (
    M0806_CONTRACT_VERSION,
    M0806_GATE,
    M0806_MAX_CANONICAL_REQUEST_BYTES,
    M0806_MODULE_ID,
    M0806_OUTPUT_MEDIA_TYPE,
    M0806_OWNER,
    M0806_PARENT,
    M0806_SAFETY_CLASS,
    DecomposeTranscriptProteinUncertaintyRequest,
    SensitivityEnvelope,
    TranscriptProteinUncertaintyDecompositionResult,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionPolicy,
    UncertaintyFinding,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M0806_CONTRACT_VERSION
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
    "request": DecomposeTranscriptProteinUncertaintyRequest,
    "output": TranscriptProteinUncertaintyDecompositionResult,
    "component": UncertaintyComponent,
    "decomposition": UncertaintyDecomposition,
    "sensitivity-envelope": SensitivityEnvelope,
    "policy": UncertaintyDecompositionPolicy,
    "finding": UncertaintyFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0806_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0806_OWNER,
        "safetyClass": M0806_SAFETY_CLASS,
        "gate": M0806_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0806_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0806_OUTPUT_MEDIA_TYPE,
        "estimatorInputMediaType": "application/vnd.glio-proteogen.m08-05+json",
        "sevenUncertaintyDimensionsRequired": True,
        "nominalCoverage": 0.9,
        "coverageEnvelope": [0.85, 0.95],
        "sensitivityRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0806_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M08-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
