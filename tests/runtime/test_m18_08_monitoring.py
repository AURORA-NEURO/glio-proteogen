"""Runtime and adversarial coverage for provisional M18-08 monitoring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m18_08 import (
    DiscrepancyObservation,
    MonitorBiomarkerPanelTranslationHealthRequest,
    MonitorStatus,
    ObservationStatus,
    RollbackDecision,
    RollbackPolicy,
    SupportDriftObservation,
    TelemetryObservation,
    TranslationFindingCode,
    TranslationHealthState,
    WorkflowEffectObservation,
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
    SupportDecision,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c18_spatial_proteomics import (
    m18_08_translation_monitoring_service as m1808,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1808:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared M18-08 health evidence.",
    )


def _decision(role: str, artifact: ArtifactReference) -> UpstreamDecisionReference:
    return UpstreamDecisionReference(
        decision_id=f"decision.{role}",
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
        request_id="request.synthetic.m1808",
        actor_id="actor.synthetic.m1808",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1808.identity"),
                evidence=artifacts["identity"],
            ),
            provenance=_decision("provenance", artifacts["provenance"]),
            consent=ConsentReference(
                decision_id="decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=artifacts["consent"],
            ),
            quality=_decision("quality", artifacts["quality"]),
            support=_decision("support", artifacts["support"]),
            intended_use=_decision("intended_use", artifacts["intended_use"]),
        ),
    )


def _request(  # noqa: PLR0913
    *,
    telemetry_status: ObservationStatus = ObservationStatus.PASS,
    support_status: ObservationStatus = ObservationStatus.PASS,
    workflow_status: ObservationStatus = ObservationStatus.PASS,
    discrepancy_status: ObservationStatus = ObservationStatus.PASS,
    discrepancy_resolved: bool = True,
    threshold: int = 2,
    upstream_media_type: str = "application/vnd.glio-proteogen.m18-07+json",
) -> MonitorBiomarkerPanelTranslationHealthRequest:
    evidence = (_evidence(_artifact("health")),)
    upstream = _artifact("upstream", upstream_media_type)
    rollback = _artifact("rollback")
    source = _artifact("source")
    return MonitorBiomarkerPanelTranslationHealthRequest(
        request_id="request.synthetic.m1808",
        context=_context(),
        upstream_result=upstream,
        telemetry=(
            TelemetryObservation(
                observation_id="observation.telemetry",
                metric_name="translation_latency",
                observed_value=1.0,
                baseline_value=1.0,
                allowed_delta=0.2,
                status=telemetry_status,
                evidence=evidence,
            ),
        ),
        support_drift=(
            SupportDriftObservation(
                observation_id="observation.support",
                support_dimension="assay_support",
                baseline_status="supported",
                current_status="supported",
                status=support_status,
                evidence=evidence,
            ),
        ),
        workflow_effects=(
            WorkflowEffectObservation(
                observation_id="observation.workflow",
                workflow="translation_export",
                effect_description="synthetic effect",
                status=workflow_status,
                evidence=evidence,
            ),
        ),
        discrepancies=(
            DiscrepancyObservation(
                discrepancy_id="discrepancy.synthetic",
                description="synthetic discrepancy",
                resolved=discrepancy_resolved,
                status=discrepancy_status,
                evidence=evidence,
            ),
        ),
        rollback_policy=RollbackPolicy(
            policy_id="rollback-policy.synthetic",
            version="1.0.0",
            critical_failure_threshold=threshold,
            rollback_target_version="0.9.0",
            rollback_artifact=rollback,
            suspension_reason="synthetic critical translation drift",
            evidence=evidence,
        ),
        source_artifacts=(source, upstream, rollback, _artifact("health")),
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="synthetic_supported",
            rationale="Synthetic fixture declares all required monitoring controls supported.",
        ),
    )


def test_healthy_monitoring_emits_report_and_replays() -> None:
    result = m1808.M1808TranslationMonitoringEngine().adapt(_request())

    assert result.status is MonitorStatus.MONITORED
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.HEALTHY
    assert result.health_report.rollback_decision is RollbackDecision.NONE
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert m1808.M1808TranslationMonitoringEngine().replay(result) == result


def test_critical_drift_triggers_rollback() -> None:
    result = m1808.M1808TranslationMonitoringEngine().adapt(
        _request(telemetry_status=ObservationStatus.FAIL, threshold=1)
    )

    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.ROLLBACK_REQUIRED
    assert result.health_report.rollback_decision is RollbackDecision.ROLLBACK
    assert any(item.code is TranslationFindingCode.ROLLBACK_REQUIRED for item in result.findings)
    assert result.human_review_required is True


def test_unresolved_discrepancy_suspends_translation() -> None:
    result = m1808.M1808TranslationMonitoringEngine().adapt(_request(discrepancy_resolved=False))

    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.SUSPENDED
    assert result.health_report.rollback_decision is RollbackDecision.SUSPEND
    assert any(
        item.code is TranslationFindingCode.DISCREPANCY_UNRESOLVED for item in result.findings
    )


def test_not_evaluable_observation_abstains() -> None:
    result = m1808.M1808TranslationMonitoringEngine().adapt(
        _request(telemetry_status=ObservationStatus.NOT_EVALUABLE)
    )

    assert result.status is MonitorStatus.ABSTAINED
    assert result.health_report is None
    assert result.abstention_reason is not None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_control_denial_precedes_monitoring() -> None:
    request = _request().model_copy(
        update={
            "context": _context().model_copy(
                update={
                    "references": _context().references.model_copy(
                        update={
                            "consent": _context().references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )

    with pytest.raises(m1808.M1808AuthorizationError, match="consent"):
        m1808.M1808TranslationMonitoringEngine().adapt(request)


def test_upstream_media_type_is_strict() -> None:
    with pytest.raises(ValueError, match="M18-07"):
        m1808.M1808TranslationMonitoringEngine().adapt(
            _request(upstream_media_type="application/json")
        )


def test_tampered_result_digest_is_rejected() -> None:
    result = m1808.M1808TranslationMonitoringEngine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})

    with pytest.raises(m1808.M1808ReplayVerificationError, match="payload digest"):
        m1808.M1808TranslationMonitoringEngine().replay(tampered)
