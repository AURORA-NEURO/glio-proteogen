"""JSON Schema 2020-12 exports for provisional M14-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_02.v1 import (
    M1402_CONTRACT_VERSION,
    M1402_GATE,
    M1402_MAX_CANONICAL_REQUEST_BYTES,
    M1402_MODULE_ID,
    M1402_OUTPUT_MEDIA_TYPE,
    M1402_OWNER,
    M1402_PARENT,
    M1402_PROVISIONAL_ABI,
    M1402_SAFETY_CLASS,
    ApplicableMechanism,
    ContextFinding,
    ContextObservation,
    ProteinSubtypeContextProfile,
    ProteinSubtypeContextStratificationResult,
    StratifierConfiguration,
    StratifierPolicy,
    StratifyProteinSubtypeContextRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-02:0.1.0-provisional"
CONTRACT_VERSION: Final = M1402_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "observation",
    "profile",
    "mechanism",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": StratifyProteinSubtypeContextRequest,
    "output": ProteinSubtypeContextStratificationResult,
    "observation": ContextObservation,
    "profile": ProteinSubtypeContextProfile,
    "mechanism": ApplicableMechanism,
    "configuration": StratifierConfiguration,
    "policy": StratifierPolicy,
    "finding": ContextFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1402_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1402_OWNER,
        "safetyClass": M1402_SAFETY_CLASS,
        "gate": M1402_GATE,
        "strict": True,
        "provisionalAbi": M1402_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "mutationRelabeling": False,
        "disagreementErasure": False,
        "identityInference": False,
        "consentInference": False,
        "parentTarget": M1402_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1402_OUTPUT_MEDIA_TYPE,
        "primaryArchitecture": "bayesian_graph_state_space_mechanistic_foundation_assisted",
        "alternateArchitecture": "curated_rule_enrichment_cn_protein_regression",
        "fallbackArchitecture": "orthogonal_consensus_negative_control",
        "contextDimensions": [
            "disease_class",
            "subtype",
            "age",
            "territory",
            "treatment_era",
            "specimen",
            "platform",
            "biological_context",
        ],
        "conflictPreservationRequired": True,
        "quarantineUnresolvedRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1402_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M14-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
