"""Runtime, service, plugin, and replay tests for provisional M24-04."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m24_04 import TransportStatus
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m24_04_external_transport_evaluator import (
    ExternalTransportSubmission,
    M2404AuthorizationError,
    M2404Plugin,
    M2404ReplayError,
    M2404Service,
    ValidatedM2404Request,
    preflight_m2404_authorization,
)
from tests.contract.test_m24_04_hardening import _request


def test_service_returns_supported_deterministic_transport_report() -> None:
    service = M2404Service()
    first = service.generate(_request())
    second = service.generate(_request())
    assert first.status.value == "evaluated"
    assert first.report is not None
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.result_digest == second.result_digest
    assert first.result_id == second.result_id
    assert set(first.report.support_domain.retained_dimensions) == {
        evaluation.dimension for evaluation in _request().evaluations
    }


def test_not_evaluable_transport_abstains_without_negative_claim() -> None:
    request = _request()
    changed = request.model_copy(
        update={
            "evaluations": (
                request.evaluations[0].model_copy(update={"status": TransportStatus.NOT_EVALUABLE}),
                *request.evaluations[1:],
            )
        }
    )
    result = M2404Service().generate(changed)
    assert result.status.value == "abstained"
    assert result.report is None
    assert result.abstention_reason is not None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required


def test_domain_narrowing_abstains_and_preserves_finding() -> None:
    request = _request()
    changed = request.model_copy(
        update={
            "evaluations": (
                request.evaluations[0].model_copy(
                    update={
                        "status": TransportStatus.DOMAIN_NARROWED,
                        "metric_value": 0.4,
                    }
                ),
                *request.evaluations[1:],
            )
        }
    )
    result = M2404Service().generate(changed)
    assert result.report is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.findings[0].code.value == "calibration_floor_failed"


def test_preflight_fails_closed_for_denied_or_malformed_controls() -> None:
    request = _request()
    denied = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"quality": denied})}
    )
    with pytest.raises(M2404AuthorizationError):
        M2404Service().generate(request.model_copy(update={"context": context}))
    with pytest.raises(M2404AuthorizationError):
        preflight_m2404_authorization({"context": {}})


def test_replay_rejects_tampering_and_plugin_requires_capability() -> None:
    service = M2404Service()
    result = service.generate(_request())
    with pytest.raises(M2404ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    plugin = M2404Plugin(service)
    validated = plugin.validate(ExternalTransportSubmission(request=_request()))
    assert isinstance(validated, ValidatedM2404Request)
    assert plugin.run(validated).result_digest == result.result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_plugin_strict_json_rejects_unknown_fields() -> None:
    plugin = M2404Plugin(M2404Service())
    document = _request().model_dump_json().encode()
    hostile = document[:-1] + b',"extra":true}'
    with pytest.raises(ValidationError):
        plugin.validate(ExternalTransportSubmission(request=hostile))


__all__ = []
