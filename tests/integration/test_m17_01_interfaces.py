"""API, CLI, schema, and plugin interface coverage for M17-01."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m17_01 import CompatibilityStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_01_upstream_contract_resolver as m1701_resolver,
)
from tests.runtime.test_m17_01_resolver import _candidate, _request

HTTP_OK = 200


def test_schema_endpoint_and_cli_export_bind_to_authority(tmp_path) -> None:
    with TestClient(create_app(tmp_path / "schema.sqlite3")) as client:
        response = client.get("/v1/contracts/M17-01/request/schema")
    assert response.status_code == HTTP_OK
    schema = response.json()
    assert schema["x-glio-contract"]["dossierSha256"].endswith(
        "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
    )
    assert schema["x-glio-contract"]["dossierSlice"].endswith(":5796-5836")

    result = CliRunner().invoke(cli_app, ["m1701-upstream", "export-schema", "output"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M17-01"


def test_api_and_cli_resolve_the_same_canonical_result(tmp_path) -> None:
    request = _request(
        _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE)
    )
    payload = request.model_dump(mode="json")
    with TestClient(create_app(tmp_path / "resolve.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M17-01/upstream-contract-resolution",
            json=payload,
        )
    assert api_response.status_code == HTTP_OK, api_response.text

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    cli_response = CliRunner().invoke(
        cli_app,
        ["m1701-upstream", "resolve", str(request_path)],
    )
    assert cli_response.exit_code == 0, cli_response.output
    cli_payload = json.loads(cli_response.output)
    api_payload = api_response.json()
    assert cli_payload["result_digest"] == api_payload["result_digest"]
    assert cli_payload["status"] == api_payload["status"] == "validated"
    assert cli_payload["compatibility_report"] == api_payload["compatibility_report"]


def test_plugin_descriptor_exposes_boundary_and_provisional_abi() -> None:
    descriptor = m1701_resolver.M1701Plugin.descriptor
    assert descriptor.module_id == "GLIO-PROTEOGEN-M17-01"
    assert descriptor.provisional_abi is True
    assert descriptor.kinase_activity is False
    assert descriptor.typed_discovery is True
    assert descriptor.typed_rejections is True
