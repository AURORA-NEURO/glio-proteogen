"""JSON Schema 2020-12 exports for M03-02."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_02.v1 import (
    M0302_CONTRACT_VERSION,
    M0302_MAX_CANONICAL_REQUEST_BYTES,
    M0302_MODULE_ID,
    CopyNumberConcordanceReceipt,
    ProteinInferenceArtifactClaim,
    ProteinInferenceArtifactDerivation,
    ProteinInferenceIdentityLineageResolution,
    ProteinInferenceLineagePolicy,
    ProteinInferenceLineageReceipt,
    ReconcileProteinInferenceIdentityLineageRequest,
    ResolvedProteinInferenceLineageGraph,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-02:1.0.0"
)
CONTRACT_VERSION: Final = M0302_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "artifact-claim",
    "derivation",
    "cn-receipt",
    "graph",
    "receipt",
]
_CONTRACTS: Final = {
    "request": ReconcileProteinInferenceIdentityLineageRequest,
    "output": ProteinInferenceIdentityLineageResolution,
    "policy": ProteinInferenceLineagePolicy,
    "artifact-claim": ProteinInferenceArtifactClaim,
    "derivation": ProteinInferenceArtifactDerivation,
    "cn-receipt": CopyNumberConcordanceReceipt,
    "graph": ResolvedProteinInferenceLineageGraph,
    "receipt": ProteinInferenceLineageReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0302_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "identityInference": False,
        "upstreamRelabeling": False,
        "complexActivityInference": False,
        "copyNumberIdentityMerge": False,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0302_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
