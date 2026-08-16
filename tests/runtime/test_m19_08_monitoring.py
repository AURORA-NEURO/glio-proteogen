"""Runtime and replay tests for M19-08 translation monitoring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_08 import (
    MonitorStatus,
    ObservationStatus,
    RollbackDecision,
    TranslationFindingCode,
    TranslationHealthState,
)
from glio_proteogen.kernel.models import ConsentState, SupportDecision, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_08_translation_monitoring_service as m1908,
)
from tests.contract.test_m19_08_hardening import _request


def test_healthy_monitoring_emits_report_and_replays() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_request())
    assert result.status is MonitorStatus.MONITORED
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.HEALTHY
    assert result.health_report.rollback_decision is RollbackDecision.NONE
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert engine.replay(result) == result


def test_critical_drift_triggers_rollback() -> None:
    request = _request().model_copy(
        update={
            "telemetry": (
                _request().telemetry[0].model_copy(update={"status": ObservationStatus.FAIL}),
            ),
            "rollback_policy": _request().rollback_policy.model_copy(
                update={"critical_failure_threshold": 1}
            ),
        }
    )
    result = m1908.M1908TranslationMonitoringEngine().infer(request)
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.ROLLBACK_REQUIRED
    assert result.health_report.rollback_decision is RollbackDecision.ROLLBACK
    assert any(item.code is TranslationFindingCode.ROLLBACK_REQUIRED for item in result.findings)
    assert result.human_review_required is True


def test_unresolved_discrepancy_suspends_translation() -> None:
    request = _request().model_copy(
        update={
            "discrepancies": (_request().discrepancies[0].model_copy(update={"resolved": False}),)
        }
    )
    result = m1908.M1908TranslationMonitoringEngine().infer(request)
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.SUSPENDED
    assert result.health_report.rollback_decision is RollbackDecision.SUSPEND
    assert any(
        item.code is TranslationFindingCode.DISCREPANCY_UNRESOLVED for item in result.findings
    )


def test_warning_degrades_and_requires_review() -> None:
    request = _request().model_copy(
        update={
            "support_drift": (
                _request()
                .support_drift[0]
                .model_copy(update={"status": ObservationStatus.WARNING}),
            )
        }
    )
    result = m1908.M1908TranslationMonitoringEngine().infer(request)
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.DEGRADED
    assert result.health_report.rollback_decision is RollbackDecision.REVIEW_REQUIRED
    assert result.human_review_required is True


def test_not_evaluable_observation_abstains_without_report() -> None:
    request = _request().model_copy(
        update={
            "telemetry": (
                _request()
                .telemetry[0]
                .model_copy(update={"status": ObservationStatus.NOT_EVALUABLE}),
            )
        }
    )
    result = m1908.M1908TranslationMonitoringEngine().infer(request)
    assert result.status is MonitorStatus.ABSTAINED
    assert result.health_report is None
    assert result.abstention_reason is not None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_unsupported_support_abstains_without_report() -> None:
    request = _request().model_copy(
        update={
            "support_decision": SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="unsupported_upstream",
                rationale="Synthetic unsupported export.",
            )
        }
    )
    result = m1908.M1908TranslationMonitoringEngine().infer(request)
    assert result.status is MonitorStatus.ABSTAINED
    assert result.health_report is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_control_denial_precedes_monitoring() -> None:
    base = _request()
    references = base.context.references.model_copy(
        update={
            "consent": base.context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    request = base.model_copy(
        update={"context": base.context.model_copy(update={"references": references})}
    )
    with pytest.raises(m1908.M1908AuthorizationError, match="consent"):
        m1908.M1908TranslationMonitoringEngine().infer(request)


def test_mapping_preflight_rejects_missing_controls() -> None:
    with pytest.raises(m1908.M1908AuthorizationError):
        m1908.preflight_m1908_authorization({})


def test_tampered_result_digest_is_rejected() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_request())
    tampered = result.model_copy(update={"human_review_required": True})
    with pytest.raises(m1908.M1908ReplayVerificationError, match="digest"):
        engine.replay(tampered)


def test_malformed_result_is_rejected() -> None:
    with pytest.raises(m1908.M1908ReplayVerificationError):
        m1908.M1908TranslationMonitoringEngine().verify({"result_digest": "bad"})


def test_strict_upstream_media_boundary_rejects_json() -> None:
    request = _request()
    upstream = request.upstream_result.model_copy(update={"media_type": "application/json"})
    request = request.model_copy(update={"upstream_result": upstream})
    with pytest.raises(ValidationError, match="M19-07"):
        m1908.M1908TranslationMonitoringEngine().validate_request(request)
