"""FastAPI/Typer parity checks for M20-03."""

from __future__ import annotations

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m2003 import app, m2003_app


def test_fastapi_exposes_schema_fuse_and_verify_routes() -> None:
    paths = set(app.openapi()["paths"])
    assert "/v1/m20-03/schema/{name}" in paths
    assert "/v1/modules/M20-03/fuse" in paths
    assert "/v1/modules/M20-03/verify" in paths


def test_typer_exports_all_contract_names_and_rejects_unknown() -> None:
    runner = CliRunner()
    success = runner.invoke(m2003_app, ["export-schema", "request"])
    assert success.exit_code == 0
    assert '"moduleId": "GLIO-PROTEOGEN-M20-03"' in success.stdout
    failure = runner.invoke(m2003_app, ["export-schema", "unknown"])
    assert failure.exit_code == 2  # noqa: PLR2004 - Typer usage error exit code.


def test_fastapi_sanitizes_missing_control_failure() -> None:
    response = TestClient(app).post(
        "/v1/modules/M20-03/fuse",
        json={"operation": "fuse_protein_subtype_evidence"},
    )
    assert response.status_code == 403  # noqa: PLR2004 - HTTP authorization status.
    assert "all seven upstream controls" in response.json()["detail"]
