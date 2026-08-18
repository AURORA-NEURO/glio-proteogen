"""FastAPI, Typer, and strict boundary parity for provisional M22-04."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - Typer resolves runtime path annotations.
from types import SimpleNamespace
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_04_external_transport_evaluator import (
    M2204Service,
    cli_app,
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m22_04_external_transport_evaluator import (
    cli as cli_module,
)
from tests.runtime.test_m2204_transport import _request

if TYPE_CHECKING:
    import pytest

    from glio_proteogen.contracts.m22_04 import (
        EvaluateProteinRnaDiscordanceExternalTransportRequest,
        ProteinRnaDiscordanceExternalTransportResult,
    )

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_UPSTREAM_COUNT = 2


def test_fastapi_evaluate_verify_and_schema_are_canonical() -> None:
    client = TestClient(create_app())
    request = _request()
    evaluated = client.post("/v1/modules/M22-04/evaluate", json=request.model_dump(mode="json"))
    assert evaluated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M22-04/verify", json={"result": evaluated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    schema = client.get("/v1/modules/M22-04/schemas/output")
    assert schema.status_code == _HTTP_OK
    metadata = schema.json()["x-glio-contract"]
    assert metadata["parentTarget"] == "protein-RNA discordance"
    assert len(metadata["upstreamInputMediaTypes"]) == _UPSTREAM_COUNT


def test_fastapi_parse_once_and_validation_errors_are_sanitized() -> None:
    client = TestClient(create_app(M2204Service()))
    assert client.get("/v1/modules/M22-04/schemas").status_code == _HTTP_OK
    assert client.get("/v1/modules/M22-04/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert client.post("/v1/modules/M22-04/evaluate", json={}).status_code == _HTTP_UNPROCESSABLE
    malformed = client.post("/v1/modules/M22-04/evaluate", content=b"{")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    non_object = client.post("/v1/modules/M22-04/verify", content=b"[]")
    assert non_object.status_code == _HTTP_UNPROCESSABLE
    malformed_envelope = client.post("/v1/modules/M22-04/verify", content=b"{")
    assert malformed_envelope.status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M22-04/verify", json={}).status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


class _RejectingService(M2204Service):
    def validate_request(
        self, request: object
    ) -> EvaluateProteinRnaDiscordanceExternalTransportRequest:
        del request
        raise ValueError

    def evaluate(self, request: object) -> ProteinRnaDiscordanceExternalTransportResult:
        del request
        raise ValueError


def test_fastapi_service_errors_are_sanitized() -> None:
    client = TestClient(create_app(_RejectingService()))
    request = _request().model_dump(mode="json")
    assert (
        client.post("/v1/modules/M22-04/validate", json=request).status_code == _HTTP_UNPROCESSABLE
    )
    assert (
        client.post("/v1/modules/M22-04/evaluate", json=request).status_code == _HTTP_UNPROCESSABLE
    )


def test_typer_evaluate_verify_schema_and_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    runner = CliRunner()
    evaluated = runner.invoke(cli_app, ["evaluate", str(request_path)])
    assert evaluated.exit_code == 0, evaluated.stdout
    result_path = tmp_path / "result.json"
    result_path.write_text(evaluated.stdout, encoding="utf-8")
    verified = runner.invoke(cli_app, ["verify", str(result_path)])
    assert verified.exit_code == 0, verified.stdout
    schema_path = tmp_path / "schema.json"
    first = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    second = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert first.exit_code == 0
    assert second.exit_code != 0
    assert json.loads(schema_path.read_text(encoding="utf-8"))["$schema"].endswith("2020-12/schema")


def test_typer_validate_and_rejects_tampered_result(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    runner = CliRunner()
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    evaluated = runner.invoke(cli_app, ["evaluate", str(request_path)])
    document = json.loads(evaluated.stdout)
    document["result_digest"] = "sha256:" + "f" * 64
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(canonical_json_bytes(document))
    assert runner.invoke(cli_app, ["verify", str(tampered)]).exit_code != 0


def test_typer_error_paths_and_replay_boolean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    assert runner.invoke(cli_app, ["export-schema", "report"]).exit_code == 0
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"{")
    assert runner.invoke(cli_app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(cli_app, ["evaluate", str(bad_request)]).exit_code != 0
    evaluated = runner.invoke(cli_app, ["evaluate", str(request_path)])
    result_path = tmp_path / "result.json"
    result_path.write_text(evaluated.stdout, encoding="utf-8")
    output_path = tmp_path / "result-output.json"
    assert (
        runner.invoke(
            cli_app, ["evaluate", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"{}")
    assert runner.invoke(cli_app, ["verify", str(bad_result)]).exit_code != 0

    class FailingService:
        def replay(self, result: object) -> object:
            del result
            raise ValueError

    monkeypatch.setattr(cli_module, "_SERVICE", FailingService())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0

    class MismatchService:
        def replay(self, result: object) -> object:
            del result
            return SimpleNamespace(result_digest="sha256:" + "0" * 64)

    monkeypatch.setattr(cli_module, "_SERVICE", MismatchService())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code == 1


def test_typer_evaluate_denied_controls_abstains_or_rejects(tmp_path: Path) -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    denied = request.model_copy(update={"context": context})
    path = tmp_path / "denied.json"
    path.write_bytes(canonical_json_bytes(denied))
    assert CliRunner().invoke(cli_app, ["evaluate", str(path)]).exit_code != 0
