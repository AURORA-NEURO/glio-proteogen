"""Adversarial boundaries for M26-05 parsing, controls, replay, and interfaces."""

from __future__ import annotations

import json
from http import HTTPStatus
from importlib import import_module
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m26_05 import (
    M2605_M2604_INPUT_MEDIA_TYPE,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    TelemetryMetricKind,
    TelemetryUnit,
)
from glio_proteogen.contracts.m26_05.canonical import result_payload_digest
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
    verify_telemetry_result,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry.plugin import (
    ValidatedM2605Request,
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
    object_submission = plugin.validate(TelemetrySubmission(_request()))
    object.__setattr__(object_submission, "_seal", object())
    with pytest.raises(TypeError):
        plugin.run(object_submission)
    assert isinstance(object_submission, ValidatedM2605Request)


def test_plugin_rejects_nested_request_mutation() -> None:
    plugin = M2605Plugin()
    token = plugin.validate(TelemetrySubmission(_request()))
    object.__setattr__(token.request, "request_id", "m2605.tampered")
    with pytest.raises(TypeError, match="validated"):
        plugin.run(token)


def test_preflight_fails_closed_for_hostile_mapping() -> None:
    class HostileMapping:
        @property
        def context(self) -> object:
            raise RuntimeError("hostile context")  # noqa: TRY003

    with pytest.raises(M2605AuthorizationError):
        preflight_m2605_authorization(HostileMapping())
    with pytest.raises(M2605AuthorizationError):
        preflight_m2605_authorization({})


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


def _self_rehashed_result(
    result: ProteomicsTelemetryResult, updates: dict[str, object]
) -> ProteomicsTelemetryResult:
    forged = result.model_copy(update=updates)
    return type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result_payload_digest(forged)}
    )


def test_self_rehashed_telemetry_mutation_is_rejected_by_all_replay_seams() -> None:
    result = M2605ObservabilityEngine().emit(_request())
    assert result.telemetry_stream is not None
    sample = result.telemetry_stream.samples[0].model_copy(update={"value": 0.42})
    forged = _self_rehashed_result(
        result,
        {
            "telemetry_stream": result.telemetry_stream.model_copy(
                update={"samples": (sample, *result.telemetry_stream.samples[1:])}
            )
        },
    )
    with pytest.raises(M2605ReplayError):
        verify_telemetry_result(forged)
    with pytest.raises(M2605ReplayError):
        M2605ObservabilityService.verify(forged)
    with pytest.raises(M2605ReplayError):
        M2605Plugin().replay(forged)


def test_emitted_result_rejects_self_rehashed_unrequested_metric() -> None:
    result = M2605ObservabilityEngine().emit(_request())
    assert result.telemetry_stream is not None
    extra = result.telemetry_stream.samples[-1].model_copy(
        update={
            "sample_id": "m2605.unrequested.reviewer-actions",
            "metric": TelemetryMetricKind.REVIEWER_ACTIONS,
            "unit": TelemetryUnit.COUNT,
        }
    )
    stream = result.telemetry_stream.model_copy(
        update={"samples": (*result.telemetry_stream.samples, extra)}
    )
    forged = _self_rehashed_result(result, {"telemetry_stream": stream})

    with pytest.raises(ValidationError, match="exactly requested metrics"):
        ProteomicsTelemetryResult.model_validate(forged.model_dump(mode="python"))


def test_request_rejects_unrequested_metric_sample() -> None:
    request = _request()
    extra = request.samples[-1].model_copy(
        update={
            "sample_id": "m2605.unrequested.reviewer-actions",
            "metric": TelemetryMetricKind.REVIEWER_ACTIONS,
            "unit": TelemetryUnit.COUNT,
        }
    )

    with pytest.raises(ValidationError, match="only requested metrics"):
        EmitProteomicsTelemetryRequest.model_validate(
            request.model_copy(update={"samples": (*request.samples, extra)}).model_dump(
                mode="python"
            )
        )


def test_api_and_cli_reject_self_rehashed_telemetry_mutation(tmp_path: Path) -> None:
    result = M2605ObservabilityEngine().emit(_request())
    assert result.telemetry_stream is not None
    finding = result.telemetry_stream.findings[0].model_copy(update={"message": "forged"})
    forged = _self_rehashed_result(
        result,
        {
            "telemetry_stream": result.telemetry_stream.model_copy(
                update={"findings": (finding, *result.telemetry_stream.findings[1:])}
            )
        },
    )
    response = TestClient(api.create_m2605_app()).post(
        "/v1/modules/M26-05/verify", json=forged.model_dump(mode="json")
    )
    assert response.status_code == _UNPROCESSABLE
    result_path = tmp_path / "forged.json"
    result_path.write_text(forged.model_dump_json(), encoding="utf-8")
    invoked = CliRunner().invoke(cli.app, ["verify", str(result_path)])
    assert invoked.exit_code != 0
    assert "replay is invalid" in invoked.output


def test_api_sanitizes_service_validation_errors() -> None:
    class FailingService:
        def validate_request(self, _request: object) -> object:
            raise ValueError("private validation detail")  # noqa: TRY003

        def execute(self, _request: object) -> object:
            raise ValueError("private execution detail")  # noqa: TRY003

    payload = _request().model_dump_json()
    client = TestClient(api.create_m2605_app(FailingService()))  # type: ignore[arg-type]
    validation = client.post("/v1/modules/M26-05/validate", content=payload)
    emission = client.post("/v1/modules/M26-05/emit", content=payload)
    assert validation.status_code == _UNPROCESSABLE
    assert emission.status_code == _UNPROCESSABLE
    assert "private" not in validation.text + emission.text


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
    schema_stdout = runner.invoke(cli.app, ["export-schema", "request"])
    first = runner.invoke(cli.app, ["emit", str(input_path), "--output", str(output_path)])
    second = runner.invoke(cli.app, ["emit", str(input_path), "--output", str(output_path)])
    assert first.exit_code == 3  # noqa: PLR2004 - CLI abstention contract.
    assert schema_stdout.exit_code == 0
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


def test_cli_emit_rejects_failed_authorization(tmp_path: Path) -> None:
    request = _request()
    quality = request.context.references.quality.model_copy(update={"state": "rejected"})
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(update={"quality": quality})
                }
            )
        }
    )
    path = tmp_path / "denied.json"
    path.write_text(denied.model_dump_json(), encoding="utf-8")
    invoked = CliRunner().invoke(cli.app, ["emit", str(path)])
    validated = CliRunner().invoke(cli.app, ["validate", str(path)])
    assert invoked.exit_code != 0
    assert "telemetry service" in invoked.output
    assert validated.exit_code != 0


def test_cli_sanitizes_service_emit_and_verify_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(_request().model_dump_json(), encoding="utf-8")
    result_path = tmp_path / "result.json"
    result = M2605ObservabilityEngine().emit(_request())
    result_path.write_text(result.model_dump_json(), encoding="utf-8")

    class FailingService:
        def execute(self, _request: object) -> object:
            raise ValueError("private execution detail")  # noqa: TRY003

        def verify(self, _candidate: object) -> object:
            raise M2605ReplayError

    monkeypatch.setattr(cli, "_SERVICE", FailingService())
    emitted = CliRunner().invoke(cli.app, ["emit", str(request_path)])
    verified = CliRunner().invoke(cli.app, ["verify", str(result_path)])
    assert emitted.exit_code != 0
    assert verified.exit_code != 0
    assert "private" not in emitted.output
    assert "replay is invalid" in verified.output


def test_service_verify_rejects_plain_object_and_replay_error() -> None:
    with pytest.raises(M2605ReplayError):
        M2605ObservabilityService.verify({"result_digest": "sha256:" + "0" * 64})


def test_replay_defensive_digest_and_stream_closures(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime_engine = import_module(
        "glio_proteogen.modules.c20_biomarker_panel.m26_05_observability_telemetry.engine"
    )
    result = M2605ObservabilityEngine().emit(_request())

    class PassthroughAdapter:
        def validate_python(self, candidate: object, *, strict: bool) -> object:  # noqa: ARG002
            return candidate

    monkeypatch.setattr(runtime_engine, "_RESULT_ADAPTER", PassthroughAdapter())
    monkeypatch.setattr(runtime_engine, "canonical_request_digest", lambda _: "sha256:" + "0" * 64)
    with pytest.raises(M2605ReplayError):
        runtime_engine.verify_telemetry_result(result)

    monkeypatch.setattr(runtime_engine, "canonical_request_digest", lambda _: result.request_digest)
    monkeypatch.setattr(runtime_engine, "result_payload_digest", lambda _: "sha256:" + "0" * 64)
    with pytest.raises(M2605ReplayError):
        runtime_engine.verify_telemetry_result(result)

    monkeypatch.setattr(runtime_engine, "result_payload_digest", lambda _: result.result_digest)
    incomplete = result.model_copy(update={"telemetry_stream": None})
    with pytest.raises(M2605ReplayError):
        runtime_engine.verify_telemetry_result(incomplete)

    class InvalidAdapter:
        def validate_python(self, _candidate: object, *, strict: bool) -> object:  # noqa: ARG002
            TypeAdapter(int).validate_python("invalid", strict=True)
            raise AssertionError("validation unexpectedly succeeded")  # noqa: TRY003

    monkeypatch.setattr(runtime_engine, "_RESULT_ADAPTER", InvalidAdapter())
    with pytest.raises(M2605ReplayError):
        runtime_engine.verify_telemetry_result(result)


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
