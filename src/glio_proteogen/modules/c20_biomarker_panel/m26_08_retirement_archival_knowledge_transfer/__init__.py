"""M26-08 retirement, archival and knowledge-transfer module."""

from .engine import (
    M2608AuthorizationError,
    M2608ReplayError,
    M2608RetirementEngine,
    preflight_m2608_authorization,
    retire_protein_subtype_service,
    verify_retirement_result,
)
from .plugin import (
    M2608Plugin,
    M2608PluginDescriptor,
    M2608TokenError,
    RetirementSubmission,
    ValidatedM2608Request,
)
from .service import (
    M2608RetirementService,
)

__all__ = [
    "M2608AuthorizationError",
    "M2608Plugin",
    "M2608PluginDescriptor",
    "M2608ReplayError",
    "M2608RetirementEngine",
    "M2608RetirementService",
    "M2608TokenError",
    "RetirementSubmission",
    "ValidatedM2608Request",
    "preflight_m2608_authorization",
    "retire_protein_subtype_service",
    "verify_retirement_result",
]
