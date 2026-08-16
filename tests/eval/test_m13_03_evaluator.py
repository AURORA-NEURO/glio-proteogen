"""Evaluator and benchmark evidence tests for M13-03."""

from __future__ import annotations

import pytest
from evals.m13_03.benchmark import run_benchmark
from evals.m13_03.run import run_evaluator

from glio_proteogen.modules.c11_protein_native_subtype import (
    m13_03_mechanistic_feature_constructor as m1303,
)
from tests.contract.test_m13_03_runtime import request

_CASE_COUNT = 7
_BENCHMARK_ITERATIONS = 3


def test_evaluator_fixture_matrix_is_complete_and_green() -> None:
    report = run_evaluator()

    assert report["module_id"] == "GLIO-PROTEOGEN-M13-03"
    assert report["declared_cases"] == report["executed_cases"] == _CASE_COUNT
    assert report["passed_cases"] == _CASE_COUNT
    assert report["all_passed"] is True
    assert (
        report["fixture_digest"]
        == "sha256:8b90ff72b65f8b8bb9ed704039a4a78a6affc95f9b0b46b0efcab4f4f1e6c607"
    )


def test_benchmark_is_bounded_and_iteration_guarded() -> None:
    report = run_benchmark(_BENCHMARK_ITERATIONS)

    assert report["iterations"] == _BENCHMARK_ITERATIONS
    assert report["budgets_pass"] is True
    with pytest.raises(ValueError, match="iterations"):
        run_benchmark(0)


def test_evaluator_construction_is_deterministic() -> None:
    candidate = request()
    first = m1303.construct_proteotype_mechanistic_features(candidate)
    second = m1303.construct_proteotype_mechanistic_features(candidate)

    assert first.result_digest == second.result_digest
