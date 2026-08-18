"""Resource-admission regressions for the M11 standalone adapters."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from typer import BadParameter

from glio_proteogen.adapters import m1101, m1102, m1103, m1104, m1105, m1106, m1107, m1108
from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m11_01 import (
    M1101_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_02 import (
    M1102_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_03 import (
    M1103_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_04 import (
    M1104_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_05 import (
    M1105_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_06 import (
    M1106_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_07 import (
    M1107_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m11_08 import (
    M1108_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.kernel.strict_json import StrictJsonError

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

_TEST_LIMIT = 32
_EXPECTED_PARSE_ERRORS = (
    BadParameter,
    RequestBodyTooLargeError,
    StrictJsonError,
    TypeError,
    ValidationError,
    ValueError,
)


def _overflow_file(path: Path) -> None:
    path.write_bytes(b"{" + b"x" * _TEST_LIMIT)


@pytest.mark.parametrize(
    ("reader", "module", "constant_name"),
    [
        (m1101._load_request, m1101, "M1101_MAX_CANONICAL_REQUEST_BYTES"),
        (
            lambda path: m1102._read_argument(str(path), _TEST_LIMIT),
            m1102,
            "M1102_MAX_CANONICAL_REQUEST_BYTES",
        ),
        (
            lambda path: m1103._read_json(path, _TEST_LIMIT),
            m1103,
            "M1103_MAX_CANONICAL_REQUEST_BYTES",
        ),
        (m1104._load_request, m1104, "M1104_MAX_CANONICAL_REQUEST_BYTES"),
        (m1105._load_request, m1105, "M1105_MAX_CANONICAL_REQUEST_BYTES"),
        (m1106._load_request, m1106, "M1106_MAX_CANONICAL_REQUEST_BYTES"),
        (
            lambda path: m1107._read_json(path, _TEST_LIMIT),
            m1107,
            "M1107_MAX_CANONICAL_REQUEST_BYTES",
        ),
        (
            lambda path: m1108._read_path(str(path), _TEST_LIMIT),
            m1108,
            "M1108_MAX_CANONICAL_REQUEST_BYTES",
        ),
    ],
)
def test_m11_file_readers_reject_overflow_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[[Path], object],
    module: ModuleType,
    constant_name: str,
) -> None:
    path = tmp_path / "oversized.json"
    _overflow_file(path)
    monkeypatch.setattr(module, constant_name, _TEST_LIMIT)
    with pytest.raises(_EXPECTED_PARSE_ERRORS):
        reader(path)


@pytest.mark.parametrize(
    "reader",
    [
        m1101._load_request,
        lambda path: m1102._read_argument(str(path), _TEST_LIMIT),
        lambda path: m1103._read_json(path, _TEST_LIMIT),
        m1104._load_request,
        m1105._load_request,
        m1106._load_request,
        lambda path: m1107._read_json(path, _TEST_LIMIT),
        lambda path: m1108._read_path(str(path), _TEST_LIMIT),
    ],
)
def test_m11_file_readers_do_not_call_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[[Path], object],
) -> None:
    path = tmp_path / "small.json"
    path.write_bytes(b"{}")

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    try:
        reader(path)
    except AssertionError:
        raise
    except _EXPECTED_PARSE_ERRORS:
        pass


@pytest.mark.parametrize(
    ("reader", "declared_limit"),
    [
        (lambda path: read_bounded(path, _TEST_LIMIT), M1101_MAX_CANONICAL_RESULT_BYTES),
        (
            lambda path: m1102._parse_argument(str(path), _TEST_LIMIT),
            M1102_MAX_CANONICAL_RESULT_BYTES,
        ),
        (
            lambda path: m1103._read_json(path, _TEST_LIMIT),
            M1103_MAX_CANONICAL_RESULT_BYTES,
        ),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1104_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1105_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1106_MAX_CANONICAL_RESULT_BYTES),
        (
            lambda path: m1107._read_json(path, _TEST_LIMIT),
            M1107_MAX_CANONICAL_RESULT_BYTES,
        ),
        (
            lambda path: m1108._read_path(str(path), _TEST_LIMIT),
            M1108_MAX_CANONICAL_RESULT_BYTES,
        ),
    ],
)
def test_m11_result_readers_use_declared_result_ceiling(
    tmp_path: Path,
    reader: Callable[[Path], object],
    declared_limit: int,
) -> None:
    assert declared_limit == 8 * 1024 * 1024
    path = tmp_path / "oversized-result.json"
    _overflow_file(path)
    with pytest.raises(_EXPECTED_PARSE_ERRORS):
        reader(path)
