"""JSON Schema 2020-12 exports for provisional M13-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_07.v1 import (
    M1307_CONTRACT_VERSION,
    M1307_GATE,
    M1307_M1306_RESULT_MEDIA_TYPE,
    M1307_MAX_CANONICAL_REQUEST_BYTES,
    M1307_MODULE_ID,
    M1307_OUTPUT_MEDIA_TYPE,
    M1307_OWNER,
    M1307_PARENT,
    M1307_PROVISIONAL_ABI,
    M1307_SAFETY_CLASS,
    AdjudicateProteotypePlausibilityRequest,
    ControlEvaluation,
    PlausibilityControl,
    PlausibilityFinding,
    ProteotypePlausibilityAdjudicationResult,
    UnresolvedConflict,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M13-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1307_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "control",
    "evaluation",
    "conflict",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdjudicateProteotypePlausibilityRequest,
    "output": ProteotypePlausibilityAdjudicationResult,
    "control": PlausibilityControl,
    "evaluation": ControlEvaluation,
    "conflict": UnresolvedConflict,
    "finding": PlausibilityFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M13-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1307_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1307_OWNER,
        "safetyClass": M1307_SAFETY_CLASS,
        "gate": M1307_GATE,
        "strict": True,
        "provisionalAbi": M1307_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1307_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1307_OUTPUT_MEDIA_TYPE,
        "mechanismInputMediaType": M1307_M1306_RESULT_MEDIA_TYPE,
        "controlsRequired": True,
        "failedControlsBlockRelease": True,
        "negativeControlRequired": True,
        "conflictsPreserved": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1307_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional M13-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
