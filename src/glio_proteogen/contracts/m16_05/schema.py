"""JSON Schema 2020-12 exports for provisional M16-05 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_05.v1 import (
    M1605_CONTRACT_VERSION,
    M1605_GATE,
    M1605_MAX_CANONICAL_REQUEST_BYTES,
    M1605_MODULE_ID,
    M1605_OUTPUT_MEDIA_TYPE,
    M1605_OWNER,
    M1605_PARENT,
    M1605_PROVISIONAL_ABI,
    M1605_SAFETY_CLASS,
    HumanReviewWorkspace,
    PresentProteinRnaReviewWorkspaceRequest,
    ProteinRnaDiscordanceReviewWorkspaceResult,
    WorkspaceConfiguration,
    WorkspaceDiagnostic,
    WorkspaceItem,
    WorkspaceView,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M16-05:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1605_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "workspace",
    "view",
    "item",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": PresentProteinRnaReviewWorkspaceRequest,
    "output": ProteinRnaDiscordanceReviewWorkspaceResult,
    "workspace": HumanReviewWorkspace,
    "view": WorkspaceView,
    "item": WorkspaceItem,
    "configuration": WorkspaceConfiguration,
    "diagnostic": WorkspaceDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M16-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1605_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1605_OWNER,
        "safetyClass": M1605_SAFETY_CLASS,
        "gate": M1605_GATE,
        "strict": True,
        "provisionalAbi": M1605_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1605_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1605_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m16-04+json",
        "taskSpecificViewsRequired": True,
        "evidenceSummaryRequired": True,
        "uncertaintyVisible": True,
        "discrepanciesVisible": True,
        "provenanceVisible": True,
        "nextActionVisible": True,
        "safeDefaultOrderingRequired": True,
        "automationBiasControls": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1605_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M16-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
