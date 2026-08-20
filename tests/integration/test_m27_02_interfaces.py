"""FastAPI strict JSON and schema parity for M27-02."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m27_02 import ComplexActivityLineageResult
from glio_proteogen.contracts.m27_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from tests.runtime.test_m27_02_lineage import _request

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_CLI_OK = 0
_HTTP_UNPROCESSABLE = 422
_CLI_REPLAY_ERROR = 1


def test_m2702_schema_route_exposes_all_contracts(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        response = client.get("/v1/contracts/M27-02/output/schema")

    assert response.status_code == _HTTP_OK
    body = response.json()
    assert body["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M27-02"
    assert body["x-glio-contract"]["queryableGraphRequired"] is True
    assert body["x-glio-contract"]["parentTarget"] == "complex activity"


def test_m2702_api_lineage_and_verify_route_are_strict_and_replayable(tmp_path: Path) -> None:
    payload = json.loads(canonical_json_bytes(_request().model_dump(mode="json")))
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        resolved = client.post("/v1/modules/M27-02/lineage", json=payload)
        assert resolved.status_code == _HTTP_OK
        verified = client.post("/v1/modules/M27-02/verify", json=resolved.json())
        assert verified.status_code == _HTTP_OK
        parsed_result = ComplexActivityLineageResult.model_validate_json(
            resolved.content, strict=True
        )
        mutated = parsed_result.model_copy(
            update={
                "support_decision": parsed_result.support_decision.model_copy(
                    update={"rationale": "caller-rehashed semantic mutation"}
                )
            }
        )
        forged = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
        rejected = client.post("/v1/modules/M27-02/verify", json=forged.model_dump(mode="json"))
        malformed = client.post("/v1/modules/M27-02/lineage", json={"request_id": 4})

    assert verified.json() == resolved.json()
    assert rejected.status_code == _HTTP_UNPROCESSABLE
    assert rejected.json()["detail"] == "M27-02 replay verification failed"
    assert malformed.status_code == _HTTP_FORBIDDEN
    assert "lineage resolution requires accepted upstream controls" in malformed.json()["detail"]


def test_m2702_cli_schema_and_resolve_commands_match_runtime(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(_request().model_dump(mode="json")))
    runner = CliRunner()

    schema = runner.invoke(app, ["m2702", "export-schema", "output"])
    resolved = runner.invoke(app, ["m2702", "resolve", str(request_path)])

    assert schema.exit_code == _CLI_OK
    assert json.loads(schema.stdout)["x-glio-contract"]["moduleId"] == "GLIO-PROTEOGEN-M27-02"
    assert resolved.exit_code == _CLI_OK
    assert json.loads(resolved.stdout)["status"] == "resolved"

    parsed_result = ComplexActivityLineageResult.model_validate_json(resolved.stdout, strict=True)
    mutated = parsed_result.model_copy(
        update={
            "support_decision": parsed_result.support_decision.model_copy(
                update={"rationale": "caller-rehashed semantic mutation"}
            )
        }
    )
    forged = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    result_path = tmp_path / "forged-result.json"
    result_path.write_text(forged.model_dump_json(), encoding="utf-8")
    rejected = runner.invoke(app, ["m2702", "verify", str(result_path)])
    assert rejected.exit_code == _CLI_REPLAY_ERROR
    assert "replay verification failed" in rejected.stderr
