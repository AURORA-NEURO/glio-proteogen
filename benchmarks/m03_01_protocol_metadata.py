"""M03-01 representative public protocol-conformance benchmark."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m03_01.run import build_scenario_request

from glio_proteogen.contracts.m03_01 import (
    M0301_HANDOFF_ROLE_COUNT,
    ProtocolConformanceDisposition,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    evaluate_protein_inference_protocol,
)

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

MEAN_BUDGET_SECONDS = 0.100
EXPECTED_PROTOCOL_SECTIONS = 8

pytestmark = pytest.mark.benchmark


def test_representative_public_protocol_conformance_latency(
    benchmark: BenchmarkFixture,
) -> None:
    request = build_scenario_request("canonical")

    result = benchmark(evaluate_protein_inference_protocol, request)

    benchmark.extra_info.update(
        {
            "boundary": "complete reviewed protein-inference protocol to conformance receipt",
            "search_space_sequences": (
                request.protocol_schema.search_space.composition.total_sequences
            ),
            "protocol_sections": EXPECTED_PROTOCOL_SECTIONS,
            "thresholds": len(request.protocol_schema.error_control.thresholds),
            "handoff_roles": len(
                request.protocol_schema.complex_activity_handoff.required_receipt_roles
            ),
            "mean_budget_seconds": MEAN_BUDGET_SECONDS,
        }
    )
    assert result.disposition is ProtocolConformanceDisposition.CONFORMANT
    assert len(result.findings) == EXPECTED_PROTOCOL_SECTIONS
    assert (
        len(result.protocol_schema.complex_activity_handoff.required_receipt_roles)
        == M0301_HANDOFF_ROLE_COUNT
    )
    benchmark_stats = benchmark.stats
    assert benchmark_stats is not None
    statistics = benchmark_stats.stats
    assert statistics is not None
    assert statistics.mean <= MEAN_BUDGET_SECONDS
