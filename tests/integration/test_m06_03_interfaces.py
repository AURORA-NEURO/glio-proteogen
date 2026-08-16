"""API/CLI/schema parity checks for provisional M06-03."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m06_03.run import build_scenario
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m06_03 import (
    EstimateProteinAbundanceBaselineResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c06_estimation.m06_03_mature_baseline_estimator import (
    estimate_protein_abundance_baseline,
)

pytestmark = pytest.mark.integration

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK: Final = 200
HTTP_UNSUPPORTED_MEDIA: Final = 415
HTTP_UNPROCESSABLE: Final = 422
HTTP_FORBIDDEN: Final = 403
CLI_USAGE_ERROR: Final = 2

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "configuration",
    "preprocessing-policy",
    "tuning-record",
    "estimate",
    "diagnostic",
)


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_library_api_and_cli_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M06-03/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["mature-baseline", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert response.json()["$id"].endswith(f":{name}")
    assert Draft202012Validator.check_schema(response.json()) is None


def test_api_cli_and_library_emit_exact_result_parity(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-03/estimate",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["mature-baseline", "estimate", str(request_path), "--output", str(output_path)],
    )

    expected = estimate_protein_abundance_baseline(request)
    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = EstimateProteinAbundanceBaselineResult.model_validate_json(
        response.content, strict=True
    )
    cli_result = EstimateProteinAbundanceBaselineResult.model_validate_json(
        output_path.read_bytes(), strict=True
    )
    assert expected == api_result == cli_result


def test_api_rejects_wrong_media_type_and_cli_leaves_no_partial_output(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    serialized = canonical_json_bytes(request.model_dump(mode="json"))
    output_path = tmp_path / "result.json"
    request_path = tmp_path / "request.json"
    request_path.write_bytes(serialized)

    with TestClient(create_app(tmp_path / "wrong-media.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-03/estimate",
            content=serialized,
            headers={"content-type": "text/plain"},
        )
    assert response.status_code == HTTP_UNSUPPORTED_MEDIA

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text('{"request_id": "canary"}', encoding="utf-8")
    cli = CliRunner().invoke(
        cli_app,
        ["mature-baseline", "estimate", str(malformed_path), "--output", str(output_path)],
    )
    assert cli.exit_code == CLI_USAGE_ERROR
    assert not output_path.exists()


def test_api_rejects_duplicate_json_keys_without_reflection(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    body = canonical_json_bytes(request.model_dump(mode="json")).decode()
    duplicate = body[:-1] + ',"request_id":"duplicate"}'

    with TestClient(create_app(tmp_path / "duplicate.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-03/estimate",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTP_UNPROCESSABLE
    assert "request_id" not in response.text


@pytest.mark.parametrize(
    ("case_id", "expected_status"),
    [("missing", "abstained"), ("upstream-abstained", "abstained")],
)
def test_api_safe_failure_parity(
    tmp_path: Path,
    case_id: str,
    expected_status: str,
) -> None:
    request = build_scenario(case_id).request
    payload = canonical_json_bytes(request.model_dump(mode="json"))
    with TestClient(create_app(tmp_path / f"{case_id}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-03/estimate",
            content=payload,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == expected_status
    assert response.json()["estimates"] == []


def test_api_denies_controls_before_upstream_replay(tmp_path: Path) -> None:
    request = build_scenario("clear").request
    payload = json.loads(request.model_dump_json())
    payload["context"]["references"]["consent"]["state"] = "denied"
    payload["formal_state_result"] = "upstream-canary"
    body = json.dumps(payload)

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M06-03/estimate",
            content=body,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == HTTP_FORBIDDEN
    assert "upstream-canary" not in response.text
