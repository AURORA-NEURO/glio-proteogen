"""Black-box API, CLI, service, plugin, and schema parity for M18-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m18_06 import (
    M1806_DOSSIER_SLICE,
    BiomarkerPanelAdjudicationResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c18_spatial_proteomics_projection.m18_06_reviewer_adjudication import (
    M1806Engine,
    M1806Plugin,
    M1806Service,
    adjudicate_biomarker_panel_queue,
)
from tests.runtime.test_m18_06_adjudication import _request

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


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_cli_and_library_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M18-06/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["m18-06-adjudication", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]
    assert response.json()["x-glio-contract"]["dossierSlice"] == M1806_DOSSIER_SLICE


def test_service_plugin_api_cli_and_function_emit_exact_parity(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    request_path.write_bytes(serialized)

    service = M1806Service()
    plugin = M1806Plugin()
    expected = adjudicate_biomarker_panel_queue(request)
    assert plugin.validate_request(request) == request
    assert service.validate_request(request) == request
    assert expected == M1806Engine().adapt(request) == service.adjudicate(request)
    assert expected == plugin.run(request)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M18-06/adjudication",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["m18-06-adjudication", "adjudicate", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = BiomarkerPanelAdjudicationResult.model_validate_json(response.content, strict=True)
    cli_result = BiomarkerPanelAdjudicationResult.model_validate_json(cli.stdout, strict=True)
    assert expected == api_result == cli_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M18-06"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.descriptor.blinded_review is True
    assert plugin.descriptor.immutable_history is True
    assert plugin.replay(expected) == expected
    assert service.replay(expected) == expected
