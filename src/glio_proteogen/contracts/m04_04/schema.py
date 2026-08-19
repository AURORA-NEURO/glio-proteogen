"""JSON Schema 2020-12 exports for M04-04 quality computation."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_04.v1 import (
    M0404_CONTRACT_VERSION,
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    M0404_MAX_CANONICAL_RESULT_BYTES,
    M0404_MODULE_ID,
    M0404_PARENT,
    M0404_RATE_SCALE,
    ComputeProteoformQualityMetricsRequest,
    ProteoformAssayQualityProfile,
    ProteoformAssayQualityResult,
    ProteoformQualityComputationReceipt,
    ProteoformQualityFactLedger,
    ProteoformQualityFinding,
    ProteoformQualityMetric,
    ProteoformQualityPolicy,
    ProteoformQualityResult,
    ProteoformQualityRoleCounts,
    ProteoformQualityRoleFacts,
    ProteoformQualityRoleFactStates,
    ProteoformQualityThreshold,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-04:1.0.0"
CONTRACT_VERSION: Final = M0404_CONTRACT_VERSION
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
    "request": ComputeProteoformQualityMetricsRequest,
    "output": ProteoformQualityResult,
    "policy": ProteoformQualityPolicy,
    "threshold": ProteoformQualityThreshold,
    "assay-profile": ProteoformAssayQualityProfile,
    "fact-counts": ProteoformQualityRoleCounts,
    "fact-states": ProteoformQualityRoleFactStates,
    "role-facts": ProteoformQualityRoleFacts,
    "fact-ledger": ProteoformQualityFactLedger,
    "metric": ProteoformQualityMetric,
    "assay-quality": ProteoformAssayQualityResult,
    "finding": ProteoformQualityFinding,
    "receipt": ProteoformQualityComputationReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0404_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "metadataOnlyAggregates": True,
        "rateScale": M0404_RATE_SCALE,
        "externalContentTraversal": False,
        "rawPayload": False,
        "modelExecution": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "isoformInference": False,
        "gliomaSpecificBiologyInference": False,
        "modificationLocalization": False,
        "copyNumberRegression": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0404_PARENT,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0404_MAX_CANONICAL_REQUEST_BYTES
    if name == "output":
        metadata["maxResultBytes"] = M0404_MAX_CANONICAL_RESULT_BYTES
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
