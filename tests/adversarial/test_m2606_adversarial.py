"""Adversarial boundary and branch-closure tests for M26-06."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from glio_proteogen.contracts.m26_06 import (
    AccessDecisionState,
    ControlStatus,
    ProteomicsSecurityAccessResult,
    SecurityAssessmentStatus,
    SecurityControlKind,
)
from glio_proteogen.contracts.m26_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control import (
    M2606AuthorizationError,
    M2606ReplayError,
    M2606SecurityEngine,
    M2606SecurityPlugin,
    M2606SecurityService,
    M2606TokenError,
    SecuritySubmission,
    preflight_m2606_authorization,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_06_security_privacy_access_control.api import (
    create_m2606_app,
)
from tests.contract.test_m26_06_provisional import _request

_HTTP_UNPROCESSABLE = 422
_HTTP_NOT_FOUND = 404


def _self_rehashed(
    result: ProteomicsSecurityAccessResult, updates: dict[str, Any]
) -> ProteomicsSecurityAccessResult:
    forged = result.model_copy(update=updates)
    return type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )


def test_request_context_and_control_declaration_drift_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="request ID"):
        type(request).model_validate(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={"request_id": "m2606.request.foreign"}
                    )
                }
            )
        )
    duplicate = (*request.control_declarations[:-1], request.control_declarations[0])
    with pytest.raises(ValidationError, match="declarations must be unique"):
        type(request).model_validate(request.model_copy(update={"control_declarations": duplicate}))


def test_plugin_rejects_forged_submission_and_cross_instance_token() -> None:
    request = _request()
    plugin = M2606SecurityPlugin()
    with pytest.raises(M2606TokenError):
        plugin.validate(object())  # type: ignore[arg-type]
    token = plugin.validate(SecuritySubmission(canonical_json_bytes(request)))
    with pytest.raises(M2606TokenError):
        M2606SecurityPlugin().run(token)


def test_plugin_token_rejects_post_issuance_request_replacement() -> None:
    request = _request()
    plugin = M2606SecurityPlugin()
    token = plugin.validate(SecuritySubmission(request))
    object.__setattr__(token, "request", request.model_copy(deep=True))
    with pytest.raises(M2606TokenError):
        plugin.run(token)


def test_preflight_hostile_mapping_fails_closed() -> None:
    class Hostile:
        def __getattr__(self, name: str) -> object:
            raise RuntimeError(name)

    with pytest.raises(M2606AuthorizationError):
        preflight_m2606_authorization(Hostile())


def test_api_rejects_duplicate_keys_nan_and_unknown_schema() -> None:
    client = TestClient(create_m2606_app())
    duplicate = client.post(
        "/v1/modules/M26-06/evaluate",
        content=b'{"request_id":"a","request_id":"b"}',
    )
    nan = client.post("/v1/modules/M26-06/evaluate", content=b'{"value":NaN}')
    unknown = client.get("/v1/modules/M26-06/schemas/not-a-contract")
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert nan.status_code == _HTTP_UNPROCESSABLE
    assert unknown.status_code == _HTTP_NOT_FOUND


def test_api_rejects_oversized_and_non_object_replay_envelopes() -> None:
    client = TestClient(create_m2606_app())
    oversized = client.post(
        "/v1/modules/M26-06/evaluate",
        content=b"{" + b'"x":"' + b"a" * (4 * 1024 * 1024) + b'"}',
    )
    scalar = client.post("/v1/modules/M26-06/verify", content=b"[]")
    assert oversized.status_code == _HTTP_UNPROCESSABLE
    assert scalar.status_code == _HTTP_UNPROCESSABLE


def test_abstention_never_becomes_negative_access_evidence() -> None:
    request = _request()
    declarations = tuple(
        item.model_copy(
            update={
                "status": ControlStatus.NOT_EVALUABLE,
                "rationale": "Secrets evidence is unavailable.",
            }
        )
        if item.control is SecurityControlKind.SECRETS
        else item
        for item in request.control_declarations
    )
    result = M2606SecurityEngine().evaluate(
        type(request).model_validate(
            request.model_copy(update={"control_declarations": declarations})
        )
    )
    assert result.status.value == "abstained"
    assert result.access_decision is None
    assert result.safe_failure_report is not None
    assert result.support_decision.status.value == "review_required"


def test_canonical_request_digest_ignores_only_no_fields_and_is_stable() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    assert canonical_request_digest(request) == canonical_request_digest(payload)
    assert canonical_json_bytes(payload) == canonical_json_bytes(
        json.loads(canonical_json_bytes(payload))
    )


@pytest.mark.parametrize("region", ["reason", "status", "posture", "evidence", "limitations"])
def test_self_rehashed_mutations_are_rejected_across_result_regions(region: str) -> None:
    result = M2606SecurityEngine().evaluate(_request())
    updates: dict[str, Any]
    if region == "reason":
        assert result.access_decision is not None
        updates = {
            "access_decision": result.access_decision.model_copy(
                update={"reason": "forged security decision"}
            )
        }
    elif region == "status":
        updates = {"status": SecurityAssessmentStatus.ABSTAINED}
    elif region == "posture":
        assert result.security_posture is not None
        finding = result.security_posture.findings[0].model_copy(update={"message": "forged"})
        updates = {
            "security_posture": result.security_posture.model_copy(
                update={"findings": (finding, *result.security_posture.findings[1:])}
            )
        }
    elif region == "evidence":
        evidence = result.evidence[0].model_copy(update={"claim": "forged evidence"})
        updates = {"evidence": (evidence, *result.evidence[1:])}
    else:
        limitation = result.limitations[0].model_copy(update={"statement": "forged"})
        updates = {"limitations": (limitation, *result.limitations[1:])}
    forged = _self_rehashed(result, updates)
    with pytest.raises(M2606ReplayError):
        M2606SecurityService.verify(forged)


def test_self_rehashed_result_identity_and_auth_failure_are_rejected_safely() -> None:
    result = M2606SecurityEngine().evaluate(_request())
    forged_identity = _self_rehashed(result, {"result_id": "result.m2606.forged"})
    with pytest.raises(M2606ReplayError, match="replay verification failed"):
        M2606SecurityService.verify(forged_identity)

    references = result.request.context.references.model_copy(
        update={
            "consent": result.request.context.references.consent.model_copy(
                update={"state": ConsentState.REVOKED}
            )
        }
    )
    request = result.request.model_copy(
        update={"context": result.request.context.model_copy(update={"references": references})}
    )
    request_digest = canonical_request_digest(request)
    forged = result.model_copy(update={"request": request, "request_digest": request_digest})
    forged = type(forged).model_construct(
        **{
            **forged.__dict__,
            "request": request,
            "request_digest": request_digest,
            "result_digest": result_payload_digest(forged),
        }
    )
    with pytest.raises(M2606ReplayError, match="replay verification failed"):
        M2606SecurityService.verify(forged)


def test_self_rehashed_evaluated_decision_cannot_change_subject_or_audit_binding() -> None:
    result = M2606SecurityEngine().evaluate(_request())
    assert result.access_decision is not None
    assert result.audit_event is not None

    forged_decision = _self_rehashed(
        result,
        {
            "access_decision": result.access_decision.model_copy(
                update={"resource": "resource.forged"}
            )
        },
    )
    with pytest.raises(ValidationError, match="access decision must bind"):
        ProteomicsSecurityAccessResult.model_validate(forged_decision.model_dump(mode="python"))

    forged_audit = _self_rehashed(
        result,
        {
            "audit_event": result.audit_event.model_copy(
                update={"decision_state": AccessDecisionState.DENY}
            )
        },
    )
    with pytest.raises(ValidationError, match="audit event must bind"):
        ProteomicsSecurityAccessResult.model_validate(forged_audit.model_dump(mode="python"))
