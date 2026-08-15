from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

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
