"""Runtime, service, plugin, and replay tests for provisional M24-03."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_03 import (
    BenchmarkMetric,
    BenchmarkStatus,
    ValidationStatus,
)
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m24_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2403AuthorizationError,
    M2403Plugin,
    M2403ReplayError,
    M2403Service,
    ValidatedM2403Request,
    preflight_m2403_authorization,
)
from tests.contract.test_m24_03_hardening import _artifact, _request


def test_service_returns_supported_deterministic_completed_result() -> None:
    service = M2403Service()
    first = service.generate(_request())
    second = service.generate(_request())
    assert first.status is BenchmarkStatus.COMPLETED
    assert first.dossier is not None
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.result_digest == second.result_digest
    assert first.result_id == second.result_id
    assert first.dossier.baselines[0].kind.value == "simple"
    assert {baseline.kind.value for baseline in first.dossier.baselines} == {"simple", "mature"}


def test_failed_declared_metric_is_visible_without_unsafe_abstention() -> None:
    request = _request()
    simple = request.baseline_runs[0]
    failed = BenchmarkMetric(
        metric_id=simple.metrics[0].metric_id,
        metric_name=simple.metrics[0].metric_name,
        baseline_value=0.5,
        candidate_value=1.0,
        tolerance=0.2,
        status=ValidationStatus.FAIL,
        evidence=simple.metrics[0].evidence,
    )
    changed = request.model_copy(
        update={
            "baseline_runs": (
                simple.model_copy(update={"metrics": (failed,)}),
                *request.baseline_runs[1:],
            )
        }
    )
    result = M2403Service().generate(changed)
    assert result.status is BenchmarkStatus.COMPLETED
    assert result.dossier is not None
    assert result.findings
    assert result.findings[0].code.value == "baseline_failure"


def test_not_evaluable_input_abstains_with_review_required_support() -> None:
    request = _request()
    simple = request.baseline_runs[0]
    not_evaluable = simple.metrics[0].model_copy(update={"status": ValidationStatus.NOT_EVALUABLE})
    changed = request.model_copy(
        update={
            "baseline_runs": (
                simple.model_copy(update={"metrics": (not_evaluable,)}),
                *request.baseline_runs[1:],
            )
        }
    )
    result = M2403Service().generate(changed)
    assert result.status is BenchmarkStatus.ABSTAINED
    assert result.dossier is None
    assert result.abstention_reason is not None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True


def test_preflight_fails_closed_for_denied_or_malformed_controls() -> None:
    request = _request()
    denied_quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(update={"quality": denied_quality})
        }
    )
    with pytest.raises(M2403AuthorizationError):
        M2403Service().generate(request.model_copy(update={"context": denied_context}))
    with pytest.raises(M2403AuthorizationError):
        preflight_m2403_authorization({"context": {}})


def test_wrong_upstream_media_is_rejected_at_contract_boundary() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="M24-02"):
        M2403Service().generate(
            request.model_copy(update={"upstream_result": _artifact("wrong", "application/json")})
        )


def test_replay_rejects_result_tampering_and_plugin_requires_capability() -> None:
    service = M2403Service()
    result = service.generate(_request())
    with pytest.raises(M2403ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    plugin = M2403Plugin(service)
    validated = plugin.validate(BenchmarkSubmission(request=_request()))
    assert isinstance(validated, ValidatedM2403Request)
    assert plugin.run(validated).result_digest == result.result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_strict_json_rejects_unknown_fields() -> None:
    service = M2403Service()
    plugin = M2403Plugin(service)
    document = _request().model_dump_json().encode()
    hostile = document[:-1] + b',"extra":true}'
    with pytest.raises(ValidationError):
        plugin.validate(BenchmarkSubmission(request=hostile))


__all__ = []
