"""API, CLI, and plugin parity checks for provisional M09-08."""

# The long import paths encode module ownership in this focused test.
# ruff: noqa: E501

import json
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher import (
    M0908InputError,
    M0908Plugin,
    M0908Service,
    ValidatedM0908Request,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher.api import (
    create_app,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_08_evidence_explanation_publisher.cli import (
    app as cli_app,
)
from tests.modules.c09_complex_stoichiometry.test_m09_08_publisher import _request


def test_api_validate_publish_and_schema_are_strict() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app(M0908Service())) as client:
        schema = client.get("/v1/modules/M09-08/schemas/verification")
        validated = client.post("/v1/modules/M09-08/validate", json=payload)
        published = client.post("/v1/modules/M09-08/publish", json=payload)
        unknown = client.get("/v1/modules/M09-08/schemas/unknown")

    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTPStatus.OK
    assert published.status_code == HTTPStatus.OK
    assert published.json()["result"]["status"] == "published"
    assert unknown.status_code == HTTPStatus.NOT_FOUND


def test_api_rejects_duplicate_json_keys_without_leaking_details() -> None:
    request = _request()
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    with TestClient(create_app(M0908Service())) as client:
        response = client.post(
            "/v1/modules/M09-08/validate",
            content=body[:-1] + ',"request_id":"forged"}',
        )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in response.text.casefold()


def test_cli_and_plugin_emit_the_same_canonical_result(tmp_path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(request.model_dump(mode="json"), separators=(",", ":")),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        cli_app,
        ["publish", str(request_path), "--output", str(output_path)],
    )
    plugin = M0908Plugin(M0908Service())
    token = plugin.validate(request)
    plugin_result = plugin.run(token)

    assert result.exit_code == 0, result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8")) == json.loads(
        plugin_result.canonical_bytes
    )


def test_plugin_rejects_forged_execution_token() -> None:
    request = _request()
    plugin = M0908Plugin(M0908Service())
    with pytest.raises(TypeError):
        plugin.run(ValidatedM0908Request(request=request, _seal=object()))


def test_api_error_handlers_cover_validation_authorization_and_input_failure() -> None:
    request = _request()
    denied_consent = request.context.references.consent.model_copy(
        update={"state": ConsentState.WITHHELD}
    )
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={"consent": denied_consent}
                    )
                }
            )
        }
    )

    class InputRejectingService(M0908Service):
        def publish(self, _request: object):
            raise M0908InputError("result_noncanonical")

    with TestClient(create_app(M0908Service())) as client:
        invalid_validate = client.post("/v1/modules/M09-08/validate", json={})
        invalid_publish = client.post("/v1/modules/M09-08/publish", json={})
        denied_validate = client.post(
            "/v1/modules/M09-08/validate", json=denied.model_dump(mode="json")
        )
        denied_publish = client.post(
            "/v1/modules/M09-08/publish", json=denied.model_dump(mode="json")
        )
        malformed = client.post("/v1/modules/M09-08/validate", content=b"{not-json")
    with TestClient(create_app(InputRejectingService())) as client:
        rejected = client.post("/v1/modules/M09-08/publish", json=request.model_dump(mode="json"))

    assert invalid_validate.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert invalid_publish.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert denied_validate.status_code == HTTPStatus.FORBIDDEN
    assert denied_publish.status_code == HTTPStatus.FORBIDDEN
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cli_boundaries_and_plugin_serialized_inputs(tmp_path) -> None:
    runner = CliRunner()
    request = _request()
    request_path = tmp_path / "request.json"
    bad_path = tmp_path / "bad.json"
    invalid_path = tmp_path / "invalid.json"
    abstain_path = tmp_path / "abstain.json"
    denied_path = tmp_path / "denied.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    bad_path.write_text("{", encoding="utf-8")
    invalid_path.write_text("{}", encoding="utf-8")
    abstain_path.write_text(
        json.dumps(request.model_copy(update={"assumptions": ()}).model_dump(mode="json")),
        encoding="utf-8",
    )
    denied_path.write_text(
        json.dumps(
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
            ).model_dump(mode="json")
        ),
        encoding="utf-8",
    )
    assert runner.invoke(cli_app, ["export-schema", "verification"]).exit_code == 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(cli_app, ["validate", str(bad_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(invalid_path)]).exit_code != 0
    assert runner.invoke(cli_app, ["publish", str(request_path)]).exit_code == 0
    assert (
        runner.invoke(
            cli_app, ["publish", str(request_path), "--output", str(output_path)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            cli_app, ["publish", str(request_path), "--output", str(output_path)]
        ).exit_code
        != 0
    )
    abstained = runner.invoke(
        cli_app,
        ["publish", str(abstain_path), "--output", str(abstain_path.with_suffix(".out.json"))],
    )
    assert abstained.exit_code == 1
    assert runner.invoke(cli_app, ["publish", str(denied_path)]).exit_code != 0

    plugin = M0908Plugin(M0908Service())
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M09-08"
    serialized = request_path.read_text(encoding="utf-8")
    for candidate in (serialized, serialized.encode("utf-8"), bytearray(serialized, "utf-8")):
        built = plugin.run(plugin.validate(candidate))
        assert built.result.status.value == "published"
    assert M0908Service().verify(built.result, built.canonical_bytes).verified
