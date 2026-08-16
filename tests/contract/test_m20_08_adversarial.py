"""Deep adversarial closure for M20-08 result and report invariants."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_08 import (
    DriftAssessment,
    MonitorDiagnostic,
    MonitorDiagnosticStatus,
    MonitorFindingCode,
    ProteinSubtypeTranslationHealthResult,
    TranslationHealthReport,
)
from glio_proteogen.modules.c20_biomarker_panel.m20_08_translation_monitoring_rollback import (
    M2008TranslationMonitoringEngine,
)
from tests.contract.test_m20_08_hardening import _report, _request, _signal


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
