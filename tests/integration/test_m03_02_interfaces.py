"""Black-box parity and hostile-ingress checks for the M03-02 transports."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final

import pytest
from evals.m03_02.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m03_02.v1 import (
    ProteinInferenceIdentityLineageResolution,
)
from glio_proteogen.modules.c03_protein_inference.m03_02_identity_lineage import (
    M0302Service,
    ProteinIdentityLineageAuthorizationError,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "artifact-claim",
    "derivation",
    "cn-receipt",
    "graph",
    "receipt",
)
PRIVACY_CANARIES: Final = {
    "direct_patient_identifier",
    "raw_identity_token",
    "peptide_sequence",
    "raw_copy_number_value",
    "raw_protein_abundance",
}
FORBIDDEN_CLAIMS: Final = {
    "observed_peptide",
    "protein_accession",
    "complex_activity_inference",
    "protein_subtype",
    "proteotype",
    "kinase_activity",
    "omics_fusion",
    "treatment_recommendation",
    "clinical_decision",
}
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_PAYLOAD_TOO_LARGE: Final = 413
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2
M0302_MAX_REQUEST_BYTES: Final = 4 * 1024 * 1024


class _HostileRequest(Mapping[str, object]):
    """Expose context while failing any attempt to traverse governed inputs."""

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
def test_api_and_cli_export_identical_m03_02_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M03-02/{name}/schema")
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-lineage", "export-schema", name],
    )

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_service_api_and_cli_emit_exact_same_private_result(tmp_path: Path) -> None:
    request = build_scenario_request("canonical")
    payload = request.model_dump_json()
    request_path = tmp_path / "protein-inference-lineage.json"
    request_path.write_text(payload, encoding="utf-8")
    service_result = M0302Service().execute(request)

    with TestClient(create_app(tmp_path / "lineage.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-02/identity-lineage-reconciliation",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteinInferenceIdentityLineageResolution.model_validate_json(
        response.content,
        strict=True,
    )
    cli_result = ProteinInferenceIdentityLineageResolution.model_validate_json(
        cli.stdout,
        strict=True,
    )
    assert service_result == api_result == cli_result
    emitted = api_result.model_dump(mode="json")
    rendered = json.dumps(emitted, sort_keys=True)
    assert not PRIVACY_CANARIES.intersection(_nested_keys(emitted))
    assert not FORBIDDEN_CLAIMS.intersection(_nested_keys(emitted))
    assert not any(canary in rendered for canary in PRIVACY_CANARIES)
    assert not any(claim in rendered for claim in FORBIDDEN_CLAIMS)


def test_api_and_cli_authorize_before_hostile_input_traversal(tmp_path: Path) -> None:
    payload = build_scenario_request("canonical").model_dump(mode="json")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["identity_resolution"] = "must_not_be_traversed"
    payload["protocol_result"] = "must_not_be_traversed"
    payload["artifact_claims"] = "must_not_be_traversed"
    serialized = json.dumps(payload)
    request_path = tmp_path / "denied-hostile.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "denied.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-02/identity-lineage-reconciliation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert "accepted upstream controls" in response.json()["detail"]
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "must_not_be_traversed" not in cli.output
    assert "Traceback" not in cli.output


def test_service_authorizes_before_mapping_traversal() -> None:
    context = build_scenario_request("canonical").context.model_dump(mode="json")
    context["references"]["support"]["state"] = "abstained"

    with pytest.raises(ProteinIdentityLineageAuthorizationError):
        M0302Service.validate_request(_HostileRequest(context))


@pytest.mark.parametrize(
    ("mutation", "expected_term"),
    [
        ("duplicate", "duplicate"),
        ("nonfinite", "finite"),
        ("unknown", "extra_forbidden"),
        ("coercion", "int_type"),
    ],
)
def test_api_and_cli_reject_non_strict_json(
    tmp_path: Path,
    mutation: str,
    expected_term: str,
) -> None:
    request = build_scenario_request("canonical")
    if mutation in {"duplicate", "nonfinite"}:
        serialized = request.model_dump_json()
        operation = '"operation":"reconcile_protein_inference_identity_lineage"'
        if mutation == "duplicate":
            serialized = serialized.replace(operation, f"{operation},{operation}", 1)
        else:
            serialized = serialized.replace(
                '"informative_feature_count":12',
                '"informative_feature_count":NaN',
                1,
            )
    else:
        payload: dict[str, Any] = copy.deepcopy(request.model_dump(mode="json"))
        if mutation == "unknown":
            payload["unexpected_private_payload"] = "must-not-pass"
        else:
            payload["cn_receipts"][0]["informative_feature_count"] = "12"
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-02/identity-lineage-reconciliation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert expected_term in cli.output.lower()
    assert "Traceback" not in cli.output


def test_api_and_cli_reject_first_byte_past_four_mib(tmp_path: Path) -> None:
    oversized = b"{" + (b" " * (M0302_MAX_REQUEST_BYTES - 1)) + b"}"
    assert len(oversized) == M0302_MAX_REQUEST_BYTES + 1
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "oversized.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M03-02/identity-lineage-reconciliation",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["protein-inference-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in cli.output
    assert "Traceback" not in cli.output
