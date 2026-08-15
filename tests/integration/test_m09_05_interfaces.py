"""API, CLI, and plugin parity checks for M09-05."""

# HTTP status literals and a forged-token assertion are intentional in boundary tests.
# ruff: noqa: E501, PLR2004, TRY003

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    M0905Plugin,
    M0905Service,
    ValidatedM0905Request,
    app,
    cli_app,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator.engine import (
    M0905ConstraintIntegrator,
)
from tests.modules.c09_complex_activity.test_m09_05_integrator import _request


def test_api_exports_schema_and_integrates_canonical_result() -> None:
    request = _request("hold")
    client = TestClient(app)
    schema = client.get("/v1/modules/M09-05/schemas/verification")
    assert schema.status_code == 200
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    response = client.post("/v1/modules/M09-05/integrate", json=request.model_dump(mode="json"))
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "estimated"
    assert json.loads(body["canonical"]) == body["result"]


def test_api_rejects_unknown_schema_and_malformed_json() -> None:
    client = TestClient(app)
    assert client.get("/v1/modules/M09-05/schemas/nope").status_code == 404
    assert client.post("/v1/modules/M09-05/validate", content=b"{bad").status_code == 422


def test_plugin_parse_once_and_token_seal() -> None:
    request = _request("hold")
    plugin = M0905Plugin(M0905Service())
    token = plugin.validate(json.dumps(request.model_dump(mode="json")))
    assert isinstance(token, ValidatedM0905Request)
    assert plugin.run(token).result.status.value == "estimated"
    try:
        plugin.run(ValidatedM0905Request(request=request, _seal=object()))
    except TypeError:
        pass
    else:
        raise AssertionError("forged plugin token unexpectedly executed")


def test_cli_export_schema_and_validation(tmp_path) -> None:
    request = _request("hold")
    runner = CliRunner()
    exported = runner.invoke(cli_app, ["export-schema", "request"])
    assert exported.exit_code == 0
    assert json.loads(exported.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M09-05"
    path = tmp_path / "valid_request.json"
    path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    validated = runner.invoke(cli_app, ["validate", str(path)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["operation"] == "integrate_complex_activity_constraints"


def test_service_replay_matches_engine() -> None:
    request = _request("hold")
    engine = M0905ConstraintIntegrator()
    built = M0905Service().execute(request)
    assert engine.verify(built.result, built.canonical_bytes).verified
