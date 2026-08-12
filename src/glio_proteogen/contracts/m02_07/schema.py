"""JSON Schema 2020-12 exports for M02-07 joint support routing."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_07.v1 import (
    M0207_MAX_CANONICAL_REQUEST_BYTES,
    DeclaredSupportFact,
    IdentificationAbstention,
    IdentificationSupportEnvelope,
    IdentificationSupportPolicy,
    IdentificationSupportPrerequisites,
    IdentificationSupportProfile,
    IdentificationSupportRouteResult,
    RouteIdentificationSupportRequest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-07:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ContractName = Literal[
    "request",
    "output",
    "prerequisites",
    "profile",
    "policy",
    "declaration",
    "envelope",
    "abstention",
]
_CONTRACTS: Final = {
    "request": RouteIdentificationSupportRequest,
    "output": IdentificationSupportRouteResult,
    "prerequisites": IdentificationSupportPrerequisites,
    "profile": IdentificationSupportProfile,
    "policy": IdentificationSupportPolicy,
    "declaration": DeclaredSupportFact,
    "envelope": IdentificationSupportEnvelope,
    "abstention": IdentificationAbstention,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M02-07",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
        "jointEnvelopeRequired": True,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0207_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
