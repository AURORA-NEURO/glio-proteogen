"""JSON Schema 2020-12 exports for M03-03 raw-source admission."""

from __future__ import annotations

from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m03_03.v1 import (
    M0303_CONTRACT_VERSION,
    M0303_MAX_CANONICAL_REQUEST_BYTES,
    M0303_MODULE_ID,
    IngestProteinInferenceRawInputsRequest,
    ProteinInferenceLineageIngestionReceipt,
    ProteinInferenceProtocolIngestionReceipt,
    ProteinInferenceRawAdmissionReceipt,
    ProteinInferenceRawAdmissionResult,
    ProteinInferenceRawPolicy,
    ProteinInferenceRawSource,
    ValidatedProteinInferenceRawInput,
)

SCHEMA_ID_PREFIX: Final = "urn:aurora-neuro:glio-proteogen:GLIO-PROTEOGEN-M03-03:1.0.0"
CONTRACT_VERSION: Final = M0303_CONTRACT_VERSION
ContractName = Literal[
    "request",
    "output",
    "policy",
    "source",
    "protocol-receipt",
    "lineage-receipt",
    "raw-input",
    "receipt",
]
_CONTRACTS: Final = {
    "request": IngestProteinInferenceRawInputsRequest,
    "output": ProteinInferenceRawAdmissionResult,
    "policy": ProteinInferenceRawPolicy,
    "source": ProteinInferenceRawSource,
    "protocol-receipt": ProteinInferenceProtocolIngestionReceipt,
    "lineage-receipt": ProteinInferenceLineageIngestionReceipt,
    "raw-input": ValidatedProteinInferenceRawInput,
    "receipt": ProteinInferenceRawAdmissionReceipt,
}


def contract_json_schema(name: ContractName) -> dict[str, object]:
    """Return one strict, metadata-only Draft 2020-12 contract schema."""

    schema = TypeAdapter(_CONTRACTS[name]).json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{SCHEMA_ID_PREFIX}:{name}"
    metadata: dict[str, object] = {
        "moduleId": M0303_MODULE_ID,
        "contractVersion": CONTRACT_VERSION,
        "strict": True,
        "rawPayloadInSchema": False,
        "identityInference": False,
        "proteinInference": False,
        "complexActivityInference": False,
        "kinaseActivityInference": False,
    }
    if name == "request":
        metadata["maxRequestBytes"] = M0303_MAX_CANONICAL_REQUEST_BYTES
    schema["x-glio-contract"] = metadata
    return schema


__all__ = ["CONTRACT_VERSION", "SCHEMA_ID_PREFIX", "ContractName", "contract_json_schema"]
