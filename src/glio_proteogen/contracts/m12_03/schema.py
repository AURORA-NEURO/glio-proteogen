"""JSON Schema 2020-12 exports for provisional M12-03 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_03.v1 import (
    M1203_CONTRACT_VERSION,
    M1203_GATE,
    M1203_MAX_CANONICAL_REQUEST_BYTES,
    M1203_MODULE_ID,
    M1203_OUTPUT_MEDIA_TYPE,
    M1203_OWNER,
    M1203_PARENT,
    M1203_PROVISIONAL_ABI,
    M1203_SAFETY_CLASS,
    BiomarkerPanelMechanisticFeatureResult,
    ConstructBiomarkerPanelMechanisticFeaturesRequest,
    MechanisticFeature,
    MechanisticFeatureConfiguration,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticRelation,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M12-03:0.1.0-provisional"
CONTRACT_VERSION: Final = M1203_CONTRACT_VERSION
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
    "request": ConstructBiomarkerPanelMechanisticFeaturesRequest,
    "output": BiomarkerPanelMechanisticFeatureResult,
    "feature-object": MechanisticFeatureObject,
    "feature": MechanisticFeature,
    "lineage": MechanisticFeatureLineage,
    "relation": MechanisticRelation,
    "configuration": MechanisticFeatureConfiguration,
    "diagnostic": MechanisticFeatureDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M12-03 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M1203_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M1203_OWNER,
        "safetyClass": M1203_SAFETY_CLASS,
        "gate": M1203_GATE,
        "strict": True,
        "provisionalAbi": M1203_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M1203_PARENT,
        "unsupportedToNegative": False,
        "outputMediaType": M1203_OUTPUT_MEDIA_TYPE,
        "upstreamInputMediaType": "application/vnd.glio-proteogen.m12-02+json",
        "sourceEvidenceRequired": True,
        "topologyInvariantsRequired": True,
        "unitInvariantsRequired": True,
        "negativeControlGatingExplicit": True,
        "safeAbstentionRequired": True,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M1203_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M12-03 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
