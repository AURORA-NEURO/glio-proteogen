"""JSON Schema 2020-12 exports for provisional M10-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_03.v1 import (
    M1003_BASELINE_MEDIA_TYPE,
    M1003_CONTRACT_VERSION,
    M1003_GATE,
    M1003_MAX_CANONICAL_REQUEST_BYTES,
    M1003_MODULE_ID,
    M1003_OUTPUT_MEDIA_TYPE,
    M1003_OWNER,
    M1003_PARENT,
    M1003_PROVISIONAL_ABI,
    M1003_SAFETY_CLASS,
    BaselineConfiguration,
    BaselineDiagnostic,
    BaselineEstimate,
    BaselinePreprocessingStep,
    BaselineTuningSpec,
    EstimateProteinRnaDiscordanceBaselineRequest,
    ProteinRnaDiscordanceBaselineResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M10-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M1003_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "preprocessing",
    "tuning",
    "estimate",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": EstimateProteinRnaDiscordanceBaselineRequest,
    "output": ProteinRnaDiscordanceBaselineResult,
    "configuration": BaselineConfiguration,
    "preprocessing": BaselinePreprocessingStep,
    "tuning": BaselineTuningSpec,
    "estimate": BaselineEstimate,
    "diagnostic": BaselineDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M10-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1003_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1003_OWNER,
        "safetyClass": M1003_SAFETY_CLASS,
        "gate": M1003_GATE,
        "strict": True,
        "provisionalAbi": M1003_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1003_PARENT,
        "unsupportedToNegative": False,
        "lockedPreprocessingRequired": True,
        "lockedTuningRequired": True,
        "uncertaintyRequired": True,
        "diagnosticsRequired": True,
        "outputMediaType": M1003_OUTPUT_MEDIA_TYPE,
        "formalStateInputMediaType": M1003_BASELINE_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1003_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
