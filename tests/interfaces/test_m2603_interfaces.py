"""FastAPI, Typer, and canonical interface parity for M26-03."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from evals.m26_03.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (  # noqa: E501
    api as m2603_api,
)
from glio_proteogen.modules.c21_reference_material.m26_03_reproducible_pipeline_orchestrator import (
    cli as m2603_cli,
)

if TYPE_CHECKING:
    from pathlib import Path

_SCHEMA_COUNT = 9


def test_fastapi_schema_validate_execute_verify_parity() -> None:
    request = build_request()
    client = TestClient(m2603_api.create_app())
    schemas = client.get("/v1/modules/M26-03/schemas")
    assert schemas.status_code == HTTPStatus.OK
    assert len(schemas.json()) == _SCHEMA_COUNT
    assert client.get("/v1/modules/M26-03/schemas/unknown").status_code == HTTPStatus.NOT_FOUND

    request_body = request.model_dump_json()
    headers = {"content-type": "application/json"}
    validated = client.post("/v1/modules/M26-03/validate", content=request_body, headers=headers)
    assert validated.status_code == HTTPStatus.OK
    executed = client.post("/v1/modules/M26-03/execute", content=request_body, headers=headers)
    assert executed.status_code == HTTPStatus.OK
    result = executed.json()
    verified = client.post("/v1/modules/M26-03/verify", json={"result": result})
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == {"verified": True, "result_digest": result["result_digest"]}


def test_fastapi_named_schema_and_denied_validation_are_closed() -> None:
    client = TestClient(m2603_api.create_app())
    named = client.get("/v1/modules/M26-03/schemas/workflow")
    denied = client.post(
        "/v1/modules/M26-03/validate", json=denied_request().model_dump(mode="json")
    )
    assert named.status_code == HTTPStatus.OK
    assert named.json()["$id"].endswith(":workflow")
    assert denied.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_fastapi_rejects_denied_and_sanitizes_contract_details() -> None:
    client = TestClient(m2603_api.create_app())
    denied = client.post(
        "/v1/modules/M26-03/execute", json=denied_request().model_dump(mode="json")
    )
    malformed = client.post(
        "/v1/modules/M26-03/execute", json={"secret_submission": "do-not-echo"}
    )
    assert denied.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "secret_submission" not in malformed.text
    assert "M26-03 contract" in malformed.text


def test_fastapi_verify_sanitizes_invalid_json_and_tampering() -> None:
    client = TestClient(m2603_api.create_app())
    malformed = client.post("/v1/modules/M26-03/verify", content=b"not-json")
    non_object = client.post("/v1/modules/M26-03/verify", content=b"[]")
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert non_object.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "request JSON is invalid" in malformed.text
    result = client.post(
        "/v1/modules/M26-03/execute", json=build_request().model_dump(mode="json")
    ).json()
    result["result_digest"] = "sha256:" + ("f" * 64)
    tampered = client.post("/v1/modules/M26-03/verify", json={"result": result})
    assert tampered.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_typer_round_trip_no_overwrite_and_schema_validation(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    schema = runner.invoke(m2603_cli.app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["$schema"].endswith("2020-12/schema")
    validated = runner.invoke(m2603_cli.app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    executed = runner.invoke(
        m2603_cli.app, ["execute", str(request_path), "--output", str(result_path)]
    )
    assert executed.exit_code == 0
    verified = runner.invoke(m2603_cli.app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
    overwrite = runner.invoke(
        m2603_cli.app, ["execute", str(request_path), "--output", str(result_path)]
    )
    assert overwrite.exit_code != 0
    assert "refusing to overwrite" in overwrite.output


def test_typer_export_to_file_and_denied_request_errors(tmp_path: Path) -> None:
    output = tmp_path / "schema.json"
    request_path = tmp_path / "denied.json"
    request_path.write_text(denied_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    exported = runner.invoke(m2603_cli.app, ["export-schema", "request", "--output", str(output)])
    denied = runner.invoke(m2603_cli.app, ["validate", str(request_path)])
    assert exported.exit_code == 0
    assert output.exists()
    assert denied.exit_code != 0
    assert "M26-03 contract" in denied.output


def test_typer_sanitizes_unknown_schema_and_invalid_request(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m2603_cli.app, ["export-schema", "secret-internal-schema"])
    assert unknown.exit_code != 0
    assert "unknown M26-03 contract" in unknown.output
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"secret_submission":"do-not-echo"}', encoding="utf-8")
    response = runner.invoke(m2603_cli.app, ["validate", str(invalid)])
    assert response.exit_code != 0
    assert "secret_submission" not in response.output


def test_typer_invalid_result_is_sanitized(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid-result.json"
    invalid.write_text('{"secret_result":"do-not-echo"}', encoding="utf-8")
    response = CliRunner().invoke(m2603_cli.app, ["verify", str(invalid)])
    assert response.exit_code != 0
    assert "secret_result" not in response.output
