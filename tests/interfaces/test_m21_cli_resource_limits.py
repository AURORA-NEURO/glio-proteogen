"""Adversarial resource-boundary tests for the M21 CLI file adapters."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer

from glio_proteogen.contracts.m21_01 import (
    M2101_MAX_CANONICAL_REQUEST_BYTES,
    M2101_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_02 import (
    M2102_MAX_CANONICAL_REQUEST_BYTES,
    M2102_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_03 import (
    M2103_MAX_CANONICAL_REQUEST_BYTES,
    M2103_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_04 import (
    M2104_MAX_CANONICAL_REQUEST_BYTES,
    M2104_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_05 import (
    M2105_MAX_CANONICAL_REQUEST_BYTES,
    M2105_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_06 import (
    M2106_MAX_CANONICAL_REQUEST_BYTES,
    M2106_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_07 import (
    M2107_MAX_CANONICAL_REQUEST_BYTES,
    M2107_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.contracts.m21_08 import (
    M2108_MAX_CANONICAL_REQUEST_BYTES,
    M2108_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c21_complex_activity.m21_05_subgroup_equity_evaluator import (
    cli as m2105_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_01_reference_truth_benchmark_curator import (
    cli as m2101_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    cli as m2102_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_03_internal_benchmark_ablation import (
    cli as m2103_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_04_external_transport_evaluator import (
    cli as m2104_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_06_robustness_shift_ood_challenge import (
    cli as m2106_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_07_human_factors_operational_evaluator import (  # noqa: E501
    cli as m2107_cli,
)
from glio_proteogen.modules.c21_reference_material.m21_08_evidence_gate_release_adjudicator import (
    cli as m2108_cli,
)

_Reader = Callable[[Path], object]

_READERS: tuple[tuple[str, _Reader, _Reader, int, int], ...] = (
    (
        "M21-01",
        m2101_cli._read_request,
        m2101_cli._read_result,
        M2101_MAX_CANONICAL_REQUEST_BYTES,
        M2101_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-02",
        m2102_cli._read_request,
        m2102_cli._read_result,
        M2102_MAX_CANONICAL_REQUEST_BYTES,
        M2102_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-03",
        m2103_cli._read_request,
        m2103_cli._read_result,
        M2103_MAX_CANONICAL_REQUEST_BYTES,
        M2103_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-04",
        m2104_cli._read_request,
        m2104_cli._read_result,
        M2104_MAX_CANONICAL_REQUEST_BYTES,
        M2104_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-05",
        m2105_cli._read_request,
        m2105_cli._read_result,
        M2105_MAX_CANONICAL_REQUEST_BYTES,
        M2105_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-06",
        m2106_cli._read_request,
        m2106_cli._read_result,
        M2106_MAX_CANONICAL_REQUEST_BYTES,
        M2106_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-07",
        m2107_cli._read_request,
        m2107_cli._read_result,
        M2107_MAX_CANONICAL_REQUEST_BYTES,
        M2107_MAX_CANONICAL_RESULT_BYTES,
    ),
    (
        "M21-08",
        m2108_cli._read_request,
        m2108_cli._read_result,
        M2108_MAX_CANONICAL_REQUEST_BYTES,
        M2108_MAX_CANONICAL_RESULT_BYTES,
    ),
)


@pytest.mark.parametrize(
    ("module", "_request_reader", "_result_reader", "request_limit", "_result_limit"),
    _READERS,
)
def test_request_reader_rejects_oversized_file_before_json_parse(
    tmp_path: Path,
    module: str,
    _request_reader: _Reader,
    _result_reader: _Reader,
    request_limit: int,
    _result_limit: int,
) -> None:
    path = tmp_path / f"{module}-request.json"
    path.write_bytes(b"{" + b" " * request_limit)
    with pytest.raises(typer.BadParameter, match="request"):
        _request_reader(path)


@pytest.mark.parametrize(
    ("module", "_request_reader", "result_reader", "_request_limit", "result_limit"),
    _READERS,
)
def test_result_reader_rejects_oversized_file_before_json_parse(
    tmp_path: Path,
    module: str,
    _request_reader: _Reader,
    result_reader: _Reader,
    _request_limit: int,
    result_limit: int,
) -> None:
    path = tmp_path / f"{module}-result.json"
    path.write_bytes(b"{" + b" " * result_limit)
    with pytest.raises(typer.BadParameter, match="result"):
        result_reader(path)


def test_m21_readers_never_call_unbounded_path_read_bytes(
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
