"""JSON Schema 2020-12 exports for provisional M09-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_02.v1 import (
    M0902_CONTRACT_VERSION,
    M0902_GATE,
    M0902_MAX_CANONICAL_REQUEST_BYTES,
    M0902_MODULE_ID,
    M0902_OUTPUT_MEDIA_TYPE,
    M0902_OWNER,
    M0902_PARENT,
    M0902_PROVISIONAL_ABI,
    M0902_SAFETY_CLASS,
    ComplexActivityRepresentationResult,
    ConstructComplexActivityRepresentationRequest,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheck,
    RepresentationFeature,
    RepresentationPolicy,
    RepresentationTransformation,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M09-02:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0902_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "feature-specification",
    "feature-lineage",
    "representation-feature",
    "transformation",
    "policy",
    "leakage-check",
]
_CONTRACTS: Final = {
    "request": ConstructComplexActivityRepresentationRequest,
    "output": ComplexActivityRepresentationResult,
    "feature-specification": FeatureSpecification,
    "feature-lineage": FeatureLineage,
    "representation-feature": RepresentationFeature,
    "transformation": RepresentationTransformation,
    "policy": RepresentationPolicy,
    "leakage-check": LeakageCheck,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M09-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0902_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0902_OWNER,
        "safetyClass": M0902_SAFETY_CLASS,
        "gate": M0902_GATE,
        "strict": True,
        "provisionalAbi": M0902_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0902_PARENT,
        "unsupportedToNegative": False,
        "featureLineageRequired": True,
        "leakageSafeTransformationsRequired": True,
        "outputMediaType": M0902_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0902_MAX_CANONICAL_REQUEST_BYTES
    return cast("dict[str, object]", schema)


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional schemas in declared order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
