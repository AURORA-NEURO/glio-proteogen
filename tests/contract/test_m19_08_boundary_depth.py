"""Deep M19-08 claims-ceiling and safe-abstention coverage."""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import pytest

from glio_proteogen.contracts.m19_08 import (
    MonitorProteotypeTranslationHealthRequest,
    MonitorStatus,
    TranslationFindingCode,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_08_translation_monitoring_service as m1908,
)
from tests.contract.test_m19_08_hardening import _request

_PROHIBITED_TEXT: Final = "caller claims protein inference for glioma-specific biology"
type _EngineUpdate = Callable[
    [MonitorProteotypeTranslationHealthRequest], MonitorProteotypeTranslationHealthRequest
]


def _with_telemetry_metric(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    telemetry = request.telemetry[0].model_copy(update={"metric_name": _PROHIBITED_TEXT})
    return request.model_copy(update={"telemetry": (telemetry, *request.telemetry[1:])})


def _with_support_dimension(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    support = request.support_drift[0].model_copy(update={"support_dimension": _PROHIBITED_TEXT})
    return request.model_copy(update={"support_drift": (support, *request.support_drift[1:])})


def _with_workflow_description(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    workflow = request.workflow_effects[0].model_copy(
        update={"effect_description": _PROHIBITED_TEXT}
    )
    return request.model_copy(
        update={"workflow_effects": (workflow, *request.workflow_effects[1:])}
    )


def _with_discrepancy_description(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    discrepancy = request.discrepancies[0].model_copy(update={"description": _PROHIBITED_TEXT})
    return request.model_copy(update={"discrepancies": (discrepancy, *request.discrepancies[1:])})


def _with_rollback_reason(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    policy = request.rollback_policy.model_copy(update={"suspension_reason": _PROHIBITED_TEXT})
    return request.model_copy(update={"rollback_policy": policy})


def _with_support_rationale(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    decision = request.support_decision.model_copy(update={"rationale": _PROHIBITED_TEXT})
    return request.model_copy(update={"support_decision": decision})


def _with_evidence_claim(
    request: MonitorProteotypeTranslationHealthRequest,
) -> MonitorProteotypeTranslationHealthRequest:
    telemetry = request.telemetry[0]
    evidence = telemetry.evidence[0].model_copy(update={"claim": _PROHIBITED_TEXT})
    updated = telemetry.model_copy(update={"evidence": (evidence, *telemetry.evidence[1:])})
    return request.model_copy(update={"telemetry": (updated, *request.telemetry[1:])})


@pytest.mark.parametrize(
    "update",
    [
        _with_telemetry_metric,
        _with_support_dimension,
        _with_workflow_description,
        _with_discrepancy_description,
        _with_rollback_reason,
        _with_support_rationale,
        _with_evidence_claim,
    ],
    ids=(
        "telemetry-metric",
        "support-dimension",
        "workflow-description",
        "discrepancy-description",
        "rollback-reason",
        "support-rationale",
        "evidence-claim",
    ),
)
def test_prohibited_claim_surfaces_abstain_without_report(update: _EngineUpdate) -> None:
    result = m1908.M1908TranslationMonitoringEngine().infer(update(_request()))
    assert result.status is MonitorStatus.ABSTAINED
    assert result.health_report is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason is not None
    assert any(
        finding.code is TranslationFindingCode.PROHIBITED_CLAIM_BOUNDARY
        for finding in result.findings
    )


def test_prohibited_claim_abstention_replays_exactly() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_with_evidence_claim(_request()))
    assert engine.verify(result) == result
