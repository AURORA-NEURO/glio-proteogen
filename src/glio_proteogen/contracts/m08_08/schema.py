"""JSON Schema 2020-12 exports for provisional M08-08 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_08.v1 import (
    M0808_CALIBRATION_MEDIA_TYPE,
    M0808_CONTRACT_VERSION,
    M0808_GATE,
    M0808_MAX_CANONICAL_REQUEST_BYTES,
    M0808_MODULE_ID,
    M0808_OUTPUT_MEDIA_TYPE,
    M0808_OWNER,
    M0808_PARENT,
    M0808_PROVISIONAL_ABI,
    M0808_SAFETY_CLASS,
    M0808_UNCERTAINTY_MEDIA_TYPE,
    EvidenceBundle,
    ExplanationAssumption,
    ExplanationDiagnostic,
    ExplanationObject,
    PublishedEvidenceItem,
    PublishTranscriptProteinEvidenceRequest,
    PublishTranscriptProteinEvidenceResult,
    ReconstructionStep,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-08:0.1.0-provisional"
CONTRACT_VERSION: Final = M0808_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "bundle",
    "explanation",
    "evidence-item",
    "assumption",
    "diagnostic",
    "reconstruction-step",
]
_CONTRACTS: Final = {
    "request": PublishTranscriptProteinEvidenceRequest,
    "output": PublishTranscriptProteinEvidenceResult,
    "bundle": EvidenceBundle,
    "explanation": ExplanationObject,
    "evidence-item": PublishedEvidenceItem,
    "assumption": ExplanationAssumption,
    "diagnostic": ExplanationDiagnostic,
    "reconstruction-step": ReconstructionStep,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-08 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0808_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0808_OWNER,
        "safetyClass": M0808_SAFETY_CLASS,
        "gate": M0808_GATE,
        "strict": True,
        "provisionalAbi": M0808_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0808_PARENT,
        "unsupportedToNegative": False,
        "sourcesRequired": True,
        "assumptionsRequired": True,
        "counterEvidenceRequired": True,
        "reconstructionRequired": True,
        "outputMediaType": M0808_OUTPUT_MEDIA_TYPE,
        "calibrationInputMediaType": M0808_CALIBRATION_MEDIA_TYPE,
        "uncertaintyInputMediaType": M0808_UNCERTAINTY_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0808_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
