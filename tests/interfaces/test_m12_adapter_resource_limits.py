"""Resource-admission regressions for the M12 standalone adapters."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from typer import BadParameter

from glio_proteogen.adapters import m1201, m1202, m1203, m1204, m1205, m1206, m1207, m1208
from glio_proteogen.adapters.limits import RequestBodyTooLargeError, read_bounded
from glio_proteogen.contracts.m12_01 import M1201_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_02 import M1202_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_03 import M1203_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_04 import M1204_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_05 import M1205_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_06 import M1206_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_07 import M1207_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.contracts.m12_08 import M1208_MAX_CANONICAL_RESULT_BYTES
from glio_proteogen.kernel.strict_json import StrictJsonError

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

_TEST_LIMIT = 32
_EXPECTED_ERRORS = (
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
        (m1201._load_request, m1201, "M1201_MAX_CANONICAL_REQUEST_BYTES"),
        (m1202._load_request, m1202, "M1202_MAX_CANONICAL_REQUEST_BYTES"),
        (m1203._read_json, m1203, "M1203_MAX_CANONICAL_REQUEST_BYTES"),
        (m1204._load_request, m1204, "M1204_MAX_CANONICAL_REQUEST_BYTES"),
        (m1205._load_request, m1205, "M1205_MAX_CANONICAL_REQUEST_BYTES"),
        (
            lambda path: m1206._read_json(path, _TEST_LIMIT),
            m1206,
            "M1206_MAX_CANONICAL_REQUEST_BYTES",
        ),
        (
            lambda path: m1207._load_json(path, max_bytes=_TEST_LIMIT),
            m1207,
            "M1207_MAX_CANONICAL_REQUEST_BYTES",
        ),
        (m1208._load_request, m1208, "M1208_MAX_CANONICAL_REQUEST_BYTES"),
    ],
)
def test_m12_request_readers_reject_overflow_before_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: Callable[[Path], object],
    module: ModuleType,
    constant_name: str,
) -> None:
    path = tmp_path / "oversized.json"
    _overflow_file(path)
    monkeypatch.setattr(module, constant_name, _TEST_LIMIT)
    with pytest.raises(_EXPECTED_ERRORS):
        reader(path)


@pytest.mark.parametrize(
    "reader",
    [
        m1201._load_request,
        m1202._load_request,
        m1203._read_json,
        m1204._load_request,
        m1205._load_request,
        lambda path: m1206._read_json(path, _TEST_LIMIT),
        lambda path: m1207._load_json(path, max_bytes=_TEST_LIMIT),
        m1208._load_request,
    ],
)
def test_m12_path_readers_do_not_call_path_read_bytes(
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
    except _EXPECTED_ERRORS:
        pass


@pytest.mark.parametrize(
    ("reader", "declared_limit"),
    [
        (lambda path: read_bounded(path, _TEST_LIMIT), M1201_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1202_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1203_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1204_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1205_MAX_CANONICAL_RESULT_BYTES),
        (lambda path: m1206._read_json(path, _TEST_LIMIT), M1206_MAX_CANONICAL_RESULT_BYTES),
        (
            lambda path: m1207._load_json(path, max_bytes=_TEST_LIMIT),
            M1207_MAX_CANONICAL_RESULT_BYTES,
        ),
        (lambda path: read_bounded(path, _TEST_LIMIT), M1208_MAX_CANONICAL_RESULT_BYTES),
    ],
)
def test_m12_result_readers_use_declared_result_ceiling(
    tmp_path: Path,
    reader: Callable[[Path], object],
    declared_limit: int,
) -> None:
    assert declared_limit == 8 * 1024 * 1024
    path = tmp_path / "oversized-result.json"
    _overflow_file(path)
    with pytest.raises(_EXPECTED_ERRORS):
        reader(path)
