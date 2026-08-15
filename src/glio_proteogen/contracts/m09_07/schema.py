"""JSON Schema 2020-12 exports for provisional M09-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_07.v1 import (
    M0907_CONTRACT_VERSION,
    M0907_GATE,
    M0907_MAX_CANONICAL_REQUEST_BYTES,
    M0907_MODULE_ID,
    M0907_OUTPUT_MEDIA_TYPE,
    M0907_OWNER,
    M0907_PARENT,
    M0907_SAFETY_CLASS,
    CalibrateComplexActivitySelectivePredictionRequest,
    CalibratedEstimate,
    CalibrationCandidate,
    CalibrationConfiguration,
    CalibrationDiagnostic,
    CalibrationScope,
    ComplexActivitySelectivePredictionResult,
    PredictionSet,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M0907_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "scope",
    "estimate",
    "prediction-set",
    "diagnostic",
    "candidate",
]
_CONTRACTS: Final = {
    "request": CalibrateComplexActivitySelectivePredictionRequest,
    "output": ComplexActivitySelectivePredictionResult,
    "configuration": CalibrationConfiguration,
    "scope": CalibrationScope,
    "estimate": CalibratedEstimate,
    "prediction-set": PredictionSet,
    "diagnostic": CalibrationDiagnostic,
}
_CANDIDATE: Final = CalibrationCandidate


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-07 schema."""

    contract = _CANDIDATE if name == "candidate" else _CONTRACTS[name]
    schema = TypeAdapter(contract).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0907_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0907_OWNER,
        "safetyClass": M0907_SAFETY_CLASS,
        "gate": M0907_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0907_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0907_OUTPUT_MEDIA_TYPE,
        "uncertaintyInputMediaType": "application/vnd.glio-proteogen.m09-06+json",
        "scopedCalibrationRequired": True,
        "supportThresholdRequired": True,
        "oodChecksRequired": True,
        "nominalCoverage": 0.9,
        "coverageEnvelope": [0.85, 0.95],
        "subgroupDisparityReviewRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0907_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return the seven public provisional M09-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
