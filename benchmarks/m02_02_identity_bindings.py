"""M02-02 representative batch binding-audit benchmark with a broad tripwire."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m02_02.run import build_scenario_request

from glio_proteogen.contracts.m02_02 import BindingDisposition
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    evaluate_identity_bindings,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from glio_proteogen.contracts.m02_02 import ValidateIdentityBindingsRequest

MEAN_BUDGET_SECONDS = 0.500
BATCH_SIZE = 32

pytestmark = pytest.mark.benchmark


def _audit_batch(
    batch: tuple[ValidateIdentityBindingsRequest, ...],
) -> tuple[BindingDisposition, ...]:
    return tuple(evaluate_identity_bindings(request).disposition for request in batch)


def test_representative_public_batch_binding_audit_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_scenario_request("canonical")
    batch = tuple(request for _ in range(BATCH_SIZE))

    dispositions = benchmark(_audit_batch, batch)

    benchmark.extra_info.update(
        {
            "boundary": "pinned synthetic opaque bindings to deterministic audit states",
            "batch_size": BATCH_SIZE,
            "bindings_per_request": len(request.bindings),
            "upstream_graph_nodes": len(request.identity_resolution.graph.nodes),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert dispositions == (BindingDisposition.CONFORMANT,) * BATCH_SIZE
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
