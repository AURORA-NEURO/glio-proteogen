"""JSON Schema 2020-12 exports for M02-03 identification raw ingestion."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m02_03.v1 import (
    BundleDiagnostic,
    IdentificationIngestionPolicy,
    IdentificationRawIngestionResult,
    IdentificationRawSource,
    IngestIdentificationRawInputsRequest,
    RoleFormatRequirement,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M02-03:1.0.0"
ContractName = Literal[
    "request",
    "output",
    "policy",
    "source",
    "role_requirement",
    "bundle_diagnostic",
]
_CONTRACTS: Final = {
    "request": IngestIdentificationRawInputsRequest,
    "output": IdentificationRawIngestionResult,
    "policy": IdentificationIngestionPolicy,
    "source": IdentificationRawSource,
    "role_requirement": RoleFormatRequirement,
    "bundle_diagnostic": BundleDiagnostic,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict agent-facing Draft 2020-12 schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    schema["x-glio-contract"] = {
        "moduleId": "GLIO-PROTEOGEN-M02-03",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawPayloadInSchema": False,
        "biologicalInterpretation": False,
    }
    return schema


__all__ = ["SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
