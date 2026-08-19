"""Adversarial API resource-boundary coverage for replay envelopes."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT

if TYPE_CHECKING:
    from types import ModuleType


_API_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "glio_proteogen.modules.c21_reference_material.m24_07_human_factors_operational_evaluator.api",
        "M2407_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M24-07/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_01_reference_truth_benchmark_curator.api",
        "M2501_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M25-01/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_02_synthetic_truth_simulation_generator.api",
        "M2502_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M25-02/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.api",
        "M2503_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M25-03/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.api",
        "M2505_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M25-05/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_07_human_factors_operational_evaluator.api",
        "M2507_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M25-07/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator.api",
        "M2508_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M25-08/verify",
    ),
    (
        "glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator.api",
        "M2603_MAX_CANONICAL_RESULT_BYTES",
        "/v1/modules/M26-03/verify",
    ),
)


@pytest.mark.parametrize(("module_name", "constant_name", "route"), _API_CASES)
def test_verify_route_uses_declared_result_byte_bound(
    module_name: str,
    constant_name: str,
    route: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay envelopes use the result cap, not the 4 MiB request default."""

    module: ModuleType = importlib.import_module(module_name)
    expected = getattr(module, constant_name)
    seen: list[int] = []

    def record_parser(body: bytes, *, max_bytes: int) -> dict[str, object]:
        del body
        seen.append(max_bytes)
        return {}

    monkeypatch.setattr(module, "_parse_object", record_parser)
    response = TestClient(module.create_app()).post(route, content=b"{}")

    # The empty candidate is intentionally schema-invalid; the assertion is
    # that the request reached the strict parser with the declared result cap.
    assert response.status_code == HTTP_422_UNPROCESSABLE_CONTENT
    assert seen == [expected]
