"""FastAPI surface for the active pre-analytic module slices."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Final

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES, RequestSizeLimitMiddleware
from glio_proteogen.contracts.m01_01.schema import (
    ContractName as M0101ContractName,
)
from glio_proteogen.contracts.m01_01.schema import (
    contract_json_schema as m0101_contract_json_schema,
)
from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceProfile,
    EvaluateMetadataRequest,
    ProtocolSchemaReceipt,
    RegisterProtocolRequest,
)
from glio_proteogen.contracts.m01_02.schema import (
    ContractName as M0102ContractName,
)
from glio_proteogen.contracts.m01_02.schema import (
    contract_json_schema as m0102_contract_json_schema,
)
from glio_proteogen.contracts.m01_02.v1 import (
    IdentityLineageResolution,
    ReconcileIdentityLineageRequest,
)
from glio_proteogen.contracts.m01_03.schema import (
    ContractName as M0103ContractName,
)
from glio_proteogen.contracts.m01_03.schema import (
    contract_json_schema as m0103_contract_json_schema,
)
from glio_proteogen.contracts.m01_03.v1 import ValidatedRawInputDescriptor
from glio_proteogen.contracts.m01_04.schema import (
    ContractName as M0104ContractName,
)
from glio_proteogen.contracts.m01_04.schema import (
    contract_json_schema as m0104_contract_json_schema,
)
from glio_proteogen.contracts.m01_04.v1 import (
    ComputeQualityMetricsRequest,
    QualityProfile,
)
from glio_proteogen.kernel.models import Identifier, Sha256Digest
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
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
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainIntegrityError as M0102ChainIntegrityError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    ChainVerification as M0102ChainVerification,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    EventStoreError as M0102EventStoreError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    IdempotencyConflictError as M0102IdempotencyConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    M0102EventStore,
    ResolutionNotFoundError,
    ResolutionSupersessionConflictError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.event_store import (
    PayloadTooLargeError as M0102PayloadTooLargeError,
)
from glio_proteogen.modules.c01_preanalytic.m01_02_identity_lineage.service import (
    IdentityLineageAuthorizationError,
    M0102Service,
    preflight_identity_authorization,
)
from glio_proteogen.modules.c01_preanalytic.m01_03_raw_ingestion.parser import (
    IngestionLimits,
    parse_raw_input,
)
from glio_proteogen.modules.c01_preanalytic.m01_04_quality_metrics.service import (
    M0104Service,
)

_REGISTER_ADAPTER: Final = TypeAdapter(RegisterProtocolRequest)
_EVALUATE_ADAPTER: Final = TypeAdapter(EvaluateMetadataRequest)
_RECONCILE_ADAPTER: Final = TypeAdapter(ReconcileIdentityLineageRequest)
_QUALITY_ADAPTER: Final = TypeAdapter(ComputeQualityMetricsRequest)
_RESOLUTION_DIGEST_ADAPTER: Final = TypeAdapter(Sha256Digest)
_IDENTIFIER_ADAPTER: Final = TypeAdapter(Identifier)
_MAX_ADVISORY_FILENAME_BYTES: Final = 512
_MAX_CHECKSUM_TEXT_LENGTH: Final = 80
_RAW_API_LIMITS: Final = IngestionLimits(
    max_source_bytes=MAX_REQUEST_BYTES,
    max_decoded_bytes=MAX_REQUEST_BYTES * 4,
)


def _contract_schema(name: M0101ContractName) -> dict[str, object]:
    """Retain the original M01-01 schema helper used by the CLI."""

    return m0101_contract_json_schema(name)


def _identity_contract_schema(name: M0102ContractName) -> dict[str, object]:
    return m0102_contract_json_schema(name)


def _raw_contract_schema(name: M0103ContractName) -> dict[str, object]:
    return m0103_contract_json_schema(name)


def _quality_contract_schema(name: M0104ContractName) -> dict[str, object]:
    return m0104_contract_json_schema(name)


def _request_body(name: M0101ContractName) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": m0101_contract_json_schema(name)}},
        }
    }


def _identity_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": m0102_contract_json_schema("request")}
            },
        }
    }


def _quality_request_body() -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": m0104_contract_json_schema("request")}
            },
        }
    }


async def _strict_json_body[ModelT](
    request: Request,
    adapter: TypeAdapter[ModelT],
    preflight: Callable[[object], None] | None = None,
) -> ModelT:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="content-type must be application/json")
    try:
        body = await request.body()
        decoded = strict_json_loads(body, max_bytes=MAX_REQUEST_BYTES)
        if preflight is not None:
            preflight(decoded)
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


async def _reconcile_body(request: Request) -> ReconcileIdentityLineageRequest:
    return await _strict_json_body(
        request,
        _RECONCILE_ADAPTER,
        preflight_identity_authorization,
    )


async def _quality_body(request: Request) -> ComputeQualityMetricsRequest:
    return await _strict_json_body(request, _QUALITY_ADAPTER)


def create_app(database_path: Path) -> FastAPI:  # noqa: PLR0915 - central route composition.
    """Create an isolated API instance backed by one append-only event database."""

    store = M0101EventStore(database_path)
    service = M0101Service(store)
    identity_store = M0102EventStore(database_path)
    identity_service = M0102Service(identity_store)
    quality_service = M0104Service()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        identity_service.close()
        service.close()

    app = FastAPI(
        title="GLIO-PROTEOGEN",
        version="0.1.0",
        description="Research-use-only preanalytic contracts and bounded evidence processing.",
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

    @app.exception_handler(ResolutionNotFoundError)
    def identity_not_found_handler(
        _request: Request,
        error: ResolutionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(M0102IdempotencyConflictError)
    @app.exception_handler(ResolutionSupersessionConflictError)
    def identity_conflict_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(M0102PayloadTooLargeError)
    def identity_payload_handler(
        _request: Request,
        error: M0102PayloadTooLargeError,
    ) -> JSONResponse:
        return JSONResponse(status_code=413, content={"detail": str(error)})

    @app.exception_handler(IdentityLineageAuthorizationError)
    def identity_authorization_handler(
        _request: Request,
        error: IdentityLineageAuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})

    @app.exception_handler(M0102ChainIntegrityError)
    @app.exception_handler(M0102EventStoreError)
    def identity_integrity_handler(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(error)})

    @app.get("/healthz", tags=["operations"])
    def health() -> dict[str, str]:
        return {"status": "alive", "module": "GLIO-PROTEOGEN-M01-01"}

    @app.get("/readyz", response_model=ChainVerification, tags=["operations"])
    def readiness() -> ChainVerification:
        _require_valid_identity_chain(identity_service.verify_event_chain())
        return _require_valid_chain(service.verify_event_chain())

    @app.get("/v1/contracts/M01-01/{name}/schema", tags=["contracts"])
    def contract_schema(name: M0101ContractName) -> dict[str, object]:
        return _contract_schema(name)

    @app.get("/v1/contracts/M01-02/{name}/schema", tags=["contracts"])
    def identity_contract_schema(name: M0102ContractName) -> dict[str, object]:
        return _identity_contract_schema(name)

    @app.get("/v1/contracts/M01-03/{name}/schema", tags=["contracts"])
    def raw_contract_schema(name: M0103ContractName) -> dict[str, object]:
        return _raw_contract_schema(name)

    @app.get("/v1/contracts/M01-04/{name}/schema", tags=["contracts"])
    def quality_contract_schema(name: M0104ContractName) -> dict[str, object]:
        return _quality_contract_schema(name)

    @app.post(
        "/v1/modules/M01-04/quality",
        response_model=QualityProfile,
        tags=["M01-04"],
        openapi_extra=_quality_request_body(),
    )
    def compute_quality_metrics(
        request: Annotated[ComputeQualityMetricsRequest, Depends(_quality_body)],
    ) -> QualityProfile:
        return quality_service.execute(request)

    @app.post(
        "/v1/modules/M01-03/inspect",
        response_model=ValidatedRawInputDescriptor,
        tags=["M01-03"],
    )
    async def inspect_raw_input(
        request: Request,
        source_id: str,
        filename: str | None = None,
        expected_sha256: str | None = None,
    ) -> ValidatedRawInputDescriptor:
        """Inspect one bounded binary body without retaining or interpreting its records."""

        media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
        if media_type != "application/octet-stream":
            raise HTTPException(
                status_code=415,
                detail="content-type must be application/octet-stream",
            )
        if (
            filename is not None
            and len(filename.encode("utf-8")) > _MAX_ADVISORY_FILENAME_BYTES
        ):
            raise HTTPException(status_code=422, detail="filename is too long")
        if expected_sha256 is not None and len(expected_sha256) > _MAX_CHECKSUM_TEXT_LENGTH:
            raise HTTPException(status_code=422, detail="checksum is too long")
        try:
            validated_source_id = _IDENTIFIER_ADAPTER.validate_python(source_id, strict=True)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="source identifier is invalid") from error
        return parse_raw_input(
            await request.body(),
            source_id=validated_source_id,
            filename=filename,
            expected_sha256=expected_sha256,
            limits=_RAW_API_LIMITS,
        )

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

    @app.post(
        "/v1/modules/M01-02/reconcile",
        response_model=IdentityLineageResolution,
        tags=["M01-02"],
        openapi_extra=_identity_request_body(),
    )
    def reconcile_identity_lineage(
        request: Annotated[ReconcileIdentityLineageRequest, Depends(_reconcile_body)],
    ) -> IdentityLineageResolution:
        return identity_service.execute(request)

    @app.get(
        "/v1/modules/M01-02/resolutions/{resolution_digest}",
        response_model=IdentityLineageResolution,
        tags=["M01-02"],
    )
    def get_identity_resolution(
        resolution_digest: str,
    ) -> IdentityLineageResolution:
        try:
            validated_digest = _RESOLUTION_DIGEST_ADAPTER.validate_python(
                resolution_digest,
                strict=True,
            )
        except ValidationError as error:
            raise HTTPException(
                status_code=422,
                detail="resolution digest is invalid",
            ) from error
        return identity_service.get_resolution(validated_digest)

    @app.get(
        "/v1/modules/M01-02/events/verify",
        response_model=M0102ChainVerification,
        tags=["operations"],
    )
    def verify_identity_events() -> M0102ChainVerification:
        return _require_valid_identity_chain(identity_service.verify_event_chain())

    return app


def _require_valid_chain(verification: ChainVerification) -> ChainVerification:
    if not verification.valid:
        raise ChainIntegrityError(verification.reason or "event chain verification failed")
    return verification


def _require_valid_identity_chain(
    verification: M0102ChainVerification,
) -> M0102ChainVerification:
    if not verification.valid:
        raise M0102ChainIntegrityError(
            verification.reason or "identity event chain verification failed"
        )
    return verification
