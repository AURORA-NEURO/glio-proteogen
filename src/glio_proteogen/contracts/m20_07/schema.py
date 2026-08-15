"""JSON Schema 2020-12 exports for provisional M20-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_07.v1 import (
    M2007_CONTRACT_VERSION,
    M2007_GATE,
    M2007_M2006_INPUT_MEDIA_TYPE,
    M2007_MAX_CANONICAL_REQUEST_BYTES,
    M2007_MODULE_ID,
    M2007_OUTPUT_MEDIA_TYPE,
    M2007_OWNER,
    M2007_PARENT,
    M2007_PROVISIONAL_ABI,
    M2007_SAFETY_CLASS,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportField,
    ExportFinding,
    ExportOwnershipBinding,
    ExportProteinSubtypeDownstreamContractRequest,
    ProteinSubtypeDownstreamExportResult,
    SignedContractEnvelope,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2007_CONTRACT_VERSION
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
    "request": ExportProteinSubtypeDownstreamContractRequest,
    "output": ProteinSubtypeDownstreamExportResult,
    "contract": DownstreamContractObject,
    "field": ExportField,
    "signature": SignedContractEnvelope,
    "configuration": DownstreamExportConfiguration,
    "finding": ExportFinding,
    "ownership": ExportOwnershipBinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2007_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2007_OWNER,
        "safetyClass": M2007_SAFETY_CLASS,
        "gate": M2007_GATE,
        "strict": True,
        "provisionalAbi": M2007_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M2007_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2007_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2007_M2006_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "longitudinal_state_space",
        "alternateArchitecture": "longitudinal_state_space",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M2007_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M20-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
