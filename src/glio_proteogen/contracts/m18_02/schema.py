"""JSON Schema 2020-12 exports for provisional M18-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m18_02.v1 import (
    M1802_CONTRACT_VERSION,
    M1802_GATE,
    M1802_M1801_INPUT_MEDIA_TYPE,
    M1802_MAX_CANONICAL_REQUEST_BYTES,
    M1802_MODULE_ID,
    M1802_OUTPUT_MEDIA_TYPE,
    M1802_OWNER,
    M1802_PARENT,
    M1802_PROVISIONAL_ABI,
    M1802_SAFETY_CLASS,
    AlignBiomarkerPanelSourcesRequest,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentFinding,
    AlignmentObservation,
    BiomarkerPanelAlignmentResult,
    DiscrepancyMapEntry,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M18-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1802_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "aligned-bundle",
    "configuration",
    "observation",
    "discrepancy",
    "finding",
]
_CONTRACTS: Final = {
    "request": AlignBiomarkerPanelSourcesRequest,
    "output": BiomarkerPanelAlignmentResult,
    "aligned-bundle": AlignedEvidenceBundle,
    "configuration": AlignmentConfiguration,
    "observation": AlignmentObservation,
    "discrepancy": DiscrepancyMapEntry,
    "finding": AlignmentFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M18-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1802_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1802_OWNER,
        "safetyClass": M1802_SAFETY_CLASS,
        "gate": M1802_GATE,
        "strict": True,
        "provisionalAbi": M1802_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1802_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1802_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M1802_M1801_INPUT_MEDIA_TYPE,
        "primaryArchitecture": "cn_to_protein_regression",
        "alternateArchitecture": "hierarchical_multilevel_regression",
        "fallbackArchitecture": "cn_to_protein_regression",
        "sampleTimeTerritoryAlignmentRequired": True,
        "analyteModalityReferenceAlignmentRequired": True,
        "biologicalContextAlignmentRequired": True,
        "conflictsPreserved": True,
        "discrepancyMapRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1802_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M18-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
