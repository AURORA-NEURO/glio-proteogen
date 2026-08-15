"""JSON Schema 2020-12 exports for provisional M15-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_03.v1 import (
    M1503_CONTRACT_VERSION,
    M1503_GATE,
    M1503_MAX_CANONICAL_REQUEST_BYTES,
    M1503_MODULE_ID,
    M1503_OUTPUT_MEDIA_TYPE,
    M1503_OWNER,
    M1503_PARENT,
    M1503_PROVISIONAL_ABI,
    M1503_SAFETY_CLASS,
    ComplexActivityMechanisticFeatureResult,
    ConstructComplexActivityMechanisticFeaturesRequest,
    FeatureConstructorConfiguration,
    FeatureConstructorPolicy,
    FeatureFinding,
    MechanisticFeature,
    MechanisticFeatureObject,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M15-03:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1503_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature",
    "feature-object",
    "configuration",
    "policy",
    "finding",
]
_CONTRACTS: Final = {
    "request": ConstructComplexActivityMechanisticFeaturesRequest,
    "output": ComplexActivityMechanisticFeatureResult,
    "feature": MechanisticFeature,
    "feature-object": MechanisticFeatureObject,
    "configuration": FeatureConstructorConfiguration,
    "policy": FeatureConstructorPolicy,
    "finding": FeatureFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M15-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1503_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1503_OWNER,
        "safetyClass": M1503_SAFETY_CLASS,
        "gate": M1503_GATE,
        "strict": True,
        "provisionalAbi": M1503_PROVISIONAL_ABI,
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
        "parentTarget": M1503_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1503_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m15-02+json",
        "primaryArchitecture": "bayesian_graph_state_space_mechanistic_foundation_assisted",
        "alternateArchitecture": "curated_rule_enrichment_protein_interaction_gnn",
        "fallbackArchitecture": "orthogonal_consensus_negative_control",
        "unitsRequired": True,
        "topologyInvariantsRequired": True,
        "perturbationInvariantsRequired": True,
        "sourceEvidenceRequired": True,
        "uncertaintyRequired": True,
        "explicitAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1503_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all seven provisional M15-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
