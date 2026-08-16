"""JSON Schema 2020-12 exports for provisional M19-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_06.v1 import (
    M1906_CONTRACT_VERSION,
    M1906_DOSSIER_SHA256,
    M1906_DOSSIER_SLICE,
    M1906_GATE,
    M1906_M1905_INPUT_MEDIA_TYPE,
    M1906_MAX_CANONICAL_REQUEST_BYTES,
    M1906_MODULE_ID,
    M1906_OUTPUT_MEDIA_TYPE,
    M1906_OWNER,
    M1906_PARENT,
    M1906_PROVISIONAL_ABI,
    M1906_SAFETY_CLASS,
    AdjudicateProteotypeQueueRequest,
    AdjudicationRecord,
    DiscrepancyQueueEntry,
    ImmutableAuditEvent,
    ProteotypeAdjudicationResult,
    QueueFinding,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-06:0.1.0-provisional"
CONTRACT_VERSION: Final = M1906_CONTRACT_VERSION
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
    "request": AdjudicateProteotypeQueueRequest,
    "output": ProteotypeAdjudicationResult,
    "record": AdjudicationRecord,
    "queue-entry": DiscrepancyQueueEntry,
    "assignment": ReviewerAssignment,
    "audit-event": ImmutableAuditEvent,
    "configuration": ReviewWorkspaceConfiguration,
    "finding": QueueFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1906_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1906_OWNER,
        "safetyClass": M1906_SAFETY_CLASS,
        "gate": M1906_GATE,
        "strict": True,
        "provisionalAbi": M1906_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "dossierSha256": M1906_DOSSIER_SHA256,
        "dossierSlice": M1906_DOSSIER_SLICE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "genericAllOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M1906_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1906_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1906_M1905_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "proteome_autoencoder",
        "alternateArchitecture": "masked_proteome_foundation_model",
        "fallbackArchitecture": "signed_human_review_package",
        "structuredDisagreementRequired": True,
        "reasonCodesRequired": True,
        "blindedReviewSupported": True,
        "escalationRequired": True,
        "resolutionRequired": True,
        "immutableHistoryRequired": True,
        "contiguousAuditSequenceRequired": True,
        "chainedAuditEventDigestRequired": True,
        "criticalTwoReviewerMinimum": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1906_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M19-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
