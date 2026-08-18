"""Resource-admission regressions for the standalone M19 adapters."""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1901, m1902, m1905
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m19_01 import (
    M1901_MAX_CANONICAL_REQUEST_BYTES,
    M1901_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m19_02 import (
    M1902_MAX_CANONICAL_REQUEST_BYTES,
    M1902_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m19_05 import (
    M1905_MAX_CANONICAL_REQUEST_BYTES,
    M1905_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m1901_request(path: Path) -> object:
    return m1901._load_request(path)


def _m1902_request(path: Path) -> object:
    return m1902._load_request(path)


def _m1905_request(path: Path) -> object:
    return m1905._load_path(str(path), max_bytes=M1905_MAX_CANONICAL_REQUEST_BYTES)


def _m1901_result(path: Path) -> object:
    return m1901._read_result(path)


def _m1902_result(path: Path) -> object:
    return m1902._read_result(path)


def _m1905_result(path: Path) -> object:
    return m1905._load_path(str(path), max_bytes=M1905_MAX_CANONICAL_RESULT_BYTES)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1901_request, M1901_MAX_CANONICAL_REQUEST_BYTES),
        (_m1902_request, M1902_MAX_CANONICAL_REQUEST_BYTES),
        (_m1905_request, M1905_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m19_request_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-request.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1901_result, M1901_MAX_CANONICAL_RESULT_BYTES),
        (_m1902_result, M1902_MAX_CANONICAL_RESULT_BYTES),
        (_m1905_result, M1905_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m19_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


def test_m1905_cli_result_overflow_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1905_MAX_CANONICAL_RESULT_BYTES)
    result = CliRunner().invoke(m1905.cli, ["verify", str(path)])
    assert result.exit_code != 0
    assert "RequestBodyTooLargeError" in result.output


class _BinaryStdin:
    def __init__(self, payload: bytes) -> None:
        self.buffer = io.BytesIO(payload)


def test_m1905_stdin_request_overflow_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    limit = M1905_MAX_CANONICAL_REQUEST_BYTES
    monkeypatch.setattr(sys, "stdin", _BinaryStdin(b"x" * (limit + 1)))
    with pytest.raises(RequestBodyTooLargeError):
        m1905._load_path("-", max_bytes=limit)


def test_m19_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m1901.py", "m1902.py", "m1905.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
