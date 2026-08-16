"""FastAPI adapter for the provisional M25-06 robustness boundary."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m25_06 import (
    M2506_MAX_CANONICAL_REQUEST_BYTES,
    ChallengeProteotypeRobustnessRequest,
    ProteotypeRobustnessChallengeResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2506AuthorizationError
from .service import M2506Service

_REQUEST_ADAPTER = TypeAdapter(ChallengeProteotypeRobustnessRequest)
_RESULT_ADAPTER = TypeAdapter(ProteotypeRobustnessChallengeResult)
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


def _safe_validation(_error: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail="request does not satisfy the M25-06 contract")


def _parse_request(body: bytes) -> ChallengeProteotypeRobustnessRequest:
    try:
        strict_json_loads(body, max_bytes=M2506_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _safe_validation(error) from error


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        value = strict_json_loads(body, max_bytes=M2506_MAX_CANONICAL_REQUEST_BYTES)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="request JSON is invalid") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="request JSON must be an object")
    return cast("dict[str, Any]", value)


def create_app(service: M2506Service | None = None) -> FastAPI:
    """Create strict validate/challenge/replay routes with sanitized errors."""

    boundary = service or M2506Service()
    api = FastAPI(title="GLIO-PROTEOGEN M25-06", version="0.1.0-provisional")

    @api.get("/v1/modules/M25-06/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @api.get("/v1/modules/M25-06/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M25-06 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @api.post("/v1/modules/M25-06/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2506AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @api.post("/v1/modules/M25-06/challenge")
    async def challenge(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            result = boundary.execute(payload)
        except (ValidationError, ValueError, M2506AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @api.post("/v1/modules/M25-06/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(await request.body())
        candidate = envelope.get("result", envelope)
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            replay = boundary.verify_replay(result)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return api


app = create_app()

__all__ = ["app", "create_app"]
