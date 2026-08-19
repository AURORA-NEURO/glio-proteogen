"""Black-box transport parity and boundary checks for M04-02."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

import pytest
from evals.m04_02.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_02 import (
    M0402_MAX_CANONICAL_REQUEST_BYTES,
    ProteoformIdentityLineageResolution,
    ReconcileProteoformIdentityLineageRequest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_02_identity_lineage import (
    M0402Plugin,
    M0402ProteoformIdentityLineageReconciler,
    M0402Service,
    reconcile_proteoform_identity_lineage,
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
    "graph",
    "finding",
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
AUTHORITY_FIELDS: Final = {
    "emits_protein_rna_discordance",
    "emits_proteogenomic_state",
    "emits_proteotype",
    "emits_protein_level_subtype",
    "infers_identity",
    "infers_consent",
    "infers_protein",
    "infers_proteoform",
    "infers_kinase_activity",
    "performs_cn_to_protein_regression",
    "performs_all_omics_fusion",
    "recommends_treatment",
    "mutates_upstream",
}
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_NOT_FOUND: Final = 404
HTTP_PAYLOAD_TOO_LARGE: Final = 413
HTTP_UNSUPPORTED_MEDIA_TYPE: Final = 415
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.fixture(scope="module")
def canonical_request() -> ReconcileProteoformIdentityLineageRequest:
    return build_scenario_request()


def _nested_values(value: object, key: str) -> list[object]:
    if isinstance(value, Mapping):
        return [
            *([value[key]] if key in value else []),
            *(nested for item in value.values() for nested in _nested_values(item, key)),
        ]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [nested for item in value for nested in _nested_values(item, key)]
    return []


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_api_and_cli_export_identical_m04_02_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M04-02/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["proteoform-lineage", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout)
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert response.json()["$id"].endswith(f":{name}")


def test_library_engine_service_plugin_api_and_cli_emit_exact_parity(
    tmp_path: Path,
    canonical_request: ReconcileProteoformIdentityLineageRequest,
) -> None:
    payload = canonical_request.model_dump_json()
    request_path = tmp_path / "proteoform-lineage.json"
    request_path.write_text(payload, encoding="utf-8")
    service = M0402Service()
    plugin = M0402Plugin(service)
    token = plugin.validate(canonical_json_bytes(canonical_request))

    with TestClient(create_app(tmp_path / "lineage.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation",
            content=payload,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteoformIdentityLineageResolution.model_validate_json(
        response.content,
        strict=True,
    )
    cli_result = ProteoformIdentityLineageResolution.model_validate_json(
        cli.stdout,
        strict=True,
    )
    expected = reconcile_proteoform_identity_lineage(canonical_request)
    assert expected == M0402ProteoformIdentityLineageReconciler().reconcile(canonical_request)
    assert expected == service.execute(canonical_request)
    assert expected == plugin.run(token) == api_result == cli_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-02"
    rendered = api_result.model_dump(mode="json")
    assert all(
        values and all(value is False for value in values)
        for field in AUTHORITY_FIELDS
        if (values := _nested_values(rendered, field))
    )


def test_api_cli_and_service_replay_verify_the_exact_result_and_reject_tampering(
    tmp_path: Path,
    canonical_request: ReconcileProteoformIdentityLineageRequest,
) -> None:
    result = M0402Service().execute(canonical_request)
    result_path = tmp_path / "lineage-result.json"
    result_path.write_bytes(canonical_json_bytes(result))

    with TestClient(create_app(tmp_path / "verify.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation/verify",
            content=result_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "verify", str(result_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert (
        ProteoformIdentityLineageResolution.model_validate_json(response.content, strict=True)
        == result
    )
    assert (
        ProteoformIdentityLineageResolution.model_validate_json(cli.stdout, strict=True) == result
    )

    tampered = result.model_dump(mode="json")
    tampered["result_digest"] = "sha256:" + ("f" * 64)
    tampered_path = tmp_path / "tampered-result.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    with TestClient(create_app(tmp_path / "tampered.sqlite3")) as client:
        rejected = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation/verify",
            content=tampered_path.read_bytes(),
            headers={"content-type": "application/json"},
        )
    rejected_cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "verify", str(tampered_path)],
    )

    assert rejected.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert rejected_cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in rejected_cli.output


@pytest.mark.parametrize(("control", "state"), DENIED_CONTROLS)
def test_api_and_cli_deny_each_control_before_lineage_validation(
    tmp_path: Path,
    canonical_request: ReconcileProteoformIdentityLineageRequest,
    control: str,
    state: str,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    payload["context"]["references"][control]["state"] = state
    payload["artifact_claims"] = "must_not_be_validated"
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-{control}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{control}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert "accepted upstream controls" in response.json()["detail"]
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "artifact_claims" not in cli.output
    assert "Traceback" not in cli.output


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "coercion"])
def test_api_and_cli_reject_non_strict_json_consistently(
    tmp_path: Path,
    canonical_request: ReconcileProteoformIdentityLineageRequest,
    mutation: str,
) -> None:
    if mutation == "duplicate":
        serialized = canonical_request.model_dump_json().replace(
            '"operation":"reconcile_proteoform_identity_lineage"',
            (
                '"operation":"reconcile_proteoform_identity_lineage",'
                '"operation":"reconcile_proteoform_identity_lineage"'
            ),
            1,
        )
    else:
        payload = canonical_request.model_dump(mode="json")
        if mutation == "unknown":
            payload["unexpected"] = "rejected"
        else:
            payload["contract_version"] = 1
        serialized = json.dumps(payload)
    request_path = tmp_path / f"{mutation}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in cli.output


def test_api_and_cli_reject_request_at_four_mib_plus_one(tmp_path: Path) -> None:
    oversized = b"{" + (b" " * M0402_MAX_CANONICAL_REQUEST_BYTES)
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "oversized.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in cli.output
    assert "Traceback" not in cli.output


def test_api_and_cli_accept_valid_json_at_exact_four_mib_raw_boundary(
    tmp_path: Path,
    canonical_request: ReconcileProteoformIdentityLineageRequest,
) -> None:
    serialized = canonical_request.model_dump_json().encode("utf-8")
    exact = serialized + (b" " * (M0402_MAX_CANONICAL_REQUEST_BYTES - len(serialized)))
    assert len(exact) == M0402_MAX_CANONICAL_REQUEST_BYTES
    request_path = tmp_path / "exact-boundary.json"
    request_path.write_bytes(exact)

    with TestClient(create_app(tmp_path / "exact-boundary.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation",
            content=exact,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-lineage", "reconcile", str(request_path)],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    assert json.loads(cli.stdout)["result_digest"] == response.json()["result_digest"]


def test_api_rejects_wrong_media_type_unknown_schema_and_binary_route(
    tmp_path: Path,
    canonical_request: ReconcileProteoformIdentityLineageRequest,
) -> None:
    payload = canonical_request.model_dump_json()
    with TestClient(create_app(tmp_path / "media.sqlite3")) as client:
        media = client.post(
            "/v1/modules/M04-02/identity-lineage-reconciliation",
            content=payload,
            headers={"content-type": "application/octet-stream"},
        )
        schema = client.get("/v1/contracts/M04-02/not-a-contract/schema")
        binary = client.post("/v1/modules/M04-02/binary", content=b"opaque")

    assert media.status_code == HTTP_UNSUPPORTED_MEDIA_TYPE
    assert schema.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert binary.status_code == HTTP_NOT_FOUND
