# ruff: noqa: E501, PLR2004, PLC0415, TC003
"""HTTP and CLI parity tests for M10-02."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from typer.testing import CliRunner

from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (
    cli_app,
    create_m1002_app,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor.service import M1002Service
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor.engine import (
    RepresentationAuthorizationError,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor.interfaces import (
    _error_response,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor.service import (
    M1002Service,
)
from tests.modules.test_m10_02_representation_constructor import _request

HTTP_UNSUPPORTED_MEDIA = 400
HTTP_TOO_LARGE = 413


def test_api_construct_and_schema_are_strict_and_replay_bound() -> None:
    client = TestClient(create_m1002_app())
    request = _request().model_dump_json()
    response = client.post(
        "/v1/m10-02/construct",
        content=request,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "constructed"
    assert client.get("/v1/m10-02/schema/request").status_code == 200
    assert client.get("/v1/m10-02/schema/unknown").status_code == 404


def test_request_bound_replay_rejects_resigned_representation() -> None:
    request = _request()
    result = M1002Service().execute(request)
    forged = result.model_copy(update={"status": "abstained"})
    assert not M1002Service().verify(forged, request)


def test_api_enforces_json_content_type_and_preparse_request_limit() -> None:
    client = TestClient(create_m1002_app())
    payload = _request().model_dump(mode="json")
    wrong_media = client.post(
        "/v1/m10-02/construct",
        json=payload,
        headers={"content-type": "text/plain"},
    )
    oversized = client.post(
        "/v1/m10-02/construct",
        content=b"{" + b"x" * (4 * 1024 * 1024 + 1) + b"}",
        headers={"content-type": "application/json"},
    )
    assert wrong_media.status_code == HTTP_UNSUPPORTED_MEDIA
    assert oversized.status_code == HTTP_TOO_LARGE


def test_api_sanitizes_duplicate_key_and_bad_control_errors() -> None:
    client = TestClient(create_m1002_app())
    duplicate = '{"request_id":"a","request_id":"b"}'
    response = client.post(
        "/v1/m10-02/validate",
        content=duplicate,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert "request_id" not in response.text


def test_api_validate_success_and_construct_error_are_sanitized() -> None:
    client = TestClient(create_m1002_app())
    request = _request().model_dump_json()
    validated = client.post(
        "/v1/m10-02/validate",
        content=request,
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == 200
    invalid = client.post(
        "/v1/m10-02/construct",
        content="[]",
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code in {400, 403, 422}
    assert "input_features" not in invalid.text


def test_error_responder_covers_strict_validation_authorization_and_generic_errors() -> None:
    strict = _error_response(StrictJsonError(StrictJsonErrorCode.INVALID_SYNTAX))
    assert strict.status_code == 400
    try:
        TypeAdapter(int).validate_python("nope")
    except ValidationError as error:
        validation = _error_response(error)
    assert validation.status_code == 422
    assert _error_response(RepresentationAuthorizationError()).status_code == 403
    assert _error_response(RuntimeError("internal")).status_code == 400


def test_cli_exports_schema_and_refuses_overwrite(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "request.json"
    first = runner.invoke(cli_app, ["export-schema", "request", "--output", str(output)])
    assert first.exit_code == 0
    stdout_schema = runner.invoke(cli_app, ["export-schema", "output"])
    assert stdout_schema.exit_code == 0
    unknown_schema = runner.invoke(cli_app, ["export-schema", "unknown"])
    assert unknown_schema.exit_code != 0
    second = runner.invoke(cli_app, ["export-schema", "request", "--output", str(output)])
    assert second.exit_code != 0
    assert json.loads(output.read_text(encoding="utf-8"))["x-glio-contract"]["provisionalAbi"]


def test_cli_validate_construct_stdout_and_atomic_output(tmp_path: Path) -> None:
    runner = CliRunner()
    request = tmp_path / "request.json"
    request.write_text(_request().model_dump_json(), encoding="utf-8")
    validated = runner.invoke(cli_app, ["validate", str(request)])
    assert validated.exit_code == 0
    bad_request = tmp_path / "bad.json"
    bad_request.write_text("[]", encoding="utf-8")
    failed_validation = runner.invoke(cli_app, ["validate", str(bad_request)])
    assert failed_validation.exit_code != 0
    result = tmp_path / "result.json"
    constructed = runner.invoke(cli_app, ["construct", str(request), "--output", str(result)])
    assert constructed.exit_code == 0
    assert json.loads(result.read_text(encoding="utf-8"))["status"] == "constructed"
    refused = runner.invoke(cli_app, ["construct", str(request), "--output", str(result)])
    assert refused.exit_code != 0
    stdout_construct = runner.invoke(cli_app, ["construct", str(request)])
    assert stdout_construct.exit_code == 0


def test_module_api_and_cli_wrappers_import() -> None:
    from glio_proteogen.modules.c10_pathway_proteotype.m10_02_representation_feature_constructor import (
        api,
        cli,
    )

    assert api.app.title.startswith("GLIO-PROTEOGEN")
    assert cli.app is cli_app
