"""JSON Schema 2020-12 exports for M01-02 public contracts."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_02.v1 import (
    IdentityEntity,
    IdentityLineageResolution,
    IdentityResolutionPolicy,
    LineageOperation,
    ReconcileIdentityLineageRequest,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-02:1.0.0"

ContractName = Literal["request", "output", "policy", "entity", "operation", "resolution"]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(ReconcileIdentityLineageRequest),
    "output": TypeAdapter(IdentityLineageResolution),
    "policy": TypeAdapter(IdentityResolutionPolicy),
    "entity": TypeAdapter(IdentityEntity),
    "operation": TypeAdapter(LineageOperation),
    "resolution": TypeAdapter(IdentityLineageResolution),
}


def _definition(schema: dict[str, Any], name: str) -> dict[str, Any] | None:
    if schema.get("title") == name:
        return schema
    candidate = schema.get("$defs", {}).get(name)
    return candidate if isinstance(candidate, dict) else None


def _mark_unique_by(schema: dict[str, Any], model: str, field: str, pointer: str) -> None:
    definition = _definition(schema, model)
    if definition is None:
        return
    array = definition.get("properties", {}).get(field)
    if isinstance(array, dict):
        array["x-glio-uniqueBy"] = pointer


def _mark_unique_by_fields(
    schema: dict[str, Any],
    model: str,
    field: str,
    pointers: tuple[str, ...],
) -> None:
    """Describe runtime composite uniqueness without pretending one field is authoritative."""

    definition = _definition(schema, model)
    if definition is None:
        return
    array = definition.get("properties", {}).get(field)
    if isinstance(array, dict):
        array["x-glio-uniqueByFields"] = list(pointers)


def _enrich(schema: dict[str, Any]) -> None:
    for model, field, pointer in (
        ("ReconcileIdentityLineageRequest", "entities", "/entity_id"),
        ("ReconcileIdentityLineageRequest", "assertions", "/assertion_id"),
        ("ReconcileIdentityLineageRequest", "lineage_operations", "/operation_id"),
        ("ReconcileIdentityLineageRequest", "concordance_observations", "/observation_id"),
        ("LineageOperation", "channels", "/channel_id"),
        ("ResolvedLineageGraph", "nodes", "/entity_id"),
        ("ResolvedLineageGraph", "operations", "/operation_id"),
        ("IdentityLineageResolution", "components", "/component_id"),
        ("IdentityLineageResolution", "assertion_dispositions", "/assertion_id"),
        ("IdentityLineageResolution", "limitations", "/code"),
        ("IdentityProvenanceRecord", "control_decisions", "/role"),
    ):
        _mark_unique_by(schema, model, field, pointer)
    _mark_unique_by_fields(
        schema,
        "IdentityEntity",
        "identity_tokens",
        ("/issuer_id", "/namespace_id", "/scope_id", "/key_id", "/token_version"),
    )
    artifact_identity = ("/artifact_id", "/version", "/digest", "/media_type")
    for model in (
        "IdentityEntity",
        "SameAsAssertion",
        "DifferentFromAssertion",
        "SubjectMembershipAssertion",
        "LineageOperation",
        "DemultiplexChannel",
        "ConcordanceObservation",
    ):
        _mark_unique_by_fields(schema, model, "evidence", artifact_identity)
    _mark_unique_by_fields(
        schema,
        "IdentityLineageResolution",
        "evidence",
        (
            "/reference/artifact_id",
            "/reference/version",
            "/reference/digest",
            "/reference/media_type",
            "/role",
            "/claim",
        ),
    )
    for model, fields in (
        ("IdentityResolutionPolicy", ("allowed_operation_kinds",)),
        ("LineageOperation", ("source_entity_ids", "target_entity_ids")),
        ("IdentityComponent", ("member_entity_ids", "subject_component_ids")),
        ("ResolvedIdentityNode", ("subject_component_ids",)),
        ("ResolvedLineageOperation", ("source_entity_ids", "target_entity_ids")),
    ):
        definition = _definition(schema, model)
        if definition is None:
            continue
        for field in fields:
            array = definition.get("properties", {}).get(field)
            if isinstance(array, dict):
                array["uniqueItems"] = True
    relations = {
        "ReconcileIdentityLineageRequest": [
            "all entity, assertion, operation, channel, and observation identifiers are unique",
            "every reference is closed over the request entity set",
            "authority, configuration digest, and policy versions agree",
            "active policy caps cannot exceed hard contract caps",
        ],
        "IdentityLineageResolution": [
            "components partition the resolved graph nodes",
            "decision, support, and human review derive from issues",
            "graph and resolution digests match canonical content",
            "mandatory module limitations occur exactly once",
        ],
    }
    for model, invariants in relations.items():
        definition = _definition(schema, model)
        if definition is not None:
            definition["x-glio-relationalInvariants"] = invariants


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Export strict structure plus machine-readable runtime invariants."""

    generated = _ADAPTERS[name].json_schema(mode="validation")
    exported: dict[str, Any] = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_PREFIX}:{name}",
        **generated,
    }
    _enrich(exported)
    exported["x-glio-validation-profile"] = {
        "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
        "scope": "structural schema plus expressible relational invariants",
        "strictJson": True,
        "silentCoercion": False,
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus the M01-02 solver",
        "extensionKeywords": [
            "x-glio-uniqueBy",
            "x-glio-uniqueByFields",
            "x-glio-relationalInvariants",
        ],
    }
    return cast("dict[str, object]", exported)


__all__ = [
    "CONTRACT_VERSION",
    "JSON_SCHEMA_DIALECT",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
]
