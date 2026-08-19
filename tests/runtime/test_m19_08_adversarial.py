"""Deep negative-path coverage for M19-08 runtime boundaries."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_08 import (
    MonitorStatus,
    RollbackDecision,
    TranslationFinding,
    TranslationHealthReport,
    TranslationHealthState,
)
from glio_proteogen.contracts.m19_08.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_08_translation_monitoring_service as m1908,
)
from tests.contract.test_m19_08_hardening import _request


def test_preflight_rejects_an_unreadable_context() -> None:
    with pytest.raises(m1908.M1908AuthorizationError):
        m1908.preflight_m1908_authorization(object())


def test_verify_supports_digest_only_mode() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_request())
    assert engine.verify(result, replay=False) == result


def test_verify_rejects_identifier_even_when_payload_digest_is_recomputed() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_request())
    forged = result.model_copy(update={"result_id": "result.forged"})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(m1908.M1908ReplayVerificationError, match="identifier"):
        engine.verify(forged, replay=False)


def test_verify_rejects_replay_mismatch_after_valid_digest_recalculation() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_request())
    forged = result.model_copy(update={"human_review_required": True})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(m1908.M1908ReplayVerificationError, match="replay"):
        engine.verify(forged)


def test_public_operation_and_service_mapping_boundaries() -> None:
    request = _request()
    encoded_request = canonical_json_bytes(request.model_dump(mode="json"))
    service = m1908.M1908Service()
    result = service.execute(encoded_request)
    assert service.execute(request.model_dump(mode="json")) == result
    encoded_result = canonical_json_bytes(result.model_dump(mode="json"))
    assert service.verify(encoded_result) == result
    assert service.verify(result.model_dump(mode="json")) == result
    assert m1908.monitor_proteotype_translation_health(request) == result
    assert service.descriptor["parent"] == "proteotype"


def test_service_rejects_invalid_json_and_plugin_strict_json_edges() -> None:
    service = m1908.M1908Service()
    with pytest.raises((TypeError, ValueError)):
        service.execute(b"{not-json")
    plugin = m1908.M1908Plugin()
    with pytest.raises(ValueError, match="valid JSON"):
        plugin.validate_json("{not-json")
    with pytest.raises(ValueError, match="size limit"):
        plugin.validate_json(b" " * (4 * 1024 * 1024 + 1))
    token = plugin.validate_json(canonical_json_bytes(_request().model_dump(mode="json")))
    result = plugin.run(token)
    assert result.status is MonitorStatus.MONITORED


def test_plugin_token_rejects_forged_cross_instance_and_nested_mutation() -> None:
    request = _request()
    plugin = m1908.M1908Plugin()
    other = m1908.M1908Plugin()
    token = plugin.validate(request)

    assert plugin.run(token).status is MonitorStatus.MONITORED

    forged = m1908.ValidatedM1908Request(request=token.request, _seal=token._seal)
    with pytest.raises(m1908.M1908TokenError):
        plugin.run(forged)
    with pytest.raises(m1908.M1908TokenError):
        other.run(token)

    changed_telemetry = token.request.telemetry[0].model_copy(update={"observed_value": 99.0})
    object.__setattr__(
        token.request,
        "telemetry",
        (changed_telemetry, *token.request.telemetry[1:]),
    )
    with pytest.raises(m1908.M1908TokenError):
        plugin.run(token)


def test_result_contract_rejects_duplicate_finding_ids_and_codes() -> None:
    engine = m1908.M1908TranslationMonitoringEngine()
    result = engine.infer(_request())
    assert result.findings
    duplicate_id = result.findings[0].model_copy(update={"finding_id": "finding.duplicate"})
    payload = result.model_dump(mode="json")
    payload["findings"] = [
        duplicate_id.model_dump(mode="json"),
        duplicate_id.model_dump(mode="json"),
    ]
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="finding ids"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)
    second = TranslationFinding(
        finding_id="finding.second",
        code=duplicate_id.code,
        message="second finding",
    )
    payload = result.model_dump(mode="json")
    payload["findings"] = [duplicate_id.model_dump(mode="json"), second.model_dump(mode="json")]
    payload["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="finding codes"):
        type(result).model_validate_json(canonical_json_bytes(payload), strict=True)


def test_report_contract_rejects_state_decision_and_identity_collisions() -> None:
    request = _request()
    report = TranslationHealthReport(
        report_id="report.m1908.adversarial",
        version="0.1.0-provisional",
        telemetry=request.telemetry,
        support_drift=request.support_drift,
        workflow_effects=request.workflow_effects,
        discrepancies=request.discrepancies,
        health_state=TranslationHealthState.HEALTHY,
        rollback_decision=RollbackDecision.NONE,
        rollback_policy=request.rollback_policy,
        evidence=request.telemetry[0].evidence,
    )
    payload = report.model_dump(mode="json")
    payload["health_state"] = "degraded"
    with pytest.raises(ValidationError, match="decision"):
        TranslationHealthReport.model_validate_json(canonical_json_bytes(payload), strict=True)
    payload = report.model_dump(mode="json")
    payload["support_drift"][0]["observation_id"] = payload["telemetry"][0]["observation_id"]
    with pytest.raises(ValidationError, match="observation ids"):
        TranslationHealthReport.model_validate_json(canonical_json_bytes(payload), strict=True)
