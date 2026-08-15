"""JSON Schema 2020-12 exports for provisional M19-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m19_07.v1 import (
    M1907_CONTRACT_VERSION,
    M1907_GATE,
    M1907_M1906_INPUT_MEDIA_TYPE,
    M1907_MAX_CANONICAL_REQUEST_BYTES,
    M1907_MODULE_ID,
    M1907_OUTPUT_MEDIA_TYPE,
    M1907_OWNER,
    M1907_PARENT,
    M1907_PROVISIONAL_ABI,
    M1907_SAFETY_CLASS,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportField,
    ExportFinding,
    ExportOwnershipBinding,
    ExportProteotypeDownstreamContractRequest,
    ProteotypeDownstreamExportResult,
    SignedContractEnvelope,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M19-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1907_CONTRACT_VERSION
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
    "request": ExportProteotypeDownstreamContractRequest,
    "output": ProteotypeDownstreamExportResult,
    "contract": DownstreamContractObject,
    "field": ExportField,
    "signature": SignedContractEnvelope,
    "configuration": DownstreamExportConfiguration,
    "finding": ExportFinding,
    "ownership": ExportOwnershipBinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M19-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1907_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1907_OWNER,
        "safetyClass": M1907_SAFETY_CLASS,
        "gate": M1907_GATE,
        "strict": True,
        "provisionalAbi": M1907_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1907_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1907_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1907_M1906_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "territory_conditioned_subtype",
        "alternateArchitecture": "spatial_proteotype_field",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1907_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M19-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
