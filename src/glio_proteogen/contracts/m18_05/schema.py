"""JSON Schema 2020-12 exports for provisional M18-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_05.v1 import (
    M1805_CONTRACT_VERSION,
    M1805_GATE,
    M1805_M1804_INPUT_MEDIA_TYPE,
    M1805_MAX_CANONICAL_REQUEST_BYTES,
    M1805_MODULE_ID,
    M1805_OUTPUT_MEDIA_TYPE,
    M1805_OWNER,
    M1805_PARENT,
    M1805_PROVISIONAL_ABI,
    M1805_SAFETY_CLASS,
    BiomarkerPanelReviewWorkspaceResult,
    HumanReviewWorkspace,
    PresentBiomarkerPanelReviewWorkspaceRequest,
    WorkspaceConfiguration,
    WorkspaceFinding,
    WorkspaceSection,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-05:0.1.0-provisional"
CONTRACT_VERSION: Final = M1805_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "workspace",
    "section",
    "configuration",
    "finding",
]
_CONTRACTS: Final = {
    "request": PresentBiomarkerPanelReviewWorkspaceRequest,
    "output": BiomarkerPanelReviewWorkspaceResult,
    "workspace": HumanReviewWorkspace,
    "section": WorkspaceSection,
    "configuration": WorkspaceConfiguration,
    "finding": WorkspaceFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1805_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1805_OWNER,
        "safetyClass": M1805_SAFETY_CLASS,
        "gate": M1805_GATE,
        "strict": True,
        "provisionalAbi": M1805_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1805_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1805_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1805_M1804_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "semi_supervised_classifier",
        "alternateArchitecture": "mixture_of_experts_subtype",
        "fallbackArchitecture": "latent_class_proteotype",
        "taskViewsRequired": True,
        "evidenceSummaryRequired": True,
        "uncertaintyVisible": True,
        "discrepanciesVisible": True,
        "provenanceVisible": True,
        "safeDefaultOrderingRequired": True,
        "automationBiasMitigationRequired": True,
        "humanReviewRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1805_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all six provisional M18-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
