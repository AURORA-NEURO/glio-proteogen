"""Resource-admission regressions for the M13 adapter family."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1301, m1302, m1303, m1304, m1305, m1307, m1308
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m13_01 import (
    M1301_MAX_CANONICAL_REQUEST_BYTES,
    M1301_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m13_02 import (
    M1302_MAX_CANONICAL_REQUEST_BYTES,
    M1302_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m13_03 import (
    M1303_MAX_CANONICAL_REQUEST_BYTES,
    M1303_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m13_04 import (
    M1304_MAX_CANONICAL_REQUEST_BYTES,
    M1304_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m13_05 import (
    M1305_MAX_CANONICAL_REQUEST_BYTES,
    M1305_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m13_07 import (
    M1307_MAX_CANONICAL_REQUEST_BYTES,
    M1307_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m13_08 import (
    M1308_MAX_CANONICAL_REQUEST_BYTES,
    M1308_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


def _m1301_reader(path: Path) -> object:
    return m1301._load_request(path)


def _m1302_reader(path: Path) -> object:
    return m1302._read_input(path, M1302_MAX_CANONICAL_REQUEST_BYTES)


def _m1303_reader(path: Path) -> object:
    return m1303._load_bytes(path, M1303_MAX_CANONICAL_REQUEST_BYTES)


def _m1304_reader(path: Path) -> object:
    return m1304._load_request(path)


def _m1305_reader(path: Path) -> object:
    return m1305._load_request(path)


def _m1307_reader(path: Path) -> object:
    return m1307._read_json(path, M1307_MAX_CANONICAL_REQUEST_BYTES)


def _m1308_reader(path: Path) -> object:
    return m1308._load_request(path)


def _m1301_result_reader(path: Path) -> object:
    return m1301._read_result(path)


def _m1302_result_reader(path: Path) -> object:
    return m1302._read_input(path, M1302_MAX_CANONICAL_RESULT_BYTES)


def _m1303_result_reader(path: Path) -> object:
    return m1303._load_bytes(path, M1303_MAX_CANONICAL_RESULT_BYTES)


def _m1304_result_reader(path: Path) -> object:
    return m1304._read_result(path)


def _m1305_result_reader(path: Path) -> object:
    return m1305._read_result(path)


def _m1307_result_reader(path: Path) -> object:
    return m1307._read_json(path, M1307_MAX_CANONICAL_RESULT_BYTES)


def _m1308_result_reader(path: Path) -> object:
    return m1308._read_result(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1301_reader, M1301_MAX_CANONICAL_REQUEST_BYTES),
        (_m1302_reader, M1302_MAX_CANONICAL_REQUEST_BYTES),
        (_m1303_reader, M1303_MAX_CANONICAL_REQUEST_BYTES),
        (_m1304_reader, M1304_MAX_CANONICAL_REQUEST_BYTES),
        (_m1305_reader, M1305_MAX_CANONICAL_REQUEST_BYTES),
        (_m1307_reader, M1307_MAX_CANONICAL_REQUEST_BYTES),
        (_m1308_reader, M1308_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m13_file_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (_m1301_result_reader, M1301_MAX_CANONICAL_RESULT_BYTES),
        (_m1302_result_reader, M1302_MAX_CANONICAL_RESULT_BYTES),
        (_m1303_result_reader, M1303_MAX_CANONICAL_RESULT_BYTES),
        (_m1304_result_reader, M1304_MAX_CANONICAL_RESULT_BYTES),
        (_m1305_result_reader, M1305_MAX_CANONICAL_RESULT_BYTES),
        (_m1307_result_reader, M1307_MAX_CANONICAL_RESULT_BYTES),
        (_m1308_result_reader, M1308_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m13_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises((RequestBodyTooLargeError, typer.BadParameter)):
        reader(path)


def test_m1302_stdin_reader_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Buffer:
        def read(self, size: int) -> bytes:
            return b"x" * size

    class _Stdin:
        buffer = _Buffer()

    monkeypatch.setattr(sys, "stdin", _Stdin())
    with pytest.raises(RequestBodyTooLargeError):
        m1302._read_input(Path("-"), M1302_MAX_CANONICAL_REQUEST_BYTES)


def test_m1301_cli_result_overflow_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1301_MAX_CANONICAL_RESULT_BYTES)
    result = CliRunner().invoke(m1301.m1301_app, ["verify", str(path)])
    assert result.exit_code != 0
    assert "verification failed" in result.output


def test_m13_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    for name in (
        "m1301.py",
        "m1302.py",
        "m1303.py",
        "m1304.py",
        "m1305.py",
        "m1307.py",
        "m1308.py",
    ):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
