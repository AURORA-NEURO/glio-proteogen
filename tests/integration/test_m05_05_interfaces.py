"""Black-box schema, API, CLI, and plugin parity checks for M05-05."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m05_05.run import build_scenario
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_05 import contract_json_schema
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_05_artifact_detection import (
    M0505Plugin,
    M0505Service,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_UNSUPPORTED_MEDIA_TYPE = 415
_HTTP_UNPROCESSABLE_CONTENT = 422

_SCHEMA_NAMES = (
    "request",
    "output",
    "policy",
    "threshold",
    "profile",
    "evidence-event",
    "evidence-ledger",
    "evidence-ledger-binding",
    "artifact-posterior",
    "contamination-flag",
    "exclusion-mask-entry",
    "finding",
    "receipt",
)


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_api_cli_and_library_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.get(f"/v1/contracts/M05-05/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["ptm-localization-artifacts", "export-schema", name],
    )

    assert response.status_code == _HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]


def test_library_service_plugin_api_and_cli_are_byte_semantic_peers(tmp_path: Path) -> None:
    request = build_scenario("contamination_detected").request
    service = M0505Service()
    plugin = M0505Plugin(service)
    library_result = service.execute(request)
    plugin_result = plugin.run(plugin.validate(canonical_json_bytes(request)))

    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M05-05/artifact-detection",
            content=canonical_json_bytes(request),
            headers={"content-type": "application/json"},
        )
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    cli = CliRunner().invoke(
        cli_app,
        ["ptm-localization-artifacts", "detect", str(request_path)],
    )

    assert response.status_code == _HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert plugin_result == library_result
    assert response.json() == library_result.model_dump(mode="json")
    assert cli.stdout.strip() == canonical_json_bytes(library_result).decode("utf-8")


def test_api_requires_exact_json_media_type(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M05-05/artifact-detection",
            content=canonical_json_bytes(request),
            headers={"content-type": "text/plain"},
        )

    assert response.status_code == _HTTP_UNSUPPORTED_MEDIA_TYPE


def test_api_rejects_stale_m0503_replay_without_reflecting_nested_content(
    tmp_path: Path,
) -> None:
    request = build_scenario("clear").request
    payload = request.model_dump(mode="json", exclude_none=False)
    raw = payload["raw_input_result"]
    assert isinstance(raw, dict)
    raw["result_digest"] = "sha256:" + ("0" * 64)

    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M05-05/artifact-detection",
            content=canonical_json_bytes(payload),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == _HTTP_UNPROCESSABLE_CONTENT
    assert "sha256:" + ("0" * 64) not in response.text
