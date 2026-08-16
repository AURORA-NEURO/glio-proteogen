"""JSON Schema 2020-12 exports for provisional M16-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m16_02.v1 import (
    M1602_CONTRACT_VERSION,
    M1602_GATE,
    M1602_MAX_CANONICAL_REQUEST_BYTES,
    M1602_MODULE_ID,
    M1602_OUTPUT_MEDIA_TYPE,
    M1602_OWNER,
    M1602_PARENT,
    M1602_PROVISIONAL_ABI,
    M1602_SAFETY_CLASS,
    AlignedEvidenceBundle,
    AlignmentConfiguration,
    AlignmentDiagnostic,
    AlignmentLink,
    DiscrepancyRecord,
    ProteinRnaDiscordanceAlignmentResult,
    ReconcileCrossSourceAlignmentRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M16-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1602_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "bundle",
    "alignment-link",
    "discrepancy",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": ReconcileCrossSourceAlignmentRequest,
    "output": ProteinRnaDiscordanceAlignmentResult,
    "bundle": AlignedEvidenceBundle,
    "alignment-link": AlignmentLink,
    "discrepancy": DiscrepancyRecord,
    "configuration": AlignmentConfiguration,
    "diagnostic": AlignmentDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M16-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1602_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1602_OWNER,
        "safetyClass": M1602_SAFETY_CLASS,
        "gate": M1602_GATE,
        "strict": True,
        "provisionalAbi": M1602_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1602_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1602_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m16-01+json",
        "alignmentDimensions": [
            "sample",
            "time",
            "territory",
            "analyte",
            "modality",
            "reference",
            "biological_context",
        ],
        "conflictDetectionRequired": True,
        "discrepanciesRemainExplicit": True,
        "humanReviewForCriticalDiscrepancy": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1602_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M16-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
