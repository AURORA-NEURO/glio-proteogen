"""FastAPI and Typer parity checks for M19-02."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1902 import app, m1902_app
from glio_proteogen.contracts.m19_02 import contract_json_schema
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from tests.contract.test_m19_02_deep import _request

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

HTTP_OK = 200
HTTP_FORBIDDEN = 403
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_UNPROCESSABLE_ENTITY = 422
HTTP_NOT_FOUND = 404
CLI_SCHEMA_ERROR = 2


def test_fastapi_align_and_verify_are_canonical_and_strict() -> None:
    client = TestClient(app)
    request_bytes = canonical_json_bytes(_request())
    response = client.post(
        "/v1/modules/M19-02/align",
        content=request_bytes,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_OK
    result_bytes = canonical_json_bytes(response.json())
    verified = client.post(
        "/v1/modules/M19-02/verify",
        content=result_bytes,
        headers={"content-type": "application/json"},
    )
    assert verified.status_code == HTTP_OK
    assert verified.json() == response.json()
    schema_response = client.get("/v1/m19-02/schema/output").json()
    expected_schema = contract_json_schema("output")
    assert schema_response["$id"] == expected_schema["$id"]
    expected_metadata = cast("dict[str, object]", expected_schema["x-glio-contract"])
    assert schema_response["x-glio-contract"] == expected_metadata


def test_fastapi_rejects_wrong_media_type_and_duplicate_keys() -> None:
    client = TestClient(app)
    assert (
        client.post(
            "/v1/modules/M19-02/align", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA_TYPE
    )
    duplicate = b'{"request_id":"a","request_id":"b"}'
    response = client.post(
        "/v1/modules/M19-02/align",
        content=duplicate,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "invalid JSON request" in response.text


def test_fastapi_sanitizes_validation_auth_and_replay_errors() -> None:
    client = TestClient(app)
    request = _request()
    invalid = client.post(
        "/v1/modules/M19-02/align",
        content=canonical_json_bytes(request.model_copy(update={"observations": ()})),
        headers={"content-type": "application/json"},
    )
    assert invalid.status_code == HTTP_UNPROCESSABLE_ENTITY
    denied = request.model_copy(
        update={
            "context": request.context.model_copy(
                update={
                    "references": request.context.references.model_copy(
                        update={
                            "consent": request.context.references.consent.model_copy(
                                update={"state": ConsentState.UNKNOWN}
                            )
                        }
                    )
                }
            )
        }
    )
    validation = client.post(
        "/v1/modules/M19-02/align",
        content=canonical_json_bytes(denied),
        headers={"content-type": "application/json"},
    )
    assert validation.status_code == HTTP_FORBIDDEN
    assert client.get("/v1/m19-02/schema/not-a-schema").status_code == HTTP_NOT_FOUND
    assert (
        client.post(
            "/v1/modules/M19-02/verify", content=b"{}", headers={"content-type": "text/plain"}
        ).status_code
        == HTTP_UNSUPPORTED_MEDIA_TYPE
    )
    assert (
        client.post(
            "/v1/modules/M19-02/verify",
            content=b"{}",
            headers={"content-type": "application/json"},
        ).status_code
        == HTTP_UNPROCESSABLE_ENTITY
    )


def test_fastapi_alignment_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(app)

    def _fail(_request: object) -> None:
        raise ValueError("internal details must not escape")  # noqa: TRY003

    monkeypatch.setattr("glio_proteogen.adapters.m1902._SERVICE.align", _fail)
    response = client.post(
        "/v1/modules/M19-02/align",
        content=canonical_json_bytes(_request()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == HTTP_UNPROCESSABLE_ENTITY
    assert "internal details" not in response.text


def test_typer_align_verify_and_no_overwrite_are_executable(tmp_path: Path) -> None:
    runner = CliRunner()
    schema = runner.invoke(m1902_app, ["export-schema", "output"])
    assert schema.exit_code == 0
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M19-02"
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request()))
    result_path = tmp_path / "result.json"
    stdout_result = runner.invoke(m1902_app, ["align", str(request_path)])
    assert stdout_result.exit_code == 0
    aligned = runner.invoke(
        m1902_app,
        ["align", str(request_path), "--output", str(result_path)],
    )
    assert aligned.exit_code == 0
    assert result_path.exists()
    verified = runner.invoke(m1902_app, ["verify", str(result_path)])
    assert verified.exit_code == 0
    duplicate = runner.invoke(
        m1902_app,
        ["align", str(request_path), "--output", str(result_path)],
    )
    assert duplicate.exit_code != 0
    assert "output already exists" in duplicate.output
    invalid_schema = runner.invoke(m1902_app, ["export-schema", "not-a-schema"])
    assert invalid_schema.exit_code == CLI_SCHEMA_ERROR
    result_path.write_text("{}", encoding="utf-8")
    invalid_verify = runner.invoke(m1902_app, ["verify", str(result_path)])
    assert invalid_verify.exit_code == 1
    invalid_request = tmp_path / "invalid.json"
    invalid_request.write_text("{}", encoding="utf-8")
    invalid_align = runner.invoke(m1902_app, ["align", str(invalid_request)])
    assert invalid_align.exit_code == 1
