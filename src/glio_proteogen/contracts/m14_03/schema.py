"""JSON Schema 2020-12 exports for provisional M14-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_03.v1 import (
    M1403_CONTRACT_VERSION,
    M1403_GATE,
    M1403_MAX_CANONICAL_REQUEST_BYTES,
    M1403_MODULE_ID,
    M1403_OUTPUT_MEDIA_TYPE,
    M1403_OWNER,
    M1403_PARENT,
    M1403_PROVISIONAL_ABI,
    M1403_SAFETY_CLASS,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticRelation,
    ProteinSubtypeMechanisticFeatureResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M14-03:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M1403_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature-object",
    "feature",
    "lineage",
    "relation",
    "configuration",
    "diagnostic",
]
_CONTRACTS: Final = {
    "request": ConstructProteinSubtypeMechanisticFeaturesRequest,
    "output": ProteinSubtypeMechanisticFeatureResult,
    "feature-object": MechanisticFeatureObject,
    "feature": MechanisticFeature,
    "lineage": MechanisticFeatureLineage,
    "relation": MechanisticRelation,
    "configuration": MechanisticFeatureConfiguration,
    "diagnostic": MechanisticFeatureDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M14-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1403_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1403_OWNER,
        "safetyClass": M1403_SAFETY_CLASS,
        "gate": M1403_GATE,
        "strict": True,
        "provisionalAbi": M1403_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1403_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1403_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m14-02+json",
        "sourceEvidenceRequired": True,
        "stoichiometricInvariantsRequired": True,
        "topologyInvariantsRequired": True,
        "unitInvariantsRequired": True,
        "negativeControlGatingExplicit": True,
        "safeAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1403_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M14-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
