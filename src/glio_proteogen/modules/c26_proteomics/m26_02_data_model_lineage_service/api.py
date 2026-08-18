"""FastAPI adapter for the M26-02 strict request/result boundary."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m26_02 import (
    BuildProteinSubtypeLineageRequest,
    ProteinSubtypeLineageResult,
    canonical_request_digest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    MAX_JSON_BYTES,
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.engine import (
    LineageAuthorizationError,
)
from glio_proteogen.modules.c26_proteomics.m26_02_data_model_lineage_service.service import (
    M2602LineageService,
)

_REQUEST_ADAPTER: Final[TypeAdapter[BuildProteinSubtypeLineageRequest]] = TypeAdapter(
    BuildProteinSubtypeLineageRequest
)
_RESULT_ADAPTER: Final[TypeAdapter[ProteinSubtypeLineageResult]] = TypeAdapter(
    ProteinSubtypeLineageResult
)


def _validated_payload(
    raw: bytes, service: M2602LineageService
) -> BuildProteinSubtypeLineageRequest:
    try:
        strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
        validated = _REQUEST_ADAPTER.validate_json(raw, strict=True)
        return service.validate_request(validated)
    except StrictJsonError as error:
        raise HTTPException(status_code=400, detail=strict_json_error_detail(error)) from error
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=sanitized_validation_errors(error)) from error
    except LineageAuthorizationError as error:
        raise HTTPException(
            status_code=403, detail={"type": "authorization", "msg": str(error)}
        ) from error


def create_m2602_app(service: M2602LineageService | None = None) -> FastAPI:
    """Create an isolated FastAPI application for tests and bounded deployments."""

    active_service = service or M2602LineageService()
    app = FastAPI(title="GLIO-PROTEOGEN M26-02", version="0.1.0-provisional")

    @app.get("/m26-02/schema/{name}")
    async def export_schema(name: str) -> JSONResponse:
        try:
            schema = contract_json_schema(name)  # type: ignore[arg-type]
        except KeyError as error:
            raise HTTPException(status_code=404, detail="unknown M26-02 schema") from error
        return JSONResponse(schema)

    @app.post("/m26-02/validate")
    async def validate(request: Request) -> JSONResponse:
        raw = await request.body()
        validated = _validated_payload(raw, active_service)
        return JSONResponse(
            {"valid": True, "requestDigest": canonical_request_digest(validated)}
        )

    @app.post("/m26-02/construct")
    async def construct(request: Request) -> JSONResponse:
        raw = await request.body()
        validated = _validated_payload(raw, active_service)
        result = active_service.execute(validated)
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/m26-02/verify")
    async def verify(request: Request) -> JSONResponse:
        raw = await request.body()
        try:
            decoded = strict_json_loads(raw, max_bytes=MAX_JSON_BYTES)
            del decoded
            result = _RESULT_ADAPTER.validate_json(raw, strict=True)
            verified = active_service.verify(result)
        except StrictJsonError as error:
            raise HTTPException(status_code=400, detail=strict_json_error_detail(error)) from error
        except ValidationError as error:
            raise HTTPException(
                status_code=422, detail=sanitized_validation_errors(error)
            ) from error
        return JSONResponse(
            {"verified": True, "resultDigest": verified.result_digest},
        )

    return app


__all__ = ["create_m2602_app"]
