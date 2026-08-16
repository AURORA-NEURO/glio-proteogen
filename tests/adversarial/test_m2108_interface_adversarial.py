"""Negative transport and boundary coverage for M21-08 interfaces."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 - used by pytest temporary path annotations.

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m21_08 import canonical_request_digest, result_payload_digest
from glio_proteogen.modules.c21_reference_material.m21_08_evidence_gate_release_adjudicator import (
    M2108Engine,
    M2108Plugin,
    M2108ReplayError,
    cli_app,
    create_app,
)

from .test_m2108_adversarial import _request


def test_fastapi_rejects_malformed_non_object_and_bad_result_envelopes() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/modules/M21-08/schemas/request").status_code == 200
    assert client.post("/v1/modules/M21-08/verify", content=b"{").status_code == 422
    assert client.post("/v1/modules/M21-08/verify", json=[]).status_code == 422
    assert (
        client.post("/v1/modules/M21-08/verify", json={"result": {"bad": True}}).status_code == 422
    )

    payload = _request().model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    denied = client.post("/v1/modules/M21-08/validate", json=payload)
    assert denied.status_code == 422
    assert "controls" not in denied.text.lower()


def test_fastapi_tampered_result_is_rejected() -> None:
    client = TestClient(create_app())
    result = M2108Engine().evaluate(_request()).model_dump(mode="json")
    result["result_digest"] = "sha256:" + "f" * 64
    response = client.post("/v1/modules/M21-08/verify", json=result)
    assert response.status_code == 422


def test_typer_rejects_unknown_malformed_abstained_and_tampered(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    schema_path = tmp_path / "schema.json"
    assert (
        runner.invoke(cli_app, ["export-schema", "request", "--output", str(schema_path)]).exit_code
        == 0
    )
    assert schema_path.exists()
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(malformed)]).exit_code != 0

    failed_request = _request().model_copy(
        update={
            "requirements": (_request().requirements[0].model_copy(update={"satisfied": False}),)
        }
    )
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(failed_request.model_dump_json(), encoding="utf-8")
    abstained = runner.invoke(
        cli_app, ["adjudicate", str(request_path), "--output", str(result_path)]
    )
    assert abstained.exit_code == 1
    emitted = runner.invoke(cli_app, ["adjudicate", str(request_path)])
    assert emitted.exit_code == 1

    tampered = json.loads(result_path.read_text(encoding="utf-8"))
    tampered["result_digest"] = "sha256:" + "f" * 64
    result_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert runner.invoke(cli_app, ["verify", str(result_path)]).exit_code != 0


def test_plugin_and_engine_reject_malformed_inputs_and_false_replay() -> None:
    engine = M2108Engine()
    plugin = M2108Plugin()
    with pytest.raises((TypeError, ValueError)):
        plugin.validate("{")
    with pytest.raises((TypeError, ValueError)):
        plugin.verify({"bad": True})
    with pytest.raises(M2108ReplayError):
        engine.verify(object())
    result = engine.evaluate(_request())
    tampered = result.model_copy(update={"abstention_reason": "changed"})
    with pytest.raises(M2108ReplayError):
        engine.verify(tampered, replay=False)


def test_engine_preflight_handles_property_failure() -> None:
    class BrokenContext:
        @property
        def context(self) -> object:
            raise RuntimeError("malformed context")  # noqa: TRY003

    with pytest.raises(ValueError, match="controls are malformed"):
        M2108Engine().evaluate(BrokenContext())


def test_canonical_dict_projections_are_stable() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    assert canonical_request_digest(request) == canonical_request_digest(payload)
    result = M2108Engine().evaluate(request)
    result_payload = result.model_dump(mode="json")
    assert result_payload_digest(result) == result_payload_digest(result_payload)
