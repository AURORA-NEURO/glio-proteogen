"""M09-03 API, CLI, and plugin parity tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c09_complex_activity import (
    m09_03_mature_baseline_estimator as m0903,
)
from tests.modules.c09_complex_activity.test_m09_03_estimator import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_plugin_parse_once_and_run() -> None:
    request = _request()
    raw = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()
    plugin = m0903.plugin.M0903Plugin(m0903.M0903Service())
    token = plugin.validate(raw)
    built = plugin.run(token)
    assert built.result.status.value == "estimated"
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M09-03"


def test_plugin_rejects_unissued_execution_token() -> None:
    plugin = m0903.plugin.M0903Plugin(m0903.M0903Service())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_api_exports_schema_and_validates_or_estimates() -> None:
    client = TestClient(m0903.api.create_app())
    body = _request().model_dump(mode="json")
    schema = client.get("/v1/modules/M09-03/schemas/output")
    validated = client.post("/v1/modules/M09-03/validate", json=body)
    estimated = client.post("/v1/modules/M09-03/estimate", json=body)
    invalid_estimate = client.post("/v1/modules/M09-03/estimate", json={"invalid": True})
    unknown = client.get("/v1/modules/M09-03/schemas/unknown")
    assert schema.is_success
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    assert validated.is_success
    assert estimated.is_success
    assert estimated.json()["result"]["status"] == "estimated"
    assert not invalid_estimate.is_success
    assert not unknown.is_success


def test_api_sanitizes_invalid_and_denied_requests() -> None:
    client = TestClient(m0903.api.create_app())
    invalid = client.post("/v1/modules/M09-03/validate", content=b"{not-json")
    denied_body = _request().model_copy(
        update={
            "context": _request().context.model_copy(
                update={
                    "references": _request().context.references.model_copy(
                        update={
                            "consent": _request().context.references.consent.model_copy(
                                update={"state": ConsentState.WITHHELD}
                            )
                        }
                    )
                }
            )
        }
    )
    denied = client.post(
        "/v1/modules/M09-03/validate",
        json=denied_body.model_dump(mode="json"),
    )
    denied_estimate = client.post(
        "/v1/modules/M09-03/estimate",
        json=denied_body.model_dump(mode="json"),
    )
    assert not invalid.is_success
    assert not denied.is_success
    assert not denied_estimate.is_success


def test_cli_export_schema_validate_and_estimate(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    output_path = tmp_path / "result.json"
    runner = CliRunner()
    schema = runner.invoke(m0903.cli.app, ["export-schema", "request"])
    validated = runner.invoke(m0903.cli.app, ["validate", str(request_path)])
    estimated = runner.invoke(
        m0903.cli.app,
        ["estimate", str(request_path), "--output", str(output_path)],
    )
    assert schema.exit_code == 0
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["operation"] == "estimate_complex_activity_baseline"
    assert estimated.exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "estimated"


def test_cli_abstention_is_nonzero_and_never_overwrites(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request(marker="unsupported").model_dump(mode="json")),
        encoding="utf-8",
    )
    output_path = tmp_path / "result.json"
    runner = CliRunner()
    abstained = runner.invoke(
        m0903.cli.app,
        ["estimate", str(request_path), "--output", str(output_path)],
    )
    existing = runner.invoke(
        m0903.cli.app,
        ["estimate", str(request_path), "--output", str(output_path)],
    )
    assert abstained.exit_code == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "abstained"
    assert existing.exit_code != 0


def test_cli_rejects_unknown_schema_invalid_json_and_invalid_request(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0903.cli.app, ["export-schema", "unknown"])
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{not-json", encoding="utf-8")
    invalid = runner.invoke(m0903.cli.app, ["validate", str(invalid_path)])
    bad_request = tmp_path / "bad-request.json"
    bad_request.write_text(json.dumps({"invalid": True}), encoding="utf-8")
    bad_validation = runner.invoke(m0903.cli.app, ["validate", str(bad_request)])
    bad_estimate = runner.invoke(m0903.cli.app, ["estimate", str(bad_request)])
    missing = runner.invoke(m0903.cli.app, ["validate", str(tmp_path / "missing.json")])
    assert unknown.exit_code != 0
    assert invalid.exit_code != 0
    assert bad_validation.exit_code != 0
    assert bad_estimate.exit_code != 0
    assert missing.exit_code != 0
