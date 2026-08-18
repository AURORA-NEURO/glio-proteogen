"""Resource-admission regressions for the standalone M17 adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1702, m1703, m1705, m1706, m1707
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m17_02 import (
    M1702_MAX_CANONICAL_REQUEST_BYTES,
    M1702_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m17_03 import (
    M1703_MAX_CANONICAL_REQUEST_BYTES,
    M1703_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m17_05 import (
    M1705_MAX_CANONICAL_REQUEST_BYTES,
    M1705_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m17_06 import (
    M1706_MAX_CANONICAL_REQUEST_BYTES,
    M1706_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m17_07 import (
    M1707_MAX_CANONICAL_REQUEST_BYTES,
    M1707_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m1702_request(path: Path) -> object:
    return m1702._load_request(path)


def _m1703_request(path: Path) -> object:
    return m1703._load_request(path)


def _m1705_request(path: Path) -> object:
    return m1705._load_path(str(path), max_bytes=M1705_MAX_CANONICAL_REQUEST_BYTES)


def _m1706_request(path: Path) -> object:
    return m1706._load_request(path)


def _m1707_request(path: Path) -> object:
    return m1707._load_path(str(path), max_bytes=M1707_MAX_CANONICAL_REQUEST_BYTES)


def _m1702_result(path: Path) -> object:
    return m1702._read_result(path)


def _m1703_result(path: Path) -> object:
    return m1703._read_result(path)


def _m1705_result(path: Path) -> object:
    return m1705._load_path(str(path), max_bytes=M1705_MAX_CANONICAL_RESULT_BYTES)


def _m1706_result(path: Path) -> object:
    return m1706._read_result(path)


def _m1707_result(path: Path) -> object:
    return m1707._load_path(str(path), max_bytes=M1707_MAX_CANONICAL_RESULT_BYTES)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1702_request, M1702_MAX_CANONICAL_REQUEST_BYTES),
        (_m1703_request, M1703_MAX_CANONICAL_REQUEST_BYTES),
        (_m1705_request, M1705_MAX_CANONICAL_REQUEST_BYTES),
        (_m1706_request, M1706_MAX_CANONICAL_REQUEST_BYTES),
        (_m1707_request, M1707_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m17_request_readers_reject_sparse_overflow(
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
        (_m1702_result, M1702_MAX_CANONICAL_RESULT_BYTES),
        (_m1703_result, M1703_MAX_CANONICAL_RESULT_BYTES),
        (_m1705_result, M1705_MAX_CANONICAL_RESULT_BYTES),
        (_m1706_result, M1706_MAX_CANONICAL_RESULT_BYTES),
        (_m1707_result, M1707_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m17_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


@pytest.mark.parametrize(
    ("app", "command", "limit"),
    [
        (m1705.cli, "verify", M1705_MAX_CANONICAL_RESULT_BYTES),
        (m1707.cli, "verify", M1707_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m17_cli_result_overflow_is_sanitized(
    tmp_path: Path,
    app: typer.Typer,
    command: str,
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    result = CliRunner().invoke(app, [command, str(path)])
    assert result.exit_code != 0
    assert "RequestBodyTooLargeError" in result.output


def test_m17_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m1702.py", "m1703.py", "m1705.py", "m1706.py", "m1707.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
