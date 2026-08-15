"""JSON Schema 2020-12 exports for provisional M16-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_07.v1 import (
    M1607_CONTRACT_VERSION,
    M1607_GATE,
    M1607_MAX_CANONICAL_REQUEST_BYTES,
    M1607_MODULE_ID,
    M1607_OUTPUT_MEDIA_TYPE,
    M1607_OWNER,
    M1607_PARENT,
    M1607_PROVISIONAL_ABI,
    M1607_SAFETY_CLASS,
    CompatibilityReport,
    DownstreamField,
    ExportConfiguration,
    ExportFinding,
    ExportPolicy,
    ExportProteinRnaDiscordanceDownstreamContractRequest,
    ProteinRnaDiscordanceDownstreamExportResult,
    SignedDownstreamContract,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M16-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M1607_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "field",
    "contract",
    "compatibility-report",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": ExportProteinRnaDiscordanceDownstreamContractRequest,
    "output": ProteinRnaDiscordanceDownstreamExportResult,
    "field": DownstreamField,
    "contract": SignedDownstreamContract,
    "compatibility-report": CompatibilityReport,
    "configuration": ExportConfiguration,
    "policy": ExportPolicy,
    "finding": ExportFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M16-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1607_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1607_OWNER,
        "safetyClass": M1607_SAFETY_CLASS,
        "gate": M1607_GATE,
        "strict": True,
        "provisionalAbi": M1607_PROVISIONAL_ABI,
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
        "parentTarget": M1607_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1607_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m16-04+json",
        "primaryArchitecture": "event_driven_reliability_aware_orchestration",
        "alternateArchitecture": "typed_service_oriented_integration_clone_linked_evolution",
        "fallbackArchitecture": "signed_human_review_package_spatial_proteotype_field",
        "versionedImmutableRequired": True,
        "consentAwareRequired": True,
        "supportAwareRequired": True,
        "ownershipSemanticsRequired": True,
        "compatibilitySemanticsRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1607_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M16-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
