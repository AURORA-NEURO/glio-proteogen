"""JSON Schema 2020-12 exports for provisional M08-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_02.v1 import (
    M0802_CONTRACT_VERSION,
    M0802_GATE,
    M0802_MAX_CANONICAL_REQUEST_BYTES,
    M0802_MODULE_ID,
    M0802_OUTPUT_MEDIA_TYPE,
    M0802_OWNER,
    M0802_PARENT,
    M0802_PROVISIONAL_ABI,
    M0802_SAFETY_CLASS,
    ConstructTranscriptProteinRepresentationRequest,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheck,
    RepresentationFeature,
    RepresentationPolicy,
    RepresentationTransformation,
    TranscriptProteinRepresentationResult,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M08-02:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0802_CONTRACT_VERSION
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
    "request": ConstructTranscriptProteinRepresentationRequest,
    "output": TranscriptProteinRepresentationResult,
    "feature-specification": FeatureSpecification,
    "feature-lineage": FeatureLineage,
    "representation-feature": RepresentationFeature,
    "transformation": RepresentationTransformation,
    "policy": RepresentationPolicy,
    "leakage-check": LeakageCheck,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M08-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0802_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0802_OWNER,
        "safetyClass": M0802_SAFETY_CLASS,
        "gate": M0802_GATE,
        "strict": True,
        "provisionalAbi": M0802_PROVISIONAL_ABI,
        "abiStatus": "dossier-behavioral-brief-only",
        "pendingOwnerConfirmation": True,
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "kinaseActivity": False,
        "treatmentRecommendation": False,
        "parentTarget": M0802_PARENT,
        "unsupportedToNegative": False,
        "featureLineageRequired": True,
        "leakageSafeTransformationsRequired": True,
        "outputMediaType": M0802_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0802_MAX_CANONICAL_REQUEST_BYTES
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
