"""FastAPI, CLI and plugin parity tests for M09-01."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.contracts.m09_01 import ComplexActivityMissingness
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    M0901InputError,
    M0901Service,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    api as m0901_api,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    cli as m0901_cli,
)
from tests.modules.c09_complex_stoichiometry.test_m09_01_formal_state import _request

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_FORBIDDEN = 403


def test_api_validate_execute_and_verify_are_canonical() -> None:
    payload = _request().model_dump(mode="json")
    with TestClient(m0901_api.create_app()) as client:
        validated = client.post("/v1/modules/M09-01/validate", json=payload)
        executed = client.post("/v1/modules/M09-01/execute", json=payload)

        assert validated.status_code == HTTP_OK
        assert executed.status_code == HTTP_OK
        body = executed.json()
        verified = client.post(
            "/v1/modules/M09-01/verify",
            json={"result": body["result"], "canonical": body["canonical"]},
        )
        assert verified.status_code == HTTP_OK
        assert verified.json()["verified"] is True


def test_api_sanitizes_duplicate_json_and_unknown_schema() -> None:
    with TestClient(m0901_api.create_app()) as client:
        duplicate = client.post(
            "/v1/modules/M09-01/validate",
            content=b'{"request_id":"one","request_id":"two"}',
            headers={"content-type": "application/json"},
        )
        unknown = client.get("/v1/modules/M09-01/schemas/not-a-contract")

    assert duplicate.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert unknown.status_code == HTTP_NOT_FOUND


def test_api_validation_authorization_and_replay_error_paths() -> None:
    payload = _request().model_dump(mode="json")
    invalid = {"request_id": "not-a-request"}
    rejected = (
        _request()
        .model_copy(
            update={
                "context": _request().context.model_copy(
                    update={
                        "references": _request().context.references.model_copy(
                            update={
                                "support": _request().context.references.support.model_copy(
                                    update={"state": UpstreamDecisionState.REJECTED}
                                )
                            }
                        )
                    }
                )
            }
        )
        .model_dump(mode="json")
    )
    with TestClient(m0901_api.create_app()) as client:
        invalid_response = client.post("/v1/modules/M09-01/validate", json=invalid)
        denied_response = client.post("/v1/modules/M09-01/validate", json=rejected)
        not_object = client.post("/v1/modules/M09-01/verify", json=[])
        missing_fields = client.post("/v1/modules/M09-01/verify", json={})
        executed = client.post("/v1/modules/M09-01/execute", json=payload).json()
        tampered = client.post(
            "/v1/modules/M09-01/verify",
            json={"result": executed["result"], "canonical": executed["canonical"] + " "},
        )

    assert invalid_response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert denied_response.status_code == HTTP_FORBIDDEN
    assert not_object.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert missing_fields.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert tampered.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_api_execute_maps_input_errors() -> None:
    class RejectingService(M0901Service):
        def _execute_validated(self, _request: object) -> object:
            raise M0901InputError("result_limit")

    with TestClient(m0901_api.create_app(RejectingService())) as client:
        response = client.post(
            "/v1/modules/M09-01/execute",
            json=_request().model_dump(mode="json"),
        )
    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT


def test_cli_validate_and_execute_no_overwrite(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_request().model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()

    validated = runner.invoke(m0901_cli.app, ["validate", str(request_path)])
    executed = runner.invoke(
        m0901_cli.app,
        ["execute", str(request_path), "--output", str(output_path)],
    )
    repeated = runner.invoke(
        m0901_cli.app,
        ["execute", str(request_path), "--output", str(output_path)],
    )

    assert validated.exit_code == 0
    assert executed.exit_code == 0
    assert output_path.exists()
    assert repeated.exit_code != 0


def test_cli_export_abstention_and_verify_paths(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    canonical_path = tmp_path / "canonical.json"
    request_path.write_text(
        json.dumps(
            _request(value=None, state=ComplexActivityMissingness.MISSING).model_dump(mode="json")
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    schema = runner.invoke(m0901_cli.app, ["export-schema", "request"])
    unknown = runner.invoke(m0901_cli.app, ["export-schema", "unknown"])
    abstained = runner.invoke(m0901_cli.app, ["execute", str(request_path)])
    invalid_request = tmp_path / "invalid.json"
    invalid_request.write_text("{}", encoding="utf-8")
    invalid = runner.invoke(m0901_cli.app, ["validate", str(invalid_request)])
    malformed_request = tmp_path / "malformed.json"
    malformed_request.write_text("[", encoding="utf-8")
    malformed = runner.invoke(m0901_cli.app, ["validate", str(malformed_request)])
    execute_invalid = runner.invoke(m0901_cli.app, ["execute", str(invalid_request)])

    assert schema.exit_code == 0
    assert unknown.exit_code != 0
    assert abstained.exit_code == 1
    assert invalid.exit_code != 0
    assert malformed.exit_code != 0
    assert execute_invalid.exit_code != 0

    valid_request = tmp_path / "valid.json"
    valid_request.write_text(
        json.dumps(_request().model_dump(mode="json")),
        encoding="utf-8",
    )
    executed = runner.invoke(
        m0901_cli.app,
        ["execute", str(valid_request), "--output", str(result_path)],
    )
    canonical_path.write_bytes(result_path.read_bytes())
    verified = runner.invoke(
        m0901_cli.app,
        ["verify", str(result_path), str(canonical_path)],
    )
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_bytes(result_path.read_bytes() + b" ")
    tampered = runner.invoke(
        m0901_cli.app,
        ["verify", str(result_path), str(tampered_path)],
    )
    invalid_result_path = tmp_path / "invalid-result.json"
    invalid_result_path.write_text("[]", encoding="utf-8")
    invalid_verify = runner.invoke(
        m0901_cli.app,
        ["verify", str(invalid_result_path), str(canonical_path)],
    )
    assert executed.exit_code == 0
    assert verified.exit_code == 0
    assert tampered.exit_code != 0
    assert invalid_verify.exit_code != 0
