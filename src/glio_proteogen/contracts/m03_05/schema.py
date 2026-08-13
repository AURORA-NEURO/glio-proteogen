"""JSON Schema 2020-12 exports for M03-05 artifact detection."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_05.v1 import (
    M0305_CONTRACT_VERSION,
    M0305_MAX_CANONICAL_REQUEST_BYTES,
    M0305_MAX_CANONICAL_RESULT_BYTES,
    M0305_MODULE_ID,
    DetectProteinInferenceArtifactsRequest,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactEvidenceLedger,
    ProteinInferenceArtifactEvidenceUnit,
    ProteinInferenceArtifactFinding,
    ProteinInferenceArtifactPolicy,
    ProteinInferenceArtifactPosterior,
    ProteinInferenceArtifactProfile,
    ProteinInferenceArtifactQualityReceipt,
    ProteinInferenceArtifactSignalScore,
    ProteinInferenceArtifactThreshold,
    ProteinInferenceContaminationFlag,
    ProteinInferenceEvidenceExclusionMask,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-05:1.0.0"
CONTRACT_VERSION: Final = M0305_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "quality-receipt",
    "evidence-ledger",
    "evidence-unit",
    "signal-score",
    "posterior",
    "contamination-flag",
    "exclusion-mask",
    "finding",
]
_CONTRACTS: Final = {
    "request": DetectProteinInferenceArtifactsRequest,
    "output": ProteinInferenceArtifactDetectionResult,
    "policy": ProteinInferenceArtifactPolicy,
    "profile": ProteinInferenceArtifactProfile,
    "threshold": ProteinInferenceArtifactThreshold,
    "quality-receipt": ProteinInferenceArtifactQualityReceipt,
    "evidence-ledger": ProteinInferenceArtifactEvidenceLedger,
    "evidence-unit": ProteinInferenceArtifactEvidenceUnit,
    "signal-score": ProteinInferenceArtifactSignalScore,
    "posterior": ProteinInferenceArtifactPosterior,
    "contamination-flag": ProteinInferenceContaminationFlag,
    "exclusion-mask": ProteinInferenceEvidenceExclusionMask,
    "finding": ProteinInferenceArtifactFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict metadata-only Draft 2020-12 contract schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0305_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayloadInSchema": False,
        "reparsesRawPayload": False,
        "identityInference": False,
        "proteinInference": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
        "calibratedProbability": False,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0305_MAX_CANONICAL_REQUEST_BYTES
    if name == "output":
        metadata["maxResultBytes"] = M0305_MAX_CANONICAL_RESULT_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
