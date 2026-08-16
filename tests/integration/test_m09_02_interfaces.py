from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c09_complex_activity import (
    m09_02_representation_feature_constructor as m0902,
)
from tests.modules.c09_complex_activity.test_m09_02_constructor import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_plugin_parse_once_and_run() -> None:
    request = _request()
    raw = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()
    plugin = m0902.plugin.M0902Plugin(m0902.M0902Service())
    token = plugin.validate(raw)
    built = plugin.run(token)
    assert built.result.status.value == "constructed"


def test_plugin_rejects_unissued_execution_token() -> None:
    plugin = m0902.plugin.M0902Plugin(m0902.M0902Service())
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_cli_export_schema_and_validate(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    schema = runner.invoke(m0902.cli.app, ["export-schema", "request"])
    validated = runner.invoke(m0902.cli.app, ["validate", str(request_path)])
    assert schema.exit_code == 0
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["operation"] == "construct_complex_activity_representation"


def test_api_exports_schema() -> None:
    response = TestClient(m0902.api.create_app()).get("/v1/modules/M09-02/schemas/output")
    assert response.is_success
    assert response.json()["x-glio-contract"]["provisionalAbi"] is True


def test_api_validates_and_constructs_strict_body() -> None:
    client = TestClient(m0902.api.create_app())
    body = _request().model_dump(mode="json")
    validated = client.post("/v1/modules/M09-02/validate", json=body)
    constructed = client.post("/v1/modules/M09-02/construct", json=body)
    unknown = client.get("/v1/modules/M09-02/schemas/unknown")
    assert validated.is_success
    assert constructed.is_success
    assert constructed.json()["result"]["status"] == "constructed"
    assert not unknown.is_success


def test_api_sanitizes_invalid_and_denied_requests() -> None:
    client = TestClient(m0902.api.create_app())
    invalid = client.post("/v1/modules/M09-02/validate", content=b"{not-json")
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
    denied = client.post("/v1/modules/M09-02/validate", json=denied_body.model_dump(mode="json"))
    assert not invalid.is_success
    assert not denied.is_success


def test_cli_construct_writes_new_result_and_abstains(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    output_path = tmp_path / "result.json"
    runner = CliRunner()
    constructed = runner.invoke(
        m0902.cli.app,
        ["construct", str(request_path), "--output", str(output_path)],
    )
    assert constructed.exit_code == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "constructed"
    unsupported_path = tmp_path / "unsupported.json"
    unsupported_path.write_text(
        json.dumps(_request(marker="unsupported").model_dump(mode="json")), encoding="utf-8"
    )
    abstained = runner.invoke(m0902.cli.app, ["construct", str(unsupported_path)])
    assert abstained.exit_code == 1
    existing = runner.invoke(
        m0902.cli.app,
        ["construct", str(request_path), "--output", str(output_path)],
    )
    assert existing.exit_code != 0
    unknown = runner.invoke(m0902.cli.app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
