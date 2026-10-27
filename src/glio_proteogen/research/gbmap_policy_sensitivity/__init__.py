"""Matched-support sensitivity for explicit, unselected GBmap point policies."""

from .analysis import score_matched_policy_sensitivity
from .contracts import (
    MatchedPolicyMetrics,
    MatchedPolicySensitivityReceipt,
    PolicySensitivityError,
    ScenarioMatchedSupport,
)

__all__ = [
    "MatchedPolicyMetrics",
    "MatchedPolicySensitivityReceipt",
    "PolicySensitivityError",
    "ScenarioMatchedSupport",
    "score_matched_policy_sensitivity",
]
