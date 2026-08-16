"""FastAPI surface for provisional M06-07 calibration."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_07 import (
    M0607_MAX_CANONICAL_REQUEST_BYTES,
    CalibrateSelectiveProteinAbundanceRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)

from .engine import CalibrationAuthorizationError, CalibrationInputError
from .service import M0607Service

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateSelectiveProteinAbundanceRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "policy",
        "stratum",
        "threshold",
        "estimate",
        "prediction-set",
        "diagnostic",
    }
)


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0607_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(status_code=422, detail=strict_json_error_detail(error)) from error
    return body


def create_app(service: M0607Service | None = None) -> FastAPI:
    """Create an isolated API app with no persistence or model side effects."""

    calibration_service = service or M0607Service()
    app = FastAPI(title="GLIO Proteogen M06-07", version="0.1.0-provisional")

    @app.get("/v1/modules/M06-07/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M06-07 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M06-07/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = calibration_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
        except ValidationError as error:
            raise _validation_error(error) from error
        except CalibrationAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M06-07 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M06-07/calibrate")
    async def calibrate(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = calibration_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
            built = calibration_service.calibrate(typed)
        except ValidationError as error:
            raise _validation_error(error) from error
        except CalibrationAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M06-07 authorization denied") from error
        return JSONResponse(
            content={
                "result": built.result.model_dump(mode="json"),
                "canonical": built.canonical_bytes.decode("utf-8"),
            }
        )

    @app.exception_handler(CalibrationInputError)
    async def calibration_input_error(
        _request: Request,
        _error: CalibrationInputError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M06-07 input rejected"})

    return app


app = create_app()

__all__ = ["app", "create_app"]
