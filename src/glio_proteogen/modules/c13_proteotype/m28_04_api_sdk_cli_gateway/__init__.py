"""Deterministic M28-04 API, SDK, and CLI gateway boundaries."""

from .api import create_app
from .cli import M2804CliError, app
from .engine import (
    M2804AuthorizationError,
    M2804GatewayEngine,
    M2804ReplayError,
    preflight_m2804_authorization,
    publish_protein_rna_discordance_access_surface,
)
from .plugin import (
    GatewaySubmission,
    M2804Plugin,
    M2804PluginDescriptor,
    M2804TokenError,
    ValidatedM2804Request,
)
from .sdk import M2804Client
from .service import M2804Service

__all__ = [
    "GatewaySubmission",
    "M2804AuthorizationError",
    "M2804CliError",
    "M2804Client",
    "M2804GatewayEngine",
    "M2804Plugin",
    "M2804PluginDescriptor",
    "M2804ReplayError",
    "M2804Service",
    "M2804TokenError",
    "ValidatedM2804Request",
    "app",
    "create_app",
    "preflight_m2804_authorization",
    "publish_protein_rna_discordance_access_surface",
]
