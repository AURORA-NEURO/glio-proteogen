"""Semantic canonicalization for M02-01 protocol conformance."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel as RuntimeBaseModel

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from pydantic import BaseModel

    from glio_proteogen.kernel.models import Sha256Digest


def _sort(values: list[Any] | tuple[Any, ...]) -> list[Any]:
    return sorted(values, key=canonical_json_bytes)


def normalized_schema(schema: BaseModel) -> dict[str, Any]:
    value = schema.model_dump(mode="python", by_alias=True, exclude_none=False)
    for vocabulary in value["vocabularies"]:
        vocabulary["terms"] = _sort(vocabulary["terms"])
    for rule in value["compatibility_rules"]:
        for field in ("allowed_terms", "trigger_terms", "allowed_pairs"):
            if field in rule:
                rule[field] = _sort(rule[field])
    for field in ("fields", "vocabularies", "units", "compatibility_rules"):
        value[field] = _sort(value[field])
    return value


def schema_digest(schema: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_schema(schema))


def normalized_profile(profile: BaseModel) -> dict[str, Any]:
    return profile.model_dump(mode="python", by_alias=True, exclude_none=False)


def profile_digest(profile: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_profile(profile))


def configuration_digest(schema: BaseModel, profile: BaseModel) -> Sha256Digest:
    return sha256_digest(
        {"schema": normalized_schema(schema), "profile": normalized_profile(profile)}
    )


def normalized_request(request: BaseModel) -> dict[str, Any]:
    value = request.model_dump(mode="python", by_alias=True, exclude_none=False)
    value["protocol_schema"] = normalized_schema(value_model(request, "protocol_schema"))
    value["conformance_profile"] = normalized_profile(
        value_model(request, "conformance_profile")
    )
    for observation in value["observations"]:
        observation["values"] = _sort(observation["values"])
        observation["evidence"] = _sort(observation["evidence"])
    value["observations"] = _sort(value["observations"])
    return value


def value_model(parent: BaseModel, field: str) -> BaseModel:
    value = getattr(parent, field)
    if not isinstance(value, RuntimeBaseModel):
        raise TypeError(f"{field} must be a model")
    return value


def canonical_request_digest(request: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_request(request))


def normalized_result_payload(result: BaseModel) -> dict[str, Any]:
    value = result.model_dump(mode="python", by_alias=True, exclude_none=False)
    value.pop("evaluation_digest", None)
    for field in ("field_evaluations", "rule_evaluations", "evidence", "limitations"):
        value[field] = _sort(value[field])
    value["provenance"]["input_digests"] = _sort(
        value["provenance"]["input_digests"]
    )
    value["provenance"]["control_decisions"] = _sort(
        value["provenance"]["control_decisions"]
    )
    return value


def result_payload_digest(result: BaseModel) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(result))


__all__ = [
    "canonical_request_digest",
    "configuration_digest",
    "normalized_profile",
    "normalized_request",
    "normalized_result_payload",
    "normalized_schema",
    "profile_digest",
    "result_payload_digest",
    "schema_digest",
]
