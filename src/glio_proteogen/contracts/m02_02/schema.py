"""JSON Schema 2020-12 exports for M02-02 identity-binding contracts."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_02.v1 import (
    IdentificationArtifactBinding,
    IdentityBindingEvaluation,
    IdentityBindingFinding,
    IdentityBindingPolicy,
    ValidateIdentityBindingsRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-02:1.0.0"
ContractName = Literal["request", "output", "policy", "binding", "finding"]
_CONTRACTS: Final = {
    "request": ValidateIdentityBindingsRequest,
    "output": IdentityBindingEvaluation,
    "policy": IdentityBindingPolicy,
    "binding": IdentificationArtifactBinding,
    "finding": IdentityBindingFinding,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict agent-facing Draft 2020-12 schema."""

    model = _CONTRACTS[name]
    schema = TypeAdapter(model).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": "GLIO-PROTEOGEN-M02-02",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawIdentityAccepted": False,
        "identityInference": False,
    }
    return schema


__all__ = ["SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
