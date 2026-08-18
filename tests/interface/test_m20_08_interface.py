"""FastAPI, Typer, and plugin boundary parity for provisional M20-08."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m20_08 import (
    M2008_MAX_CANONICAL_REQUEST_BYTES,
    M2008_MAX_CANONICAL_RESULT_BYTES,
    HealthSignalStatus,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c20_biomarker_panel.m20_08_translation_monitoring_rollback import (
    M2008Service,
    M2008TranslationMonitoringEngine,
    cli_app,
    create_app,
)
from tests.contract.test_m20_08_hardening import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE_ENTITY = 422


class _RejectingService(M2008Service):
    def validate_request(self, request: object) -> object:
        del request
        raise ValueError

    def execute(self, request: object) -> object:
        del request
        raise ValueError


def test_fastapi_monitor_verify_and_schema_are_canonical() -> None:
    client = TestClient(create_app())
    request = _request()
    document = request.model_dump(mode="json")
    monitored = client.post("/v1/modules/M20-08/monitor", json=document)
    assert monitored.status_code == _HTTP_OK
    result = monitored.json()
    verified = client.post("/v1/modules/M20-08/verify", json={"result": result})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/v1/modules/M20-08/schemas/output")
    assert schema.status_code == _HTTP_OK
    assert schema.json()["x-glio-contract"]["upstreamInputMediaType"].endswith("m20-07+json")


def test_fastapi_sanitizes_unknown_schema_and_invalid_request() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M20-08/schemas/unknown").status_code == _HTTP_NOT_FOUND
    response = client.post("/v1/modules/M20-08/monitor", json={})
    assert response.status_code == _HTTP_UNPROCESSABLE_ENTITY
    assert response.json() == {"detail": "request does not satisfy the M20-08 contract"}


def test_fastapi_parse_once_error_paths_are_sanitized() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M20-08/schemas").status_code == _HTTP_OK
    malformed = client.post("/v1/modules/M20-08/monitor", content=b"{")
    assert malformed.status_code == _HTTP_UNPROCESSABLE_ENTITY
    non_object = client.post("/v1/modules/M20-08/verify", content=b"[]")
    assert non_object.status_code == _HTTP_UNPROCESSABLE_ENTITY
    invalid_envelope = client.post("/v1/modules/M20-08/verify", json={})
    assert invalid_envelope.status_code == _HTTP_UNPROCESSABLE_ENTITY
    malformed_envelope = client.post("/v1/modules/M20-08/verify", content=b"{")
    assert malformed_envelope.status_code == _HTTP_UNPROCESSABLE_ENTITY


def test_fastapi_service_errors_are_sanitized() -> None:
    client = TestClient(create_app(_RejectingService()))
    request = _request().model_dump(mode="json")
    assert (
        client.post("/v1/modules/M20-08/validate", json=request).status_code
        == _HTTP_UNPROCESSABLE_ENTITY
    )
    assert (
        client.post("/v1/modules/M20-08/monitor", json=request).status_code
        == _HTTP_UNPROCESSABLE_ENTITY
    )


def test_fastapi_validate_route_accepts_strict_request() -> None:
    client = TestClient(create_app())
    response = client.post("/v1/modules/M20-08/validate", json=_request().model_dump(mode="json"))
    assert response.status_code == _HTTP_OK
    assert response.json()["operation"] == "monitor_protein_subtype_translation_health"


def test_typer_monitor_verify_and_no_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))
    monitored = runner.invoke(cli_app, ["monitor", str(request_path)])
    assert monitored.exit_code == 0, monitored.stdout
    result_document = json.loads(monitored.stdout)
    result_path = tmp_path / "result.json"
    result_path.write_bytes(canonical_json_bytes(result_document))
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0, verified.stdout
    schema_path = tmp_path / "schema.json"
    first = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    second = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert first.exit_code == 0
    assert second.exit_code != 0


def test_typer_validate_stdout_schema_stdout_and_output_file(tmp_path: Path) -> None:
    runner = CliRunner()
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    schema = runner.invoke(cli_app, ["export-schema", "signal"])
    output_path = tmp_path / "result-output.json"
    monitored = runner.invoke(cli_app, ["monitor", str(request_path), "--output", str(output_path)])
    assert validated.exit_code == 0
    assert schema.exit_code == 0
    assert '"$schema"' in schema.stdout
    assert monitored.exit_code == 0
    assert output_path.exists()


def test_typer_abstention_and_malformed_request_are_safe(tmp_path: Path) -> None:
    runner = CliRunner()
    request = _request()
    signal = request.signals[0].model_copy(
        update={
            "status": HealthSignalStatus.NOT_EVALUABLE,
            "lower_bound": None,
            "upper_bound": None,
        }
    )
    abstained_path = tmp_path / "abstained.json"
    abstained_path.write_bytes(
        canonical_json_bytes(
            request.model_copy(update={"signals": (signal,)}).model_dump(mode="json")
        )
    )
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{", encoding="utf-8")
    abstained = runner.invoke(cli_app, ["monitor", str(abstained_path)])
    invalid = runner.invoke(cli_app, ["validate", str(malformed_path)])
    assert abstained.exit_code == 1
    assert invalid.exit_code != 0


def test_typer_rejects_bad_result(tmp_path: Path) -> None:
    runner = CliRunner()
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    result = runner.invoke(cli_app, ["verify", str(bad)])
    assert result.exit_code != 0
    assert M2008TranslationMonitoringEngine().infer(_request()).result_digest


def test_typer_rejects_oversized_request_and_result_before_parse(tmp_path: Path) -> None:
    request_path = tmp_path / "oversized-request.json"
    result_path = tmp_path / "oversized-result.json"
    for path, limit in (
        (request_path, M2008_MAX_CANONICAL_REQUEST_BYTES),
        (result_path, M2008_MAX_CANONICAL_RESULT_BYTES),
    ):
        with path.open("wb") as stream:
            stream.seek(limit)
            stream.write(b"{}")
    runner = CliRunner()
    request_failure = runner.invoke(cli_app, ["validate", str(request_path)])
    result_failure = runner.invoke(cli_app, ["verify", str(result_path)])
    assert request_failure.exit_code != 0
    assert result_failure.exit_code != 0
    assert "Traceback" not in request_failure.output + result_failure.output
