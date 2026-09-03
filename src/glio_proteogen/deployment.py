"""Production configuration and ASGI application construction."""

from __future__ import annotations

# ruff: noqa: TRY003
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from fastapi.routing import APIRoute

from glio_proteogen import __version__
from glio_proteogen.adapters.api import _MODEL_ROUTE_LIMITS, create_app
from glio_proteogen.adapters.limits import MAX_REQUEST_BYTES, RequestSizeLimitMiddleware
from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI

_ALLOWED_LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})
_DEFAULT_DATABASE = "/data/glio-proteogen/events.sqlite3"
_DEFAULT_HOST = "0.0.0.0"  # noqa: S104 - container ingress intentionally binds all interfaces.
_DEFAULT_PORT = 8000
_DEFAULT_LOG_LEVEL = "info"
_DEFAULT_ENVIRONMENT = "production"
_MIN_PORT = 1
_MAX_PORT = 65_535
_S3_FIRST_MODULE = 21
_MODULE_ID_PATTERN = re.compile(r"M\d{2}-\d{2}", re.IGNORECASE)
_OPENAPI_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD", "TRACE"}
)
_RESEARCH_ROUTE_PREFIXES = ("/v1/research/", "/v2/research/")
_VALIDATED_EXAMPLES = {
    "/v1/research/proteogenomic-state/analyze": "synthetic-glioma-demo-v1",
    "/v1/research/gbm-factor-graph/analyze": ("kncc-gbm-factor-graph-synthetic-model-derived-v1"),
    "/v1/research/gbm-functional-proteotype/analyze": (
        "synthetic-migliozzi-functional-proteotype-v1"
    ),
    "/v1/research/gbm-proteomic-axes/analyze": "synthetic-gbm-lfq-demo-v1",
    "/v1/research/neftel-protein-programs/analyze": "synthetic-neftel-ac-program-v1",
    "/v1/research/gbm-master-kinases/analyze": (
        "synthetic-sphinks-gbm-master-kinase-concordance-v1"
    ),
    "/v1/research/gbm-rna-purity/analyze": ("synthetic-primary-idhwt-gbm-rna-purity-v1"),
    "/v1/research/longitudinal-gbm/analyze": ("synthetic-kncc-longitudinal-protein-series-v1"),
    "/v1/research/longitudinal-gbm-phospho/analyze": (
        "synthetic-kncc-longitudinal-phosphosite-series-v1"
    ),
    "/v1/research/longitudinal-gbm-kinase-transition/analyze": (
        "synthetic-kncc-sphinks-signature-transition-v1"
    ),
    "/v1/research/longitudinal-gbm-neftel-transition/analyze": (
        "synthetic-kncc-neftel-program-transition-v1"
    ),
    "/v1/research/longitudinal-gbm-reactome-transition/analyze": (
        "synthetic-kncc-reactome-conditional-transition-v1"
    ),
    "/v1/research/longitudinal-gbm-complex-transition/analyze": (
        "synthetic-kncc-reactome-complex-transition-v1"
    ),
    "/v2/research/modules/m09/complex-transition-concordance/analyze": (
        "synthetic-kncc-reactome-complex-transition-v1"
    ),
    "/v2/research/modules/m10/functional-proteotype/analyze": (
        "synthetic-migliozzi-functional-proteotype-v1"
    ),
    "/v2/research/modules/m11/protein-native-subtype/analyze": ("synthetic-gbm-lfq-demo-v1"),
    "/v2/research/modules/m14/microenvironment-protein-programs/analyze": (
        "synthetic-neftel-ac-program-v1"
    ),
    "/v2/research/modules/m15/longitudinal-recurrence-proteotype/analyze": (
        "synthetic-kncc-longitudinal-protein-series-v1"
    ),
}
_EXAMPLE_STATUS_VALIDATED = "validated"
_EXAMPLE_STATUS_ABSTAINED = "abstained"
_NO_REQUEST_BODY_REASON = "operation_has_no_request_body"
_PRIOR_RESULT_REASON = "requires_prior_operation_result"
_NO_FIXTURE_REASON = "no_repository_validated_fixture"


class DeploymentConfigurationError(ValueError):
    """Environment configuration is invalid for a production process."""


def _validated_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeploymentConfigurationError(f"{name} must not be blank")
    return value.strip()


def _validated_port(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DeploymentConfigurationError(f"{name} must be an integer")
    if not _MIN_PORT <= value <= _MAX_PORT:
        raise DeploymentConfigurationError(f"{name} must be between {_MIN_PORT} and {_MAX_PORT}")
    return value


def _validated_log_level(name: str, value: object) -> str:
    normalized = _validated_text(name, value).lower()
    if normalized not in _ALLOWED_LOG_LEVELS:
        allowed = ", ".join(sorted(_ALLOWED_LOG_LEVELS))
        raise DeploymentConfigurationError(f"{name} must be one of: {allowed}")
    return normalized


def _mounted_paths(app: FastAPI) -> set[str]:
    """Collect paths from the root app and FastAPI's included routers."""

    paths: set[str] = set()
    pending = list(app.routes)
    while pending:
        route = pending.pop()
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(original_router.routes)
    return paths


def _mounted_api_routes(app: FastAPI) -> tuple[APIRoute, ...]:
    """Return every mounted API route, including routes composed from sub-apps."""

    routes: list[APIRoute] = []
    pending = list(reversed(app.routes))
    while pending:
        route = pending.pop()
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            pending.extend(reversed(original_router.routes))
        elif isinstance(route, APIRoute):
            routes.append(route)
    return tuple(routes)


def _mounted_operation_index(app: FastAPI) -> dict[tuple[str, str], APIRoute]:
    """Index effective operations and reject ambiguous Starlette dispatch order."""

    operations: dict[tuple[str, str], APIRoute] = {}
    duplicates: set[tuple[str, str]] = set()
    for route in _mounted_api_routes(app):
        for method in sorted(route.methods or set()):
            if method not in _OPENAPI_HTTP_METHODS:
                continue
            key = (method, route.path)
            if key in operations:
                duplicates.add(key)
            else:
                operations[key] = route
    if duplicates:
        rendered = ", ".join(f"{method} {path}" for method, path in sorted(duplicates))
        raise DeploymentConfigurationError(
            f"duplicate mounted method/path registrations: {rendered}"
        )
    return operations


def _transport_configuration(
    app: FastAPI,
) -> tuple[int, int | None, Mapping[str, tuple[int, int | None]]]:
    """Read the request-limiting configuration mounted on the root application."""

    for middleware in app.user_middleware:
        if cast("object", middleware.cls) is not RequestSizeLimitMiddleware:
            continue
        return (
            cast("int", middleware.kwargs.get("max_bytes", MAX_REQUEST_BYTES)),
            cast("int | None", middleware.kwargs.get("result_max_bytes")),
            cast(
                "Mapping[str, tuple[int, int | None]]",
                middleware.kwargs.get("route_limits", {}),
            ),
        )
    return MAX_REQUEST_BYTES, None, {}


def _route_limits(app: FastAPI, path: str) -> tuple[int, int | None, bool, bool]:
    """Resolve the effective request limits and whether they are route-declared."""

    default_request_limit, default_result_limit, route_limits = _transport_configuration(app)

    matching = (
        (prefix, limits)
        for prefix, limits in route_limits.items()
        if path == prefix or path.startswith(f"{prefix}/")
    )
    selected = max(matching, key=lambda item: len(item[0]), default=None)
    if selected is not None:
        request_limit, result_limit = selected[1]
        return request_limit, result_limit, True, path == selected[0]
    return default_request_limit, default_result_limit, False, False


def _operation_safety(path: str) -> str:
    if path.startswith(_RESEARCH_ROUTE_PREFIXES):
        return "research-use-only"
    module_match = _MODULE_ID_PATTERN.search(path)
    if module_match is not None:
        module_number = int(module_match.group(0)[1:3])
        # Repository contract/plugin declarations consistently bind M01-M20 to
        # S2 and the reference/deployment families M21-M28 to S3.
        return "S3" if module_number >= _S3_FIRST_MODULE else "S2"
    return "operational"


def _operation_mutability(path: str, method: str) -> str:
    if method == "GET":
        return "read-only"
    lowered = path.lower()
    if lowered.endswith("/verify") or "replay" in lowered:
        return "verification"
    if path.startswith(_RESEARCH_ROUTE_PREFIXES):
        return "stateless-compute"
    return "bounded-execution"


def _validated_example_metadata(
    path: str,
    *,
    request_body_present: bool,
    mutability_class: str,
) -> dict[str, str | None]:
    """Return an explicit validated-example registration or abstention contract."""

    example_id = _VALIDATED_EXAMPLES.get(path)
    if example_id is not None:
        return {
            "validated_example_status": _EXAMPLE_STATUS_VALIDATED,
            "validated_example_id": example_id,
            "validated_example_abstention_reason": None,
        }
    if not request_body_present:
        reason = _NO_REQUEST_BODY_REASON
    elif mutability_class == "verification":
        reason = _PRIOR_RESULT_REASON
    else:
        reason = _NO_FIXTURE_REASON
    return {
        "validated_example_status": _EXAMPLE_STATUS_ABSTAINED,
        "validated_example_id": None,
        "validated_example_abstention_reason": reason,
    }


def _operation_catalog(app: FastAPI, settings: DeploymentSettings) -> dict[str, object]:
    """Build a route-derived operation catalog without conflating routes and limits."""

    openapi = app.openapi()
    documented_paths = openapi.get("paths", {})
    operations: list[dict[str, object]] = []
    mounted_operations = _mounted_operation_index(app)
    for (method, path), route in sorted(mounted_operations.items()):
        path_document = documented_paths.get(path, {})
        operation_document = path_document.get(method.lower(), {})
        request_body = operation_document.get("requestBody", {})
        request_content = request_body.get("content", {})
        responses = operation_document.get("responses", {})
        response_media_types = sorted(
            {
                media_type
                for response in responses.values()
                for media_type in response.get("content", {})
            }
        )
        (
            effective_request_limit,
            effective_result_limit,
            route_limits_declared,
            exact_route_limit,
        ) = _route_limits(app, path)
        result_limit = effective_result_limit if route_limits_declared else None
        request_limit = (
            effective_result_limit
            if request_body
            and path.lower().endswith("/verify")
            and effective_result_limit is not None
            and not exact_route_limit
            else effective_request_limit
            if request_body
            else None
        )
        parameters = (
            *path_document.get("parameters", ()),
            *operation_document.get("parameters", ()),
        )
        parameter_locations: set[str] = set()
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            location = parameter.get("in")
            if isinstance(location, str):
                parameter_locations.add(location)
        mutability_class = _operation_mutability(path, method)
        operation: dict[str, object] = {
            "operation_id": operation_document.get("operationId", route.name),
            "method": method,
            "path": path,
            "summary": operation_document.get("summary", route.summary),
            "tags": sorted(str(tag) for tag in route.tags),
            "request_media_types": sorted(request_content),
            "response_media_types": response_media_types,
            "parameter_locations": sorted(parameter_locations),
            "request_max_bytes": request_limit,
            "result_max_bytes": result_limit,
            "safety_class": _operation_safety(path),
            "mutability_class": mutability_class,
        }
        operation.update(
            _validated_example_metadata(
                path,
                request_body_present=bool(request_body),
                mutability_class=mutability_class,
            )
        )
        operations.append(operation)
    catalog: dict[str, object] = {
        "catalog_version": 2,
        "environment": settings.environment,
        "version": __version__,
        "operation_count": len(operations),
        "operations": operations,
    }
    catalog["catalog_digest"] = sha256_digest({"operations": operations})
    return catalog


def _env_text(name: str, default: str) -> str:
    return _validated_text(name, os.environ.get(name, default))


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _env_text(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise DeploymentConfigurationError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise DeploymentConfigurationError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_log_level(name: str, default: str) -> str:
    return _validated_log_level(name, os.environ.get(name, default))


def _deployment_catalog(app: FastAPI, settings: DeploymentSettings) -> dict[str, object]:
    """Build the deterministic mounted-route catalog for one application."""

    mounted_paths = _mounted_paths(app)
    modules: list[dict[str, object]] = []
    unmounted_prefixes: list[str] = []
    for prefix, (request_limit, result_limit) in sorted(_MODEL_ROUTE_LIMITS.items()):
        paths = sorted(
            path for path in mounted_paths if path == prefix or path.startswith(f"{prefix}/")
        )
        if not paths:
            unmounted_prefixes.append(prefix)
            continue
        module_match = _MODULE_ID_PATTERN.search(prefix)
        if module_match is None:
            continue
        modules.append(
            {
                "module_id": module_match.group(0).upper(),
                "route_prefix": prefix,
                "paths": paths,
                "request_max_bytes": request_limit,
                "result_max_bytes": result_limit,
            }
        )
    catalog = {
        "catalog_version": 1,
        "environment": settings.environment,
        "version": __version__,
        "module_count": len(modules),
        "modules": modules,
        "unmounted_route_limit_prefixes": unmounted_prefixes,
    }
    catalog["catalog_digest"] = sha256_digest(
        {
            "modules": modules,
            "unmounted_route_limit_prefixes": unmounted_prefixes,
        }
    )
    return catalog


@dataclass(frozen=True, slots=True)
class DeploymentSettings:
    """Environment-backed settings for the supported production process."""

    database_path: Path
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    log_level: str = _DEFAULT_LOG_LEVEL
    environment: str = _DEFAULT_ENVIRONMENT

    def __post_init__(self) -> None:
        """Validate programmatic settings with the same rules as environment settings."""

        if not isinstance(self.database_path, Path):
            raise DeploymentConfigurationError("database_path must be a pathlib.Path")
        object.__setattr__(self, "host", _validated_text("GLIO_PROTEOGEN_HOST", self.host))
        object.__setattr__(self, "port", _validated_port("GLIO_PROTEOGEN_PORT", self.port))
        object.__setattr__(
            self,
            "log_level",
            _validated_log_level("GLIO_PROTEOGEN_LOG_LEVEL", self.log_level),
        )
        object.__setattr__(
            self,
            "environment",
            _validated_text("GLIO_PROTEOGEN_ENVIRONMENT", self.environment),
        )

    @classmethod
    def from_environment(cls) -> DeploymentSettings:
        return cls(
            database_path=Path(
                _env_text("GLIO_PROTEOGEN_DATABASE_PATH", _DEFAULT_DATABASE)
            ).expanduser(),
            host=_env_text("GLIO_PROTEOGEN_HOST", _DEFAULT_HOST),
            port=_env_int(
                "GLIO_PROTEOGEN_PORT",
                _DEFAULT_PORT,
                minimum=_MIN_PORT,
                maximum=_MAX_PORT,
            ),
            log_level=_env_log_level("GLIO_PROTEOGEN_LOG_LEVEL", _DEFAULT_LOG_LEVEL),
            environment=_env_text("GLIO_PROTEOGEN_ENVIRONMENT", _DEFAULT_ENVIRONMENT),
        )

    def prepare(self) -> None:
        """Create the persistent data directory before SQLite opens the database."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)


def create_deployment_app(settings: DeploymentSettings | None = None) -> FastAPI:
    """Build the canonical API with deployment metadata and persistent storage."""

    resolved = settings or DeploymentSettings.from_environment()
    resolved.prepare()
    app = create_app(resolved.database_path)
    app.state.deployment = {
        "environment": resolved.environment,
        "version": __version__,
        "database_path": str(resolved.database_path),
        "host": resolved.host,
        "port": resolved.port,
        "log_level": resolved.log_level,
    }
    _mounted_operation_index(app)
    initial_catalog = _deployment_catalog(app, resolved)
    if initial_catalog["unmounted_route_limit_prefixes"]:
        raise DeploymentConfigurationError(
            "route limit registry contains unmounted prefixes: "
            f"{initial_catalog['unmounted_route_limit_prefixes']}"
        )

    @app.get("/v1/deployment/catalog", tags=["deployment"])
    def deployment_catalog() -> dict[str, object]:
        """Return the mounted model routes and their transport ceilings."""

        return _deployment_catalog(app, resolved)

    @app.get("/v2/deployment/catalog", tags=["deployment"])
    def operation_catalog() -> dict[str, object]:
        """Return every mounted operation and its execution metadata."""

        return _operation_catalog(app, resolved)

    return app


__all__ = [
    "DeploymentConfigurationError",
    "DeploymentSettings",
    "_operation_catalog",
    "create_deployment_app",
]
