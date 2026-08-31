"""M04-03 representative benchmark boundary and estimator checks."""

from __future__ import annotations

import gc
from types import SimpleNamespace

import pytest
from evals.m04_03 import benchmark

from glio_proteogen.contracts.m04_03 import (
    M0403_LIMITATION_COUNT,
    M0403_MIN_EVIDENCE,
    M0403_ROLE_COUNT,
    ProteoformRawInputDisposition,
)

_GC_COLLECTED_OBJECTS = 17
_STARTED_NS = 100
_FINISHED_NS = 200
_ELAPSED_NS = _FINISHED_NS - _STARTED_NS
_EXPECTED_DEFAULT_ITERATIONS = 100
_EXPECTED_P95_INDEX = 94


def _synthetic_representative_workload() -> tuple[SimpleNamespace, SimpleNamespace]:
    request = SimpleNamespace(artifacts=(None,) * M0403_ROLE_COUNT)
    scenario = SimpleNamespace(
        request=request,
        artifacts_by_role=dict.fromkeys(range(M0403_ROLE_COUNT), b"{}"),
    )
    result = SimpleNamespace(
        disposition=ProteoformRawInputDisposition.VALIDATED,
        validated_inputs=(None,) * M0403_ROLE_COUNT,
        diagnostics=(),
        evidence=(None,) * M0403_MIN_EVIDENCE,
        limitations=(None,) * M0403_LIMITATION_COUNT,
        parent_target="protein_rna_discordance",
        request_digest="sha256:" + ("1" * 64),
        result_digest="sha256:" + ("2" * 64),
    )
    return scenario, result


def test_default_sample_count_produces_a_real_p95_tail() -> None:
    assert benchmark.ITERATIONS == _EXPECTED_DEFAULT_ITERATIONS
    assert (95 * benchmark.ITERATIONS - 1) // 100 == _EXPECTED_P95_INDEX


def test_untimed_setup_gc_precedes_every_timed_call(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario, expected = _synthetic_representative_workload()
    events: list[str] = []
    ticks = iter((_STARTED_NS, _FINISHED_NS))

    def ingest(request: object, artifacts_by_role: object) -> object:
        assert request is scenario.request
        assert artifacts_by_role is scenario.artifacts_by_role
        events.append("ingest")
        return expected

    def collect() -> int:
        events.append("collect")
        return _GC_COLLECTED_OBJECTS

    monkeypatch.setattr(benchmark, "build_scenario", lambda: scenario)
    monkeypatch.setattr(benchmark, "ingest_proteoform_raw_inputs", ingest)
    monkeypatch.setattr(gc, "collect", collect)
    monkeypatch.setattr(benchmark, "process_time_ns", lambda: next(ticks))

    report = benchmark.run_benchmark(iterations=1)

    assert events == ["ingest", "collect", "ingest"]
    assert report.pre_timing_gc_collected_objects == _GC_COLLECTED_OBJECTS
    assert report.cyclic_gc_enabled_during_timing is True
    assert report.measurement_clock == "process_time_ns"
    assert report.mean_ns == _ELAPSED_NS
    assert report.passed is True


def test_disabled_cyclic_gc_is_rejected_before_scenario_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gc, "isenabled", lambda: False)
    monkeypatch.setattr(
        benchmark,
        "build_scenario",
        lambda: pytest.fail("scenario must not be built for an invalid benchmark environment"),
    )

    with pytest.raises(benchmark.InvalidBenchmarkEnvironmentError):
        benchmark.run_benchmark(iterations=1)


def test_nonpositive_iteration_count_is_rejected_before_gc_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gc,
        "isenabled",
        lambda: pytest.fail("GC must not be inspected for an invalid iteration count"),
    )

    with pytest.raises(ValueError, match="iterations must be positive"):
        benchmark.run_benchmark(iterations=0)
