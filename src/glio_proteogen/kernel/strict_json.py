"""Bounded, duplicate-safe JSON parsing and sanitized validation diagnostics."""

from __future__ import annotations

import json
import math
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    from pydantic import ValidationError

MAX_JSON_BYTES: Final = 4 * 1024 * 1024
MAX_VALIDATION_ERRORS: Final = 256
_TRUNCATION_MESSAGE: Final = (
    "Additional validation errors were omitted at the deterministic limit."
)

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type ErrorLocation = tuple[str | int, ...]


class StrictJsonErrorCode(StrEnum):
    """Stable machine-readable reasons for rejecting a raw JSON document."""

    TOO_LARGE = "json_too_large"
    INVALID_UTF8 = "json_invalid_utf8"
    INVALID_SYNTAX = "json_invalid_syntax"
    DUPLICATE_KEY = "json_duplicate_key"
    NONFINITE_NUMBER = "json_nonfinite_number"


_ERROR_MESSAGES: Final = {
    StrictJsonErrorCode.TOO_LARGE: "JSON input exceeds the byte limit",
    StrictJsonErrorCode.INVALID_UTF8: "JSON input must be valid UTF-8",
    StrictJsonErrorCode.INVALID_SYNTAX: "invalid JSON document",
    StrictJsonErrorCode.DUPLICATE_KEY: "duplicate JSON object key",
    StrictJsonErrorCode.NONFINITE_NUMBER: "JSON numbers must be finite",
}


class StrictJsonError(ValueError):
    """Sanitized parse failure that never embeds submitted keys or values."""

    def __init__(self, code: StrictJsonErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


class _InvalidLimitError(ValueError):
    def __init__(self, name: str) -> None:
        super().__init__(f"{name} must be positive")


def _reject_duplicate_keys(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(StrictJsonErrorCode.DUPLICATE_KEY)
        result[key] = value
    return result


def _reject_nonfinite(_token: str) -> None:
    raise StrictJsonError(StrictJsonErrorCode.NONFINITE_NUMBER)


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise StrictJsonError(StrictJsonErrorCode.NONFINITE_NUMBER)
    return value


def strict_json_loads(
    payload: bytes | bytearray | str,
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> JsonValue:
    """Decode one bounded RFC 8259 document, rejecting duplicate object members."""

    if isinstance(max_bytes, bool) or max_bytes < 1:
        raise _InvalidLimitError("max_bytes")
    if len(payload) > max_bytes:
        raise StrictJsonError(StrictJsonErrorCode.TOO_LARGE)
    encoded = b""
    text = ""
    invalid_encoding = False
    try:
        if isinstance(payload, str):
            encoded = payload.encode("utf-8")
            text = payload
        else:
            encoded = bytes(payload)
            text = encoded.decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        invalid_encoding = True
    if invalid_encoding:
        raise StrictJsonError(StrictJsonErrorCode.INVALID_UTF8)
    if len(encoded) > max_bytes:
        raise StrictJsonError(StrictJsonErrorCode.TOO_LARGE)
    decoded: Any = None
    invalid_syntax = False
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_finite_float,
        )
    except StrictJsonError:
        raise
    except (RecursionError, ValueError, json.JSONDecodeError):
        invalid_syntax = True
    if invalid_syntax:
        raise StrictJsonError(StrictJsonErrorCode.INVALID_SYNTAX)
    return cast("JsonValue", decoded)


def assert_strict_json(
    payload: bytes | bytearray | str,
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> None:
    """Validate raw JSON without retaining its decoded representation."""

    strict_json_loads(payload, max_bytes=max_bytes)


def strict_json_error_detail(
    error: StrictJsonError,
    *,
    location_prefix: ErrorLocation = (),
) -> dict[str, object]:
    """Return one stable API/CLI diagnostic for a strict JSON failure."""

    return {
        "type": error.code.value,
        "loc": location_prefix,
        "msg": str(error),
    }


def sanitized_validation_errors(
    error: ValidationError,
    *,
    location_prefix: ErrorLocation = (),
    max_errors: int = MAX_VALIDATION_ERRORS,
) -> list[dict[str, object]]:
    """Return deterministic, bounded Pydantic diagnostics without submitted inputs."""

    if isinstance(max_errors, bool) or max_errors < 1:
        raise _InvalidLimitError("max_errors")
    details: list[dict[str, object]] = []
    raw_errors = error.errors(
        include_context=False,
        include_input=False,
        include_url=False,
    )
    for item in raw_errors:
        error_type = item["type"]
        location = tuple(item["loc"])
        if error_type == "extra_forbidden" and location:
            location = (*location[:-1], "<unknown-field>")
        details.append(
            {
                "type": error_type,
                "loc": (*location_prefix, *location),
                "msg": "request does not match the declared contract",
            }
        )
    details.sort(
        key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    if len(details) <= max_errors:
        return details
    marker: dict[str, object] = {
        "type": "validation_errors_truncated",
        "loc": location_prefix,
        "msg": _TRUNCATION_MESSAGE,
    }
    return [*details[: max_errors - 1], marker]


__all__ = [
    "MAX_JSON_BYTES",
    "MAX_VALIDATION_ERRORS",
    "JsonValue",
    "StrictJsonError",
    "StrictJsonErrorCode",
    "assert_strict_json",
    "sanitized_validation_errors",
    "strict_json_error_detail",
    "strict_json_loads",
]
