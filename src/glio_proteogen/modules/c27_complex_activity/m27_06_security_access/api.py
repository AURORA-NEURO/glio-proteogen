"""FastAPI boundary for strict M27-06 security/access evaluation."""

from __future__ import annotations

from typing import cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import RequestSizeLimitMiddleware
from glio_proteogen.contracts.m27_06 import (
    M2706_MAX_CANONICAL_REQUEST_BYTES,
    M2706_MAX_CANONICAL_RESULT_BYTES,
    ComplexActivitySecurityAccessResult,
    EvaluateComplexActivitySecurityAccessRequest,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2706AuthorizationError
from .service import M2706Service

_REQUEST_ADAPTER = TypeAdapter(EvaluateComplexActivitySecurityAccessRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivitySecurityAccessResult)
_CONTRACT_NAMES = frozenset(
    {
        "request",
        "output",
        "access-decision",
        "audit-event",
        "posture",
        "control",
        "finding",
        "safe-failure",
    }
)


def _invalid(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M27-06 contract")


def _require_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError
    return value


def _parse_request(body: bytes) -> EvaluateComplexActivitySecurityAccessRequest:
    try:
        strict_json_loads(body, max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _invalid(error) from error


def create_app(service: M2706Service | None = None) -> FastAPI:  # noqa: C901
    """Create schema, validation, evaluation, and replay routes."""

    boundary = service or M2706Service()
    app = FastAPI(title="GLIO-PROTEOGEN M27-06", version="0.1.0-provisional")
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=M2706_MAX_CANONICAL_REQUEST_BYTES,
        result_max_bytes=M2706_MAX_CANONICAL_RESULT_BYTES,
    )

    def _require_json(request: Request) -> None:
        if (
            request.headers.get("content-type", "").partition(";")[0].strip().lower()
            != "application/json"
        ):
            raise HTTPException(status_code=415, detail="content-type must be application/json")

    @app.get("/v1/modules/M27-06/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M27-06/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M27-06 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M27-06/validate")
    async def validate(request: Request) -> dict[str, object]:
        _require_json(request)
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except (ValidationError, ValueError, M2706AuthorizationError) as error:
            raise _invalid(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M27-06/evaluate")
    async def evaluate(request: Request) -> dict[str, object]:
        _require_json(request)
        payload = _parse_request(await request.body())
        try:
            result = boundary.emit(payload)
        except (ValidationError, ValueError, M2706AuthorizationError) as error:
            raise _invalid(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M27-06/verify")
    async def verify(request: Request) -> dict[str, object]:
        _require_json(request)
        try:
            decoded = strict_json_loads(await request.body())
            envelope = _require_object(decoded)
            candidate = envelope.get("result", envelope)
            supplied_request = envelope.get("request")
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            typed_request = (
                _REQUEST_ADAPTER.validate_json(canonical_json_bytes(supplied_request), strict=True)
                if supplied_request is not None
                else None
            )
            replay = boundary.replay(result, typed_request)
        except (StrictJsonError, ValueError, ValidationError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {
            "verified": replay.result_digest == result.result_digest,
            "result_digest": replay.result_digest,
        }

    return app


__all__ = ["create_app"]
