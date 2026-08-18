"""Substantive M27-05 validator, replay, API, CLI, and capability coverage."""

from __future__ import annotations

from math import inf
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from pathlib import Path

    from glio_proteogen.kernel.models import EvidenceReference

import pytest
from evals.m27_05.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m27_05 import (
    AlertRecord,
    AlertSeverity,
    AlertState,
    DashboardDefinition,
    EmitProteomicsTelemetryRequest,
    ProteomicsTelemetryResult,
    TelemetryFinding,
    TelemetryFindingCode,
    TelemetrySample,
    TelemetryStream,
    TelemetryUnit,
    contract_json_schemas,
)
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry import (
    M2705AuthorizationError,
    M2705Plugin,
    M2705ReplayError,
    M2705Service,
    M2705TelemetryEngine,
    TelemetrySubmission,
    create_app,
)
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry import (
    cli as cli_module,
)
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry.cli import app
from glio_proteogen.modules.c27_complex_activity.m27_05_observability_telemetry.plugin import (
    M2705TokenError,
)

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422
_SCHEMA_COUNT = 8


def _evidence(request: EmitProteomicsTelemetryRequest) -> tuple[EvidenceReference, ...]:
    return request.dashboard_definitions[0].evidence or ()


def test_schema_single_routes_and_api_validation_replay() -> None:
    request = build_request()
    client = TestClient(create_app())
    assert client.get("/v1/modules/M27-05/schemas/request").status_code == _HTTP_OK
    assert client.get("/v1/modules/M27-05/schemas/unknown").status_code == _HTTP_NOT_FOUND
    body = request.model_dump_json()
    assert client.post("/v1/modules/M27-05/validate", content=body).status_code == _HTTP_OK
    result = M2705Service().emit(request)
    verified = client.post("/v1/modules/M27-05/verify", content=result.model_dump_json())
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert (
        client.post("/v1/modules/M27-05/verify", content=b"[]").status_code
        == _HTTP_UNPROCESSABLE
    )


def test_api_validation_and_emit_sanitize_denied_controls() -> None:
    request = build_request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "consent": request.context.references.consent.model_copy(
                        update={"state": "withheld"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    response = TestClient(create_app()).post(
        "/v1/modules/M27-05/emit", content=denied.model_dump_json()
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert "private" not in response.text.lower()


def test_cli_schema_validate_verify_and_output_guards(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request = build_request()
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["export-schema", "request"]).exit_code == 0
    assert runner.invoke(app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(app, ["validate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["emit", str(request_path), "--output", str(result_path)]).exit_code == 0
    )
    assert runner.invoke(app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(app, ["emit", str(request_path), "--output", str(result_path)]).exit_code != 0
    )
    schema_path = tmp_path / "schema.json"
    assert (
        runner.invoke(app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        == 0
    )
    assert schema_path.exists()


def test_cli_rejects_invalid_request_and_reports_safe_abstention(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")
    invalid = runner.invoke(app, ["validate", str(invalid_path)])
    assert invalid.exit_code != 0
    unsupported_path = tmp_path / "unsupported.json"
    unsupported_path.write_text(
        build_request(upstream_media_type="application/json").model_dump_json(),
        encoding="utf-8",
    )
    abstained = runner.invoke(app, ["emit", str(unsupported_path)])
    assert abstained.exit_code == 1
    assert '"status":"abstained"' in abstained.stdout


def test_api_validation_denial_and_service_descriptor() -> None:
    request = build_request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    denied = request.model_copy(update={"context": denied_context})
    response = TestClient(create_app()).post(
        "/v1/modules/M27-05/validate", content=denied.model_dump_json()
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    descriptor = M2705Service().descriptor
    assert descriptor["module_id"] == "GLIO-PROTEOGEN-M27-05"


def test_plugin_rejects_invalid_submission_and_seal_tamper() -> None:
    plugin = M2705Plugin()
    with pytest.raises(M2705TokenError, match=r"validated"):
        plugin.validate(object())  # type: ignore[arg-type]
    token = plugin.validate(TelemetrySubmission(build_request()))
    object.__setattr__(token, "_seal", object())
    with pytest.raises(M2705TokenError, match=r"validated"):
        plugin.run(token)


def test_replay_rejects_digest_and_request_identity_tampering() -> None:
    service = M2705Service()
    result = service.emit(build_request())
    forged_digest = result.model_copy(update={"request_digest": "sha256:forged"})
    with pytest.raises(ValueError, match=r".+"):
        service.replay(forged_digest)
    forged_result = result.model_copy(update={"result_digest": "sha256:forged"})
    with pytest.raises(ValueError, match=r".+"):
        service.replay(forged_result)


def test_cli_rejects_invalid_result_and_denied_emit(tmp_path: Path) -> None:
    runner = CliRunner()
    invalid_result = tmp_path / "invalid-result.json"
    invalid_result.write_text("{}", encoding="utf-8")
    assert runner.invoke(app, ["verify", str(invalid_result)]).exit_code != 0

    request = build_request()
    denied_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    denied_path = tmp_path / "denied.json"
    denied_path.write_text(
        request.model_copy(update={"context": denied_context}).model_dump_json(),
        encoding="utf-8",
    )
    assert runner.invoke(app, ["emit", str(denied_path)]).exit_code != 0
    assert runner.invoke(app, ["validate", str(denied_path)]).exit_code != 0


def test_cli_verify_replay_failure_and_false_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = build_request()
    result = M2705Service().emit(request)
    result_path = tmp_path / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")

    class ReplayFailure:
        def replay(self, candidate: object) -> ProteomicsTelemetryResult:
            del candidate
            raise ValueError("replay failed")  # noqa: TRY003

    monkeypatch.setattr(cli_module, "_SERVICE", ReplayFailure())
    assert CliRunner().invoke(app, ["verify", str(result_path)]).exit_code != 0

    class FalseVerification:
        def replay(self, candidate: object) -> ProteomicsTelemetryResult:
            assert isinstance(candidate, ProteomicsTelemetryResult)
            return candidate.model_copy(update={"result_digest": "sha256:forged"})

    monkeypatch.setattr(cli_module, "_SERVICE", FalseVerification())
    assert CliRunner().invoke(app, ["verify", str(result_path)]).exit_code == 1


def test_engine_replay_rejects_all_digest_closure_paths() -> None:
    engine = M2705TelemetryEngine()
    result = engine.emit(build_request())
    with pytest.raises(M2705ReplayError):
        engine.replay(result.model_copy(update={"request_digest": "sha256:forged"}))
    with pytest.raises(M2705ReplayError):
        engine.replay(result.model_copy(update={"result_id": "m2705.result.forged"}))
    with pytest.raises(M2705ReplayError):
        engine.replay(result.model_copy(update={"result_digest": "sha256:forged"}))


def test_request_and_stream_identity_closures_are_explicit() -> None:
    request = build_request()
    payload = request.model_dump(mode="json")
    payload["requested_metrics"] = ["input_quality", "input_quality"]
    with pytest.raises(ValueError, match=r".+"):
        EmitProteomicsTelemetryRequest.model_validate(payload, strict=True)
    payload = request.model_dump(mode="json")
    dashboard = payload["dashboard_definitions"][0]
    payload["dashboard_definitions"] = [dashboard, dashboard]
    with pytest.raises(ValueError, match=r".+"):
        EmitProteomicsTelemetryRequest.model_validate(payload, strict=True)


def test_engine_accepts_mapping_and_json_bytes() -> None:
    request = build_request()
    engine = M2705TelemetryEngine()
    service = M2705Service()
    assert engine.emit(request.model_dump(mode="json")).status.value == "emitted"
    assert service.emit(request.model_dump_json()).status.value == "emitted"


def test_preflight_hostile_object_fails_closed() -> None:
    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("should be sanitized")  # noqa: TRY003

    with pytest.raises(M2705AuthorizationError):
        M2705TelemetryEngine().emit(Hostile())


def test_plugin_bytes_and_foreign_token_rejection() -> None:
    request = build_request()
    first = M2705Plugin()
    second = M2705Plugin()
    token = first.validate(TelemetrySubmission(request.model_dump_json()))
    assert first.run(token).status.value == "emitted"
    with pytest.raises(TypeError):
        second.run(token)


def test_service_mapping_and_bytes_replay() -> None:
    request = build_request()
    service = M2705Service()
    result = service.emit(request.model_dump(mode="json"))
    assert service.replay(result.model_dump(mode="json")) == result
    assert service.replay(result.model_dump_json()) == result


def test_contract_rejects_duplicate_dashboard_and_metric_ids() -> None:
    request = build_request()
    with pytest.raises(ValueError, match=r".+"):
        DashboardDefinition(
            dashboard_id="m2705.duplicate",
            title="duplicate",
            metrics=(request.requested_metrics[0], request.requested_metrics[0]),
            owner="test",
            refresh_seconds=1,
        )
    payload = request.model_dump(mode="json")
    payload["requested_metrics"] = ["input_quality", "input_quality"]
    with pytest.raises(ValueError, match=r".+"):
        type(request).model_validate(payload, strict=True)


def test_contract_rejects_nonfinite_alert_and_bad_chronology() -> None:
    request = build_request()
    evidence = _evidence(request)
    with pytest.raises(ValueError, match=r".+"):
        TelemetrySample(
            sample_id="m2705.invalid",
            metric=request.requested_metrics[0],
            value=inf,
            unit=TelemetryUnit.SCORE,
            observed_at=request.context.occurred_at,
            source="test",
            evidence=evidence,
        )
    with pytest.raises(ValueError, match=r".+"):
        AlertRecord(
            alert_id="m2705.invalid-alert",
            state=AlertState.CLEAR,
            severity=AlertSeverity.INFO,
            metric=request.requested_metrics[0],
            message="bad chronology",
            triggered_at=request.context.occurred_at,
            resolved_at=request.context.occurred_at.replace(year=2025),
            evidence=evidence,
        )


def test_contract_rejects_duplicate_stream_samples_and_findings() -> None:
    request = build_request()
    result = M2705Service().emit(request)
    assert result.telemetry_stream is not None
    stream_payload = result.telemetry_stream.model_dump(mode="json")
    sample = stream_payload["samples"][0]
    stream_payload["samples"] = [sample, sample]
    with pytest.raises(ValueError, match=r".+"):
        TelemetryStream.model_validate(stream_payload, strict=True)
    finding = TelemetryFinding(
        finding_id="m2705.finding.duplicate",
        code=TelemetryFindingCode.DRIFT_DETECTED,
        message="drift",
    )
    finding_payload = result.telemetry_stream.model_dump(mode="json")
    finding_payload["findings"] = [finding.model_dump(mode="json"), finding.model_dump(mode="json")]
    with pytest.raises(ValueError, match=r".+"):
        TelemetryStream.model_validate(finding_payload, strict=True)


def test_result_id_and_status_shape_are_closed() -> None:
    result = M2705Service().emit(build_request())
    payload = result.model_dump(mode="json")
    payload["result_id"] = "m2705.result.forged"
    with pytest.raises(ValueError, match=r".+"):
        ProteomicsTelemetryResult.model_validate(payload, strict=True)
    payload = result.model_dump(mode="json")
    payload["status"] = "abstained"
    payload["telemetry_stream"] = None
    payload["dashboards"] = []
    payload["alert"] = None
    payload["safe_failure_report"] = None
    with pytest.raises(ValueError, match=r".+"):
        ProteomicsTelemetryResult.model_validate(payload, strict=True)


def test_schema_metadata_is_closed() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    for schema in schemas.values():
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["unsupportedToNegative"] is False
        assert metadata["provisionalAbi"] is True
