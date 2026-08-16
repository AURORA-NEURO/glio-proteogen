"""Runtime, replay, determinism, and fail-closed tests for M26-06."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m26_06 import (
    ControlStatus,
    SecurityAssessmentStatus,
    SecurityControlKind,
)
from glio_proteogen.contracts.m26_06.canonical import result_payload_digest
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    M2606AuthorizationError,
    M2606ReplayError,
    M2606SecurityEngine,
    M2606SecurityService,
    verify_security_access_result,
)
from tests.contract.test_m26_06_provisional import _request


def test_supported_controls_emit_allow_decision_and_replay() -> None:
    result = M2606SecurityEngine().evaluate(_request())

    assert result.status is SecurityAssessmentStatus.EVALUATED
    assert result.access_decision is not None
    assert result.access_decision.state.value == "allow"
    assert result.security_posture is not None
    assert result.security_posture.status.value == "compliant"
    assert result.audit_event is not None
    assert verify_security_access_result(result).result_digest == result.result_digest


def test_failed_control_abstains_without_publishing_access_records() -> None:
    request = _request()
    declarations = tuple(
        declaration.model_copy(
            update={
                "status": ControlStatus.FAILED,
                "rationale": "Threat detector reports an unresolved event.",
            }
        )
        if declaration.control is SecurityControlKind.THREAT_DETECTION
        else declaration
        for declaration in request.control_declarations
    )
    failed_request = type(request).model_validate(
        request.model_copy(update={"control_declarations": declarations})
    )
    result = M2606SecurityEngine().evaluate(failed_request)

    assert result.status is SecurityAssessmentStatus.ABSTAINED
    assert result.access_decision is None
    assert result.audit_event is None
    assert result.safe_failure_report is not None
    assert result.human_review_required is True
    assert result.support_decision.status.value == "review_required"


def test_unresolved_control_is_review_abstention_not_negative_evidence() -> None:
    request = _request()
    declarations = tuple(
        declaration.model_copy(
            update={
                "status": ControlStatus.NOT_EVALUABLE,
                "rationale": "Encryption evidence is unavailable.",
            }
        )
        if declaration.control is SecurityControlKind.ENCRYPTION
        else declaration
        for declaration in request.control_declarations
    )
    result = M2606SecurityEngine().evaluate(
        type(request).model_validate(
            request.model_copy(update={"control_declarations": declarations})
        )
    )

    assert result.status is SecurityAssessmentStatus.ABSTAINED
    assert result.support_decision.status.value == "review_required"
    assert result.security_posture is not None
    assert result.security_posture.status.value == "not_evaluable"
    assert all(
        finding.code.value != "access_rejected" for finding in result.security_posture.findings
    )


def test_upstream_consent_is_fail_closed_before_security_evaluation() -> None:
    request = _request()
    references = request.context.references.model_copy(
        update={
            "consent": request.context.references.consent.model_copy(
                update={"state": ConsentState.REVOKED}
            )
        }
    )
    denied_request = type(request).model_validate(
        request.model_copy(
            update={"context": request.context.model_copy(update={"references": references})}
        )
    )
    with pytest.raises(M2606AuthorizationError):
        M2606SecurityService().execute(denied_request)


def test_replay_rejects_tampered_payload_and_same_request_is_deterministic() -> None:
    request = _request()
    first = M2606SecurityEngine().evaluate(request)
    second = M2606SecurityEngine().evaluate(request)
    assert first.result_digest == second.result_digest
    tampered = first.model_construct(
        **{
            **first.model_dump(mode="python"),
            "result_digest": "sha256:" + "f" * 64,
        }
    )
    with pytest.raises(M2606ReplayError):
        verify_security_access_result(tampered)
    assert result_payload_digest(first) == first.result_digest
