"""Deterministic M05-01 PTM-localization protocol conformance engine."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m05_01 import (
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    M0501_MAX_COMPATIBILITY_RULES,
    M0501_MAX_METADATA_FIELDS,
    M0501_MAX_UNIT_POLICIES,
    M0501_MAX_VOCABULARY_TERMS,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationProtocolConformanceResult,
    expected_protocol_result,
    preflight_authorized,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes

_AUTHORIZATION_MESSAGE: Final = (
    "PTM-localization protocol conformance requires accepted upstream controls"
)
_REQUEST_ADAPTER: Final = TypeAdapter(EvaluatePtmLocalizationProtocolRequest)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_NODES: Final = 100_000
_MAX_PLAIN_SEQUENCE: Final = max(
    M0501_MAX_VOCABULARY_TERMS,
    M0501_MAX_COMPATIBILITY_RULES,
    M0501_MAX_METADATA_FIELDS,
    M0501_MAX_UNIT_POLICIES,
)
_REQUEST_FIELDS: Final = frozenset(
    {
        "operation",
        "contract_version",
        "request_id",
        "context",
        "protocol_schema",
        "conformance_profile",
        "supersedes_result_digest",
    }
)


class PtmLocalizationProtocolAuthorizationError(PermissionError):
    """Authorization failed before protocol or profile declarations were read."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class PtmLocalizationProtocolInputError(ValueError):
    """An authorized request failed closed without reflecting caller content."""

    def __init__(self) -> None:
        super().__init__("M05-01 request failed strict validation")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M05-01 strict request values require exact built-in containers")


class _SerializedRequestTooLargeError(ValueError):
    def __init__(self) -> None:
        super().__init__("M05-01 canonical request exceeds its byte limit")


class M0501PtmLocalizationProtocolEngine:
    """Validate declarations and assemble only the exact conformance envelope."""

    __slots__ = ()

    def evaluate(self, request: object) -> PtmLocalizationProtocolConformanceResult:
        validated = _validate_prepared_request(_prepare_request_candidate(request))
        return self._evaluate_validated(validated)

    @staticmethod
    def _evaluate_validated(
        request: EvaluatePtmLocalizationProtocolRequest,
    ) -> PtmLocalizationProtocolConformanceResult:
        result = expected_protocol_result(request)
        return PtmLocalizationProtocolConformanceResult.model_validate(
            result.model_dump(mode="python", exclude_none=False),
            strict=True,
        )


def evaluate_ptm_localization_protocol(
    request: object,
) -> PtmLocalizationProtocolConformanceResult:
    """Public stateless M05-01 operation."""

    return M0501PtmLocalizationProtocolEngine().evaluate(request)


def preflight_ptm_localization_protocol_authorization(candidate: object) -> None:
    """Check seven controls without touching protocol or profile declarations."""

    try:
        preflight_authorized(candidate)
    except Exception:  # noqa: BLE001 - hostile ordinary exceptions fail closed.
        raise PtmLocalizationProtocolAuthorizationError from None


def _prepare_request_candidate(candidate: object) -> dict[str, object]:
    preflight_ptm_localization_protocol_authorization(candidate)
    try:
        _validate_outer_request_shape(candidate)
        plain = _plain_value(candidate)
        return cast("dict[str, object]", plain)
    except _InvalidPlainValueError:
        raise
    except Exception:  # noqa: BLE001 - caller content must never escape this boundary.
        raise PtmLocalizationProtocolInputError from None


def _validate_prepared_request(
    prepared: dict[str, object],
) -> EvaluatePtmLocalizationProtocolRequest:
    try:
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(prepared), strict=True)
    except Exception:  # noqa: BLE001 - do not reflect nested caller content.
        raise PtmLocalizationProtocolInputError from None


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> EvaluatePtmLocalizationProtocolRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0501_MAX_CANONICAL_REQUEST_BYTES:
        raise _SerializedRequestTooLargeError
    return _validate_prepared_request(_prepare_request_candidate(candidate))


def _validate_outer_request_shape(candidate: object) -> None:
    if type(candidate) is EvaluatePtmLocalizationProtocolRequest:
        return
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if dict not in candidate_mro:
        raise PtmLocalizationProtocolInputError
    mapping = cast("dict[object, object]", candidate)
    if any(key not in _REQUEST_FIELDS for key in dict.keys(mapping)):
        raise PtmLocalizationProtocolInputError


def _plain_value(  # noqa: C901, PLR0912 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    candidate_mro = type.__getattribute__(type(candidate), "__mro__")
    if BaseModel in candidate_mro:
        storage = cast("dict[object, object]", object.__getattribute__(candidate, "__dict__"))
        if (
            type(storage) is not dict
            or dict.__len__(storage) > _MAX_PLAIN_DICT_ITEMS
            or any(type(key) is not str for key in dict.keys(storage))
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(storage, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(storage)
        }
    if dict in candidate_mro:
        mapping = cast("dict[object, object]", candidate)
        if dict.__len__(mapping) > _MAX_PLAIN_DICT_ITEMS or any(
            type(key) is not str for key in dict.keys(mapping)
        ):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(
                dict.__getitem__(mapping, key),
                _depth=_depth + 1,
                _budget=budget,
            )
            for key in dict.keys(mapping)
        }
    if list in candidate_mro:
        list_values = cast("list[object]", candidate)
        if list.__len__(list_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return [
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in list.__iter__(list_values)
        ]
    if tuple in candidate_mro:
        tuple_values = cast("tuple[object, ...]", candidate)
        if tuple.__len__(tuple_values) > _MAX_PLAIN_SEQUENCE:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(item, _depth=_depth + 1, _budget=budget)
            for item in tuple.__iter__(tuple_values)
        )
    if Mapping in candidate_mro:
        raise _InvalidPlainValueError
    if StrEnum in candidate_mro:
        value = object.__getattribute__(candidate, "_value_")
        if type(value) is not str:
            raise _InvalidPlainValueError
        return value
    return candidate


__all__ = [
    "M0501PtmLocalizationProtocolEngine",
    "PtmLocalizationProtocolAuthorizationError",
    "PtmLocalizationProtocolInputError",
    "evaluate_ptm_localization_protocol",
    "preflight_ptm_localization_protocol_authorization",
]
