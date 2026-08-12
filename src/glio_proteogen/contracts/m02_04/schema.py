"""JSON Schema 2020-12 exports for M02-04 identification quality."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_04.v1 import (
    ComputeIdentificationQualityRequest,
    IdentificationAssayProfile,
    IdentificationMetricResult,
    IdentificationQualityPolicy,
    IdentificationQualityProfile,
    MetricObservation,
    MetricThreshold,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-04:1.0.0"
ContractName = Literal[
    "request",
    "output",
    "assay_profile",
    "policy",
    "threshold",
    "observation",
    "metric",
]
_CONTRACTS: Final = {
    "request": ComputeIdentificationQualityRequest,
    "output": IdentificationQualityProfile,
    "assay_profile": IdentificationAssayProfile,
    "policy": IdentificationQualityPolicy,
    "threshold": MetricThreshold,
    "observation": MetricObservation,
    "metric": IdentificationMetricResult,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": "GLIO-PROTEOGEN-M02-04",
        "contractVersion": "1.0.0",
        "strict": True,
        "biologicalInterpretation": False,
    }
    return schema


__all__ = ["SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
