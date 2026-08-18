"""Resource-admission regressions for the standalone M16 adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1601, m1602, m1604, m1605, m1607, m1608
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m16_01 import (
    M1601_MAX_CANONICAL_REQUEST_BYTES,
    M1601_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m16_02 import (
    M1602_MAX_CANONICAL_REQUEST_BYTES,
    M1602_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m16_04 import (
    M1604_MAX_CANONICAL_REQUEST_BYTES,
    M1604_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m16_05 import (
    M1605_MAX_CANONICAL_REQUEST_BYTES,
    M1605_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m16_07 import (
    M1607_MAX_CANONICAL_REQUEST_BYTES,
    M1607_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m16_08 import (
    M1608_MAX_CANONICAL_REQUEST_BYTES,
    M1608_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m1601_request(path: Path) -> object:
    return m1601._load_request(path)


def _m1602_request(path: Path) -> object:
    return m1602._load_request(path)


def _m1604_request(path: Path) -> object:
    return m1604._load_request(path)


def _m1605_request(path: Path) -> object:
    return m1605._load_request(path)


def _m1607_request(path: Path) -> object:
    return m1607._load_request(path)


def _m1608_request(path: Path) -> object:
    return m1608._load_request(path)


def _m1601_result(path: Path) -> object:
    return m1601._read_result(path)


def _m1602_result(path: Path) -> object:
    return m1602._read_result(path)


def _m1604_result(path: Path) -> object:
    return m1604._read_result(path)


def _m1605_result(path: Path) -> object:
    return m1605._read_result(path)


def _m1607_result(path: Path) -> object:
    return m1607._read_result(path)


def _m1608_result(path: Path) -> object:
    return m1608._read_result(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1601_request, M1601_MAX_CANONICAL_REQUEST_BYTES),
        (_m1602_request, M1602_MAX_CANONICAL_REQUEST_BYTES),
        (_m1604_request, M1604_MAX_CANONICAL_REQUEST_BYTES),
        (_m1605_request, M1605_MAX_CANONICAL_REQUEST_BYTES),
        (_m1607_request, M1607_MAX_CANONICAL_REQUEST_BYTES),
        (_m1608_request, M1608_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m16_request_readers_reject_sparse_overflow(
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
        (_m1601_result, M1601_MAX_CANONICAL_RESULT_BYTES),
        (_m1602_result, M1602_MAX_CANONICAL_RESULT_BYTES),
        (_m1604_result, M1604_MAX_CANONICAL_RESULT_BYTES),
        (_m1605_result, M1605_MAX_CANONICAL_RESULT_BYTES),
        (_m1607_result, M1607_MAX_CANONICAL_RESULT_BYTES),
        (_m1608_result, M1608_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m16_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


def test_m1607_cli_result_overflow_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1607_MAX_CANONICAL_RESULT_BYTES)
    result = CliRunner().invoke(m1607.m1607_app, ["verify", str(path)])
    assert result.exit_code != 0
    assert "verification failed" in result.output


def test_m16_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m1601.py", "m1602.py", "m1604.py", "m1605.py", "m1607.py", "m1608.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
