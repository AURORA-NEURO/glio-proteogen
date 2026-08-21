"""API, CLI, and plugin parity tests for provisional M10-07."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction.api import (  # noqa: E501
    create_app,
)
from glio_proteogen.modules.c10_pathway_proteotype.m10_07_calibration_selective_prediction.cli import (  # noqa: E501
    app as cli_app,
)
from tests.modules.test_m10_07_runtime import _request

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_UNSUPPORTED_MEDIA = 415
_HTTP_TOO_LARGE = 413


def test_api_validate_execute_verify_and_schema_are_canonical() -> None:
    request = _request()
    body = request.model_dump_json()
    with TestClient(create_app()) as client:
        schema = client.get("/v1/modules/M10-07/schemas/output")
        assert schema.status_code == _HTTP_OK
        assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
        headers = {"content-type": "application/json"}
        validated = client.post("/v1/modules/M10-07/validate", content=body, headers=headers)
        assert validated.status_code == _HTTP_OK
        executed = client.post("/v1/modules/M10-07/execute", content=body, headers=headers)
        assert executed.status_code == _HTTP_OK
        envelope = executed.json()
        assert envelope["result"]["status"] == "calibrated"
        verified = client.post(
            "/v1/modules/M10-07/verify",
            json={"result": envelope["result"], "canonical": envelope["canonical"]},
            headers=headers,
        )
        assert verified.status_code == _HTTP_OK
        assert verified.json()["verified"] is True


def test_api_request_bound_verify_rejects_resigned_semantic_result() -> None:
    request = _request()
    with TestClient(create_app()) as client:
        built = client.post(
            "/v1/modules/M10-07/execute",
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        ).json()
        forged = dict(built["result"])
        forged["status"] = "abstained"
        response = client.post(
            "/v1/modules/M10-07/verify",
            json={
                "request": request.model_dump(mode="json"),
                "result": forged,
                "canonical": forged,
            },
            headers={"content-type": "application/json"},
        )
        assert response.status_code == _HTTP_OK
        assert response.json()["verified"] is False


def test_api_sanitizes_invalid_json_and_replay_tampering() -> None:
    request = _request()
    with TestClient(create_app()) as client:
        headers = {"content-type": "application/json"}
        invalid = client.post("/v1/modules/M10-07/validate", content=b"{not-json", headers=headers)
        assert invalid.status_code == _HTTP_UNPROCESSABLE
        assert (
            invalid.json()["detail"] == "request JSON is invalid"
            or "contract" in invalid.json()["detail"]
        )
        executed = client.post(
            "/v1/modules/M10-07/execute", content=request.model_dump_json(), headers=headers
        )
        envelope = executed.json()
        envelope["canonical"] = envelope["canonical"].replace("discordant", "concordant", 1)
        replay = client.post("/v1/modules/M10-07/verify", json=envelope, headers=headers)
        assert replay.status_code == _HTTP_OK
        assert replay.json()["verified"] is False


def test_api_enforces_media_type_and_preparse_request_result_limits() -> None:
    request = _request().model_dump(mode="json")
    with TestClient(create_app()) as client:
        wrong_media = client.post(
            "/v1/modules/M10-07/execute",
            json=request,
            headers={"content-type": "text/plain"},
        )
        oversized_request = client.post(
            "/v1/modules/M10-07/execute",
            content=b"{" + b"x" * (4 * 1024 * 1024 + 1) + b"}",
            headers={"content-type": "application/json"},
        )
        oversized_result = client.post(
            "/v1/modules/M10-07/verify",
            content=b"{" + b"x" * (8 * 1024 * 1024 + 1) + b"}",
            headers={"content-type": "application/json"},
        )
    assert wrong_media.status_code == _HTTP_UNSUPPORTED_MEDIA
    assert oversized_request.status_code == _HTTP_TOO_LARGE
    assert oversized_result.status_code == _HTTP_TOO_LARGE


def test_cli_validate_calibrate_no_overwrite_and_verify(tmp_path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(cli_app, ["validate", str(request_path)])
    assert validated.exit_code == 0
    assert (
        json.loads(validated.stdout)["operation"]
        == "calibrate_protein_rna_discordance_selective_prediction"
    )
    calibrated = runner.invoke(
        cli_app, ["calibrate", str(request_path), "--output", str(result_path)]
    )
    assert calibrated.exit_code == 0
    assert result_path.exists()
    overwritten = runner.invoke(
        cli_app, ["calibrate", str(request_path), "--output", str(result_path)]
    )
    assert overwritten.exit_code != 0
    verified = runner.invoke(cli_app, ["verify", str(result_path), str(result_path)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["verified"] is True

    schema_path = tmp_path / "schema.json"
    schema = runner.invoke(cli_app, ["export-schema", "output", "--output", str(schema_path)])
    assert schema.exit_code == 0
    assert (
        json.loads(schema_path.read_text(encoding="utf-8"))["x-glio-contract"]["provisionalAbi"]
        is True
    )
