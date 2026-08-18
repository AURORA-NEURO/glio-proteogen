"""M19-08 API/CLI parity for the claims-ceiling abstention path."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m19_08 import (
    MonitorStatus,
    ProteotypeTranslationMonitoringResult,
    TranslationFindingCode,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_08_translation_monitoring_service as m1908,
)
from tests.contract.test_m19_08_boundary_depth import _with_evidence_claim
from tests.contract.test_m19_08_hardening import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200


def test_api_cli_service_share_claim_boundary_result(tmp_path: Path) -> None:
    request = _with_evidence_claim(_request())
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / "m1908-boundary.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M19-08/translation-health",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTP_OK, response.text
    api_result = ProteotypeTranslationMonitoringResult.model_validate_json(
        response.content, strict=True
    )

    request_path = tmp_path / "m1908-boundary-request.json"
    request_path.write_bytes(serialized)
    cli = CliRunner().invoke(
        cli_app,
        ["m1908-translation-health", "monitor", str(request_path)],
    )
    assert cli.exit_code == 0, cli.output
    cli_result = ProteotypeTranslationMonitoringResult.model_validate_json(cli.stdout, strict=True)
    service_result = m1908.M1908Service().monitor(request)

    assert api_result == cli_result == service_result
    assert api_result.status is MonitorStatus.ABSTAINED
    assert api_result.health_report is None
    assert any(
        finding.code is TranslationFindingCode.PROHIBITED_CLAIM_BOUNDARY
        for finding in api_result.findings
    )
