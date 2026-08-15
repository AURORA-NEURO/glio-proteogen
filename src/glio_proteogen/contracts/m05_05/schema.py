"""JSON Schema 2020-12 exports for M05-05 artifact detection."""

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_05.v1 import (
    M0505_CONTRACT_VERSION,
    M0505_GATE,
    M0505_MAX_CANONICAL_REQUEST_BYTES,
    M0505_MODULE_ID,
    M0505_OUTPUT_MEDIA_TYPE,
    M0505_OWNER,
    M0505_PARENT,
    M0505_RATE_SCALE,
    M0505_SAFETY_CLASS,
    DetectPtmLocalizationArtifactsRequest,
    PtmLocalizationArtifactComputationReceipt,
    PtmLocalizationArtifactDetectionResult,
    PtmLocalizationArtifactEvidenceEvent,
    PtmLocalizationArtifactEvidenceLedger,
    PtmLocalizationArtifactEvidenceLedgerBinding,
    PtmLocalizationArtifactFinding,
    PtmLocalizationArtifactPolicy,
    PtmLocalizationArtifactPosterior,
    PtmLocalizationArtifactProfile,
    PtmLocalizationArtifactThreshold,
    PtmLocalizationContaminationFlag,
    PtmLocalizationExclusionMaskEntry,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-05:1.0.0"
CONTRACT_VERSION: Final = M0505_CONTRACT_VERSION
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
    "request": DetectPtmLocalizationArtifactsRequest,
    "output": PtmLocalizationArtifactDetectionResult,
    "policy": PtmLocalizationArtifactPolicy,
    "threshold": PtmLocalizationArtifactThreshold,
    "profile": PtmLocalizationArtifactProfile,
    "evidence-event": PtmLocalizationArtifactEvidenceEvent,
    "evidence-ledger": PtmLocalizationArtifactEvidenceLedger,
    "evidence-ledger-binding": PtmLocalizationArtifactEvidenceLedgerBinding,
    "artifact-posterior": PtmLocalizationArtifactPosterior,
    "contamination-flag": PtmLocalizationContaminationFlag,
    "exclusion-mask-entry": PtmLocalizationExclusionMaskEntry,
    "finding": PtmLocalizationArtifactFinding,
    "receipt": PtmLocalizationArtifactComputationReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only M05-05 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0505_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0505_OWNER,
        "safetyClass": M0505_SAFETY_CLASS,
        "gate": M0505_GATE,
        "strict": True,
        "aggregateEvidenceOnly": True,
        "eventSourced": True,
        "openSetAbstention": True,
        "rateScale": M0505_RATE_SCALE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "calibratedProbability": False,
        "identityInference": False,
        "consentInference": False,
        "ptmLocalizationInference": False,
        "modificationLocalization": False,
        "proteogenomicStateInference": False,
        "proteotypeInference": False,
        "proteinLevelSubtypeInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "variantPeptideEmission": False,
        "parentTarget": M0505_PARENT,
        "outputMediaType": M0505_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0505_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all thirteen installed M05-05 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
