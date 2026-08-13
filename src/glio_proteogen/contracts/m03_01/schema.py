"""JSON Schema 2020-12 exports for M03-01."""

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_01.v1 import (
    AmbiguityReportingPolicy,
    EvaluateProteinInferenceProtocolRequest,
    ProteinInferenceProtocolConformanceResult,
    ProteinInferenceProtocolReceipt,
    ProteinInferenceProtocolSchema,
    ReviewedProteinInferenceConformanceProfile,
    SearchSpaceReceipt,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-01:1.0.0"
CONTRACT_VERSION: Final = "1.0.0"
ContractName = Literal[
    "request",
    "output",
    "protocol",
    "profile",
    "search-space",
    "ambiguity",
    "receipt",
]
_CONTRACTS: Final = {
    "request": EvaluateProteinInferenceProtocolRequest,
    "output": ProteinInferenceProtocolConformanceResult,
    "protocol": ProteinInferenceProtocolSchema,
    "profile": ReviewedProteinInferenceConformanceProfile,
    "search-space": SearchSpaceReceipt,
    "ambiguity": AmbiguityReportingPolicy,
    "receipt": ProteinInferenceProtocolReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": "GLIO-PROTEOGEN-M03-01",
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayload": False,
        "observedPeptideAssignment": False,
        "proteinInference": False,
        "biologicalInterpretation": False,
    }
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
