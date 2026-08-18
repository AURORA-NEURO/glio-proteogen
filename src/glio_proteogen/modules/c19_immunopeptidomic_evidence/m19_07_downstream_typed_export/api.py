"""Strict FastAPI surface for M19-07 downstream typed export."""

from __future__ import annotations

from typing import Annotated, Final

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m19_07 import (
    M1907_MAX_CANONICAL_REQUEST_BYTES,
    M1907_MAX_CANONICAL_RESULT_BYTES,
    ContractName,
    ExportProteotypeDownstreamContractRequest,
    ProteotypeDownstreamExportResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import strict_json_loads

from .engine import M1907AuthorizationError, M1907ExportError
from .service import M1907Service

_REQUEST_ADAPTER: Final = TypeAdapter(ExportProteotypeDownstreamContractRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeDownstreamExportResult)


async def _request_body(request: Request) -> ExportProteotypeDownstreamContractRequest:
    try:
        decoded = strict_json_loads(
            await request.body(),
            max_bytes=M1907_MAX_CANONICAL_REQUEST_BYTES,
        )
        return _REQUEST_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail="M19-07 request is invalid") from error


async def _result_body(request: Request) -> ProteotypeDownstreamExportResult:
    try:
        decoded = strict_json_loads(
            await request.body(),
            max_bytes=M1907_MAX_CANONICAL_RESULT_BYTES,
        )
        return _RESULT_ADAPTER.validate_json(canonical_json_bytes(decoded), strict=True)
    except (ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail="M19-07 result is invalid") from error


def create_m1907_app(service: M1907Service | None = None) -> FastAPI:
    """Create an isolated API exposing validate, export and replay operations."""

    m1907_service = service or M1907Service()
    app = FastAPI(title="GLIO-PROTEOGEN M19-07", version="0.1.0-provisional")

    @app.exception_handler(M1907AuthorizationError)
    async def authorization_handler(
        _request: Request,
        error: M1907AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(M1907ExportError)
    async def export_handler(
        _request: Request,
        _error: M1907ExportError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M19-07 operation failed safely"})

    @app.get("/v1/contracts/M19-07/{name}/schema", tags=["contracts"])
    def schema(name: ContractName) -> dict[str, object]:
        return contract_json_schema(name)

    @app.post(
        "/v1/modules/M19-07/validate",
        response_model=ExportProteotypeDownstreamContractRequest,
        tags=["M19-07"],
    )
    def validate(
        typed: Annotated[ExportProteotypeDownstreamContractRequest, Depends(_request_body)],
    ) -> ExportProteotypeDownstreamContractRequest:
        return m1907_service.validate_request(typed)

    @app.post(
        "/v1/modules/M19-07/export",
        response_model=ProteotypeDownstreamExportResult,
        tags=["M19-07"],
    )
    def export(
        typed: Annotated[ExportProteotypeDownstreamContractRequest, Depends(_request_body)],
    ) -> ProteotypeDownstreamExportResult:
        return m1907_service.execute(typed)

    @app.post(
        "/v1/modules/M19-07/verify",
        response_model=ProteotypeDownstreamExportResult,
        tags=["M19-07"],
    )
    async def verify(
        result: Annotated[ProteotypeDownstreamExportResult, Depends(_result_body)],
    ) -> ProteotypeDownstreamExportResult:
        return m1907_service.verify(result)

    return app


__all__ = ["create_m1907_app"]
