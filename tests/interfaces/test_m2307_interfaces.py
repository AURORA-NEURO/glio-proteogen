"""FastAPI, Typer, and plugin parity tests for provisional M23-07."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c21_reference_material import (
    m23_07_human_factors_operational_evaluator as m2307,
)
from tests.adversarial.test_m2307_contract import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_fastapi_validate_evaluate_verify_and_sanitized_errors() -> None:
    request = _request()
    client = TestClient(m2307.create_app(m2307.M2307Service()))
    schemas = client.get("/v1/modules/M23-07/schemas")
    assert schemas.status_code == _HTTP_OK
    assert set(schemas.json()) == {
        "request",
        "output",
        "report",
        "metric",
        "fallback",
        "configuration",
        "finding",
    }
    assert client.get("/v1/modules/M23-07/schemas/request").status_code == _HTTP_OK
    body = request.model_dump(mode="json")
    assert client.post("/v1/modules/M23-07/validate", json=body).status_code == _HTTP_OK
    generated = client.post("/v1/modules/M23-07/evaluate", json=body)
    assert generated.status_code == _HTTP_OK
    verified = client.post("/v1/modules/M23-07/verify", json={"result": generated.json()})
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True
    assert client.get("/v1/modules/M23-07/schemas/unknown").status_code == _HTTP_NOT_FOUND
    assert (
        client.post("/v1/modules/M23-07/validate", content=b"[]").status_code == _HTTP_UNPROCESSABLE
    )
    malformed = client.post("/v1/modules/M23-07/verify", content=b"[")
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert client.post("/v1/modules/M23-07/verify", json={}).status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in malformed.text


def test_fastapi_not_evaluable_dimension_is_explicit_abstention() -> None:
    request = _request().model_dump(mode="json")
    request["metrics"][0]["status"] = "not_evaluable"
    response = TestClient(m2307.create_app(m2307.M2307Service())).post(
        "/v1/modules/M23-07/evaluate", json=request
    )
    assert response.status_code == _HTTP_OK
    assert response.json()["status"] == "abstained"
    assert response.json()["report"] is None


def test_fastapi_denied_controls_are_sanitized() -> None:
    request = _request()
    consent = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"consent": consent})}
    )
    denied = request.model_copy(update={"context": context}).model_dump(mode="json")
    client = TestClient(m2307.create_app(m2307.M2307Service()))
    validate_response = client.post("/v1/modules/M23-07/validate", json=denied)
    evaluate_response = client.post("/v1/modules/M23-07/evaluate", json=denied)
    assert validate_response.status_code == _HTTP_UNPROCESSABLE
    assert evaluate_response.status_code == _HTTP_UNPROCESSABLE
    assert "Traceback" not in evaluate_response.text


def test_plugin_is_strict_parse_once_and_requires_token() -> None:
    request = _request()
    plugin = m2307.M2307Plugin(m2307.M2307Service())
    validated = plugin.validate(
        m2307.HumanFactorsEvaluationSubmission(request=request.model_dump_json())
    )
    result = plugin.run(validated)
    assert plugin.replay(result).result_digest == result.result_digest
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M23-07"
    with pytest.raises(TypeError, match="human-factors submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", request))


def test_plugin_tokens_are_instance_bound_and_snapshot_bound() -> None:
    first = m2307.M2307Plugin(m2307.M2307Service())
    second = m2307.M2307Plugin(m2307.M2307Service())
    token = first.validate(m2307.HumanFactorsEvaluationSubmission(_request()))

    assert first.run(token).result_digest.startswith("sha256:")
    with pytest.raises(TypeError, match="validated request token"):
        second.run(token)

    forged = m2307.ValidatedM2307Request(token.request, object())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(forged)

    mutated = first.validate(m2307.HumanFactorsEvaluationSubmission(_request()))
    object.__setattr__(mutated.request, "request_id", "request.m2307.forged")
    with pytest.raises(TypeError, match="validated request token"):
        first.run(mutated)

    replaced = first.validate(m2307.HumanFactorsEvaluationSubmission(_request()))
    object.__setattr__(replaced, "request", replaced.request.model_copy())
    with pytest.raises(TypeError, match="validated request token"):
        first.run(replaced)


def test_typer_export_validate_evaluate_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    schema_path = tmp_path / "schema.json"
    result_path = tmp_path / "result.json"
    runner = CliRunner()
    assert (
        runner.invoke(
            m2307.app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            m2307.app, ["export-schema", "request", "--output", str(schema_path)]
        ).exit_code
        != 0
    )
    assert runner.invoke(m2307.app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(m2307.app, ["evaluate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            m2307.app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(m2307.app, ["verify", str(result_path)]).exit_code == 0
    assert (
        runner.invoke(
            m2307.app, ["evaluate", str(request_path), "--output", str(result_path)]
        ).exit_code
        != 0
    )


def test_typer_sanitizes_bad_inputs_and_replay_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    assert runner.invoke(m2307.app, ["export-schema", "unknown"]).exit_code != 0
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_bytes(b"[]")
    assert runner.invoke(m2307.app, ["validate", str(bad_request)]).exit_code != 0
    assert runner.invoke(m2307.app, ["evaluate", str(bad_request)]).exit_code != 0
    bad_result = tmp_path / "bad-result.json"
    bad_result.write_bytes(b"[]")
    assert runner.invoke(m2307.app, ["verify", str(bad_result)]).exit_code != 0
    result_path = tmp_path / "valid-result.json"
    result_path.write_bytes(canonical_json_bytes(m2307.M2307Service().evaluate(_request())))

    class ReplayFailure:
        def replay(self, _result: object) -> object:
            raise ValueError

    monkeypatch.setattr(m2307.cli, "_SERVICE", ReplayFailure())
    assert runner.invoke(m2307.app, ["verify", str(result_path)]).exit_code != 0
