"""Deterministic M27-04 API, SDK, and CLI gateway boundaries."""

from .engine import (
    M2704AuthorizationError,
    M2704GatewayEngine,
    M2704ReplayError,
    preflight_m2704_authorization,
    publish_complex_activity_access_surface,
)
from .plugin import (
    GatewaySubmission,
    M2704Plugin,
    M2704PluginDescriptor,
    M2704TokenError,
    ValidatedM2704Request,
)
from .service import M2704Service

__all__ = [
    "GatewaySubmission",
    "M2704AuthorizationError",
    "M2704GatewayEngine",
    "M2704Plugin",
    "M2704PluginDescriptor",
    "M2704ReplayError",
    "M2704Service",
    "M2704TokenError",
    "ValidatedM2704Request",
    "preflight_m2704_authorization",
    "publish_complex_activity_access_surface",
]
