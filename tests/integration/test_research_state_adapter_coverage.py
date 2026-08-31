"""Fail-closed branch coverage for the narrow ECGI HTTP and CLI adapter."""

# ruff: noqa: PLR2004, TRY003

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from glio_proteogen.adapters import research_state as adapter
from glio_proteogen.adapters.api import create_app
from glio_proteogen.research.proteogenomic_state import synthetic_demo_request
from glio_proteogen.research.proteogenomic_state.canonical import canonical_json_bytes

if TYPE_CHECKING:
    from pathlib import Path


class _ExhaustedSlots:
    def acquire(self, *, blocking: bool) -> bool:
        assert blocking is False
        return False

    def release(self) -> None:
        raise AssertionError("an unacquired slot must not be released")


def _raise_value_error(_value: object) -> Any:
    raise ValueError("private diagnostic must be sanitized")


def test_http_rejects_wrong_media_type_and_malformed_json(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        wrong_media = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "text/plain"},
        )
        malformed = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=b'{"sample_id":',
            headers={"content-type": "application/json"},
        )

    assert wrong_media.status_code == 415
    assert wrong_media.json() == {"detail": "content-type must be application/json"}
    assert malformed.status_code == 422
    assert malformed.json() == {"detail": "request does not satisfy the research-state contract"}


def test_analysis_and_replay_capacity_gates_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _ExhaustedSlots())
    request = synthetic_demo_request()

    with pytest.raises(HTTPException, match="capacity") as analysis_error:
        adapter._execute(request)
    with pytest.raises(HTTPException, match="capacity") as replay_error:
        adapter._execute_verification(object())  # type: ignore[arg-type]

    assert analysis_error.value.status_code == 429
    assert replay_error.value.status_code == 429


def test_execute_sanitizes_engine_errors_and_enforces_result_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", _raise_value_error)
    with pytest.raises(HTTPException, match="could not be evaluated") as analysis_error:
        adapter._execute(request)
    assert analysis_error.value.status_code == 422

    monkeypatch.setattr(adapter, "analyze_proteogenomic_state", lambda _request: object())
    monkeypatch.setattr(
        adapter,
        "canonical_json_bytes",
        lambda _value: b"x" * (adapter.RESEARCH_STATE_RESULT_MAX_BYTES + 1),
    )
    with pytest.raises(HTTPException, match="transport bound") as size_error:
        adapter._execute(request)
    assert size_error.value.status_code == 500


def test_execute_verification_sanitizes_engine_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapter, "verify_proteogenomic_replay", _raise_value_error)
    with pytest.raises(HTTPException, match="replay envelope") as replay_error:
        adapter._execute_verification(object())  # type: ignore[arg-type]
    assert replay_error.value.status_code == 422


def test_cli_file_and_engine_failures_are_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_bytes(b'{"duplicate":1,"duplicate":2}')
    with pytest.raises(adapter.ResearchStateCliError, match="does not satisfy"):
        adapter._read_typed(
            invalid_path,
            adapter._REQUEST_ADAPTER,
            adapter.RESEARCH_STATE_REQUEST_MAX_BYTES,
        )

    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical_json_bytes(synthetic_demo_request().model_dump(mode="json")))
    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "analyze_proteogenomic_state", _raise_value_error)
        with pytest.raises(adapter.ResearchStateCliError, match="analysis failed safely"):
            adapter.cli_analyze(request_path)

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "analyze_proteogenomic_state", lambda _request: object())
        scoped.setattr(
            adapter,
            "canonical_json_bytes",
            lambda _value: b"x" * (adapter.RESEARCH_STATE_RESULT_MAX_BYTES + 1),
        )
        with pytest.raises(adapter.ResearchStateCliError, match="analysis failed safely"):
            adapter.cli_analyze(request_path)

    with monkeypatch.context() as scoped:
        scoped.setattr(adapter, "_read_typed", lambda *_args: object())
        scoped.setattr(adapter, "verify_proteogenomic_replay", _raise_value_error)
        with pytest.raises(adapter.ResearchStateCliError, match="replay failed safely"):
            adapter.cli_verify(tmp_path / "unused.json")


def test_bare_research_router_enforces_admission_headers_and_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_research_state_openapi(app)
    monkeypatch.setattr(adapter, "_ANALYSIS_SLOTS", _ExhaustedSlots())
    monkeypatch.setattr(
        adapter,
        "_decode_typed",
        lambda *_args: pytest.fail("capacity must be acquired before request parsing"),
    )

    with TestClient(app) as client:
        response = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        openapi = client.get("/openapi.json").json()

    assert response.status_code == 429
    assert response.headers["retry-after"] == str(adapter.RESEARCH_STATE_RETRY_AFTER_SECONDS)
    assert response.headers["cache-control"] == "no-store"
    responses = openapi["paths"][
        f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze"
    ]["post"]["responses"]
    assert set(responses) == {"200", "400", "413", "415", "422", "429", "499", "500", "504"}


def test_bare_research_router_rejects_oversize_before_json_parsing() -> None:
    app = FastAPI()
    app.include_router(adapter.router)
    body = b"{}" + b" " * (adapter.RESEARCH_STATE_REQUEST_MAX_BYTES - 1)

    with TestClient(app) as client:
        response = client.post(
            f"{adapter.RESEARCH_STATE_ROUTE_PREFIX}/analyze",
            content=body,
            headers={"content-type": "application/json"},
        )

    assert len(body) == adapter.RESEARCH_STATE_REQUEST_MAX_BYTES + 1
    assert response.status_code == 413
    assert response.json() == {"detail": "request body exceeds the byte limit"}
    assert response.headers["cache-control"] == "no-store"
