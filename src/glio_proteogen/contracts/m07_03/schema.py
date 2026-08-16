"""JSON Schema 2020-12 exports for provisional M07-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_03.v1 import (
    M0703_CONTRACT_VERSION,
    M0703_GATE,
    M0703_MAX_CANONICAL_REQUEST_BYTES,
    M0703_MODULE_ID,
    M0703_OUTPUT_MEDIA_TYPE,
    M0703_OWNER,
    M0703_PARENT,
    M0703_SAFETY_CLASS,
    BaselineDiagnostic,
    BaselineEstimate,
    BaselinePreprocessingPolicy,
    BaselineTuningRecord,
    EstimateCopyNumberDosageBaselineRequest,
    EstimateCopyNumberDosageBaselineResult,
    MatureBaselineConfiguration,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M0703_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "estimate",
    "diagnostic",
    "preprocessing",
    "tuning",
    "configuration",
]
_CONTRACTS: Final = {
    "request": EstimateCopyNumberDosageBaselineRequest,
    "output": EstimateCopyNumberDosageBaselineResult,
    "estimate": BaselineEstimate,
    "diagnostic": BaselineDiagnostic,
    "preprocessing": BaselinePreprocessingPolicy,
    "tuning": BaselineTuningRecord,
    "configuration": MatureBaselineConfiguration,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M07-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0703_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0703_OWNER,
        "safetyClass": M0703_SAFETY_CLASS,
        "gate": M0703_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0703_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0703_OUTPUT_MEDIA_TYPE,
        "representationInputMediaType": "application/vnd.glio-proteogen.m07-02+json",
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0703_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M07-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
