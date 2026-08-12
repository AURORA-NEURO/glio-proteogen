"""JSON Schema 2020-12 exports for M02-08 identification release packaging."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_08.v1 import (
    M0208_MAX_CANONICAL_REQUEST_BYTES,
    BuildIdentificationQcReleaseRequest,
    ExternalIdentificationSignature,
    IdentificationQcReleaseResult,
    IdentificationQcReproducibilityManifest,
    IdentificationReleaseArtifact,
    IdentificationReleasePolicy,
    IdentificationReleaseVerification,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-08:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ContractName = Literal[
    "request",
    "output",
    "policy",
    "artifact",
    "manifest",
    "verification",
    "signature",
]
_CONTRACTS: Final = {
    "request": BuildIdentificationQcReleaseRequest,
    "output": IdentificationQcReleaseResult,
    "policy": IdentificationReleasePolicy,
    "artifact": IdentificationReleaseArtifact,
    "manifest": IdentificationQcReproducibilityManifest,
    "verification": IdentificationReleaseVerification,
    "signature": ExternalIdentificationSignature,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M02-08",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
        "exactByteReproduction": True,
        "signatureAuthorityOwnedExternally": True,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0208_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
