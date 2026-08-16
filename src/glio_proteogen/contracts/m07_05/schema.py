"""JSON Schema 2020-12 exports for provisional M07-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_05.v1 import (
    M0705_CONTRACT_VERSION,
    M0705_GATE,
    M0705_MAX_CANONICAL_REQUEST_BYTES,
    M0705_MODULE_ID,
    M0705_OUTPUT_MEDIA_TYPE,
    M0705_OWNER,
    M0705_PARENT,
    M0705_SAFETY_CLASS,
    IntegrateProteotypeConstraintsRequest,
    IntegrateProteotypeConstraintsResult,
    ProteotypeConstraintAblation,
    ProteotypeConstraintAwareEstimate,
    ProteotypeConstraintEvaluation,
    ProteotypeMechanismConstraint,
    ProteotypeMechanismConstraintSet,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M0705_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "constraint",
    "constraint-set",
    "evaluation",
    "ablation",
    "estimate",
]
_CONTRACTS: Final = {
    "request": IntegrateProteotypeConstraintsRequest,
    "output": IntegrateProteotypeConstraintsResult,
    "constraint": ProteotypeMechanismConstraint,
    "constraint-set": ProteotypeMechanismConstraintSet,
    "evaluation": ProteotypeConstraintEvaluation,
    "ablation": ProteotypeConstraintAblation,
    "estimate": ProteotypeConstraintAwareEstimate,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M07-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0705_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0705_OWNER,
        "safetyClass": M0705_SAFETY_CLASS,
        "gate": M0705_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0705_PARENT,
        "variantPeptideEmission": False,
        "hiddenPriorDominance": False,
        "softConstraintAblationRequired": True,
        "outputMediaType": M0705_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0705_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M07-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
