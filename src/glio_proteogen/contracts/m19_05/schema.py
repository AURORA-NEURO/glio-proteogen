"""JSON Schema 2020-12 exports for provisional M19-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_05.v1 import (
    M1905_CONTRACT_VERSION,
    M1905_DOSSIER_SHA256,
    M1905_DOSSIER_SLICE,
    M1905_EVIDENCE_CLAIM,
    M1905_GATE,
    M1905_M1904_RESULT_MEDIA_TYPE,
    M1905_MAX_CANONICAL_REQUEST_BYTES,
    M1905_MODULE_ID,
    M1905_OUTPUT_MEDIA_TYPE,
    M1905_OWNER,
    M1905_PARENT,
    M1905_PROHIBITED_CLAIM_TERMS,
    M1905_PROVISIONAL_ABI,
    M1905_SAFETY_CLASS,
    HumanReviewWorkspace,
    NextAction,
    PresentationConfiguration,
    PresentationPolicy,
    PresentProteotypeHumanReviewWorkspaceRequest,
    ProteotypeHumanReviewWorkspaceResult,
    ReviewItem,
    ViewKind,
    WorkflowFinding,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M1905_CONTRACT_VERSION
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
    "request": PresentProteotypeHumanReviewWorkspaceRequest,
    "output": ProteotypeHumanReviewWorkspaceResult,
    "review-item": ReviewItem,
    "next-action": NextAction,
    "workspace": HumanReviewWorkspace,
    "configuration": PresentationConfiguration,
    "policy": PresentationPolicy,
    "finding": WorkflowFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1905_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "dossierSha256": M1905_DOSSIER_SHA256,
        "dossierSlice": M1905_DOSSIER_SLICE,
        "owner": M1905_OWNER,
        "safetyClass": M1905_SAFETY_CLASS,
        "gate": M1905_GATE,
        "strict": True,
        "provisionalAbi": M1905_PROVISIONAL_ABI,
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
        "parentTarget": M1905_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1905_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1905_M1904_RESULT_MEDIA_TYPE,
        "primaryArchitecture": "event_driven_reliability_aware_orchestration_open_set_proteotype",
        "alternateArchitecture": "typed_service_integration_semi_supervised_classifier",
        "fallbackArchitecture": "signed_human_review_package_latent_class_proteotype",
        "taskSpecificViewsRequired": True,
        "evidenceSummaryRequired": True,
        "uncertaintyRequired": True,
        "discrepancyReviewRequired": True,
        "provenanceRequired": True,
        "safeDefaultOrderingRequired": True,
        "taskSpecificViews": [kind.value for kind in ViewKind],
        "evidenceClaim": M1905_EVIDENCE_CLAIM,
        "automationBiasGuardRequired": True,
        "explicitAbstentionRequired": True,
        "prohibitedClaimTerms": list(M1905_PROHIBITED_CLAIM_TERMS),
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1905_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M19-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
