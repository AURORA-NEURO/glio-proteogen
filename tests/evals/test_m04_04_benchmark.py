"""M04-04 representative benchmark boundary checks."""

from __future__ import annotations

import gc
from types import SimpleNamespace

import pytest
from evals.m04_04 import benchmark

from glio_proteogen.contracts.m04_04 import (
    M0404_COMPUTED_METRIC_COUNT,
    M0404_LIMITATION_COUNT,
    M0404_MAX_EVIDENCE,
    M0404_MAX_PROFILES,
    M0404_METRIC_COUNT,
    M0404_ROLE_COUNT,
    ProteoformQualityDisposition,
)

_GC_COLLECTED_OBJECTS = 17
_STARTED_NS = 100
_FINISHED_NS = 200
_ELAPSED_NS = _FINISHED_NS - _STARTED_NS


def _synthetic_maximum_shape() -> tuple[SimpleNamespace, SimpleNamespace]:
    profiles = tuple(
        SimpleNamespace(thresholds=(None,) * M0404_METRIC_COUNT) for _ in range(M0404_MAX_PROFILES)
    )
    request = SimpleNamespace(
        policy=SimpleNamespace(profiles=profiles),
        fact_ledger=SimpleNamespace(role_facts=(None,) * M0404_ROLE_COUNT),
    )
    metrics_per_role = M0404_COMPUTED_METRIC_COUNT // M0404_ROLE_COUNT
    result = SimpleNamespace(
        assay_quality=tuple(
            SimpleNamespace(metrics=(None,) * metrics_per_role) for _ in range(M0404_ROLE_COUNT)
        ),
        disposition=ProteoformQualityDisposition.QUALIFIED,
        evidence=(None,) * M0404_MAX_EVIDENCE,
        limitations=(None,) * M0404_LIMITATION_COUNT,
        parent_target="protein_rna_discordance",
        request_digest="sha256:" + ("1" * 64),
        result_digest="sha256:" + ("2" * 64),
    )
    return SimpleNamespace(request=request), result


def test_untimed_setup_gc_precedes_every_timed_call(monkeypatch: pytest.MonkeyPatch) -> None:
    scenario, expected = _synthetic_maximum_shape()
    events: list[str] = []
    ticks = iter((_STARTED_NS, _FINISHED_NS))

    def compute(request: object) -> object:
        assert request is scenario.request
        events.append("compute")
        return expected

    def collect() -> int:
        events.append("collect")
        return _GC_COLLECTED_OBJECTS

    monkeypatch.setattr(benchmark, "build_representative_quality_fixture", lambda: scenario)
    monkeypatch.setattr(benchmark, "compute_proteoform_quality_metrics", compute)
    monkeypatch.setattr(gc, "collect", collect)
    monkeypatch.setattr(benchmark, "process_time_ns", lambda: next(ticks))

    report = benchmark.run_benchmark(iterations=1)

    assert events == ["compute", "collect", "compute"]
    assert report.pre_timing_gc_collected_objects == _GC_COLLECTED_OBJECTS
    assert report.cyclic_gc_enabled_during_timing is True
    assert report.measurement_clock == "process_time_ns"
    assert report.mean_ns == _ELAPSED_NS
    assert report.passed is True


def test_disabled_cyclic_gc_is_rejected_before_fixture_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gc, "isenabled", lambda: False)
    monkeypatch.setattr(
        benchmark,
        "build_representative_quality_fixture",
        lambda: pytest.fail("fixture must not be built for an invalid benchmark environment"),
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
