"""Negative and tamper-path tests for M12-07 boundaries."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from glio_proteogen.adapters.m1207 import app
from glio_proteogen.contracts.m12_07 import (
    AdjudicateBiomarkerPanelPlausibilityRequest,
    BiomarkerPanelPlausibilityAdjudicationResult,
    ControlOutcome,
    UnresolvedConflict,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import Limitation, SupportStatus
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c12_driver_protein_consequence.m12_07_plausibility_adjudicator import (
    M1207PlausibilityAdjudicatorEngine,
    adjudicate_biomarker_panel_plausibility,
    preflight_m1207_authorization,
    verify_m1207_result,
)
from tests.runtime.test_m1207_runtime import _artifact, _request

_HTTP_UNPROCESSABLE = 422
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelPlausibilityAdjudicationResult)


def test_strict_json_rejects_duplicate_keys_and_non_finite_numbers() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"x": 1, "x": 2}', max_bytes=128)
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"x": NaN}', max_bytes=128)


def test_contract_rejects_wrong_upstream_media_type() -> None:
    request = _request()
    with pytest.raises(ValueError, match="must bind the provisional M12-06 result"):
        AdjudicateBiomarkerPanelPlausibilityRequest(
            request_id=request.request_id,
            context=request.context,
            mechanism_inference_result=_artifact("wrong", "application/json"),
            controls=request.controls,
            source_artifacts=request.source_artifacts,
        )


def test_contract_rejects_duplicate_control_and_context_ids() -> None:
    request = _request()
    duplicate = request.controls[1].model_copy(
        update={"control_id": request.controls[0].control_id}
    )
    with pytest.raises(ValueError, match="control ids must be unique"):
        AdjudicateBiomarkerPanelPlausibilityRequest(
            request_id=request.request_id,
            context=request.context,
            mechanism_inference_result=request.mechanism_inference_result,
            controls=(request.controls[0], duplicate),
            source_artifacts=request.source_artifacts,
        )


def test_contract_rejects_upstream_source_reuse_and_duplicate_conflicts() -> None:
    request = _request()
    with pytest.raises(ValueError, match="mechanism result must not be duplicated"):
        AdjudicateBiomarkerPanelPlausibilityRequest(
            request_id=request.request_id,
            context=request.context,
            mechanism_inference_result=request.mechanism_inference_result,
            controls=request.controls,
            source_artifacts=(request.mechanism_inference_result,),
        )
    conflict = UnresolvedConflict(
        conflict_id="conflict.duplicate",
        description="Two mechanisms remain unresolved.",
        competing_mechanisms=("a", "b"),
    )
    with pytest.raises(ValueError, match="declared conflict ids must be unique"):
        AdjudicateBiomarkerPanelPlausibilityRequest(
            request_id=request.request_id,
            context=request.context,
            mechanism_inference_result=request.mechanism_inference_result,
            controls=request.controls,
            source_artifacts=request.source_artifacts,
            declared_conflicts=(conflict, conflict),
        )


def test_public_stateless_operations_and_preflight_missing_context() -> None:
    request = _request()
    result = adjudicate_biomarker_panel_plausibility(request)
    assert verify_m1207_result(request, result) == result
    with pytest.raises(ValueError, match="seven upstream"):
        preflight_m1207_authorization({})


def test_expected_direction_requires_observation_and_accepts_match() -> None:
    request = _request()
    control = request.controls[0].model_copy(
        update={
            "expected_direction": "increasing",
            "declared_observed_direction": None,
            "declared_outcome": ControlOutcome.PASSED,
        }
    )
    not_evaluable = M1207PlausibilityAdjudicatorEngine().adjudicate(
        request.model_copy(update={"controls": (control, *request.controls[1:])})
    )
    assert not_evaluable.status.value == "abstained"
    matching = control.model_copy(update={"declared_observed_direction": "increasing"})
    accepted = M1207PlausibilityAdjudicatorEngine().adjudicate(
        request.model_copy(update={"controls": (matching, *request.controls[1:])})
    )
    assert accepted.status.value == "adjudicated"
    with pytest.raises(ValueError, match="request id"):
        AdjudicateBiomarkerPanelPlausibilityRequest(
            request_id="request.other",
            context=request.context,
            mechanism_inference_result=request.mechanism_inference_result,
            controls=request.controls,
            source_artifacts=request.source_artifacts,
        )


def test_missing_declared_outcome_abstains_and_never_emits_negative_grade() -> None:
    request = _request()
    controls = list(request.controls)
    controls[0] = controls[0].model_copy(update={"declared_outcome": None})
    result = M1207PlausibilityAdjudicatorEngine().adjudicate(
        request.model_copy(update={"controls": tuple(controls)})
    )
    assert result.grade is None
    assert result.status.value == "abstained"


def test_api_rejects_extra_verify_fields_without_leaking_details() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/modules/M12-07/verify",
        json={"request": _request().model_dump(mode="json"), "result": {}, "extra": "x"},
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json() == {"detail": "invalid M12-07 request or result"}


def test_result_tamper_of_support_status_is_rejected() -> None:
    engine = M1207PlausibilityAdjudicatorEngine()
    request = _request()
    result = engine.adjudicate(request)
    tampered = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"reason_code": "tampered"}
            )
        }
    )
    with pytest.raises(ValueError, match="result digest"):
        engine.verify(request, tampered)


def test_result_contract_closure_rejects_each_tamper_shape() -> None:
    engine = M1207PlausibilityAdjudicatorEngine()
    request = _request()
    result = engine.adjudicate(request)
    invalid = (
        (result.model_copy(update={"request_digest": "sha256:" + "0" * 64}), "request digest"),
        (result.model_copy(update={"evaluations": ()}), "every control"),
        (result.model_copy(update={"result_digest": "sha256:" + "0" * 64}), "result digest"),
    )
    for candidate, message in invalid:
        with pytest.raises(ValueError, match=message):
            _RESULT_ADAPTER.validate_python(candidate, strict=True)


def test_result_contract_rejects_duplicate_findings_conflicts_and_status_closure() -> None:
    engine = M1207PlausibilityAdjudicatorEngine()
    request = _request()
    controls = list(request.controls)
    controls[0] = controls[0].model_copy(update={"declared_outcome": ControlOutcome.FAILED})
    failed = engine.adjudicate(request.model_copy(update={"controls": tuple(controls)}))
    duplicate_finding = failed.model_copy(
        update={"findings": (failed.findings[0], failed.findings[0])}
    )
    with pytest.raises(ValueError, match="finding ids"):
        _RESULT_ADAPTER.validate_python(duplicate_finding, strict=True)
    conflict = UnresolvedConflict(
        conflict_id="conflict.status",
        description="Competing mechanisms remain unresolved.",
        competing_mechanisms=("a", "b"),
    )
    conflicted = engine.adjudicate(request.model_copy(update={"declared_conflicts": (conflict,)}))
    duplicate_conflict = conflicted.model_copy(
        update={"conflicts": (conflicted.conflicts[0], conflicted.conflicts[0])}
    )
    with pytest.raises(ValueError, match="conflict ids"):
        _RESULT_ADAPTER.validate_python(duplicate_conflict, strict=True)
    invalid_supported = engine.adjudicate(request).model_copy(
        update={
            "support_decision": engine.adjudicate(request).support_decision.model_copy(
                update={"status": SupportStatus.REVIEW_REQUIRED}
            )
        }
    )
    with pytest.raises(ValueError, match="adjudicated result"):
        _RESULT_ADAPTER.validate_python(invalid_supported, strict=True)
    invalid_abstained = failed.model_copy(update={"human_review_required": False})
    with pytest.raises(ValueError, match="abstained result"):
        _RESULT_ADAPTER.validate_python(invalid_abstained, strict=True)


def test_replay_verifier_rejects_recomputed_payload_tamper() -> None:
    engine = M1207PlausibilityAdjudicatorEngine()
    request = _request()
    result = engine.adjudicate(request)
    payload = result.model_dump(mode="json")
    payload["limitations"] = [
        *payload["limitations"],
        Limitation(code="m1207.extra", statement="Extra limitation for replay test.").model_dump(
            mode="json"
        ),
    ]
    payload["result_digest"] = result_payload_digest(payload)
    recomputed = _RESULT_ADAPTER.validate_json(canonical_json_bytes(payload), strict=True)
    with pytest.raises(ValueError, match="replay digest"):
        engine.verify(request, recomputed)
