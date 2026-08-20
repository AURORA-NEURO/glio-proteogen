"""Deep adversarial closure for M20-08 result and report invariants."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_08 import (
    DriftAssessment,
    HealthSignal,
    MonitorDiagnostic,
    MonitorDiagnosticStatus,
    MonitorFindingCode,
    ProteinSubtypeTranslationHealthResult,
    RollbackDecision,
    RollbackPlan,
    TranslationHealthReport,
    TranslationHealthStatus,
    TranslationMonitoringConfiguration,
)
from glio_proteogen.modules.c20_biomarker_panel.m20_08_translation_monitoring_rollback import (
    M2008TranslationMonitoringEngine,
)
from tests.contract.test_m20_08_hardening import _artifact, _report, _request, _signal


def test_report_cannot_drop_or_repeat_a_signal_assessment() -> None:
    report = _report()
    assessment = report.assessments[0]
    extra = _signal().model_copy(update={"signal_id": "signal.m2008.extra"})
    with pytest.raises(ValidationError, match="each report signal"):
        TranslationHealthReport.model_validate(
            report.model_copy(update={"signals": (report.signals[0], extra)})
        )
    with pytest.raises(ValidationError, match="assessment ids"):
        TranslationHealthReport.model_validate(
            report.model_copy(update={"assessments": (assessment, assessment)})
        )


def test_result_cannot_repeat_findings_or_diagnostics() -> None:
    result = M2008TranslationMonitoringEngine().infer(_request())
    with pytest.raises(ValidationError, match="monitor findings"):
        TypeAdapter(ProteinSubtypeTranslationHealthResult).validate_python(
            result.model_copy(update={"findings": result.findings * 2}), strict=True
        )
    diagnostic = result.diagnostics[0]
    with pytest.raises(ValidationError, match="diagnostic ids"):
        TypeAdapter(ProteinSubtypeTranslationHealthResult).validate_python(
            result.model_copy(update={"diagnostics": (diagnostic, diagnostic)}), strict=True
        )


def test_constructed_invalid_assessment_is_rejected_by_strict_adapter() -> None:
    report = _report()
    signal = report.signals[0]
    forged = DriftAssessment.model_construct(
        assessment_id="assessment.forged",
        signal_ids=(signal.signal_id, "signal.forged"),
        summary="Forged closure.",
        status=signal.status,
    )
    with pytest.raises(ValidationError, match="unknown signal"):
        TranslationHealthReport.model_validate(report.model_copy(update={"assessments": (forged,)}))


def test_diagnostic_shape_is_strict_and_finding_codes_are_typed() -> None:
    diagnostic = MonitorDiagnostic(
        diagnostic_id="diagnostic.m2008.adversarial",
        status=MonitorDiagnosticStatus.FAIL,
        message="A critical drift requires review.",
    )
    assert diagnostic.status is MonitorDiagnosticStatus.FAIL
    assert MonitorFindingCode.ROLLBACK_REQUIRED.value == "rollback_required"


def test_signal_configuration_and_rollback_bounds_are_closed() -> None:
    signal = _signal()
    with pytest.raises(ValidationError, match="bounds must be ordered"):
        HealthSignal.model_validate(
            signal.model_copy(update={"lower_bound": 2.0, "upper_bound": 1.0})
        )
    config = _request().configuration
    with pytest.raises(ValidationError, match="evidence must be unique"):
        TranslationMonitoringConfiguration.model_validate(
            config.model_copy(update={"evidence": config.evidence * 2})
        )
    plan = _report().rollback_plan
    with pytest.raises(ValidationError, match="recovery steps"):
        RollbackPlan.model_validate(
            plan.model_copy(update={"recovery_steps": plan.recovery_steps * 2})
        )


def test_request_requires_retained_upstream_and_unique_sources() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="exact M20-07 result"):
        type(request).model_validate(
            request.model_copy(update={"source_artifacts": (_artifact("other"),)})
        )
    with pytest.raises(ValidationError, match="source artifact references"):
        type(request).model_validate(
            request.model_copy(update={"source_artifacts": (request.source_artifacts[0],) * 2})
        )


def test_result_closure_rejects_digest_identifier_and_state_tampering() -> None:
    result = M2008TranslationMonitoringEngine().infer(_request())
    adapter = TypeAdapter(ProteinSubtypeTranslationHealthResult)
    with pytest.raises(ValidationError, match="request digest"):
        adapter.validate_python(
            result.model_copy(update={"request_digest": "sha256:" + "f" * 64}), strict=True
        )
    with pytest.raises(ValidationError, match="identifier"):
        adapter.validate_python(
            result.model_copy(update={"result_id": "result.forged"}), strict=True
        )
    with pytest.raises(ValidationError, match="result digest"):
        adapter.validate_python(
            result.model_copy(update={"result_digest": "sha256:" + "f" * 64}), strict=True
        )
    with pytest.raises(ValidationError, match="healthy result"):
        adapter.validate_python(
            result.model_copy(update={"rollback_decision": RollbackDecision.SUSPEND}), strict=True
        )
    degraded = result.model_copy(update={"health_status": TranslationHealthStatus.DEGRADED})
    with pytest.raises(ValidationError, match="degraded result"):
        adapter.validate_python(degraded, strict=True)
    abstained = result.model_copy(update={"health_status": TranslationHealthStatus.ABSTAINED})
    with pytest.raises(ValidationError, match="abstained result"):
        adapter.validate_python(abstained, strict=True)


def test_result_evidence_and_report_evidence_must_remain_unique() -> None:
    result = M2008TranslationMonitoringEngine().infer(_request())
    adapter = TypeAdapter(ProteinSubtypeTranslationHealthResult)
    with pytest.raises(ValidationError, match="result evidence"):
        adapter.validate_python(
            result.model_copy(update={"evidence": result.evidence * 2}), strict=True
        )
    report = _report()
    with pytest.raises(ValidationError, match="report evidence"):
        TranslationHealthReport.model_validate(
            report.model_copy(update={"evidence": report.evidence * 2})
        )
