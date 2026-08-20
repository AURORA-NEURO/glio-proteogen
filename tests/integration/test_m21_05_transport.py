"""Prove the M21-05 FastAPI boundary caps streamed request bodies."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from starlette.types import Message, Receive, Scope, Send

from glio_proteogen.modules.c21_complex_activity.m21_05_subgroup_equity_evaluator import (
    api as api_module,
)

HTTP_PAYLOAD_TOO_LARGE = 413


def _scope(path: str) -> Scope:
    return cast(
        "Scope",
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {},
        },
    )


def _response_status(messages: list[Message]) -> int:
    start = next(message for message in messages if message["type"] == "http.response.start")
    return int(start["status"])


@pytest.mark.parametrize(
    ("path", "limit"),
    [
        ("/v1/modules/M21-05/validate", "request"),
        ("/v1/modules/M21-05/verify", "result"),
    ],
)
def test_chunked_oversized_body_is_rejected_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    limit: str,
) -> None:
    request_limit = 16
    result_limit = 32
    monkeypatch.setattr(api_module, "M2105_MAX_CANONICAL_REQUEST_BYTES", request_limit)
    monkeypatch.setattr(api_module, "M2105_MAX_CANONICAL_RESULT_BYTES", result_limit)
    app = api_module.create_app()
    ceiling = request_limit if limit == "request" else result_limit
    chunks = iter(
        (
            {"type": "http.request", "body": b"{", "more_body": True},
            {"type": "http.request", "body": b"x" * ceiling, "more_body": False},
        )
    )
    messages: list[Message] = []

    async def receive() -> Message:
        return next(chunks)

    async def send(message: Message) -> None:
        messages.append(message)

    asyncio.run(app(_scope(path), cast("Receive", receive), cast("Send", send)))

    assert _response_status(messages) == HTTP_PAYLOAD_TOO_LARGE
    assert json.loads(
        b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
    ) == {"detail": "request body exceeds the byte limit"}
