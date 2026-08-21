"""Deep M27-05 runtime, replay, safe-failure, and token tests."""

from __future__ import annotations

from math import inf

import pytest
from evals.m27_05.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m27_05 import (
    ProteomicsTelemetryResult,
    TelemetrySample,
    TelemetryStatus,
    TelemetryUnit,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry import (
    M2705AuthorizationError,
    M2705Plugin,
    M2705ReplayError,
    M2705Service,
    M2705TelemetryEngine,
    TelemetrySubmission,
    emit_search_quant_observability_telemetry,
)

_EXPECTED_SAMPLE_COUNT = 9


def test_supported_emission_retains_all_requested_metrics() -> None:
    result = emit_search_quant_observability_telemetry(build_request())
    assert result.status is TelemetryStatus.EMITTED
    assert result.telemetry_stream is not None
    assert len(result.telemetry_stream.samples) == _EXPECTED_SAMPLE_COUNT
    assert result.alert is not None
    assert result.safe_failure_report is None
    assert result.parent_target == "complex activity"
    assert result.emits_parent is False


def test_replay_is_byte_equivalent_and_tamper_rejected() -> None:
    service = M2705Service()
    result = service.emit(build_request())
    assert service.replay(result) == result
    forged = result.model_copy(update={"result_id": "m2705.result.forged"})
    with pytest.raises((ValidationError, M2705ReplayError)):
        service.replay(forged)


def test_unsupported_upstream_abstains_without_stream() -> None:
    request = build_request(upstream_media_type="application/json")
    result = M2705TelemetryEngine().emit(request)
    assert result.status is TelemetryStatus.ABSTAINED
    assert result.telemetry_stream is None
    assert result.dashboards == ()
    assert result.safe_failure_report is not None
    assert result.support_decision.status.value == "unsupported"


def test_denied_control_fails_before_telemetry_traversal() -> None:
    request = build_request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    with pytest.raises(M2705AuthorizationError):
        M2705TelemetryEngine().emit(denied)


def test_context_request_identity_must_match_telemetry_request() -> None:
    request = build_request()
    mismatched_context = request.context.model_copy(update={"request_id": "m2705.request.other"})
    with pytest.raises(M2705AuthorizationError):
        M2705TelemetryEngine().emit(request.model_copy(update={"context": mismatched_context}))


def test_plugin_requires_issued_token_and_preserves_parity() -> None:
    plugin = M2705Plugin()
    request = build_request()
    token = plugin.validate(TelemetrySubmission(request))
    assert plugin.run(token) == plugin._service.emit(request)
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_json_service_roundtrip() -> None:
    service = M2705Service()
    request = build_request()
    result = service.emit(request.model_dump_json())
    replay = service.replay(result.model_dump_json())
    assert replay == result


def test_contract_rejects_nonfinite_telemetry_and_bad_result_identity() -> None:
    request = build_request()
    evidence = request.dashboard_definitions[0].evidence or ()
    with pytest.raises(ValidationError):
        TelemetrySample(
            sample_id="m2705.sample.bad",
            metric=request.requested_metrics[0],
            value=inf,
            unit=TelemetryUnit.SCORE,
            observed_at=request.context.occurred_at,
            source="test",
            evidence=evidence,
        )
    result = M2705Service().emit(request)
    payload = result.model_dump(mode="json")
    payload["result_id"] = "m2705.result.other"
    with pytest.raises(ValidationError):
        ProteomicsTelemetryResult.model_validate(payload, strict=True)


def test_provenance_binds_upstream_and_telemetry_configuration() -> None:
    request = build_request()
    result = M2705Service().emit(request)

    assert request.upstream_result.digest in result.provenance.input_digests
    assert result.evidence[0].reference == request.upstream_result
    expected_configuration_digest = sha256_digest(
        {
            "module": "GLIO-PROTEOGEN-M27-05",
            "contract": "0.1.0-provisional",
            "requested_metrics": request.requested_metrics,
            "dashboard_definitions": request.dashboard_definitions,
        }
    )
    assert result.provenance.configuration_digest == expected_configuration_digest

    changed_dashboard = request.dashboard_definitions[0].model_copy(
        update={"metrics": request.requested_metrics[:1]}
    )
    changed = request.model_copy(
        update={
            "requested_metrics": request.requested_metrics[:1],
            "dashboard_definitions": (changed_dashboard,),
        }
    )
    changed_result = M2705Service().emit(changed)
    assert changed_result.provenance.configuration_digest != result.provenance.configuration_digest
