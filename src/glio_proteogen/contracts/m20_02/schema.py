"""JSON Schema 2020-12 exports for provisional M20-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m20_02.v1 import (
    M2002_CONTRACT_VERSION,
    M2002_GATE,
    M2002_M2001_INPUT_MEDIA_TYPE,
    M2002_MAX_CANONICAL_REQUEST_BYTES,
    M2002_MODULE_ID,
    M2002_OUTPUT_MEDIA_TYPE,
    M2002_OWNER,
    M2002_PARENT,
    M2002_PROVISIONAL_ABI,
    M2002_SAFETY_CLASS,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentFinding,
    AlignmentObservation,
    AlignProteinSubtypeSourcesRequest,
    DiscrepancyMapEntry,
    ProteinSubtypeAlignmentResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M20-02:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M2002_CONTRACT_VERSION
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
    "request": AlignProteinSubtypeSourcesRequest,
    "output": ProteinSubtypeAlignmentResult,
    "aligned-bundle": AlignedEvidenceBundle,
    "configuration": AlignmentConfiguration,
    "observation": AlignmentObservation,
    "discrepancy": DiscrepancyMapEntry,
    "finding": AlignmentFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M20-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M2002_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M2002_OWNER,
        "safetyClass": M2002_SAFETY_CLASS,
        "gate": M2002_GATE,
        "strict": True,
        "provisionalAbi": M2002_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "upstreamMutation": False,
        "identityInference": False,
        "consentInference": False,
        "disagreementErasure": False,
        "parentTarget": M2002_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M2002_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": M2002_M2001_INPUT_MEDIA_TYPE,
        "primaryArchitecture": (
            "event_driven_reliability_aware_orchestration_elastic_net_consequence_model"
        ),
        "alternateArchitecture": "typed_service_integration_elastic_net_consequence_model",
        "fallbackArchitecture": "signed_human_review_package_cn_to_protein_regression",
        "sampleTimeTerritoryAlignmentRequired": True,
        "analyteModalityReferenceAlignmentRequired": True,
        "biologicalContextAlignmentRequired": True,
        "conflictsPreserved": True,
        "discrepancyMapRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M2002_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M20-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
