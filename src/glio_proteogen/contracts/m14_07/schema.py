"""JSON Schema 2020-12 exports for provisional M14-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_07.v1 import (
    M1407_CONTRACT_VERSION,
    M1407_GATE,
    M1407_M1404_RESULT_MEDIA_TYPE,
    M1407_MAX_CANONICAL_REQUEST_BYTES,
    M1407_MODULE_ID,
    M1407_OUTPUT_MEDIA_TYPE,
    M1407_OWNER,
    M1407_PARENT,
    M1407_PROVISIONAL_ABI,
    M1407_SAFETY_CLASS,
    AdjudicateProteinSubtypePlausibilityRequest,
    ControlEvaluation,
    PlausibilityControl,
    PlausibilityFinding,
    ProteinSubtypePlausibilityAdjudicationResult,
    UnresolvedConflict,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M1407_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "control",
    "evaluation",
    "conflict",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdjudicateProteinSubtypePlausibilityRequest,
    "output": ProteinSubtypePlausibilityAdjudicationResult,
    "control": PlausibilityControl,
    "evaluation": ControlEvaluation,
    "conflict": UnresolvedConflict,
    "finding": PlausibilityFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1407_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1407_OWNER,
        "safetyClass": M1407_SAFETY_CLASS,
        "gate": M1407_GATE,
        "strict": True,
        "provisionalAbi": M1407_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1407_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1407_OUTPUT_MEDIA_TYPE,
        "mechanismInputMediaType": M1407_M1404_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "territory_conditioned_subtype",
        "alternateArchitecture": "spatial_proteotype_field",
        "fallbackArchitecture": "spatial_proteotype_field",
        "controlsRequired": True,
        "failedControlsBlockRelease": True,
        "negativeControlRequired": True,
        "conflictsPreserved": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1407_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional M14-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
