"""Black-box schema, transport, strict-JSON, and output checks for M04-04."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

import pytest
from evals.m04_04.run import build_scenario_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_04 import (
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    M0404Plugin,
    M0404ProteoformQualityEngine,
    M0404Service,
    compute_proteoform_quality_metrics,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.integration

SCHEMA_NAMES: Final = (
    "request",
    "output",
    "policy",
    "threshold",
    "assay-profile",
    "fact-counts",
    "fact-states",
    "role-facts",
    "fact-ledger",
    "metric",
    "assay-quality",
    "finding",
    "receipt",
)
DENIED_CONTROLS: Final = (
    ("approved_configuration", "rejected"),
    ("identity_lineage", "unresolved"),
    ("provenance", "rejected"),
    ("consent", "denied"),
    ("quality", "rejected"),
    ("support", "rejected"),
    ("intended_use", "rejected"),
)
HTTP_OK: Final = 200
HTTP_FORBIDDEN: Final = 403
HTTP_PAYLOAD_TOO_LARGE: Final = 413
HTTP_UNPROCESSABLE_CONTENT: Final = 422
CLI_USAGE_ERROR: Final = 2


@pytest.fixture(scope="module")
def canonical_request() -> ComputeProteoformQualityMetricsRequest:
    return build_scenario_request()


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_library_api_and_cli_export_identical_schemas(tmp_path: Path, name: str) -> None:
    with TestClient(create_app(tmp_path / f"schema-{name}.sqlite3")) as client:
        response = client.get(f"/v1/contracts/M04-04/{name}/schema")
    cli = CliRunner().invoke(cli_app, ["proteoform-quality", "export-schema", name])

    assert response.status_code == HTTP_OK
    assert cli.exit_code == 0, cli.output
    assert response.json() == json.loads(cli.stdout) == contract_json_schema(name)  # type: ignore[arg-type]
    assert response.json()["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert response.json()["$id"].endswith(f":{name}")


def test_library_engine_service_plugin_api_and_cli_emit_exact_parity(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    serialized = canonical_json_bytes(canonical_request.model_dump(mode="json"))
    request_path = tmp_path / "quality-request.json"
    output_path = tmp_path / "quality-result.json"
    request_path.write_bytes(serialized)
    service = M0404Service()
    plugin = M0404Plugin(service)
    token = plugin.validate(serialized)

    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        [
            "proteoform-quality",
            "compute",
            str(request_path),
            "--output",
            str(output_path),
        ],
    )

    assert response.status_code == HTTP_OK, response.text
    assert cli.exit_code == 0, cli.output
    api_result = ProteoformQualityResult.model_validate_json(response.content, strict=True)
    cli_result = ProteoformQualityResult.model_validate_json(output_path.read_bytes(), strict=True)
    expected = compute_proteoform_quality_metrics(canonical_request)
    assert expected == M0404ProteoformQualityEngine().compute(canonical_request)
    assert expected == service.execute(canonical_request)
    assert expected == plugin.run(token) == api_result == cli_result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M04-04"


@pytest.mark.parametrize(("control", "state"), DENIED_CONTROLS)
def test_api_and_cli_deny_each_control_before_fact_ledger_validation(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
    control: str,
    state: str,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    payload["context"]["references"][control]["state"] = state
    payload["fact_ledger"] = "must_not_be_validated"
    serialized = json.dumps(payload)
    request_path = tmp_path / f"denied-{control}.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"denied-{control}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(tmp_path / "x")],
    )

    assert response.status_code == HTTP_FORBIDDEN
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "proteoform quality computation failed:" in cli.output
    assert "invalid request:" not in cli.output
    assert "fact_ledger" not in cli.output
    assert "Traceback" not in cli.output


@pytest.mark.parametrize(
    "case_id",
    [
        "quarantined_upstream_zero_ledger_traversal",
        "abstained_upstream_zero_ledger_traversal",
    ],
)
def test_api_and_cli_classify_safe_failure_before_hostile_ledger_validation(
    tmp_path: Path,
    case_id: str,
) -> None:
    payload = build_scenario_request(case_id).model_dump(mode="json")
    payload["fact_ledger"] = {"role_facts": "ledger-field-canary"}
    serialized = json.dumps(payload)
    request_path = tmp_path / f"{case_id}.json"
    output_path = tmp_path / f"{case_id}-result.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"{case_id}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.json() == {"detail": "M04-04 request validation failed"}
    assert cli.exit_code == 1
    assert "proteoform quality computation failed:" in cli.output
    assert "nonvalidated M04-03 input prohibits fact-ledger traversal" in cli.output
    assert "ledger-field-canary" not in response.text + cli.output
    assert "role_facts" not in response.text + cli.output
    assert not output_path.exists()


def test_api_and_cli_reject_forged_upstream_before_hostile_ledger_validation(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    payload["raw_input_result"]["result_digest"] = "sha256:" + ("f" * 64)
    payload["fact_ledger"] = {"role_facts": "ledger-field-canary"}
    serialized = json.dumps(payload)
    request_path = tmp_path / "forged-upstream.json"
    output_path = tmp_path / "forged-upstream-result.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "forged-upstream.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "ledger-field-canary" not in response.text + cli.output
    assert "fact_ledger" not in response.text + cli.output
    assert not output_path.exists()


def test_api_and_cli_reject_malformed_upstream_type_without_reflection(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    payload["raw_input_result"] = "raw-upstream-value-canary"
    payload["fact_ledger"] = {"role_facts": "ledger-field-canary"}
    serialized = json.dumps(payload)
    request_path = tmp_path / "malformed-upstream.json"
    output_path = tmp_path / "malformed-upstream-result.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / "malformed-upstream.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )

    combined = response.text + cli.output
    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.json() == {"detail": "M04-04 request validation failed"}
    assert cli.exit_code == 1
    assert "proteoform quality computation failed:" in cli.output
    assert "raw-upstream-value-canary" not in combined
    assert "ledger-field-canary" not in combined
    assert "Traceback" not in combined
    assert not output_path.exists()


@pytest.mark.parametrize("mutation", ["empty", "missing_request"])
def test_api_and_cli_reject_malformed_upstream_objects_without_internal_errors(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
    mutation: str,
) -> None:
    payload = canonical_request.model_dump(mode="json")
    if mutation == "empty":
        payload["raw_input_result"] = {}
    else:
        del payload["raw_input_result"]["request"]
    payload["fact_ledger"] = {"role_facts": "ledger-field-canary"}
    serialized = json.dumps(payload)
    request_path = tmp_path / f"malformed-upstream-{mutation}.json"
    output_path = tmp_path / f"malformed-upstream-{mutation}-result.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"malformed-upstream-{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )

    combined = response.text + cli.output
    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert isinstance(response.json().get("detail"), list)
    assert cli.exit_code == CLI_USAGE_ERROR
    assert cli.output.startswith("invalid request: ")
    assert "KeyError" not in combined
    assert "Internal Server Error" not in combined
    assert "ledger-field-canary" not in combined
    assert "Traceback" not in combined
    assert not output_path.exists()


@pytest.mark.parametrize("mutation", ["duplicate", "unknown", "coercion"])
def test_api_and_cli_reject_non_strict_json(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
    mutation: str,
) -> None:
    if mutation == "duplicate":
        serialized = canonical_request.model_dump_json().replace(
            '"operation":"compute_proteoform_quality_metrics"',
            (
                '"operation":"compute_proteoform_quality_metrics",'
                '"operation":"compute_proteoform_quality_metrics"'
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
    output_path = tmp_path / f"{mutation}-result.json"
    request_path.write_text(serialized, encoding="utf-8")

    with TestClient(create_app(tmp_path / f"{mutation}.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=serialized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "Traceback" not in cli.output
    assert not output_path.exists()


def test_api_and_cli_reject_request_at_four_mib_plus_one(tmp_path: Path) -> None:
    oversized = b"{" + (b" " * M0404_MAX_CANONICAL_REQUEST_BYTES)
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(oversized)

    with TestClient(create_app(tmp_path / "oversized.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-04/quality-metric-computation",
            content=oversized,
            headers={"content-type": "application/json"},
        )
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(tmp_path / "x")],
    )

    assert response.status_code == HTTP_PAYLOAD_TOO_LARGE
    assert cli.exit_code == CLI_USAGE_ERROR
    assert "byte limit" in cli.output


def test_cli_accepts_exact_four_mib_and_refuses_existing_output(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    serialized = canonical_json_bytes(canonical_request.model_dump(mode="json"))
    exact = serialized + (b" " * (M0404_MAX_CANONICAL_REQUEST_BYTES - len(serialized)))
    request_path = tmp_path / "exact.json"
    output_path = tmp_path / "result.json"
    request_path.write_bytes(exact)

    accepted = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )
    assert accepted.exit_code == 0, accepted.output
    ProteoformQualityResult.model_validate_json(output_path.read_bytes(), strict=True)

    output_path.write_bytes(b"existing")
    refused = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )
    assert refused.exit_code == 1
    assert output_path.read_bytes() == b"existing"


def test_cli_refuses_symlink_output_when_supported(
    tmp_path: Path,
    canonical_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    target = tmp_path / "target.json"
    request_path.write_bytes(canonical_json_bytes(canonical_request.model_dump(mode="json")))
    try:
        output_path.symlink_to(target)
    except OSError as error:
        pytest.skip(f"platform cannot create a test symlink: {error}")

    result = CliRunner().invoke(
        cli_app,
        ["proteoform-quality", "compute", str(request_path), "--output", str(output_path)],
    )
    assert result.exit_code == 1
    assert not target.exists()
