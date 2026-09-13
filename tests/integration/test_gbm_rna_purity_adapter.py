"""HTTP lifecycle and transport boundaries for published GBMPurity inference."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.status import (
    HTTP_200_OK,
    HTTP_413_CONTENT_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    HTTP_422_UNPROCESSABLE_CONTENT,
)

from glio_proteogen.adapters import gbm_rna_purity as adapter
from glio_proteogen.research.gbm_rna_purity.contracts import MODEL_FEATURE_COUNT


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_gbm_rna_purity_openapi(app)
    return app


def test_demo_analyze_verify_lifecycle_and_headers() -> None:
    with TestClient(_app()) as client:
        profile = client.get(f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/profile")
        demo = client.get(f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/demo")
        analysis = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
            json=demo.json(),
        )
        verification = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/verify",
            json={"request": demo.json(), "result": analysis.json()},
        )

    assert profile.status_code == HTTP_200_OK
    assert demo.status_code == HTTP_200_OK
    assert len(demo.json()["counts"]) == MODEL_FEATURE_COUNT
    assert analysis.status_code == HTTP_200_OK
    assert analysis.json()["support"] == "supported"
    assert analysis.headers["x-glio-profile-digest"] == profile.json()["profile_digest"]
    assert analysis.headers["x-glio-result-digest"] == analysis.json()["result_digest"]
    assert verification.status_code == HTTP_200_OK
    assert verification.json()["verified"] is True


def test_openapi_has_exact_replay_union_and_all_operations() -> None:
    schema = _app().openapi()
    prefix = adapter.GBM_RNA_PURITY_ROUTE_PREFIX

    assert {path for path in schema["paths"] if path.startswith(prefix)} == {
        f"{prefix}/profile",
        f"{prefix}/demo",
        f"{prefix}/analyze",
        f"{prefix}/verify",
    }
    request_schema = schema["components"]["schemas"]["GbmRnaPurityReplayVerificationRequest"]
    assert request_schema["properties"]["result"]["anyOf"]


def test_transport_errors_are_bounded_and_sanitized() -> None:
    with TestClient(_app()) as client:
        wrong_media = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        invalid = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
            content=b'{"bad":true}',
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{adapter.GBM_RNA_PURITY_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(adapter.GBM_RNA_PURITY_REQUEST_MAX_BYTES + 1),
            },
        )

    assert wrong_media.status_code == HTTP_415_UNSUPPORTED_MEDIA_TYPE
    assert invalid.status_code == HTTP_422_UNPROCESSABLE_CONTENT
    assert oversized.status_code == HTTP_413_CONTENT_TOO_LARGE
    assert "traceback" not in invalid.text.lower()
