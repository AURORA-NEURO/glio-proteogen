"""Evaluator and benchmark evidence checks for provisional M06-03."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final, cast

import pytest
from evals.m06_03 import benchmark
from evals.m06_03.benchmark import run_benchmark
from evals.m06_03.run import build_scenario, canonical_smoke, main, run_evaluation

from glio_proteogen.contracts.m06_03 import M0603_BENCHMARK_ITERATIONS

if TYPE_CHECKING:
    from pathlib import Path

    from _pytest.capture import CaptureFixture

SCENARIO_COUNT: Final = 3


def test_evaluator_closes_all_declared_scenarios(capsys: CaptureFixture[str]) -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert len(cast("list[object]", report["checks"])) == SCENARIO_COUNT
    assert canonical_smoke()["status"] == "estimated"
    assert main(["--json"]) == 0
    assert "GLIO-PROTEOGEN-M06-03" in capsys.readouterr().out
    assert main([]) == 0
    assert "GLIO-PROTEOGEN-M06-03" in capsys.readouterr().out
    assert build_scenario("clear") is build_scenario("clear")


def test_benchmark_uses_exact_public_workload() -> None:
    report = run_benchmark()
    assert report.module_id == "GLIO-PROTEOGEN-M06-03"
    assert report.iterations == M0603_BENCHMARK_ITERATIONS
    assert report.warmup_count == 1
    assert (
        report.feature_count
        == report.estimate_count
        == report.diagnostic_count
        == SCENARIO_COUNT
    )
    assert report.passed is True


def test_benchmark_writes_json_report(tmp_path: Path) -> None:
    output = tmp_path / "benchmark.json"
    assert benchmark.main(["--output", str(output)]) == 0
    assert output.exists()


def test_benchmark_rejects_invalid_representative_workload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario("clear")
    original = benchmark.estimate_protein_abundance_baseline
    warmup = original(scenario.request)
    monkeypatch.setattr(
        benchmark,
        "build_scenario",
        lambda _case_id: scenario.__class__(
            scenario.case_id,
            scenario.request.model_copy(update={"feature_values": ()}),
            scenario.expected_status,
        ),
    )
    monkeypatch.setattr(benchmark, "estimate_protein_abundance_baseline", lambda _request: warmup)
    with pytest.raises(benchmark.InvalidRepresentativeWorkloadError):
        run_benchmark()


def test_benchmark_rejects_nondeterministic_public_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario("clear")
    estimator = cast("Any", benchmark.estimate_protein_abundance_baseline)
    original = estimator
    warmup = original(scenario.request)
    calls = 0

    def changed(_request: Any) -> Any:
        nonlocal calls
        calls += 1
        return (
            warmup
            if calls == 1
            else warmup.model_copy(update={"result_digest": "sha256:" + "0" * 64})
        )

    monkeypatch.setattr(benchmark, "estimate_protein_abundance_baseline", changed)
    with pytest.raises(benchmark.NonDeterministicBenchmarkError):
        run_benchmark()
