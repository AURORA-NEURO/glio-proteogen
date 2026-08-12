"""Public contracts for M01-03 raw-format ingestion."""

from glio_proteogen.contracts.m01_03.canonical import (
    canonical_request_digest,
    policy_digest,
    result_payload_digest,
    source_descriptor_digest,
)
from glio_proteogen.contracts.m01_03.schema import (
    CONTRACT_VERSION,
    ContractName,
    contract_json_schema,
)
from glio_proteogen.contracts.m01_03.v1 import (
    M0103_CONTRACT_VERSION,
    M0103_MODULE_ID,
    Compression,
    DetectedRawFormat,
    DiagnosticAction,
    DiagnosticSeverity,
    FormatVersion,
    IngestRawInputsRequest,
    ParseDiagnostic,
    RawFormat,
    RawIngestionPolicy,
    RawIngestionResult,
    RawInputDisposition,
    RawSourceDescriptor,
    ValidatedRawInputDescriptor,
)

__all__ = [
    "CONTRACT_VERSION",
    "M0103_CONTRACT_VERSION",
    "M0103_MODULE_ID",
    "Compression",
    "ContractName",
    "DetectedRawFormat",
    "DiagnosticAction",
    "DiagnosticSeverity",
    "FormatVersion",
    "IngestRawInputsRequest",
    "ParseDiagnostic",
    "RawFormat",
    "RawIngestionPolicy",
    "RawIngestionResult",
    "RawInputDisposition",
    "RawSourceDescriptor",
    "ValidatedRawInputDescriptor",
    "canonical_request_digest",
    "contract_json_schema",
    "policy_digest",
    "result_payload_digest",
    "source_descriptor_digest",
]
