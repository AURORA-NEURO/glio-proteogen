"""Black-box API, CLI, schema, and library parity for provisional M05-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from evals.m05_06.run import build_scenario
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_06 import contract_json_schema
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Plugin,
    M0506Service,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_HTTP_UNSUPPORTED_MEDIA_TYPE = 415

_SCHEMA_NAMES = (
    "request",
    "output",
    "artifact-receipt",
    "support-ledger",
    "support-observation",
    "support-invariant",
    "policy",
    "profile",
    "normalization-stage",
    "level-shift",
    "stage-transformation",
    "transformation-manifest",
    "analysis",
    "receipt",
)


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_api_cli_and_library_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.get(f"/v1/contracts/M05-06/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["ptm-localization-harmonization", "export-schema", name],
    )

    assert response.status_code == _HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]


def test_library_plugin_api_and_cli_are_result_peers(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    service = M0506Service()
    library_result = service.execute(request)
    plugin_result = M0506Plugin(service).run(
        M0506Plugin(service).validate(canonical_json_bytes(request))
    )
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(request))
    output_path = tmp_path / "result.json"

    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M05-06/harmonization",
            content=canonical_json_bytes(request),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        [
            "ptm-localization-harmonization",
            "harmonize",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )

    assert response.status_code == _HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert plugin_result == library_result
    assert response.json() == library_result.model_dump(mode="json")
    assert output_path.read_bytes() == canonical_json_bytes(library_result)


def test_api_requires_exact_json_media_type(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M05-06/harmonization",
            content=canonical_json_bytes(request),
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == _HTTP_UNSUPPORTED_MEDIA_TYPE


def test_api_denies_missing_authority_before_nested_replay(tmp_path: Path) -> None:
    request = build_scenario("clear").request.model_dump(mode="json")
    context = request["context"]
    assert isinstance(context, dict)
    references = context["references"]
    assert isinstance(references, dict)
    references["consent"]["state"] = "denied"

    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.post(
            "/v1/modules/M05-06/harmonization",
            content=canonical_json_bytes(request),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == _HTTP_FORBIDDEN
