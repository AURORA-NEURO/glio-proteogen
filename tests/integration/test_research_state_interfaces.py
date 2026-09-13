"""End-to-end interfaces for the stateless ECGI research lane."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.adapters.research_state import (
    RESEARCH_STATE_REPLAY_MAX_BYTES,
    RESEARCH_STATE_REQUEST_MAX_BYTES,
    RESEARCH_STATE_RESULT_MAX_BYTES,
)

if TYPE_CHECKING:
    from pathlib import Path

_PREFIX = "/v1/research/proteogenomic-state"
_HTTP_OK = 200
_HTTP_PAYLOAD_TOO_LARGE = 413
_HTTP_UNPROCESSABLE = 422
_DEMO_NODE_COUNT = 64
_DEMO_TOPOLOGY_SOURCE_COUNT = 3


def _assert_topology_provenance(request: dict[str, object], result: dict[str, object]) -> None:
    topology = request["topology_provenance"]
    assert isinstance(topology, dict)
    assert topology["derivation"] == "synthetic_abstraction"
    assert len(topology["sources"]) == _DEMO_TOPOLOGY_SOURCE_COUNT
    provenance = result["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["topology"] == topology


def _assert_limited_claim_ceiling(profile: dict[str, object], result: dict[str, object]) -> None:
    assert profile["claim_ceiling"] == "limited_unvalidated_caller_graph"
    node_states = result["node_states"]
    kinase_states = result["kinase_states"]
    assert isinstance(node_states, list)
    assert isinstance(kinase_states, list)
    estimated_states = [
        state
        for state in (*node_states, *kinase_states)
        if isinstance(state, dict) and state["support"] != "abstained"
    ]
    assert estimated_states
    assert {state["support"] for state in estimated_states} == {"limited"}


def test_demo_analyze_verify_lifecycle_and_openapi(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        profile_response = client.get(f"{_PREFIX}/profile")
        demo_response = client.get(f"{_PREFIX}/demo")

        assert profile_response.status_code == _HTTP_OK
        assert demo_response.status_code == _HTTP_OK
        profile = profile_response.json()
        request = demo_response.json()
        assert profile["profile_id"] == "glio-ecgi/1.0.0"
        assert profile["numpy_version"] == "2.5.2"
        assert profile["safety_class"] == "research_use_only"
        assert profile["limits"] == {
            "max_nodes": 256,
            "max_edges": 2048,
            "max_observations": 4096,
            "max_kinases": 128,
            "max_request_bytes": 2_097_152,
            "max_result_bytes": 4_194_304,
            "max_bootstrap_replicates": 256,
            "max_permutation_replicates": 2048,
        }
        assert len(request["nodes"]) == _DEMO_NODE_COUNT
        assert {node["kind"] for node in request["nodes"]} == {
            "protein",
            "proteoform",
            "phosphosite",
            "complex",
            "pathway",
            "kinase",
        }

        analysis_response = client.post(f"{_PREFIX}/analyze", json=request)
        assert analysis_response.status_code == _HTTP_OK, analysis_response.text
        result = analysis_response.json()
        assert result["research_use_only"] is True
        assert result["non_prescriptive"] is True
        assert result["request_digest"] == result["provenance"]["request_digest"]
        _assert_topology_provenance(request, result)
        assert result["profile_digest"] == profile["profile_digest"]
        assert result["solver"]["first_pass"]["objective_trace"]
        assert result["solver"]["second_pass"]["objective_trace"]
        assert result["kinase_states"]
        assert result["external_kinase_comparison"]["matches"]
        _assert_limited_claim_ceiling(profile, result)

        verification_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request, "result": result},
        )
        assert verification_response.status_code == _HTTP_OK
        verification = verification_response.json()
        assert verification["verified"] is True
        assert all(
            verification[field]
            for field in (
                "request_digest_match",
                "profile_digest_match",
                "solver_trace_match",
                "result_digest_match",
                "semantic_match",
            )
        )

        forged_result = {**result, "result_digest": "sha256:" + "f" * 64}
        forged_response = client.post(
            f"{_PREFIX}/verify",
            json={"request": request, "result": forged_result},
        )
        assert forged_response.status_code == _HTTP_OK
        forged_verification = forged_response.json()
        assert forged_verification["verified"] is False
        assert forged_verification["result_digest_match"] is False
        assert forged_verification["provided_result_digest"] == forged_result["result_digest"]

        document = client.get("/openapi.json").json()
        for suffix in ("profile", "demo", "analyze", "verify"):
            assert f"{_PREFIX}/{suffix}" in document["paths"]
        analyze_schema = document["paths"][f"{_PREFIX}/analyze"]["post"]
        assert analyze_schema["requestBody"]["content"]["application/json"]["schema"]
        assert analyze_schema["responses"]["200"]["content"]["application/json"]["schema"]
        verify_schema = document["paths"][f"{_PREFIX}/verify"]["post"]
        assert verify_schema["requestBody"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ReplayVerificationRequest"
        }
        replay_schema = document["components"]["schemas"]["ReplayVerificationRequest"]
        result_variants = replay_schema["properties"]["result"]["anyOf"]
        assert {variant["$ref"] for variant in result_variants} == {
            "#/components/schemas/ProteogenomicStateResult",
            "#/components/schemas/UnverifiedProteogenomicStateResult",
        }
        assert document["components"]["schemas"]["EvidenceState"]["enum"] == [
            "observed",
            "missing",
            "unknown",
            "not_applicable",
        ]
        assert document["components"]["schemas"]["ResearchEvidenceState"]["enum"] == [
            "observed",
            "left_censored",
            "missing",
            "unsupported",
        ]


def test_research_api_enforces_graph_and_transport_bounds(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        request = client.get(f"{_PREFIX}/demo").json()
        request["nodes"].append(request["nodes"][0])
        invalid = client.post(f"{_PREFIX}/analyze", json=request)
        oversized = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"padding":"' + (b"x" * RESEARCH_STATE_REQUEST_MAX_BYTES) + b'"}',
            headers={"content-type": "application/json"},
        )

    assert invalid.status_code == _HTTP_UNPROCESSABLE
    assert oversized.status_code == _HTTP_PAYLOAD_TOO_LARGE
    assert oversized.json() == {"detail": "request body exceeds the byte limit"}


def test_http_replay_receipt_uses_result_envelope_transport_bound(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        request = client.get(f"{_PREFIX}/demo").json()
        request["bootstrap_replicates"] = 8
        request["permutation_replicates"] = 32
        result = client.post(f"{_PREFIX}/analyze", json=request).json()
        envelope = json.dumps(
            {"request": request, "result": result},
            separators=(",", ":"),
        ).encode("utf-8")
        padded = envelope + b" " * (RESEARCH_STATE_RESULT_MAX_BYTES + 1 - len(envelope))

        accepted = client.post(
            f"{_PREFIX}/verify",
            content=padded,
            headers={"content-type": "application/json"},
        )
        oversized = client.post(
            f"{_PREFIX}/verify",
            content=envelope + b" " * (RESEARCH_STATE_REPLAY_MAX_BYTES + 1 - len(envelope)),
            headers={"content-type": "application/json"},
        )

    assert len(padded) > RESEARCH_STATE_RESULT_MAX_BYTES
    assert len(padded) <= RESEARCH_STATE_REPLAY_MAX_BYTES
    assert accepted.status_code == _HTTP_OK, accepted.text
    assert accepted.json()["verified"] is True
    assert oversized.status_code == _HTTP_PAYLOAD_TOO_LARGE


def test_research_state_cli_profile_analyze_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = runner.invoke(cli_app, ["research-state", "profile"])
    demo = runner.invoke(cli_app, ["research-state", "demo"])
    assert profile.exit_code == 0, profile.output
    assert demo.exit_code == 0, demo.output
    assert json.loads(profile.output)["profile_id"] == "glio-ecgi/1.0.0"

    request = json.loads(demo.output)
    request["bootstrap_replicates"] = 8
    request["permutation_replicates"] = 32
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    analyzed = runner.invoke(
        cli_app,
        ["research-state", "analyze", str(request_path)],
    )
    assert analyzed.exit_code == 0, analyzed.output
    result = json.loads(analyzed.output)
    envelope_path = tmp_path / "verification.json"
    envelope_path.write_text(
        json.dumps({"request": request, "result": result}),
        encoding="utf-8",
    )

    verified = runner.invoke(
        cli_app,
        ["research-state", "verify", str(envelope_path)],
    )
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.output)["verified"] is True

    result["result_digest"] = "sha256:" + "f" * 64
    envelope_path.write_text(
        json.dumps({"request": request, "result": result}),
        encoding="utf-8",
    )
    rejected = runner.invoke(
        cli_app,
        ["research-state", "verify", str(envelope_path)],
    )
    assert rejected.exit_code == 1
    assert json.loads(rejected.output)["verified"] is False
