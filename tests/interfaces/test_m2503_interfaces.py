"""FastAPI, Typer, and plugin interface parity for M25-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m25_03.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_03 import (
    ProteotypeInternalBenchmarkResult,
    result_payload_digest,
)
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.api import (
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m25_03_internal_benchmark_ablation.cli import app

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
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


def test_api_unknown_schema_is_not_found() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-03/schemas/unknown")

    assert response.status_code == _HTTP_NOT_FOUND


def test_api_returns_one_named_schema() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-03/schemas/request")

    assert response.status_code == _HTTP_OK
    assert response.json()["$id"].endswith(":request")


def test_api_verify_rejects_malformed_and_non_object_json() -> None:
    client = TestClient(create_app())

    malformed = client.post(
        "/v1/modules/M25-03/verify",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    non_object = client.post(
        "/v1/modules/M25-03/verify",
        content=b"[]",
        headers={"content-type": "application/json"},
    )

    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert malformed.json()["detail"] == "request JSON is invalid"
    assert non_object.status_code == _HTTP_UNPROCESSABLE
    assert non_object.json()["detail"] == "request JSON must be an object"


def test_api_rejects_denied_validate_and_benchmark() -> None:
    client = TestClient(create_app())
    payload = denied_request().model_dump(mode="json")

    validated = client.post("/v1/modules/M25-03/validate", json=payload)
    benchmark = client.post("/v1/modules/M25-03/benchmark", json=payload)

    assert validated.status_code == _HTTP_UNPROCESSABLE
    assert benchmark.status_code == _HTTP_UNPROCESSABLE


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


def test_api_verify_rejects_tampered_result() -> None:
    client = TestClient(create_app())
    result = client.post(
        "/v1/modules/M25-03/benchmark",
        json=build_request().model_dump(mode="json"),
    ).json()
    result["result_digest"] = "sha256:" + ("f" * 64)

    response = client.post("/v1/modules/M25-03/verify", json={"result": result})

    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "replay envelope is invalid"


def test_api_verify_rejects_self_rehashed_nested_mutation() -> None:
    client = TestClient(create_app())
    result = client.post(
        "/v1/modules/M25-03/benchmark",
        json=build_request().model_dump(mode="json"),
    ).json()
    typed = ProteotypeInternalBenchmarkResult.model_validate_json(json.dumps(result), strict=True)
    assert typed.dossier is not None
    metric = typed.dossier.metrics[0].model_copy(
        update={"candidate_value": typed.dossier.metrics[0].candidate_value + 1.0}
    )
    dossier = typed.dossier.model_copy(update={"metrics": (metric, *typed.dossier.metrics[1:])})
    tampered = typed.model_copy(update={"dossier": dossier})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})

    response = client.post(
        "/v1/modules/M25-03/verify",
        content=json.dumps({"result": tampered.model_dump(mode="json")}),
    )

    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "replay envelope is invalid"


def test_cli_exports_schema(tmp_path: Path) -> None:
    output = tmp_path / "request-schema.json"
    result = CliRunner().invoke(app, ["export-schema", "request", "--output", str(output)])

    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["$schema"]

    printed = CliRunner().invoke(app, ["export-schema", "request"])
    unknown = CliRunner().invoke(app, ["export-schema", "unknown"])
    assert printed.exit_code == 0
    assert unknown.exit_code != 0


def test_cli_rejects_malformed_request_and_result(tmp_path: Path) -> None:
    request_path = tmp_path / "bad-request.json"
    result_path = tmp_path / "bad-result.json"
    request_path.write_text("not-json", encoding="utf-8")
    result_path.write_text("{}", encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(app, ["validate", str(request_path)])
    benchmark = runner.invoke(app, ["benchmark", str(request_path)])
    verified = runner.invoke(app, ["verify", str(result_path)])

    assert validated.exit_code != 0
    assert benchmark.exit_code != 0
    assert verified.exit_code != 0


def test_cli_sanitizes_denied_request(tmp_path: Path) -> None:
    request_path = tmp_path / "denied.json"
    request_path.write_text(denied_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(app, ["validate", str(request_path)])
    benchmark = runner.invoke(app, ["benchmark", str(request_path)])

    assert validated.exit_code != 0
    assert benchmark.exit_code != 0


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


def test_cli_verify_rejects_self_rehashed_nested_mutation(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert (
        runner.invoke(app, ["benchmark", str(request_path), "--output", str(result_path)]).exit_code
        == 0
    )
    result = ProteotypeInternalBenchmarkResult.model_validate_json(
        result_path.read_bytes(), strict=True
    )
    assert result.dossier is not None
    metric = result.dossier.metrics[0].model_copy(
        update={"candidate_value": result.dossier.metrics[0].candidate_value + 1.0}
    )
    dossier = result.dossier.model_copy(update={"metrics": (metric, *result.dossier.metrics[1:])})
    tampered = result.model_copy(update={"dossier": dossier})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    result_path.write_text(tampered.model_dump_json(), encoding="utf-8")

    verified = runner.invoke(app, ["verify", str(result_path)])

    assert verified.exit_code != 0
    assert "result replay is invalid" in verified.output


def test_cli_benchmark_can_print_to_stdout(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")

    result = CliRunner().invoke(app, ["benchmark", str(request_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"
