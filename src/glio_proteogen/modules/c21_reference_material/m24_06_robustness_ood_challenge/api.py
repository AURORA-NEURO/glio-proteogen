"""FastAPI adapter for provisional M24-06 robustness challenges."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m24_06 import (
    M2406_MAX_CANONICAL_REQUEST_BYTES,
    M2406_MAX_CANONICAL_RESULT_BYTES,
    BiomarkerPanelRobustnessChallengeResult,
    ChallengeBiomarkerPanelRobustnessRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import AuthorizationError, M2406ReplayError
from .service import M2406Service

_REQUEST_ADAPTER = TypeAdapter(ChallengeBiomarkerPanelRobustnessRequest)
_RESULT_ADAPTER = TypeAdapter(BiomarkerPanelRobustnessChallengeResult)
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


def _parse_request(body: bytes) -> ChallengeBiomarkerPanelRobustnessRequest:
    try:
        strict_json_loads(body, max_bytes=M2406_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise HTTPException(
            status_code=422, detail="request does not satisfy the M24-06 contract"
        ) from error


def _parse_result(body: bytes) -> BiomarkerPanelRobustnessChallengeResult:
    try:
        candidate = strict_json_loads(body, max_bytes=M2406_MAX_CANONICAL_RESULT_BYTES)
        if isinstance(candidate, dict) and "result" in candidate:
            candidate = candidate["result"]
        return _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail="replay envelope is invalid") from error


def create_app(service: M2406Service | None = None) -> FastAPI:
    boundary = service or M2406Service()
    app = FastAPI(title="GLIO-PROTEOGEN M24-06", version="0.1.0-provisional")

    @app.get("/v1/modules/M24-06/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M24-06/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M24-06 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M24-06/validate")
    async def validate(request: Request) -> dict[str, object]:
        try:
            typed = boundary.validate_request(_parse_request(await request.body()))
        except (ValidationError, ValueError, AuthorizationError) as error:
            raise HTTPException(
                status_code=422, detail="request does not satisfy the M24-06 contract"
            ) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M24-06/challenge")
    async def challenge(request: Request) -> dict[str, object]:
        try:
            result = boundary.evaluate(_parse_request(await request.body()))
        except (ValidationError, ValueError, AuthorizationError) as error:
            raise HTTPException(
                status_code=422, detail="request was rejected by the M24-06 service"
            ) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M24-06/verify")
    async def verify(request: Request) -> dict[str, object]:
        try:
            result = _parse_result(await request.body())
            replay = boundary.verify_replay(result)
        except (ValidationError, ValueError, TypeError, M2406ReplayError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]
