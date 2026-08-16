"""Runtime, authorization, and replay tests for provisional M26-05."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_05 import (
    M2605_M2604_INPUT_MEDIA_TYPE,
    AlertSeverity,
    AlertState,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    TelemetryMetricKind,
    TelemetrySample,
    TelemetryStatus,
    TelemetryUnit,
)
from glio_proteogen.contracts.m26_05.canonical import canonical_request_digest
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
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    M2605AuthorizationError,
    M2605ObservabilityService,
    M2605ReplayError,
)

_WHEN = datetime(2026, 1, 1, tzinfo=UTC)


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2605.runtime.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(f"evidence-{label}"),
        role="evidence",
        claim="Synthetic retained M26-05 telemetry evidence.",
    )


def _context() -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2605.runtime.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id="m2605.runtime.request",
        actor_id="m2605.runtime.actor",
        occurred_at=_WHEN,
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2605.runtime.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2605.runtime.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _sample(
    metric: TelemetryMetricKind,
    value: float,
    unit: TelemetryUnit,
    index: int,
) -> TelemetrySample:
    return TelemetrySample(
        sample_id=f"m2605.runtime.sample.{metric.value}",
        metric=metric,
        value=value,
        unit=unit,
        observed_at=_WHEN + timedelta(seconds=index),
        source="m2605.runtime.synthetic",
        evidence=(_evidence(metric.value),),
    )


def _request(
    *, include_drift: bool = False, include_errors: bool = False
) -> EmitProteomicsTelemetryRequest:
    upstream = _artifact("m2604", M2605_M2604_INPUT_MEDIA_TYPE)
    samples = (
        _sample(TelemetryMetricKind.INPUT_QUALITY, 0.9, TelemetryUnit.SCORE, 0),
        _sample(TelemetryMetricKind.MODEL_BEHAVIOR, 0.8, TelemetryUnit.SCORE, 1),
        _sample(TelemetryMetricKind.UNCERTAINTY, 0.1, TelemetryUnit.RATIO, 2),
        _sample(TelemetryMetricKind.ABSTENTION, 0.02, TelemetryUnit.RATIO, 3),
        _sample(
            TelemetryMetricKind.DRIFT,
            0.6 if include_drift else 0.1,
            TelemetryUnit.SCORE,
            4,
        ),
        _sample(TelemetryMetricKind.LATENCY, 12.0, TelemetryUnit.MILLISECONDS, 5),
        _sample(
            TelemetryMetricKind.ERRORS,
            0.08 if include_errors else 0.01,
            TelemetryUnit.RATIO,
            6,
        ),
        _sample(TelemetryMetricKind.RESOURCES, 1024.0, TelemetryUnit.BYTES, 7),
    )
    requested = tuple(item.metric for item in samples)
    evidence = _evidence("dashboard")
    dashboards = (
        DashboardDefinition(
            dashboard_id="m2605.runtime.dashboard.operations",
            title="Operations telemetry",
            metrics=(TelemetryMetricKind.INPUT_QUALITY, TelemetryMetricKind.MODEL_BEHAVIOR),
            owner="m2605-review",
            refresh_seconds=60,
            evidence=(evidence,),
        ),
        DashboardDefinition(
            dashboard_id="m2605.runtime.dashboard.risk",
            title="Risk telemetry",
            metrics=(TelemetryMetricKind.DRIFT, TelemetryMetricKind.ERRORS),
            owner="m2605-review",
            refresh_seconds=120,
            evidence=(evidence,),
        ),
    )
    return EmitProteomicsTelemetryRequest(
        request_id="m2605.runtime.request.telemetry",
        context=_context(),
        upstream_result=upstream,
        requested_metrics=requested,
        samples=samples,
        dashboard_definitions=dashboards,
        source_artifacts=(upstream,),
    )


def test_emit_is_deterministic_and_replay_closed() -> None:
    service = M2605ObservabilityService()
    request = _request()
    first = service.execute(request)
    second = service.execute(request)

    assert first.status is TelemetryStatus.EMITTED
    assert first.result_digest == second.result_digest
    assert first.request_digest == canonical_request_digest(request)
    assert first.telemetry_stream is not None
    assert service.verify(first).result_digest == first.result_digest


def test_threshold_findings_open_alert_and_require_human_review() -> None:
    result = M2605ObservabilityService().execute(_request(include_drift=True, include_errors=True))

    assert result.status is TelemetryStatus.EMITTED
    assert result.alert is not None
    assert result.alert.state is AlertState.OPEN
    assert result.alert.severity is AlertSeverity.ERROR
    assert result.human_review_required is True
    assert {finding.code.value for finding in result.findings} >= {
        "drift_detected",
        "error_budget_exceeded",
    }


def test_missing_requested_metric_abstains_without_negative_inference() -> None:
    request = _request()
    missing = request.model_copy(
        update={
            "requested_metrics": (*request.requested_metrics, TelemetryMetricKind.REVIEWER_ACTIONS),
        }
    )
    result = M2605ObservabilityService().execute(missing)

    assert result.status is TelemetryStatus.ABSTAINED
    assert result.telemetry_stream is None
    assert result.safe_failure_report is not None
    assert result.human_review_required is True
    assert result.support_decision.status.value == "review_required"
    assert result.emits_parent is False


def test_preflight_rejects_one_failed_control_before_execution() -> None:
    request = _request()
    failed_quality = request.context.references.quality.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    failed_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(update={"quality": failed_quality})
        }
    )
    denied = request.model_copy(update={"context": failed_context})

    with pytest.raises(M2605AuthorizationError):
        M2605ObservabilityService().execute(denied)


def test_replay_rejects_tampered_result_digest() -> None:
    service = M2605ObservabilityService()
    result = service.execute(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "a" * 64})

    with pytest.raises(M2605ReplayError):
        service.verify(tampered)


def test_strict_service_does_not_coerce_unvalidated_mapping() -> None:
    request = _request()
    candidate = request.model_dump(mode="python")
    candidate["unexpected"] = True
    with pytest.raises(ValidationError):
        M2605ObservabilityService.validate_request(candidate)
