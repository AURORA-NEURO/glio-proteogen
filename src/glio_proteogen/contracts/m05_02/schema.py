"""JSON Schema 2020-12 exports for M05-02 identity-lineage reconciliation."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_02.v1 import (
    M0502_CONTRACT_VERSION,
    M0502_MAX_CANONICAL_REQUEST_BYTES,
    M0502_MODULE_ID,
    ApprovedPtmLocalizationLineageConfiguration,
    PtmLocalizationIdentityLineageFinding,
    PtmLocalizationIdentityLineagePolicy,
    PtmLocalizationIdentityLineageReceipt,
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactClaim,
    PtmLocalizationLineageArtifactDerivation,
    ReconcilePtmLocalizationIdentityLineageRequest,
    ResolvedPtmLocalizationIdentityLineageGraph,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M05-02:1.0.0"
CONTRACT_VERSION: Final = M0502_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "approved-configuration",
    "artifact-claim",
    "derivation",
    "graph",
    "finding",
    "receipt",
]
_CONTRACTS: Final = {
    "request": ReconcilePtmLocalizationIdentityLineageRequest,
    "output": PtmLocalizationIdentityLineageResolution,
    "policy": PtmLocalizationIdentityLineagePolicy,
    "approved-configuration": ApprovedPtmLocalizationLineageConfiguration,
    "artifact-claim": PtmLocalizationLineageArtifactClaim,
    "derivation": PtmLocalizationLineageArtifactDerivation,
    "graph": ResolvedPtmLocalizationIdentityLineageGraph,
    "finding": PtmLocalizationIdentityLineageFinding,
    "receipt": PtmLocalizationIdentityLineageReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only M05-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0502_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "ptmLocalizationInference": False,
        "copyNumberRegression": False,
        "proteinRnaDiscordanceInference": False,
        "variantPeptideEmission": False,
        "proteogenomicStateEmission": False,
        "proteotypeEmission": False,
        "proteinLevelSubtypeEmission": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": "variant_peptide",
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0502_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all installed M05-02 schemas."""

    names: tuple[ContractName, ...] = (
        "request",
        "output",
        "policy",
        "approved-configuration",
        "artifact-claim",
        "derivation",
        "graph",
        "finding",
        "receipt",
    )
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
