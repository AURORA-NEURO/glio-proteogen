"""Black-box API, CLI and plugin parity for M18-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m18_03 import (
    BiomarkerPanelIntegratedEvidenceResult,
    FuseBiomarkerPanelEvidenceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_03_fusion_aggregation,
)
from tests.runtime.test_m18_03_fusion import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "integrated-evidence",
    "source-contribution",
    "disagreement",
    "aggregation",
    "configuration",
    "finding",
)


def test_api_and_cli_export_identical_authority_bound_schemas(tmp_path: Path) -> None:
    for name in SCHEMA_NAMES:
        with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
            response = client.get(f"/v1/contracts/M18-03/{name}/schema")
        cli = CliRunner().invoke(cli_app, ["m1803-fusion", "export-schema", name])

        assert response.status_code == HTTP_OK
        assert cli.exit_code == 0, cli.output
        assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]
        assert response.json()["x-glio-contract"]["dossierSlice"].endswith(":6244-6284")


def test_api_cli_service_plugin_emit_exact_parity(tmp_path: Path) -> None:
    request: FuseBiomarkerPanelEvidenceRequest = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "fusion-request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M18-03/fusion",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m1803-fusion", "fuse", str(request_path)])

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = BiomarkerPanelIntegratedEvidenceResult.model_validate_json(
        api_response.content,
        strict=True,
    )
    cli_result = BiomarkerPanelIntegratedEvidenceResult.model_validate_json(
        cli.stdout,
        strict=True,
    )
    service_result = m18_03_fusion_aggregation.M1803Service().fuse(request)
    plugin = m18_03_fusion_aggregation.M1803Plugin()
    assert service_result == plugin.run(request) == api_result == cli_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M18-03"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.replay(api_result) == api_result
