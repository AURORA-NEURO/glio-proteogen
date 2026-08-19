"""FastAPI strict JSON and schema parity for M27-02."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.contracts.m27_02 import (
    ComplexActivityLineageResult,
    graph_payload_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c27_complex_activity.m27_02_lineage_service import (
    M2702LineageResolver,
)
from tests.runtime.test_m27_02_lineage import _request

_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_HTTP_FORBIDDEN = 403
_CLI_OK = 0


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
        malformed = client.post("/v1/modules/M27-02/lineage", json={"request_id": 4})

    assert verified.json() == resolved.json()
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


def test_m2702_api_and_cli_verify_replay_resigned_nested_tamper(
    tmp_path: Path,
) -> None:
    payload = json.loads(canonical_json_bytes(_request().model_dump(mode="json")))
    with TestClient(create_app(tmp_path / "events.sqlite")) as client:
        published = client.post("/v1/modules/M27-02/lineage", json=payload)
        assert published.status_code == _HTTP_OK
        result = M2702LineageResolver().resolve(_request())
        assert result.lineage_graph is not None
        forged_nodes = (
            result.lineage_graph.nodes[0],
            result.lineage_graph.nodes[1].model_copy(update={"name": "forged-node-label"}),
            *result.lineage_graph.nodes[2:],
        )
        forged_graph = result.lineage_graph.model_copy(update={"nodes": forged_nodes})
        forged_bundle = forged_graph.reproducibility_bundle.model_copy(
            update={"manifest_digest": graph_payload_digest(forged_graph)}
        )
        forged_graph = forged_graph.model_copy(update={"reproducibility_bundle": forged_bundle})
        forged_payload = result.model_dump(mode="python")
        forged_payload["lineage_graph"] = forged_graph
        forged_payload["result_digest"] = result_payload_digest(forged_payload)
        forged_result = ComplexActivityLineageResult.model_validate(forged_payload, strict=True)
        forged = json.loads(canonical_json_bytes(forged_result.model_dump(mode="json")))
        rejected = client.post("/v1/modules/M27-02/verify", json=forged)

    assert rejected.status_code == _HTTP_UNPROCESSABLE
    assert rejected.json() == {"detail": "M27-02 replay envelope is invalid"}

    result_path = tmp_path / "forged-result.json"
    result_path.write_text(json.dumps(forged), encoding="utf-8")
    cli_rejected = CliRunner().invoke(app, ["m2702", "verify", str(result_path)])
    assert cli_rejected.exit_code != _CLI_OK
    assert "replay verification failed" in cli_rejected.output
    assert "Traceback" not in cli_rejected.output
