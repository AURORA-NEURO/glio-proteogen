"""JSON Schema 2020-12 exports for provisional M15-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_07.v1 import (
    M1507_CONTRACT_VERSION,
    M1507_GATE,
    M1507_M1506_RESULT_MEDIA_TYPE,
    M1507_MAX_CANONICAL_REQUEST_BYTES,
    M1507_MODULE_ID,
    M1507_OUTPUT_MEDIA_TYPE,
    M1507_OWNER,
    M1507_PARENT,
    M1507_PROVISIONAL_ABI,
    M1507_SAFETY_CLASS,
    AdjudicateComplexActivityPlausibilityRequest,
    ComplexActivityPlausibilityAdjudicationResult,
    ControlEvaluation,
    PlausibilityControl,
    PlausibilityFinding,
    UnresolvedConflict,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M1507_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "control",
    "evaluation",
    "conflict",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdjudicateComplexActivityPlausibilityRequest,
    "output": ComplexActivityPlausibilityAdjudicationResult,
    "control": PlausibilityControl,
    "evaluation": ControlEvaluation,
    "conflict": UnresolvedConflict,
    "finding": PlausibilityFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1507_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1507_OWNER,
        "safetyClass": M1507_SAFETY_CLASS,
        "gate": M1507_GATE,
        "strict": True,
        "provisionalAbi": M1507_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1507_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1507_OUTPUT_MEDIA_TYPE,
        "sensitivityInputMediaType": M1507_M1506_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "longitudinal_state_space",
        "alternateArchitecture": "longitudinal_state_space",
        "fallbackArchitecture": "spatial_proteotype_field",
        "controlsRequired": True,
        "failedControlsBlockRelease": True,
        "negativeControlRequired": True,
        "conflictsPreserved": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1507_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional M15-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
