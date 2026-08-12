"""JSON Schema 2020-12 exports for M01-08 release packaging."""

from __future__ import annotations

from typing import Final, Literal, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_08.v1 import (
    BuildReleasePackageRequest,
    ReleasePackagingPolicy,
    ReleasePackagingResult,
    ReproducibilityManifest,
)

CONTRACT_VERSION: Final = "1.0.0"
JSON_SCHEMA_DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M01-08:1.0.0"
ContractName = Literal["request", "output", "policy", "manifest"]

_ADAPTERS: Final[dict[ContractName, TypeAdapter[object]]] = {
    "request": TypeAdapter(BuildReleasePackageRequest),
    "output": TypeAdapter(ReleasePackagingResult),
    "policy": TypeAdapter(ReleasePackagingPolicy),
    "manifest": TypeAdapter(ReproducibilityManifest),
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
            "authoritativeRuntime": "Pydantic-v2 strict contracts plus deterministic M01-08 rules",
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
