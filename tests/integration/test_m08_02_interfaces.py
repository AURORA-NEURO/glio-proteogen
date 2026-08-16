"""API, CLI, and plugin parity tests for M08-02."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c08_transcript_protein_discordance import (
    m08_02_representation_feature_constructor as m0802,
)
from tests.modules.c08_transcript_protein_discordance.test_m08_02_representation import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404


def test_api_construct_and_schema_export_match_canonical_plugin() -> None:
    request = _request()
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()
    api = TestClient(m0802.create_app())
    response = api.post("/v1/modules/M08-02/construct", content=body)
    assert response.status_code == HTTP_OK
    payload = response.json()
    plugin_result = m0802.M0802Plugin().construct(request)
    assert payload["canonical"] == plugin_result.canonical_bytes.decode()
    schema = api.get("/v1/modules/M08-02/schemas/output")
    assert schema.status_code == HTTP_OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True


def test_api_rejects_non_strict_json_and_bad_authorization() -> None:
    api = TestClient(m0802.create_app())
    invalid = api.post("/v1/modules/M08-02/validate", content=b'{"bad": NaN}')
    assert invalid.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "detail" in invalid.json()
    denied_request = _request().model_copy(
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
    denied = api.post(
        "/v1/modules/M08-02/construct",
        json=denied_request.model_dump(mode="json"),
    )
    assert denied.status_code == HTTP_FORBIDDEN


def test_api_validate_and_unknown_schema_failures_are_sanitized() -> None:
    api = TestClient(m0802.create_app())
    request = _request()
    valid = api.post(
        "/v1/modules/M08-02/validate",
        json=request.model_dump(mode="json"),
    )
    assert valid.status_code == HTTP_OK
    malformed = api.post("/v1/modules/M08-02/construct", json={"unknown": 1})
    assert malformed.status_code == HTTP_UNPROCESSABLE_ENTITY
    unknown = api.get("/v1/modules/M08-02/schemas/not-a-contract")
    assert unknown.status_code == HTTP_NOT_FOUND


def test_plugin_requires_parse_once_token_and_accepts_json_bytes() -> None:
    plugin = m0802.M0802Plugin()
    request = _request()
    body = json.dumps(request.model_dump(mode="json"), separators=(",", ":")).encode()
    validated = plugin.validate(m0802.RepresentationSubmission(body))
    assert plugin.run(validated).result.status.value == "constructed"
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(request)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="representation submission"):
        plugin.validate(request)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(object())  # type: ignore[arg-type]


def test_cli_schema_validate_and_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request().model_dump(mode="json"), separators=(",", ":")),
        encoding="utf-8",
    )
    runner = CliRunner()
    schema = runner.invoke(m0802.cli_app, ["export-schema", "request"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M08-02"
    validated = runner.invoke(m0802.cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    output = tmp_path / "result.json"
    constructed = runner.invoke(
        m0802.cli_app, ["construct", str(request_path), "--output", str(output)]
    )
    assert constructed.exit_code == 0
    assert output.exists()
    overwrite = runner.invoke(
        m0802.cli_app, ["construct", str(request_path), "--output", str(output)]
    )
    assert overwrite.exit_code != 0


def test_cli_invalid_schema_and_request_are_bounded(tmp_path: Path) -> None:
    runner = CliRunner()
    unknown = runner.invoke(m0802.cli_app, ["export-schema", "unknown"])
    assert unknown.exit_code != 0
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text('{"unknown": 1}', encoding="utf-8")
    validated = runner.invoke(m0802.cli_app, ["validate", str(invalid_path)])
    assert validated.exit_code != 0
    bad_json = tmp_path / "bad.json"
    bad_json.write_text('{"value": NaN}', encoding="utf-8")
    constructed = runner.invoke(m0802.cli_app, ["construct", str(bad_json)])
    assert constructed.exit_code != 0
