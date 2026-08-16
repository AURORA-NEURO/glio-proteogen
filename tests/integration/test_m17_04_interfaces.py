"""API, CLI, schema, and plugin parity for M17-04."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_04_intended_use_adapter as m1704,
)
from tests.runtime.test_m17_04_adapter import _request

HTTP_OK = 200


def test_schema_endpoint_and_cli_export_bind_authority(tmp_path) -> None:
    with TestClient(create_app(tmp_path / "schema.sqlite3")) as client:
        response = client.get("/v1/contracts/M17-04/request/schema")
    assert response.status_code == HTTP_OK
    schema = response.json()
    assert schema["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M17-04"
    assert schema["x-glio-contract"]["dossierSha256"].endswith(
        "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert schema["x-glio-contract"]["dossierSlice"].endswith(":5928-5968")

    cli_result = CliRunner().invoke(
        cli_app, ["m1704-intended-use", "export-schema", "output"]
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert json.loads(cli_result.output)["x-glio-contract"]["moduleId"] == (
        "GLIO-PROTEOGEN-M17-04"
    )


def test_api_and_cli_adapt_the_same_result_digest(tmp_path) -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    with TestClient(create_app(tmp_path / "adapt.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M17-04/intended-use-adaptation",
            json=payload,
        )
    assert api_response.status_code == HTTP_OK, api_response.text

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    cli_result = CliRunner().invoke(
        cli_app, ["m1704-intended-use", "adapt", str(request_path)]
    )
    assert cli_result.exit_code == 0, cli_result.output
    cli_payload = json.loads(cli_result.output)
    api_payload = api_response.json()
    assert cli_payload["result_digest"] == api_payload["result_digest"]
    assert cli_payload["status"] == api_payload["status"] == "adapted"


def test_plugin_descriptor_repeats_boundary() -> None:
    descriptor = m1704.M1704Plugin.descriptor
    assert descriptor.module_id == "GLIO-PROTEOGEN-M17-04"
    assert descriptor.provisional_abi is True
    assert descriptor.typed_policy is True
    assert descriptor.kinase_activity is False
    assert descriptor.treatment_recommendation is False
    assert descriptor.unsupported_to_negative is False
