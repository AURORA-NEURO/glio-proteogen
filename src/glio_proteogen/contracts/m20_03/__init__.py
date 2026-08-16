"""Provisional M20-03 fusion and aggregation exports."""

from glio_proteogen.contracts.m20_03.canonical import (
    canonical_request_bytes,
    canonical_request_digest,
    canonical_result_payload_bytes,
    normalized_request,
    normalized_result_payload,
    result_payload_digest,
    verify_request_digest,
    verify_result_digest,
)
from glio_proteogen.contracts.m20_03.schema import (
    CONTRACT_VERSION,
    SCHEMA_ID_PREFIX,
    ContractName,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.contracts.m20_03.v1 import *  # noqa: F403

__all__ = [
    "CONTRACT_VERSION",
    "SCHEMA_ID_PREFIX",
    "ContractName",
    "canonical_request_bytes",
    "canonical_request_digest",
    "canonical_result_payload_bytes",
    "contract_json_schema",
    "contract_json_schemas",
    "normalized_request",
    "normalized_result_payload",
    "result_payload_digest",
    "verify_request_digest",
    "verify_result_digest",
]
