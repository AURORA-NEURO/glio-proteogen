"""JSON Schema 2020-12 exports for provisional M22-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m22_05.v1 import (
    M2205_CONTRACT_VERSION,
    M2205_DOSSIER_SHA256,
    M2205_DOSSIER_SLICE,
    M2205_GATE,
    M2205_M2204_INPUT_MEDIA_TYPE,
    M2205_MAX_CANONICAL_REQUEST_BYTES,
    M2205_MODULE_ID,
    M2205_OUTPUT_MEDIA_TYPE,
    M2205_OWNER,
    M2205_PARENT,
    M2205_PROVISIONAL_ABI,
    M2205_SAFETY_CLASS,
    CalibrationSummary,
    CoverageSummary,
    EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
    EvaluationConfiguration,
    ProteinRnaDiscordanceSubgroupEvaluationResult,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupPerformance,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M22-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M2205_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "report",
    "performance",
    "calibration",
    "coverage",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": EvaluateProteinRnaDiscordanceSubgroupEquityRequest,
    "output": ProteinRnaDiscordanceSubgroupEvaluationResult,
    "report": SubgroupEvaluationReport,
    "performance": SubgroupPerformance,
    "calibration": CalibrationSummary,
    "coverage": CoverageSummary,
    "configuration": EvaluationConfiguration,
    "finding": SubgroupFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M22-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2205_MODULE_ID,
        "authoritySha256": M2205_DOSSIER_SHA256,
        "authoritySlice": M2205_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2205_OWNER,
        "safetyClass": M2205_SAFETY_CLASS,
        "gate": M2205_GATE,
        "strict": True,
        "provisionalAbi": M2205_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2205_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2205_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2205_M2204_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_nonparametric_subtype",
        "alternateArchitecture": "open_set_proteotype",
        "fallbackArchitecture": "latent_class_proteotype",
        "subgroupDimensionsRequired": True,
        "equitySafetyFloorRequired": True,
        "calibrationRequired": True,
        "coverageRequired": True,
        "rareContextRestrictionRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2205_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M22-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
