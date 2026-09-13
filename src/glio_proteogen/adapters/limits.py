"""Transport limits enforced before JSON or model parsing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from glio_proteogen.kernel.strict_json import MAX_JSON_BYTES

MAX_REQUEST_BYTES = MAX_JSON_BYTES

type AsgiApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestBodyTooLargeError(ValueError):
    """Internal control flow raised before an oversized body reaches a parser."""

    def __init__(self) -> None:
        super().__init__("request body exceeds the byte limit")


def is_json_content_type(value: str | None) -> bool:
    """Return whether a request media type is exactly JSON, allowing parameters."""

    return (value or "").partition(";")[0].strip().lower() == "application/json"


class RequestSizeLimitMiddleware:
    """Reject oversized HTTP requests from headers or streamed bytes before parsing.

    Most JSON endpoints accept a 4 MiB request envelope, while replay/verify
    endpoints may legitimately receive the independently declared 8 MiB result
    envelope.  ``result_max_bytes`` widens only paths ending in ``/verify``;
    ordinary request routes retain the request limit and therefore keep their
    existing transport behavior.
    """

    def __init__(
        self,
        app: AsgiApp,
        max_bytes: int = MAX_REQUEST_BYTES,
        result_max_bytes: int | None = None,
        route_limits: Mapping[str, tuple[int, int | None]] | None = None,
    ) -> None:
        self._app = app
        self._max_bytes = max_bytes
        self._result_max_bytes = result_max_bytes
        self._route_limits = tuple(
            sorted((route_limits or {}).items(), key=lambda item: len(item[0]), reverse=True)
        )

    def _limit_for_scope(self, scope: Scope) -> int:
        path = scope.get("path", "")
        for prefix, (request_max_bytes, result_max_bytes) in self._route_limits:
            if path == prefix or path.startswith(f"{prefix}/"):
                # An exact route declaration can distinguish a replay request
                # envelope from that operation's independently bounded result.
                # Family declarations retain the legacy behavior where a
                # nested ``/verify`` consumes the family's result envelope.
                if path == prefix:
                    return request_max_bytes
                if result_max_bytes is not None and path.endswith("/verify"):
                    return result_max_bytes
                return request_max_bytes
        if self._result_max_bytes is not None and path.endswith("/verify"):
            return self._result_max_bytes
        return self._max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        max_bytes = self._limit_for_scope(scope)

        content_length = dict(scope.get("headers", ())).get(b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                await self._respond(scope, send, 400, "invalid content-length")
                return
            if declared_size < 0:
                await self._respond(scope, send, 400, "invalid content-length")
                return
            if declared_size > max_bytes:
                await self._respond(scope, send, 413, "request body exceeds the byte limit")
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    raise RequestBodyTooLargeError
            return message

        try:
            await self._app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await self._respond(scope, send, 413, "request body exceeds the byte limit")

    @staticmethod
    async def _respond(scope: Scope, send: Send, status_code: int, detail: str) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"detail": detail},
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}


def read_bounded(path: Path, max_bytes: int = MAX_REQUEST_BYTES) -> bytes:
    """Read at most max_bytes + 1 from a path-like object and fail before JSON parsing."""

    with path.open("rb") as stream:
        payload = stream.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise RequestBodyTooLargeError
    return payload


__all__ = [
    "MAX_REQUEST_BYTES",
    "RequestBodyTooLargeError",
    "RequestSizeLimitMiddleware",
    "is_json_content_type",
    "read_bounded",
]
