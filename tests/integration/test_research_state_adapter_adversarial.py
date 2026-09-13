"""Failure-path coverage for the narrow research HTTP and CLI adapter."""

from __future__ import annotations

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
    ReplayVerificationRequest,
    analyze_proteogenomic_state,
    verify_proteogenomic_replay,
)

if TYPE_CHECKING:
    from pathlib import Path

_PREFIX = adapter.RESEARCH_STATE_ROUTE_PREFIX
_HTTP_INTERNAL_ERROR = 500
_HTTP_MEDIA_TYPE = 415
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_UNPROCESSABLE = 422
_SENSITIVE_ENGINE_DETAIL = "sensitive engine detail"
_SENSITIVE_REPLAY_DETAIL = "sensitive replay detail"
_UNAVAILABLE_RELEASE_MESSAGE = "an unavailable slot cannot be released"


class _UnavailableSlots:
    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return False

    def release(self) -> None:
        raise AssertionError(_UNAVAILABLE_RELEASE_MESSAGE)


class _TrackingSlot:
    def __init__(self) -> None:
        self.released = False

    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return True

    def release(self) -> None:
        self.released = True


def _small_request() -> ProteogenomicStateRequest:
    return ProteogenomicStateRequest(
        sample_id="adapter.small",
        nodes=(GraphNode(node_id="protein.signal", kind=NodeKind.PROTEIN),),
        bootstrap_replicates=8,
        permutation_replicates=32,
    )


def _write(path: Path, value: str) -> Path:
    path.write_text(value, encoding="utf-8")
    return path


def test_http_rejects_media_type_ambiguous_json_and_capacity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verification_request = _small_request()
    verification_envelope = {
        "request": verification_request.model_dump(mode="json"),
        "result": analyze_proteogenomic_state(verification_request).model_dump(mode="json"),
    }
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        request = client.get(f"{_PREFIX}/demo").json()
        wrong_media = client.post(
            f"{_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        duplicate_json = client.post(
            f"{_PREFIX}/analyze",
            content=b'{"sample_id":"secret-a","sample_id":"secret-b"}',
            headers={"content-type": "application/json"},
        )
        monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
        unavailable = client.post(f"{_PREFIX}/analyze", json=request)
        unavailable_verify = client.post(
            f"{_PREFIX}/verify",
            json=verification_envelope,
        )

    assert wrong_media.status_code == _HTTP_MEDIA_TYPE
    assert duplicate_json.status_code == _HTTP_UNPROCESSABLE
    assert "secret" not in duplicate_json.text
    assert unavailable.status_code == _HTTP_TOO_MANY_REQUESTS
    assert unavailable_verify.status_code == _HTTP_TOO_MANY_REQUESTS


def test_execute_sanitizes_engine_failure_releases_slot_and_bounds_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _small_request()
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)

    def fail_analysis(_request: ProteogenomicStateRequest) -> None:
        raise ValueError(_SENSITIVE_ENGINE_DETAIL)

    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", fail_analysis)
    with pytest.raises(HTTPException) as failure:
        adapter._execute(request)
    assert failure.value.status_code == _HTTP_UNPROCESSABLE
    assert "sensitive" not in str(failure.value.detail)
    assert slot.released is True

    result = analyze_proteogenomic_state(request)
    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", lambda _request: result)
    monkeypatch.setattr(
        adapter,
        "canonical_json_bytes",
        lambda _value: b"x" * (adapter.RESEARCH_STATE_RESULT_MAX_BYTES + 1),
    )
    with pytest.raises(HTTPException) as oversized:
        adapter._execute(request)
    assert oversized.value.status_code == _HTTP_INTERNAL_ERROR


def test_verify_sanitizes_service_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _small_request()
    envelope = ReplayVerificationRequest(
        request=request,
        result=analyze_proteogenomic_state(request),
    )
    slot = _TrackingSlot()
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", slot)

    def fail_verification(_request: ReplayVerificationRequest) -> None:
        raise ValueError(_SENSITIVE_REPLAY_DETAIL)

    monkeypatch.setattr(adapter, "verify_proteogenomic_replay", fail_verification)
    with pytest.raises(HTTPException) as failure:
        adapter._execute_verification(envelope)
    assert failure.value.status_code == _HTTP_UNPROCESSABLE
    assert "sensitive" not in str(failure.value.detail)
    assert slot.released is True

    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _UnavailableSlots())
    with pytest.raises(HTTPException) as unavailable:
        adapter._execute_verification(envelope)
    assert unavailable.value.status_code == _HTTP_TOO_MANY_REQUESTS


def test_cli_rejects_invalid_input_and_sanitizes_engine_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    invalid = _write(
        tmp_path / "invalid.json",
        '{"sample_id":"secret-a","sample_id":"secret-b"}',
    )
    invalid_result = runner.invoke(adapter.cli, ["analyze", str(invalid)])
    assert invalid_result.exit_code != 0
    assert "secret" not in invalid_result.output
    assert "does not satisfy" in invalid_result.output

    request_path = _write(tmp_path / "request.json", _small_request().model_dump_json())

    def fail_analysis(_request: ProteogenomicStateRequest) -> None:
        raise ValueError(_SENSITIVE_ENGINE_DETAIL)

    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", fail_analysis)
    failed = runner.invoke(adapter.cli, ["analyze", str(request_path)])
    assert failed.exit_code != 0
    assert "sensitive" not in failed.output
    assert "failed safely" in failed.output


def test_cli_enforces_result_bound_and_failed_replay_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    request = _small_request()
    result = analyze_proteogenomic_state(request)
    request_path = _write(tmp_path / "request.json", request.model_dump_json())
    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", lambda _request: result)
    monkeypatch.setattr(
        adapter,
        "canonical_json_bytes",
        lambda _value: b"x" * (adapter.RESEARCH_STATE_RESULT_MAX_BYTES + 1),
    )
    oversized = runner.invoke(adapter.cli, ["analyze", str(request_path)])
    assert oversized.exit_code != 0
    assert "failed safely" in oversized.output

    monkeypatch.undo()
    envelope = ReplayVerificationRequest(request=request, result=result)
    envelope_path = _write(tmp_path / "envelope.json", envelope.model_dump_json())
    verified = verify_proteogenomic_replay(envelope)
    mismatch = verified.model_copy(
        update={"verified": False, "message": "Replay mismatch detected."}
    )
    monkeypatch.setattr(adapter, "verify_proteogenomic_replay", lambda _request: mismatch)
    rejected = runner.invoke(adapter.cli, ["verify", str(envelope_path)])
    assert rejected.exit_code == 1
    assert '"verified":false' in rejected.output


def test_cli_read_and_verify_failures_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(adapter.ResearchStateCliError):
        adapter._read_typed(
            missing,
            adapter._REQUEST_ADAPTER,
            adapter.RESEARCH_STATE_REQUEST_MAX_BYTES,
        )

    request = _small_request()
    envelope = ReplayVerificationRequest(
        request=request,
        result=analyze_proteogenomic_state(request),
    )
    envelope_path = _write(tmp_path / "envelope.json", envelope.model_dump_json())

    def fail_verification(_request: ReplayVerificationRequest) -> None:
        raise ValueError(_SENSITIVE_REPLAY_DETAIL)

    monkeypatch.setattr(adapter, "verify_proteogenomic_replay", fail_verification)
    outcome = CliRunner().invoke(adapter.cli, ["verify", str(envelope_path)])
    assert outcome.exit_code != 0
    assert "sensitive" not in outcome.output
    assert "failed safely" in outcome.output
