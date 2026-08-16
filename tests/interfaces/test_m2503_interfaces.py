"""FastAPI, Typer, and plugin interface parity for M25-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m25_03.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.api import (
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.cli import app

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422


def test_api_schema_surface_is_closed() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-03/schemas")

    assert response.status_code == _HTTP_OK
    assert tuple(response.json()) == (
        "request",
        "output",
        "dossier",
        "split",
        "baseline",
        "metric",
        "ablation",
        "comparison",
        "finding",
    )


def test_api_validate_and_benchmark_share_contract() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")

    validated = client.post("/v1/modules/M25-03/validate", json=payload)
    benchmark = client.post("/v1/modules/M25-03/benchmark", json=payload)

    assert validated.status_code == _HTTP_OK
    assert benchmark.status_code == _HTTP_OK
    assert benchmark.json()["request"] == validated.json()
    assert benchmark.json()["status"] == "completed"


def test_api_sanitizes_validation_errors() -> None:
    response = TestClient(create_app()).post(
        "/v1/modules/M25-03/benchmark",
        json={"request_id": "malformed"},
    )

    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "request does not satisfy the M25-03 contract"


def test_api_verify_replays_result() -> None:
    client = TestClient(create_app())
    result = client.post(
        "/v1/modules/M25-03/benchmark",
        json=build_request().model_dump(mode="json"),
    ).json()

    response = client.post("/v1/modules/M25-03/verify", json={"result": result})

    assert response.status_code == _HTTP_OK
    assert response.json()["verified"] is True


def test_cli_exports_schema(tmp_path: Path) -> None:
    output = tmp_path / "request-schema.json"
    result = CliRunner().invoke(app, ["export-schema", "request", "--output", str(output)])

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["$schema"]


def test_cli_validate_and_benchmark_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(app, ["validate", str(request_path)])
    executed = runner.invoke(app, ["benchmark", str(request_path), "--output", str(result_path)])
    repeated = runner.invoke(app, ["benchmark", str(request_path), "--output", str(result_path)])

    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["request_id"] == "m2503-fixture-request"
    assert executed.exit_code == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "completed"
    assert repeated.exit_code != 0


def test_cli_verify_result(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert (
        runner.invoke(app, ["benchmark", str(request_path), "--output", str(result_path)]).exit_code
        == 0
    )

    verified = runner.invoke(app, ["verify", str(result_path)])

    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True
