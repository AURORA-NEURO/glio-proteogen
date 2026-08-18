"""JSON Schema 2020-12 exports for provisional M10-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m10_01.v1 import (
    M1001_CONTRACT_VERSION,
    M1001_GATE,
    M1001_MAX_CANONICAL_REQUEST_BYTES,
    M1001_MODULE_ID,
    M1001_OUTPUT_MEDIA_TYPE,
    M1001_OWNER,
    M1001_PARENT,
    M1001_SAFETY_CLASS,
    FormalProteinRnaDiscordanceStateSchema,
    ProteinRnaFeatureDefinition,
    ProteinRnaFeatureValue,
    ProteinRnaInvariant,
    ProteinRnaInvariantResult,
    ProteinRnaMigrationRule,
    ValidateProteinRnaDiscordanceStateRequest,
    ValidateProteinRnaDiscordanceStateResult,
    ValidateProteinRnaDiscordanceStateVerification,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M10-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M1001_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature-definition",
    "feature-value",
    "invariant",
    "invariant-result",
    "schema",
    "migration",
    "verification",
]
_CONTRACTS: Final = {
    "request": ValidateProteinRnaDiscordanceStateRequest,
    "output": ValidateProteinRnaDiscordanceStateResult,
    "feature-definition": ProteinRnaFeatureDefinition,
    "feature-value": ProteinRnaFeatureValue,
    "invariant": ProteinRnaInvariant,
    "invariant-result": ProteinRnaInvariantResult,
    "schema": FormalProteinRnaDiscordanceStateSchema,
    "migration": ProteinRnaMigrationRule,
    "verification": ValidateProteinRnaDiscordanceStateVerification,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M10-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1001_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1001_OWNER,
        "safetyClass": M1001_SAFETY_CLASS,
        "gate": M1001_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1001_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1001_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1001_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all nine provisional M10-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
