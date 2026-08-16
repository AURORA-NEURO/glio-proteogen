"""FastAPI interface for strict M08-08 validation and publishing."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_08 import (
    M0808_MAX_CANONICAL_REQUEST_BYTES,
    PublishTranscriptProteinEvidenceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0808AuthorizationError, M0808InputError
from .service import M0808Service

_REQUEST_ADAPTER: Final = TypeAdapter(PublishTranscriptProteinEvidenceRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "bundle",
        "explanation",
        "evidence-item",
        "assumption",
        "diagnostic",
        "reconstruction-step",
        "verification",
    }
)


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0808_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def create_app(service: M0808Service | None = None) -> FastAPI:
    """Create an isolated API with no persistence or external-content traversal."""

    publisher = service or M0808Service()
    app = FastAPI(title="GLIO Proteogen M08-08", version="0.1.0-provisional")

    @app.get("/v1/modules/M08-08/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M08-08 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M08-08/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = publisher.validate_request(_REQUEST_ADAPTER.validate_json(body, strict=True))
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0808AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M08-08 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M08-08/publish")
    async def publish(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = _REQUEST_ADAPTER.validate_json(body, strict=True)
            built = publisher.publish(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0808AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M08-08 authorization denied") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.exception_handler(M0808InputError)
    async def input_error(_request: Request, _error: M0808InputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M08-08 input rejected"})

    return app


app = create_app()

__all__ = ["app", "create_app"]
