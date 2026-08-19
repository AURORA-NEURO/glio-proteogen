"""M20-04 intended-use adaptation beneath protein-subtype integration."""

from .engine import (
    M2004AuthorizationError,
    M2004Engine,
    M2004ReplayError,
    adapt_protein_subtype_intended_use,
    preflight_m2004_authorization,
)
from .plugin import M2004Plugin, M2004PluginDescriptor, ValidatedM2004Request
from .service import M2004Service

__all__ = [
    "M2004AuthorizationError",
    "M2004Engine",
    "M2004Plugin",
    "M2004PluginDescriptor",
    "M2004ReplayError",
    "M2004Service",
    "ValidatedM2004Request",
    "adapt_protein_subtype_intended_use",
    "preflight_m2004_authorization",
]
