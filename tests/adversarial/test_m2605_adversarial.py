"""Adversarial boundaries for M26-05 parsing, controls, replay, and interfaces."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_05 import (
    M2605_M2604_INPUT_MEDIA_TYPE,
    TelemetryMetricKind,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry import (
    M2605AuthorizationError,
    M2605ObservabilityEngine,
    M2605Plugin,
    M2605ReplayError,
    TelemetrySubmission,
    api,
    cli,
    emit_proteomics_telemetry,
    preflight_m2605_authorization,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry.service import (
    M2605ObservabilityService,
)
from tests.runtime.test_m26_05_runtime import _request

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

_UNPROCESSABLE = HTTPStatus.UNPROCESSABLE_ENTITY


def test_plugin_rejects_duplicate_and_nonfinite_json() -> None:
    plugin = M2605Plugin()
    with pytest.raises(StrictJsonError) as duplicate:
        plugin.validate(TelemetrySubmission('{"request_id":"a","request_id":"b"}'))
    assert duplicate.value.code is StrictJsonErrorCode.DUPLICATE_KEY
    with pytest.raises(StrictJsonError) as nonfinite:
        plugin.validate(TelemetrySubmission('{"value":NaN}'))
    assert nonfinite.value.code is StrictJsonErrorCode.NONFINITE_NUMBER


def test_plugin_rejects_oversized_and_cross_plugin_tokens() -> None:
    plugin = M2605Plugin()
    with pytest.raises(StrictJsonError) as oversized:
        plugin.validate(TelemetrySubmission(" " * (4 * 1024 * 1024 + 1)))
    assert oversized.value.code is StrictJsonErrorCode.TOO_LARGE
    token = plugin.validate(TelemetrySubmission(_request().model_dump_json()))
    with pytest.raises(TypeError):
        M2605Plugin().run(token)


def test_preflight_fails_closed_for_hostile_mapping() -> None:
    class HostileMapping(dict[str, object]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError(key)

    with pytest.raises(M2605AuthorizationError):
        preflight_m2605_authorization(HostileMapping())


def test_engine_and_public_entrypoint_reject_wrong_media_type() -> None:
    request = _request()
    wrong = request.model_copy(
        update={
            "upstream_result": request.upstream_result.model_copy(
                update={"media_type": "text/plain"}
            )
        }
    )
    with pytest.raises(ValidationError):
        M2605ObservabilityEngine().emit(wrong)
    with pytest.raises(ValidationError):
        emit_proteomics_telemetry(wrong)
    assert request.upstream_result.media_type == M2605_M2604_INPUT_MEDIA_TYPE


def test_api_rejects_nonobject_and_bad_request_json() -> None:
    client = TestClient(api.create_m2605_app())
    nonobject = client.post("/v1/modules/M26-05/validate", json=["bad"])
    malformed = client.post(
        "/v1/modules/M26-05/validate",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )
    assert nonobject.status_code == _UNPROCESSABLE
    assert malformed.status_code == _UNPROCESSABLE
    assert "not-json" not in malformed.text


def test_api_verify_rejects_tamper_and_unknown_result_envelope() -> None:
    client = TestClient(api.create_m2605_app())
    result = M2605ObservabilityEngine().emit(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    rejected = client.post("/v1/modules/M26-05/verify", json=tampered.model_dump(mode="json"))
    unknown = client.post("/v1/modules/M26-05/verify", json={"result": {"unknown": True}})
    assert rejected.status_code == _UNPROCESSABLE
    assert unknown.status_code == _UNPROCESSABLE


def test_cli_abstention_is_nonzero_and_writes_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    missing = request.model_copy(
        update={
            "requested_metrics": (*request.requested_metrics, TelemetryMetricKind.REVIEWER_ACTIONS)
        }
    )
    input_path = tmp_path / "missing.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(missing.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    first = runner.invoke(cli.app, ["emit", str(input_path), "--output", str(output_path)])
    second = runner.invoke(cli.app, ["emit", str(input_path), "--output", str(output_path)])
    assert first.exit_code == 3  # noqa: PLR2004 - CLI abstention contract.
    assert output_path.exists()
    assert second.exit_code != 0
    assert "already exists" in second.output
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "abstained"


def test_cli_invalid_replay_is_sanitized(tmp_path: Path) -> None:
    path = tmp_path / "tampered.json"
    result = M2605ObservabilityEngine().emit(_request())
    path.write_text(
        json.dumps(result.model_dump(mode="json") | {"result_digest": "sha256:" + "1" * 64}),
        encoding="utf-8",
    )
    invoked = CliRunner().invoke(cli.app, ["verify", str(path)])
    assert invoked.exit_code != 0
    assert "valid M26-05 result" in invoked.output


def test_service_verify_rejects_plain_object_and_replay_error() -> None:
    with pytest.raises(M2605ReplayError):
        M2605ObservabilityService.verify({"result_digest": "sha256:" + "0" * 64})


def test_api_schema_contract_names_are_closed() -> None:
    client = TestClient(api.create_m2605_app())
    response = client.get("/v1/modules/M26-05/schemas/not-a-contract")
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_mapping_protocol_does_not_leak_submitted_values() -> None:
    request = _request()
    mapping: Mapping[str, object] = request.model_dump(mode="python")
    assert "m2605.runtime.actor" in str(mapping)
    # The public API rejects malformed mappings without echoing submitted fields.
    response = TestClient(api.create_m2605_app()).post(
        "/v1/modules/M26-05/emit", content=b'{"actor":"private","unknown":true}'
    )
    assert response.status_code in {403, 422}
    assert "private" not in response.text
