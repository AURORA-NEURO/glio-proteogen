"""HTTP lifecycle for fitted M09 participant-transition concordance evidence."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import longitudinal_gbm_complex_transition as adapter
from glio_proteogen.adapters.api import _MODEL_ROUTE_LIMITS
from glio_proteogen.research.longitudinal_gbm_complex_transition import (
    LongitudinalGbmComplexTransitionRequest,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.service import (
    analyze_longitudinal_gbm_complex_transition,
)

_PREFIX = adapter.M09_COMPLEX_TRANSITION_ROUTE_PREFIX
_HTTP_OK = 200


def _app() -> FastAPI:
    app = FastAPI()
    adapter.mount_longitudinal_gbm_complex_transition(app)
    adapter.install_longitudinal_gbm_complex_transition_openapi(app)
    return app


def test_http_lifecycle_is_exact_content_bound_delegation() -> None:
    with TestClient(_app()) as client:
        profile_response = client.get(f"{_PREFIX}/profile")
        demo_response = client.get(f"{_PREFIX}/demo")
        request = demo_response.json()
        analysis_response = client.post(f"{_PREFIX}/analyze", json=request)
        result = analysis_response.json()
        verification_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request, "result": result},
        )
        forged = {**result, "result_digest": "sha256:" + "f" * 64}
        forged_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request, "result": forged},
        )
        openapi = client.get("/openapi.json").json()

    typed = LongitudinalGbmComplexTransitionRequest.model_validate_json(
        json.dumps(request),
        strict=True,
    )
    direct = analyze_longitudinal_gbm_complex_transition(typed)
    profile = profile_response.json()

    assert profile_response.status_code == _HTTP_OK
    assert demo_response.status_code == _HTTP_OK
    assert analysis_response.status_code == _HTTP_OK, analysis_response.text
    assert result == direct.model_dump(mode="json")
    assert result["output_semantics"] == "reactome_participant_set_transition_concordance"
    assert verification_response.status_code == _HTTP_OK
    assert verification_response.json()["verified"] is True
    assert forged_response.status_code == _HTTP_OK
    assert forged_response.json()["verified"] is False
    assert forged_response.json()["result_digest_match"] is False

    facade_digest = profile["facade_profile_digest"]
    delegated_digest = direct.profile_digest
    for response in (
        profile_response,
        demo_response,
        analysis_response,
        verification_response,
        forged_response,
    ):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-glio-facade-profile-digest"] == facade_digest
        assert response.headers["x-glio-profile-digest"] == delegated_digest
    assert analysis_response.headers["x-glio-request-digest"] == direct.request_digest
    assert analysis_response.headers["x-glio-result-digest"] == direct.result_digest

    for suffix in ("profile", "demo", "analyze", "verify"):
        assert f"{_PREFIX}/{suffix}" in openapi["paths"]
    assert openapi["paths"][f"{_PREFIX}/analyze"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/LongitudinalGbmComplexTransitionRequest"}
    assert openapi["paths"][f"{_PREFIX}/verify"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/ComplexTransitionReplayVerificationRequest"}
    for operation in ("analyze", "verify"):
        responses = openapi["paths"][f"{_PREFIX}/{operation}"]["post"]["responses"]
        assert {"400", "413", "415", "422", "429", "499", "500", "503", "504"} <= set(responses)


def test_transport_limits_are_exact_delegated_bounds() -> None:
    assert _MODEL_ROUTE_LIMITS[_PREFIX] == (
        adapter.M09_COMPLEX_TRANSITION_REQUEST_MAX_BYTES,
        adapter.M09_COMPLEX_TRANSITION_RESULT_MAX_BYTES,
    )
    assert _MODEL_ROUTE_LIMITS[f"{_PREFIX}/verify"] == (
        adapter.M09_COMPLEX_TRANSITION_REPLAY_MAX_BYTES,
        adapter.M09_COMPLEX_TRANSITION_RESULT_MAX_BYTES,
    )
