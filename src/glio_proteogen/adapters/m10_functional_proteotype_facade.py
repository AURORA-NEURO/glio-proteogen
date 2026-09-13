"""Research/v2 M10 facade over the fitted Migliozzi GBM proteotype model.

The facade deliberately reuses the delegated adapter's bounded ingress,
concurrency pool, cancellation handling, and replay implementation.  It adds an
M10-specific compatibility profile without creating a second numerical path or
silently changing any governed M10 route.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import TypeAdapter

from glio_proteogen.adapters import gbm_functional_proteotype as delegated_adapter
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.m10_functional_proteotype_facade import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    ROUTE_PREFIX,
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    M10FunctionalProteotypeFacadeProfile,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    m10_facade_demo,
    m10_facade_profile,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

M10_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX: Final = ROUTE_PREFIX
M10_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES: Final = MAX_REQUEST_BYTES
M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES: Final = MAX_RESULT_BYTES
M10_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES: Final = MAX_REPLAY_BYTES
M10_FUNCTIONAL_PROTEOTYPE_MAX_CONCURRENT_ANALYSES: Final = (
    delegated_adapter.GBM_FUNCTIONAL_PROTEOTYPE_MAX_CONCURRENT_ANALYSES
)
M10_FUNCTIONAL_PROTEOTYPE_TIMEOUT_SECONDS: Final = (
    delegated_adapter.GBM_FUNCTIONAL_PROTEOTYPE_TIMEOUT_SECONDS
)

_REQUEST_ADAPTER: Final = TypeAdapter(FunctionalProteotypeRequest)
_REPLAY_ADAPTER: Final = TypeAdapter(ReplayVerificationRequest)
_REQUEST_SCHEMA: Final = _REQUEST_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
_REQUEST_DEFINITIONS: Final = _REQUEST_SCHEMA.pop("$defs")
_REPLAY_SCHEMA: Final = _REPLAY_ADAPTER.json_schema(ref_template="#/components/schemas/{model}")
_REPLAY_DEFINITIONS: Final = _REPLAY_SCHEMA.pop("$defs")

_ERROR_RESPONSES: Final[dict[int | str, dict[str, Any]]] = {
    code: {
        "description": description,
        "content": {"application/json": {"schema": {"type": "object"}}},
    }
    for code, description in {
        400: "Invalid transport metadata",
        413: "Request body exceeds the byte limit",
        415: "Unsupported request media type",
        422: "Request is not evaluable",
        429: "Research execution capacity exhausted",
        499: "Caller disconnected or cancelled",
        500: "Sanitized internal failure",
        504: "Research execution deadline exceeded",
    }.items()
}

router = APIRouter(
    prefix=M10_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX,
    tags=["research-m10-functional-proteotype-evidence"],
)


def _http_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def _bounded[T](value: T, maximum: int, message: str) -> T:
    if len(canonical_json_bytes(value)) > maximum:
        raise _http_error(500, message)
    return value


def _request_body_schema(component: str) -> dict[str, object]:
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{component}"}}
            },
        }
    }


def install_m10_functional_proteotype_openapi(app: FastAPI) -> None:
    """Expose strict delegated request/replay schemas at the M10 research routes."""

    original_openapi = app.openapi

    def openapi_with_facade_contracts() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in {**_REQUEST_DEFINITIONS, **_REPLAY_DEFINITIONS}.items():
            components.setdefault(name, definition)
        components["M10FunctionalProteotypeRequest"] = _REQUEST_SCHEMA
        components["M10FunctionalProteotypeReplayVerificationRequest"] = _REPLAY_SCHEMA
        for operation, component in (
            ("analyze", "M10FunctionalProteotypeRequest"),
            ("verify", "M10FunctionalProteotypeReplayVerificationRequest"),
        ):
            schema["paths"][f"{M10_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX}/{operation}"]["post"][
                "requestBody"
            ] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{component}"}}
                },
            }
        app.openapi_schema = schema
        return schema

    app.__dict__["openapi"] = openapi_with_facade_contracts


@router.get("/profile", response_model=M10FunctionalProteotypeFacadeProfile)
def profile(response: Response) -> M10FunctionalProteotypeFacadeProfile:
    """Describe exact fitted-model delegation and the conservative M10 claim ceiling."""

    try:
        result = _bounded(
            m10_facade_profile(),
            M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES,
            "M10 functional-proteotype profile exceeded its byte limit",
        )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - public boundary never exposes model internals.
        raise _http_error(500, "M10 functional-proteotype profile is unavailable") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Facade-Profile-Digest"] = result.facade_profile_digest
    response.headers["X-GLIO-Profile-Digest"] = result.delegated_profile_digest
    return result


@router.get("/demo", response_model=FunctionalProteotypeRequest)
def demo(response: Response) -> FunctionalProteotypeRequest:
    """Return the exact synthetic request owned by the fitted delegated model."""

    try:
        result = _bounded(
            m10_facade_demo(),
            M10_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES,
            "M10 functional-proteotype demo exceeded its byte limit",
        )
        facade_profile = m10_facade_profile()
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - public boundary never exposes source internals.
        raise _http_error(500, "M10 functional-proteotype demo is unavailable") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-GLIO-Facade-Profile-Digest"] = facade_profile.facade_profile_digest
    response.headers["X-GLIO-Profile-Digest"] = facade_profile.delegated_profile_digest
    response.headers["X-GLIO-Request-Digest"] = result.request_digest
    return result


@router.post(
    "/analyze",
    response_model=FunctionalProteotypeResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema("M10FunctionalProteotypeRequest"),
)
async def analyze(request: Request, response: Response) -> FunctionalProteotypeResult:
    """Run the exact fitted engine through its single shared transport boundary."""

    result = await delegated_adapter.analyze(request, response)
    response.headers["X-GLIO-Facade-Profile-Digest"] = m10_facade_profile().facade_profile_digest
    return result


@router.post(
    "/verify",
    response_model=ReplayVerificationResult,
    responses=_ERROR_RESPONSES,
    openapi_extra=_request_body_schema("M10FunctionalProteotypeReplayVerificationRequest"),
)
async def verify(request: Request, response: Response) -> ReplayVerificationResult:
    """Recompute the exact delegated receipt; the facade adds no replay semantics."""

    result = await delegated_adapter.verify(request, response)
    response.headers["X-GLIO-Facade-Profile-Digest"] = m10_facade_profile().facade_profile_digest
    return result


__all__ = [
    "M10_FUNCTIONAL_PROTEOTYPE_MAX_CONCURRENT_ANALYSES",
    "M10_FUNCTIONAL_PROTEOTYPE_REPLAY_MAX_BYTES",
    "M10_FUNCTIONAL_PROTEOTYPE_REQUEST_MAX_BYTES",
    "M10_FUNCTIONAL_PROTEOTYPE_RESULT_MAX_BYTES",
    "M10_FUNCTIONAL_PROTEOTYPE_ROUTE_PREFIX",
    "M10_FUNCTIONAL_PROTEOTYPE_TIMEOUT_SECONDS",
    "install_m10_functional_proteotype_openapi",
    "router",
]
