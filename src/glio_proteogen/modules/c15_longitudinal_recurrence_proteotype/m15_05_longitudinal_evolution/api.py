"""FastAPI boundary for the provisional M15-05 longitudinal replay."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m15_05 import (
    M1505_MAX_CANONICAL_REQUEST_BYTES,
    ModelComplexActivityLongitudinalEvolutionRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

from .engine import M1505AuthorizationError
from .service import M1505Service

_REQUEST_ADAPTER = TypeAdapter(ModelComplexActivityLongitudinalEvolutionRequest)
_CONTRACT_NAMES = {
    "request",
    "output",
    "observation",
    "trajectory-state",
    "change-point",
    "configuration",
    "policy",
    "diagnostic",
}


def _parse_request(body: bytes) -> ModelComplexActivityLongitudinalEvolutionRequest:
    try:
        strict_json_loads(body, max_bytes=M1505_MAX_CANONICAL_REQUEST_BYTES)
        return _REQUEST_ADAPTER.validate_json(body, strict=True)
    except (StrictJsonError, ValueError, ValidationError) as error:
        raise HTTPException(status_code=422, detail="M15-05 request is invalid") from error


def create_app(service: M1505Service | None = None) -> FastAPI:
    """Create strict schema and longitudinal-evolution routes."""

    boundary = service or M1505Service()
    app = FastAPI(title="GLIO-PROTEOGEN M15-05", version="0.1.0-provisional")

    @app.get("/v1/contracts/M15-05/{name}/schema")
    async def schema(name: str) -> dict[str, object]:
        if name not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M15-05 contract")
        return contract_json_schema(name)  # type: ignore[arg-type]

    @app.post("/v1/modules/M15-05/longitudinal-evolution")
    async def longitudinal_evolution(request: Request) -> dict[str, Any]:
        if request.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
            raise HTTPException(status_code=415, detail="application/json is required")
        payload = _parse_request(await request.body())
        try:
            result = boundary.execute(payload)
        except M1505AuthorizationError as error:
            raise HTTPException(status_code=403, detail="M15-05 authorization denied") from error
        except (ValidationError, ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail="M15-05 request is invalid") from error
        return result.model_dump(mode="json")

    return app


__all__ = ["create_app"]
