"""Adversarial runtime and interface closure for M24-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from evals.m24_04.fixture import denied_request, narrowed_request, not_evaluable_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m24_04 import TransportStatus
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c21_reference_material.m24_04_external_transport_evaluator import (
    ExternalTransportSubmission,
    M2404AuthorizationError,
    M2404Plugin,
    M2404Service,
    cli_app,
    create_app,
    evaluate_biomarker_panel_external_transport,
    preflight_m2404_authorization,
)
from glio_proteogen.modules.c21_reference_material.m24_04_external_transport_evaluator import (
    cli as cli_module,
)
from tests.contract.test_m24_04_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_UNPROCESSABLE = 422
_HTTP_OK = 200


def test_preflight_rejects_non_mapping_and_missing_context() -> None:
    with pytest.raises(M2404AuthorizationError):
        preflight_m2404_authorization(object())
    with pytest.raises(M2404AuthorizationError):
        preflight_m2404_authorization({"context": None})


def test_public_entrypoint_and_json_validation_are_deterministic() -> None:
    request = _request()
    assert evaluate_biomarker_panel_external_transport(request).status.value == "evaluated"
    assert (
        M2404Service().validate_request(request.model_dump_json()).request_id == request.request_id
    )


def test_not_evaluable_and_narrowed_inputs_are_safe_review_paths() -> None:
    service = M2404Service()
    missing = service.generate(not_evaluable_request())
    narrowed = service.generate(narrowed_request())
    assert missing.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert missing.report is None
    assert narrowed.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert narrowed.report is None
    assert narrowed.findings[0].code.value == "calibration_floor_failed"


def test_plugin_strict_json_and_replay_close_capability_boundary() -> None:
    plugin = M2404Plugin(M2404Service())
    token = plugin.validate(ExternalTransportSubmission(request=_request().model_dump_json()))
    result = plugin.run(token)
    assert plugin.replay(result).result_digest == result.result_digest
    with pytest.raises((ValidationError, M2404AuthorizationError)):
        plugin.validate(ExternalTransportSubmission(request=b'{"request_id":null}'))


def test_fastapi_tamper_and_denied_errors_are_sanitized() -> None:
    service = M2404Service()
    client = TestClient(create_app(service))
    result = service.generate(_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "0" * 64
    tampered = client.post("/v1/modules/M24-04/verify", json=result)
    assert tampered.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in tampered.text
    denied = client.post("/v1/modules/M24-04/evaluate", content=denied_request().model_dump_json())
    assert denied.status_code == _HTTP_UNPROCESSABLE
    assert client.get("/v1/modules/M24-04/schemas/request").status_code == _HTTP_OK


def test_typer_abstention_writes_immutable_result_and_returns_nonzero(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(not_evaluable_request().model_dump_json(), encoding="utf-8")
    invoked = CliRunner().invoke(
        cli_app, ["evaluate", str(request_path), "--output", str(result_path)]
    )
    assert invoked.exit_code == 1
    assert result_path.exists()
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "abstained"


def test_typer_sanitizes_denial_unknown_schema_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(denied_request().model_dump_json(), encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["evaluate", str(denied_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    result_path = tmp_path / "result.json"
    result_path.write_text(M2404Service().generate(_request()).model_dump_json(), encoding="utf-8")

    class FakeService:
        def replay(self, result: Any) -> Any:
            return result.model_copy(update={"result_digest": "sha256:" + "0" * 64})

    monkeypatch.setattr(cli_module, "_SERVICE", FakeService())
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0


def test_status_enum_is_not_an_implicit_negative() -> None:
    assert TransportStatus.NOT_EVALUABLE.value == "not_evaluable"


__all__ = []
