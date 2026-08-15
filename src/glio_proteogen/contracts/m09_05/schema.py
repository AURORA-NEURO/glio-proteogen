"""JSON Schema 2020-12 exports for provisional M09-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_05.v1 import (
    M0905_BASELINE_MEDIA_TYPE,
    M0905_CONTRACT_VERSION,
    M0905_GATE,
    M0905_MAX_CANONICAL_REQUEST_BYTES,
    M0905_MODULE_ID,
    M0905_OUTPUT_MEDIA_TYPE,
    M0905_OWNER,
    M0905_PARENT,
    M0905_PROVISIONAL_ABI,
    M0905_SAFETY_CLASS,
    ConstraintAwareEstimate,
    ConstraintIntegratorPolicy,
    ConstraintSatisfactionReport,
    IntegrateComplexActivityConstraintsRequest,
    IntegrateComplexActivityConstraintsResult,
    IntegrateComplexActivityConstraintsVerification,
    MechanismConstraint,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M0905_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "estimate",
    "constraint",
    "report",
    "policy",
    "verification",
]
_CONTRACTS: Final = {
    "request": IntegrateComplexActivityConstraintsRequest,
    "output": IntegrateComplexActivityConstraintsResult,
    "estimate": ConstraintAwareEstimate,
    "constraint": MechanismConstraint,
    "report": ConstraintSatisfactionReport,
    "policy": ConstraintIntegratorPolicy,
    "verification": IntegrateComplexActivityConstraintsVerification,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0905_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0905_OWNER,
        "safetyClass": M0905_SAFETY_CLASS,
        "gate": M0905_GATE,
        "strict": True,
        "provisionalAbi": M0905_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0905_PARENT,
        "unsupportedToNegative": False,
        "hardConstraintsRequired": True,
        "softConflictsQuantified": True,
        "hiddenPriorDominance": False,
        "outputMediaType": M0905_OUTPUT_MEDIA_TYPE,
        "baselineInputMediaType": M0905_BASELINE_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0905_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
