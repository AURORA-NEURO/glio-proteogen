"""Transport and integration checks for aggregate replication receipts."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from threading import BoundedSemaphore

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from typer.testing import CliRunner

from glio_proteogen.adapters import cohort_replication as adapter
from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware
from glio_proteogen.research.cohort_replication import synthetic_demo_request
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)

PREFIX = adapter.COHORT_REPLICATION_ROUTE_PREFIX


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(adapter.router)
    adapter.install_cohort_replication_openapi(app)
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=adapter.COHORT_REPLICATION_REQUEST_MAX_BYTES,
        route_limits={
            f"{PREFIX}/verify": (
                adapter.COHORT_REPLICATION_REPLAY_MAX_BYTES,
                adapter.COHORT_REPLICATION_RESULT_MAX_BYTES,
            )
        },
    )
    with TestClient(app) as transport:
        yield transport


def test_demo_analysis_replay_and_source_headers(client):
    profile = client.get(f"{PREFIX}/profile")
    demo = client.get(f"{PREFIX}/demo")
    assert profile.status_code == demo.status_code == 200
    request = demo.json()
    response = client.post(f"{PREFIX}/analyze", json=request)
    assert response.status_code == 200
    result = response.json()
    assert result["profile_digest"] == profile.json()["profile_digest"]
    assert response.headers["x-glio-request-digest"] == demo.headers["x-glio-request-digest"]
    assert response.headers["x-glio-result-digest"] == result["result_digest"]
    assert response.headers["cache-control"] == "no-store"
    checked = client.post(f"{PREFIX}/verify", json={"request": request, "result": result})
    assert checked.status_code == 200
    assert checked.json()["valid"] is True
    assert checked.headers["x-glio-result-digest"] == result["result_digest"]


def test_replay_rejects_changed_scientific_result(client):
    request = client.get(f"{PREFIX}/demo").json()
    result = client.post(f"{PREFIX}/analyze", json=request).json()
    result["features"][0]["label"] = "tampered aggregate label"
    checked = client.post(f"{PREFIX}/verify", json={"request": request, "result": result})
    assert checked.status_code == 200
    assert checked.json()["valid"] is False


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b"[]", b"null", b"{"])
def test_strict_json_failures_are_sanitized(client, payload):
    response = client.post(
        f"{PREFIX}/analyze", content=payload, headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "request does not satisfy the cohort-replication contract"}
    assert response.headers["cache-control"] == "no-store"


def test_overlapping_cohort_declaration_is_rejected(client):
    payload = synthetic_demo_request().model_dump(mode="json")
    payload["cohorts"][1]["independence_group"] = payload["cohorts"][0]["independence_group"]
    assert client.post(f"{PREFIX}/analyze", json=payload).status_code == 422


def test_unsupported_media_type_and_oversized_envelopes(client):
    assert client.post(f"{PREFIX}/analyze", content="{}").status_code == 415
    oversized = client.post(
        f"{PREFIX}/analyze",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "2097153"},
    )
    assert oversized.status_code == 413


def test_capacity_rejection_is_retryable_and_does_not_leak_input(client, monkeypatch):
    slots = BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(adapter, "_SLOTS", slots)
    response = client.post(f"{PREFIX}/analyze", json=client.get(f"{PREFIX}/demo").json())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"
    slots.release()


def test_numerical_failure_is_sanitized_and_slot_is_released(client, monkeypatch):
    def fail(_request):
        raise RuntimeError("private source path and numerical internals")  # noqa: TRY003 - probe sanitization.

    request = client.get(f"{PREFIX}/demo").json()
    original = adapter.analyze_replication
    monkeypatch.setattr(adapter, "analyze_replication", fail)
    failed = client.post(f"{PREFIX}/analyze", json=request)
    assert failed.status_code == 500
    assert "private" not in failed.text
    monkeypatch.setattr(adapter, "analyze_replication", original)
    assert client.post(f"{PREFIX}/analyze", json=request).status_code == 200


def test_openapi_describes_strict_analysis_and_replay(client):
    schema = client.get("/openapi.json").json()
    for operation in ("analyze", "verify"):
        reference = schema["paths"][f"{PREFIX}/{operation}"]["post"]["requestBody"]["content"][
            "application/json"
        ]["schema"]["$ref"]
        name = reference.rsplit("/", 1)[-1]
        contract = schema["components"]["schemas"][name]
        assert contract["additionalProperties"] is False


def test_cli_analysis_and_false_replay_exit_status(tmp_path):
    runner = CliRunner()
    demo = runner.invoke(adapter.cli, ["demo"])
    assert demo.exit_code == 0
    request_file = tmp_path / "request.json"
    request_file.write_text(demo.stdout, encoding="utf-8")
    analysis = runner.invoke(adapter.cli, ["analyze", str(request_file)])
    assert analysis.exit_code == 0
    result = json.loads(analysis.stdout)
    envelope = {"request": json.loads(demo.stdout), "result": result}
    envelope_file = tmp_path / "receipt.json"
    envelope_file.write_text(json.dumps(envelope), encoding="utf-8")
    verified = runner.invoke(adapter.cli, ["verify", str(envelope_file)])
    assert verified.exit_code == 0
    assert json.loads(verified.stdout)["valid"] is True
    corrupted = deepcopy(envelope)
    corrupted["result"]["features"][0]["label"] = "modified"
    envelope_file.write_text(json.dumps(corrupted), encoding="utf-8")
    rejected = runner.invoke(adapter.cli, ["verify", str(envelope_file)])
    assert rejected.exit_code == 1
    assert json.loads(rejected.stdout)["valid"] is False


def streamed_request(chunks, *, headers=(), disconnect=False, delay=0.0):
    """Expose actual ASGI body chunks without a buffering middleware."""

    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    if disconnect:
        messages = [{"type": "http.disconnect"}]
    reads = []

    async def receive():
        if delay:
            await asyncio.sleep(delay)
        reads.append(True)
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    scope = {"type": "http", "method": "POST", "path": f"{PREFIX}/analyze", "headers": headers}
    return Request(scope, receive), reads


@pytest.mark.parametrize("declared", [b"invalid", b"-1"])
def test_adapter_rejects_malformed_length_before_consuming_body(declared):
    request, reads = streamed_request([b"{}"], headers=[(b"content-length", declared)])
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(adapter._bounded_body(request, 32))
    assert rejected.value.status_code == 400
    assert rejected.value.detail == "invalid content-length"
    assert reads == []


def test_declared_and_actual_chunked_limits_are_enforced_without_middleware():
    request, reads = streamed_request([b"{}"], headers=[(b"content-length", b"33")])
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(adapter._bounded_body(request, 32))
    assert rejected.value.status_code == 413
    assert reads == []
    exact, _reads = streamed_request([b"abc", b"def"])
    assert asyncio.run(adapter._bounded_body(exact, 6)) == b"abcdef"
    oversized, reads = streamed_request([b"abc", b"def", b"must-not-be-consumed"])
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(adapter._bounded_body(oversized, 5))
    assert rejected.value.status_code == 413
    assert len(reads) == 2


def test_disconnect_during_body_read_returns_cancellation():
    request, _reads = streamed_request([], disconnect=True)
    with pytest.raises(HTTPException) as cancelled:
        asyncio.run(adapter._bounded_body(request, 32))
    assert cancelled.value.status_code == 499
    assert cancelled.value.detail == "cohort-replication computation was cancelled"


@pytest.mark.parametrize("condition", ["body_timeout", "deadline", "cancelled"])
def test_parsing_obeys_deadline_and_cancellation_before_computation(condition):
    headers = [(b"content-type", b"application/json; charset=utf-8")]
    if condition == "body_timeout":
        context = CancellationContext.with_timeout(0.001)
        request, _reads = streamed_request([b"{}"], headers=headers, delay=1.0)
    else:
        context = (
            CancellationContext(deadline=0.0, clock=lambda: 1.0)
            if condition == "deadline"
            else CancellationContext()
        )
        if condition == "cancelled":
            context.cancel()
        request, _reads = streamed_request([b"{}"], headers=headers)
    with pytest.raises(HTTPException) as stopped:
        asyncio.run(adapter._typed_body(request, adapter._REQUEST_ADAPTER, 1024, context))
    assert stopped.value.status_code == (499 if condition == "cancelled" else 504)
    assert stopped.value.headers["Cache-Control"] == "no-store"


def test_disconnect_watcher_cancels_after_an_open_connection_poll(monkeypatch):
    class Connection:
        calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls >= 2

    async def watch():
        context = CancellationContext()
        connection = Connection()
        await adapter._watch_disconnect(connection, context, asyncio.Event())
        assert connection.calls == 2
        with pytest.raises(InferenceCancelledError):
            context.checkpoint()

    monkeypatch.setattr(adapter, "_DISCONNECT_POLL_SECONDS", 0.001)
    asyncio.run(watch())


@pytest.mark.parametrize("operation", ["analyze", "verify"])
@pytest.mark.parametrize(
    ("error", "status"),
    [
        (InferenceCancelledError("private cancellation internals"), 499),
        (InferenceDeadlineExceededError("private deadline internals"), 504),
        (ValueError("private numerical input"), 422),
        (RuntimeError("private numerical engine state"), 500),
    ],
)
def test_execution_failures_are_sanitized_and_capacity_recovers(
    client, monkeypatch, operation, error, status
):
    request = synthetic_demo_request()
    envelope = {
        "request": request.model_dump(mode="json"),
        "result": adapter.analyze_replication(request).model_dump(mode="json"),
    }
    payload = request.model_dump(mode="json") if operation == "analyze" else envelope
    attribute = "analyze_replication" if operation == "analyze" else "verify_replay"
    original = getattr(adapter, attribute)
    slots = BoundedSemaphore(1)
    monkeypatch.setattr(adapter, "_SLOTS", slots)

    def fail(*_arguments):
        raise error

    monkeypatch.setattr(adapter, attribute, fail)
    response = client.post(f"{PREFIX}/{operation}", json=payload)
    assert response.status_code == status
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"
    monkeypatch.setattr(adapter, attribute, original)
    assert client.post(f"{PREFIX}/{operation}", json=payload).status_code == 200


@pytest.mark.parametrize(
    ("operation", "bound", "detail"),
    [
        (
            "analyze",
            "COHORT_REPLICATION_RESULT_MAX_BYTES",
            "cohort-replication result exceeded its bound",
        ),
        (
            "analyze",
            "COHORT_REPLICATION_REPLAY_MAX_BYTES",
            "cohort-replication receipt exceeded its bound",
        ),
        (
            "verify",
            "COHORT_REPLICATION_RESULT_MAX_BYTES",
            "cohort-replication verification exceeded its bound",
        ),
    ],
)
def test_oversized_output_or_receipt_fails_closed_and_releases_slot(
    client, monkeypatch, operation, bound, detail
):
    request = synthetic_demo_request()
    result = adapter.analyze_replication(request)
    payload = (
        request.model_dump(mode="json")
        if operation == "analyze"
        else {"request": request.model_dump(mode="json"), "result": result.model_dump(mode="json")}
    )
    previous = getattr(adapter, bound)
    monkeypatch.setattr(adapter, "_SLOTS", BoundedSemaphore(1))
    monkeypatch.setattr(adapter, bound, 1)
    failed = client.post(f"{PREFIX}/{operation}", json=payload)
    assert failed.status_code == 500
    assert failed.json() == {"detail": detail}
    monkeypatch.setattr(adapter, bound, previous)
    assert client.post(f"{PREFIX}/{operation}", json=payload).status_code == 200


@pytest.mark.parametrize(
    ("operation", "attribute"),
    [
        ("profile", "algorithm_profile"),
        ("demo", "algorithm_profile"),
        ("demo", "synthetic_demo_request"),
    ],
)
def test_profile_and_demo_integrity_failures_are_sanitized(
    client, monkeypatch, operation, attribute
):
    def fail():
        raise RuntimeError("private local profile source")  # noqa: TRY003 - probe sanitization.

    monkeypatch.setattr(adapter, attribute, fail)
    response = client.get(f"{PREFIX}/{operation}")
    assert response.status_code == 500
    assert response.json() == {"detail": f"cohort-replication {operation} failed safely"}
    assert "private" not in response.text


@pytest.mark.parametrize("operation", ["analyze", "verify"])
@pytest.mark.parametrize(
    "payload", ['{"analysis_id":"one","analysis_id":"two"}', '{"effect":NaN}', "[]"]
)
def test_cli_rejects_non_strict_or_structurally_invalid_inputs(tmp_path, operation, payload):
    path = tmp_path / "invalid.json"
    path.write_text(payload, encoding="utf-8")
    result = CliRunner().invoke(adapter.cli, [operation, str(path)])
    assert result.exit_code == 2
    assert "input does not satisfy the cohort-replication contract" in result.output
    assert not result.stdout.strip()


def test_cli_input_read_errors_and_byte_limit_are_sanitized(tmp_path, monkeypatch):
    path = tmp_path / "request.json"
    path.write_text(synthetic_demo_request().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(adapter, "COHORT_REPLICATION_REQUEST_MAX_BYTES", 1)
    oversized = CliRunner().invoke(adapter.cli, ["analyze", str(path)])
    assert oversized.exit_code == 2
    assert "input does not satisfy" in oversized.output

    def unreadable(*_arguments):
        raise OSError("private local filesystem path")  # noqa: TRY003 - probe sanitization.

    monkeypatch.setattr(adapter, "read_bounded", unreadable)
    unreadable_result = CliRunner().invoke(adapter.cli, ["analyze", str(path)])
    assert unreadable_result.exit_code == 2
    assert "private" not in unreadable_result.output


def test_cli_profile_emits_bound_numerical_policy():
    result = CliRunner().invoke(adapter.cli, ["profile"])
    assert result.exit_code == 0
    profile = json.loads(result.stdout)
    assert profile["profile_id"] == "glioma-cohort-replication/1.0.0"
    assert profile["profile_digest"].startswith("sha256:")
    assert any("Benjamini-Yekutieli" in method for method in profile["methods"])


@pytest.mark.parametrize(
    ("command", "attribute", "message"),
    [
        ("profile", "algorithm_profile", "cohort-replication analysis failed safely"),
        ("demo", "synthetic_demo_request", "cohort-replication analysis failed safely"),
        ("analyze", "analyze_replication", "cohort-replication analysis failed safely"),
        ("verify", "verify_replay", "cohort-replication replay failed safely"),
    ],
)
def test_cli_internal_failures_do_not_expose_private_details(
    tmp_path, monkeypatch, command, attribute, message
):
    request = synthetic_demo_request()
    result = adapter.analyze_replication(request)
    payload = (
        request.model_dump(mode="json")
        if command == "analyze"
        else {"request": request.model_dump(mode="json"), "result": result.model_dump(mode="json")}
    )
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    def fail(*_arguments):
        raise RuntimeError("private local source and model state")  # noqa: TRY003 - probe sanitization.

    monkeypatch.setattr(adapter, attribute, fail)
    arguments = [command, str(path)] if command in {"analyze", "verify"} else [command]
    failed = CliRunner().invoke(adapter.cli, arguments)
    assert failed.exit_code == 2
    assert message in failed.output
    assert "private" not in failed.output
    assert not failed.stdout.strip()


def test_cli_never_emits_an_oversized_analysis_result(tmp_path, monkeypatch):
    path = tmp_path / "request.json"
    path.write_text(synthetic_demo_request().model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(adapter, "COHORT_REPLICATION_RESULT_MAX_BYTES", 1)
    response = CliRunner().invoke(adapter.cli, ["analyze", str(path)])
    assert response.exit_code == 2
    assert "cohort-replication result exceeded its bound" in response.output
    assert not response.stdout.strip()
