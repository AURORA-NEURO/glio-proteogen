"""Focused lifecycle tests for the thin M01-05 service and plugin."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m01_05 import (
    ArtifactClass,
    DetectArtifactsRequest,
    DetectionDisposition,
)
from glio_proteogen.modules.c01_preanalytic.m01_05_artifact_detection import (
    M0105Plugin,
    M0105Service,
    ValidatedM0105Request,
)
from tests.modules.c01_preanalytic.test_m01_05_engine import _request, _rule, _signal


def _valid_request() -> DetectArtifactsRequest:
    rule = _rule("rule.lifecycle", ArtifactClass.TECHNICAL, "signal.lifecycle")
    return _request((rule,), (_signal("target.a", "signal.lifecycle", 0.1),))


def test_service_is_stateless_and_deterministic() -> None:
    request = _valid_request()
    service = M0105Service()

    assert service.execute(request) == service.execute(request)


def test_service_revalidates_mutated_mapping() -> None:
    candidate = _valid_request().model_dump(mode="python")
    candidate["operation"] = "not-artifact-detection"

    with pytest.raises(ValidationError):
        M0105Service().execute(candidate)


@pytest.mark.parametrize("as_bytes", [False, True])
def test_plugin_accepts_strict_json(*, as_bytes: bool) -> None:
    request = _valid_request()
    serialized: str | bytes = request.model_dump_json()
    if as_bytes:
        serialized = serialized.encode()
    plugin = M0105Plugin(M0105Service())

    token = plugin.validate(serialized)
    result = plugin.run(token)

    assert isinstance(token, ValidatedM0105Request)
    assert result.disposition is DetectionDisposition.ACCEPTED


def test_plugin_descriptor_locks_safety_boundary() -> None:
    descriptor = M0105Plugin(M0105Service()).descriptor()

    assert descriptor.module_id == "GLIO-PROTEOGEN-M01-05"
    assert descriptor.gate == "G1"
    assert any("kinase" in item for item in descriptor.prohibited_outputs)


def test_plugin_rejects_unvalidated_execution_token() -> None:
    plugin = M0105Plugin(M0105Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("ValidatedM0105Request", object()))


def test_plugin_revalidates_forged_token() -> None:
    request = _valid_request()
    forged = request.model_construct(operation="not-artifact-detection")

    with pytest.raises(ValidationError):
        M0105Plugin(M0105Service()).run(ValidatedM0105Request(request=forged))
