"""JSON Schema 2020-12 exports for M02-06 identification harmonization."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_06.v1 import (
    M0206_MAX_CANONICAL_REQUEST_BYTES,
    HarmonizedIdentificationValue,
    HarmonizeIdentificationEvidenceRequest,
    IdentificationAbundanceObservation,
    IdentificationHarmonizationPolicy,
    IdentificationHarmonizationPrerequisites,
    IdentificationHarmonizationProfile,
    IdentificationHarmonizationResult,
    IdentificationTransformationManifest,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-06:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ContractName = Literal[
    "request",
    "output",
    "prerequisites",
    "profile",
    "policy",
    "observation",
    "value",
    "manifest",
]
_CONTRACTS: Final = {
    "request": HarmonizeIdentificationEvidenceRequest,
    "output": IdentificationHarmonizationResult,
    "prerequisites": IdentificationHarmonizationPrerequisites,
    "profile": IdentificationHarmonizationProfile,
    "policy": IdentificationHarmonizationPolicy,
    "observation": IdentificationAbundanceObservation,
    "value": HarmonizedIdentificationValue,
    "manifest": IdentificationTransformationManifest,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": "GLIO-PROTEOGEN-M02-06",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0206_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
