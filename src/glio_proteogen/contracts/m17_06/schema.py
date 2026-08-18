"""JSON Schema 2020-12 exports for provisional M17-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_06.v1 import (
    M1706_CONTRACT_VERSION,
    M1706_GATE,
    M1706_M1705_INPUT_MEDIA_TYPE,
    M1706_MAX_CANONICAL_REQUEST_BYTES,
    M1706_MODULE_ID,
    M1706_OUTPUT_MEDIA_TYPE,
    M1706_OWNER,
    M1706_PARENT,
    M1706_PROVISIONAL_ABI,
    M1706_SAFETY_CLASS,
    AdjudicateVariantPeptideDiscrepancyQueueRequest,
    AdjudicationRecord,
    DiscrepancyQueueEntry,
    ImmutableAuditEvent,
    QueueFinding,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
    VariantPeptideAdjudicationResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M17-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M1706_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "record",
    "queue-entry",
    "assignment",
    "audit-event",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": AdjudicateVariantPeptideDiscrepancyQueueRequest,
    "output": VariantPeptideAdjudicationResult,
    "record": AdjudicationRecord,
    "queue-entry": DiscrepancyQueueEntry,
    "assignment": ReviewerAssignment,
    "audit-event": ImmutableAuditEvent,
    "configuration": ReviewWorkspaceConfiguration,
    "finding": QueueFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M17-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1706_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1706_OWNER,
        "safetyClass": M1706_SAFETY_CLASS,
        "gate": M1706_GATE,
        "strict": True,
        "provisionalAbi": M1706_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1706_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1706_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1706_M1705_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "contrastive_protein_encoder",
        "alternateArchitecture": "proteome_autoencoder",
        "fallbackArchitecture": "proteome_autoencoder",
        "structuredDisagreementRequired": True,
        "reasonCodesRequired": True,
        "blindedReviewSupported": True,
        "escalationRequired": True,
        "immutableHistoryRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1706_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M17-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
