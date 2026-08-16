"""JSON Schema 2020-12 exports for provisional M06-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_07.v1 import (
    M0607_CONTRACT_VERSION,
    M0607_GATE,
    M0607_MAX_CANONICAL_REQUEST_BYTES,
    M0607_MODULE_ID,
    M0607_OUTPUT_MEDIA_TYPE,
    M0607_OWNER,
    M0607_PARENT,
    M0607_PROVISIONAL_ABI,
    M0607_SAFETY_CLASS,
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrateSelectiveProteinAbundanceRequest,
    CalibrateSelectiveProteinAbundanceResult,
    CalibrationDiagnostic,
    CalibrationPolicy,
    CalibrationStratum,
    SelectiveSupportThreshold,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0607_CONTRACT_VERSION
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
    "request": CalibrateSelectiveProteinAbundanceRequest,
    "output": CalibrateSelectiveProteinAbundanceResult,
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
        "moduleId": M0607_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0607_OWNER,
        "safetyClass": M0607_SAFETY_CLASS,
        "gate": M0607_GATE,
        "strict": True,
        "provisionalAbi": M0607_PROVISIONAL_ABI,
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
        "parentTarget": M0607_PARENT,
        "outputMediaType": M0607_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0607_MAX_CANONICAL_REQUEST_BYTES
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
