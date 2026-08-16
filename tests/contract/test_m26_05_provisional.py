"""Focused schema and critical-signal smoke for provisional M26-05."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from glio_proteogen.contracts.m26_05 import (
    M2605_M2604_INPUT_MEDIA_TYPE,
    M2605_OUTPUT_MEDIA_TYPE,
    M2605_PROVISIONAL_ABI,
    AlertRecord,
    AlertSeverity,
    AlertState,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    TelemetryMetricKind,
    TelemetrySample,
    TelemetryStatus,
    TelemetryStream,
    TelemetryUnit,
    contract_json_schemas,
)
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

_SCHEMA_COUNT = 8
_METRIC_COUNT = 9


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2605.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type=media_type,
    )


def _evidence(label: str) -> EvidenceReference:
    return EvidenceReference(
        reference=_artifact(f"evidence-{label}"),
        role="evidence",
        claim="Caller-declared telemetry evidence.",
    )


def _context() -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2605.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id="m2605.request.telemetry",
        actor_id="m2605.actor.telemetry",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2605.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=_artifact("identity").digest,
                evidence=_artifact("identity-evidence"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2605.decision.consent",
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
    metric: TelemetryMetricKind = TelemetryMetricKind.INPUT_QUALITY,
    value: float = 0.9,
    unit: TelemetryUnit = TelemetryUnit.SCORE,
    label: str = "quality",
    observed_at: datetime | None = None,
) -> TelemetrySample:
    return TelemetrySample(
        sample_id=f"m2605.sample.{label}",
        metric=metric,
        value=value,
        unit=unit,
        observed_at=observed_at or datetime(2026, 1, 1, tzinfo=UTC),
        source="m2605.synthetic",
        evidence=(_evidence(label),),
    )


def test_provisional_schemas_require_critical_telemetry_controls() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "stream",
        "sample",
        "dashboard",
        "alert",
        "reviewer-action",
        "safe-failure",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["inputQualityRequired"] is True
        assert metadata["modelBehaviorRequired"] is True
        assert metadata["uncertaintyRequired"] is True
        assert metadata["abstentionRequired"] is True
        assert metadata["driftRequired"] is True
        assert metadata["telemetryRetentionRequired"] is True
        assert metadata["alertStateRequired"] is True
        assert metadata["unsupportedToNegative"] is False
        assert metadata["parentTarget"] == "protein subtype"
        assert metadata["upstreamInputMediaType"] == M2605_M2604_INPUT_MEDIA_TYPE
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2605_OUTPUT_MEDIA_TYPE
    assert M2605_PROVISIONAL_ABI is True


def test_telemetry_metrics_and_statuses_are_explicit() -> None:
    assert len(tuple(TelemetryMetricKind)) == _METRIC_COUNT
    assert TelemetryMetricKind.REVIEWER_ACTIONS.value == "reviewer_actions"
    assert TelemetryStatus.ABSTAINED.value == "abstained"
    assert TelemetryUnit.MILLISECONDS.value == "milliseconds"


def test_samples_reject_nonfinite_values_and_incompatible_units() -> None:
    with pytest.raises(ValidationError):
        _sample(value=float("nan"))
    with pytest.raises(ValidationError, match="incompatible"):
        _sample(metric=TelemetryMetricKind.LATENCY, unit=TelemetryUnit.SCORE)


def test_alert_temporal_state_is_explicit() -> None:
    evidence = (_evidence("alert"),)
    with pytest.raises(ValidationError, match="triggered_at"):
        AlertRecord(
            alert_id="m2605.alert.open",
            state=AlertState.OPEN,
            severity=AlertSeverity.WARNING,
            metric=TelemetryMetricKind.DRIFT,
            message="Drift requires review.",
            evidence=evidence,
        )
    with pytest.raises(ValidationError, match="follow"):
        AlertRecord(
            alert_id="m2605.alert.closed",
            state=AlertState.CLEAR,
            severity=AlertSeverity.INFO,
            metric=TelemetryMetricKind.DRIFT,
            message="Drift cleared.",
            triggered_at=datetime(2026, 1, 2, tzinfo=UTC),
            resolved_at=datetime(2026, 1, 1, tzinfo=UTC),
            evidence=evidence,
        )


def test_stream_requires_unique_and_chronological_records() -> None:
    evidence = (_evidence("stream"),)
    with pytest.raises(ValidationError, match="sample ids"):
        TelemetryStream(
            stream_id="m2605.stream.duplicate",
            version="1.0.0",
            samples=(_sample(label="same"), _sample(label="same")),
            evidence=evidence,
        )
    with pytest.raises(ValidationError, match="ordered"):
        TelemetryStream(
            stream_id="m2605.stream.unsorted",
            version="1.0.0",
            samples=(
                _sample(label="late", observed_at=datetime(2026, 1, 2, tzinfo=UTC)),
                _sample(label="early", observed_at=datetime(2026, 1, 1, tzinfo=UTC)),
            ),
            evidence=evidence,
        )


def test_request_binds_upstream_and_dashboard_metric_scope() -> None:
    upstream = _artifact("m2604", M2605_M2604_INPUT_MEDIA_TYPE)
    dashboard = DashboardDefinition(
        dashboard_id="m2605.dashboard.quality",
        title="Quality telemetry",
        metrics=(TelemetryMetricKind.INPUT_QUALITY,),
        owner="quality-review",
        refresh_seconds=60,
        evidence=(_evidence("dashboard"),),
    )
    request = EmitProteomicsTelemetryRequest(
        request_id="m2605.request.telemetry",
        context=_context(),
        upstream_result=upstream,
        requested_metrics=(TelemetryMetricKind.INPUT_QUALITY,),
        samples=(_sample(),),
        dashboard_definitions=(dashboard,),
        source_artifacts=(upstream,),
    )
    assert request.upstream_result.media_type == M2605_M2604_INPUT_MEDIA_TYPE
    with pytest.raises(ValidationError, match="requested telemetry metrics"):
        EmitProteomicsTelemetryRequest(
            request_id=request.request_id,
            context=request.context,
            upstream_result=upstream,
            requested_metrics=(TelemetryMetricKind.INPUT_QUALITY,),
            samples=(_sample(),),
            dashboard_definitions=(
                dashboard.model_copy(update={"metrics": (TelemetryMetricKind.DRIFT,)}),
            ),
            source_artifacts=(upstream,),
        )
