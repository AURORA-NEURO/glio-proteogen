"""JSON Schema 2020-12 exports for provisional M24-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m24_05.v1 import (
    M2405_CONTRACT_VERSION,
    M2405_GATE,
    M2405_M2404_INPUT_MEDIA_TYPE,
    M2405_MAX_CANONICAL_REQUEST_BYTES,
    M2405_MODULE_ID,
    M2405_OUTPUT_MEDIA_TYPE,
    M2405_OWNER,
    M2405_PARENT,
    M2405_PROVISIONAL_ABI,
    M2405_SAFETY_CLASS,
    BiomarkerPanelSubgroupEvaluationResult,
    CalibrationSummary,
    CoverageSummary,
    EvaluateBiomarkerPanelSubgroupEquityRequest,
    EvaluationConfiguration,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupPerformance,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M24-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M2405_CONTRACT_VERSION
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
    "request": EvaluateBiomarkerPanelSubgroupEquityRequest,
    "output": BiomarkerPanelSubgroupEvaluationResult,
    "report": SubgroupEvaluationReport,
    "performance": SubgroupPerformance,
    "calibration": CalibrationSummary,
    "coverage": CoverageSummary,
    "configuration": EvaluationConfiguration,
    "finding": SubgroupFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M24-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2405_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2405_OWNER,
        "safetyClass": M2405_SAFETY_CLASS,
        "gate": M2405_GATE,
        "strict": True,
        "provisionalAbi": M2405_PROVISIONAL_ABI,
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
        "parentTarget": M2405_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2405_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2405_M2404_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "open_set_proteotype",
        "alternateArchitecture": "semi_supervised_classifier",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2405_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M24-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
