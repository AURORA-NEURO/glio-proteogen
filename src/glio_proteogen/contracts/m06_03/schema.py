"""JSON Schema 2020-12 exports for provisional M06-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_03.v1 import (
    M0603_CONTRACT_VERSION,
    M0603_GATE,
    M0603_MAX_CANONICAL_REQUEST_BYTES,
    M0603_MODULE_ID,
    M0603_OUTPUT_MEDIA_TYPE,
    M0603_OWNER,
    M0603_PARENT,
    M0603_SAFETY_CLASS,
    BaselineDiagnostic,
    BaselineEstimate,
    BaselinePreprocessingPolicy,
    BaselineTuningRecord,
    EstimateProteinAbundanceBaselineRequest,
    EstimateProteinAbundanceBaselineResult,
    MatureBaselineConfiguration,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-03:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0603_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "configuration",
    "preprocessing-policy",
    "tuning-record",
    "estimate",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": EstimateProteinAbundanceBaselineRequest,
    "output": EstimateProteinAbundanceBaselineResult,
    "configuration": MatureBaselineConfiguration,
    "preprocessing-policy": BaselinePreprocessingPolicy,
    "tuning-record": BaselineTuningRecord,
    "estimate": BaselineEstimate,
    "diagnostic": BaselineDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M06-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0603_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0603_OWNER,
        "safetyClass": M0603_SAFETY_CLASS,
        "gate": M0603_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "externalContentTraversal": False,
        "rawPayload": False,
        "calibratedProbability": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0603_PARENT,
        "variantPeptideEmission": False,
        "outputMediaType": M0603_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0603_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M06-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
