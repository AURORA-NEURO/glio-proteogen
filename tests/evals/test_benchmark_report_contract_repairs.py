"""Canonical pass and budget evidence for repaired benchmark reports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, cast

import pytest
from tools.verify_module_validation import normalize_benchmark_report

if TYPE_CHECKING:
    from collections.abc import Callable


_BENCHMARKS = (
    ("evals.m07_07.benchmark", "benchmark", "GLIO-PROTEOGEN-M07-07"),
    ("evals.m11_01.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M11-01"),
    ("evals.m13_06.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M13-06"),
    ("evals.m14_03.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M14-03"),
    ("evals.m14_05.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M14-05"),
    ("evals.m15_02.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M15-02"),
    ("evals.m15_05.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M15-05"),
    ("evals.m15_08.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M15-08"),
    ("evals.m16_03.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M16-03"),
    ("evals.m16_06.benchmark", "run_benchmark", "GLIO-PROTEOGEN-M16-06"),
)
_ITERATIONS = 3


@pytest.mark.parametrize(
    ("module_name", "callable_name", "module_id"),
    _BENCHMARKS,
    ids=[module_id for _, _, module_id in _BENCHMARKS],
)
def test_repaired_benchmark_reports_close_over_pass_and_budget_evidence(
    module_name: str,
    callable_name: str,
    module_id: str,
) -> None:
    module = import_module(module_name)
    runner = cast(
        "Callable[[int], dict[str, object]]",
        getattr(module, callable_name),
    )
    report = runner(_ITERATIONS)

    assert report["module_id"] == module_id
    assert report["iterations"] == _ITERATIONS
    assert report["passed"] is True
    assert type(report["mean_budget_ns"]) is int
    assert type(report["p95_budget_ns"]) is int
    assert report["mean_budget_ns"] > 0
    assert report["p95_budget_ns"] > 0
    assert report["mean_ns"] <= report["mean_budget_ns"]
    assert report["p95_ns"] <= report["p95_budget_ns"]

    normalized = normalize_benchmark_report(report, expected_module_id=module_id)
    assert normalized["passed"] is True
    assert normalized["pass_evidence"] == [{"path": "passed", "passed": True}]
    assert normalized["budget_evidence"] == [
        {"path": "mean_budget_ns", "value": report["mean_budget_ns"]},
        {"path": "p95_budget_ns", "value": report["p95_budget_ns"]},
    ]
