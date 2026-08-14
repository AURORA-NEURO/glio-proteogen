"""Black-box transport parity and strict boundary checks for M05-01."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m05_01.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m05_01 import (
    M0501_MAX_CANONICAL_REQUEST_BYTES,
    PtmLocalizationProtocolConformanceResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    M0501Plugin,
    M0501PtmLocalizationProtocolEngine,
    M0501Service,
    evaluate_ptm_localization_protocol,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "protocol",
    "profile",
    "reference-bundle",
    "reference-cardinality",
    "controlled-vocabulary",
    "unit-policy",
    "metadata-field-policy",
    "compatibility-policy",
    "assay-specimen-policy",
    "variant-peptide-handoff",
    "receipt",
)
DENIED_CONTROLS: Final = (
    ("approved_configuration", "rejected"),
    ("identity_lineage", "unresolved"),
    ("provenance", "rejected"),
    ("consent", "withheld"),
    ("quality", "rejected"),
    ("support", "rejected"),
    ("intended_use", "rejected"),
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_PAYLOAD_TOO_LARGE: Final = 413
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m05_01_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M05-01/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["m05-01-export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert response.json()["$id"].endswith(f":{name}")


def test_library_engine_service_plugin_api_and_cli_emit_exact_parity(tmp_path: Path) -> None:
    request = build_scenario_request()
    payload = request.model_dump_json()
    request_path = tmp_path / "ptm-protocol.json"
    request_path.write_text(payload, encoding="utf-8")
    service = M0501Service()
    plugin = M0501Plugin(service)
    token = plugin.validate(canonical_json_bytes(request))

    with TestClient(create_app(tmp_path / "protocol.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-01/protocol-conformance",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m05-01-validate", str(request_path)])

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = PtmLocalizationProtocolConformanceResult.model_validate_json(
        response.content, strict=True
    )
    cli_result = PtmLocalizationProtocolConformanceResult.model_validate_json(
        cli.stdout, strict=True
    )
    expected = evaluate_ptm_localization_protocol(request)
    assert expected == M0501PtmLocalizationProtocolEngine().evaluate(request)
    assert expected == service.execute(request) == plugin.run(token) == api_result == cli_result


@pytest.mark.parametrize(("control", "state"), DENIED_CONTROLS)
def test_api_and_cli_deny_each_control_before_protocol_validation(
    tmp_path: Path,
    control: str,
    state: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="json")
    payload["context"]["references"][control]["state"] = state
    payload["protocol_schema"] = "must_not_be_validated"
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-{control}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{control}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-01/protocol-conformance",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m05-01-validate", str(request_path)])

    assert response.status_code == HTTP_FORBIDDEN
    assert "accepted upstream controls" in response.json()["detail"]
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "protocol_schema" not in cli.output
    assert "Traceback" not in cli.output


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "coercion"])
def test_api_and_cli_reject_non_strict_json_consistently(
    tmp_path: Path,
    mutation: str,
) -> None:
    request = build_scenario_request()
    if mutation == "duplicate":
        serialized = request.model_dump_json().replace(
            '"operation":"evaluate_ptm_localization_protocol"',
            (
                '"operation":"evaluate_ptm_localization_protocol",'
                '"operation":"evaluate_ptm_localization_protocol"'
            ),
            1,
        )
    else:
        payload = request.model_dump(mode="json")
        if mutation == "unknown":
            payload["unexpected"] = True
        else:
            payload["contract_version"] = 1
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-01/protocol-conformance",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m05-01-validate", str(request_path)])

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in cli.output


def test_api_and_cli_reject_request_above_four_mib(tmp_path: Path) -> None:
    oversized = b"{" + (b" " * M0501_MAX_CANONICAL_REQUEST_BYTES)
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "oversized.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M05-01/protocol-conformance",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(cli_app, ["m05-01-validate", str(request_path)])

    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in cli.output
    assert "Traceback" not in cli.output


def test_api_rejects_wrong_media_type_and_unknown_schema(tmp_path: Path) -> None:
    payload = build_scenario_request().model_dump_json()
    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        media = client.post(
            "/v1/modules/M05-01/protocol-conformance",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        schema = client.get("/v1/contracts/M05-01/not-a-contract/schema")

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert schema.status_code == HTTP_UNPROCESSABLE_CONTENT
