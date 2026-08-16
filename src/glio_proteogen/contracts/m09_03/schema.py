"""JSON Schema 2020-12 exports for provisional M09-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_03.v1 import (
    M0903_CONTRACT_VERSION,
    M0903_GATE,
    M0903_MAX_CANONICAL_REQUEST_BYTES,
    M0903_MODULE_ID,
    M0903_OUTPUT_MEDIA_TYPE,
    M0903_OWNER,
    M0903_PARENT,
    M0903_SAFETY_CLASS,
    BaselineDiagnostic,
    BaselineRunConfiguration,
    ComplexActivityBaselineEstimate,
    ComplexActivityBaselineResult,
    EstimateComplexActivityBaselineRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M0903_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "estimate",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": EstimateComplexActivityBaselineRequest,
    "output": ComplexActivityBaselineResult,
    "configuration": BaselineRunConfiguration,
    "estimate": ComplexActivityBaselineEstimate,
    "diagnostic": BaselineDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0903_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0903_OWNER,
        "safetyClass": M0903_SAFETY_CLASS,
        "gate": M0903_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0903_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0903_OUTPUT_MEDIA_TYPE,
        "representationInputMediaType": "application/vnd.glio-proteogen.m09-02+json",
        "lockedPreprocessingRequired": True,
        "lockedTuningRequired": True,
        "lockedUncertaintyRequired": True,
        "benchmarkEvidenceRequired": True,
        "diagnosticsRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0903_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all five provisional M09-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
