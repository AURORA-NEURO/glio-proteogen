"""JSON Schema 2020-12 exports for provisional M18-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_07.v1 import (
    M1807_CONTRACT_VERSION,
    M1807_GATE,
    M1807_M1806_INPUT_MEDIA_TYPE,
    M1807_MAX_CANONICAL_REQUEST_BYTES,
    M1807_MODULE_ID,
    M1807_OUTPUT_MEDIA_TYPE,
    M1807_OWNER,
    M1807_PARENT,
    M1807_PROVISIONAL_ABI,
    M1807_SAFETY_CLASS,
    BiomarkerPanelDownstreamExportResult,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportBiomarkerPanelDownstreamContractRequest,
    ExportField,
    ExportFinding,
    ExportOwnershipBinding,
    SignedContractEnvelope,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-07:0.1.0-provisional"
CONTRACT_VERSION: Final = M1807_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "contract",
    "field",
    "signature",
    "configuration",
    "finding",
    "ownership",
]
_CONTRACTS: Final = {
    "request": ExportBiomarkerPanelDownstreamContractRequest,
    "output": BiomarkerPanelDownstreamExportResult,
    "contract": DownstreamContractObject,
    "field": ExportField,
    "signature": SignedContractEnvelope,
    "configuration": DownstreamExportConfiguration,
    "finding": ExportFinding,
    "ownership": ExportOwnershipBinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1807_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1807_OWNER,
        "safetyClass": M1807_SAFETY_CLASS,
        "gate": M1807_GATE,
        "strict": True,
        "provisionalAbi": M1807_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1807_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1807_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1807_M1806_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "spatial_proteotype_field",
        "alternateArchitecture": "recurrence_transition",
        "fallbackArchitecture": "spatial_proteotype_field",
        "documentedFieldsOnly": True,
        "versionedCompatibilityRequired": True,
        "immutableExportRequired": True,
        "ownershipSemanticsRequired": True,
        "consentAware": True,
        "supportAware": True,
        "signatureRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1807_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M18-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
