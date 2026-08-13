"""JSON Schema 2020-12 exports for M04-02 identity-lineage reconciliation."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m04_02.v1 import (
    M0402_CONTRACT_VERSION,
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    M0402_MODULE_ID,
    ProteoformIdentityLineageFinding,
    ProteoformIdentityLineagePolicy,
    ProteoformIdentityLineageReceipt,
    ProteoformIdentityLineageResolution,
    ProteoformLineageArtifactClaim,
    ProteoformLineageArtifactDerivation,
    ReconcileProteoformIdentityLineageRequest,
    ResolvedProteoformIdentityLineageGraph,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M04-02:1.0.0"
CONTRACT_VERSION: Final = M0402_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "artifact-claim",
    "derivation",
    "graph",
    "finding",
    "receipt",
]
_CONTRACTS: Final = {
    "request": ReconcileProteoformIdentityLineageRequest,
    "output": ProteoformIdentityLineageResolution,
    "policy": ProteoformIdentityLineagePolicy,
    "artifact-claim": ProteoformLineageArtifactClaim,
    "derivation": ProteoformLineageArtifactDerivation,
    "graph": ResolvedProteoformIdentityLineageGraph,
    "finding": ProteoformIdentityLineageFinding,
    "receipt": ProteoformIdentityLineageReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only M04-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0402_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "identityInference": False,
        "consentInference": False,
        "proteinInference": False,
        "proteoformInference": False,
        "copyNumberRegression": False,
        "proteinRnaDiscordanceInference": False,
        "kinaseActivityInference": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": "protein_rna_discordance",
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0402_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all installed M04-02 schemas."""

    names: tuple[ContractName, ...] = (
        "request",
        "output",
        "policy",
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
