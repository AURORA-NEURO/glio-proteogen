"""Semantic canonicalization for M01-03 request and result identities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_policy(policy: BaseModel) -> dict[str, Any]:
    value = policy.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["allowed_formats"] = _sort(value["allowed_formats"])
    value["allowed_compressions"] = _sort(value["allowed_compressions"])
    return value


def policy_digest(policy: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_policy(policy))


def normalized_source_descriptor(source: BaseModel) -> dict[str, Any]:
    return source.model_dump(mode="python", by_alias=True, exclude_none=False)


def source_descriptor_digest(source: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_source_descriptor(source))


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["policy"]["allowed_formats"] = _sort(value["policy"]["allowed_formats"])
    value["policy"]["allowed_compressions"] = _sort(
        value["policy"]["allowed_compressions"]
    )
    value["sources"] = _sort(value["sources"])
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("result_digest", None)
    for raw_input in value["raw_inputs"]:
        for diagnostic in raw_input["diagnostics"]:
            diagnostic["evidence"] = _sort(diagnostic["evidence"])
        raw_input["diagnostics"] = _sort(raw_input["diagnostics"])
    value["raw_inputs"] = _sort(value["raw_inputs"])
    value["provenance"]["input_digests"] = _sort(value["provenance"]["input_digests"])
    value["provenance"]["control_decisions"] = _sort(
        value["provenance"]["control_decisions"]
    )
    value["evidence"] = _sort(value["evidence"])
    value["limitations"] = _sort(value["limitations"])
    return value


def result_payload_digest(result: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "canonical_request_digest",
    "normalized_policy",
    "normalized_request",
    "normalized_result_payload",
    "normalized_source_descriptor",
    "policy_digest",
    "result_payload_digest",
    "source_descriptor_digest",
]
