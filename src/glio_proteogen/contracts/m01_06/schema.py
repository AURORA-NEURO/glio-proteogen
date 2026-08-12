"""JSON Schema 2020-12 exports for M01-06 harmonization."""

from __future__ import annotations

from typing import Any, Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_06.v1 import (
    BiologicalInvariant,
    HarmonizationPolicy,
    HarmonizationProfile,
    HarmonizationResult,
    HarmonizedValue,
    HarmonizeObservationsRequest,
    StageTransformation,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-06:1.0.0"

ContractName = Literal[
    "request",
    "output",
    "policy",
    "profile",
    "invariant",
    "value",
    "transformation",
]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(HarmonizeObservationsRequest),
    "output": TypeAdapter(HarmonizationResult),
    "policy": TypeAdapter(HarmonizationPolicy),
    "profile": TypeAdapter(HarmonizationProfile),
    "invariant": TypeAdapter(BiologicalInvariant),
    "value": TypeAdapter(HarmonizedValue),
    "transformation": TypeAdapter(StageTransformation),
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    generated = _ADAPTERS[name].json_schema(mode="validation")
    exported: dict[str, Any] = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_PREFIX}:{name}",
        **generated,
        "x-glio-validation-profile": {
            "id": f"{SCHEMA_ID_PREFIX}:runtime-conformance",
            "strictJson": True,
            "silentCoercion": False,
            "rawPayloadInOutput": False,
            "authoritativeRuntime": "Pydantic-v2 strict contracts plus deterministic M01-06",
        },
    }
    return cast("dict[str, object]", exported)


__all__ = [
    "CONTRACT_VERSION",
    "JSON_SCHEMA_DIALECT",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
]
