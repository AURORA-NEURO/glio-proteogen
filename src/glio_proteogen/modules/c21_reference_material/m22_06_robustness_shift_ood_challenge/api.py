"""FastAPI adapter for provisional M22-06 robustness challenges."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m22_06 import (
    M2206_MAX_CANONICAL_REQUEST_BYTES,
    ChallengeProteinRnaDiscordanceRobustnessRequest,
    ProteinRnaDiscordanceRobustnessChallengeResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2206AuthorizationError, M2206EvaluationError
from .service import M2206Service

_REQUEST_ADAPTER = TypeAdapter(ChallengeProteinRnaDiscordanceRobustnessRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinRnaDiscordanceRobustnessChallengeResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "surface",
    "scenario",
    "observation",
    "safe-failure",
    "configuration",
    "finding",
}


def _safe_validation(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M22-06 contract")


def _parse_request(body: bytes) -> ChallengeProteinRnaDiscordanceRobustnessRequest:
    try:
        strict_json_loads(body, max_bytes=M2206_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _safe_validation(error) from error


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        value = strict_json_loads(body)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="request JSON is invalid") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="request JSON must be an object")
    return cast("dict[str, Any]", value)


def create_app(service: M2206Service | None = None) -> FastAPI:
    """Create strict validate/challenge/replay routes with sanitized errors."""

    boundary = service or M2206Service()
    app = FastAPI(title="GLIO-PROTEOGEN M22-06", version="0.1.0-provisional")

    @app.get("/v1/modules/M22-06/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M22-06/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M22-06 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M22-06/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2206AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M22-06/challenge")
    async def challenge(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            result = boundary.execute(payload)
        except (
            ValidationError,
            ValueError,
            M2206AuthorizationError,
            M2206EvaluationError,
        ) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M22-06/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(await request.body())
        candidate = envelope.get("result", envelope)
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            replay = boundary.verify(result)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]
