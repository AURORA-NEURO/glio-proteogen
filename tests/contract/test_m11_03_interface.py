"""FastAPI and Typer parity tests for M11-03."""

from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.m1103 import app, m1103_app
from glio_proteogen.contracts.m11_03 import result_payload_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c11_protein_native_subtype import (
    m11_03_mechanistic_feature_constructor as m1103,
)
from tests.contract.test_m11_03_runtime import _request

if TYPE_CHECKING:
    from pathlib import Path


def test_schema_and_api_construct_verify_are_canonical() -> None:
    request = _request()
    client = TestClient(app)
    schema = client.get("/v1/m11-03/schema/request")
    assert schema.status_code == HTTPStatus.OK
    assert schema.json()["x-glio-contract"]["provisionalAbi"] is True
    constructed = client.post(
        "/v1/modules/M11-03/mechanistic-features",
        content=request.model_dump_json(),
    )
    assert constructed.status_code == HTTPStatus.OK
    result = constructed.json()
    assert result["status"] == "constructed"
    verified = client.post(
        "/v1/modules/M11-03/verify",
        json={"request": request.model_dump(mode="json"), "result": result},
    )
    assert verified.status_code == HTTPStatus.OK
    assert verified.json() == {"verified": True}
    typed_result = m1103.construct_variant_peptide_mechanistic_features(request)
    mutated = typed_result.model_copy(
        update={
            "support_decision": typed_result.support_decision.model_copy(
                update={"rationale": "caller-rehashed semantic mutation"}
            )
        }
    )
    forged = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    rejected = client.post(
        "/v1/modules/M11-03/verify",
        json={"request": request.model_dump(mode="json"), "result": forged.model_dump(mode="json")},
    )
    assert rejected.status_code == HTTPStatus.OK
    assert rejected.json() == {"verified": False}


def test_api_rejects_duplicate_json_and_denied_control() -> None:
    request = _request()
    client = TestClient(app)
    duplicate = request.model_dump_json()[:-1] + ',"request_id":"request.duplicate"}'
    assert (
        client.post("/v1/modules/M11-03/mechanistic-features", content=duplicate).status_code
        == HTTPStatus.BAD_REQUEST
    )
    denied = _request(controls={"quality": UpstreamDecisionState.REJECTED})
    response = client.post(
        "/v1/modules/M11-03/mechanistic-features",
        content=denied.model_dump_json(),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_cli_construct_verify_and_no_overwrite(tmp_path: Path) -> None:
    request = _request()
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    construct = runner.invoke(
        m1103_app,
        ["construct", str(request_path), "--output", str(result_path)],
    )
    assert construct.exit_code == 0, construct.output
    assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "constructed"
    verify = runner.invoke(m1103_app, ["verify", str(request_path), str(result_path)])
    assert verify.exit_code == 0, verify.output
    assert json.loads(verify.output) == {"verified": True}
    overwrite = runner.invoke(
        m1103_app,
        ["construct", str(request_path), "--output", str(result_path)],
    )
    assert overwrite.exit_code != 0
    assert m1103.M1103Service().execute(request).status.value == "constructed"


def test_cli_verify_rejects_self_rehashed_semantic_mutation(tmp_path: Path) -> None:
    request = _request()
    result = m1103.construct_variant_peptide_mechanistic_features(request)
    mutated = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "caller-rehashed semantic mutation"}
            )
        }
    )
    forged = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "forged.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    result_path.write_text(forged.model_dump_json(), encoding="utf-8")
    rejected = CliRunner().invoke(
        m1103_app,
        ["verify", str(request_path), str(result_path)],
    )
    assert rejected.exit_code == 1
    assert json.loads(rejected.stdout) == {"verified": False}
