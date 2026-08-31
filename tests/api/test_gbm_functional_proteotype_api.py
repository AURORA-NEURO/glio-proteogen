"""HTTP, CLI, transport, and replay lifecycle for functional proteotypes."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Lock
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import gbm_functional_proteotype as adapter
from glio_proteogen.adapters.api import _MODEL_ROUTE_LIMITS, create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.deployment import DeploymentSettings, create_deployment_app
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbm_functional_proteotype import (
    DEMO_ID,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    ReplayVerificationRequest,
    analyze_functional_proteotype,
    synthetic_demo_request,
    verify_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

if TYPE_CHECKING:
    from pathlib import Path

PREFIX = "/v1/research/gbm-functional-proteotype"
HTTP_OK = 200
HTTP_TOO_LARGE = 413
HTTP_UNSUPPORTED_MEDIA = 415
HTTP_UNPROCESSABLE = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_CLIENT_CLOSED = 499
HTTP_INTERNAL_ERROR = 500
HTTP_TIMEOUT = 504


def _database_dump(database: Path) -> str:
    with sqlite3.connect(database) as connection:
        return "\n".join(connection.iterdump())


def test_central_demo_analyze_verify_is_non_prescriptive_and_stateless(
    tmp_path: Path,
) -> None:
    database = tmp_path / "events.sqlite3"
    with TestClient(create_app(database)) as client:
        before = _database_dump(database)
        profile = client.get(f"{PREFIX}/profile")
        demo = client.get(f"{PREFIX}/demo")
        first = client.post(f"{PREFIX}/analyze", json=demo.json())
        second = client.post(f"{PREFIX}/analyze", json=demo.json())
        verification = client.post(
            f"{PREFIX}/verify",
            json={"request": demo.json(), "result": first.json()},
        )
        after = _database_dump(database)

    assert profile.status_code == demo.status_code == HTTP_OK
    assert first.status_code == second.status_code == verification.status_code == HTTP_OK
    assert profile.json()["source_license"] == "CC-BY-4.0"
    assert profile.json()["claim_ceiling"] == (
        "bulk_tumor_protein_concordance_to_source_selected_cptac_gbm_signatures"
    )
    assert demo.json()["sample_id"] == DEMO_ID
    assert first.json() == second.json()
    assert verification.json()["verified"] is True
    assert first.json()["research_use_only"] is True
    assert first.json()["non_prescriptive"] is True
    assert first.json()["clinical_subtype_inference"] is False
    assert first.json()["emits_subtype_classification"] is False
    assert first.json()["source_cohort_pathway_inference"] is False
    assert [item["axis"] for item in first.json()["axis_evidence"]] == [
        "GPM",
        "MTC",
        "NEU",
        "PPR",
    ]
    assert first.headers["x-glio-result-digest"] == first.json()["result_digest"]
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (profile, demo, first, second, verification)
    )
    assert before == after


def test_transport_rejects_wrong_media_duplicate_keys_unknown_fields_and_oversize(
    tmp_path: Path,
) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        wrong_media = client.post(
            f"{PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate = client.post(
            f"{PREFIX}/analyze",
            content=b'{"sample_id":"private-a","sample_id":"private-b"}',
            headers={"content-type": "application/json"},
        )
        unknown = client.post(
            f"{PREFIX}/analyze",
            json={**synthetic_demo_request().model_dump(mode="json"), "subtype": "secret"},
        )
        oversized = client.post(
            f"{PREFIX}/analyze",
            content=b"{}",
            headers={
                "content-type": "application/json",
                "content-length": str(MAX_REQUEST_BYTES + 1),
            },
        )

    assert wrong_media.status_code == HTTP_UNSUPPORTED_MEDIA
    assert duplicate.status_code == unknown.status_code == HTTP_UNPROCESSABLE
    assert oversized.status_code == HTTP_TOO_LARGE
    assert "private-" not in duplicate.text
    assert "secret" not in unknown.text
    assert all(
        response.headers["cache-control"] == "no-store"
        for response in (wrong_media, duplicate, unknown, oversized)
    )


def test_invalid_body_is_rejected_before_compute_capacity_is_acquired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisitions = 0

    def acquire() -> None:
        nonlocal acquisitions
        acquisitions += 1

    monkeypatch.setattr(adapter, "_acquire_slot", acquire)
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        wrong_media = client.post(
            f"{PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        invalid_contract = client.post(f"{PREFIX}/analyze", json={"sample_id": "bad"})
        invalid_replay = client.post(f"{PREFIX}/verify", json={"request": {}})

    assert wrong_media.status_code == HTTP_UNSUPPORTED_MEDIA
    assert invalid_contract.status_code == invalid_replay.status_code == HTTP_UNPROCESSABLE
    assert acquisitions == 0


def test_openapi_route_limits_and_v2_catalog_are_exact(tmp_path: Path) -> None:
    app = create_app(tmp_path / "events.sqlite3")
    schema = app.openapi()
    assert {path for path in schema["paths"] if path.startswith(PREFIX)} == {
        f"{PREFIX}/profile",
        f"{PREFIX}/demo",
        f"{PREFIX}/analyze",
        f"{PREFIX}/verify",
    }
    analyze_schema = schema["paths"][f"{PREFIX}/analyze"]["post"]
    assert analyze_schema["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/FunctionalProteotypeRequest"
    }
    verify_schema = schema["paths"][f"{PREFIX}/verify"]["post"]
    assert verify_schema["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GbmFunctionalProteotypeReplayVerificationRequest"
    }
    assert _MODEL_ROUTE_LIMITS[PREFIX] == (MAX_REQUEST_BYTES, MAX_RESULT_BYTES)
    assert _MODEL_ROUTE_LIMITS[f"{PREFIX}/verify"] == (MAX_REPLAY_BYTES, MAX_RESULT_BYTES)

    deployed = create_deployment_app(
        DeploymentSettings(database_path=tmp_path / "catalog.sqlite3", environment="test")
    )
    with TestClient(deployed) as client:
        response = client.get("/v2/deployment/catalog")
    operations = {
        (item["method"], item["path"]): item
        for item in response.json()["operations"]
        if item["path"].startswith(PREFIX)
    }
    assert set(operations) == {
        ("GET", f"{PREFIX}/profile"),
        ("GET", f"{PREFIX}/demo"),
        ("POST", f"{PREFIX}/analyze"),
        ("POST", f"{PREFIX}/verify"),
    }
    analyze = operations[("POST", f"{PREFIX}/analyze")]
    assert analyze["request_max_bytes"] == MAX_REQUEST_BYTES
    assert analyze["result_max_bytes"] == MAX_RESULT_BYTES
    assert analyze["safety_class"] == "research-use-only"
    assert analyze["validated_example_id"] == DEMO_ID


def test_cli_profile_demo_analyze_and_verify(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = runner.invoke(cli_app, ["gbm-functional-proteotype", "profile"])
    demo = runner.invoke(cli_app, ["gbm-functional-proteotype", "demo"])
    assert profile.exit_code == demo.exit_code == 0
    request_path = tmp_path / "request.json"
    request_path.write_text(demo.stdout, encoding="utf-8")
    analysis = runner.invoke(
        cli_app,
        ["gbm-functional-proteotype", "analyze", str(request_path)],
    )
    assert analysis.exit_code == 0, analysis.output
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(
        canonical_json_bytes(
            {"request": json.loads(demo.stdout), "result": json.loads(analysis.stdout)}
        )
    )
    verification = runner.invoke(
        cli_app,
        ["gbm-functional-proteotype", "verify", str(receipt)],
    )
    assert verification.exit_code == 0, verification.output
    assert json.loads(verification.stdout)["verified"] is True


class _ConcurrentGate:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.lock = Lock()
        self.active = 0

    def run[T](self, value: T) -> T:
        with self.lock:
            self.active += 1
            if self.active == adapter.GBM_FUNCTIONAL_PROTEOTYPE_MAX_CONCURRENT_ANALYSES:
                self.entered.set()
        try:
            if not self.release.wait(timeout=10):
                raise TimeoutError
            return value
        finally:
            with self.lock:
                self.active -= 1


def test_analyze_and_verify_share_bounded_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    result = analyze_functional_proteotype(request)
    envelope = ReplayVerificationRequest(request=request, result=result)
    verification = verify_replay(envelope)
    gate = _ConcurrentGate()
    monkeypatch.setattr(
        adapter,
        "_SLOTS",
        BoundedSemaphore(adapter.GBM_FUNCTIONAL_PROTEOTYPE_MAX_CONCURRENT_ANALYSES),
    )
    monkeypatch.setattr(
        adapter,
        "analyze_functional_proteotype",
        lambda _request, **_kwargs: gate.run(result),
    )
    monkeypatch.setattr(
        adapter,
        "verify_replay",
        lambda _envelope, **_kwargs: gate.run(verification),
    )

    with (
        TestClient(create_app(tmp_path / "events.sqlite3")) as client,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        analysis_future = executor.submit(
            client.post,
            f"{PREFIX}/analyze",
            json=request.model_dump(mode="json"),
        )
        verification_future = executor.submit(
            client.post,
            f"{PREFIX}/verify",
            json=envelope.model_dump(mode="json"),
        )
        assert gate.entered.wait(timeout=10), "two functional-proteotype workers never overlapped"
        rejected = client.post(f"{PREFIX}/analyze", json=request.model_dump(mode="json"))
        gate.release.set()
        accepted = (analysis_future.result(timeout=10), verification_future.result(timeout=10))
        recovered = client.post(f"{PREFIX}/analyze", json=request.model_dump(mode="json"))

    assert rejected.status_code == HTTP_TOO_MANY_REQUESTS
    assert rejected.headers["retry-after"] == "1"
    assert tuple(response.status_code for response in accepted) == (HTTP_OK, HTTP_OK)
    assert recovered.status_code == HTTP_OK


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (InferenceCancelledError("private cancellation detail"), HTTP_CLIENT_CLOSED),
        (InferenceDeadlineExceededError("private deadline detail"), HTTP_TIMEOUT),
        (ValueError("private validation detail"), HTTP_UNPROCESSABLE),
        (RuntimeError("private runtime detail"), HTTP_INTERNAL_ERROR),
    ],
)
def test_execution_failures_are_cooperative_and_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_status: int,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(adapter, "analyze_functional_proteotype", fail)
    with pytest.raises(HTTPException) as captured:
        adapter._execute(synthetic_demo_request(), CancellationContext())
    assert captured.value.status_code == expected_status
    assert "private" not in str(captured.value.detail)
    assert captured.value.headers is not None
    assert captured.value.headers["Cache-Control"] == "no-store"
