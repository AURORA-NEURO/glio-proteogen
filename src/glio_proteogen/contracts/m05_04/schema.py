"""JSON Schema 2020-12 exports for M05-04 quality computation."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_04.v1 import (
    M0504_CONTRACT_VERSION,
    M0504_MAX_CANONICAL_REQUEST_BYTES,
    M0504_MODULE_ID,
    M0504_PARENT,
    M0504_RATE_SCALE,
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationAssayQualityProfile,
    PtmLocalizationAssayQualityResult,
    PtmLocalizationQualityComputationReceipt,
    PtmLocalizationQualityFactLedger,
    PtmLocalizationQualityFinding,
    PtmLocalizationQualityMetric,
    PtmLocalizationQualityPolicy,
    PtmLocalizationQualityResult,
    PtmLocalizationQualityRoleCounts,
    PtmLocalizationQualityRoleFacts,
    PtmLocalizationQualityRoleFactStates,
    PtmLocalizationQualityThreshold,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-04:1.0.0"
CONTRACT_VERSION: Final = M0504_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "threshold",
    "assay-profile",
    "fact-counts",
    "fact-states",
    "role-facts",
    "fact-ledger",
    "metric",
    "assay-quality",
    "finding",
    "receipt",
]
_CONTRACTS: Final = {
    "request": ComputePtmLocalizationQualityMetricsRequest,
    "output": PtmLocalizationQualityResult,
    "policy": PtmLocalizationQualityPolicy,
    "threshold": PtmLocalizationQualityThreshold,
    "assay-profile": PtmLocalizationAssayQualityProfile,
    "fact-counts": PtmLocalizationQualityRoleCounts,
    "fact-states": PtmLocalizationQualityRoleFactStates,
    "role-facts": PtmLocalizationQualityRoleFacts,
    "fact-ledger": PtmLocalizationQualityFactLedger,
    "metric": PtmLocalizationQualityMetric,
    "assay-quality": PtmLocalizationAssayQualityResult,
    "finding": PtmLocalizationQualityFinding,
    "receipt": PtmLocalizationQualityComputationReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0504_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "metadataOnlyAggregates": True,
        "rateScale": M0504_RATE_SCALE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "modelExecution": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "ptm_localizationInference": False,
        "modificationLocalization": False,
        "copyNumberRegression": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "eventPersistence": False,
        "parentTarget": M0504_PARENT,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0504_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


from typing import cast  # noqa: E402 - kept beside the typed schema iterator.

__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
