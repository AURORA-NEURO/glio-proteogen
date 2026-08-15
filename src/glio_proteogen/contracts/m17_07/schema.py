"""JSON Schema 2020-12 exports for provisional M17-07 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_07.v1 import (
    M1707_CONTRACT_VERSION,
    M1707_GATE,
    M1707_M1706_INPUT_MEDIA_TYPE,
    M1707_MAX_CANONICAL_REQUEST_BYTES,
    M1707_MODULE_ID,
    M1707_OUTPUT_MEDIA_TYPE,
    M1707_OWNER,
    M1707_PARENT,
    M1707_PROVISIONAL_ABI,
    M1707_SAFETY_CLASS,
    DownstreamContractObject,
    DownstreamExportConfiguration,
    ExportField,
    ExportFinding,
    ExportOwnershipBinding,
    ExportVariantPeptideDownstreamContractRequest,
    SignedContractEnvelope,
    VariantPeptideDownstreamExportResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M17-07:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1707_CONTRACT_VERSION
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
    "request": ExportVariantPeptideDownstreamContractRequest,
    "output": VariantPeptideDownstreamExportResult,
    "contract": DownstreamContractObject,
    "field": ExportField,
    "signature": SignedContractEnvelope,
    "configuration": DownstreamExportConfiguration,
    "finding": ExportFinding,
    "ownership": ExportOwnershipBinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M17-07 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1707_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1707_OWNER,
        "safetyClass": M1707_SAFETY_CLASS,
        "gate": M1707_GATE,
        "strict": True,
        "provisionalAbi": M1707_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1707_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1707_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1707_M1706_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "clone_linked_protein_evolution",
        "alternateArchitecture": "territory_conditioned_subtype",
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
        schema["x-glio-contract"]["maxRequestBytes"] = M1707_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M17-07 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
