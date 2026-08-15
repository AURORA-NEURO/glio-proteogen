"""JSON Schema 2020-12 exports for provisional M08-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_05.v1 import (
    M0805_BASELINE_MEDIA_TYPE,
    M0805_CONTRACT_VERSION,
    M0805_GATE,
    M0805_MAX_CANONICAL_REQUEST_BYTES,
    M0805_MODULE_ID,
    M0805_OUTPUT_MEDIA_TYPE,
    M0805_OWNER,
    M0805_PARENT,
    M0805_PROVISIONAL_ABI,
    M0805_SAFETY_CLASS,
    ConstraintAwareEstimate,
    ConstraintIntegratorPolicy,
    ConstraintSatisfactionReport,
    IntegrateTranscriptProteinConstraintsRequest,
    IntegrateTranscriptProteinConstraintsResult,
    MechanismConstraint,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-05:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0805_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "estimate",
    "constraint",
    "report",
    "policy",
]
_CONTRACTS: Final = {
    "request": IntegrateTranscriptProteinConstraintsRequest,
    "output": IntegrateTranscriptProteinConstraintsResult,
    "estimate": ConstraintAwareEstimate,
    "constraint": MechanismConstraint,
    "report": ConstraintSatisfactionReport,
    "policy": ConstraintIntegratorPolicy,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0805_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0805_OWNER,
        "safetyClass": M0805_SAFETY_CLASS,
        "gate": M0805_GATE,
        "strict": True,
        "provisionalAbi": M0805_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0805_PARENT,
        "unsupportedToNegative": False,
        "hardConstraintsRequired": True,
        "softConflictsQuantified": True,
        "hiddenPriorDominance": False,
        "outputMediaType": M0805_OUTPUT_MEDIA_TYPE,
        "baselineInputMediaType": M0805_BASELINE_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0805_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
