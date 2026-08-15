"""API, CLI, and plugin parity checks for provisional M08-05."""

# The long module import paths make the test's ownership explicit.
# ruff: noqa: E501, ARG002

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator import (
    M0805InputError,
    M0805Plugin,
    M0805Service,
    create_app,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_05_mechanism_constraint_integrator.cli import (
    app as cli_app,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_05_integrator import (
    _request,
)


def test_api_validate_integrate_and_schema_are_strict() -> None:
    request = _request("conservation_hold")
    payload = request.model_dump(mode="json")
    with TestClient(create_app(M0805Service())) as client:
        schema = client.get("/v1/modules/M08-05/schemas/verification")
        validated = client.post("/v1/modules/M08-05/validate", json=payload)
        integrated = client.post("/v1/modules/M08-05/integrate", json=payload)
        unknown = client.get("/v1/modules/M08-05/schemas/not-a-contract")

    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTPStatus.OK
    assert integrated.status_code == HTTPStatus.OK
    assert integrated.json()["result"]["status"] == "estimated"
    assert unknown.status_code == HTTPStatus.NOT_FOUND


def test_api_rejects_duplicate_json_keys_without_leaking_details() -> None:
    request = _request("conservation_hold")
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    with TestClient(create_app(M0805Service())) as client:
        response = client.post(
            "/v1/modules/M08-05/validate",
            content=body[:-1] + ',"request_id":"forged"}',
        )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in response.text.casefold()


def test_cli_and_plugin_use_the_same_canonical_result(tmp_path) -> None:
    request = _request("conservation_hold")
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(request.model_dump(mode="json"), separators=(",", ":")),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli_app,
        ["integrate", str(request_path), "--output", str(output_path)],
    )
    plugin = M0805Plugin(M0805Service())
    token = plugin.validate(request)
    plugin_result = plugin.run(token)

    assert result.exit_code == 0, result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8")) == json.loads(
        plugin_result.canonical_bytes
    )


def test_api_validation_authorization_and_input_handlers() -> None:
    request = _request("conservation_hold")
    withheld = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied = request.model_copy(
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

    class InputRejectingService(M0805Service):
        def integrate(self, request: object):
            raise M0805InputError("result_noncanonical")

    with TestClient(create_app(M0805Service())) as client:
        invalid = client.post("/v1/modules/M08-05/validate", json={})
        invalid_integrate = client.post("/v1/modules/M08-05/integrate", json={})
        denied_validate = client.post(
            "/v1/modules/M08-05/validate", json=denied.model_dump(mode="json")
        )
        denied_integrate = client.post(
            "/v1/modules/M08-05/integrate", json=denied.model_dump(mode="json")
        )
        malformed = client.post("/v1/modules/M08-05/validate", content=b"{not-json")
    with TestClient(create_app(InputRejectingService())) as client:
        rejected = client.post(
            "/v1/modules/M08-05/integrate",
            json=request.model_dump(mode="json"),
        )

    assert invalid.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid_integrate.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert denied_validate.status_code == HTTPStatus.FORBIDDEN
    assert denied_integrate.status_code == HTTPStatus.FORBIDDEN
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cli_schema_validation_and_safe_output_boundaries(tmp_path) -> None:
    runner = CliRunner()
    request = _request("conservation_hold")
    request_path = tmp_path / "request.json"
    bad_path = tmp_path / "bad.json"
    invalid_path = tmp_path / "invalid-contract.json"
    abstain_path = tmp_path / "abstain.json"
    denied_path = tmp_path / "denied.json"
    output_path = tmp_path / "output.json"
    request_path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    bad_path.write_text("{", encoding="utf-8")
    invalid_path.write_text("{}", encoding="utf-8")
    abstain_path.write_text(
        json.dumps(_request("force_violation").model_dump(mode="json")), encoding="utf-8"
    )
    denied = request.model_copy(
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
    denied_path.write_text(json.dumps(denied.model_dump(mode="json")), encoding="utf-8")

    assert runner.invoke(cli_app, ["export-schema", "verification"]).exit_code == 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(cli_app, ["validate", str(bad_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(invalid_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(tmp_path / "missing.json")]).exit_code != 0
    assert (
        runner.invoke(
            cli_app, ["integrate", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    assert runner.invoke(cli_app, ["integrate", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["integrate", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )
    abstained = runner.invoke(
        cli_app,
        ["integrate", str(abstain_path), "--output", str(abstain_path.with_suffix(".out.json"))],
    )
    assert abstained.exit_code == 1
    assert runner.invoke(cli_app, ["integrate", str(denied_path)]).exit_code != 0
