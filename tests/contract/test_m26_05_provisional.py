"""Focused schema and critical-signal smoke for provisional M26-05."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from evals.m26_05.fixture import make_request
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
    ReviewerActionKind,
    ReviewerActionRecord,
    TelemetryFinding,
    TelemetryFindingCode,
    TelemetryMetricKind,
    TelemetrySample,
    TelemetryStatus,
    TelemetryStream,
    TelemetryUnit,
    contract_json_schemas,
)
from glio_proteogen.contracts.m26_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
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
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    M2605ObservabilityEngine,
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


def test_contract_closes_sample_dashboard_alert_and_stream_edges() -> None:
    sample = _sample()
    nonfinite = sample.model_construct(**{**sample.__dict__, "value": float("nan")})
    with pytest.raises(ValueError, match="finite"):
        nonfinite.value_and_unit_are_closed()

    with pytest.raises(ValidationError, match="dashboard metrics"):
        DashboardDefinition(
            dashboard_id="m2605.dashboard.duplicate-metrics",
            title="Duplicate metrics",
            metrics=(TelemetryMetricKind.INPUT_QUALITY, TelemetryMetricKind.INPUT_QUALITY),
            owner="review",
            refresh_seconds=60,
        )

    evidence = (_evidence("alert-closure"),)
    with pytest.raises(ValidationError, match="resolved alerts"):
        AlertRecord(
            alert_id="m2605.alert.invalid-resolved",
            state=AlertState.OPEN,
            severity=AlertSeverity.WARNING,
            metric=TelemetryMetricKind.DRIFT,
            message="Open alert cannot be resolved in this state.",
            triggered_at=datetime(2026, 1, 1, tzinfo=UTC),
            resolved_at=datetime(2026, 1, 2, tzinfo=UTC),
            evidence=evidence,
        )
    with pytest.raises(ValidationError, match="critical severity"):
        AlertRecord(
            alert_id="m2605.alert.invalid-critical",
            state=AlertState.NOT_EVALUABLE,
            severity=AlertSeverity.CRITICAL,
            metric=TelemetryMetricKind.DRIFT,
            message="Critical not-evaluable alert.",
            evidence=evidence,
        )
    AlertRecord(
        alert_id="m2605.alert.valid-not-evaluable-resolution",
        state=AlertState.NOT_EVALUABLE,
        severity=AlertSeverity.WARNING,
        metric=TelemetryMetricKind.DRIFT,
        message="Not-evaluable alert with a valid resolution path.",
        triggered_at=datetime(2026, 1, 1, tzinfo=UTC),
        resolved_at=datetime(2026, 1, 2, tzinfo=UTC),
        evidence=evidence,
    )

    action = ReviewerActionRecord(
        action_id="m2605.action.duplicate",
        kind=ReviewerActionKind.ACKNOWLEDGED,
        reviewer="reviewer",
        target_id="m2605.alert.target",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        rationale="Duplicate action closure test.",
        evidence=evidence,
    )
    finding = TelemetryFinding(
        finding_id="m2605.finding.duplicate",
        code=TelemetryFindingCode.DRIFT_DETECTED,
        message="Duplicate finding closure test.",
        evidence=evidence,
    )
    with pytest.raises(ValidationError, match="reviewer action ids"):
        TelemetryStream(
            stream_id="m2605.stream.duplicate-actions",
            version="1.0.0",
            samples=(sample,),
            reviewer_actions=(action, action),
            evidence=evidence,
        )
    with pytest.raises(ValidationError, match="telemetry finding ids"):
        TelemetryStream(
            stream_id="m2605.stream.duplicate-findings",
            version="1.0.0",
            samples=(sample,),
            findings=(finding, finding),
            evidence=evidence,
        )


def test_request_and_result_closures_reject_duplicate_and_forged_bindings() -> None:
    request = make_request()

    def invalid_request(update: dict[str, object], message: str) -> None:
        candidate = request.model_copy(update=update)
        with pytest.raises(ValidationError, match=message):
            EmitProteomicsTelemetryRequest.model_validate(candidate.model_dump(mode="python"))

    invalid_request(
        {"requested_metrics": (TelemetryMetricKind.INPUT_QUALITY,) * 2},
        "requested telemetry metrics",
    )
    other_upstream = request.upstream_result.model_copy(
        update={"artifact_id": "m2605.other", "digest": sha256_digest("other")}
    )
    invalid_request({"source_artifacts": (other_upstream,)}, "included in source artifacts")
    invalid_request(
        {
            "dashboard_definitions": (
                request.dashboard_definitions[0],
                request.dashboard_definitions[0],
            )
        },
        "dashboard ids",
    )
    action = ReviewerActionRecord(
        action_id="m2605.request.duplicate-action",
        kind=ReviewerActionKind.ACKNOWLEDGED,
        reviewer="m2605-reviewer",
        target_id="m2605.fixture.alert",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        rationale="Duplicate request action closure test.",
        evidence=(_evidence("request-action"),),
    )
    invalid_request(
        {"reviewer_actions": (action, action)},
        "reviewer action ids",
    )
    invalid_request(
        {"samples": (request.samples[0], request.samples[0], *request.samples[2:])},
        "telemetry sample ids",
    )
    invalid_request(
        {"samples": (request.samples[1], request.samples[0], *request.samples[2:])},
        "telemetry samples",
    )

    result = M2605ObservabilityEngine().emit(request)

    def invalid_result(update: dict[str, object], message: str) -> None:
        candidate = result.model_copy(update=update)
        with pytest.raises(ValidationError, match=message):
            type(result).model_validate(candidate.model_dump(mode="python"))

    invalid_result({"request_digest": sha256_digest("forged-request")}, "request digest")
    invalid_result({"result_id": "result.m2605.forged"}, "result id")
    invalid_result(
        {"dashboards": (result.dashboards[0], result.dashboards[0])}, "dashboard ids"
    )
    invalid_result(
        {"findings": (result.findings[0], result.findings[0])}, "result finding ids"
    )
    invalid_result(
        {"evidence": (result.evidence[0], result.evidence[0])}, "result evidence"
    )
    invalid_result({"telemetry_stream": None}, "emitted result")

    assert result.telemetry_stream is not None
    stream_missing_metric = result.telemetry_stream.model_copy(
        update={"samples": (result.telemetry_stream.samples[0],)}
    )
    invalid_result(
        {"telemetry_stream": stream_missing_metric},
        "cover every requested metric",
    )

    drifted_request = request.model_copy(
        update={
            "samples": tuple(
                sample.model_copy(update={"value": 0.6})
                if sample.metric is TelemetryMetricKind.DRIFT
                else sample
                for sample in request.samples
            )
        }
    )
    drifted = M2605ObservabilityEngine().emit(drifted_request)
    invalid_drift = drifted.model_copy(update={"human_review_required": False})
    with pytest.raises(ValidationError, match="human review"):
        type(drifted).model_validate(invalid_drift.model_dump(mode="python"))

    abstained_request = request.model_copy(
        update={
            "requested_metrics": (
                *request.requested_metrics,
                TelemetryMetricKind.REVIEWER_ACTIONS,
            )
        }
    )
    abstained = M2605ObservabilityEngine().emit(abstained_request)
    invalid_abstention = abstained.model_copy(update={"safe_failure_report": None})
    with pytest.raises(ValidationError, match="abstained result"):
        type(abstained).model_validate(invalid_abstention.model_dump(mode="python"))


def test_canonical_projections_accept_mapping_inputs() -> None:
    assert canonical_request_digest({"request_id": "m2605.mapping"}).startswith("sha256:")
    assert result_payload_digest(
        {
            "result_id": "m2605.mapping.result",
            "result_digest": "sha256:" + "0" * 64,
        }
    ).startswith("sha256:")
