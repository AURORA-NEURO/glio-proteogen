"""FastAPI, Typer, and plugin parity for provisional M25-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m25_04.fixture import build_request, denied_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_04 import TransportStatus
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator import (
    M2504Plugin,
    M2504Service,
    TransportSubmission,
)
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator.api import (
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m25_04_external_transport_evaluator.cli import (
    app,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_schema_surface_is_closed() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-04/schemas")

    assert response.status_code == _HTTP_OK
    assert tuple(response.json()) == (
        "request",
        "output",
        "validation",
        "evaluation",
        "support-domain-update",
        "configuration",
        "report",
        "finding",
    )


def test_api_unknown_schema_is_not_found() -> None:
    response = TestClient(create_app()).get("/v1/modules/M25-04/schemas/unknown")
    assert response.status_code == _HTTP_NOT_FOUND


def test_api_validate_and_evaluate_share_canonical_request() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")

    validated = client.post("/v1/modules/M25-04/validate", json=payload)
    evaluated = client.post("/v1/modules/M25-04/evaluate", json=payload)

    assert validated.status_code == _HTTP_OK
    assert evaluated.status_code == _HTTP_OK
    assert evaluated.json()["request"] == validated.json()
    assert evaluated.json()["status"] == "evaluated"


def test_api_denied_and_malformed_requests_are_sanitized() -> None:
    client = TestClient(create_app())
    denied = client.post(
        "/v1/modules/M25-04/evaluate", json=denied_request().model_dump(mode="json")
    )
    malformed = client.post("/v1/modules/M25-04/evaluate", json={"request_id": "bad"})

    assert denied.status_code == _HTTP_UNPROCESSABLE
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert "M2504AuthorizationError" not in denied.text


def test_api_verify_replays_result_and_rejects_tamper() -> None:
    client = TestClient(create_app())
    result = client.post(
        "/v1/modules/M25-04/evaluate", json=build_request().model_dump(mode="json")
    ).json()
    verified = client.post("/v1/modules/M25-04/verify", json={"result": result})
    result["result_digest"] = "sha256:" + ("f" * 64)
    tampered = client.post("/v1/modules/M25-04/verify", json={"result": result})

    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert tampered.status_code == _HTTP_UNPROCESSABLE


def test_api_verify_rejects_non_object_json() -> None:
    response = TestClient(create_app()).post(
        "/v1/modules/M25-04/verify", content=b"[]", headers={"content-type": "application/json"}
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "request JSON must be an object"


def test_cli_exports_and_validates_schema(tmp_path: Path) -> None:
    output = tmp_path / "request-schema.json"
    exported = CliRunner().invoke(app, ["export-schema", "request", "--output", str(output)])
    unknown = CliRunner().invoke(app, ["export-schema", "unknown"])

    assert exported.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["$schema"]
    assert unknown.exit_code != 0


def test_cli_evaluate_refuses_overwrite_and_verify_replays(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(app, ["validate", str(request_path)])
    evaluated = runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)])
    repeated = runner.invoke(app, ["evaluate", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(app, ["verify", str(result_path)])

    assert validated.exit_code == 0
    assert evaluated.exit_code == 0
    assert repeated.exit_code != 0
    assert verified.exit_code == 0
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "evaluated"


def test_cli_abstention_is_nonzero_and_writes_safe_result(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(
        build_request(status=TransportStatus.NOT_EVALUABLE).model_dump_json(), encoding="utf-8"
    )
    result = CliRunner().invoke(app, ["evaluate", str(request_path), "--output", str(result_path)])

    assert result.exit_code == 1
    assert json.loads(result_path.read_text(encoding="utf-8"))["report"] is None


def test_strict_plugin_parity_and_token_boundary() -> None:
    service = M2504Service()
    plugin = M2504Plugin(service)
    token = plugin.validate(TransportSubmission(build_request().model_dump_json()))
    direct = service.execute(build_request())

    assert plugin.run(token) == direct
