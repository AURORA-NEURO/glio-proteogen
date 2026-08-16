"""Provisional M24-05 subgroup equity evaluator service boundary."""

from .api import create_app
from .cli import app as cli_app
from .engine import (
    M2405AuthorizationError,
    M2405ReplayError,
    M2405SubgroupEquityEvaluator,
    evaluate_biomarker_panel_subgroup_equity,
    preflight_m2405_authorization,
)
from .plugin import M2405Plugin, SubgroupEvaluationSubmission, ValidatedM2405Request
from .service import M2405Service

__all__ = [
    "M2405AuthorizationError",
    "M2405Plugin",
    "M2405ReplayError",
    "M2405Service",
    "M2405SubgroupEquityEvaluator",
    "SubgroupEvaluationSubmission",
    "ValidatedM2405Request",
    "cli_app",
    "create_app",
    "evaluate_biomarker_panel_subgroup_equity",
    "preflight_m2405_authorization",
]
