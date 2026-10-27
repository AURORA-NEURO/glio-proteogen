"""Content-bound numerical policy for exploratory aggregate replication."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from glio_proteogen.kernel.canonical import sha256_digest

from .contracts import ReplicationLimits, ReplicationProfile

METHODS = (
    "Inverse-variance fixed-effect weighted mean with a two-sided nominal normal 95% interval.",
    "DerSimonian-Laird random-effects mean with a two-sided nominal normal 95% interval.",
    "Cochran Q, I-squared percent, and nonnegative DerSimonian-Laird tau-squared.",
    "Approximate normal prediction interval only with at least three observed cohorts.",
    "Two-sided normal random-effects p-values; fixed predeclared-family Benjamini-Hochberg and Benjamini-Yekutieli adjustments, including abstained p=1.",
    "Leave-one-observed-cohort-out random-effects refits only with at least three observed cohorts.",
)
ASSUMPTIONS = (
    "All cohorts use the declared disease context, contrast, effect scale, and estimand with aligned signs; this is a caller assertion, not empirically verified compatibility.",
    "Participants are disjoint across cohorts by caller declaration. Unique source digests and independence groups are conservative checks, not proof of independence.",
    "Input standard errors are treated as supplied positive uncertainty summaries; their estimation and validity are not verified. Sample sizes are descriptive and are not additional analytic weights.",
    "Normal intervals and prediction intervals are approximate and can be unreliable with few cohorts; no Student-t, Hartung-Knapp, or interval-calibration correction is applied.",
    "Benjamini-Hochberg relies on independence or suitable positive dependence. Benjamini-Yekutieli provides a dependence-robust adjustment under valid marginal null p-values, which this exploratory lane does not establish.",
    "The selected feature family must be fixed before inspecting effects. Adjustment does not repair selective reporting, invalid standard errors, publication bias, or incompatible cohorts.",
    "No real dataset or source-derived biological result ships with this algorithm; the demo is entirely fictitious.",
)


@lru_cache(maxsize=1)
def algorithm_profile() -> ReplicationProfile:
    """Return a source- and policy-bound immutable profile."""

    directory = Path(__file__).parent
    source_digest = sha256_digest(
        {
            name: (directory / name).read_text(encoding="utf-8").replace("\r\n", "\n")
            for name in ("contracts.py", "canonical.py", "engine.py", "profile.py")
        }
    )
    payload = {
        "schema_version": "1.0.0",
        "profile_id": "glioma-cohort-replication/1.0.0",
        "algorithm_id": "glioma-cohort-replication",
        "algorithm_version": "1.0.0",
        "engine_semantic_digest": source_digest,
        "methods": METHODS,
        "assumptions": ASSUMPTIONS,
        "limits": ReplicationLimits().model_dump(mode="json"),
        "synthetic_demo_only": True,
    }
    return ReplicationProfile.model_validate({**payload, "profile_digest": sha256_digest(payload)})
