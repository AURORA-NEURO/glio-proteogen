"""HTTP admission and replay tests for the fitted-model M10 research facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m10_functional_proteotype_facade as adapter

if TYPE_CHECKING:
    import pytest

_PREFIX = adapter.M10_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX
_HTTP_OK = 200
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_INTERNAL_ERROR = 500
_SENSITIVE_FAILURE = "sensitive fitted-artifact path"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_m10_functional_proteotype_openapi(app)
    return app


def test_http_lifecycle_delegates_exact_fitted_receipts() -> None:
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
        openapi = client.get("/openapi.json").json()

    assert profile_response.status_code == _HTTP_OK
    profile = profile_response.json()
    assert profile["delegation"]["engine_profile_id"] == (
        "migliozzi-gbm-functional-proteotype/1.0.0"
    )
    assert profile["claim_ceiling"] == {
        "supplies_source_locked_four_axis_protein_concordance": True,
        "can_replace_synthetic_or_caller_declared_m10_03_m10_07_numerical_stand_ins": True,
        "emits_sample_pathway_activation": False,
        "emits_posterior_subtype": False,
        "infers_mechanism": False,
        "infers_causal_perturbation": False,
        "emits_prognosis": False,
        "recommends_treatment": False,
        "governed_m10_replacement": False,
    }
    assert [item["module_id"] for item in profile["responsibility_boundaries"]] == [
        f"GLIO-PROTEOGEN-M10-{index:02d}" for index in range(1, 9)
    ]
    assert demo_response.status_code == _HTTP_OK
    assert analysis_response.status_code == _HTTP_OK, analysis_response.text
    assert verification_response.status_code == _HTTP_OK
    assert verification_response.json()["verified"] is True
    assert result["profile_digest"] == profile["delegated_profile_digest"]
    assert result["request_digest"] == demo_response.headers["x-glio-request-digest"]
    assert analysis_response.headers["x-glio-profile-digest"] == result["profile_digest"]
    assert analysis_response.headers["x-glio-request-digest"] == result["request_digest"]
    assert analysis_response.headers["x-glio-result-digest"] == result["result_digest"]
    assert verification_response.headers["x-glio-profile-digest"] == result["profile_digest"]
    assert (
        verification_response.headers["x-glio-request-digest"]
        == (verification_response.json()["recomputed_request_digest"])
    )
    assert (
        verification_response.headers["x-glio-result-digest"]
        == (verification_response.json()["recomputed_result_digest"])
    )
    assert (
        profile_response.headers["x-glio-facade-profile-digest"]
        == (profile["facade_profile_digest"])
    )
    assert (
        profile_response.headers["x-glio-profile-digest"] == (profile["delegated_profile_digest"])
    )
    assert demo_response.headers["x-glio-profile-digest"] == profile["delegated_profile_digest"]
    for response in (demo_response, analysis_response, verification_response):
        assert (
            response.headers["x-glio-facade-profile-digest"] == (profile["facade_profile_digest"])
        )
    for suffix in ("profile", "demo", "analyze", "verify"):
        assert f"{_PREFIX}/{suffix}" in openapi["paths"]
    assert openapi["paths"][f"{_PREFIX}/analyze"]["post"]["requestBody"] == {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/M10FunctionalProteotypeRequest"}
            }
        },
    }
    expected_post_responses = {
        "200",
        "400",
        "413",
        "415",
        "422",
        "429",
        "499",
        "500",
        "504",
    }
    for operation in ("analyze", "verify"):
        assert set(openapi["paths"][f"{_PREFIX}/{operation}"]["post"]["responses"]) == (
            expected_post_responses
        )
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (
            profile_response,
            demo_response,
            analysis_response,
            verification_response,
        )
    )


def test_strict_ingress_and_byte_limits_fail_closed() -> None:
    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        unknown = client.post(f"{_PREFIX}/analyze", json={"private": "do-not-echo"})
        duplicate = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"sample_id":"secret-a","sample_id":"secret-b"}',
            headers={"content-type": "application/json"},
        )
        too_large = client.post(
            f"{_PREFIX}/verify",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(adapter.M10_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES + 1),
            },
        )

    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert unknown.status_code == _HTTP_UNPROCESSABLE
    assert duplicate.status_code == _HTTP_UNPROCESSABLE
    assert too_large.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert "do-not-echo" not in unknown.text
    assert "secret" not in duplicate.text
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (wrong_media, unknown, duplicate, too_large)
    )


def test_profile_and_demo_size_or_integrity_failures_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES", 1)
        with TestClient(_app()) as client:
            profile_too_large = client.get(f"{_PREFIX}/profile")
    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "M10_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES", 1)
        with TestClient(_app()) as client:
            demo_too_large = client.get(f"{_PREFIX}/demo")

    def fail() -> None:
        raise RuntimeError(_SENSITIVE_FAILURE)

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "m10_facade_profile", fail)
        with TestClient(_app()) as client:
            profile_failure = client.get(f"{_PREFIX}/profile")
    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "m10_facade_demo", fail)
        with TestClient(_app()) as client:
            demo_failure = client.get(f"{_PREFIX}/demo")

    assert all(
        response.status_code == _HTTP_INTERNAL_ERROR
        for response in (profile_too_large, demo_too_large, profile_failure, demo_failure)
    )
    assert profile_too_large.json() == {
        "detail": "M10 functional-proteotype profile exceeded its byte limit"
    }
    assert demo_too_large.json() == {
        "detail": "M10 functional-proteotype demo exceeded its byte limit"
    }
    assert profile_failure.json() == {"detail": "M10 functional-proteotype profile is unavailable"}
    assert demo_failure.json() == {"detail": "M10 functional-proteotype demo is unavailable"}
    assert "sensitive" not in profile_failure.text
    assert "sensitive" not in demo_failure.text
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (profile_too_large, demo_too_large, profile_failure, demo_failure)
    )
