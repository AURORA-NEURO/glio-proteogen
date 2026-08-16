"""JSON Schema 2020-12 exports for provisional M11-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_07.v1 import (
    M1107_CONTRACT_VERSION,
    M1107_GATE,
    M1107_M1104_RESULT_MEDIA_TYPE,
    M1107_MAX_CANONICAL_REQUEST_BYTES,
    M1107_MODULE_ID,
    M1107_OUTPUT_MEDIA_TYPE,
    M1107_OWNER,
    M1107_PARENT,
    M1107_PROVISIONAL_ABI,
    M1107_SAFETY_CLASS,
    AdjudicateVariantPeptidePlausibilityRequest,
    ControlEvaluation,
    PlausibilityControl,
    PlausibilityFinding,
    UnresolvedConflict,
    VariantPeptidePlausibilityAdjudicationResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M11-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M1107_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "control",
    "evaluation",
    "conflict",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdjudicateVariantPeptidePlausibilityRequest,
    "output": VariantPeptidePlausibilityAdjudicationResult,
    "control": PlausibilityControl,
    "evaluation": ControlEvaluation,
    "conflict": UnresolvedConflict,
    "finding": PlausibilityFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M11-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1107_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1107_OWNER,
        "safetyClass": M1107_SAFETY_CLASS,
        "gate": M1107_GATE,
        "strict": True,
        "provisionalAbi": M1107_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1107_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1107_OUTPUT_MEDIA_TYPE,
        "mechanismInputMediaType": M1107_M1104_RESULT_MEDIA_TYPE,
        "controlsRequired": True,
        "failedControlsBlockRelease": True,
        "negativeControlRequired": True,
        "conflictsPreserved": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1107_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional M11-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
