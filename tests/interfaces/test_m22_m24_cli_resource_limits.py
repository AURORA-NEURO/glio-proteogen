"""Adversarial resource-boundary tests for the M22-M24 CLI file adapters."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest
import typer

_Reader = Callable[[Path], object]
_MODULES = (
    ("M22-01", "m22_01_reference_truth_benchmark_curator"),
    ("M22-02", "m22_02_synthetic_truth_simulation_generator"),
    ("M22-03", "m22_03_internal_benchmark_ablation"),
    ("M22-04", "m22_04_external_transport_evaluator"),
    ("M22-05", "m22_05_subgroup_equity_evaluator"),
    ("M22-06", "m22_06_robustness_shift_ood_challenge"),
    ("M22-07", "m22_07_human_factors_operational_evaluator"),
    ("M22-08", "m22_08_evidence_gate_release_adjudicator"),
    ("M23-01", "m23_01_reference_truth_benchmark_curator"),
    ("M23-02", "m23_02_synthetic_truth_simulation_generator"),
    ("M23-03", "m23_03_internal_benchmark_ablation"),
    ("M23-04", "m23_04_external_transport_evaluator"),
    ("M23-05", "m23_05_subgroup_equity_evaluator"),
    ("M23-07", "m23_07_human_factors_operational_evaluator"),
    ("M23-08", "m23_08_evidence_gate_release_adjudicator"),
    ("M24-07", "m24_07_human_factors_operational_evaluator"),
)


def _cli(module_name: str) -> Any:
    return import_module(f"glio_proteogen.modules.c21_reference_material.{module_name}.cli")


def _contract(module_id: str) -> Any:
    normalized = module_id.replace("-", "_").lower()
    return import_module(f"glio_proteogen.contracts.{normalized}")


def _readers() -> tuple[tuple[str, _Reader, _Reader, int, int], ...]:
    readers = []
    for module_id, module_name in _MODULES:
        cli = _cli(module_name)
        contract = _contract(module_id)
        readers.append(
            (
                module_id,
                cast("_Reader", cli._read_request),
                cast("_Reader", cli._read_result),
                cast(
                    "int",
                    getattr(contract, f"{module_id.replace('-', '')}_MAX_CANONICAL_REQUEST_BYTES"),
                ),
                cast(
                    "int",
                    getattr(contract, f"{module_id.replace('-', '')}_MAX_CANONICAL_RESULT_BYTES"),
                ),
            )
        )
    return tuple(readers)


_READERS = _readers()


@pytest.mark.parametrize(
    ("module", "request_reader", "_result_reader", "request_limit", "_result_limit"),
    _READERS,
)
def test_request_reader_rejects_oversized_file_before_json_parse(
    tmp_path: Path,
    module: str,
    request_reader: _Reader,
    _result_reader: _Reader,
    request_limit: int,
    _result_limit: int,
) -> None:
    path = tmp_path / f"{module}-request.json"
    path.write_bytes(b"{" + b" " * request_limit)
    with pytest.raises(typer.BadParameter, match="request"):
        request_reader(path)


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


def test_m22_m24_readers_never_call_unbounded_path_read_bytes(
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
