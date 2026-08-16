"""FastAPI boundary for provisional M08-06 uncertainty decomposition."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_06 import (
    M0806_MAX_CANONICAL_REQUEST_BYTES,
    DecomposeTranscriptProteinUncertaintyRequest,
    TranscriptProteinUncertaintyDecompositionResult,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0806AuthorizationError, M0806ReplayVerificationError
from .service import M0806Service

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeTranscriptProteinUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(TranscriptProteinUncertaintyDecompositionResult)
_CONTRACT_NAMES: Final = frozenset(
    {"request", "output", "component", "decomposition", "sensitivity-envelope", "policy", "finding"}
)


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0806_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def create_app(service: M0806Service | None = None) -> FastAPI:  # noqa: C901
    """Create an isolated strict JSON app with no persistence side effects."""

    uncertainty_service = service or M0806Service()
    app = FastAPI(title="GLIO Proteogen M08-06", version="0.1.0-provisional")

    @app.get("/v1/modules/M08-06/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M08-06 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M08-06/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = uncertainty_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0806AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M08-06 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M08-06/decompose")
    async def decompose(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = uncertainty_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
            result = uncertainty_service.execute(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0806AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M08-06 authorization denied") from error
        return JSONResponse(
            content={
                "result": result.model_dump(mode="json"),
                "canonical": canonical_json_bytes(result.model_dump(mode="json")).decode("utf-8"),
            }
        )

    @app.post("/v1/modules/M08-06/verify")
    async def verify(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            result = _RESULT_ADAPTER.validate_json(body, strict=True)
            verified = uncertainty_service.verify(result, replay=True)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0806ReplayVerificationError as error:
            raise HTTPException(
                status_code=409, detail="M08-06 replay verification failed"
            ) from error
        return JSONResponse(content={"verified": True, "result": verified.model_dump(mode="json")})

    return app


app = create_app()

__all__ = ["app", "create_app"]
