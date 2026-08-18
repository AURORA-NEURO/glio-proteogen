"""Resource-admission regressions for the standalone M15 adapters."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from typer.testing import CliRunner

from glio_proteogen.adapters import m1501, m1503, m1504, m1506, m1507
from glio_proteogen.adapters.limits import RequestBodyTooLargeError
from glio_proteogen.contracts.m15_01 import (
    M1501_MAX_CANONICAL_REQUEST_BYTES,
    M1501_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m15_03 import (
    M1503_MAX_CANONICAL_REQUEST_BYTES,
    M1503_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m15_04 import (
    M1504_MAX_CANONICAL_REQUEST_BYTES,
    M1504_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m15_06 import (
    M1506_MAX_CANONICAL_REQUEST_BYTES,
    M1506_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m15_07 import (
    M1507_MAX_CANONICAL_REQUEST_BYTES,
    M1507_MAX_CANONICAL_RESULT_BYTES,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def _sparse_overflow(path: Path, limit: int) -> None:
    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b"x")


@pytest.mark.parametrize(
    ("reader", "limit"),
    [
        (m1501._load_request, M1501_MAX_CANONICAL_REQUEST_BYTES),
        (m1503._load_request, M1503_MAX_CANONICAL_REQUEST_BYTES),
        (m1504._load_request, M1504_MAX_CANONICAL_REQUEST_BYTES),
        (m1506._load_request, M1506_MAX_CANONICAL_REQUEST_BYTES),
        (m1507._load_request, M1507_MAX_CANONICAL_REQUEST_BYTES),
    ],
)
def test_m15_request_readers_reject_sparse_overflow(
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
        (m1501._read_result, M1501_MAX_CANONICAL_RESULT_BYTES),
        (m1503._read_result, M1503_MAX_CANONICAL_RESULT_BYTES),
        (m1504._read_result, M1504_MAX_CANONICAL_RESULT_BYTES),
        (m1506._read_result, M1506_MAX_CANONICAL_RESULT_BYTES),
        (m1507._read_result, M1507_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m15_result_readers_reject_sparse_overflow(
    tmp_path: Path,
    reader: Callable[[Path], object],
    limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, limit)
    with pytest.raises(RequestBodyTooLargeError):
        reader(path)


def test_m1507_cli_result_overflow_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "oversized-result.json"
    _sparse_overflow(path, M1507_MAX_CANONICAL_RESULT_BYTES)
    result = CliRunner().invoke(m1507.m1507_app, ["verify", str(path)])
    assert result.exit_code != 0
    assert "verification failed" in result.output


def test_m15_adapters_have_no_unbounded_path_read_bytes() -> None:
    root = Path(__file__).parents[2] / "src" / "glio_proteogen" / "adapters"
    names = ("m1501.py", "m1503.py", "m1504.py", "m1506.py", "m1507.py")
    for name in names:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Attribute) and node.attr == "read_bytes" for node in ast.walk(tree)
        ), name
