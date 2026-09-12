"""Lifecycle and transport tests for the Neftel-to-ECGI bridge."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import gbm_microenvironment_graph as adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app
from glio_proteogen.research.gbm_microenvironment_graph import (
    MicroenvironmentGraphReplayRequest,
    analyze_microenvironment_graph,
    synthetic_microenvironment_graph_request,
)

if TYPE_CHECKING:
    from pathlib import Path


HTTP_OK = 200
HTTP_UNSUPPORTED_MEDIA_TYPE = 415
HTTP_UNPROCESSABLE_ENTITY = 422
GRAPH_NODE_COUNT = 12


def test_bridge_http_demo_analyze_verify_round_trip(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        profile = client.get(f"{adapter.MICROENVIRONMENT_GRAPH_ROUTE_PREFIX}/profile")
        demo = client.get(f"{adapter.MICROENVIRONMENT_GRAPH_ROUTE_PREFIX}/demo")
        assert profile.status_code == HTTP_OK
        assert demo.status_code == HTTP_OK
        result = client.post(
            f"{adapter.MICROENVIRONMENT_GRAPH_ROUTE_PREFIX}/analyze",
            json=demo.json(),
        )
        assert result.status_code == HTTP_OK
        body = result.json()
        assert body["source_result"]["output_semantics"] == "bulk_protein_program_evidence"
        assert body["axis_result"]["profile_id"] == "gbm-proteomic-axes/1.0.0"
        assert len(body["graph_result"]["node_states"]) == GRAPH_NODE_COUNT
        verified = client.post(
            f"{adapter.MICROENVIRONMENT_GRAPH_ROUTE_PREFIX}/verify",
            json={"request": demo.json(), "result": body},
        )
        assert verified.status_code == HTTP_OK
        assert verified.json()["verified"] is True
        assert verified.json()["axis_replay_match"] is True


def test_bridge_rejects_non_json_and_tampered_receipt(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        prefix = adapter.MICROENVIRONMENT_GRAPH_ROUTE_PREFIX
        assert (
            client.post(
                f"{prefix}/analyze",
                content=b"{}",
                headers={"content-type": "text/plain"},
            ).status_code
            == HTTP_UNSUPPORTED_MEDIA_TYPE
        )
        demo = client.get(f"{prefix}/demo").json()
        result = client.post(f"{prefix}/analyze", json=demo).json()
        result["result_digest"] = "sha256:" + "f" * 64
        assert (
            client.post(f"{prefix}/verify", json={"request": demo, "result": result}).status_code
            == HTTP_UNPROCESSABLE_ENTITY
        )


def test_bridge_direct_and_cli_parity(tmp_path: Path) -> None:
    request = synthetic_microenvironment_graph_request()
    expected = analyze_microenvironment_graph(request)
    request_path = tmp_path / "request.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    runner = CliRunner()
    cli_result = runner.invoke(app, ["gbm-microenvironment-graph", "analyze", str(request_path)])
    assert cli_result.exit_code == 0, cli_result.stdout
    assert json.loads(cli_result.stdout) == expected.model_dump(mode="json")
    envelope_path = tmp_path / "envelope.json"
    envelope_path.write_text(
        MicroenvironmentGraphReplayRequest(request=request, result=expected).model_dump_json(),
        encoding="utf-8",
    )
    verification = runner.invoke(app, ["gbm-microenvironment-graph", "verify", str(envelope_path)])
    assert verification.exit_code == 0, verification.stdout
    assert json.loads(verification.stdout)["verified"] is True
