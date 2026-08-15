"""Adversarial closure and transport coverage for provisional M10-07."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 - pytest resolves the runtime annotation.

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.contracts.m10_07 import (
    CalibrateProteinRnaDiscordanceSelectivePredictionVerification,
    CalibrationReplayReason,
    ProteinRnaDiscordanceSelectivePredictionResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    BuiltM1007Result,
    M1007AuthorizationError,
    M1007CalibrationEngine,
    M1007InputError,
    M1007Plugin,
    M1007Service,
    M1007TokenError,
    ValidatedM1007Request,
    calibrate_protein_rna_discordance_selective_prediction,
    preflight_m1007_authorization,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    api as m1007_api,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    cli as m1007_cli,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction import (
    engine as m1007_engine,
)
from tests.modules.test_m10_07_runtime import _request

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def _invalid_result_payload(result: object) -> dict[str, object]:
    assert isinstance(result, ProteinRnaDiscordanceSelectivePredictionResult)
    return result.model_dump(mode="json")


def _reject(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        ProteinRnaDiscordanceSelectivePredictionResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_contract_validator_rejects_every_closed_result_escape() -> None:
    request = _request()
    built = M1007CalibrationEngine().execute(request)
    payload = _invalid_result_payload(built.result)

    wrong_request = dict(payload)
    wrong_request["request_digest"] = "sha256:" + ("b" * 64)
    _reject(wrong_request, "request digest")

    missing_estimate = dict(payload)
    missing_estimate["estimate"] = None
    _reject(missing_estimate, "supported, evaluable")

    wrong_coverage = dict(payload)
    wrong_coverage["prediction_set"] = {
        **wrong_coverage["prediction_set"],
        "nominal_coverage": 0.91,
    }
    _reject(wrong_coverage, "nominal 90 percent")

    invalid_abstention = dict(payload)
    invalid_abstention["status"] = "abstained"
    invalid_abstention["abstention_reason"] = "review"
    _reject(invalid_abstention, "no prediction")

    duplicate_diagnostics = dict(payload)
    duplicate_diagnostics["diagnostics"] = [
        payload["diagnostics"][0],
        payload["diagnostics"][0],
    ]
    _reject(duplicate_diagnostics, "diagnostic ids")

    abstained = M1007CalibrationEngine().execute(_request(support_threshold=1.0)).result
    duplicate_findings = _invalid_result_payload(abstained)
    duplicate_findings["findings"] = [
        "support_threshold_not_met",
        "support_threshold_not_met",
    ]
    _reject(duplicate_findings, "findings")

    wrong_digest = dict(payload)
    wrong_digest["result_digest"] = "sha256:" + ("b" * 64)
    _reject(wrong_digest, "result digest")


def test_contract_validator_rejects_bad_binding_and_replay_flags() -> None:
    request_payload = _request().model_dump(mode="json")
    request_payload["uncertainty_result"]["media_type"] = "application/unsupported+json"
    with pytest.raises(ValidationError, match="bind the provisional M10-06"):
        type(_request()).model_validate_json(canonical_json_bytes(request_payload), strict=True)

    digest = "sha256:" + ("a" * 64)
    with pytest.raises(ValidationError, match="content and deterministic"):
        CalibrateProteinRnaDiscordanceSelectivePredictionVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=digest,
            reason=CalibrationReplayReason.VERIFIED,
        )
    with pytest.raises(ValidationError, match="result digest only"):
        CalibrateProteinRnaDiscordanceSelectivePredictionVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=digest,
            reason=CalibrationReplayReason.INVALID_RESULT,
        )
    valid = CalibrateProteinRnaDiscordanceSelectivePredictionVerification(
        content_verified=True,
        deterministic_verified=True,
        verified=True,
        result_digest=digest,
        reason=CalibrationReplayReason.VERIFIED,
    )
    assert valid.verified is True


def test_runtime_edges_wrapper_limits_and_replay_reasons(monkeypatch) -> None:
    request = _request()
    engine = M1007CalibrationEngine()
    built = engine.execute(request)
    assert calibrate_protein_rna_discordance_selective_prediction(request) == built
    assert M1007InputError("other").reason == "other"
    with pytest.raises(M1007AuthorizationError):
        preflight_m1007_authorization(object())
    with pytest.raises(M1007AuthorizationError):
        engine.execute(
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": request.context.references.model_copy(
                                update={
                                    "consent": request.context.references.consent.model_copy(
                                        update={"state": ConsentState.WITHHELD}
                                    )
                                }
                            )
                        }
                    )
                }
            )
        )
    monkeypatch.setattr(m1007_engine, "M1007_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(M1007InputError, match="byte limit"):
        engine.execute(request)
    monkeypatch.setattr(m1007_engine, "M1007_MAX_CANONICAL_RESULT_BYTES", 8 * 1024 * 1024)
    with pytest.raises(M1007InputError, match="digest"):
        BuiltM1007Result(
            result=built.result.model_copy(update={"result_digest": "sha256:" + ("b" * 64)}),
            canonical_bytes=built.canonical_bytes,
        )
    with pytest.raises(M1007InputError, match="canonical"):
        BuiltM1007Result(result=built.result, canonical_bytes=b"{}")
    other = engine.execute(_request(support_threshold=1.0))
    mismatch = engine.verify(other.result, built.canonical_bytes)
    assert mismatch.verified is False
    assert "differs" in mismatch.reason
    invalid = engine.verify({}, built.canonical_bytes)
    assert invalid.verified is False
    assert canonical_request_digest(request) == built.result.request_digest
    assert canonical_request_digest(request.model_dump(mode="json")) == built.result.request_digest
    assert result_payload_digest(built.result) == built.result.result_digest


def test_plugin_descriptor_typed_and_forged_tokens_fail_closed() -> None:
    request = _request()
    plugin = M1007Plugin(M1007Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M10-07"
    typed_token = plugin.validate(request)
    assert plugin.run(typed_token).result.status.value == "calibrated"
    forged = ValidatedM1007Request(request=typed_token.request, _seal=object())
    with pytest.raises(M1007TokenError):
        plugin.run(forged)
    with pytest.raises(M1007TokenError):
        plugin.run(object())  # type: ignore[arg-type]


def test_api_and_cli_reject_transport_edges_and_abstention(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    with TestClient(m1007_api.create_app()) as client:
        assert client.get("/v1/modules/M10-07/schemas").status_code == _HTTP_OK
        assert client.get("/v1/modules/M10-07/schemas/unknown").status_code == _HTTP_NOT_FOUND
        assert (
            client.post("/v1/modules/M10-07/validate", content=b"[]").status_code
            == _HTTP_UNPROCESSABLE
        )
        assert client.post("/v1/modules/M10-07/verify", json={}).status_code == _HTTP_UNPROCESSABLE
        assert (
            client.post("/v1/modules/M10-07/verify", content=b"[]").status_code
            == _HTTP_UNPROCESSABLE
        )
        assert (
            client.post("/v1/modules/M10-07/verify", content=b"{").status_code
            == _HTTP_UNPROCESSABLE
        )
        denied = _request().model_copy(
            update={
                "context": _request().context.model_copy(
                    update={
                        "references": _request().context.references.model_copy(
                            update={
                                "consent": _request().context.references.consent.model_copy(
                                    update={"state": ConsentState.WITHHELD}
                                )
                            }
                        )
                    }
                )
            }
        )
        assert (
            client.post("/v1/modules/M10-07/validate", content=denied.model_dump_json()).status_code
            == _HTTP_UNPROCESSABLE
        )
        assert (
            client.post("/v1/modules/M10-07/execute", content=denied.model_dump_json()).status_code
            == _HTTP_UNPROCESSABLE
        )
    runner = CliRunner()
    assert runner.invoke(m1007_cli.app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(m1007_cli.app, ["validate", str(tmp_path / "missing")]).exit_code != 0
    assert runner.invoke(m1007_cli.app, ["export-schema", "output"]).exit_code == 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text("{}", encoding="utf-8")
    assert runner.invoke(m1007_cli.app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(m1007_cli.app, ["calibrate", str(bad_request)]).exit_code != 0
    assert runner.invoke(m1007_cli.app, ["calibrate", str(request_path)]).exit_code == 0
    abstention = _request(support_threshold=1.0)
    abstention_path = tmp_path / "abstention.json"
    abstention_path.write_text(abstention.model_dump_json(), encoding="utf-8")
    result_path = tmp_path / "abstained-result.json"
    assert (
        runner.invoke(
            m1007_cli.app,
            ["calibrate", str(abstention_path), "--output", str(result_path)],
        ).exit_code
        == 1
    )
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_text("[]", encoding="utf-8")
    assert (
        runner.invoke(m1007_cli.app, ["verify", str(bad_result), str(result_path)]).exit_code != 0
    )
    bad_canonical = tmp_path / "bad-canonical.json"
    bad_canonical.write_text("{", encoding="utf-8")
    assert (
        runner.invoke(m1007_cli.app, ["verify", str(result_path), str(bad_canonical)]).exit_code
        != 0
    )
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(
        result_path.read_bytes().replace(b"support_threshold_not_met", b"ood_unsupported")
    )
    assert runner.invoke(m1007_cli.app, ["verify", str(tampered), str(result_path)]).exit_code == 1
