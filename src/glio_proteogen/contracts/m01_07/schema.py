"""JSON Schema 2020-12 exports for M01-07 support routing."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_07.v1 import (
    CriterionAssessment,
    RouteSupportRequest,
    SupportCriterion,
    SupportEvidence,
    SupportRoutingPolicy,
    SupportRoutingProfile,
    SupportRoutingResult,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-07:1.0.0"

ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "criterion",
    "evidence",
    "assessment",
]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(RouteSupportRequest),
    "output": TypeAdapter(SupportRoutingResult),
    "policy": TypeAdapter(SupportRoutingPolicy),
    "profile": TypeAdapter(SupportRoutingProfile),
    "criterion": TypeAdapter(SupportCriterion),
    "evidence": TypeAdapter(SupportEvidence),
    "assessment": TypeAdapter(CriterionAssessment),
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
        ("SupportRoutingProfile", "criteria", "/criterion_id"),
        ("RouteSupportRequest", "evidence", "/evidence_id"),
        ("SupportRoutingResult", "assessments", "/criterion_id"),
        ("SupportRoutingResult", "limitations", "/code"),
        ("ProvenanceRecord", "control_decisions", "/role"),
    ):
        _mark_unique(schema, model, field, pointer)
    for model, field in (
        ("SupportCriterion", "allowed_terms"),
        ("CriterionAssessment", "evidence_digests"),
    ):
        definition = _definition(schema, model)
        if definition is not None:
            array = definition.get("properties", {}).get(field)
            if isinstance(array, dict):
                array["uniqueItems"] = True
    relations = {
        "RouteSupportRequest": [
            "authorization is accepted before routing",
            "profile and evidence identifiers close exactly",
            "observed evidence type and unit match each criterion",
            "approved configuration binds profile and policy",
        ],
        "SupportRoutingResult": [
            "every routing dimension is assessed",
            "blocking assessments determine supported versus abstained",
            "provenance and result digest bind privacy-minimized content",
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
        "rawPayloadInOutput": False,
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus deterministic M01-07 rules",
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
