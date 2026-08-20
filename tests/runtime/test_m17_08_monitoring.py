"""Runtime and adversarial coverage for provisional M17-08 monitoring."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glio_proteogen.contracts.m17_08 import (
    DiscrepancyObservation,
    MonitorStatus,
    MonitorVariantPeptideTranslationHealthRequest,
    ObservationStatus,
    RollbackDecision,
    RollbackPolicy,
    SupportDriftObservation,
    TelemetryObservation,
    TranslationFindingCode,
    TranslationHealthState,
    WorkflowEffectObservation,
)
from glio_proteogen.contracts.m17_08.canonical import result_payload_digest
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
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_08_translation_monitoring as m1708,
)


def _artifact(name: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest(f"m1708:{name}:{media_type}"),
        media_type=media_type,
    )


def _evidence(artifact: ArtifactReference) -> EvidenceReference:
    return EvidenceReference(
        reference=artifact,
        role="evidence",
        claim="Synthetic caller-declared M17-08 health evidence.",
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
        request_id="request.synthetic.m1708",
        actor_id="actor.synthetic.m1708",
        occurred_at=datetime(2026, 8, 15, 20, 0, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=_decision("configuration", artifacts["configuration"]),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("m1708.identity"),
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
    threshold: int = 1,
    upstream_media_type: str = "application/vnd.glio-proteogen.m17-07+json",
) -> MonitorVariantPeptideTranslationHealthRequest:
    evidence = (_evidence(_artifact("health")),)
    return MonitorVariantPeptideTranslationHealthRequest(
        request_id="request.synthetic.m1708",
        context=_context(),
        upstream_result=_artifact("upstream", upstream_media_type),
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
            rollback_artifact=_artifact("rollback"),
            suspension_reason="synthetic critical translation drift",
            evidence=evidence,
        ),
        source_artifacts=(_artifact("source"),),
    )


def test_healthy_monitoring_emits_report_and_replays() -> None:
    result = m1708.M1708Engine().adapt(_request())

    assert result.status is MonitorStatus.MONITORED
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.HEALTHY
    assert result.health_report.rollback_decision is RollbackDecision.NONE
    assert result.parent_target == "variant peptide"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert m1708.M1708Engine().replay(result) == result


def test_critical_drift_triggers_rollback() -> None:
    result = m1708.M1708Engine().adapt(
        _request(telemetry_status=ObservationStatus.FAIL, threshold=1)
    )

    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.ROLLBACK_REQUIRED
    assert result.health_report.rollback_decision is RollbackDecision.ROLLBACK
    assert any(item.code is TranslationFindingCode.ROLLBACK_REQUIRED for item in result.findings)
    assert result.human_review_required is True


def test_unresolved_discrepancy_suspends_translation() -> None:
    result = m1708.M1708Engine().adapt(_request(discrepancy_resolved=False))

    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.SUSPENDED
    assert result.health_report.rollback_decision is RollbackDecision.SUSPEND
    assert any(
        item.code is TranslationFindingCode.DISCREPANCY_UNRESOLVED for item in result.findings
    )


def test_not_evaluable_observation_abstains() -> None:
    result = m1708.M1708Engine().adapt(_request(telemetry_status=ObservationStatus.NOT_EVALUABLE))

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

    with pytest.raises(m1708.M1708AuthorizationError, match="consent"):
        m1708.M1708Engine().adapt(request)


def test_upstream_media_type_is_strict() -> None:
    with pytest.raises(ValueError, match="M17-07"):
        m1708.M1708Engine().adapt(_request(upstream_media_type="application/json"))


def test_tampered_result_digest_is_rejected() -> None:
    result = m1708.M1708Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})

    with pytest.raises(m1708.M1708ReplayError, match="payload digest"):
        m1708.M1708Engine().replay(tampered)


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    result = m1708.M1708Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    with pytest.raises(m1708.M1708ReplayError, match="semantic replay"):
        m1708.M1708Engine().replay(tampered)
