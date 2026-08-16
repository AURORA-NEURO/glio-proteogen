"""FastAPI/Typer parity checks for M20-04."""

from __future__ import annotations

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m2004 import app, m2004_app


def test_fastapi_exposes_schema_adapt_and_verify_routes() -> None:
    paths = set(app.openapi()["paths"])
    assert "/v1/m20-04/schema/{name}" in paths
    assert "/v1/modules/M20-04/adapt" in paths
    assert "/v1/modules/M20-04/verify" in paths


def test_typer_exports_contract_names_and_rejects_unknown() -> None:
    runner = CliRunner()
    success = runner.invoke(m2004_app, ["export-schema", "request"])
    assert success.exit_code == 0
    assert '"moduleId": "GLIO-PROTEOGEN-M20-04"' in success.stdout
    failure = runner.invoke(m2004_app, ["export-schema", "unknown"])
    assert failure.exit_code == 2  # noqa: PLR2004 - Typer usage error exit code.


def test_fastapi_sanitizes_missing_control_failure() -> None:
    response = TestClient(app).post(
        "/v1/modules/M20-04/adapt",
        json={"operation": "adapt_protein_subtype_intended_use"},
    )
    assert response.status_code == 403  # noqa: PLR2004 - HTTP authorization status.
    assert "all seven upstream controls" in response.json()["detail"]
