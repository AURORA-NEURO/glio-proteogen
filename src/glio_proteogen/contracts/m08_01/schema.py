"""JSON Schema 2020-12 exports for provisional M08-01 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_01.v1 import (
    M0801_CONTRACT_VERSION,
    M0801_GATE,
    M0801_MAX_CANONICAL_REQUEST_BYTES,
    M0801_MODULE_ID,
    M0801_OUTPUT_MEDIA_TYPE,
    M0801_OWNER,
    M0801_PARENT,
    M0801_SAFETY_CLASS,
    FormalTranscriptProteinStateSchema,
    TranscriptProteinFeatureDefinition,
    TranscriptProteinFeatureValue,
    TranscriptProteinInvariant,
    TranscriptProteinInvariantResult,
    TranscriptProteinMigrationRule,
    ValidateTranscriptProteinStateRequest,
    ValidateTranscriptProteinStateResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-01:0.1.0-provisional"
CONTRACT_VERSION: Final = M0801_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature-definition",
    "feature-value",
    "invariant",
    "invariant-result",
    "schema",
    "migration",
]
_CONTRACTS: Final = {
    "request": ValidateTranscriptProteinStateRequest,
    "output": ValidateTranscriptProteinStateResult,
    "feature-definition": TranscriptProteinFeatureDefinition,
    "feature-value": TranscriptProteinFeatureValue,
    "invariant": TranscriptProteinInvariant,
    "invariant-result": TranscriptProteinInvariantResult,
    "schema": FormalTranscriptProteinStateSchema,
    "migration": TranscriptProteinMigrationRule,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-01 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0801_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0801_OWNER,
        "safetyClass": M0801_SAFETY_CLASS,
        "gate": M0801_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0801_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M0801_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0801_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M08-01 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
