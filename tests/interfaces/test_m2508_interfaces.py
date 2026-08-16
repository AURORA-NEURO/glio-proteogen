"""FastAPI, Typer, and canonical interface parity for M25-08."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from evals.m25_08.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator import (
    api as m2508_api,
)
from glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator import (
    cli as m2508_cli,
)

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_COUNT = 10


def test_fastapi_schema_validate_adjudicate_verify_parity() -> None:
    request = build_request()
    client = TestClient(m2508_api.create_app())
    schemas = client.get("/v1/modules/M25-08/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    assert client.get("/v1/modules/M25-08/schemas/unknown").status_code == HTTPStatus.NOT_FOUND

    request_body = request.model_dump_json()
    headers = {"content-type": "application/json"}
    validated = client.post("/v1/modules/M25-08/validate", content=request_body, headers=headers)
    assert validated.status_code == HTTPStatus.OK
    adjudicated = client.post(
        "/v1/modules/M25-08/adjudicate", content=request_body, headers=headers
    )
    assert adjudicated.status_code == HTTPStatus.OK
    result = adjudicated.json()
    verified = client.post("/v1/modules/M25-08/verify", json={"result": result})
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == {"verified": True, "result_digest": result["result_digest"]}


def test_fastapi_rejects_denied_and_sanitizes_contract_details() -> None:
    client = TestClient(m2508_api.create_app())
    denied = client.post(
        "/v1/modules/M25-08/adjudicate", json=denied_request().model_dump(mode="json")
    )
    malformed = client.post(
        "/v1/modules/M25-08/adjudicate", json={"secret_submission": "do-not-echo"}
    )
    assert denied.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret_submission" not in malformed.text
    assert "M25-08 contract" in malformed.text


def test_fastapi_verify_sanitizes_invalid_json() -> None:
    client = TestClient(m2508_api.create_app())
    malformed = client.post("/v1/modules/M25-08/verify", content=b"not-json")
    non_object = client.post("/v1/modules/M25-08/verify", content=b"[]")
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert non_object.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "request JSON is invalid" in malformed.text


def test_typer_round_trip_no_overwrite_and_schema_validation(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    schema = runner.invoke(m2508_cli.app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$schema"].endswith("2020-12/schema")
    validated = runner.invoke(m2508_cli.app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    adjudicated = runner.invoke(
        m2508_cli.app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert adjudicated.exit_code == 0
    verified = runner.invoke(m2508_cli.app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    overwrite = runner.invoke(
        m2508_cli.app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert overwrite.exit_code != 0
    assert "refusing to overwrite" in overwrite.output


def test_typer_sanitizes_unknown_schema_and_invalid_request(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2508_cli.app, ["export-schema", "secret-internal-schema"])
    assert unknown.exit_code != 0
    assert "unknown M25-08 contract" in unknown.output
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"secret_submission":"do-not-echo"}', encoding="utf-8")
    response = runner.invoke(m2508_cli.app, ["validate", str(invalid)])
    assert response.exit_code != 0
    assert "secret_submission" not in response.output


def test_typer_abstention_is_non_constructed_and_nonzero(tmp_path: Path) -> None:
    request_path = tmp_path / "blocked.json"
    result_path = tmp_path / "blocked-result.json"
    request_path.write_text(
        build_request(requirement_satisfied=False).model_dump_json(), encoding="utf-8"
    )
    response = CliRunner().invoke(
        m2508_cli.app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert response.exit_code != 0
    assert result_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "abstained"
