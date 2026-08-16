"""JSON Schema 2020-12 exports for provisional M07-02 contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m07_02.v1 import (
    M0702_CONTRACT_VERSION,
    M0702_GATE,
    M0702_MAX_CANONICAL_REQUEST_BYTES,
    M0702_MODULE_ID,
    M0702_OUTPUT_MEDIA_TYPE,
    M0702_OWNER,
    M0702_PARENT,
    M0702_SAFETY_CLASS,
    ConstructProteotypeAnalysisRepresentationRequest,
    FeatureLineage,
    FeatureSpecification,
    LeakageCheck,
    ProteotypeAnalysisRepresentationResult,
    RepresentationFeature,
    RepresentationPolicy,
    RepresentationTransformation,
)

SCHEMA_ID_PREFIX: Final = (
    "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M07-02:0.1.0-provisional"
)
CONTRACT_VERSION: Final = M0702_CONTRACT_VERSION
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
    "request": ConstructProteotypeAnalysisRepresentationRequest,
    "output": ProteotypeAnalysisRepresentationResult,
    "feature-specification": FeatureSpecification,
    "feature-lineage": FeatureLineage,
    "representation-feature": RepresentationFeature,
    "transformation": RepresentationTransformation,
    "policy": RepresentationPolicy,
    "leakage-check": LeakageCheck,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only provisional M07-02 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": M0702_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "owner": M0702_OWNER,
        "safetyClass": M0702_SAFETY_CLASS,
        "gate": M0702_GATE,
        "strict": True,
        "provisionalAbi": True,
        "abiStatus": "dossier-behavioral-brief-only",
        "externalContentTraversal": False,
        "rawPayload": False,
        "allOmicsFusion": False,
        "treatmentRecommendation": False,
        "parentTarget": M0702_PARENT,
        "variantPeptideEmission": False,
        "featureLineageRequired": True,
        "leakageSafeTransformationsRequired": True,
        "outputMediaType": M0702_OUTPUT_MEDIA_TYPE,
    }
    if name == "request":
        schema["x-glio-contract"]["maxRequestBytes"] = M0702_MAX_CANONICAL_REQUEST_BYTES
    return schema


def contract_json_schemas() -> dict[ContractName, dict[str, object]]:
    """Return all eight provisional M07-02 schemas in ABI order."""

    names = cast("tuple[ContractName, ...]", tuple(_CONTRACTS))
    return {name: contract_json_schema(name) for name in names}


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
    "contract_json_schemas",
]
