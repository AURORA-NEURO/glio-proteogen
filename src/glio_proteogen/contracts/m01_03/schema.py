"""JSON Schema 2020-12 exports for M01-03 public contracts."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_03.v1 import (
    IngestRawInputsRequest,
    ParseDiagnostic,
    RawIngestionPolicy,
    RawIngestionResult,
    RawSourceDescriptor,
    ValidatedRawInputDescriptor,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-03:1.0.0"

ContractName = Literal["request", "output", "policy", "source", "raw_input", "diagnostic"]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(IngestRawInputsRequest),
    "output": TypeAdapter(RawIngestionResult),
    "policy": TypeAdapter(RawIngestionPolicy),
    "source": TypeAdapter(RawSourceDescriptor),
    "raw_input": TypeAdapter(ValidatedRawInputDescriptor),
    "diagnostic": TypeAdapter(ParseDiagnostic),
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
        ("IngestRawInputsRequest", "sources", "/source_id"),
        ("ValidatedRawInputDescriptor", "diagnostics", "/diagnostic_id"),
        ("RawIngestionResult", "raw_inputs", "/source_id"),
        ("RawIngestionResult", "limitations", "/code"),
        ("ProvenanceRecord", "control_decisions", "/role"),
    ):
        _mark_unique(schema, model, field, pointer)
    for model, fields in (
        ("RawIngestionPolicy", ("allowed_formats", "allowed_compressions")),
    ):
        definition = _definition(schema, model)
        if definition is None:
            continue
        for field in fields:
            array = definition.get("properties", {}).get(field)
            if isinstance(array, dict):
                array["uniqueItems"] = True
    relations = {
        "IngestRawInputsRequest": [
            "authorization is accepted before policy hashing or source access",
            "source identifiers are unique and active policy caps apply",
            "approved configuration digest binds the active policy",
        ],
        "ValidatedRawInputDescriptor": [
            "accepted inputs passed checksum, format detection, and structural validation",
            "non-accepted inputs carry typed blocking diagnostics",
        ],
        "RawIngestionResult": [
            "overall disposition, support, and review derive from source results",
            "provenance binds request, policy, and exact source digests",
            "result digest matches canonical metadata-only content",
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
        "rawContentInOutput": False,
        "authoritativeRuntime": "Pydantic-v2 strict contracts plus the M01-03 parser registry",
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
