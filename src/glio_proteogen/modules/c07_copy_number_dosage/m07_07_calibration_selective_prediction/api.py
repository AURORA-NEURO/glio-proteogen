"""FastAPI boundary for the provisional M07-07 operation.

The endpoint parses each body exactly once with the repository's duplicate-key,
non-finite-number, UTF-8, and byte-limit policy.  Error responses intentionally
contain stable type/location/message data only; caller values and raw payloads
never cross the boundary.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_07 import (
    M0707_MAX_CANONICAL_REQUEST_BYTES,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_loads,
)

from .engine import CalibrationAuthorizationError, CalibrationInputError
from .service import M0707Service

router = APIRouter(prefix="/modules/m07-07", tags=["GLIO-PROTEOGEN-M07-07"])


async def _body(request: Request) -> object:
    try:
        raw = await request.body()
        strict_json_loads(
            raw,
            max_bytes=M0707_MAX_CANONICAL_REQUEST_BYTES,
        )
    except StrictJsonError as exc:
        raise HTTPException(
            status_code=400,
            detail={"type": f"json_{exc.code.value}", "loc": ["body"], "msg": str(exc)},
        ) from None
    else:
        return raw


def _safe_validation(exc: ValidationError) -> list[dict[str, object]]:
    return sanitized_validation_errors(exc)


@router.get("/schema")
def export_schema() -> dict[str, dict[str, object]]:
    """Return the complete provisional schema inventory."""

    return cast("dict[str, dict[str, object]]", contract_json_schemas())


@router.post("/validate")
async def validate(request: Request) -> dict[str, object]:
    """Strictly validate a request without executing calibration."""

    try:
        candidate = await _body(request)
        typed = M0707Service.validate_request(candidate)
    except CalibrationAuthorizationError as exc:
        raise HTTPException(
            status_code=403,
            detail={"type": "authorization", "msg": str(exc)},
        ) from None
    except CalibrationInputError as exc:
        raise HTTPException(
            status_code=422,
            detail={"type": "validation", "msg": str(exc)},
        ) from None
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_safe_validation(exc)) from None
    return {
        "module_id": "GLIO-PROTEOGEN-M07-07",
        "contract_version": typed.contract_version,
        "request_digest": canonical_request_digest(typed),
        "valid": True,
    }


@router.post("/calibrate")
async def calibrate(request: Request) -> dict[str, object]:
    """Execute one deterministic selective calibration request."""

    try:
        candidate = await _body(request)
        result = M0707Service().execute(candidate)
    except CalibrationAuthorizationError as exc:
        raise HTTPException(
            status_code=403,
            detail={"type": "authorization", "msg": str(exc)},
        ) from None
    except CalibrationInputError as exc:
        raise HTTPException(
            status_code=422,
            detail={"type": "validation", "msg": str(exc)},
        ) from None
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_safe_validation(exc)) from None
    return result.model_dump(mode="json")


@router.post("/verify")
async def verify(request: Request) -> dict[str, object]:
    """Verify a serialized result's canonical digest and closure."""

    try:
        candidate = await _body(request)
        typed = M0707Service.verify_result(candidate)
    except (ValidationError, ValueError) as exc:
        detail = (
            _safe_validation(exc)
            if isinstance(exc, ValidationError)
            else {"type": "replay", "msg": str(exc)}
        )
        raise HTTPException(status_code=422, detail=detail) from None
    return {"valid": True, "result_digest": typed.result_digest}


__all__ = ["calibrate", "export_schema", "router", "validate", "verify"]
