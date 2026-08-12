"""M01-02 public-boundary latency and deterministic scaling tripwires.

Budgets are intentionally broad across CI hardware. They detect algorithmic or persistence
regressions, not small machine-to-machine variance. The maximum graph benchmark isolates the
linear reconciliation kernel; contract, public solver, and ledger replay have separate gates.
"""

from __future__ import annotations

import tracemalloc
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import TypeAdapter

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
    from pytest_benchmark.fixture import BenchmarkFixture

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
SCALING_TIMING_ROUNDS = 3
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


def _median_runtime_seconds(request: dict[str, Any]) -> float:
    _analyze(cast("Any", request))
    samples: list[int] = []
    for _ in range(SCALING_TIMING_ROUNDS):
        started = perf_counter_ns()
        _analyze(cast("Any", request))
        samples.append(perf_counter_ns() - started)
    return median(samples) / 1_000_000_000


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
    baseline_seconds = _median_runtime_seconds(baseline)

    analysis = benchmark.pedantic(
        _analyze,
        args=(cast("Any", request),),
        rounds=MAX_GRAPH_BENCHMARK_ROUNDS,
        warmup_rounds=1,
        iterations=1,
    )
    maximum_seconds = benchmark.stats.stats.mean
    fourfold_ratio = maximum_seconds / baseline_seconds

    tracemalloc.start()
    try:
        traced = _analyze(cast("Any", request))
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    benchmark.extra_info.update(
        {
            "complexity_expectation": "O(V + E)",
            "baseline_nodes": SCALING_BASELINE_NODES,
            "maximum_nodes": MAX_GRAPH_NODES,
            "maximum_edges": MAX_GRAPH_NODES - 1,
            "fourfold_latency_ratio": fourfold_ratio,
            "fourfold_ratio_budget": MAX_GRAPH_FOURFOLD_RATIO,
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
