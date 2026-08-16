"""Adversarial closure for M18-08 service, plugin and replay boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m18_08 import (
    M1808_MAX_CANONICAL_REQUEST_BYTES,
    MonitorStatus,
    ObservationStatus,
    TelemetryObservation,
    TranslationHealthReport,
    TranslationHealthState,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportDecision, SupportStatus
from glio_proteogen.modules.c18_spatial_proteomics import (
    m18_08_translation_monitoring_service as m1808,
)
from tests.runtime.test_m18_08_monitoring import _artifact, _evidence, _request


def test_unsupported_upstream_abstains_without_report() -> None:
    request = _request().model_copy(
        update={
            "support_decision": SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="unsupported_upstream",
                rationale="synthetic unsupported export",
            )
        }
    )
    result = m1808.M1808TranslationMonitoringEngine().infer(request)
    assert result.status is MonitorStatus.ABSTAINED
    assert result.health_report is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED


def test_mapping_preflight_rejects_missing_context() -> None:
    with pytest.raises(m1808.M1808AuthorizationError):
        m1808.preflight_m1808_authorization({})


def test_mapping_preflight_rejects_wrong_control_state() -> None:
    request = _request()
    candidate = request.model_dump(mode="json")
    candidate["context"]["references"]["consent"]["state"] = "withheld"
    with pytest.raises(m1808.M1808AuthorizationError):
        m1808.M1808TranslationMonitoringEngine().infer(candidate)


def test_engine_verify_accepts_replay_disabled() -> None:
    engine = m1808.M1808TranslationMonitoringEngine()
    result = engine.infer(_request())
    assert engine.verify(result, replay=False) == result


def test_engine_verify_rejects_malformed_result() -> None:
    with pytest.raises(m1808.M1808ReplayVerificationError):
        m1808.M1808TranslationMonitoringEngine().verify({"result_digest": "bad"})


def test_public_operation_and_service_json_boundaries() -> None:
    request = _request()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))
    service = m1808.M1808Service()
    result = service.execute(encoded)
    assert service.execute(request.model_dump(mode="json")) == result
    encoded_result = canonical_json_bytes(result.model_dump(mode="json"))
    assert service.verify(encoded_result) == result
    assert service.verify(result.model_dump(mode="json")) == result
    assert m1808.monitor_biomarker_panel_translation_health(request) == result
    assert service.descriptor["parent"] == "biomarker panel"


def test_service_rejects_invalid_json() -> None:
    with pytest.raises((TypeError, ValueError)):
        m1808.M1808Service().execute(b"{not-json")


def test_service_rejects_oversized_json_before_validation() -> None:
    oversized = b'{"padding":"' + b"x" * M1808_MAX_CANONICAL_REQUEST_BYTES + b'"}'
    with pytest.raises((TypeError, ValueError), match="byte limit"):
        m1808.M1808Service().execute(oversized)


def test_service_rejects_duplicate_json_keys() -> None:
    encoded = canonical_json_bytes(_request().model_dump(mode="json"))
    duplicate = encoded[:-1] + b',"request_id":"forged"}'
    with pytest.raises((TypeError, ValueError), match="duplicate"):
        m1808.M1808Service().execute(duplicate)


def test_authorization_preflight_precedes_malformed_observations() -> None:
    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["telemetry"] = "not-a-sequence"
    with pytest.raises(m1808.M1808AuthorizationError):
        m1808.M1808TranslationMonitoringEngine().infer(payload)


def test_plugin_rejects_forged_and_cross_instance_tokens() -> None:
    request = _request()
    first = m1808.M1808Plugin()
    second = m1808.M1808Plugin()
    token = first.validate(request)
    assert first.validate_request(request) == request
    with pytest.raises(AttributeError):
        token.request = request  # type: ignore[misc]
    with pytest.raises(m1808.M1808TokenError):
        second.run(token)
    token._seal = object()
    with pytest.raises(m1808.M1808TokenError):
        first.run(token)
    result = first.run(first.validate(request))
    assert first.verify(result) == first.replay(result) == result


def test_contract_rejects_duplicate_ids_and_unknown_evidence() -> None:
    request = _request()
    duplicate = request.model_copy(
        update={
            "discrepancies": (
                request.discrepancies[0],
                request.discrepancies[0].model_copy(update={"status": ObservationStatus.WARNING}),
            )
        }
    )
    with pytest.raises(ValidationError):
        type(request).model_validate(duplicate.model_dump(mode="json"), strict=True)
    unknown = _evidence(_artifact("unknown"))
    bad = request.model_copy(
        update={"telemetry": (request.telemetry[0].model_copy(update={"evidence": (unknown,)}),)}
    )
    with pytest.raises(ValidationError):
        type(request).model_validate(bad.model_dump(mode="json"), strict=True)


def test_contract_rejects_source_binding_closure_violations() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["source_artifacts"] = [payload["source_artifacts"][0]]
    with pytest.raises(ValidationError, match="upstream result"):
        type(request).model_validate_json(canonical_json_bytes(payload), strict=True)
    payload = request.model_dump(mode="json")
    payload["source_artifacts"] = payload["source_artifacts"] + [payload["source_artifacts"][0]]
    with pytest.raises(ValidationError, match="source artifacts"):
        type(request).model_validate_json(canonical_json_bytes(payload), strict=True)


def test_contract_rejects_health_and_result_identity_collisions() -> None:
    request = _request()
    result = m1808.M1808TranslationMonitoringEngine().infer(request)
    assert result.health_report is not None
    report_payload = result.health_report.model_dump(mode="json")
    report_payload["support_drift"][0]["observation_id"] = report_payload["telemetry"][0][
        "observation_id"
    ]
    with pytest.raises(ValidationError, match="observation ids"):
        type(result.health_report).model_validate_json(
            canonical_json_bytes(report_payload), strict=True
        )
    result_payload = result.model_dump(mode="json")
    result_payload["request_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="request digest"):
        type(result).model_validate_json(canonical_json_bytes(result_payload), strict=True)


def test_result_closure_rejects_invalid_status_and_digest() -> None:
    result = m1808.M1808TranslationMonitoringEngine().infer(_request())
    payload = result.model_dump(mode="json")
    payload["health_report"] = None
    payload["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="supported health report"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)
    payload = result.model_dump(mode="json")
    payload["status"] = "abstained"
    payload["abstention_reason"] = None
    payload["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="abstained result"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)
    payload = result.model_dump(mode="json")
    payload["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="result digest"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)


def test_contract_rejects_nonfinite_telemetry() -> None:
    with pytest.raises(ValidationError):
        TelemetryObservation.model_validate(
            _request().telemetry[0].model_dump(mode="json") | {"observed_value": float("nan")},
            strict=True,
        )


def test_contract_rejects_passing_telemetry_outside_declared_delta() -> None:
    with pytest.raises(ValidationError, match="allowed delta"):
        TelemetryObservation.model_validate_json(
            canonical_json_bytes(
                _request().telemetry[0].model_dump(mode="json")
                | {"observed_value": 2.0, "baseline_value": 1.0, "allowed_delta": 0.2},
            ),
            strict=True,
        )


def test_discrepancy_failure_is_never_silently_healthy() -> None:
    result = m1808.M1808TranslationMonitoringEngine().infer(
        _request(discrepancy_status=ObservationStatus.FAIL)
    )
    assert result.health_report is not None
    assert result.health_report.health_state is TranslationHealthState.DEGRADED
    assert any(item.code.value == "policy_violation" for item in result.findings)


def test_contract_rejects_decision_state_mismatch() -> None:
    result = m1808.M1808TranslationMonitoringEngine().infer(_request())
    assert result.health_report is not None
    payload = result.health_report.model_dump(mode="json")
    payload.update({"health_state": "suspended", "rollback_decision": "none"})
    with pytest.raises(ValidationError):
        TranslationHealthReport.model_validate(payload, strict=True)
