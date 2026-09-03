"""M01-02 public-boundary latency and deterministic scaling tripwires.

Budgets are intentionally broad across CI hardware. They detect algorithmic or persistence
regressions, not small machine-to-machine variance. The maximum graph benchmark isolates the
near-linear reconciliation kernel with matched CPU-time samples while pytest-benchmark
independently records wall latency; contract, public solver, and ledger replay have separate gates.
"""

from __future__ import annotations

import gc
import tracemalloc
from pathlib import Path
from statistics import median
from time import process_time_ns
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import TypeAdapter

from benchmarks._module_validation import run_pytest_benchmark
from glio_proteogen.contracts.m01_02.v1 import ReconcileIdentityLineageRequest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    M0102Service,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.solver import (
    _analyze,
    reconcile_identity_lineage,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Protocol, TypeVar

    _ResultT = TypeVar("_ResultT")

    class _TimingStatistics(Protocol):
        mean: float

    class _BenchmarkStatistics(Protocol):
        stats: _TimingStatistics

    class BenchmarkFixture(Protocol):
        stats: _BenchmarkStatistics
        extra_info: dict[str, object]

        def __call__(
            self,
            operation: Callable[..., _ResultT],
            *args: object,
            **kwargs: object,
        ) -> _ResultT: ...

        def pedantic(
            self,
            operation: Callable[..., _ResultT],
            *,
            args: tuple[object, ...] = (),
            rounds: int,
            warmup_rounds: int,
            iterations: int,
        ) -> _ResultT: ...


ROOT = Path(__file__).parents[1]
SCENARIO_PATH = ROOT / "tests" / "fixtures" / "m01_02" / "scenarios.json"
REFERENCE_CONTRACT_MEAN_BUDGET_SECONDS = 0.005
REFERENCE_SOLVER_MEAN_BUDGET_SECONDS = 0.010
SERVICE_REPLAY_MEAN_BUDGET_SECONDS = 0.020
MAX_GRAPH_MEAN_BUDGET_SECONDS = 1.500
MAX_GRAPH_FOURFOLD_RATIO = 6.5
MAX_GRAPH_PEAK_BYTES = 256 * 1024 * 1024
REFERENCE_EDGE_COUNT = 6
MAX_GRAPH_NODES = 10_000
SCALING_BASELINE_NODES = MAX_GRAPH_NODES // 4
SCALING_TIMING_ROUNDS = 5
SCALING_MAXIMUM_REPETITIONS = 2
SCALING_BASELINE_REPETITIONS = (
    SCALING_MAXIMUM_REPETITIONS * MAX_GRAPH_NODES // SCALING_BASELINE_NODES
)
MAX_GRAPH_BENCHMARK_ROUNDS = 3
_REQUEST_ADAPTER = TypeAdapter(ReconcileIdentityLineageRequest)

pytestmark = pytest.mark.benchmark


def _artifact(role: str, digest_character: str) -> dict[str, str]:
    return {
        "artifact_id": f"artifact.synthetic.{role}",
        "version": "1.0.0",
        "digest": f"sha256:{digest_character * 64}",
        "media_type": "application/json",
    }


def _context() -> dict[str, Any]:
    evidence = _artifact("control", "e")
    accepted = {
        "state": "accepted",
        "policy_version": "1.0.0",
        "evidence": evidence,
    }
    return {
        "request_id": "request.synthetic.benchmark",
        "actor_id": "actor.synthetic.benchmark",
        "occurred_at": "2026-08-11T00:00:00Z",
        "references": {
            "approved_configuration": {
                **accepted,
                "decision_id": "decision.synthetic.approved-configuration",
            },
            "identity_authority": {
                **accepted,
                "decision_id": "authority.synthetic.v1",
            },
            "provenance": {**accepted, "decision_id": "decision.synthetic.provenance"},
            "consent": {
                **accepted,
                "decision_id": "decision.synthetic.consent",
                "state": "granted",
            },
            "quality": {**accepted, "decision_id": "decision.synthetic.quality"},
            "support": {**accepted, "decision_id": "decision.synthetic.support"},
            "intended_use": {
                **accepted,
                "decision_id": "decision.synthetic.intended-use",
            },
        },
    }


def _reference_payload() -> dict[str, Any]:
    corpus = cast(
        "dict[str, Any]",
        strict_json_loads(SCENARIO_PATH.read_bytes()),
    )
    return cast(
        "dict[str, Any]",
        next(
            scenario["request"]
            for scenario in corpus["scenarios"]
            if scenario["case_id"] == "complete_ordinary_lineage"
        ),
    )


def _reference_request() -> ReconcileIdentityLineageRequest:
    return _REQUEST_ADAPTER.validate_json(
        canonical_json_bytes(_reference_payload()),
        strict=True,
    )


def _maximum_wide_dag(node_count: int = MAX_GRAPH_NODES) -> dict[str, Any]:
    entity_evidence = [_artifact("entity", "a")]
    operation_evidence = [_artifact("operation", "c")]
    entities = [
        {
            "entity_id": f"obj-{index:05d}",
            "kind": "derived_object",
            "composition": "unknown",
            "identity_tokens": [],
            "evidence": entity_evidence,
        }
        for index in range(node_count)
    ]
    operations = [
        {
            "operation_id": f"op-{index:05d}",
            "kind": "computed_from",
            "source_entity_ids": ["obj-00000"],
            "target_entity_ids": [f"obj-{index:05d}"],
            "mixed_subject": False,
            "authority_decision_id": "authority.synthetic.v1",
            "policy_version": "1.0.0",
            "evidence": operation_evidence,
        }
        for index in range(1, node_count)
    ]
    return {
        "policy": {
            "policy_id": "policy.synthetic.benchmark",
            "version": "1.0.0",
            "max_component_size": 256,
            "maximum_depth": 64,
            "allow_mixed_subject_pooling": False,
            "require_demultiplex_authority": True,
            "allowed_operation_kinds": ["computed_from"],
        },
        "context": _context(),
        "entities": entities,
        "assertions": [],
        "lineage_operations": operations,
        "concordance_observations": [],
    }


def _cpu_seconds_per_analysis(request: dict[str, Any], repetitions: int) -> float:
    started = process_time_ns()
    for _ in range(repetitions):
        _analyze(cast("Any", request))
    return (process_time_ns() - started) / repetitions / 1_000_000_000


def _paired_median_cpu_seconds(
    baseline: dict[str, Any],
    maximum: dict[str, Any],
) -> tuple[float, float]:
    _analyze(cast("Any", baseline))
    _analyze(cast("Any", maximum))
    baseline_samples: list[float] = []
    maximum_samples: list[float] = []
    workloads = (
        (baseline, SCALING_BASELINE_REPETITIONS, baseline_samples),
        (maximum, SCALING_MAXIMUM_REPETITIONS, maximum_samples),
    )
    for round_index in range(SCALING_TIMING_ROUNDS):
        # Alternate equal-node-work batches to remove ordering and CPU-frequency drift. Collection
        # remains outside the measured region so an unrelated prior test cannot inject a cyclic-GC
        # pause. Process CPU time excludes hosted-runner preemption, which can affect a 10k-node
        # wall sample without affecting its shorter baseline.
        ordered_workloads = workloads if round_index % 2 == 0 else reversed(workloads)
        for request, repetitions, samples in ordered_workloads:
            gc.collect()
            samples.append(_cpu_seconds_per_analysis(request, repetitions))
    return median(baseline_samples), median(maximum_samples)


def test_reference_strict_contract_mean_latency(benchmark: BenchmarkFixture) -> None:
    encoded = canonical_json_bytes(_reference_payload())

    request = benchmark(_REQUEST_ADAPTER.validate_json, encoded, strict=True)

    benchmark.extra_info.update(
        {
            "boundary": "strict JSON to typed request",
            "entity_count": len(request.entities),
            "mean_budget_seconds": REFERENCE_CONTRACT_MEAN_BUDGET_SECONDS,
        }
    )
    assert len(request.lineage_operations) == REFERENCE_EDGE_COUNT
    assert benchmark.stats.stats.mean <= REFERENCE_CONTRACT_MEAN_BUDGET_SECONDS


def test_reference_public_solver_mean_latency(benchmark: BenchmarkFixture) -> None:
    request = _reference_request()

    draft = benchmark(reconcile_identity_lineage, request)

    benchmark.extra_info.update(
        {
            "boundary": "typed request to pure public resolution draft",
            "entity_count": len(request.entities),
            "mean_budget_seconds": REFERENCE_SOLVER_MEAN_BUDGET_SECONDS,
        }
    )
    assert len(draft.graph.operations) == REFERENCE_EDGE_COUNT
    assert not draft.issues
    assert benchmark.stats.stats.mean <= REFERENCE_SOLVER_MEAN_BUDGET_SECONDS


def test_exact_service_replay_mean_latency(
    benchmark: BenchmarkFixture,
    tmp_path: Path,
) -> None:
    request = _reference_request()
    runtime = M0102Service(M0102EventStore(tmp_path / "replay.sqlite3"))
    expected = runtime.execute(request)
    try:
        actual = benchmark(runtime.execute, request)
        verification = runtime.verify_event_chain()
    finally:
        runtime.close()

    benchmark.extra_info.update(
        {
            "boundary": "authorized exact replay through verified SQLite ledger",
            "committed_event_count": verification.event_count,
            "mean_budget_seconds": SERVICE_REPLAY_MEAN_BUDGET_SECONDS,
        }
    )
    assert actual == expected
    assert verification.valid
    assert verification.event_count == 1
    assert benchmark.stats.stats.mean <= SERVICE_REPLAY_MEAN_BUDGET_SECONDS


def test_ten_thousand_node_wide_dag_stays_within_linear_budget(
    benchmark: BenchmarkFixture,
) -> None:
    request = _maximum_wide_dag()
    baseline = _maximum_wide_dag(SCALING_BASELINE_NODES)
    baseline_cpu_seconds, maximum_cpu_seconds = _paired_median_cpu_seconds(
        baseline,
        request,
    )
    fourfold_ratio = maximum_cpu_seconds / baseline_cpu_seconds

    analysis = benchmark.pedantic(
        _analyze,
        args=(cast("Any", request),),
        rounds=MAX_GRAPH_BENCHMARK_ROUNDS,
        warmup_rounds=1,
        iterations=1,
    )
    maximum_seconds = benchmark.stats.stats.mean

    tracemalloc.start()
    try:
        traced = _analyze(cast("Any", request))
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    benchmark.extra_info.update(
        {
            "complexity_expectation": (
                "near-linear; O((V + E) log(V + E)) deterministic-ordering bound"
            ),
            "baseline_nodes": SCALING_BASELINE_NODES,
            "maximum_nodes": MAX_GRAPH_NODES,
            "maximum_edges": MAX_GRAPH_NODES - 1,
            "fourfold_latency_ratio": fourfold_ratio,
            "fourfold_ratio_budget": MAX_GRAPH_FOURFOLD_RATIO,
            "scaling_clock": "process_time_ns",
            "scaling_design": "paired-equal-node-work-alternating-order",
            "scaling_timing_rounds": SCALING_TIMING_ROUNDS,
            "scaling_baseline_repetitions": SCALING_BASELINE_REPETITIONS,
            "scaling_maximum_repetitions": SCALING_MAXIMUM_REPETITIONS,
            "baseline_median_cpu_seconds": baseline_cpu_seconds,
            "maximum_median_cpu_seconds": maximum_cpu_seconds,
            "peak_traced_bytes": peak_bytes,
            "peak_traced_bytes_budget": MAX_GRAPH_PEAK_BYTES,
            "mean_budget_seconds": MAX_GRAPH_MEAN_BUDGET_SECONDS,
        }
    )
    assert len(analysis.components) == MAX_GRAPH_NODES
    assert len(analysis.lineage_edges) == MAX_GRAPH_NODES - 1
    assert not analysis.issues
    assert len(traced.components) == MAX_GRAPH_NODES
    assert maximum_seconds <= MAX_GRAPH_MEAN_BUDGET_SECONDS
    assert fourfold_ratio <= MAX_GRAPH_FOURFOLD_RATIO
    assert peak_bytes <= MAX_GRAPH_PEAK_BYTES


def run_benchmark(iterations: int = 10) -> dict[str, object]:
    """Run the locked representative public lineage solver workload."""

    return run_pytest_benchmark(
        module_id="GLIO-PROTEOGEN-M01-02",
        workload=test_reference_public_solver_mean_latency,
        iterations=iterations,
        mean_budget_seconds=REFERENCE_SOLVER_MEAN_BUDGET_SECONDS,
    )
