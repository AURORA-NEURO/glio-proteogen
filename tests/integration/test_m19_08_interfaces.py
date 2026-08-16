"""FastAPI/service/plugin parity for M19-08."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m19_08 import (
    ProteotypeTranslationMonitoringResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_08_translation_monitoring_service as m1908,
)
from tests.contract.test_m19_08_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration
HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA: Final = 415
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


def test_api_exposes_authority_bound_contract_schemas(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m1908.sqlite3")) as client:
        for name in SCHEMA_NAMES:
            response = client.get(f"/v1/contracts/M19-08/{name}/schema")
            assert response.status_code == HTTP_OK, response.text
            assert response.json() == contract_json_schema(name)
            assert response.json()["x-glio-contract"]["parentTarget"] == "proteotype"


def test_api_service_and_plugin_are_replay_safe_and_parity_preserving(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "m1908-api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-08/translation-health",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTP_OK, response.text
    api_result = ProteotypeTranslationMonitoringResult.model_validate_json(
        response.content, strict=True
    )
    service = m1908.M1908Service()
    service_result = service.monitor(request)
    plugin = m1908.M1908Plugin()
    token = plugin.validate(request)
    plugin_result = plugin.run(token)
    assert api_result == service_result == plugin_result
    assert service.replay(api_result) == api_result
    assert plugin.replay(api_result) == api_result
    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-08"
    assert plugin.descriptor.external_content_traversal is False


def test_cli_monitor_matches_api_and_service(tmp_path: Path) -> None:
    request = _request()
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "m1908-request.json"
    request_path.write_bytes(serialized)
    cli = CliRunner().invoke(
        cli_app,
        ["m1908-translation-health", "monitor", str(request_path)],
    )
    assert cli.exit_code == 0, cli.output
    cli_result = ProteotypeTranslationMonitoringResult.model_validate_json(cli.stdout, strict=True)
    assert cli_result == m1908.M1908Service().monitor(request)


def test_plugin_rejects_cross_instance_and_forged_tokens() -> None:
    request = _request()
    first = m1908.M1908Plugin()
    second = m1908.M1908Plugin()
    token = first.validate(request)
    with pytest.raises(m1908.M1908TokenError):
        second.run(token)
    with pytest.raises(m1908.M1908TokenError):
        first.run(object())


def test_json_service_boundary_rejects_duplicate_keys() -> None:
    with pytest.raises((TypeError, ValueError)):
        m1908.M1908Service().execute('{"request_id":"a","request_id":"b"}')


def test_api_rejects_wrong_content_type(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "m1908-content.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-08/translation-health",
            content=json.dumps({}),
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == HTTP_UNSUPPORTED_MEDIA
