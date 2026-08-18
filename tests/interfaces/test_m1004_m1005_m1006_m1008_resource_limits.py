"""Adversarial file and stdin ceilings for the M10-04..08 adapters."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest
from pydantic import ValidationError

from glio_proteogen.adapters import m1004, m1005, m1006, m1008
from glio_proteogen.adapters.limits import RequestBodyTooLargeError

_TEST_LIMIT = 32


class _ReaderCase(NamedTuple):
    module: Any
    reader: Callable[..., object]
    request_limit_name: str
    result_limit_name: str


@pytest.mark.parametrize(
    "case",
    [
        _ReaderCase(
            m1004,
            m1004._read_request,
            "M1004_MAX_CANONICAL_REQUEST_BYTES",
            "M1004_MAX_CANONICAL_RESULT_BYTES",
        ),
        _ReaderCase(
            m1005,
            m1005._read_request,
            "M1005_MAX_CANONICAL_REQUEST_BYTES",
            "M1005_MAX_CANONICAL_RESULT_BYTES",
        ),
        _ReaderCase(
            m1006,
            m1006._read_request,
            "M1006_MAX_CANONICAL_REQUEST_BYTES",
            "M1006_MAX_CANONICAL_RESULT_BYTES",
        ),
    ],
)
@pytest.mark.parametrize("result", [False, True])
def test_m1004_to_m1006_path_readers_reject_oversized_payloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: _ReaderCase,
    result: bool,  # noqa: FBT001
) -> None:
    monkeypatch.setattr(case.module, case.request_limit_name, _TEST_LIMIT)
    monkeypatch.setattr(case.module, case.result_limit_name, _TEST_LIMIT)
    payload = tmp_path / "oversized.json"
    payload.write_bytes(b"{" + b"x" * _TEST_LIMIT + b"}")

    with pytest.raises(RequestBodyTooLargeError):
        case.reader(payload, result=result)


@pytest.mark.parametrize(
    "reader",
    [m1004._read_request, m1005._read_request, m1006._read_request],
)
def test_m1004_to_m1006_path_readers_never_call_unbounded_read_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    reader: Callable[..., object],
) -> None:
    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    payload = tmp_path / "request.json"
    payload.write_bytes(b"{}")

    with pytest.raises(ValidationError):
        reader(payload)


@pytest.mark.parametrize("loader", [m1008._load_request_path, m1008._load_result_path])
def test_m1008_path_readers_reject_oversized_payloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    loader: Callable[[str], object],
) -> None:
    monkeypatch.setattr(m1008, "M1008_MAX_CANONICAL_REQUEST_BYTES", _TEST_LIMIT)
    monkeypatch.setattr(m1008, "M1008_MAX_CANONICAL_RESULT_BYTES", _TEST_LIMIT)
    payload = tmp_path / "oversized.json"
    payload.write_bytes(b"{" + b"x" * _TEST_LIMIT + b"}")

    with pytest.raises(RequestBodyTooLargeError):
        loader(str(payload))


def test_m1008_path_reader_never_calls_unbounded_read_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    payload = tmp_path / "request.json"
    payload.write_bytes(b"{}")

    with pytest.raises((ValidationError, PermissionError)):
        m1008._load_request_path(str(payload))


class _Stdin:
    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


def test_m1008_stdin_reader_enforces_the_same_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", _Stdin(b"x" * 33))

    with pytest.raises(RequestBodyTooLargeError):
        m1008._read_path("-", max_bytes=_TEST_LIMIT)
