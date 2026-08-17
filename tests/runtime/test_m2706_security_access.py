"""Deep M27-06 security/access runtime, replay, and token tests."""

from __future__ import annotations

import pytest
from evals.m27_06.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m27_06 import (
    ComplexActivitySecurityAccessResult,
    SecurityAssessmentStatus,
)
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access import (
    M2706AuthorizationError,
    M2706Plugin,
    M2706ReplayError,
    M2706SecurityEngine,
    M2706Service,
    SecuritySubmission,
    evaluate_complex_activity_security_access,
)

_CONTROL_COUNT = 8


def test_supported_access_is_evaluated_and_replays() -> None:
    service = M2706Service()
    result = evaluate_complex_activity_security_access(build_request())
    assert result.status is SecurityAssessmentStatus.EVALUATED
    assert result.access_decision is not None
    assert result.access_decision.state.value == "allow"
    assert result.security_posture is not None
    assert len(result.security_posture.controls) == _CONTROL_COUNT
    assert service.replay(result) == result


def test_denied_and_missing_consent_are_explicit() -> None:
    denied = M2706SecurityEngine().emit(build_request(action="deny-read"))
    assert denied.status is SecurityAssessmentStatus.EVALUATED
    assert denied.access_decision is not None
    assert denied.access_decision.state.value == "deny"
    assert denied.security_posture is not None
    assert denied.security_posture.status.value == "critical"
    missing = M2706SecurityEngine().emit(build_request(with_consent=False))
    assert missing.status is SecurityAssessmentStatus.ABSTAINED
    assert missing.access_decision is None
    assert missing.safe_failure_report is not None


def test_unsupported_upstream_abstains_without_security_records() -> None:
    result = M2706SecurityEngine().emit(build_request(upstream_media_type="application/json"))
    assert result.status is SecurityAssessmentStatus.ABSTAINED
    assert result.access_decision is None
    assert result.security_posture is None
    assert result.safe_failure_report is not None


def test_denied_control_fails_before_request_traversal() -> None:
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
    with pytest.raises(M2706AuthorizationError):
        M2706SecurityEngine().emit(request.model_copy(update={"context": denied_context}))


def test_plugin_token_parity_and_replay_tamper_rejection() -> None:
    plugin = M2706Plugin()
    request = build_request()
    token = plugin.validate(SecuritySubmission(request))
    assert plugin.run(token) == plugin._service.emit(request)
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]
    result = plugin.run(token)
    with pytest.raises((ValidationError, M2706ReplayError)):
        plugin.replay(result.model_copy(update={"result_id": "m2706.result.forged"}))


def test_json_service_roundtrip() -> None:
    service = M2706Service()
    request = build_request()
    result = service.emit(request.model_dump_json())
    assert service.replay(result.model_dump_json()) == result
    payload = result.model_dump(mode="json")
    payload["result_digest"] = "sha256:" + "f" * 64
    with pytest.raises((ValidationError, M2706ReplayError, ValueError)):
        service.replay(payload)


def test_result_projection_rejects_forged_status_shape() -> None:
    result = M2706Service().emit(build_request())
    payload = result.model_dump(mode="json")
    payload["status"] = "abstained"
    payload["access_decision"] = None
    with pytest.raises(ValueError, match=r".+"):
        ComplexActivitySecurityAccessResult.model_validate(payload, strict=True)
