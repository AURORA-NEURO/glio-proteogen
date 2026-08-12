"""JSON Schema 2020-12 exports for M01-04 public contracts."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_04.v1 import (
    AssayProfile,
    ComputeQualityMetricsRequest,
    MetricDefinition,
    Observation,
    QualityComputationPolicy,
    QualityMetric,
    QualityProfile,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-04:1.0.0"

ContractName = Literal[
    "request",
    "output",
    "policy",
    "assay_profile",
    "metric_definition",
    "observation",
    "quality_metric",
]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(ComputeQualityMetricsRequest),
    "output": TypeAdapter(QualityProfile),
    "policy": TypeAdapter(QualityComputationPolicy),
    "assay_profile": TypeAdapter(AssayProfile),
    "metric_definition": TypeAdapter(MetricDefinition),
    "observation": TypeAdapter(Observation),
    "quality_metric": TypeAdapter(QualityMetric),
}


def _definition(schema: dict[str, Any], name: str) -> dict[str, Any] | None:
    if schema.get("title") == name:
        return schema
    candidate = schema.get("$defs", {}).get(name)
    return candidate if isinstance(candidate, dict) else None


def _mark_unique(schema: dict[str, Any], model: str, field: str, pointer: str) -> None:
    definition = _definition(schema, model)
    if definition is None:
        return
    array = definition.get("properties", {}).get(field)
    if isinstance(array, dict):
        array["x-glio-uniqueBy"] = pointer


def _enrich(schema: dict[str, Any]) -> None:
    for model, field, pointer in (
        ("AssayProfile", "required_metric_ids", "/"),
        ("ComputeQualityMetricsRequest", "metric_definitions", "/metric_id"),
        ("ComputeQualityMetricsRequest", "observations", "/observation_id"),
        ("QualityProfile", "metrics", "/metric_id"),
        ("QualityProfile", "limitations", "/code"),
        ("ProvenanceRecord", "control_decisions", "/role"),
    ):
        _mark_unique(schema, model, field, pointer)
    for model, fields in (
        ("AssayProfile", ("required_metric_ids",)),
        ("MetricDefinition", ("observation_ids",)),
        ("QualityComputationPolicy", ("enabled_categories",)),
        ("Provenance", ("observation_ids",)),
    ):
        definition = _definition(schema, model)
        if definition is None:
            continue
        for field in fields:
            array = definition.get("properties", {}).get(field)
            if isinstance(array, dict):
                array["uniqueItems"] = True
    relations = {
        "ComputeQualityMetricsRequest": [
            "authorization is accepted before quality computation",
            "approved configuration digest binds the active policy",
            "profile metric and definition observation references are closed over the request",
        ],
        "QualityMetric": [
            "non-observed states remain not evaluable and never become numeric zero",
            "metric computation agrees with its privacy-minimized provenance",
        ],
        "QualityProfile": [
            "failed metrics force quarantine and all-passing profiles force acceptance",
            "support and review state agree with the disposition",
            "provenance binds request, assay profile, policy, definitions, and observations",
            "result digest matches canonical public content",
        ],
    }
    for model, invariants in relations.items():
        definition = _definition(schema, model)
        if definition is not None:
            definition["x-glio-relationalInvariants"] = invariants


def contract_json_schema(name: ContractName) -> dict[str, object]:
    generated = _ADAPTERS[name].json_schema(mode="validation")
    exported: dict[str, Any] = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_PREFIX}:{name}",
        **generated,
    }
    _enrich(exported)
    exported["x-glio-validation-profile"] = {
        "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
        "strictJson": True,
        "silentCoercion": False,
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus deterministic M01-04 rules",
        "extensionKeywords": ["x-glio-uniqueBy", "x-glio-relationalInvariants"],
    }
    return cast("dict[str, object]", exported)


__all__ = [
    "CONTRACT_VERSION",
    "JSON_SCHEMA_DIALECT",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
]
