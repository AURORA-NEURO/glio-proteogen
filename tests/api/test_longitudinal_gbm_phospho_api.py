"""HTTP, OpenAPI, deployment-catalog, and CLI lifecycle tests for phosphosites."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import _MODEL_ROUTE_LIMITS, create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.deployment import DeploymentSettings, create_deployment_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
)
from glio_proteogen.research.longitudinal_gbm_phospho.demo import synthetic_demo_request

PREFIX = "/v1/research/longitudinal-gbm-phospho"
HTTP_OK = 200
HTTP_TOO_LARGE = 413
HTTP_UNSUPPORTED_MEDIA = 415
HTTP_UNPROCESSABLE = 422
EXPECTED_LOG_BASE = 2

if TYPE_CHECKING:
    from pathlib import Path


def test_central_api_demo_analyze_verify_lifecycle(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        profile = client.get(f"{PREFIX}/profile")
        assert profile.status_code == HTTP_OK
        assert profile.headers["cache-control"] == "no-store"
        assert not profile.json()["quality_gates"]["bootstrap_calibration_passed"]
        assert profile.json()["sphinks_crosswalk_provenance"]["license"] == "CC-BY-4.0"

        demo = client.get(f"{PREFIX}/demo")
        assert demo.status_code == HTTP_OK
        assert demo.json()["assay_compatibility"]["log_base"] == EXPECTED_LOG_BASE

        analysis = client.post(f"{PREFIX}/analyze", json=demo.json())
        assert analysis.status_code == HTTP_OK
        assert analysis.headers["x-glio-result-digest"] == analysis.json()["result_digest"]
        assert all(item["support"] == "limited" for item in analysis.json()["transitions"])
        assert analysis.json()["model_views"][1]["support"] == "not_fitted"
        assert (
            analysis.json()["provenance"]["sphinks_crosswalk_provenance"]["runtime_use"]
            == "exact_identity_annotation_only_no_kinase_inference"
        )

        verification = client.post(
            f"{PREFIX}/verify",
            json={"request": demo.json(), "result": analysis.json()},
        )
        assert verification.status_code == HTTP_OK
        assert verification.json()["verified"]


def test_api_rejects_wrong_media_duplicate_keys_and_unknown_sites(tmp_path: Path) -> None:
    request = synthetic_demo_request().model_dump(mode="json")
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        wrong_media = client.post(f"{PREFIX}/analyze", content=b"{}", headers={})
        assert wrong_media.status_code == HTTP_UNSUPPORTED_MEDIA

        duplicate = client.post(
            f"{PREFIX}/analyze",
            content=b'{"series_id":"a","series_id":"b"}',
            headers={"content-type": "application/json"},
        )
        assert duplicate.status_code == HTTP_UNPROCESSABLE

        request["time_points"][0]["observations"][0]["phosphosite_id"] = "ENSP99999999999.1:s1"
        unknown = client.post(f"{PREFIX}/analyze", json=request)
        assert unknown.status_code == HTTP_UNPROCESSABLE
        assert "ENSP" not in unknown.json()["detail"]


def test_openapi_and_route_limits_are_exact(tmp_path: Path) -> None:
    app = create_app(tmp_path / "events.sqlite3")
    schema = app.openapi()
    assert {path for path in schema["paths"] if path.startswith(PREFIX)} == {
        f"{PREFIX}/profile",
        f"{PREFIX}/demo",
        f"{PREFIX}/analyze",
        f"{PREFIX}/verify",
    }
    analyze_schema = schema["paths"][f"{PREFIX}/analyze"]["post"]
    assert analyze_schema["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LongitudinalGbmPhosphoRequest"
    }
    verify_schema = schema["paths"][f"{PREFIX}/verify"]["post"]
    assert verify_schema["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LongitudinalGbmPhosphoReplayVerificationRequest"
    }
    assert _MODEL_ROUTE_LIMITS[PREFIX] == (MAX_REQUEST_BYTES, MAX_RESULT_BYTES)
    assert _MODEL_ROUTE_LIMITS[f"{PREFIX}/verify"] == (MAX_REPLAY_BYTES, MAX_RESULT_BYTES)


def test_v2_deployment_catalog_discovers_every_phosphosite_operation(tmp_path: Path) -> None:
    app = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "events.sqlite3", environment="test")
    )
    with TestClient(app) as client:
        response = client.get("/v2/deployment/catalog")
    assert response.status_code == HTTP_OK
    operations = {
        (item["method"], item["path"]): item
        for item in response.json()["operations"]
        if item["path"].startswith(PREFIX)
    }
    assert set(operations) == {
        ("GET", f"{PREFIX}/profile"),
        ("GET", f"{PREFIX}/demo"),
        ("POST", f"{PREFIX}/analyze"),
        ("POST", f"{PREFIX}/verify"),
    }
    analyze = operations[("POST", f"{PREFIX}/analyze")]
    assert analyze["request_max_bytes"] == MAX_REQUEST_BYTES
    assert analyze["result_max_bytes"] == MAX_RESULT_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["validated_example_id"] == ("synthetic-kncc-longitudinal-phosphosite-series-v1")


def test_declared_oversized_body_is_rejected_before_decode(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        response = client.post(
            f"{PREFIX}/analyze",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(MAX_REQUEST_BYTES + 1),
            },
        )
    assert response.status_code == HTTP_TOO_LARGE


def test_cli_demo_analyze_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    demo = runner.invoke(cli_app, ["longitudinal-gbm-phospho", "demo"])
    assert demo.exit_code == 0
    request_path = tmp_path / "request.json"
    request_path.write_text(demo.stdout, encoding="utf-8")
    analysis = runner.invoke(
        cli_app,
        ["longitudinal-gbm-phospho", "analyze", str(request_path)],
    )
    assert analysis.exit_code == 0
    result = json.loads(analysis.stdout)
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(
        canonical_json_bytes({"request": json.loads(demo.stdout), "result": result})
    )
    verification = runner.invoke(
        cli_app,
        ["longitudinal-gbm-phospho", "verify", str(receipt)],
    )
    assert verification.exit_code == 0
    assert json.loads(verification.stdout)["verified"]
