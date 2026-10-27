"""Private request-bound endpoint diagnostics; no solver or admission override."""

from .audit import audit_simplex_solution
from .contracts import (
    AUDIT_VERSION,
    DIAGNOSTIC_TOLERANCE,
    ENDPOINT_TOLERANCE,
    SOLVER_CONFIGURATION_DIGEST,
    SimplexAuditError,
    SimplexEndpointAudit,
)

__all__ = [
    "AUDIT_VERSION",
    "DIAGNOSTIC_TOLERANCE",
    "ENDPOINT_TOLERANCE",
    "SOLVER_CONFIGURATION_DIGEST",
    "SimplexAuditError",
    "SimplexEndpointAudit",
    "audit_simplex_solution",
]
