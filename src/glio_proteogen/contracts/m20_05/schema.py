"""JSON Schema 2020-12 exports for provisional M20-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_05.v1 import (
    M2005_CONTRACT_VERSION,
    M2005_GATE,
    M2005_M2004_RESULT_MEDIA_TYPE,
    M2005_MAX_CANONICAL_REQUEST_BYTES,
    M2005_MODULE_ID,
    M2005_OUTPUT_MEDIA_TYPE,
    M2005_OWNER,
    M2005_PARENT,
    M2005_PROVISIONAL_ABI,
    M2005_SAFETY_CLASS,
    HumanReviewWorkspace,
    NextAction,
    PresentationConfiguration,
    PresentationPolicy,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ProteinSubtypeHumanReviewWorkspaceResult,
    ReviewItem,
    WorkflowFinding,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-05:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2005_CONTRACT_VERSION
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
    "request": PresentProteinSubtypeHumanReviewWorkspaceRequest,
    "output": ProteinSubtypeHumanReviewWorkspaceResult,
    "review-item": ReviewItem,
    "next-action": NextAction,
    "workspace": HumanReviewWorkspace,
    "configuration": PresentationConfiguration,
    "policy": PresentationPolicy,
    "finding": WorkflowFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2005_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2005_OWNER,
        "safetyClass": M2005_SAFETY_CLASS,
        "gate": M2005_GATE,
        "strict": True,
        "provisionalAbi": M2005_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "disagreementErasure": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M2005_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2005_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2005_M2004_RESULT_MEDIA_TYPE,
        "primaryArchitecture": (
            "event_driven_reliability_aware_orchestration_latent_class_proteotype"
        ),
        "alternateArchitecture": "typed_service_integration_latent_class_proteotype",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2005_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M20-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
