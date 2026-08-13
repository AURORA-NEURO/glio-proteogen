"""Black-box parity and hostile-boundary checks for M04-01 transports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

import pytest
from evals.m04_01.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_01 import (
    M0401_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformProtocolConformanceResult,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_01_protocol_metadata import (
    M0401Plugin,
    M0401ProteoformProtocolEngine,
    M0401Service,
    evaluate_proteoform_protocol,
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
    "coordinate-policy",
    "evidence-eligibility-policy",
    "isoform-discrimination-policy",
    "modification-localization-policy",
    "quantification-policy",
    "discordance-handoff",
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
FORBIDDEN_RESULT_KEYS: Final = {
    "clinical_decision",
    "kinase_activity",
    "protein_rna_discordance",
    "proteogenomic_state",
    "protein_subtype",
    "proteoform_inference",
    "proteotype",
    "treatment_recommendation",
}
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_PAYLOAD_TOO_LARGE: Final = 413
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, Mapping):
        return {
            *(str(key) for key in value),
            *(nested for item in value.values() for nested in _nested_keys(item)),
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return {nested for item in value for nested in _nested_keys(item)}
    return set()


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m04_01_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M04-01/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["proteoform-protocol", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert response.json()["$id"].endswith(f":{name}")


def test_library_engine_service_plugin_api_and_cli_emit_exact_parity(tmp_path: Path) -> None:
    request = build_scenario_request()
    payload = request.model_dump_json()
    request_path = tmp_path / "proteoform-protocol.json"
    request_path.write_text(payload, encoding="utf-8")
    service = M0401Service()
    plugin = M0401Plugin(service)
    token = plugin.validate(canonical_json_bytes(request))

    with TestClient(create_app(tmp_path / "protocol.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-01/protocol-conformance",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteoformProtocolConformanceResult.model_validate_json(
        response.content,
        strict=True,
    )
    cli_result = ProteoformProtocolConformanceResult.model_validate_json(
        cli.stdout,
        strict=True,
    )
    expected = evaluate_proteoform_protocol(request)
    assert expected == M0401ProteoformProtocolEngine().evaluate(request)
    assert expected == service.execute(request) == plugin.run(token) == api_result == cli_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-01"
    assert not FORBIDDEN_RESULT_KEYS.intersection(_nested_keys(api_result.model_dump(mode="json")))


@pytest.mark.parametrize(("control", "state"), DENIED_CONTROLS)
def test_api_and_cli_deny_each_control_before_governed_validation(
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
            "/v1/modules/M04-01/protocol-conformance",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-protocol", "validate", str(request_path)],
    )

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
            '"operation":"evaluate_proteoform_protocol"',
            (
                '"operation":"evaluate_proteoform_protocol",'
                '"operation":"evaluate_proteoform_protocol"'
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
            "/v1/modules/M04-01/protocol-conformance",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in cli.output


def test_api_and_cli_reject_request_at_four_mib_plus_one(tmp_path: Path) -> None:
    oversized = b"{" + (b" " * M0401_MAX_CANONICAL_REQUEST_BYTES)
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "oversized.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-01/protocol-conformance",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in cli.output
    assert "Traceback" not in cli.output


def test_api_rejects_wrong_media_type_and_unknown_schema(tmp_path: Path) -> None:
    payload = build_scenario_request().model_dump_json()
    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        media = client.post(
            "/v1/modules/M04-01/protocol-conformance",
            content=payload,
            headers={"content-type": "text/plain"},
        )
        schema = client.get("/v1/contracts/M04-01/not-a-contract/schema")

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert schema.status_code == HTTP_UNPROCESSABLE_CONTENT
