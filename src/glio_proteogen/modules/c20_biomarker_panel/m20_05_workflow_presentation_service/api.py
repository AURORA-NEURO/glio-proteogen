"""FastAPI adapter for the provisional M20-05 service boundary."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m20_05 import (
    M2005_MAX_CANONICAL_REQUEST_BYTES,
    PresentProteinSubtypeHumanReviewWorkspaceRequest,
    ProteinSubtypeHumanReviewWorkspaceResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2005AuthorizationError
from .service import M2005Service

_REQUEST_ADAPTER = TypeAdapter(PresentProteinSubtypeHumanReviewWorkspaceRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypeHumanReviewWorkspaceResult)
_CONTRACT_NAMES = {
    "request",
    "output",
    "review-item",
    "next-action",
    "workspace",
    "configuration",
    "policy",
    "finding",
}


def _safe_validation(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M20-05 contract")


def _parse_request(body: bytes) -> PresentProteinSubtypeHumanReviewWorkspaceRequest:
    try:
        strict_json_loads(body, max_bytes=M2005_MAX_CANONICAL_REQUEST_BYTES)
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


def create_app(service: M2005Service | None = None) -> FastAPI:
    """Create a strict API app with sanitized validation and replay errors."""

    boundary = service or M2005Service()
    app = FastAPI(title="GLIO-PROTEOGEN M20-05", version="0.1.0-provisional")

    @app.get("/v1/modules/M20-05/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M20-05/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M20-05 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M20-05/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2005AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M20-05/present")
    async def present(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            result = boundary.present(payload)
        except (ValidationError, ValueError, M2005AuthorizationError) as error:
            raise _safe_validation(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M20-05/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(await request.body())
        candidate = envelope.get("result", envelope)
        try:
            result = _RESULT_ADAPTER.validate_json(
                canonical_json_bytes(candidate),
                strict=True,
            )
            replay = boundary.replay(result)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]
