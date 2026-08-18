"""Adversarial resource-boundary coverage for the M25/M26-03 CLI readers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer

from glio_proteogen.contracts.m25_01 import (
    M2501_MAX_CANONICAL_REQUEST_BYTES,
    M2501_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_02 import (
    M2502_MAX_CANONICAL_REQUEST_BYTES,
    M2502_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_03 import (
    M2503_MAX_CANONICAL_REQUEST_BYTES,
    M2503_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_05 import (
    M2505_MAX_CANONICAL_REQUEST_BYTES,
    M2505_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_07 import (
    M2507_MAX_CANONICAL_REQUEST_BYTES,
    M2507_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m25_08 import (
    M2508_MAX_CANONICAL_REQUEST_BYTES,
    M2508_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m26_03 import (
    M2603_MAX_CANONICAL_REQUEST_BYTES,
    M2603_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator import (
    cli as m2501_cli,
)
from glio_proteogen.modules.c21_reference_material.m25_02_synthetic_truth_simulation_generator import (  # noqa: E501
    cli as m2502_cli,
)
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation import (
    cli as m2503_cli,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator import (
    cli as m2505_cli,
)
from glio_proteogen.modules.c21_reference_material.m25_07_human_factors_operational_evaluator import (  # noqa: E501
    cli as m2507_cli,
)
from glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator import (
    cli as m2508_cli,
)
from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (  # noqa: E501
    cli as m2603_cli,
)

Reader = Callable[[Path], object]
ReaderCase = tuple[object, Reader, Reader, int, int]
_READERS: tuple[ReaderCase, ...] = (
    (
        m2501_cli,
        m2501_cli._read_request,
        m2501_cli._read_result,
        M2501_MAX_CANONICAL_REQUEST_BYTES,
        M2501_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2502_cli,
        m2502_cli._read_request,
        m2502_cli._read_result,
        M2502_MAX_CANONICAL_REQUEST_BYTES,
        M2502_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2503_cli,
        m2503_cli._read_request,
        m2503_cli._read_result,
        M2503_MAX_CANONICAL_REQUEST_BYTES,
        M2503_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2505_cli,
        m2505_cli._read_request,
        m2505_cli._read_result,
        M2505_MAX_CANONICAL_REQUEST_BYTES,
        M2505_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2507_cli,
        m2507_cli._read_request,
        m2507_cli._read_result,
        M2507_MAX_CANONICAL_REQUEST_BYTES,
        M2507_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2508_cli,
        m2508_cli._read_request,
        m2508_cli._read_result,
        M2508_MAX_CANONICAL_REQUEST_BYTES,
        M2508_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        m2603_cli,
        m2603_cli._read_request,
        m2603_cli._read_result,
        M2603_MAX_CANONICAL_REQUEST_BYTES,
        M2603_MAX_CANONICAL_RESULT_BYTES,
    ),
)


def _make_oversized_file(path: Path, limit: int) -> None:
    """Create a sparse limit+1 file without allocating the full test payload."""

    with path.open("wb") as stream:
        stream.seek(limit)
        stream.write(b" ")


@pytest.mark.parametrize(
    ("_module", "request_reader", "_result_reader", "request_limit", "_result_limit"),
    _READERS,
)
def test_request_reader_rejects_oversized_file(
    tmp_path: Path,
    _module: object,
    request_reader: Reader,
    _result_reader: Reader,
    request_limit: int,
    _result_limit: int,
) -> None:
    path = tmp_path / "oversized-request.json"
    _make_oversized_file(path, request_limit)
    with pytest.raises(typer.BadParameter, match="request"):
        request_reader(path)


@pytest.mark.parametrize(
    ("_module", "_request_reader", "result_reader", "_request_limit", "result_limit"),
    _READERS,
)
def test_result_reader_rejects_oversized_file(
    tmp_path: Path,
    _module: object,
    _request_reader: Reader,
    result_reader: Reader,
    _request_limit: int,
    result_limit: int,
) -> None:
    path = tmp_path / "oversized-result.json"
    _make_oversized_file(path, result_limit)
    with pytest.raises(typer.BadParameter, match="result"):
        result_reader(path)


def test_m25_m26_readers_never_call_unbounded_path_read_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "small.json"
    path.write_bytes(b"{}")

    def forbidden_read_bytes(_path: Path) -> bytes:
        raise AssertionError

    monkeypatch.setattr(Path, "read_bytes", forbidden_read_bytes)
    for _module, request_reader, result_reader, _request_limit, _result_limit in _READERS:
        with pytest.raises(typer.BadParameter):
            request_reader(path)
        with pytest.raises(typer.BadParameter):
            result_reader(path)
