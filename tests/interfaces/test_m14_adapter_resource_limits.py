"""Resource-admission regressions for the standalone M14 adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1401, m1402, m1404, m1406, m1407, m1408
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m14_01 import (
    M1401_MAX_CANONICAL_REQUEST_BYTES,
    M1401_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m14_02 import (
    M1402_MAX_CANONICAL_REQUEST_BYTES,
    M1402_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m14_04 import (
    M1404_MAX_CANONICAL_REQUEST_BYTES,
    M1404_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m14_06 import (
    M1406_MAX_CANONICAL_REQUEST_BYTES,
    M1406_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m14_07 import (
    M1407_MAX_CANONICAL_REQUEST_BYTES,
    M1407_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m14_08 import (
    M1408_MAX_CANONICAL_REQUEST_BYTES,
    M1408_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m1401_request(path: Path) -> object:
    return m1401._load_request(path)


def _m1402_request(path: Path) -> object:
    return m1402._load_request(path)


def _m1404_request(path: Path) -> object:
    return m1404._load_request(path)


def _m1406_request(path: Path) -> object:
    return m1406._load_request(path)


def _m1407_request(path: Path) -> object:
    return m1407._load_request(path)


def _m1408_request(path: Path) -> object:
    return m1408._load_request(path)


def _m1401_result(path: Path) -> object:
    return m1401._read_result(path)


def _m1402_result(path: Path) -> object:
    return m1402._read_result(path)


def _m1404_result(path: Path) -> object:
    return m1404._read_result(path)


def _m1406_result(path: Path) -> object:
    return m1406._read_result(path)


def _m1407_result(path: Path) -> object:
    return m1407._read_result(path)


def _m1408_result(path: Path) -> object:
    return m1408._read_result(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1401_request, M1401_MAX_CANONICAL_REQUEST_BYTES),
        (_m1402_request, M1402_MAX_CANONICAL_REQUEST_BYTES),
        (_m1404_request, M1404_MAX_CANONICAL_REQUEST_BYTES),
        (_m1406_request, M1406_MAX_CANONICAL_REQUEST_BYTES),
        (_m1407_request, M1407_MAX_CANONICAL_REQUEST_BYTES),
        (_m1408_request, M1408_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m14_request_readers_reject_sparse_overflow(
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
        (_m1401_result, M1401_MAX_CANONICAL_RESULT_BYTES),
        (_m1402_result, M1402_MAX_CANONICAL_RESULT_BYTES),
        (_m1404_result, M1404_MAX_CANONICAL_RESULT_BYTES),
        (_m1406_result, M1406_MAX_CANONICAL_RESULT_BYTES),
        (_m1407_result, M1407_MAX_CANONICAL_RESULT_BYTES),
        (_m1408_result, M1408_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m14_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


def test_m1407_cli_result_overflow_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1407_MAX_CANONICAL_RESULT_BYTES)
    result = CliRunner().invoke(m1407.m1407_app, ["verify", str(path)])
    assert result.exit_code != 0
    assert "verification failed" in result.output


def test_m14_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m1401.py", "m1402.py", "m1404.py", "m1406.py", "m1407.py", "m1408.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
