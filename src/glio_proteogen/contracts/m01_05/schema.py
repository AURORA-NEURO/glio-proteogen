"""JSON Schema 2020-12 exports for M01-05 artifact detection."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_05.v1 import (
    ArtifactDetectionPolicy,
    ArtifactDetectionResult,
    ArtifactFlag,
    ArtifactRule,
    DetectArtifactsRequest,
    DetectorProfile,
    SignalObservation,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-05:1.0.0"

ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "rule",
    "signal",
    "flag",
]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(DetectArtifactsRequest),
    "output": TypeAdapter(ArtifactDetectionResult),
    "policy": TypeAdapter(ArtifactDetectionPolicy),
    "profile": TypeAdapter(DetectorProfile),
    "rule": TypeAdapter(ArtifactRule),
    "signal": TypeAdapter(SignalObservation),
    "flag": TypeAdapter(ArtifactFlag),
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
        ("DetectArtifactsRequest", "rules", "/rule_id"),
        ("DetectArtifactsRequest", "signals", "/target_id+/signal_id"),
        ("ArtifactDetectionResult", "flags", "/target_id+/artifact_class"),
        ("ArtifactDetectionResult", "limitations", "/code"),
        ("ProvenanceRecord", "control_decisions", "/role"),
    ):
        _mark_unique(schema, model, field, pointer)
    for model, fields in (
        ("DetectorProfile", ("required_rule_ids",)),
        ("ArtifactDetectionPolicy", ("enabled_classes",)),
        ("ArtifactFlag", ("rule_ids",)),
        ("FlagProvenance", ("rule_digests", "signal_digests")),
        ("ExclusionMask", ("excluded_target_ids", "review_target_ids")),
    ):
        definition = _definition(schema, model)
        if definition is None:
            continue
        for field in fields:
            array = definition.get("properties", {}).get(field)
            if isinstance(array, dict):
                array["uniqueItems"] = True
    relations = {
        "DetectArtifactsRequest": [
            "authorization is accepted before artifact detection",
            "profile, policy, and rules are bound by the approved configuration digest",
            "rule and signal references are closed over the request",
            "derived flag and provenance counts fit the public result limits",
        ],
        "ArtifactFlag": [
            "posterior state and flag disposition agree",
            "flag provenance binds exact configuration, rule, and signal digests",
        ],
        "ArtifactDetectionResult": [
            "flags determine the exclusion mask and overall disposition",
            "provenance binds request, configuration, rules, and signals",
            "result digest matches canonical privacy-minimized content",
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
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus deterministic M01-05 rules",
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
