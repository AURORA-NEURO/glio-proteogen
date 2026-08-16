"""Black-box parity and boundary checks for the thin M03-01 transports."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Final

import pytest
from evals.m03_01.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_01.v1 import (
    ProteinInferenceProtocolConformanceResult,
)
from glio_proteogen.modules.c03_protein_inference.m03_01_protocol_metadata import (
    M0301Service,
    ProteinInferenceProtocolAuthorizationError,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES = (
    "request",
    "output",
    "protocol",
    "profile",
    "search-space",
    "ambiguity",
    "receipt",
)
FORBIDDEN_RESULT_KEYS: Final = {
    "activity_score",
    "clinical_decision",
    "complex_activity_inference",
    "kinase_activity",
    "omics_fusion",
    "protein_subtype",
    "proteotype",
    "treatment_recommendation",
}
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


class _HostileRequest(Mapping[str, object]):
    """Expose authorization context while failing any attempted protocol traversal."""

    def __init__(self, context: object) -> None:
        self._context = context

    def __getitem__(self, key: str) -> object:
        if key == "context":
            return self._context
        raise AssertionError

    def __iter__(self) -> Iterator[str]:
        raise AssertionError

    def __len__(self) -> int:
        raise AssertionError


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
def test_api_and_cli_export_identical_m03_01_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-01/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-protocol", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_service_api_and_cli_emit_one_closed_private_result(tmp_path: Path) -> None:
    request = build_scenario_request("canonical")
    payload = request.model_dump_json()
    request_path = tmp_path / "protein-inference-protocol.json"
    request_path.write_text(payload, encoding="utf-8")
    service_result = M0301Service().execute(request)

    with TestClient(create_app(tmp_path / "protocol.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-01/protocol-conformance",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteinInferenceProtocolConformanceResult.model_validate_json(
        response.content,
        strict=True,
    )
    cli_result = ProteinInferenceProtocolConformanceResult.model_validate_json(
        cli.stdout,
        strict=True,
    )
    assert service_result == api_result == cli_result
    assert api_result.disposition.value == "conformant"
    assert api_result.result_digest != "sha256:" + ("0" * 64)
    assert api_result.infers_protein is False
    assert api_result.infers_proteoform is False
    assert api_result.infers_isoform is False
    assert api_result.infers_glioma_specific_biology is False
    assert not FORBIDDEN_RESULT_KEYS.intersection(
        _nested_keys(api_result.model_dump(mode="json"))
    )


def test_api_and_cli_reject_a_true_glioma_claim_at_request_boundary(tmp_path: Path) -> None:
    payload = build_scenario_request("canonical").model_dump(mode="json")
    payload["infers_glioma_specific_biology"] = True
    serialized = json.dumps(payload)
    request_path = tmp_path / "forbidden-claim.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "forbidden-claim.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-01/protocol-conformance",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in cli.output


def test_api_and_cli_authorize_before_hostile_protocol_traversal(tmp_path: Path) -> None:
    payload = build_scenario_request("canonical").model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["protocol_schema"] = "must_not_be_traversed"
    serialized = json.dumps(payload)
    request_path = tmp_path / "denied-hostile.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-01/protocol-conformance",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert "accepted upstream controls" in response.json()["detail"]
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "protocol_schema" not in cli.output
    assert "Traceback" not in cli.output


def test_service_authorizes_before_mapping_traversal() -> None:
    context = build_scenario_request("canonical").context.model_dump(mode="json")
    context["references"]["consent"]["state"] = "withheld"

    with pytest.raises(ProteinInferenceProtocolAuthorizationError):
        M0301Service.validate_request(_HostileRequest(context))


def test_duplicate_raw_json_is_rejected_consistently(tmp_path: Path) -> None:
    payload = build_scenario_request("canonical").model_dump_json()
    operation = '"operation":"evaluate_protein_inference_protocol"'
    duplicate = payload.replace(operation, f"{operation},{operation}", 1)
    request_path = tmp_path / "duplicate.json"
    request_path.write_text(duplicate, encoding="utf-8")

    with TestClient(create_app(tmp_path / "duplicate.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-01/protocol-conformance",
            content=duplicate,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-protocol", "validate", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "duplicate" in cli.output.lower()
    assert "Traceback" not in cli.output
