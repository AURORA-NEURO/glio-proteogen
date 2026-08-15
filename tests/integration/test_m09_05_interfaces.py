"""API, CLI, and plugin parity checks for M09-05."""

# HTTP status literals and a forged-token assertion are intentional in boundary tests.
# ruff: noqa: ARG002, E501, PLR2004, PLC0415, TRY003

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator import (
    M0905Plugin,
    M0905Service,
    ValidatedM0905Request,
    app,
    cli_app,
)
from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator.engine import (
    M0905ConstraintIntegrator,
    M0905InputError,
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
    assert client.post("/v1/modules/M09-05/validate", json={}).status_code == 422


def test_api_handles_authorization_and_service_failures() -> None:
    request = _request("hold")
    withheld = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    blocked = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": withheld}
                    )
                }
            )
        }
    )
    assert (
        TestClient(app)
        .post("/v1/modules/M09-05/validate", json=blocked.model_dump(mode="json"))
        .status_code
        == 403
    )
    client = TestClient(app)
    assert client.post("/v1/modules/M09-05/integrate", json={}).status_code == 422
    assert (
        client.post(
            "/v1/modules/M09-05/integrate", json=blocked.model_dump(mode="json")
        ).status_code
        == 403
    )
    assert (
        client.post("/v1/modules/M09-05/validate", json=request.model_dump(mode="json")).status_code
        == 200
    )

    class FailingService:
        def validate_request(self, request: object) -> object:
            return request

        def integrate(self, request: object) -> object:
            raise M0905InputError("result_limit")

    from glio_proteogen.modules.c09_complex_activity.m09_05_mechanism_constraint_integrator.api import (
        create_app,
    )

    failure_client = TestClient(create_app(FailingService()))
    assert (
        failure_client.post(
            "/v1/modules/M09-05/integrate", json=request.model_dump(mode="json")
        ).status_code
        == 422
    )


def test_plugin_parse_once_and_token_seal() -> None:
    request = _request("hold")
    plugin = M0905Plugin(M0905Service())
    token = plugin.validate(json.dumps(request.model_dump(mode="json")))
    assert isinstance(token, ValidatedM0905Request)
    assert plugin.run(token).result.status.value == "estimated"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M09-05"
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
    assert runner.invoke(cli_app, ["export-schema", "nope"]).exit_code != 0
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{bad", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(invalid)]).exit_code != 0
    semantically_invalid = tmp_path / "semantically-invalid.json"
    semantically_invalid.write_text("{}", encoding="utf-8")
    assert runner.invoke(cli_app, ["validate", str(semantically_invalid)]).exit_code != 0


def test_cli_integrate_writes_once_and_abstains_nonzero(tmp_path) -> None:
    request = _request("hold")
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    output = tmp_path / "result.json"
    runner = CliRunner()
    first = runner.invoke(cli_app, ["integrate", str(path), "--output", str(output)])
    assert first.exit_code == 0
    second = runner.invoke(cli_app, ["integrate", str(path), "--output", str(output)])
    assert second.exit_code != 0
    blocked = _request("force_violation")
    blocked_path = tmp_path / "blocked.json"
    blocked_path.write_text(json.dumps(blocked.model_dump(mode="json")), encoding="utf-8")
    assert runner.invoke(cli_app, ["integrate", str(blocked_path)]).exit_code == 1
    withheld = request.context.references.consent.model_copy(update={"state": ConsentState.WITHHELD})
    unauthorized = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": withheld}
                    )
                }
            )
        }
    )
    unauthorized_path = tmp_path / "unauthorized.json"
    unauthorized_path.write_text(json.dumps(unauthorized.model_dump(mode="json")), encoding="utf-8")
    assert runner.invoke(cli_app, ["integrate", str(unauthorized_path)]).exit_code != 0


def test_service_replay_matches_engine() -> None:
    request = _request("hold")
    engine = M0905ConstraintIntegrator()
    built = M0905Service().execute(request)
    assert engine.verify(built.result, built.canonical_bytes).verified
    assert M0905Service().verify(built.result, built.canonical_bytes).verified
