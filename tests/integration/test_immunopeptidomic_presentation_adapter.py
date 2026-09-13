"""Transport and lifecycle coverage for the caller-owned HLA presentation lane."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.status import (
    HTTP_200_OK,
    HTTP_413_CONTENT_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    HTTP_422_UNPROCESSABLE_CONTENT,
)

from glio_proteogen.adapters import immunopeptidomic_presentation as adapter


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    return app


def test_demo_analyze_verify_lifecycle_and_headers() -> None:
    with TestClient(_app()) as client:
        profile = client.get(f"{adapter.PRESENTATION_ROUTE_PREFIX}/profile")
        demo = client.get(f"{adapter.PRESENTATION_ROUTE_PREFIX}/demo")
        analysis = client.post(
            f"{adapter.PRESENTATION_ROUTE_PREFIX}/analyze",
            json=demo.json(),
        )
        verification = client.post(
            f"{adapter.PRESENTATION_ROUTE_PREFIX}/verify",
            json={"request": demo.json(), "result": analysis.json()},
        )

    assert profile.status_code == HTTP_200_OK
    assert demo.status_code == HTTP_200_OK
    assert analysis.status_code == HTTP_200_OK
    assert analysis.json()["support"] == "supported"
    assert analysis.headers["x-glio-profile-digest"] == profile.json()["profile_digest"]
    assert analysis.headers["x-glio-result-digest"] == analysis.json()["result_digest"]
    assert verification.status_code == HTTP_200_OK
    assert verification.json()["verified"] is True


def test_openapi_contains_all_operations_and_nested_replay_schema() -> None:
    schema = _app().openapi()
    prefix = adapter.PRESENTATION_ROUTE_PREFIX
    assert {path for path in schema["paths"] if path.startswith(prefix)} == {
        f"{prefix}/profile",
        f"{prefix}/demo",
        f"{prefix}/analyze",
        f"{prefix}/verify",
    }
    verify_body = schema["paths"][f"{prefix}/verify"]["post"]["requestBody"]
    assert verify_body["content"]["application/json"]["schema"]["$defs"]


def test_transport_errors_are_bounded_and_sanitized() -> None:
    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{adapter.PRESENTATION_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        invalid = client.post(
            f"{adapter.PRESENTATION_ROUTE_PREFIX}/analyze",
            content=b'{"bad":true}',
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{adapter.PRESENTATION_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(adapter.PRESENTATION_REQUEST_MAX_BYTES + 1),
            },
        )

    assert wrong_media.status_code == HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert invalid.status_code == HTTP_422_UNPROCESSABLE_CONTENT
    assert oversized.status_code == HTTP_413_CONTENT_TOO_LARGE
    assert "traceback" not in invalid.text.lower()


def test_modified_receipt_is_rejected() -> None:
    with TestClient(_app()) as client:
        demo = client.get(f"{adapter.PRESENTATION_ROUTE_PREFIX}/demo").json()
        result = client.post(f"{adapter.PRESENTATION_ROUTE_PREFIX}/analyze", json=demo).json()
        result["sample_id"] = "forged"
        verification = client.post(
            f"{adapter.PRESENTATION_ROUTE_PREFIX}/verify",
            json={"request": demo, "result": result},
        )
    assert verification.status_code == HTTP_422_UNPROCESSABLE_CONTENT

