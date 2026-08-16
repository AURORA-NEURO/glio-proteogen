"""JSON Schema 2020-12 exports for provisional M07-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_07.v1 import (
    M0707_CONTRACT_VERSION,
    M0707_GATE,
    M0707_MAX_CANDIDATES,
    M0707_MAX_CANONICAL_REQUEST_BYTES,
    M0707_MODULE_ID,
    M0707_OUTPUT_MEDIA_TYPE,
    M0707_OWNER,
    M0707_PARENT,
    M0707_PROVISIONAL_ABI,
    M0707_SAFETY_CLASS,
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrateSelectiveCopyNumberDosageRequest,
    CalibrateSelectiveCopyNumberDosageResult,
    CalibrationDiagnostic,
    CalibrationPolicy,
    CalibrationStratum,
    SelectiveSupportThreshold,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M0707_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "stratum",
    "threshold",
    "estimate",
    "prediction-set",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": CalibrateSelectiveCopyNumberDosageRequest,
    "output": CalibrateSelectiveCopyNumberDosageResult,
    "policy": CalibrationPolicy,
    "stratum": CalibrationStratum,
    "threshold": SelectiveSupportThreshold,
    "estimate": CalibratedEstimate,
    "prediction-set": CalibratedPredictionSet,
    "diagnostic": CalibrationDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict schema; this inventory is not frozen ABI."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0707_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0707_OWNER,
        "safetyClass": M0707_SAFETY_CLASS,
        "gate": M0707_GATE,
        "strict": True,
        "provisionalAbi": M0707_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "provisionalLimits": True,
        "calibrationMetricsFrozen": False,
        "coverageCeilingsFrozen": False,
        "externalContentTraversal": False,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "kinaseActivityInference": False,
        "parentTarget": M0707_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0707_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0707_MAX_CANONICAL_REQUEST_BYTES
        schema["x-glio-contract"]["maxCandidates"] = M0707_MAX_CANDIDATES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
