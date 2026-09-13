"""Locked fixture, evidence-schema, and executable ECGI performance checks."""

# ruff: noqa: PLR2004

from __future__ import annotations

import os
from collections import Counter
from typing import TYPE_CHECKING

import pytest
from benchmarks.research_proteogenomic_state import (
    DEMO_P95_THRESHOLD_SECONDS,
    EVIDENCE_SCHEMA_VERSION,
    EXECUTION_ISOLATION,
    FIXTURE_GENERATION_VERSION,
    MAXIMUM_FIXTURE_DIGEST,
    MAXIMUM_P95_THRESHOLD_SECONDS,
    MEMORY_METRIC,
    PEAK_MEMORY_THRESHOLD_MIB,
    PerformanceEvidence,
    ScenarioEvidence,
    build_maximum_request,
    nearest_rank_percentile,
    run_performance_gate,
)
from pydantic import ValidationError

from benchmarks import research_proteogenomic_state as performance_benchmark
from glio_proteogen.research.proteogenomic_state import (
    MAX_EDGES,
    MAX_KINASES,
    MAX_NODES,
    MAX_OBSERVATIONS,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    EdgeKind,
    NodeKind,
)
from glio_proteogen.research.proteogenomic_state.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from pathlib import Path

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _scenario(
    scenario: str = "demo-64",
    *,
    passed: bool = True,
    p95_seconds: float = 0.8,
) -> ScenarioEvidence:
    maximum = scenario == "maximum-bounds"
    return ScenarioEvidence(
        scenario=scenario,  # type: ignore[arg-type]
        fixture_digest=DIGEST_A,
        result_digest=DIGEST_B,
        node_count=MAX_NODES if maximum else 64,
        edge_count=MAX_EDGES if maximum else 83,
        observation_count=MAX_OBSERVATIONS if maximum else 40,
        kinase_count=MAX_KINASES if maximum else 4,
        bootstrap_replicates=8,
        permutation_replicates=32,
        request_bytes=1_024,
        result_bytes=2_048,
        warmup_runs=1,
        measured_runs=2,
        durations_seconds=(0.5, 0.8),
        p95_seconds=p95_seconds,
        p95_threshold_seconds=10.0 if maximum else 2.0,
        peak_memory_mib=50.0,
        peak_memory_threshold_mib=PEAK_MEMORY_THRESHOLD_MIB,
        passed=passed,
    )


def _updated_scenario(value: ScenarioEvidence, **updates: object) -> ScenarioEvidence:
    payload = value.model_dump(mode="python")
    payload.update(updates)
    return ScenarioEvidence.model_validate(payload, strict=True)


def _performance_evidence(
    scenarios: tuple[ScenarioEvidence, ScenarioEvidence],
    *,
    passed: bool,
) -> PerformanceEvidence:
    return PerformanceEvidence(
        profile_digest=DIGEST_A,
        numpy_version="2.5.2",
        python_version="3.12.13",
        platform="test-platform",
        scenarios=scenarios,
        passed=passed,
    )


def test_maximum_fixture_is_locked_and_reaches_every_named_structural_bound() -> None:
    request = build_maximum_request()

    assert request.request_digest == MAXIMUM_FIXTURE_DIGEST
    assert len(request.nodes) == MAX_NODES
    assert len(request.edges) == MAX_EDGES
    assert len(request.observations) == MAX_OBSERVATIONS
    assert sum(node.kind is NodeKind.KINASE for node in request.nodes) == MAX_KINASES
    assert request.bootstrap_replicates == 64
    assert request.permutation_replicates == 256
    assert len(canonical_json_bytes(request.model_dump(mode="json"))) <= MAX_REQUEST_BYTES
    assert len({node.node_id for node in request.nodes}) == MAX_NODES
    assert len({edge.edge_id for edge in request.edges}) == MAX_EDGES
    assert len({item.observation_id for item in request.observations}) == MAX_OBSERVATIONS
    assert all(edge.kind is EdgeKind.KINASE_SUBSTRATE for edge in request.edges)
    substrate_counts = Counter(edge.source_id for edge in request.edges)
    observation_counts = Counter(item.node_id for item in request.observations)
    assert set(substrate_counts.values()) == {16}
    assert set(observation_counts.values()) == {32}


def test_performance_evidence_schema_is_versioned_strict_and_machine_readable() -> None:
    receipt = PerformanceEvidence(
        profile_digest=DIGEST_A,
        numpy_version="2.5.2",
        python_version="3.12.13",
        platform="test-platform",
        scenarios=(_scenario(), _scenario("maximum-bounds")),
        passed=True,
    )
    schema = PerformanceEvidence.model_json_schema()
    payload = canonical_json_bytes(receipt.model_dump(mode="json"))

    assert receipt.schema_version == EVIDENCE_SCHEMA_VERSION
    assert receipt.fixture_generation_version == FIXTURE_GENERATION_VERSION
    assert receipt.execution_isolation == EXECUTION_ISOLATION
    assert receipt.memory_metric == MEMORY_METRIC
    assert schema["additionalProperties"] is False
    assert "ScenarioEvidence" in schema["$defs"]
    assert PerformanceEvidence.model_validate_json(payload, strict=True) == receipt


def test_evidence_models_reject_incomplete_or_self_inconsistent_claims() -> None:
    with pytest.raises(ValidationError, match="duration count"):
        _updated_scenario(_scenario(), measured_runs=3)
    with pytest.raises(ValidationError, match="reported p95"):
        _scenario(p95_seconds=0.7)
    with pytest.raises(ValidationError, match="pass state"):
        _scenario(passed=False)
    with pytest.raises(ValidationError, match="exactly 64"):
        _updated_scenario(_scenario(), node_count=63)
    with pytest.raises(ValidationError, match="every structural bound"):
        _updated_scenario(_scenario("maximum-bounds"), edge_count=MAX_EDGES - 1)
    with pytest.raises(ValidationError, match="less than or equal"):
        _updated_scenario(_scenario(), result_bytes=MAX_RESULT_BYTES + 1)
    demo = _scenario()
    maximum = _scenario("maximum-bounds")
    with pytest.raises(ValidationError, match="both scenarios"):
        _performance_evidence((maximum, demo), passed=True)
    with pytest.raises(ValidationError, match="receipt pass state"):
        _performance_evidence((demo, maximum), passed=False)


def test_nearest_rank_p95_is_conservative_and_rejects_invalid_inputs() -> None:
    assert nearest_rank_percentile((0.5, 0.1, 0.4, 0.2, 0.3), 95) == 0.5
    assert nearest_rank_percentile((0.5,), 95) == 0.5
    with pytest.raises(ValueError, match="at least one"):
        nearest_rank_percentile((), 95)
    with pytest.raises(ValueError, match=r"\[1, 100\]"):
        nearest_rank_percentile((0.1,), 0)
    with pytest.raises(ValueError, match=r"\[1, 100\]"):
        nearest_rank_percentile((0.1,), 101)


def test_fresh_benchmark_process_has_bounded_numeric_worker_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variables = performance_benchmark._NUMERIC_THREAD_ENVIRONMENT_VARIABLES
    for variable in variables:
        monkeypatch.setenv(variable, "64")

    environment = performance_benchmark._fresh_process_environment()

    assert all(environment[variable] == "1" for variable in variables)
    assert all(os.environ[variable] == "64" for variable in variables)
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"


def test_linux_peak_rss_uses_the_current_executable_image_high_water_mark(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "status"
    status_path.write_text(
        "Name:\tpython\nVmHWM:\t73421 kB\nVmRSS:\t70000 kB\n",
        encoding="ascii",
    )
    monkeypatch.setattr(performance_benchmark, "_LINUX_PROCESS_STATUS", status_path)

    assert performance_benchmark._linux_peak_rss_bytes() == 73_421 * 1_024


@pytest.mark.parametrize(
    "status",
    [
        "Name:\tpython\n",
        "VmHWM:\t1 kB\nVmHWM:\t2 kB\n",
        "VmHWM:\tnot-a-number kB\n",
        "VmHWM:\t12 bytes\n",
        "VmHWM:\t0 kB\n",
    ],
)
def test_linux_peak_rss_fails_closed_on_invalid_procfs_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: str,
) -> None:
    status_path = tmp_path / "status"
    status_path.write_text(status, encoding="ascii")
    monkeypatch.setattr(performance_benchmark, "_LINUX_PROCESS_STATUS", status_path)

    with pytest.raises(performance_benchmark.BenchmarkError, match=r"peak.RSS"):
        performance_benchmark._linux_peak_rss_bytes()


def test_linux_peak_rss_fails_closed_when_procfs_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(performance_benchmark, "_LINUX_PROCESS_STATUS", tmp_path / "missing")

    with pytest.raises(performance_benchmark.BenchmarkError, match="procfs"):
        performance_benchmark._linux_peak_rss_bytes()


@pytest.mark.benchmark
def test_executable_performance_gate_meets_strict_acceptance_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        performance_benchmark,
        "_process_peak_rss_bytes",
        lambda: int((PEAK_MEMORY_THRESHOLD_MIB + 100.0) * 1_024 * 1_024),
    )
    evidence = run_performance_gate(warmup_runs=0, demo_runs=1, maximum_runs=1)

    assert evidence.passed
    assert evidence.execution_isolation == EXECUTION_ISOLATION
    assert evidence.memory_metric == MEMORY_METRIC
    demo, maximum = evidence.scenarios
    assert demo.p95_seconds < DEMO_P95_THRESHOLD_SECONDS
    assert maximum.p95_seconds < MAXIMUM_P95_THRESHOLD_SECONDS
    assert demo.request_bytes <= MAX_REQUEST_BYTES
    assert maximum.request_bytes <= MAX_REQUEST_BYTES
    assert demo.result_bytes <= MAX_RESULT_BYTES
    assert maximum.result_bytes <= MAX_RESULT_BYTES
    assert demo.peak_memory_mib < PEAK_MEMORY_THRESHOLD_MIB
    assert maximum.peak_memory_mib < PEAK_MEMORY_THRESHOLD_MIB
