"""API, CLI, and plugin parity checks for provisional M08-08."""

# The long module import paths make the test's ownership explicit.
# ruff: noqa: E501

import json
from http import HTTPStatus

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher import (
    M0808Plugin,
    M0808Service,
    create_app,
)
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_08_evidence_explanation_publisher.cli import (
    app as cli_app,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_08_publisher import _request


def test_api_validate_publish_and_schema_are_strict() -> None:
    request = _request("source.1")
    payload = request.model_dump(mode="json")
    with TestClient(create_app(M0808Service())) as client:
        schema = client.get("/v1/modules/M08-08/schemas/verification")
        validated = client.post("/v1/modules/M08-08/validate", json=payload)
        published = client.post("/v1/modules/M08-08/publish", json=payload)
        unknown = client.get("/v1/modules/M08-08/schemas/not-a-contract")
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.status_code == HTTPStatus.OK
    assert published.status_code == HTTPStatus.OK
    assert published.json()["result"]["status"] == "published"
    assert unknown.status_code == HTTPStatus.NOT_FOUND


def test_api_rejects_duplicate_json_keys_and_malformed_body() -> None:
    request = _request("source.1")
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    with TestClient(create_app(M0808Service())) as client:
        duplicate = client.post(
            "/v1/modules/M08-08/validate",
            content=body[:-1] + ',"request_id":"forged"}',
        )
        malformed = client.post("/v1/modules/M08-08/validate", content=b"{not-json")
    assert duplicate.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert "traceback" not in duplicate.text.casefold()
    assert malformed.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cli_and_plugin_have_the_same_canonical_result(tmp_path) -> None:
    request = _request("source.1")
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    cli_result = CliRunner().invoke(
        cli_app,
        ["publish", str(request_path), "--output", str(output_path)],
    )
    token = M0808Plugin(M0808Service()).validate(request)
    plugin_result = M0808Plugin(M0808Service()).run(token)
    assert cli_result.exit_code == 0, cli_result.stdout
    assert json.loads(output_path.read_text(encoding="utf-8")) == json.loads(
        plugin_result.canonical_bytes
    )


def test_cli_schema_validation_and_no_overwrite(tmp_path) -> None:
    runner = CliRunner()
    request = _request("source.1")
    request_path = tmp_path / "request.json"
    bad_path = tmp_path / "bad.json"
    output_path = tmp_path / "output.json"
    request_path.write_text(json.dumps(request.model_dump(mode="json")), encoding="utf-8")
    bad_path.write_text("{", encoding="utf-8")
    assert runner.invoke(cli_app, ["export-schema", "verification"]).exit_code == 0
    assert runner.invoke(cli_app, ["export-schema", "unknown"]).exit_code != 0
    assert runner.invoke(cli_app, ["validate", str(request_path)]).exit_code == 0
    assert runner.invoke(cli_app, ["validate", str(bad_path)]).exit_code != 0
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
