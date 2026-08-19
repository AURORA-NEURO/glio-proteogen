"""Provisional M24-02 synthetic-truth generator boundary."""

from .api import create_app
from .cli import app as cli_app
from .engine import (
    AuthorizationError,
    M2402ReplayError,
    M2402SyntheticTruthGenerator,
    generate_biomarker_panel_synthetic_truth,
    preflight_m2402_authorization,
)
from .plugin import M2402Plugin, SyntheticTruthSubmission, ValidatedM2402Request
from .service import M2402Service

__all__ = [
    "AuthorizationError",
    "M2402Plugin",
    "M2402ReplayError",
    "M2402Service",
    "M2402SyntheticTruthGenerator",
    "SyntheticTruthSubmission",
    "ValidatedM2402Request",
    "cli_app",
    "create_app",
    "generate_biomarker_panel_synthetic_truth",
    "preflight_m2402_authorization",
]
