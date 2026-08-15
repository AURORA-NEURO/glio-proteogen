"""FastAPI, Typer, and plugin parity checks for M08-07."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m08_07 import verify_result_replay
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_07_calibration_selective_prediction import (
    M0807Plugin,
    M0807Service,
    create_app,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_07_calibration_selective_prediction.cli import (
    app as cli_app,
)

from tests.modules.test_m08_07_runtime import _candidate
from tests.contract.test_m08_07_contract_hardening import _request


def _document() -> tuple[dict[str, object], object]:
    request = _request().model_copy(update={"candidate": _candidate()})
    return request.model_dump(mode="json"), request


def test_plugin_json_parity_and_replay_tamper_detection() -> None:
    document, request = _document()
    plugin = M0807Plugin(M0807Service())
    token = plugin.validate(json.dumps(document, separators=(",", ":")))
    result = plugin.run(token)
    assert result.status.value == "calibrated"
    assert M0807Service.verify(result, request)
    assert verify_result_replay(result, request)
    tampered = result.model_dump(mode="json")
    tampered["status"] = "abstained"
    assert not M0807Service.verify(tampered, request)


def test_api_rejects_duplicate_json_keys_and_returns_schema() -> None:
    document, _ = _document()
    client = TestClient(create_app(M0807Service()))
    response = client.post("/m08-07/calibrate", content=b'{"request_id":1,"request_id":2}')
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "json_duplicate_key"
    schemas = client.get("/m08-07/schema")
    assert schemas.status_code == 200
    assert schemas.json()["schemas"]["request"]["x-glio-contract"]["provisionalAbi"] is True
    assert client.post("/m08-07/calibrate", json=document).status_code == 200


def test_cli_schema_and_strict_validation(tmp_path) -> None:
    document, _ = _document()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(document), encoding="utf-8")
    runner = CliRunner()
    exported = runner.invoke(cli_app, ["export-schema", "candidate"])
    assert exported.exit_code == 0
    assert '"provisionalAbi": true' in exported.stdout
    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["valid"] is True
    executed = runner.invoke(cli_app, ["calibrate", str(request_path)])
    assert executed.exit_code == 0
    assert json.loads(executed.stdout)["status"] == "calibrated"
