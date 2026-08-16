"""FastAPI boundary for strict M26-06 security evaluation and replay."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_06 import (
    M2606_MAX_CANONICAL_REQUEST_BYTES,
    M2606_MAX_CANONICAL_RESULT_BYTES,
    EvaluateProteomicsSecurityAccessRequest,
    ProteomicsSecurityAccessResult,
    contract_json_schema,
    contract_json_schemas,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M2606AuthorizationError
from .service import M2606SecurityService

_REQUEST_ADAPTER: TypeAdapter[EvaluateProteomicsSecurityAccessRequest] = TypeAdapter(
    EvaluateProteomicsSecurityAccessRequest
)
_RESULT_ADAPTER: TypeAdapter[ProteomicsSecurityAccessResult] = TypeAdapter(
    ProteomicsSecurityAccessResult
)
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


def _invalid_request(error: Exception) -> HTTPException:
    del error
    return HTTPException(status_code=422, detail="request does not satisfy the M26-06 contract")


def _parse_request(body: bytes) -> EvaluateProteomicsSecurityAccessRequest:
    try:
        decoded = strict_json_loads(body, max_bytes=M2606_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise _invalid_request(error) from error


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        decoded = strict_json_loads(body, max_bytes=M2606_MAX_CANONICAL_RESULT_BYTES)
    except (StrictJsonError, ValueError) as error:
        raise HTTPException(status_code=422, detail="result JSON is invalid") from error
    if not isinstance(decoded, dict):
        raise HTTPException(status_code=422, detail="result JSON must be an object")
    return cast("dict[str, Any]", decoded)


def create_m2606_app(service: M2606SecurityService | None = None) -> FastAPI:  # noqa: C901
    """Create schema, validation, evaluation, and replay routes."""

    boundary = service or M2606SecurityService()
    app = FastAPI(title="GLIO-PROTEOGEN M26-06", version="0.1.0-provisional")

    @app.get("/v1/modules/M26-06/schemas")
    async def schemas() -> dict[str, dict[str, object]]:
        return cast("dict[str, dict[str, object]]", contract_json_schemas())

    @app.get("/v1/modules/M26-06/schemas/{name}")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M26-06 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M26-06/validate")
    async def validate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            typed = boundary.validate_request(payload)
        except M2606AuthorizationError as error:
            raise HTTPException(
                status_code=403, detail="M26-06 authorization controls rejected request"
            ) from error
        except (ValidationError, ValueError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", typed.model_dump(mode="json"))

    @app.post("/v1/modules/M26-06/evaluate")
    async def evaluate(request: Request) -> dict[str, object]:
        payload = _parse_request(await request.body())
        try:
            result = boundary.execute(payload)
        except M2606AuthorizationError as error:
            raise HTTPException(
                status_code=403, detail="M26-06 authorization controls rejected request"
            ) from error
        except (ValidationError, ValueError) as error:
            raise _invalid_request(error) from error
        return cast("dict[str, object]", result.model_dump(mode="json"))

    @app.post("/v1/modules/M26-06/verify")
    async def verify(request: Request) -> dict[str, object]:
        envelope = _parse_object(await request.body())
        candidate = envelope.get("result", envelope)
        try:
            result = _RESULT_ADAPTER.validate_json(canonical_json_bytes(candidate), strict=True)
            replay = boundary.verify(result)
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="replay envelope is invalid") from error
        return {"verified": True, "result_digest": replay.result_digest}

    return app


create_app = create_m2606_app

__all__ = ["create_app", "create_m2606_app"]
