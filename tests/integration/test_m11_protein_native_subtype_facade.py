"""Strict HTTP and direct-service parity for the M11 protein-axis facade."""

from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from glio_proteogen.adapters import m11_protein_native_subtype_facade as adapter
from glio_proteogen.research.gbm_proteomic_axes import (
    GbmProteomicAxesRequest,
    analyze_gbm_proteomic_axes,
)

_PREFIX = adapter.M11_PROTEIN_NATIVE_SUBTYPE_ROUTE_PREFIX
_HTTP_OK = 200
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_UNPROCESSABLE = 422
_HTTP_INTERNAL_ERROR = 500
_HTTP_CLIENT_CLOSED = 499


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_m11_protein_native_subtype_openapi(app)
    return app


def _demo_without_bootstrap(client: TestClient) -> dict[str, object]:
    request: dict[str, object] = client.get(f"{_PREFIX}/demo").json()
    request["bootstrap_replicates"] = 0
    return request


def test_http_lifecycle_matches_direct_published_service_output() -> None:
    with TestClient(_app()) as client:
        profile_response = client.get(f"{_PREFIX}/profile")
        demo_response = client.get(f"{_PREFIX}/demo")
        request = demo_response.json()
        request["bootstrap_replicates"] = 0
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

    typed = GbmProteomicAxesRequest.model_validate_json(json.dumps(request), strict=True)
    direct = analyze_gbm_proteomic_axes(typed)
    profile = profile_response.json()
    assert profile_response.status_code == _HTTP_OK
    assert profile_response.json()["claim_ceiling"] == {
        "supplies_published_protein_axis_evidence": True,
        "can_replace_synthetic_or_caller_declared_axis_scores": True,
        "emits_posterior_subtype_classifier": False,
        "infers_longitudinal_evolution": False,
        "emits_clinical_class": False,
        "infers_mechanism": False,
        "recommends_treatment": False,
        "governed_m11_replacement": False,
    }
    assert analysis_response.status_code == _HTTP_OK, analysis_response.text
    assert result == direct.model_dump(mode="json")
    assert verification_response.status_code == _HTTP_OK
    assert verification_response.json()["verified"] is True
    assert forged_response.status_code == _HTTP_OK
    assert forged_response.json()["verified"] is False
    assert forged_response.json()["result_digest_match"] is False
    assert analysis_response.headers["x-glio-profile-digest"] == direct.profile_digest
    assert analysis_response.headers["x-glio-request-digest"] == direct.request_digest
    assert analysis_response.headers["x-glio-result-digest"] == direct.result_digest
    for response in (
        profile_response,
        demo_response,
        analysis_response,
        verification_response,
        forged_response,
    ):
        assert (
            response.headers["x-glio-facade-profile-digest"] == (profile["facade_profile_digest"])
        )
        assert response.headers["x-glio-profile-digest"] == (profile["delegated_profile_digest"])
    for suffix in ("profile", "demo", "analyze", "verify"):
        assert f"{_PREFIX}/{suffix}" in openapi["paths"]
    analyze_schema = openapi["paths"][f"{_PREFIX}/analyze"]["post"]["requestBody"]
    verify_schema = openapi["paths"][f"{_PREFIX}/verify"]["post"]["requestBody"]
    assert analyze_schema["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GbmProteomicAxesRequest"
    }
    assert verify_schema["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GbmReplayVerificationRequest"
    }
    replay_result_schema = openapi["components"]["schemas"]["GbmReplayVerificationRequest"][
        "properties"
    ]["result"]
    assert {item["$ref"] for item in replay_result_schema["anyOf"]} == {
        "#/components/schemas/GbmProteomicAxesResult",
        "#/components/schemas/UnverifiedGbmProteomicAxesResult",
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
            forged_response,
        )
    )


def test_strict_ingress_rejects_hostile_json_without_echoing_values() -> None:
    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"sample_id":"sensitive-a","sample_id":"sensitive-b"}',
            headers={"content-type": "application/json"},
        )
        unknown = client.post(
            f"{_PREFIX}/analyze",
            json={"private-field": "sensitive-value"},
        )
        coercion = client.post(
            f"{_PREFIX}/analyze",
            json={
                "profile_id": "gbm-proteomic-axes/1.0.0",
                "sample_id": "sample",
                "measurements": [],
                "bootstrap_replicates": True,
            },
        )
        nonfinite = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"value":NaN}',
            headers={"content-type": "application/json"},
        )

    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert all(
        response.status_code == _HTTP_UNPROCESSABLE
        for response in (duplicate, unknown, coercion, nonfinite)
    )
    combined = " ".join(response.text for response in (duplicate, unknown, coercion, nonfinite))
    assert "sensitive" not in combined
    assert "private-field" not in combined
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (wrong_media, duplicate, unknown, coercion, nonfinite)
    )


def test_request_replay_and_response_byte_limits_are_enforced(monkeypatch) -> None:
    with TestClient(_app()) as client:
        request_too_large = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(adapter.M11_PROTEIN_NATIVE_SUBTYPE_REQUEST_MAX_BYTES + 1),
            },
        )
        replay_too_large = client.post(
            f"{_PREFIX}/verify",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(adapter.M11_PROTEIN_NATIVE_SUBTYPE_REPLAY_MAX_BYTES + 1),
            },
        )
        request = _demo_without_bootstrap(client)
        monkeypatch.setattr(adapter, "M11_PROTEIN_NATIVE_SUBTYPE_RESULT_MAX_BYTES", 1)
        result_too_large = client.post(f"{_PREFIX}/analyze", json=request)

    assert request_too_large.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert replay_too_large.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert result_too_large.status_code == _HTTP_INTERNAL_ERROR
    assert "response exceeded its byte limit" in result_too_large.text


def test_unexpected_model_failure_is_sanitized(monkeypatch) -> None:
    sensitive_detail = "sensitive upstream model filesystem detail"

    def fail(*_args, **_kwargs):
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(adapter, "analyze_m11_protein_axis_evidence", fail)
    with TestClient(_app()) as client:
        request = _demo_without_bootstrap(client)
        response = client.post(f"{_PREFIX}/analyze", json=request)

    assert response.status_code == _HTTP_INTERNAL_ERROR
    assert response.json() == {"detail": "M11 protein-axis evidence analysis failed safely"}
    assert "sensitive" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_disconnect_watcher_cancels_the_running_model_token(monkeypatch) -> None:
    async def disconnect(_request, cancellation, _finished) -> None:
        cancellation.cancel()

    def wait_for_cancellation(_request, *, cancellation):
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            cancellation.checkpoint()
            time.sleep(0.001)
        raise AssertionError

    monkeypatch.setattr(adapter, "_watch_disconnect", disconnect)
    monkeypatch.setattr(adapter, "analyze_m11_protein_axis_evidence", wait_for_cancellation)
    with TestClient(_app()) as client:
        request = _demo_without_bootstrap(client)
        response = client.post(f"{_PREFIX}/analyze", json=request)

    assert response.status_code == _HTTP_CLIENT_CLOSED
    assert response.json() == {"detail": "M11 protein-axis evidence computation was cancelled"}
    assert response.headers["cache-control"] == "no-store"
