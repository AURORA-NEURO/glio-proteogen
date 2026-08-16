"""FastAPI, Typer, and plugin interface parity for M25-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m25_05.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.api import (
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m25_05_subgroup_equity_evaluator.cli import (
    app,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_schema_surface_is_closed() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-05/schemas")

    assert response.status_code == _HTTP_OK
    assert tuple(response.json()) == (
        "request",
        "output",
        "report",
        "performance",
        "calibration",
        "coverage",
        "configuration",
        "finding",
    )


def test_api_unknown_schema_is_not_found() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-05/schemas/unknown")

    assert response.status_code == _HTTP_NOT_FOUND


def test_api_validate_and_evaluate_share_contract() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")

    validated = client.post("/v1/modules/M25-05/validate", json=payload)
    evaluated = client.post("/v1/modules/M25-05/evaluate", json=payload)

    assert validated.status_code == _HTTP_OK
    assert evaluated.status_code == _HTTP_OK
    assert evaluated.json()["request"] == validated.json()
    assert evaluated.json()["status"] == "evaluated"


def test_api_rejects_denied_and_tampered_requests() -> None:
    client = TestClient(create_app())
    denied = client.post(
        "/v1/modules/M25-05/evaluate", json=denied_request().model_dump(mode="json")
    )
    malformed = client.post("/v1/modules/M25-05/evaluate", json={"request_id": "malformed"})

    assert denied.status_code == _HTTP_UNPROCESSABLE
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert malformed.json()["detail"] == "request does not satisfy the M25-05 contract"


def test_api_verify_replays_and_rejects_tamper() -> None:
    client = TestClient(create_app())
    result = client.post(
        "/v1/modules/M25-05/evaluate", json=build_request().model_dump(mode="json")
    ).json()
    verified = client.post("/v1/modules/M25-05/verify", json={"result": result})
    result["result_digest"] = "sha256:" + ("f" * 64)
    tampered = client.post("/v1/modules/M25-05/verify", json={"result": result})

    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert tampered.status_code == _HTTP_UNPROCESSABLE


def test_api_verify_sanitizes_invalid_json() -> None:
    client = TestClient(create_app())
    malformed = client.post("/v1/modules/M25-05/verify", content=b"not-json")
    non_object = client.post("/v1/modules/M25-05/verify", content=b"[]")

    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert non_object.status_code == _HTTP_UNPROCESSABLE
    assert malformed.json()["detail"] == "request JSON is invalid"


def test_cli_schema_and_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "request-schema.json"
    runner = CliRunner()

    exported = runner.invoke(app, ["export-schema", "request", "--output", str(output)])
    repeated = runner.invoke(app, ["export-schema", "request", "--output", str(output)])
    unknown = runner.invoke(app, ["export-schema", "unknown"])

    assert exported.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["$schema"]
    assert repeated.exit_code != 0
    assert unknown.exit_code != 0


def test_cli_validate_evaluate_and_verify(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(app, ["validate", str(request_path)])
    evaluated = runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(app, ["verify", str(result_path)])

    assert validated.exit_code == 0
    assert evaluated.exit_code == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "evaluated"
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True


def test_cli_rejects_malformed_and_denied(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.json"
    denied_path = tmp_path / "denied.json"
    bad_path.write_text("not-json", encoding="utf-8")
    denied_path.write_text(denied_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    assert runner.invoke(app, ["validate", str(bad_path)]).exit_code != 0
    assert runner.invoke(app, ["evaluate", str(denied_path)]).exit_code != 0
