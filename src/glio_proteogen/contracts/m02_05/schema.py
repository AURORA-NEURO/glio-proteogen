"""JSON Schema 2020-12 exports for M02-05 identification-artifact detection."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_05.v1 import (
    DetectIdentificationArtifactsRequest,
    IdentificationArtifactDetectionResult,
    IdentificationArtifactFlag,
    IdentificationArtifactPolicy,
    IdentificationArtifactProfile,
    IdentificationSignalObservation,
    RuleEvaluationTrace,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-05:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ContractName = Literal[
    "request",
    "output",
    "profile",
    "policy",
    "signal",
    "flag",
    "evaluation",
]
_CONTRACTS: Final = {
    "request": DetectIdentificationArtifactsRequest,
    "output": IdentificationArtifactDetectionResult,
    "profile": IdentificationArtifactProfile,
    "policy": IdentificationArtifactPolicy,
    "signal": IdentificationSignalObservation,
    "flag": IdentificationArtifactFlag,
    "evaluation": RuleEvaluationTrace,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": "GLIO-PROTEOGEN-M02-05",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
    }
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
