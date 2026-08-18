"""JSON Schema 2020-12 exports for M03-06 protein-inference harmonization."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_06.v1 import (
    M0306_CONTRACT_VERSION,
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MODULE_ID,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceArtifactHarmonizationReceipt,
    ProteinInferenceArtifactUnitReceipt,
    ProteinInferenceHarmonizationFinding,
    ProteinInferenceHarmonizationPolicy,
    ProteinInferenceHarmonizationProfile,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceHarmonizedAnalysis,
    ProteinInferenceHarmonizedSupportValue,
    ProteinInferenceNormalizationStage,
    ProteinInferenceSupportInvariant,
    ProteinInferenceSupportLedger,
    ProteinInferenceSupportObservation,
    ProteinInferenceTransformationManifest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-06:1.0.0"
CONTRACT_VERSION: Final = M0306_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "stage",
    "artifact-receipt",
    "unit-receipt",
    "support-ledger",
    "observation",
    "invariant",
    "analysis",
    "value",
    "transformation-manifest",
    "finding",
]
_CONTRACTS: Final = {
    "request": HarmonizeProteinInferenceSupportRequest,
    "output": ProteinInferenceHarmonizationResult,
    "policy": ProteinInferenceHarmonizationPolicy,
    "profile": ProteinInferenceHarmonizationProfile,
    "stage": ProteinInferenceNormalizationStage,
    "artifact-receipt": ProteinInferenceArtifactHarmonizationReceipt,
    "unit-receipt": ProteinInferenceArtifactUnitReceipt,
    "support-ledger": ProteinInferenceSupportLedger,
    "observation": ProteinInferenceSupportObservation,
    "invariant": ProteinInferenceSupportInvariant,
    "analysis": ProteinInferenceHarmonizedAnalysis,
    "value": ProteinInferenceHarmonizedSupportValue,
    "transformation-manifest": ProteinInferenceTransformationManifest,
    "finding": ProteinInferenceHarmonizationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict fixed-point Draft 2020-12 contract schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0306_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "fixedPointScale": 1_000_000,
        "rawPayloadInSchema": False,
        "reparsesRawPayload": False,
        "identityInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "isoformInference": False,
        "gliomaSpecificBiologyInference": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
        "abundanceInference": False,
        "calibratedProbability": False,
        "opaqueIdentifierPattern": (
            "^(request|policy|profile|ledger|unit|anchor|group|level|invariant|stage|evidence|reviewer)"
            r"\.[0-9a-f]{64}$"
        ),
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0306_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
