"""Semantic canonicalization for M05-03 raw-input ingestion contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel

from glio_proteogen.contracts.m05_02 import (
    normalized_result_payload as normalized_m0502_result_payload,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest

if TYPE_CHECKING:
    from glio_proteogen.kernel.models import Sha256Digest

_ZERO_DIGEST = "sha256:" + ("0" * 64)


def _python(value: Any) -> Any:  # noqa: ANN401 - recursive canonical JSON shape.
    """Copy one semantic value without invoking caller-overridable traversal hooks."""

    value_type = type(value)
    value_mro = type.__getattribute__(value_type, "__mro__")
    if BaseModel in value_mro:
        storage = object.__getattribute__(value, "__dict__")
        if type(storage) is not dict or any(type(key) is not str for key in dict.keys(storage)):
            raise TypeError("M05-03 model storage must use exact string keys")
        return {key: _python(dict.__getitem__(storage, key)) for key in dict.keys(storage)}
    if value_type is dict:
        mapping = cast("dict[object, object]", value)
        if any(type(key) is not str for key in dict.keys(mapping)):
            raise TypeError("M05-03 canonical objects require exact string keys")
        return {
            cast("str", key): _python(dict.__getitem__(mapping, key)) for key in dict.keys(mapping)
        }
    if value_type is list:
        return tuple(_python(item) for item in list.__iter__(value))
    if value_type is tuple:
        return tuple(_python(item) for item in tuple.__iter__(value))
    if Enum in value_mro:
        return _python(object.__getattribute__(value, "_value_"))
    if value is None or value_type in {bool, int, float, str, bytes, date, datetime}:
        return value
    if dict in value_mro or list in value_mro or tuple in value_mro:
        raise TypeError("M05-03 canonical collections must be exact built-ins")
    raise TypeError(f"unsupported M05-03 canonical value: {value_type.__name__}")


def _dump(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _python(value)
    if type(data) is not dict:
        raise TypeError("M05-03 canonical model payload must be an object")
    return cast("dict[str, Any]", data)


def _sequence(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    if type(values) is list:
        return tuple(list.__iter__(values))
    if type(values) is tuple:
        return tuple.__getitem__(values, slice(None))
    raise TypeError("M05-03 canonical collections must be exact lists or tuples")


def _sorted(values: list[Any] | tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(sorted(_sequence(values), key=canonical_json_bytes))


def normalized_parser(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return one parser profile's stable semantic payload."""

    return _dump(value)


def parser_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_parser(value))


def normalized_policy(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["approved_parsers"] = _sorted(data["approved_parsers"])
    return data


def policy_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_policy(value))


def configuration_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest({"policy_digest": policy_digest(value)})


def normalized_artifact(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def artifact_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_artifact(value))


def artifact_mapping_digest(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> Sha256Digest:
    """Bind the complete canonical four-role artifact mapping."""

    return sha256_digest(_sorted(tuple(normalized_artifact(item) for item in _sequence(values))))


def normalized_document(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    if "vocabularies" in data:
        data["vocabularies"] = _sorted(data["vocabularies"])
    return data


def document_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_document(value))


def normalized_lineage_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    source = _dump(value)
    data = normalized_m0502_result_payload(source)
    data["result_digest"] = source["result_digest"]
    return data


def normalized_request(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["lineage_result"] = normalized_lineage_result(data["lineage_result"])
    data["policy"] = normalized_policy(data["policy"])
    data["artifacts"] = _sorted(data["artifacts"])
    return data


def canonical_request_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_request(value))


def context_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    data = _dump(value)
    context = data.get("context", data)
    return sha256_digest(context)


def normalized_validated_input(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["document"] = normalized_document(data["document"])
    data["diagnostic_codes"] = _sorted(data["diagnostic_codes"])
    return data


def validated_input_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_validated_input(value))


def validated_inputs_digest(
    values: tuple[BaseModel | dict[str, Any], ...] | list[BaseModel | dict[str, Any]],
) -> Sha256Digest:
    """Bind the canonical zero-or-four validated-input region."""

    return sha256_digest(
        _sorted(tuple(normalized_validated_input(item) for item in _sequence(values)))
    )


def normalized_diagnostic(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return _dump(value)


def diagnostic_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_diagnostic(value))


def normalized_receipt(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    data = _dump(value)
    data["receipt_digest"] = _ZERO_DIGEST
    data["diagnostic_codes"] = _sorted(data["diagnostic_codes"])
    return data


def receipt_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_receipt(value))


def normalized_result_payload(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    source = _dump(value)
    data = deepcopy(source)
    data["result_digest"] = _ZERO_DIGEST
    data["request"] = normalized_request(data["request"])
    data["receipt"] = normalized_receipt(data["receipt"])
    data["receipt"]["receipt_digest"] = source["receipt"]["receipt_digest"]
    data["validated_inputs"] = _sorted(
        tuple(normalized_validated_input(item) for item in data["validated_inputs"])
    )
    data["diagnostics"] = _sorted(data["diagnostics"])
    data["evidence"] = _sorted(data["evidence"])
    data["limitations"] = _sorted(data["limitations"])
    data["provenance"]["input_digests"] = _sorted(data["provenance"]["input_digests"])
    data["provenance"]["control_decisions"] = _sorted(data["provenance"]["control_decisions"])
    data["uncertainty"]["sensitivity_notes"] = _sorted(data["uncertainty"]["sensitivity_notes"])
    return data


def normalized_result(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """Return the canonical result envelope while retaining its final digest."""

    data = normalized_result_payload(value)
    data["result_digest"] = _dump(value)["result_digest"]
    return data


def result_payload_digest(value: BaseModel | dict[str, Any]) -> Sha256Digest:
    return sha256_digest(normalized_result_payload(value))


__all__ = [
    "artifact_digest",
    "artifact_mapping_digest",
    "canonical_request_digest",
    "configuration_digest",
    "context_digest",
    "diagnostic_digest",
    "document_digest",
    "normalized_artifact",
    "normalized_diagnostic",
    "normalized_document",
    "normalized_lineage_result",
    "normalized_parser",
    "normalized_policy",
    "normalized_receipt",
    "normalized_request",
    "normalized_result",
    "normalized_result_payload",
    "normalized_validated_input",
    "parser_digest",
    "policy_digest",
    "receipt_digest",
    "result_payload_digest",
    "validated_input_digest",
    "validated_inputs_digest",
]
