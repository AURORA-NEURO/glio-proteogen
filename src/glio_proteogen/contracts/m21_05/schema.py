"""JSON Schema 2020-12 exports for provisional M21-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m21_05.v1 import (
    M2105_CONTRACT_VERSION,
    M2105_GATE,
    M2105_M2104_INPUT_MEDIA_TYPE,
    M2105_MAX_CANONICAL_REQUEST_BYTES,
    M2105_MODULE_ID,
    M2105_OUTPUT_MEDIA_TYPE,
    M2105_OWNER,
    M2105_PARENT,
    M2105_PROVISIONAL_ABI,
    M2105_SAFETY_CLASS,
    CalibrationSummary,
    ComplexActivitySubgroupEvaluationResult,
    CoverageSummary,
    EvaluateComplexActivitySubgroupEquityRequest,
    EvaluationConfiguration,
    SubgroupEvaluationReport,
    SubgroupFinding,
    SubgroupPerformance,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M21-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M2105_CONTRACT_VERSION
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
    "request": EvaluateComplexActivitySubgroupEquityRequest,
    "output": ComplexActivitySubgroupEvaluationResult,
    "report": SubgroupEvaluationReport,
    "performance": SubgroupPerformance,
    "calibration": CalibrationSummary,
    "coverage": CoverageSummary,
    "configuration": EvaluationConfiguration,
    "finding": SubgroupFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M21-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2105_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2105_OWNER,
        "safetyClass": M2105_SAFETY_CLASS,
        "gate": M2105_GATE,
        "strict": True,
        "provisionalAbi": M2105_PROVISIONAL_ABI,
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
        "parentTarget": M2105_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2105_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2105_M2104_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "mixture_of_experts_subtype",
        "alternateArchitecture": "bayesian_nonparametric_subtype",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2105_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M21-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
