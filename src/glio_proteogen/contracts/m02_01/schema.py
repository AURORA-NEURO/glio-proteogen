"""JSON Schema 2020-12 exports for M02-01 conformance contracts."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_01.v1 import (
    ConformanceEvaluation,
    ConformanceProfile,
    EvaluateConformanceRequest,
    FieldObservation,
    ProtocolSchema,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-01:1.0.0"
ContractName = Literal["request", "output", "schema", "profile", "observation"]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(EvaluateConformanceRequest),
    "output": TypeAdapter(ConformanceEvaluation),
    "schema": TypeAdapter(ProtocolSchema),
    "profile": TypeAdapter(ConformanceProfile),
    "observation": TypeAdapter(FieldObservation),
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    generated = _ADAPTERS[name].json_schema(mode="validation")
    generated = {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_ID_PREFIX}:{name}",
        **generated,
        "x-glio-validation-profile": {
            "strictJson": True,
            "silentCoercion": False,
            "rawPayloadInOutput": False,
            "authoritativeRuntime": "Pydantic-v2 strict contracts plus deterministic M02-01 rules",
        },
    }
    return cast("dict[str, object]", generated)


__all__ = [
    "CONTRACT_VERSION",
    "JSON_SCHEMA_DIALECT",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "contract_json_schema",
]
