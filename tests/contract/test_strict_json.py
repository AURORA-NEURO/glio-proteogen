"""Locked parser and diagnostic invariants shared by every raw JSON boundary."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from glio_proteogen.kernel.strict_json import (
    MAX_VALIDATION_ERRORS,
    StrictJsonError,
    StrictJsonErrorCode,
    assert_strict_json,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

pytestmark = pytest.mark.contract
DIAGNOSTIC_LIMIT = 3


class _DiagnosticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    count: int


def _validation_error(item_count: int) -> ValidationError:
    adapter = TypeAdapter(tuple[int, ...])
    with pytest.raises(ValidationError) as captured:
        adapter.validate_python(tuple("secret-value" for _ in range(item_count)), strict=True)
    return captured.value


@pytest.mark.parametrize(
    "payload",
    ['{"value":1}', b'{"value":1}', bytearray(b'{"value":1}')],
)
def test_strict_json_accepts_every_public_payload_container(
    payload: str | bytes | bytearray,
) -> None:
    assert strict_json_loads(payload) == {"value": 1}


def test_strict_json_accepts_an_exact_byte_limit_and_counts_utf8_bytes() -> None:
    payload = '{"value":"µ"}'.encode()

    assert strict_json_loads(payload, max_bytes=len(payload)) == {"value": "µ"}
    with pytest.raises(StrictJsonError) as captured:
        strict_json_loads(payload, max_bytes=len(payload) - 1)

    assert captured.value.code is StrictJsonErrorCode.TOO_LARGE


def test_byte_cap_precedes_utf8_decoding() -> None:
    with pytest.raises(StrictJsonError) as captured:
        strict_json_loads(b"\xff\xff", max_bytes=1)

    assert captured.value.code is StrictJsonErrorCode.TOO_LARGE


def test_duplicate_keys_are_rejected_recursively_without_echoing_them() -> None:
    duplicate_key = "sensitive-duplicate-key"
    payload = f'{{"outer":{{"{duplicate_key}":1,"{duplicate_key}":1}}}}'

    with pytest.raises(StrictJsonError) as captured:
        strict_json_loads(payload)

    assert captured.value.code is StrictJsonErrorCode.DUPLICATE_KEY
    assert str(captured.value) == "duplicate JSON object key"
    assert duplicate_key not in str(captured.value)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
def test_nonfinite_numeric_extensions_are_rejected(token: str) -> None:
    with pytest.raises(StrictJsonError) as captured:
        strict_json_loads(f'{{"value":{token}}}')

    assert captured.value.code is StrictJsonErrorCode.NONFINITE_NUMBER


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b'{"value":"\xff"}', StrictJsonErrorCode.INVALID_UTF8),
        (b'{"value":', StrictJsonErrorCode.INVALID_SYNTAX),
        (b"\xef\xbb\xbf{}", StrictJsonErrorCode.INVALID_SYNTAX),
    ],
)
def test_malformed_encodings_and_syntax_have_stable_codes(
    payload: bytes,
    code: StrictJsonErrorCode,
) -> None:
    with pytest.raises(StrictJsonError) as captured:
        strict_json_loads(payload)

    assert captured.value.code is code
    assert payload.decode("utf-8", errors="ignore") not in str(captured.value)


def test_unencodable_python_text_is_rejected_as_invalid_utf8() -> None:
    with pytest.raises(StrictJsonError) as captured:
        strict_json_loads('{"value":"\ud800"}')

    assert captured.value.code is StrictJsonErrorCode.INVALID_UTF8


@pytest.mark.parametrize("invalid_limit", [0, -1, True])
def test_parser_rejects_nonpositive_or_boolean_byte_limits(invalid_limit: int) -> None:
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        strict_json_loads("{}", max_bytes=invalid_limit)


def test_assertion_helper_applies_the_same_duplicate_key_policy() -> None:
    with pytest.raises(StrictJsonError) as captured:
        assert_strict_json('{"nested":{"key":1,"key":2}}')

    assert captured.value.code is StrictJsonErrorCode.DUPLICATE_KEY


def test_strict_json_api_detail_contains_only_code_location_and_safe_message() -> None:
    error = StrictJsonError(StrictJsonErrorCode.DUPLICATE_KEY)

    assert strict_json_error_detail(error, location_prefix=("body",)) == {
        "type": "json_duplicate_key",
        "loc": ("body",),
        "msg": "duplicate JSON object key",
    }


def test_validation_diagnostics_are_deterministic_bounded_and_value_free() -> None:
    details = sanitized_validation_errors(
        _validation_error(5),
        max_errors=DIAGNOSTIC_LIMIT,
    )

    assert len(details) == DIAGNOSTIC_LIMIT
    assert details[-1] == {
        "type": "validation_errors_truncated",
        "loc": (),
        "msg": "Additional validation errors were omitted at the deterministic limit.",
    }
    rendered = repr(details)
    assert "secret-value" not in rendered
    assert "input" not in rendered
    assert details[:2] == sorted(
        details[:2],
        key=lambda item: json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )


def test_default_validation_error_cap_is_locked() -> None:
    details = sanitized_validation_errors(_validation_error(MAX_VALIDATION_ERRORS + 50))

    assert len(details) == MAX_VALIDATION_ERRORS
    assert details[-1]["type"] == "validation_errors_truncated"


def test_validation_diagnostics_redact_values_and_unknown_field_names() -> None:
    canary_field = "canary-field-" + ("Q" * 16)
    canary_value = "canary-value-" + ("R" * 16)
    with pytest.raises(ValidationError) as captured:
        _DiagnosticModel.model_validate(
            {"count": canary_value, canary_field: canary_value},
        )

    details = sanitized_validation_errors(captured.value)
    rendered = repr(details)

    assert {tuple(detail["loc"]) for detail in details} == {
        ("count",),
        ("<unknown-field>",),
    }
    assert canary_field not in rendered
    assert canary_value not in rendered


@pytest.mark.parametrize("invalid_limit", [0, -1, True])
def test_diagnostic_renderer_rejects_invalid_error_limits(invalid_limit: int) -> None:
    with pytest.raises(ValueError, match="max_errors must be positive"):
        sanitized_validation_errors(_validation_error(1), max_errors=invalid_limit)
