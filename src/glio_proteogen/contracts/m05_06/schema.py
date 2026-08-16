"""JSON Schema exports for provisional M05-06."""

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_06.v1 import (
    M0506_CONTRACT_VERSION,
    M0506_GATE,
    M0506_MAX_CANONICAL_REQUEST_BYTES,
    M0506_MODULE_ID,
    M0506_OUTPUT_MEDIA_TYPE,
    M0506_OWNER,
    M0506_PARENT,
    M0506_PROVISIONAL_ABI,
    M0506_RATE_SCALE,
    M0506_SAFETY_CLASS,
    HarmonizePtmLocalizationAnalysisRequest,
    PtmLocalizationArtifactHarmonizationReceipt,
    PtmLocalizationHarmonizationComputationReceipt,
    PtmLocalizationHarmonizationPolicy,
    PtmLocalizationHarmonizationProfile,
    PtmLocalizationHarmonizationResult,
    PtmLocalizationHarmonizedAnalysis,
    PtmLocalizationNormalizationStage,
    PtmLocalizationStageTransformation,
    PtmLocalizationSupportInvariant,
    PtmLocalizationSupportLedger,
    PtmLocalizationSupportLevelShift,
    PtmLocalizationSupportObservation,
    PtmLocalizationTransformationManifest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-06:1.0.0-provisional"
CONTRACT_VERSION: Final = M0506_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "artifact-receipt",
    "support-ledger",
    "support-observation",
    "support-invariant",
    "policy",
    "profile",
    "normalization-stage",
    "level-shift",
    "stage-transformation",
    "transformation-manifest",
    "analysis",
    "receipt",
]
_CONTRACTS: Final = {
    "request": HarmonizePtmLocalizationAnalysisRequest,
    "output": PtmLocalizationHarmonizationResult,
    "artifact-receipt": PtmLocalizationArtifactHarmonizationReceipt,
    "support-ledger": PtmLocalizationSupportLedger,
    "support-observation": PtmLocalizationSupportObservation,
    "support-invariant": PtmLocalizationSupportInvariant,
    "policy": PtmLocalizationHarmonizationPolicy,
    "profile": PtmLocalizationHarmonizationProfile,
    "normalization-stage": PtmLocalizationNormalizationStage,
    "level-shift": PtmLocalizationSupportLevelShift,
    "stage-transformation": PtmLocalizationStageTransformation,
    "transformation-manifest": PtmLocalizationTransformationManifest,
    "analysis": PtmLocalizationHarmonizedAnalysis,
    "receipt": PtmLocalizationHarmonizationComputationReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict schema with an explicit provisional ABI marker."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0506_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0506_OWNER,
        "safetyClass": M0506_SAFETY_CLASS,
        "gate": M0506_GATE,
        "strict": True,
        "provisionalAbi": M0506_PROVISIONAL_ABI,
        "pendingOwnerConfirmation": True,
        "aggregateEvidenceOnly": True,
        "openSetAbstention": True,
        "rateScale": M0506_RATE_SCALE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "calibratedProbability": False,
        "identityInference": False,
        "consentInference": False,
        "ptmLocalizationInference": False,
        "modificationLocalization": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "variantPeptideEmission": False,
        "parentTarget": M0506_PARENT,
        "outputMediaType": M0506_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0506_MAX_CANONICAL_REQUEST_BYTES
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
