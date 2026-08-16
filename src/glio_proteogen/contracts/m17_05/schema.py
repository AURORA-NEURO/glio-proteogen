"""JSON Schema 2020-12 exports for provisional M17-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_05.v1 import (
    M1705_CONTRACT_VERSION,
    M1705_GATE,
    M1705_MAX_CANONICAL_REQUEST_BYTES,
    M1705_MODULE_ID,
    M1705_OUTPUT_MEDIA_TYPE,
    M1705_OWNER,
    M1705_PARENT,
    M1705_PROVISIONAL_ABI,
    M1705_SAFETY_CLASS,
    HumanReviewWorkspace,
    NextAction,
    PresentationConfiguration,
    PresentationPolicy,
    PresentVariantPeptideHumanReviewWorkspaceRequest,
    ReviewItem,
    VariantPeptideHumanReviewWorkspaceResult,
    WorkflowFinding,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M17-05:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1705_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "review-item",
    "next-action",
    "workspace",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": PresentVariantPeptideHumanReviewWorkspaceRequest,
    "output": VariantPeptideHumanReviewWorkspaceResult,
    "review-item": ReviewItem,
    "next-action": NextAction,
    "workspace": HumanReviewWorkspace,
    "configuration": PresentationConfiguration,
    "policy": PresentationPolicy,
    "finding": WorkflowFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M17-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1705_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1705_OWNER,
        "safetyClass": M1705_SAFETY_CLASS,
        "gate": M1705_GATE,
        "strict": True,
        "provisionalAbi": M1705_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "mutationRelabeling": False,
        "disagreementErasure": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M1705_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1705_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "event_driven_reliability_aware_orchestration",
        "alternateArchitecture": "typed_service_oriented_integration_open_set_proteotype",
        "fallbackArchitecture": "signed_human_review_package_latent_class_proteotype",
        "taskSpecificViewsRequired": True,
        "evidenceSummaryRequired": True,
        "uncertaintyRequired": True,
        "discrepancyReviewRequired": True,
        "provenanceRequired": True,
        "safeDefaultOrderingRequired": True,
        "automationBiasGuardRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1705_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M17-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
