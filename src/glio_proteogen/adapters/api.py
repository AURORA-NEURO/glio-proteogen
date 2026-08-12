"""FastAPI surface for the active M01-01 vertical slice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Final

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES, RequestSizeLimitMiddleware
from glio_proteogen.contracts.m01_01.schema import ContractName, contract_json_schema
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceProfile,
    EvaluateMetadataRequest,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    assert_strict_json,
    sanitized_validation_errors,
    strict_json_error_detail,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.event_store import (
    ChainVerification,
    M0101EventStore,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.service import (
    ChainIntegrityError,
    ConsentAuthorizationError,
    IdempotencyConflictError,
    InvalidProtocolLookupError,
    M0101Service,
    PayloadTooLargeError,
    ProtocolNotFoundError,
    ProtocolSchemaValidationError,
    ProtocolVersionConflictError,
    UpstreamControlAuthorizationError,
)

_REGISTER_ADAPTER: Final = TypeAdapter(RegisterProtocolRequest)
_EVALUATE_ADAPTER: Final = TypeAdapter(EvaluateMetadataRequest)


def _contract_schema(name: ContractName) -> dict[str, object]:
    return contract_json_schema(name)


def _request_body(name: ContractName) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": contract_json_schema(name)}},
        }
    }


async def _strict_json_body[ModelT](
    request: Request,
    adapter: TypeAdapter[ModelT],
) -> ModelT:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="content-type must be application/json")
    try:
        body = await request.body()
        assert_strict_json(body, max_bytes=MAX_REQUEST_BYTES)
        return adapter.validate_json(body, strict=True)
    except StrictJsonError as error:
        details = [strict_json_error_detail(error, location_prefix=("body",))]
        raise RequestValidationError(details) from error
    except ValidationError as error:
        details = sanitized_validation_errors(error, location_prefix=("body",))
        raise RequestValidationError(details) from error


async def _register_body(request: Request) -> RegisterProtocolRequest:
    return await _strict_json_body(request, _REGISTER_ADAPTER)


async def _evaluate_body(request: Request) -> EvaluateMetadataRequest:
    return await _strict_json_body(request, _EVALUATE_ADAPTER)


def create_app(database_path: Path) -> FastAPI:
    """Create an isolated API instance backed by one append-only event database."""

    store = M0101EventStore(database_path)
    service = M0101Service(store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        service.close()

    app = FastAPI(
        title="GLIO-PROTEOGEN",
        version="0.1.0",
        description="Research-use-only protocol specification and metadata conformance.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)

    @app.exception_handler(ProtocolNotFoundError)
    def not_found_handler(_request: Request, error: ProtocolNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(ProtocolVersionConflictError)
    @app.exception_handler(IdempotencyConflictError)
    def conflict_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(PayloadTooLargeError)
    def payload_handler(_request: Request, error: PayloadTooLargeError) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(error)})

    @app.exception_handler(ConsentAuthorizationError)
    @app.exception_handler(UpstreamControlAuthorizationError)
    def authorization_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(InvalidProtocolLookupError)
    def lookup_input_handler(
        _request: Request,
        error: InvalidProtocolLookupError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ProtocolSchemaValidationError)
    def schema_handler(
        _request: Request,
        error: ProtocolSchemaValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": str(error),
                "issues": [issue.model_dump(mode="json") for issue in error.issues],
            },
        )

    @app.exception_handler(ChainIntegrityError)
    def integrity_handler(_request: Request, error: ChainIntegrityError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/healthz", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "alive", "module": "GLIO-PROTEOGEN-M01-01"}

    @app.get("/readyz", response_model=ChainVerification, tags=["operations"])
    def readiness() -> ChainVerification:
        return _require_valid_chain(service.verify_event_chain())

    @app.get("/v1/contracts/M01-01/{name}/schema", tags=["contracts"])
    def contract_schema(name: ContractName) -> dict[str, object]:
        return _contract_schema(name)

    @app.post(
        "/v1/modules/M01-01/protocols",
        response_model=ProtocolSchemaReceipt,
        tags=["M01-01"],
        openapi_extra=_request_body("register-request"),
    )
    def register_protocol(
        request: Annotated[RegisterProtocolRequest, Depends(_register_body)],
    ) -> ProtocolSchemaReceipt:
        return service.register(request)

    @app.post(
        "/v1/modules/M01-01/conformance",
        response_model=ConformanceProfile,
        tags=["M01-01"],
        openapi_extra=_request_body("evaluate-request"),
    )
    def evaluate_metadata(
        request: Annotated[EvaluateMetadataRequest, Depends(_evaluate_body)],
    ) -> ConformanceProfile:
        return service.evaluate(request)

    @app.get(
        "/v1/modules/M01-01/protocols/{schema_id}/{version}",
        response_model=ProtocolSchemaReceipt,
        tags=["M01-01"],
    )
    def get_protocol(
        schema_id: str,
        version: str,
    ) -> ProtocolSchemaReceipt:
        return service.get_protocol(schema_id, version)

    @app.get(
        "/v1/modules/M01-01/events/verify",
        response_model=ChainVerification,
        tags=["operations"],
    )
    def verify_events() -> ChainVerification:
        return _require_valid_chain(service.verify_event_chain())

    return app


def _require_valid_chain(verification: ChainVerification) -> ChainVerification:
    if not verification.valid:
        raise ChainIntegrityError(verification.reason or "event chain verification failed")
    return verification
