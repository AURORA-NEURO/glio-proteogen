"""JSON Schema 2020-12 exports for provisional M08-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_07.v1 import (
    M0807_CONTRACT_VERSION,
    M0807_GATE,
    M0807_MAX_CANONICAL_REQUEST_BYTES,
    M0807_MODULE_ID,
    M0807_OUTPUT_MEDIA_TYPE,
    M0807_OWNER,
    M0807_PARENT,
    M0807_SAFETY_CLASS,
    CalibratedEstimate,
    CalibrateProteinSubtypeSelectivePredictionRequest,
    CalibrationConfiguration,
    CalibrationDiagnostic,
    CalibrationScope,
    PredictionSet,
    ProteinSubtypeSelectivePredictionResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M0807_CONTRACT_VERSION
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
    "request": CalibrateProteinSubtypeSelectivePredictionRequest,
    "output": ProteinSubtypeSelectivePredictionResult,
    "configuration": CalibrationConfiguration,
    "scope": CalibrationScope,
    "estimate": CalibratedEstimate,
    "prediction-set": PredictionSet,
    "diagnostic": CalibrationDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0807_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0807_OWNER,
        "safetyClass": M0807_SAFETY_CLASS,
        "gate": M0807_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0807_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0807_OUTPUT_MEDIA_TYPE,
        "uncertaintyInputMediaType": "application/vnd.glio-proteogen.m08-06+json",
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0807_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M08-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
