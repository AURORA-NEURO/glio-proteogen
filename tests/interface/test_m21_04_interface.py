"""FastAPI, Typer, and plugin boundary parity for provisional M21-04."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material.m21_04_external_transport_evaluator import (
    M2104Service,
    cli_app,
    create_app,
)
from tests.contract.test_m21_04_hardening import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE_ENTITY = 422


class _RejectingService(M2104Service):
    def validate_request(self, request: object) -> object:
        del request
        raise ValueError

    def evaluate(self, request: object) -> object:
        del request
        raise ValueError


def test_fastapi_evaluate_verify_and_schema_are_canonical() -> None:
    client = TestClient(create_app())
    request = _request()
    evaluated = client.post("/v1/modules/M21-04/evaluate", json=request.model_dump(mode="json"))
    assert evaluated.status_code == _HTTP_OK
    result = evaluated.json()
    verified = client.post("/v1/modules/M21-04/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/v1/modules/M21-04/schemas/output")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["upstreamInputMediaType"].endswith("m21-03+json")


def test_fastapi_sanitizes_unknown_schema_and_invalid_request() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M21-04/schemas/unknown").status_code == _HTTP_NOT_FOUND
    response = client.post("/v1/modules/M21-04/evaluate", json={})
    assert response.status_code == _HTTP_UNPROCESSABLE_ENTITY
    assert response.json() == {"detail": "request does not satisfy the M21-04 contract"}


def test_fastapi_parse_once_error_paths_are_sanitized() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M21-04/schemas").status_code == _HTTP_OK
    malformed = client.post("/v1/modules/M21-04/evaluate", content=b"{")
    assert malformed.status_code == _HTTP_UNPROCESSABLE_ENTITY
    non_object = client.post("/v1/modules/M21-04/verify", content=b"[]")
    assert non_object.status_code == _HTTP_UNPROCESSABLE_ENTITY
    invalid_envelope = client.post("/v1/modules/M21-04/verify", json={})
    assert invalid_envelope.status_code == _HTTP_UNPROCESSABLE_ENTITY
    malformed_envelope = client.post("/v1/modules/M21-04/verify", content=b"{")
    assert malformed_envelope.status_code == _HTTP_UNPROCESSABLE_ENTITY


def test_fastapi_service_errors_are_sanitized() -> None:
    client = TestClient(create_app(_RejectingService()))
    request = _request().model_dump(mode="json")
    assert (
        client.post("/v1/modules/M21-04/validate", json=request).status_code
        == _HTTP_UNPROCESSABLE_ENTITY
    )
    assert (
        client.post("/v1/modules/M21-04/evaluate", json=request).status_code
        == _HTTP_UNPROCESSABLE_ENTITY
    )


def test_fastapi_validate_route_accepts_strict_request() -> None:
    client = TestClient(create_app())
    response = client.post("/v1/modules/M21-04/validate", json=_request().model_dump(mode="json"))
    assert response.status_code == _HTTP_OK
    assert response.json()["operation"] == "evaluate_complex_activity_external_transport"


def test_typer_evaluate_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))
    evaluated = runner.invoke(cli_app, ["evaluate", str(request_path)])
    assert evaluated.exit_code == 0, evaluated.stdout
    result_document = json.loads(evaluated.stdout)
    result_path = tmp_path / "result.json"
    result_path.write_bytes(canonical_json_bytes(result_document))
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0, verified.stdout
    schema_path = tmp_path / "schema.json"
    first = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    second = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert first.exit_code == 0
    assert second.exit_code != 0


def test_typer_validate_schema_stdout_and_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    schema = runner.invoke(cli_app, ["export-schema", "report"])
    output_path = tmp_path / "result-output.json"
    evaluated = runner.invoke(
        cli_app, ["evaluate", str(request_path), "--output", str(output_path)]
    )
    assert validated.exit_code == 0
    assert schema.exit_code == 0
    assert '"$schema"' in schema.stdout
    assert evaluated.exit_code == 0
    assert output_path.exists()


def test_typer_rejects_malformed_request_and_bad_result(tmp_path: Path) -> None:
    runner = CliRunner()
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    invalid = runner.invoke(cli_app, ["validate", str(malformed)])
    assert invalid.exit_code != 0
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    result = runner.invoke(cli_app, ["verify", str(bad)])
    assert result.exit_code != 0
