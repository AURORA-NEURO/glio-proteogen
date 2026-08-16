"""JSON Schema 2020-12 exports for M03-04 quality computation."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_04.v1 import (
    M0304_CONTRACT_VERSION,
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    M0304_MODULE_ID,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityFactLedger,
    ProteinInferenceQualityFinding,
    ProteinInferenceQualityMetricResult,
    ProteinInferenceQualityPolicy,
    ProteinInferenceQualityResult,
    ProteinInferenceQualityThreshold,
    ProteinInferenceRawQualityReceipt,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-04:1.0.0"
CONTRACT_VERSION: Final = M0304_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "raw-quality-receipt",
    "fact-ledger",
    "metric",
    "finding",
]
_CONTRACTS: Final = {
    "request": ComputeProteinInferenceQualityRequest,
    "output": ProteinInferenceQualityResult,
    "policy": ProteinInferenceQualityPolicy,
    "profile": ProteinInferenceAssayQualityProfile,
    "threshold": ProteinInferenceQualityThreshold,
    "raw-quality-receipt": ProteinInferenceRawQualityReceipt,
    "fact-ledger": ProteinInferenceQualityFactLedger,
    "metric": ProteinInferenceQualityMetricResult,
    "finding": ProteinInferenceQualityFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict metadata-only Draft 2020-12 contract schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0304_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayloadInSchema": False,
        "reparsesRawPayload": False,
        "identityInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "isoformInference": False,
        "gliomaSpecificBiologyInference": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0304_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
