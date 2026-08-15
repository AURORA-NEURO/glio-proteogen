"""JSON Schema 2020-12 exports for provisional M06-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m06_01.v1 import (
    M0601_CONTRACT_VERSION,
    M0601_GATE,
    M0601_MAX_CANONICAL_REQUEST_BYTES,
    M0601_MODULE_ID,
    M0601_OUTPUT_MEDIA_TYPE,
    M0601_OWNER,
    M0601_PARENT,
    M0601_SAFETY_CLASS,
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateInvariant,
    FormalStateInvariantResult,
    FormalStateMigrationRule,
    ValidateFormalProteinStateRequest,
    ValidateFormalProteinStateResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M06-01:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0601_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "schema",
    "feature-definition",
    "feature-value",
    "invariant",
    "invariant-result",
    "migration",
]
_CONTRACTS: Final = {
    "request": ValidateFormalProteinStateRequest,
    "output": ValidateFormalProteinStateResult,
    "schema": FormalProteinStateSchema,
    "feature-definition": FormalStateFeatureDefinition,
    "feature-value": FormalStateFeatureValue,
    "invariant": FormalStateInvariant,
    "invariant-result": FormalStateInvariantResult,
    "migration": FormalStateMigrationRule,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M06-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0601_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0601_OWNER,
        "safetyClass": M0601_SAFETY_CLASS,
        "gate": M0601_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "externalContentTraversal": False,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0601_PARENT,
        "variantPeptideEmission": False,
        "outputMediaType": M0601_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0601_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M06-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
