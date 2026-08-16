"""Adversarial closure for the provisional M20-08 monitoring contract."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_08 import (
    M2008_DOSSIER_SHA256,
    M2008_DOSSIER_SLICE,
    M2008_M2007_INPUT_MEDIA_TYPE,
    DriftAssessment,
    HealthSignal,
    HealthSignalKind,
    HealthSignalStatus,
    MonitorDiagnostic,
    MonitorDiagnosticStatus,
    MonitorProteinSubtypeTranslationHealthRequest,
    RollbackPlan,
    TranslationHealthReport,
    TranslationMonitoringConfiguration,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m2008.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m2008:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Caller-declared M20-08 monitoring evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.m2008.{role}",
        state=UpstreamDecisionState.ACCEPTED,
        policy_version="1.0.0",
        evidence=artifact,
    )


def _context() -> ExecutionContext:
    artifacts = {
        role: _artifact(role)
        for role in (
            "configuration",
            "identity",
            "provenance",
            "quality",
            "support",
            "intended_use",
            "consent",
        )
    }
    return ExecutionContext(
        request_id="request.m2008.synthetic",
        actor_id="actor.m2008.synthetic",
        occurred_at=datetime(2026, 8, 16, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m2008.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m2008.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.m2008.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _signal(name: str = "usage") -> HealthSignal:
    artifact = _artifact(f"signal-{name}")
    return HealthSignal(
        signal_id=f"signal.m2008.{name}",
        kind=HealthSignalKind.USAGE_TELEMETRY,
        metric="usage_rate",
        observed_value=0.5,
        lower_bound=0.0,
        upper_bound=1.0,
        status=HealthSignalStatus.WITHIN_ENVELOPE,
        source_artifacts=(artifact,),
        evidence=(_evidence(artifact),),
    )


def _configuration() -> TranslationMonitoringConfiguration:
    return TranslationMonitoringConfiguration(
        configuration_id="configuration.m2008.synthetic",
        version="1.0.0",
        reference_artifact=_artifact("reference"),
        monitoring_window="30 days",
        critical_threshold="critical drift requires rollback review",
        evidence=(_evidence(_artifact("configuration")),),
    )


def _report() -> TranslationHealthReport:
    signal = _signal()
    return TranslationHealthReport(
        report_id="report.m2008.synthetic",
        version="1.0.0",
        signals=(signal,),
        assessments=(
            DriftAssessment(
                assessment_id="assessment.m2008.synthetic",
                signal_ids=(signal.signal_id,),
                summary="Usage remains within the declared envelope.",
                status=HealthSignalStatus.WITHIN_ENVELOPE,
                evidence=(_evidence(_artifact("assessment")),),
            ),
        ),
        rollback_plan=RollbackPlan(
            plan_id="plan.m2008.synthetic",
            trigger_conditions=("critical drift",),
            target_version="1.0.0",
            action="continue while within envelope",
            recovery_steps=("review evidence",),
            evidence=(_evidence(_artifact("rollback")),),
        ),
        configuration=_configuration(),
        evidence=(_evidence(_artifact("report")),),
    )


def _request() -> MonitorProteinSubtypeTranslationHealthRequest:
    upstream = _artifact("upstream", M2008_M2007_INPUT_MEDIA_TYPE)
    return MonitorProteinSubtypeTranslationHealthRequest(
        request_id="request.m2008.synthetic",
        context=_context(),
        upstream_result=upstream,
        configuration=_configuration(),
        source_artifacts=(upstream, _artifact("telemetry")),
    )


def test_authority_and_upstream_boundary_are_explicit() -> None:
    assert (
        M2008_DOSSIER_SHA256
        == "sha256:" + "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert M2008_DOSSIER_SLICE.endswith(":7184-7224")
    assert _request().upstream_result.media_type == M2008_M2007_INPUT_MEDIA_TYPE


def test_signal_bounds_and_source_references_are_closed() -> None:
    with pytest.raises(ValidationError, match="within its bounds"):
        HealthSignal.model_validate(_signal().model_dump() | {"observed_value": 2.0})
    with pytest.raises(ValidationError, match="both bounds"):
        HealthSignal.model_validate(
            _signal().model_dump() | {"lower_bound": None, "upper_bound": None}
        )
    signal = _signal()
    with pytest.raises(ValidationError, match="source artifact ids"):
        HealthSignal.model_validate(
            signal.model_dump() | {"source_artifacts": signal.source_artifacts * 2}
        )


def test_assessment_report_and_rollback_collections_are_closed() -> None:
    signal = _signal()
    assessment = DriftAssessment.model_construct(
        assessment_id="assessment.m2008.duplicate",
        signal_ids=(signal.signal_id, signal.signal_id),
        summary="Duplicate signal reference.",
        status=HealthSignalStatus.DRIFTING,
    )
    with pytest.raises(ValidationError, match="signal ids"):
        TypeAdapter(DriftAssessment).validate_python(assessment, strict=True)
    report = _report()
    with pytest.raises(ValidationError, match="unknown signal"):
        TranslationHealthReport.model_validate(
            report.model_dump()
            | {
                "assessments": (
                    report.assessments[0].model_copy(update={"signal_ids": ("signal.unknown",)}),
                )
            }
        )
    plan = RollbackPlan.model_construct(
        plan_id="plan.m2008.duplicate",
        trigger_conditions=("critical drift", "critical drift"),
        target_version="1.0.0",
        action="rollback",
        recovery_steps=("review",),
    )
    with pytest.raises(ValidationError, match="trigger conditions"):
        TypeAdapter(RollbackPlan).validate_python(plan, strict=True)


def test_configuration_and_request_sources_require_unique_evidence() -> None:
    configuration = _configuration()
    with pytest.raises(ValidationError, match="configuration evidence"):
        TranslationMonitoringConfiguration.model_validate(
            configuration.model_dump() | {"evidence": configuration.evidence * 2}
        )
    request = _request()
    with pytest.raises(ValidationError, match="source artifact references"):
        TypeAdapter(MonitorProteinSubtypeTranslationHealthRequest).validate_python(
            request.model_copy(update={"source_artifacts": (request.source_artifacts[0],) * 2}),
            strict=True,
        )
    with pytest.raises(ValidationError, match="M20-07"):
        TypeAdapter(MonitorProteinSubtypeTranslationHealthRequest).validate_python(
            request.model_copy(update={"upstream_result": _artifact("wrong")}), strict=True
        )


def test_report_fixture_contains_telemetry_drift_rollback_and_configuration() -> None:
    report = _report()
    assert report.signals[0].kind is HealthSignalKind.USAGE_TELEMETRY
    assert report.assessments[0].status is HealthSignalStatus.WITHIN_ENVELOPE
    assert report.rollback_plan.recovery_steps
    assert report.configuration.locked is True
    diagnostic = MonitorDiagnostic(
        diagnostic_id="diagnostic.m2008.synthetic",
        status=MonitorDiagnosticStatus.PASS,
        message="Monitoring report is evaluable.",
    )
    assert diagnostic.status is MonitorDiagnosticStatus.PASS
