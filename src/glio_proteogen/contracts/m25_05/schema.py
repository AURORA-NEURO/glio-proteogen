"""JSON Schema 2020-12 exports for provisional M25-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m25_05.v1 import (
    M2505_CONTRACT_VERSION,
    M2505_GATE,
    M2505_M2504_INPUT_MEDIA_TYPE,
    M2505_MAX_CANONICAL_REQUEST_BYTES,
    M2505_MODULE_ID,
    M2505_OUTPUT_MEDIA_TYPE,
    M2505_OWNER,
    M2505_PARENT,
    M2505_PROVISIONAL_ABI,
    M2505_SAFETY_CLASS,
    CalibrationSummary,
    CoverageSummary,
    EvaluateProteotypeSubgroupEquityRequest,
    EvaluationConfiguration,
    ProteotypeSubgroupEvaluationResult,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupPerformance,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M25-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M2505_CONTRACT_VERSION
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
    "request": EvaluateProteotypeSubgroupEquityRequest,
    "output": ProteotypeSubgroupEvaluationResult,
    "report": SubgroupEvaluationReport,
    "performance": SubgroupPerformance,
    "calibration": CalibrationSummary,
    "coverage": CoverageSummary,
    "configuration": EvaluationConfiguration,
    "finding": SubgroupFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M25-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2505_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2505_OWNER,
        "safetyClass": M2505_SAFETY_CLASS,
        "gate": M2505_GATE,
        "strict": True,
        "provisionalAbi": M2505_PROVISIONAL_ABI,
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
        "parentTarget": M2505_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2505_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2505_M2504_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "latent_class_proteotype",
        "alternateArchitecture": "latent_class_proteotype",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2505_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M25-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
