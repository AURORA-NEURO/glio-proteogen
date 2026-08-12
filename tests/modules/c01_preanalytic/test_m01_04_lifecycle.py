"""Focused lifecycle tests for the thin M01-04 service and plugin."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m01_04 import (
    Computation,
    ComputeQualityMetricsRequest,
    QualityDisposition,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics import (
    M0104Plugin,
    M0104Service,
    ValidatedM0104Request,
)
from tests.modules.c01_preanalytic.test_m01_04_engine import (
    _definition,
    _observation,
    _request,
)


def _valid_request() -> ComputeQualityMetricsRequest:
    definition = _definition("metric.lifecycle", Computation.DIRECT, ("value",))
    return _request((definition,), (_observation("value", 0.9),))


def test_service_is_stateless_and_deterministic() -> None:
    request = _valid_request()
    service = M0104Service()

    assert service.execute(request) == service.execute(request)


def test_service_revalidates_mutated_mapping() -> None:
    candidate = _valid_request().model_dump(mode="python")
    candidate["operation"] = "not-quality"

    with pytest.raises(ValidationError):
        M0104Service().execute(candidate)


@pytest.mark.parametrize("as_bytes", [False, True])
def test_plugin_accepts_strict_json_and_returns_typed_token(*, as_bytes: bool) -> None:
    request = _valid_request()
    serialized: str | bytes = request.model_dump_json()
    if as_bytes:
        serialized = serialized.encode()
    plugin = M0104Plugin(M0104Service())

    token = plugin.validate(serialized)
    result = plugin.run(token)

    assert isinstance(token, ValidatedM0104Request)
    assert result.disposition is QualityDisposition.ACCEPTED


def test_plugin_descriptor_locks_safety_boundary() -> None:
    descriptor = M0104Plugin(M0104Service()).descriptor()

    assert descriptor.module_id == "GLIO-PROTEOGEN-M01-04"
    assert descriptor.gate == "G1"
    assert any("kinase" in item for item in descriptor.prohibited_outputs)


def test_plugin_rejects_unvalidated_execution_token() -> None:
    plugin = M0104Plugin(M0104Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM0104Request", object()))


def test_plugin_revalidates_forged_token() -> None:
    request = _valid_request()
    forged = request.model_construct(operation="not-quality")
    token = ValidatedM0104Request(request=forged)

    with pytest.raises(ValidationError):
        M0104Plugin(M0104Service()).run(token)
