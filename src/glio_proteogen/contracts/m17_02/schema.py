"""JSON Schema 2020-12 exports for provisional M17-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m17_02.v1 import (
    M1702_CONTRACT_VERSION,
    M1702_GATE,
    M1702_MAX_CANONICAL_REQUEST_BYTES,
    M1702_MODULE_ID,
    M1702_OUTPUT_MEDIA_TYPE,
    M1702_OWNER,
    M1702_PARENT,
    M1702_PROVISIONAL_ABI,
    M1702_SAFETY_CLASS,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentFinding,
    AlignmentPolicy,
    AlignVariantPeptideCrossSourceEvidenceRequest,
    Discrepancy,
    SourceObservation,
    VariantPeptideCrossSourceAlignmentResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M17-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1702_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "observation",
    "discrepancy",
    "bundle",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": AlignVariantPeptideCrossSourceEvidenceRequest,
    "output": VariantPeptideCrossSourceAlignmentResult,
    "observation": SourceObservation,
    "discrepancy": Discrepancy,
    "bundle": AlignedEvidenceBundle,
    "configuration": AlignmentConfiguration,
    "policy": AlignmentPolicy,
    "finding": AlignmentFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M17-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1702_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1702_OWNER,
        "safetyClass": M1702_SAFETY_CLASS,
        "gate": M1702_GATE,
        "strict": True,
        "provisionalAbi": M1702_PROVISIONAL_ABI,
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
        "parentTarget": M1702_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1702_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "event_driven_reliability_aware_orchestration",
        "alternateArchitecture": "typed_service_oriented_integration_transcript_protein_residual",
        "fallbackArchitecture": "signed_human_review_package_cn_protein_regression",
        "alignmentAxesRequired": [
            "sample",
            "time",
            "territory",
            "analyte",
            "modality",
            "reference",
            "biological_context",
        ],
        "conflictDetectionRequired": True,
        "conflictPreservationRequired": True,
        "discrepancyMapRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1702_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M17-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
