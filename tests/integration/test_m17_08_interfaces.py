"""Black-box API, CLI and plugin parity for M17-08."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m17_08 import (
    MonitorVariantPeptideTranslationHealthRequest,
    VariantPeptideTranslationMonitoringResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_08_translation_monitoring,
)
from tests.runtime.test_m17_08_monitoring import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "health-report",
    "telemetry",
    "support-drift",
    "workflow-effect",
    "discrepancy",
    "rollback-policy",
    "finding",
)


def test_api_and_cli_export_identical_authority_bound_schemas(tmp_path: Path) -> None:
    for name in SCHEMA_NAMES:
        with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
            response = client.get(f"/v1/contracts/M17-08/{name}/schema")
        cli = CliRunner().invoke(cli_app, ["m1708-translation-health", "export-schema", name])

        assert response.status_code == HTTP_OK
        assert cli.exit_code == 0, cli.output
        assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]
        assert response.json()["x-glio-contract"]["dossierSlice"].endswith(":6104-6144")


def test_api_cli_service_plugin_emit_replay_safe_parity(tmp_path: Path) -> None:
    request: MonitorVariantPeptideTranslationHealthRequest = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "monitor-request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        api_response = client.post(
            "/v1/modules/M17-08/translation-health",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["m1708-translation-health", "monitor", str(request_path)],
    )

    assert api_response.status_code == HTTP_OK, api_response.text
    assert cli.exit_code == 0, cli.output
    api_result = VariantPeptideTranslationMonitoringResult.model_validate_json(
        api_response.content,
        strict=True,
    )
    cli_result = VariantPeptideTranslationMonitoringResult.model_validate_json(
        cli.stdout,
        strict=True,
    )
    service_result = m17_08_translation_monitoring.M1708Service().monitor(request)
    plugin = m17_08_translation_monitoring.M1708Plugin()
    assert service_result == plugin.run(request) == api_result == cli_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M17-08"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.replay(api_result) == api_result
