"""Resource-admission regressions for the standalone M18 adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1801, m1802, m1804, m1805, m1807
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m18_01 import (
    M1801_MAX_CANONICAL_REQUEST_BYTES,
    M1801_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m18_02 import (
    M1802_MAX_CANONICAL_REQUEST_BYTES,
    M1802_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m18_04 import (
    M1804_MAX_CANONICAL_REQUEST_BYTES,
    M1804_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m18_05 import (
    M1805_MAX_CANONICAL_REQUEST_BYTES,
    M1805_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m18_07 import (
    M1807_MAX_CANONICAL_REQUEST_BYTES,
    M1807_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m1802_request(path: Path) -> object:
    return m1802._load_path(str(path), max_bytes=M1802_MAX_CANONICAL_REQUEST_BYTES)


def _m1805_request(path: Path) -> object:
    return m1805._load_path(str(path), max_bytes=M1805_MAX_CANONICAL_REQUEST_BYTES)


def _m1802_result(path: Path) -> object:
    return m1802._load_path(str(path), max_bytes=M1802_MAX_CANONICAL_RESULT_BYTES)


def _m1805_result(path: Path) -> object:
    return m1805._load_path(str(path), max_bytes=M1805_MAX_CANONICAL_RESULT_BYTES)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (m1801._load_request, M1801_MAX_CANONICAL_REQUEST_BYTES),
        (_m1802_request, M1802_MAX_CANONICAL_REQUEST_BYTES),
        (m1804._load_request, M1804_MAX_CANONICAL_REQUEST_BYTES),
        (_m1805_request, M1805_MAX_CANONICAL_REQUEST_BYTES),
        (m1807._load_request, M1807_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m18_request_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-request.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter, ValueError)):
        reader(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (m1801._read_result, M1801_MAX_CANONICAL_RESULT_BYTES),
        (_m1802_result, M1802_MAX_CANONICAL_RESULT_BYTES),
        (m1804._read_result, M1804_MAX_CANONICAL_RESULT_BYTES),
        (_m1805_result, M1805_MAX_CANONICAL_RESULT_BYTES),
        (m1807._read_result, M1807_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m18_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter, ValueError)):
        reader(path)


def test_m1807_cli_result_overflow_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1807_MAX_CANONICAL_RESULT_BYTES)
    result = CliRunner().invoke(m1807.m1807_app, ["verify", str(path)])
    assert result.exit_code != 0
    assert "verification failed" in result.output


def test_m18_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m1801.py", "m1802.py", "m1804.py", "m1805.py", "m1807.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
