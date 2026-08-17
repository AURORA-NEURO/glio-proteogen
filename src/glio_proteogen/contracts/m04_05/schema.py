"""JSON Schema 2020-12 exports for M04-05 artifact detection."""

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_05.v1 import (
    M0405_CONTRACT_VERSION,
    M0405_MAX_CANONICAL_REQUEST_BYTES,
    M0405_MODULE_ID,
    M0405_PARENT,
    M0405_RATE_SCALE,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactComputationReceipt,
    ProteoformArtifactDetectionResult,
    ProteoformArtifactEvidenceEvent,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactEvidenceLedgerBinding,
    ProteoformArtifactFinding,
    ProteoformArtifactPolicy,
    ProteoformArtifactPosterior,
    ProteoformArtifactProfile,
    ProteoformArtifactThreshold,
    ProteoformContaminationFlag,
    ProteoformExclusionMaskEntry,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-05:1.0.0"
CONTRACT_VERSION: Final = M0405_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "threshold",
    "profile",
    "evidence-event",
    "evidence-ledger",
    "evidence-ledger-binding",
    "artifact-posterior",
    "contamination-flag",
    "exclusion-mask-entry",
    "finding",
    "receipt",
]
_CONTRACTS: Final = {
    "request": DetectProteoformArtifactsRequest,
    "output": ProteoformArtifactDetectionResult,
    "policy": ProteoformArtifactPolicy,
    "threshold": ProteoformArtifactThreshold,
    "profile": ProteoformArtifactProfile,
    "evidence-event": ProteoformArtifactEvidenceEvent,
    "evidence-ledger": ProteoformArtifactEvidenceLedger,
    "evidence-ledger-binding": ProteoformArtifactEvidenceLedgerBinding,
    "artifact-posterior": ProteoformArtifactPosterior,
    "contamination-flag": ProteoformContaminationFlag,
    "exclusion-mask-entry": ProteoformExclusionMaskEntry,
    "finding": ProteoformArtifactFinding,
    "receipt": ProteoformArtifactComputationReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0405_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "aggregateEvidenceOnly": True,
        "eventSourced": True,
        "openSetAbstention": True,
        "rateScale": M0405_RATE_SCALE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "calibratedProbability": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "modificationLocalization": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0405_PARENT,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0405_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
