"""JSON Schema 2020-12 exports for provisional M20-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_06.v1 import (
    M2006_CONTRACT_VERSION,
    M2006_DOSSIER_SHA256,
    M2006_DOSSIER_SLICE,
    M2006_GATE,
    M2006_M2005_INPUT_MEDIA_TYPE,
    M2006_MAX_CANONICAL_REQUEST_BYTES,
    M2006_MODULE_ID,
    M2006_OUTPUT_MEDIA_TYPE,
    M2006_OWNER,
    M2006_PARENT,
    M2006_PROVISIONAL_ABI,
    M2006_SAFETY_CLASS,
    AdjudicateProteinSubtypeQueueRequest,
    AdjudicationRecord,
    DiscrepancyQueueEntry,
    ImmutableAuditEvent,
    ProteinSubtypeAdjudicationResult,
    QueueFinding,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M2006_CONTRACT_VERSION
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
    "request": AdjudicateProteinSubtypeQueueRequest,
    "output": ProteinSubtypeAdjudicationResult,
    "record": AdjudicationRecord,
    "queue-entry": DiscrepancyQueueEntry,
    "assignment": ReviewerAssignment,
    "audit-event": ImmutableAuditEvent,
    "configuration": ReviewWorkspaceConfiguration,
    "finding": QueueFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2006_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2006_OWNER,
        "safetyClass": M2006_SAFETY_CLASS,
        "gate": M2006_GATE,
        "strict": True,
        "provisionalAbi": M2006_PROVISIONAL_ABI,
        "dossierSha256": M2006_DOSSIER_SHA256,
        "dossierSlice": M2006_DOSSIER_SLICE,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2006_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2006_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2006_M2005_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "proteogenomic_vae",
        "alternateArchitecture": "proteogenomic_vae",
        "fallbackArchitecture": "proteome_autoencoder",
        "structuredDisagreementRequired": True,
        "reasonCodesRequired": True,
        "blindedReviewSupported": True,
        "escalationRequired": True,
        "resolutionRequired": True,
        "immutableHistoryRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2006_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M20-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
