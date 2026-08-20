"""Central API and CLI registration checks for M20-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as central_cli_app
from tests.contract.test_m20_05_adversarial import _request

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200


def test_central_api_and_cli_expose_m2005_replay_surface(tmp_path: Path) -> None:
    request = _request()
    body = request.model_dump(mode="json")
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        schemas = client.get("/v1/modules/M20-05/schemas")
        presented = client.post("/v1/modules/M20-05/present", json=body)
        assert schemas.status_code == _HTTP_OK
        assert presented.status_code == _HTTP_OK, presented.text
        verified = client.post(
            "/v1/modules/M20-05/verify",
            json={"result": presented.json()},
        )
    assert verified.status_code == _HTTP_OK, verified.text
    assert verified.json()["verified"] is True

    schema = CliRunner().invoke(
        central_cli_app,
        ["m20-05-presentation", "export-schema", "request"],
    )
    assert schema.exit_code == 0, schema.output
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M20-05"
