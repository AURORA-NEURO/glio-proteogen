"""JSON Schema 2020-12 exports for provisional M09-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_01.v1 import (
    M0901_CONTRACT_VERSION,
    M0901_GATE,
    M0901_MAX_CANONICAL_REQUEST_BYTES,
    M0901_MODULE_ID,
    M0901_OUTPUT_MEDIA_TYPE,
    M0901_OWNER,
    M0901_PARENT,
    M0901_SAFETY_CLASS,
    ComplexActivityCompatibilityRule,
    ComplexActivityConstraint,
    ComplexActivityFeatureDefinition,
    ComplexActivityFeatureValue,
    ComplexActivityInvariant,
    ComplexActivityInvariantResult,
    ComplexActivityMigrationRule,
    FormalComplexActivityStateSchema,
    ValidateComplexActivityStateRequest,
    ValidateComplexActivityStateResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M0901_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature-definition",
    "feature-value",
    "invariant",
    "invariant-result",
    "constraint",
    "compatibility",
    "schema",
    "migration",
]
_CONTRACTS: Final = {
    "request": ValidateComplexActivityStateRequest,
    "output": ValidateComplexActivityStateResult,
    "feature-definition": ComplexActivityFeatureDefinition,
    "feature-value": ComplexActivityFeatureValue,
    "invariant": ComplexActivityInvariant,
    "invariant-result": ComplexActivityInvariantResult,
    "constraint": ComplexActivityConstraint,
    "compatibility": ComplexActivityCompatibilityRule,
    "schema": FormalComplexActivityStateSchema,
    "migration": ComplexActivityMigrationRule,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0901_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0901_OWNER,
        "safetyClass": M0901_SAFETY_CLASS,
        "gate": M0901_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0901_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0901_OUTPUT_MEDIA_TYPE,
        "executableInvariantLibrary": True,
        "unitsAndDomainsRequired": True,
        "missingnessExplicit": True,
        "compatibilityAndMigrationReviewRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0901_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all ten provisional M09-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
