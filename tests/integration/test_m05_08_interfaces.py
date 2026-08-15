"""API/CLI parity and strict-ingress tests for M05-08."""

from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m05_08 import contract_json_schema
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.api import (
    create_app,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.cli import (
    app as cli_app,
)
from tests.modules.c05_ptm_localization.test_m05_08_release_packaging import _valid_fixture

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422


def test_api_and_cli_export_identical_schema() -> None:
    contracts = (
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "signature",
        "quarantine",
        "verification",
        "transformation",
        "quality-decision",
    )
    runner = CliRunner()
    with TestClient(create_app()) as client:
        for name in contracts:
            api_schema = client.get(f"/v1/modules/M05-08/schemas/{name}")
            cli_schema = runner.invoke(cli_app, ["export-schema", name])
            assert api_schema.status_code == _HTTP_OK
            assert cli_schema.exit_code == 0
            assert api_schema.json() == json.loads(cli_schema.stdout)
            assert api_schema.json() == contract_json_schema(name)


def test_api_and_cli_validate_the_same_canonical_request(tmp_path) -> None:
    request, _ = _valid_fixture()
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request.model_dump(mode="json")))

    with TestClient(create_app()) as client:
        api = client.post(
            "/v1/modules/M05-08/validate",
            content=request_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["validate", str(request_path)])

    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 0
    assert api.json() == json.loads(cli.stdout)


def test_api_and_cli_reject_duplicate_keys_without_leaking_input(tmp_path) -> None:
    payload = b'{"request_id":"safe","request_id":"secret"}'
    request_path = tmp_path / "duplicate.json"
    request_path.write_bytes(payload)

    with TestClient(create_app()) as client:
        api = client.post("/v1/modules/M05-08/validate", content=payload)
    cli = CliRunner().invoke(cli_app, ["validate", str(request_path)])

    assert api.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in api.text
    assert cli.exit_code != 0
    assert "secret" not in cli.stdout


def test_api_build_quarantines_without_default_signing_verifier() -> None:
    request, artifacts = _valid_fixture()
    envelope = {
        "request": request.model_dump(mode="json"),
        "artifacts": {
            path: base64.b64encode(content).decode("ascii")
            for path, content in artifacts.items()
        },
    }

    with TestClient(create_app()) as client:
        response = client.post("/v1/modules/M05-08/build", json=envelope)

    assert response.status_code == _HTTP_OK
    assert response.json()["package"] is None
    assert response.json()["result"]["disposition"] == "quarantined"


def test_cli_build_matches_api_quarantine_result(tmp_path) -> None:
    request, artifacts = _valid_fixture()
    envelope = {
        "request": request.model_dump(mode="json"),
        "artifacts": {
            path: base64.b64encode(content).decode("ascii")
            for path, content in artifacts.items()
        },
    }
    request_path = tmp_path / "build.json"
    request_path.write_bytes(canonical_json_bytes(envelope))

    with TestClient(create_app()) as client:
        api = client.post("/v1/modules/M05-08/build", content=request_path.read_bytes())
    cli = CliRunner().invoke(cli_app, ["build", str(request_path)])

    assert api.status_code == _HTTP_OK
    assert cli.exit_code == 1
    api_payload = api.json()
    cli_payload = json.loads(cli.stdout)
    assert api_payload["package"] == cli_payload["package"]
    assert api_payload["result"]["request_digest"] == cli_payload["result"]["request_digest"]
    assert api_payload["result"]["disposition"] == cli_payload["result"]["disposition"]
    assert api_payload["result"]["quarantine_reasons"] == cli_payload["result"][
        "quarantine_reasons"
    ]
