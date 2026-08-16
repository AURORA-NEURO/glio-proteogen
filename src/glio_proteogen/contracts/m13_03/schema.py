"""JSON Schema 2020-12 exports for provisional M13-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_03.v1 import (
    M1303_CONTRACT_VERSION,
    M1303_GATE,
    M1303_MAX_CANONICAL_REQUEST_BYTES,
    M1303_MODULE_ID,
    M1303_OUTPUT_MEDIA_TYPE,
    M1303_OWNER,
    M1303_PARENT,
    M1303_PROVISIONAL_ABI,
    M1303_SAFETY_CLASS,
    ConstructProteotypeMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticRelation,
    ProteotypeMechanisticFeatureResult,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M13-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M1303_CONTRACT_VERSION
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
    "request": ConstructProteotypeMechanisticFeaturesRequest,
    "output": ProteotypeMechanisticFeatureResult,
    "feature-object": MechanisticFeatureObject,
    "feature": MechanisticFeature,
    "lineage": MechanisticFeatureLineage,
    "relation": MechanisticRelation,
    "configuration": MechanisticFeatureConfiguration,
    "diagnostic": MechanisticFeatureDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M13-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1303_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1303_OWNER,
        "safetyClass": M1303_SAFETY_CLASS,
        "gate": M1303_GATE,
        "strict": True,
        "provisionalAbi": M1303_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1303_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1303_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m13-02+json",
        "sourceEvidenceRequired": True,
        "pathwayActivityRequired": True,
        "topologyInvariantsRequired": True,
        "unitInvariantsRequired": True,
        "negativeControlGatingExplicit": True,
        "safeAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1303_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M13-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
