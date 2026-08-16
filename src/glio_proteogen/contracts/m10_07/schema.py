"""JSON Schema 2020-12 exports for provisional M10-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_07.v1 import (
    M1007_CONTRACT_VERSION,
    M1007_GATE,
    M1007_MAX_CANONICAL_REQUEST_BYTES,
    M1007_MODULE_ID,
    M1007_OUTPUT_MEDIA_TYPE,
    M1007_OWNER,
    M1007_PARENT,
    M1007_PROVISIONAL_ABI,
    M1007_SAFETY_CLASS,
    M1007_UNCERTAINTY_MEDIA_TYPE,
    CalibratedEstimate,
    CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    CalibrationConfiguration,
    CalibrationDiagnostic,
    CalibrationScope,
    PredictionSet,
    ProteinRnaDiscordanceSelectivePredictionResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M10-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1007_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "scope",
    "estimate",
    "prediction-set",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": CalibrateProteinRnaDiscordanceSelectivePredictionRequest,
    "output": ProteinRnaDiscordanceSelectivePredictionResult,
    "configuration": CalibrationConfiguration,
    "scope": CalibrationScope,
    "estimate": CalibratedEstimate,
    "prediction-set": PredictionSet,
    "diagnostic": CalibrationDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M10-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1007_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1007_OWNER,
        "safetyClass": M1007_SAFETY_CLASS,
        "gate": M1007_GATE,
        "strict": True,
        "provisionalAbi": M1007_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1007_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1007_OUTPUT_MEDIA_TYPE,
        "uncertaintyInputMediaType": M1007_UNCERTAINTY_MEDIA_TYPE,
        "scopedCalibrationRequired": True,
        "supportThresholdRequired": True,
        "oodChecksRequired": True,
        "nominalCoverage": 0.9,
        "coverageEnvelope": [0.85, 0.95],
        "subgroupDisparityReviewRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1007_MAX_CANONICAL_REQUEST_BYTES
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
