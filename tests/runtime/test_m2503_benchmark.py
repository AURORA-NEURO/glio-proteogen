"""Runtime, control, replay, and plugin tests for M25-03."""

from __future__ import annotations

import pytest
from evals.m25_03.fixture import build_request, denied_request
from pydantic import ValidationError

from glio_proteogen.contracts.m25_03 import BenchmarkStatus, ValidationStatus
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2503AuthorizationError,
    M2503Plugin,
    M2503ReplayError,
    M2503Service,
)


def test_service_completes_locked_metadata_benchmark() -> None:
    result = M2503Service().execute(build_request())

    assert result.status is BenchmarkStatus.COMPLETED
    assert result.dossier is not None
    assert result.dossier.locked is True
    assert result.support_decision.status.value == "supported"
    assert result.emits_parent is False


def test_service_is_deterministic_and_replayable() -> None:
    service = M2503Service()
    first = service.execute(build_request())
    second = service.execute(build_request())

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify_replay(first).model_dump(mode="json") == first.model_dump(mode="json")


def test_non_passing_metric_abstains_without_dossier() -> None:
    result = M2503Service().execute(build_request(metric_status=ValidationStatus.FAIL))

    assert result.status is BenchmarkStatus.ABSTAINED
    assert result.dossier is None
    assert result.human_review_required is True
    assert result.findings[0].code.value == "baseline_failure"
    assert result.support_decision.status.value == "review_required"


def test_denied_control_fails_before_execution() -> None:
    with pytest.raises(M2503AuthorizationError):
        M2503Service().execute(denied_request())


def test_replay_detects_digest_tampering() -> None:
    service = M2503Service()
    result = service.execute(build_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises((M2503ReplayError, ValidationError)):
        service.verify_replay(tampered)


def test_plugin_requires_submission_and_validated_token() -> None:
    service = M2503Service()
    plugin = M2503Plugin(service)

    with pytest.raises(TypeError, match="submission"):
        plugin.validate(build_request())
    token = plugin.validate(BenchmarkSubmission(build_request()))
    result = plugin.run(token)
    assert result.status is BenchmarkStatus.COMPLETED
    with pytest.raises(TypeError, match="validated request"):
        plugin.run(build_request())  # type: ignore[arg-type]


def test_plugin_strict_json_submission_is_parse_once() -> None:
    request = build_request()
    payload = request.model_dump_json()
    plugin = M2503Plugin(M2503Service())

    validated = plugin.validate(BenchmarkSubmission(payload))
    assert plugin.run(validated).request.request_id == request.request_id
