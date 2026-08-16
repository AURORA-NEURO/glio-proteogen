"""M21-02 synthetic truth and simulation generator boundary."""

from .api import create_app
from .cli import app as cli_app
from .engine import (
    M2102AuthorizationError,
    M2102Engine,
    M2102ReplayError,
    generate_complex_activity_synthetic_truth,
    preflight_m2102_authorization,
)
from .plugin import M2102Plugin, SyntheticTruthSubmission, ValidatedM2102Request
from .service import M2102Service

__all__ = [
    "M2102AuthorizationError",
    "M2102Engine",
    "M2102Plugin",
    "M2102ReplayError",
    "M2102Service",
    "SyntheticTruthSubmission",
    "ValidatedM2102Request",
    "cli_app",
    "create_app",
    "generate_complex_activity_synthetic_truth",
    "preflight_m2102_authorization",
]
