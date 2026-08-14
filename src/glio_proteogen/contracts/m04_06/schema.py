"""JSON Schema 2020-12 exports for M04-06 proteoform harmonization."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_06.v1 import (
    M0406_CONTRACT_VERSION,
    M0406_MAX_CANONICAL_REQUEST_BYTES,
    M0406_MODULE_ID,
    HarmonizeProteoformAnalysisRequest,
    ProteoformArtifactHarmonizationReceipt,
    ProteoformArtifactTargetReceipt,
    ProteoformHarmonizationFinding,
    ProteoformHarmonizationPolicy,
    ProteoformHarmonizationProfile,
    ProteoformHarmonizationResult,
    ProteoformHarmonizedAnalysis,
    ProteoformHarmonizedSupportValue,
    ProteoformNormalizationStage,
    ProteoformSupportInvariant,
    ProteoformSupportLedger,
    ProteoformSupportObservation,
    ProteoformTransformationManifest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-06:1.0.0"
CONTRACT_VERSION: Final = M0406_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "stage",
    "artifact-receipt",
    "target-receipt",
    "support-ledger",
    "observation",
    "invariant",
    "analysis",
    "value",
    "transformation-manifest",
    "finding",
]
_CONTRACTS: Final = {
    "request": HarmonizeProteoformAnalysisRequest,
    "output": ProteoformHarmonizationResult,
    "policy": ProteoformHarmonizationPolicy,
    "profile": ProteoformHarmonizationProfile,
    "stage": ProteoformNormalizationStage,
    "artifact-receipt": ProteoformArtifactHarmonizationReceipt,
    "target-receipt": ProteoformArtifactTargetReceipt,
    "support-ledger": ProteoformSupportLedger,
    "observation": ProteoformSupportObservation,
    "invariant": ProteoformSupportInvariant,
    "analysis": ProteoformHarmonizedAnalysis,
    "value": ProteoformHarmonizedSupportValue,
    "transformation-manifest": ProteoformTransformationManifest,
    "finding": ProteoformHarmonizationFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict fixed-point Draft 2020-12 contract schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0406_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "fixedPointScale": 1_000_000,
        "rawPayloadInSchema": False,
        "reparsesRawPayload": False,
        "identityInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "abundanceInference": False,
        "calibratedProbability": False,
        "opaqueIdentifierPattern": (
            "^(request|policy|profile|ledger|target|anchor|group|level|invariant|stage|evidence|reviewer)"
            r"\.[0-9a-f]{64}$"
        ),
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0406_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
