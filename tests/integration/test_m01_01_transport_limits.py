"""Prove transport byte ceilings run before JSON or Pydantic parsing."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

import pytest
import typer
from starlette.types import Message, Receive, Scope, Send

from glio_proteogen.adapters import cli
from glio_proteogen.adapters.limits import (
    MAX_REQUEST_BYTES,
    RequestBodyTooLargeError,
    RequestSizeLimitMiddleware,
    _empty_receive,
    read_bounded,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, StrictJsonErrorCode
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    plugin as plugin_module,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.plugin import (
    M0101Plugin,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import TypeAdapter

    from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
        M0101Service,
    )

pytestmark = pytest.mark.integration

type AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]

HTTP_BAD_REQUEST = 400
HTTP_PAYLOAD_TOO_LARGE = 413
CLI_INVALID_INPUT = 2


def _http_scope(
    *,
    headers: list[tuple[bytes, bytes]],
    path: str = "/v1/modules/M01-01/protocols",
) -> Scope:
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
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "state": {},
        },
    )


def _response(messages: list[Message]) -> tuple[int, dict[str, str]]:
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"") for message in messages if message["type"] == "http.response.body"
    )
    return start["status"], json.loads(body)


def test_declared_body_over_four_mib_is_rejected_before_downstream_app() -> None:
    downstream_called = False
    receive_called = False
    messages: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        nonlocal receive_called
        receive_called = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    scope = _http_scope(headers=[(b"content-length", str(MAX_REQUEST_BYTES + 1).encode("ascii"))])
    asyncio.run(RequestSizeLimitMiddleware(downstream)(scope, receive, send))

    assert _response(messages) == (
        HTTP_PAYLOAD_TOO_LARGE,
        {"detail": "request body exceeds the byte limit"},
    )
    assert downstream_called is False
    assert receive_called is False


def test_streamed_body_over_four_mib_is_rejected_before_parser() -> None:
    parser_called = False
    messages: list[Message] = []
    chunks = iter(
        (
            {"type": "http.request", "body": b"{", "more_body": True},
            {
                "type": "http.request",
                "body": b"x" * MAX_REQUEST_BYTES,
                "more_body": False,
            },
        )
    )

    async def downstream(_scope: Scope, receive: Receive, _send: Send) -> None:
        nonlocal parser_called
        body = bytearray()
        while True:
            message = await receive()
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        json.loads(body)
        parser_called = True

    async def receive() -> Message:
        return next(chunks)

    async def send(message: Message) -> None:
        messages.append(message)

    middleware = RequestSizeLimitMiddleware(cast("AsgiApp", downstream))
    asyncio.run(middleware(_http_scope(headers=[]), receive, send))

    assert _response(messages) == (
        HTTP_PAYLOAD_TOO_LARGE,
        {"detail": "request body exceeds the byte limit"},
    )
    assert parser_called is False


def test_verify_path_can_use_independent_result_transport_ceiling() -> None:
    downstream_called = False
    messages: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    middleware = RequestSizeLimitMiddleware(
        cast("AsgiApp", downstream),
        max_bytes=16,
        result_max_bytes=32,
    )
    asyncio.run(
        middleware(
            _http_scope(
                headers=[(b"content-length", b"24")],
                path="/v1/modules/M03-05/artifacts/verify",
            ),
            receive,
            send,
        )
    )

    assert downstream_called is True
    assert messages == []


def test_explicit_path_limit_can_widen_one_binary_route() -> None:
    downstream_called = False
    messages: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        return {"type": "http.request", "body": b"x" * 24, "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    middleware = RequestSizeLimitMiddleware(
        cast("AsgiApp", downstream),
        max_bytes=16,
        path_max_bytes={"/v1/modules/M01-03/inspect": 32},
    )
    asyncio.run(
        middleware(
            _http_scope(
                headers=[(b"content-length", b"24")],
                path="/v1/modules/M01-03/inspect",
            ),
            receive,
            send,
        )
    )

    assert downstream_called is True
    assert messages == []


def test_verify_path_still_rejects_body_above_result_ceiling() -> None:
    downstream_called = False
    messages: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        raise AssertionError  # pragma: no cover - header rejection must precede receive.

    async def send(message: Message) -> None:
        messages.append(message)

    middleware = RequestSizeLimitMiddleware(
        cast("AsgiApp", downstream),
        max_bytes=16,
        result_max_bytes=32,
    )
    asyncio.run(
        middleware(
            _http_scope(
                headers=[(b"content-length", b"33")],
                path="/v1/modules/M03-05/artifacts/verify",
            ),
            receive,
            send,
        )
    )

    assert downstream_called is False
    assert _response(messages) == (
        HTTP_PAYLOAD_TOO_LARGE,
        {"detail": "request body exceeds the byte limit"},
    )


def test_cli_reader_accepts_exact_limit_and_rejects_first_excess_byte(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exact = tmp_path / "exact.json"
    oversized = tmp_path / "oversized.json"
    exact.write_bytes(b"x" * MAX_REQUEST_BYTES)
    oversized.write_bytes(b"x" * (MAX_REQUEST_BYTES + 1))

    assert len(read_bounded(exact)) == MAX_REQUEST_BYTES
    with pytest.raises(RequestBodyTooLargeError, match="exceeds the byte limit"):
        read_bounded(oversized)

    class ParserSpy:
        called = False

        def validate_json(self, _payload: bytes, *, strict: object) -> object:
            self.called = True
            raise AssertionError(strict)

    parser = ParserSpy()
    with pytest.raises(typer.Exit) as exit_info:
        cli._load_request(oversized, cast("TypeAdapter[object]", parser))

    assert exit_info.value.exit_code == CLI_INVALID_INPUT
    assert parser.called is False
    assert "invalid request: request body exceeds the byte limit" in capsys.readouterr().err


def test_plugin_rejects_oversized_raw_json_before_pydantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ParserSpy:
        called = False

        def validate_json(self, _payload: bytes, *, strict: object) -> object:
            self.called = True
            raise AssertionError(strict)

    parser = ParserSpy()
    monkeypatch.setattr(
        plugin_module,
        "_REQUEST_ADAPTER",
        cast("TypeAdapter[object]", parser),
    )
    plugin = M0101Plugin(cast("M0101Service", object()))

    with pytest.raises(StrictJsonError) as captured:
        plugin.validate(b" " * (MAX_REQUEST_BYTES + 1))

    assert captured.value.code is StrictJsonErrorCode.TOO_LARGE
    assert parser.called is False


@pytest.mark.parametrize("declared_length", [b"not-an-integer", b"-1"])
def test_invalid_content_length_is_rejected_without_downstream_call(
    declared_length: bytes,
) -> None:
    downstream_called = False
    messages: list[Message] = []

    async def downstream(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal downstream_called
        downstream_called = True

    async def receive() -> Message:
        raise AssertionError

    async def send(message: Message) -> None:
        messages.append(message)

    scope = _http_scope(headers=[(b"content-length", declared_length)])
    asyncio.run(RequestSizeLimitMiddleware(downstream)(scope, receive, send))

    assert _response(messages) == (HTTP_BAD_REQUEST, {"detail": "invalid content-length"})
    assert downstream_called is False


def test_non_http_scope_and_non_request_messages_pass_through() -> None:
    websocket_called = False
    disconnect_seen = False

    async def websocket_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        nonlocal websocket_called
        websocket_called = True

    async def unused_receive() -> Message:
        raise AssertionError

    async def unused_send(_message: Message) -> None:
        return None

    websocket_scope = cast(
        "Scope",
        {"type": "websocket", "headers": [], "path": "/synthetic"},
    )
    asyncio.run(
        RequestSizeLimitMiddleware(websocket_app)(
            websocket_scope,
            unused_receive,
            unused_send,
        )
    )

    async def http_app(_scope: Scope, receive: Receive, _send: Send) -> None:
        nonlocal disconnect_seen
        disconnect_seen = (await receive())["type"] == "http.disconnect"

    async def disconnect() -> Message:
        return {"type": "http.disconnect"}

    asyncio.run(
        RequestSizeLimitMiddleware(http_app)(
            _http_scope(headers=[]),
            disconnect,
            unused_send,
        )
    )

    assert websocket_called is True
    assert disconnect_seen is True


def test_empty_receive_is_a_terminal_empty_request() -> None:
    assert asyncio.run(_empty_receive()) == {
        "type": "http.request",
        "body": b"",
        "more_body": False,
    }
