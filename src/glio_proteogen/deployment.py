"""Production configuration and ASGI application construction."""

from __future__ import annotations

# ruff: noqa: TRY003
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from glio_proteogen import __version__
from glio_proteogen.adapters.api import _MODEL_ROUTE_LIMITS, create_app
from glio_proteogen.kernel.canonical import sha256_digest

if TYPE_CHECKING:
    from fastapi import FastAPI

_ALLOWED_LOG_LEVELS = frozenset({"critical", "error", "warning", "info", "debug", "trace"})
_DEFAULT_DATABASE = "/data/glio-proteogen/events.sqlite3"
_DEFAULT_HOST = "0.0.0.0"  # noqa: S104 - container ingress intentionally binds all interfaces.
_DEFAULT_PORT = 8000
_DEFAULT_LOG_LEVEL = "info"
_DEFAULT_ENVIRONMENT = "production"
_MIN_PORT = 1
_MAX_PORT = 65_535
_MODULE_ID_PATTERN = re.compile(r"M\d{2}-\d{2}", re.IGNORECASE)


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

    return app


__all__ = ["DeploymentConfigurationError", "DeploymentSettings", "create_deployment_app"]
