"""Runtime isolation, concurrency, and disclosure guards for the ECGI API."""

# ruff: noqa: TRY003

from __future__ import annotations

import logging
import sqlite3
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Lock
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from glio_proteogen.adapters import research_state as adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.research.proteogenomic_state import (
    GraphNode,
    NodeKind,
    ProteogenomicStateRequest,
    PublicTopologySource,
    ReplayVerificationRequest,
    TopologyProvenance,
    analyze_proteogenomic_state,
    graph_topology_digest,
    verify_proteogenomic_replay,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_HTTP_INTERNAL_ERROR = 500
_HTTP_OK = 200
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_UNPROCESSABLE = 422
_PREFIX = adapter.RESEARCH_STATE_ROUTE_PREFIX


def _request(sample_id: str = "runtime-guard.sample") -> ProteogenomicStateRequest:
    return ProteogenomicStateRequest(
        sample_id=sample_id,
        nodes=(GraphNode(node_id="protein.signal", kind=NodeKind.PROTEIN),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )


def _research_store_counts(database: Path) -> tuple[int, int, int, int]:
    with sqlite3.connect(database) as connection:
        return tuple(
            connection.execute(query).fetchone()[0]
            for query in (
                "SELECT COUNT(*) FROM m0101_events",
                "SELECT COUNT(*) FROM m0101_protocols",
                "SELECT COUNT(*) FROM m0102_events",
                "SELECT COUNT(*) FROM m0102_resolutions",
            )
        )


def _database_dump(database: Path) -> str:
    with sqlite3.connect(database) as connection:
        return "\n".join(connection.iterdump())


def _request_with_private_provenance(
    sample_id: str, node_id: str, source_id: str, note: str
) -> ProteogenomicStateRequest:
    node = GraphNode(node_id=node_id, kind=NodeKind.PROTEIN)
    source = PublicTopologySource(
        source_id=source_id,
        resource_name="Public topology fixture",
        resource_release="2026-08-29",
        record_id="record.runtime-guard",
        record_title="Runtime guard topology record",
        source_uri="https://example.org/runtime-guard.json",
        source_format="JSON",
        source_digest="sha256:" + "a" * 64,
        source_size_bytes=128,
        license_id="CC0-1.0",
        license_uri="https://creativecommons.org/publicdomain/zero/1.0/",
        retrieved_on="2026-08-29",
        scope_node_ids=(node_id,),
    )
    topology = TopologyProvenance(
        topology_digest=graph_topology_digest({"nodes": [node], "edges": []}),
        derivation="caller_curated",
        sources=(source,),
        curation_note=note,
    )
    return ProteogenomicStateRequest(
        sample_id=sample_id,
        nodes=(node,),
        bootstrap_replicates=8,
        permutation_replicates=32,
        topology_provenance=topology,
    )


class _ConcurrentGate:
    """Hold two genuine worker calls while recording their simultaneous occupancy."""

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self._lock = Lock()
        self._active = 0
        self.maximum_active = 0

    def run[T](self, value: T) -> T:
        with self._lock:
            self._active += 1
            self.maximum_active = max(self.maximum_active, self._active)
            if self._active == adapter.RESEARCH_STATE_MAX_CONCURRENT_ANALYSES:
                self.entered.set()
        try:
            if not self.release.wait(timeout=10):
                raise TimeoutError("concurrency test did not release the worker")
            return value
        finally:
            with self._lock:
                self._active -= 1


def test_http_analyze_and_verify_share_a_true_simultaneous_capacity_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    analysis_result = analyze_proteogenomic_state(request)
    verification_request = ReplayVerificationRequest(request=request, result=analysis_result)
    verification_result = verify_proteogenomic_replay(verification_request)
    gate = _ConcurrentGate()
    monkeypatch.setattr(
        adapter,
        "_ANALYSIS_SLOTS",
        BoundedSemaphore(adapter.RESEARCH_STATE_MAX_CONCURRENT_ANALYSES),
    )
    monkeypatch.setattr(
        adapter,
        "analyze_proteogenomic_state",
        lambda _request, **_kwargs: gate.run(analysis_result),
    )
    monkeypatch.setattr(
        adapter,
        "verify_proteogenomic_replay",
        lambda _request, **_kwargs: gate.run(verification_result),
    )

    database = tmp_path / "events.sqlite3"
    with TestClient(create_app(database)) as client, ThreadPoolExecutor(max_workers=2) as executor:
        analyze_future = executor.submit(
            client.post,
            f"{_PREFIX}/analyze",
            json=request.model_dump(mode="json"),
        )
        verify_future = executor.submit(
            client.post,
            f"{_PREFIX}/verify",
            json=verification_request.model_dump(mode="json"),
        )
        assert gate.entered.wait(timeout=10), "two endpoint workers never overlapped"

        rejected_analysis = client.post(
            f"{_PREFIX}/analyze",
            json=request.model_dump(mode="json"),
        )
        rejected_verification = client.post(
            f"{_PREFIX}/verify",
            json=verification_request.model_dump(mode="json"),
        )
        gate.release.set()
        accepted = (analyze_future.result(timeout=10), verify_future.result(timeout=10))

        recovered = client.post(
            f"{_PREFIX}/analyze",
            json=request.model_dump(mode="json"),
        )

    assert tuple(response.status_code for response in accepted) == (_HTTP_OK, _HTTP_OK)
    assert rejected_analysis.status_code == _HTTP_TOO_MANY_REQUESTS
    assert rejected_verification.status_code == _HTTP_TOO_MANY_REQUESTS
    assert recovered.status_code == _HTTP_OK
    assert gate.maximum_active == adapter.RESEARCH_STATE_MAX_CONCURRENT_ANALYSES


def test_http_analysis_and_replay_are_deterministic_and_never_persisted(
    tmp_path: Path,
) -> None:
    canaries = (
        "private-sample-never-persist-4f394f96",
        "private-node-never-persist-6776c87f",
        "private-source-never-persist-45450f7a",
        "private-curation-note-never-persist-625919cb",
    )
    request = _request_with_private_provenance(*canaries)
    database = tmp_path / "events.sqlite3"
    app = create_app(database)

    with TestClient(app) as client:
        counts_before = _research_store_counts(database)
        database_before = _database_dump(database)
        files_before = {path.name for path in tmp_path.iterdir()}

        first = client.post(f"{_PREFIX}/analyze", json=request.model_dump(mode="json"))
        second = client.post(f"{_PREFIX}/analyze", json=request.model_dump(mode="json"))
        replay = client.post(
            f"{_PREFIX}/verify",
            json={"request": request.model_dump(mode="json"), "result": first.json()},
        )

        counts_after = _research_store_counts(database)
        database_after = _database_dump(database)
        files_after = {path.name for path in tmp_path.iterdir()}

    assert first.status_code == second.status_code == replay.status_code == _HTTP_OK
    assert first.json() == second.json()
    assert replay.json()["verified"] is True
    assert counts_before == counts_after == (0, 0, 0, 0)
    assert database_before == database_after
    assert files_before == files_after
    for path in tmp_path.iterdir():
        if path.is_file():
            content = path.read_bytes()
            assert all(canary.encode("utf-8") not in content for canary in canaries)


def _raise_sensitive_value_error(canary: str) -> Callable[..., None]:
    def fail(request: object, **_kwargs: object) -> None:
        raise ValueError(f"{canary}: {request!r}")

    return fail


def _raise_sensitive_runtime_error(canary: str) -> Callable[..., None]:
    def fail(request: object, **_kwargs: object) -> None:
        raise RuntimeError(f"{canary}: {request!r}")

    return fail


def test_http_validation_and_expected_engine_failures_do_not_disclose_request_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "private-request-canary-308df487"
    request = _request(canary)
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(
        adapter,
        "analyze_proteogenomic_state",
        _raise_sensitive_value_error(canary),
    )

    malformed = (
        b'{"sample_id":"'
        + canary.encode("utf-8")
        + b'","nodes":[{"node_id":"bad node","kind":"protein"}]}'
    )
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        validation_failure = client.post(
            f"{_PREFIX}/analyze",
            content=malformed,
            headers={"content-type": "application/json"},
        )
        engine_failure = client.post(
            f"{_PREFIX}/analyze",
            json=request.model_dump(mode="json"),
        )

    assert validation_failure.status_code == engine_failure.status_code == _HTTP_UNPROCESSABLE
    observable = validation_failure.text + engine_failure.text + caplog.text
    assert canary not in observable


def test_unexpected_service_failures_are_sanitized_without_traceback_disclosure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "private-unexpected-canary-cf85ac7d"
    request = _request(canary)
    result = analyze_proteogenomic_state(request)
    envelope = ReplayVerificationRequest(request=request, result=result)
    caplog.set_level(logging.DEBUG)

    with monkeypatch.context() as scoped:
        scoped.setattr(
            adapter,
            "analyze_proteogenomic_state",
            _raise_sensitive_runtime_error(canary),
        )
        with pytest.raises(HTTPException) as captured:
            adapter._execute(request)
        rendered = "".join(traceback.format_exception(captured.value))
        assert captured.value.status_code == _HTTP_INTERNAL_ERROR
        assert canary not in rendered

        with TestClient(create_app(tmp_path / "analysis.sqlite3")) as client:
            analysis_failure = client.post(
                f"{_PREFIX}/analyze",
                json=request.model_dump(mode="json"),
            )

    with monkeypatch.context() as scoped:
        scoped.setattr(
            adapter,
            "verify_proteogenomic_replay",
            _raise_sensitive_runtime_error(canary),
        )
        with TestClient(create_app(tmp_path / "verification.sqlite3")) as client:
            verification_failure = client.post(
                f"{_PREFIX}/verify",
                json=envelope.model_dump(mode="json"),
            )

    assert analysis_failure.status_code == verification_failure.status_code == _HTTP_INTERNAL_ERROR
    assert analysis_failure.json() == {"detail": "research analysis failed safely"}
    assert verification_failure.json() == {"detail": "research replay failed safely"}
    observable = analysis_failure.text + verification_failure.text + caplog.text
    assert canary not in observable


def test_unexpected_cli_failures_do_not_disclose_request_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canary = "private-cli-canary-69384c6b"
    request = _request(canary)
    result = analyze_proteogenomic_state(request)
    envelope = ReplayVerificationRequest(request=request, result=result)
    request_path = tmp_path / "request.json"
    envelope_path = tmp_path / "envelope.json"
    request_path.write_text(request.model_dump_json(), encoding="utf-8")
    envelope_path.write_text(envelope.model_dump_json(), encoding="utf-8")

    with monkeypatch.context() as scoped:
        scoped.setattr(
            adapter,
            "analyze_proteogenomic_state",
            _raise_sensitive_runtime_error(canary),
        )
        analysis_failure = CliRunner().invoke(adapter.cli, ["analyze", str(request_path)])

    with monkeypatch.context() as scoped:
        scoped.setattr(
            adapter,
            "verify_proteogenomic_replay",
            _raise_sensitive_runtime_error(canary),
        )
        verification_failure = CliRunner().invoke(adapter.cli, ["verify", str(envelope_path)])

    assert analysis_failure.exit_code != 0
    assert verification_failure.exit_code != 0
    assert analysis_failure.exception is not None
    assert verification_failure.exception is not None
    rendered = (
        analysis_failure.output
        + verification_failure.output
        + "".join(traceback.format_exception(analysis_failure.exception))
        + "".join(traceback.format_exception(verification_failure.exception))
    )
    assert canary not in rendered
    assert "failed safely" in analysis_failure.output
    assert "failed safely" in verification_failure.output
