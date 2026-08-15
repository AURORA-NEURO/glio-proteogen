"""Negative and tamper-path tests for M12-07 boundaries."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from glio_proteogen.adapters.m1207 import app
from glio_proteogen.contracts.m12_07 import (
    AdjudicateBiomarkerPanelPlausibilityRequest,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c12_driver_protein_consequence.m12_07_plausibility_adjudicator import (
    M1207PlausibilityAdjudicatorEngine,
)
from tests.runtime.test_m1207_runtime import _artifact, _request

_HTTP_UNPROCESSABLE = 422


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
