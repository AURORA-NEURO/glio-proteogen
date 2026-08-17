"""FastAPI surface for the M05-08 release-packaging boundary."""

# The adapter deliberately translates internal validation failures into sanitized
# HTTP diagnostics; the exception messages are part of that boundary.
# ruff: noqa: TRY003, TRY004

from __future__ import annotations

import base64
import binascii
from typing import Final

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m05_08 import (
    M0508_MAX_CANONICAL_REQUEST_BYTES,
    BuildPtmLocalizationReleaseRequest,
    contract_json_schema,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.strict_json import (
    StrictJsonError,
    sanitized_validation_errors,
    strict_json_error_detail,
    strict_json_loads,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.engine import (
    PtmLocalizationReleaseAuthorizationError,
    PtmLocalizationReleaseInputError,
)
from glio_proteogen.modules.c05_ptm_localization.m05_08_release_packaging.service import (
    M0508Service,
)

_REQUEST_ADAPTER: Final = TypeAdapter(BuildPtmLocalizationReleaseRequest)
_CONTRACT_NAMES: Final = frozenset(
    {
        "request",
        "output",
        "policy",
        "artifact",
        "manifest",
        "signature",
        "quarantine",
        "verification",
        "transformation",
        "quality-decision",
    }
)


def _validation_error(error: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail=sanitized_validation_errors(error))


async def _strict_body(request: Request) -> bytes:
    body = await request.body()
    try:
        strict_json_loads(body, max_bytes=M0508_MAX_CANONICAL_REQUEST_BYTES)
    except StrictJsonError as error:
        raise HTTPException(
            status_code=422,
            detail=strict_json_error_detail(error),
        ) from error
    return body


def _decode_artifacts(value: object) -> dict[str, bytes]:
    if not isinstance(value, dict):
        raise ValueError("artifacts must be an object")
    decoded: dict[str, bytes] = {}
    for path, encoded in value.items():
        if not isinstance(path, str) or not isinstance(encoded, str):
            raise ValueError("artifact paths and values must be strings")
        try:
            decoded[path] = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("artifact values must be valid base64") from error
    return decoded


def _decode_build_envelope(
    body: bytes,
) -> tuple[BuildPtmLocalizationReleaseRequest, dict[str, bytes]]:
    document = strict_json_loads(body, max_bytes=M0508_MAX_CANONICAL_REQUEST_BYTES)
    if not isinstance(document, dict):
        raise ValueError("build body must be an object")
    request_document = document.get("request")
    if not isinstance(request_document, dict):
        raise ValueError("build body requires a request object")
    request = _REQUEST_ADAPTER.validate_json(canonical_json_bytes(request_document), strict=True)
    return request, _decode_artifacts(document.get("artifacts"))


def create_app(service: M0508Service | None = None) -> FastAPI:
    """Create an isolated API app; no persistence or signing keys are configured."""

    release_service = service or M0508Service()
    app = FastAPI(title="GLIO Proteogen M05-08", version="0.1.0-provisional")

    @app.get("/v1/modules/M05-08/schemas/{contract}")
    def export_schema(contract: str) -> dict[str, object]:
        if contract not in _CONTRACT_NAMES:
            raise HTTPException(status_code=404, detail="unknown M05-08 contract")
        return contract_json_schema(contract)  # type: ignore[arg-type]

    @app.post("/v1/modules/M05-08/validate")
    async def validate_request(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed = release_service.validate_request(
                _REQUEST_ADAPTER.validate_json(body, strict=True)
            )
        except ValidationError as error:
            raise _validation_error(error) from error
        except PtmLocalizationReleaseAuthorizationError as error:
            raise HTTPException(status_code=403, detail="M05-08 authorization denied") from error
        return JSONResponse(content=typed.model_dump(mode="json"))

    @app.post("/v1/modules/M05-08/build")
    async def build_release(request: Request) -> JSONResponse:
        body = await _strict_body(request)
        try:
            typed, artifacts = _decode_build_envelope(body)
            built = release_service.build(typed, artifacts)
        except (StrictJsonError, ValidationError, ValueError, TypeError) as error:
            if isinstance(error, ValidationError):
                raise _validation_error(error) from error
            raise HTTPException(status_code=422, detail="M05-08 build input is invalid") from error
        result = {
            "result": built.result.model_dump(mode="json"),
            "package": (
                base64.b64encode(built.package_bytes).decode("ascii")
                if built.package_bytes is not None
                else None
            ),
        }
        return JSONResponse(content=result)

    @app.exception_handler(PtmLocalizationReleaseInputError)
    async def release_input_error(
        _request: Request,
        _error: PtmLocalizationReleaseInputError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "M05-08 release input rejected"})

    return app


app = create_app()


__all__ = ["app", "create_app"]
