"""Black-box API, CLI, service, plugin, and schema parity for M19-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m19_06 import (
    M1906_DOSSIER_SLICE,
    ProteotypeAdjudicationResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_06_reviewer_adjudication import (
    M1906Engine,
    M1906Plugin,
    M1906Service,
    adjudicate_proteotype_queue,
)
from tests.contract.test_m19_06_provisional import _request

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "record",
    "queue-entry",
    "assignment",
    "audit-event",
    "configuration",
    "finding",
)
HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_cli_and_library_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M19-06/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["m19-06-adjudication", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]
    assert response.json()["x-glio-contract"]["dossierSlice"] == M1906_DOSSIER_SLICE


def test_service_plugin_api_cli_and_function_emit_exact_parity(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(serialized)

    service = M1906Service()
    plugin = M1906Plugin()
    expected = adjudicate_proteotype_queue(request)
    assert plugin.validate_request(request) == request
    assert service.validate_request(request) == request
    assert expected == M1906Engine().adapt(request) == service.adjudicate(request)
    assert expected == plugin.run(request)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-06/adjudication",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["m19-06-adjudication", "adjudicate", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteotypeAdjudicationResult.model_validate_json(response.content, strict=True)
    cli_result = ProteotypeAdjudicationResult.model_validate_json(cli.stdout, strict=True)
    assert expected == api_result == cli_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-06"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.descriptor.blinded_review is True
    assert plugin.descriptor.immutable_history is True
    assert plugin.replay(expected) == expected
    assert service.replay(expected) == expected


def test_api_replay_and_strict_content_type_are_closed(tmp_path: Path) -> None:
    result = M1906Engine().adapt(_request())
    payload = canonical_json_bytes(result.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "verify.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-06/adjudication/verify",
            content=payload,
            headers={"content-type": "application/json"},
        )
        wrong_media = client.post(
            "/v1/modules/M19-06/adjudication",
            content=canonical_json_bytes(_request().model_dump(mode="json")),
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == HTTP_OK
    assert ProteotypeAdjudicationResult.model_validate_json(response.content, strict=True) == result
    assert wrong_media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
