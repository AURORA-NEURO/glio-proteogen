"""FastAPI surface for provisional M07-01 formal-state validation."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_01 import (
    M0701_MAX_CANONICAL_REQUEST_BYTES,
    ValidateCopyNumberStateRequest,
    ValidateCopyNumberStateResult,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import FormalStateAuthorizationError, FormalStateInputError
from .service import M0701Service

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateCopyNumberStateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ValidateCopyNumberStateResult)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "schema",
        "feature-definition",
        "feature-value",
        "invariant",
        "invariant-result",
        "migration",
    }
)


def _validation(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _body(request: Request) -> bytes:
    payload = await request.body()
    try:
        strict_json_loads(payload, max_bytes=M0701_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return payload


# The route handlers intentionally keep one isolated app factory for adapter parity.
# ruff: noqa: C901
def create_app(service: M0701Service | None = None) -> FastAPI:
    """Create an isolated app; no model or persistence side effects occur at import time."""

    formal_state_service = service or M0701Service()
    app = FastAPI(title="GLIO Proteogen M07-01", version="0.1.0-provisional")

    @app.get("/v1/modules/M07-01/schemas/{contract}")
    def schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M07-01 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M07-01/validate")
    async def validate(request: Request) -> JSONResponse:
        payload = await _body(request)
        try:
            typed = formal_state_service.validate_request(
                _REQUEST_ADAPTER.validate_json(payload, strict=True)
            )
        except ValidationError as error:
            raise _validation(error) from error
        except FormalStateAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M07-01 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M07-01/execute")
    async def execute(request: Request) -> JSONResponse:
        payload = await _body(request)
        try:
            typed = _REQUEST_ADAPTER.validate_json(payload, strict=True)
            built = formal_state_service.execute(typed)
        except ValidationError as error:
            raise _validation(error) from error
        except FormalStateAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M07-01 authorization denied") from error
        except FormalStateInputError as error:
            raise HTTPException(status_code=422, detail="M07-01 input rejected") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.post("/v1/modules/M07-01/verify")
    async def verify(request: Request) -> JSONResponse:
        payload = await _body(request)
        try:
            decoded = strict_json_loads(payload, max_bytes=M0701_MAX_CANONICAL_REQUEST_BYTES)
            if not isinstance(decoded, dict) or "result" not in decoded:
                raise ValueError  # noqa: TRY301
            canonical = decoded.get("canonical")
            if not isinstance(canonical, str):
                raise ValueError  # noqa: TRY301
            canonical_bytes = canonical.encode("utf-8")
            result = _RESULT_ADAPTER.validate_json(canonical_bytes, strict=True)
            verified = formal_state_service.verify(result, canonical_bytes)
        except (ValidationError, TypeError, ValueError, FormalStateInputError) as error:
            raise HTTPException(
                status_code=422,
                detail="M07-01 result verification failed",
            ) from error
        return JSONResponse(content={"verified": True, "result": verified.model_dump(mode="json")})

    return app


app = create_app()

__all__ = ["app", "create_app"]
