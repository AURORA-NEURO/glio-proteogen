"""M27-06 API, CLI, and plugin parity tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evals.m27_06.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c27_complex_activity.m27_06_security_access import (
    M2706Service,
    create_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_06_security_access.cli import app

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_schema_validate_evaluate_verify_parity() -> None:
    request = build_request()
    client = TestClient(create_app())
    assert client.get("/v1/modules/M27-06/schemas/request").status_code == _HTTP_OK
    assert client.get("/v1/modules/M27-06/schemas/unknown").status_code == _HTTP_NOT_FOUND
    body = request.model_dump_json()
    assert client.post("/v1/modules/M27-06/validate", content=body).status_code == _HTTP_OK
    response = client.post("/v1/modules/M27-06/evaluate", content=body)
    assert response.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M27-06/verify", content=response.content)
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True


def test_cli_file_parity_and_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["export-schema", "request"]).exit_code == 0
    assert runner.invoke(app, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)]).exit_code
        == 0
    )
    assert runner.invoke(app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)]).exit_code
        != 0
    )


def test_api_denial_and_service_descriptor() -> None:
    request = build_request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "withheld"}
                    )
                }
            )
        }
    )
    response = TestClient(create_app()).post(
        "/v1/modules/M27-06/evaluate",
        content=request.model_copy(update={"context": denied_context}).model_dump_json(),
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert M2706Service().descriptor["module_id"] == "GLIO-PROTEOGEN-M27-06"


def test_api_rejects_invalid_replay() -> None:
    response = TestClient(create_app()).post("/v1/modules/M27-06/verify", content=b"{}")
    assert response.status_code == _HTTP_UNPROCESSABLE
