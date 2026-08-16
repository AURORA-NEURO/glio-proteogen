"""FastAPI interface for strict M09-01 formal-state validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_01 import (
    M0901_MAX_CANONICAL_REQUEST_BYTES,
    M0901_MAX_CANONICAL_RESULT_BYTES,
    ValidateComplexActivityStateRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import M0901AuthorizationError, M0901FormalStateEngine, M0901InputError
from .service import M0901Service

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateComplexActivityStateRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "feature-definition",
        "feature-value",
        "invariant",
        "invariant-result",
        "constraint",
        "compatibility",
        "schema",
        "migration",
    }
)


async def _strict_body(request: Request, *, max_bytes: int) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=max_bytes)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


def create_app(service: M0901Service | None = None) -> FastAPI:  # noqa: C901
    """Create an isolated API with no persistence or content traversal."""

    formal_state_service = service or M0901Service()
    app = FastAPI(title="GLIO Proteogen M09-01", version="0.1.0-provisional")

    @app.get("/v1/modules/M09-01/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M09-01 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M09-01/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request, max_bytes=M0901_MAX_CANONICAL_REQUEST_BYTES)
        try:
            typed = _REQUEST_ADAPTER.validate_json(body, strict=True)
            formal_state_service.validate_request(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0901AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-01 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M09-01/execute")
    async def execute(request: Request) -> JSONResponse:
        body = await _strict_body(request, max_bytes=M0901_MAX_CANONICAL_REQUEST_BYTES)
        try:
            typed = _REQUEST_ADAPTER.validate_json(body, strict=True)
            formal_state_service.validate_request(typed)
            built = formal_state_service._execute_validated(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except M0901AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M09-01 authorization denied") from error
        except M0901InputError as error:
            raise HTTPException(status_code=422, detail="M09-01 input rejected") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.post("/v1/modules/M09-01/verify")
    async def verify(request: Request) -> JSONResponse:
        body = await _strict_body(request, max_bytes=M0901_MAX_CANONICAL_RESULT_BYTES)
        decoded = strict_json_loads(body, max_bytes=M0901_MAX_CANONICAL_RESULT_BYTES)
        if not isinstance(decoded, Mapping):
            raise HTTPException(status_code=422, detail="M09-01 verification envelope is invalid")
        result = decoded.get("result")
        canonical = decoded.get("canonical")
        if not isinstance(result, Mapping) or not isinstance(canonical, str):
            raise HTTPException(status_code=422, detail="M09-01 verification envelope is invalid")
        outcome = M0901FormalStateEngine.verify(result, canonical)
        status = 200 if outcome.verified else 422
        return JSONResponse(
            status_code=status,
            content={"verified": outcome.verified, "reason": outcome.reason},
        )

    return app


app = create_app()

__all__ = ["app", "create_app"]
