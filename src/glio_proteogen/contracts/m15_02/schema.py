"""JSON Schema 2020-12 exports for provisional M15-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_02.v1 import (
    M1502_CONTRACT_VERSION,
    M1502_GATE,
    M1502_M1501_INPUT_MEDIA_TYPE,
    M1502_MAX_CANONICAL_REQUEST_BYTES,
    M1502_MODULE_ID,
    M1502_OUTPUT_MEDIA_TYPE,
    M1502_OWNER,
    M1502_PARENT,
    M1502_PROVISIONAL_ABI,
    M1502_SAFETY_CLASS,
    ApplicableMechanism,
    ContextAttribute,
    ContextEvaluation,
    ContextFinding,
    ContextProfile,
    LongitudinalRecurrenceContextStratificationResult,
    StratifyContextAndSubtypeRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1502_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "attribute",
    "mechanism",
    "profile",
    "evaluation",
    "finding",
]
_CONTRACTS: Final = {
    "request": StratifyContextAndSubtypeRequest,
    "output": LongitudinalRecurrenceContextStratificationResult,
    "attribute": ContextAttribute,
    "mechanism": ApplicableMechanism,
    "profile": ContextProfile,
    "evaluation": ContextEvaluation,
    "finding": ContextFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1502_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1502_OWNER,
        "safetyClass": M1502_SAFETY_CLASS,
        "gate": M1502_GATE,
        "strict": True,
        "provisionalAbi": M1502_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1502_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1502_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1502_M1501_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "elastic_net_consequence_model",
        "alternateArchitecture": "curated_mechanistic_baseline",
        "fallbackArchitecture": "cn_to_protein_regression",
        "contextDimensionsExplicit": True,
        "applicableMechanismsExplicit": True,
        "conflictsPreserved": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
        "safeMissingEvidence": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1502_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M15-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
