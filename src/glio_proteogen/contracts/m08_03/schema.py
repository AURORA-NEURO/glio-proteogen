"""JSON Schema 2020-12 exports for provisional M08-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_03.v1 import (
    M0803_CONTRACT_VERSION,
    M0803_GATE,
    M0803_MAX_CANONICAL_REQUEST_BYTES,
    M0803_MODULE_ID,
    M0803_OUTPUT_MEDIA_TYPE,
    M0803_OWNER,
    M0803_PARENT,
    M0803_SAFETY_CLASS,
    BaselineDiagnostic,
    BaselineRunConfiguration,
    EstimateProteinSubtypeBaselineRequest,
    ProteinSubtypeBaselineEstimate,
    ProteinSubtypeBaselineResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M0803_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "estimate",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": EstimateProteinSubtypeBaselineRequest,
    "output": ProteinSubtypeBaselineResult,
    "configuration": BaselineRunConfiguration,
    "estimate": ProteinSubtypeBaselineEstimate,
    "diagnostic": BaselineDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0803_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0803_OWNER,
        "safetyClass": M0803_SAFETY_CLASS,
        "gate": M0803_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0803_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0803_OUTPUT_MEDIA_TYPE,
        "representationInputMediaType": "application/vnd.glio-proteogen.m08-02+json",
        "lockedPreprocessingRequired": True,
        "lockedTuningRequired": True,
        "lockedUncertaintyRequired": True,
        "benchmarkEvidenceRequired": True,
        "diagnosticsRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0803_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all five provisional M08-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
