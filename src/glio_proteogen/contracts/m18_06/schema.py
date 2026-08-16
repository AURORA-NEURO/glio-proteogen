"""JSON Schema 2020-12 exports for provisional M18-06 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_06.v1 import (
    M1806_CONTRACT_VERSION,
    M1806_DOSSIER_SHA256,
    M1806_DOSSIER_SLICE,
    M1806_GATE,
    M1806_M1805_INPUT_MEDIA_TYPE,
    M1806_MAX_CANONICAL_REQUEST_BYTES,
    M1806_MODULE_ID,
    M1806_OUTPUT_MEDIA_TYPE,
    M1806_OWNER,
    M1806_PARENT,
    M1806_PROVISIONAL_ABI,
    M1806_SAFETY_CLASS,
    AdjudicateBiomarkerPanelQueueRequest,
    AdjudicationRecord,
    BiomarkerPanelAdjudicationResult,
    DiscrepancyQueueEntry,
    ImmutableAuditEvent,
    QueueFinding,
    ReviewerAssignment,
    ReviewWorkspaceConfiguration,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-06:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1806_CONTRACT_VERSION
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
    "request": AdjudicateBiomarkerPanelQueueRequest,
    "output": BiomarkerPanelAdjudicationResult,
    "record": AdjudicationRecord,
    "queue-entry": DiscrepancyQueueEntry,
    "assignment": ReviewerAssignment,
    "audit-event": ImmutableAuditEvent,
    "configuration": ReviewWorkspaceConfiguration,
    "finding": QueueFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-06 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1806_MODULE_ID,
        "dossierSha256": M1806_DOSSIER_SHA256,
        "dossierSlice": M1806_DOSSIER_SLICE,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1806_OWNER,
        "safetyClass": M1806_SAFETY_CLASS,
        "gate": M1806_GATE,
        "strict": True,
        "provisionalAbi": M1806_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M1806_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1806_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1806_M1805_INPUT_MEDIA_TYPE,
        "primaryArchitecture": (
            "event_driven_reliability_aware_orchestration_masked_proteome_foundation_model"
        ),
        "alternateArchitecture": "typed_service_integration_cross_attention_genome_protein",
        "fallbackArchitecture": "signed_human_review_package_proteome_autoencoder",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1806_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M18-06 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
