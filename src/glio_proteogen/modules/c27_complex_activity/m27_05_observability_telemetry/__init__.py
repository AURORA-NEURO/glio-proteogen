"""M27-05 search/quant observability and telemetry runtime."""

from .api import create_app
from .cli import app
from .engine import (
    M2705AuthorizationError,
    M2705ReplayError,
    M2705TelemetryEngine,
    emit_search_quant_observability_telemetry,
    preflight_m2705_authorization,
)
from .plugin import (
    M2705Plugin,
    M2705PluginDescriptor,
    M2705TokenError,
    TelemetrySubmission,
    ValidatedM2705Request,
)
from .service import M2705Service

__all__ = [
    "M2705AuthorizationError",
    "M2705Plugin",
    "M2705PluginDescriptor",
    "M2705ReplayError",
    "M2705Service",
    "M2705TelemetryEngine",
    "M2705TokenError",
    "TelemetrySubmission",
    "ValidatedM2705Request",
    "app",
    "create_app",
    "emit_search_quant_observability_telemetry",
    "preflight_m2705_authorization",
]
