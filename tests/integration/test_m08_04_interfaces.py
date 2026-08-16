"""FastAPI and Typer parity checks for the isolated M08-04 boundary."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m08_04 import create_m0804_app, m0804_app
from tests.modules.c08_transcript_protein_discordance.test_m08_04_lifecycle import _request

_HTTP_OK = 200


def test_fastapi_schema_and_estimate_match_service(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    client = TestClient(create_m0804_app())
    schema = client.get("/v1/contracts/M08-04/request/schema")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True

    response = client.post(
        "/v1/modules/M08-04/probabilistic-estimate",
        content=request.model_dump_json(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _HTTP_OK
    assert response.json()["status"] == "estimated"
    assert response.json()["result_digest"].startswith("sha256:")

    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    assert path.exists()


def test_typer_export_validate_and_estimate(tmp_path) -> None:  # type: ignore[no-untyped-def]
    request = _request()
    path = tmp_path / "request.json"
    path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    exported = runner.invoke(m0804_app, ["export-schema", "output"])
    assert exported.exit_code == 0
    assert json.loads(exported.stdout)["x-glio-contract"]["moduleId"] == (
        "GLIO-PROTEOGEN-M08-04"
    )

    validated = runner.invoke(m0804_app, ["validate", str(path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["operation"] == (
        "estimate_transcript_protein_probabilistic"
    )

    estimated = runner.invoke(m0804_app, ["estimate", str(path)])
    assert estimated.exit_code == 0
    assert json.loads(estimated.stdout)["status"] == "estimated"
