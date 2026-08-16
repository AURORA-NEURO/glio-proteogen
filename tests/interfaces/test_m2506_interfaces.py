"""FastAPI/Typer parity and sanitized boundaries for M25-06."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from evals.m25_06.fixture import build_request
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m25_06 import ChallengeDisposition
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge.api import (
    create_app,
)
from glio_proteogen.modules.c21_reference_material.m25_06_robustness_shift_ood_challenge.cli import (
    app,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_NOT_FOUND = 404
_HTTP_UNPROCESSABLE = 422


def test_api_schema_surface_and_unknown_name() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/modules/M25-06/schemas")
    unknown = client.get("/v1/modules/M25-06/schemas/unknown")
    assert response.status_code == _HTTP_OK
    assert tuple(response.json()) == (
        "request",
        "output",
        "surface",
        "scenario",
        "observation",
        "safe-failure",
        "configuration",
        "finding",
    )
    assert unknown.status_code == _HTTP_NOT_FOUND


def test_api_validate_challenge_and_verify_have_canonical_parity() -> None:
    client = TestClient(create_app())
    payload = build_request().model_dump(mode="json")
    validated = client.post("/v1/modules/M25-06/validate", json=payload)
    challenged = client.post("/v1/modules/M25-06/challenge", json=payload)
    verified = client.post("/v1/modules/M25-06/verify", json={"result": challenged.json()})
    assert validated.status_code == _HTTP_OK
    assert challenged.status_code == _HTTP_OK
    assert challenged.json()["request"] == validated.json()
    assert challenged.json()["status"] == "evaluated"
    assert verified.status_code == _HTTP_OK
    assert verified.json()["verified"] is True


def test_api_rejects_malformed_and_tampered_requests_without_leaking_values() -> None:
    client = TestClient(create_app())
    malformed = client.post("/v1/modules/M25-06/challenge", json={"request_id": "bad"})
    result = client.post(
        "/v1/modules/M25-06/challenge", json=build_request().model_dump(mode="json")
    ).json()
    result["result_digest"] = "sha256:" + "f" * 64
    tampered = client.post("/v1/modules/M25-06/verify", json={"result": result})
    assert malformed.status_code == _HTTP_UNPROCESSABLE
    assert tampered.status_code == _HTTP_UNPROCESSABLE
    assert "request_id" not in malformed.text


def test_api_verify_rejects_non_object_json() -> None:
    response = TestClient(create_app()).post(
        "/v1/modules/M25-06/verify",
        content=b"[]",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == _HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "request JSON must be an object"


def test_cli_exports_validates_challenges_and_refuses_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(build_request().model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    exported = runner.invoke(app, ["export-schema", "request"])
    validated = runner.invoke(app, ["validate", str(request_path)])
    challenged = runner.invoke(app, ["challenge", str(request_path), "--output", str(result_path)])
    repeated = runner.invoke(app, ["challenge", str(request_path), "--output", str(result_path)])
    verified = runner.invoke(app, ["verify", str(result_path)])
    assert exported.exit_code == 0
    assert json.loads(exported.stdout)["$schema"]
    assert validated.exit_code == 0
    assert challenged.exit_code == 0
    assert repeated.exit_code != 0
    assert verified.exit_code == 0


def test_cli_abstention_is_nonzero_and_safe(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(
        build_request(disposition=ChallengeDisposition.ABSTAIN_UNSUPPORTED).model_dump_json(),
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["challenge", str(request_path), "--output", str(result_path)])
    assert result.exit_code == 1
    assert json.loads(result_path.read_text(encoding="utf-8"))["robustness_surface"] is None
