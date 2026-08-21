"""Result-envelope transport ceilings for M24-07 replay."""

from __future__ import annotations

import asyncio
from http import HTTPStatus

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from glio_proteogen.contracts.m24_07 import (
    M2407_MAX_CANONICAL_REQUEST_BYTES,
    M2407_MAX_CANONICAL_RESULT_BYTES,
)
from glio_proteogen.modules.c21_reference_material.m24_07_human_factors_operational_evaluator import (  # noqa: E501
    api as m2407_api,
)


def test_verify_uses_result_ceiling_and_allows_result_sized_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []

    def record_parser(body: bytes, *, max_bytes: int) -> dict[str, object]:
        del body
        seen.append(max_bytes)
        return {}

    monkeypatch.setattr(m2407_api, "_parse_object", record_parser)
    response = TestClient(m2407_api.create_app()).post(
        "/v1/modules/M24-07/verify",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(M2407_MAX_CANONICAL_REQUEST_BYTES + 1),
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert seen == [M2407_MAX_CANONICAL_RESULT_BYTES]


def test_verify_rejects_declared_result_overflow_before_parsing() -> None:
    response = TestClient(m2407_api.create_app()).post(
        "/v1/modules/M24-07/verify",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": str(M2407_MAX_CANONICAL_RESULT_BYTES + 1),
        },
    )

    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_verify_rejects_streamed_result_overflow_without_content_length() -> None:
    body = iter([b"x" * (M2407_MAX_CANONICAL_RESULT_BYTES + 1)])
    response = TestClient(m2407_api.create_app()).post(
        "/v1/modules/M24-07/verify",
        content=body,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert response.json() == {"detail": "request body exceeds the byte limit"}


def test_bounded_reader_rejects_streamed_overflow() -> None:
    class StreamOnlyRequest:
        async def stream(self):
            yield b"x" * (M2407_MAX_CANONICAL_RESULT_BYTES + 1)

    with pytest.raises(HTTPException, match="request exceeds byte limit"):
        asyncio.run(
            m2407_api._read_bounded(StreamOnlyRequest(), max_bytes=M2407_MAX_CANONICAL_RESULT_BYTES)
        )
