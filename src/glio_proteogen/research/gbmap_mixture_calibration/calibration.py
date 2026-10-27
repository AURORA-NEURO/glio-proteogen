"""A corrected bounded-support rank cutoff, separate from the frozen experiment.

For normalized scores in [0, 1], use the kth order statistic with
k = ceil((n + 1) * c). If k exceeds n, use the known support bound 1, rather
than incorrectly substituting the sample maximum. This is the bounded-support
equivalent of the infinite cutoff in Appendix D of Angelopoulos and Bates:
https://arxiv.org/html/2107.07511v6#A4

The usual marginal rank argument needs a fixed scoring rule and exchangeable
calibration/test units. This primitive does not establish those conditions.
Repeated donor-fold occurrences are not automatically independent units.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .model import (
    BoundedUnknownMassCalibration,
    MixtureCalibrationError,
    _rank,
    _unit_interval,
)


def _scores(values: npt.ArrayLike, *, name: str, allow_empty: bool) -> list[float]:
    if np.ma.isMaskedArray(values):
        raise MixtureCalibrationError(f"{name} cannot silently discard masked scores")
    try:
        raw = np.asarray(values, dtype=object)
    except (TypeError, ValueError) as error:
        raise MixtureCalibrationError(f"{name} requires a one-dimensional score vector") from error
    if raw.ndim != 1 or (not allow_empty and raw.size == 0):
        raise MixtureCalibrationError(f"{name} requires a one-dimensional score vector")
    return [_unit_interval(value, name=name) for value in raw]


def calibrate_unknown_mass(
    known_calibration_scores: npt.ArrayLike,
    omission_evaluation_scores: npt.ArrayLike | None = None,
    *,
    target_specificity: object = 0.95,
    hard_ceiling: object = 0.35,
) -> BoundedUnknownMassCalibration:
    """Summarize a known-score cutoff; omission scores evaluate sensitivity only.

    Inputs must be one-dimensional finite real scores in [0, 1]. Bounds are
    checked before float64 normalization; Boolean and masked inputs are rejected.
    The target is normalized to float64, then interpreted by its canonical
    decimal rendering ``str(float(c))`` when computing the rank. This explicit
    policy avoids floating multiplication changing adjacent rank boundaries.

    ``hard_ceiling=None`` or ``1`` leaves the rank rule uncapped. Any ceiling
    below one declares a modified rule, whether or not it truncates this sample's
    candidate. Empirical specificity/sensitivity describe supplied observations,
    never nominal coverage. Empty omission evaluation has sensitivity None.
    The immutable summary retains cutoff scalars and aggregate outcomes, without
    score vectors or per-observation records. A candidate may equal a supplied
    order-statistic score.
    """

    target = _unit_interval(target_specificity, name="target specificity")
    if not 0.0 < target < 1.0:
        raise MixtureCalibrationError("target specificity must lie strictly between zero and one")
    ceiling = None if hard_ceiling is None else _unit_interval(hard_ceiling, name="hard ceiling")
    known = _scores(known_calibration_scores, name="known calibration", allow_empty=False)
    omitted = (
        []
        if omission_evaluation_scores is None
        else _scores(omission_evaluation_scores, name="omission evaluation", allow_empty=True)
    )
    rank = _rank(len(known), target)
    support_fallback = rank > len(known)
    candidate = 1.0 if support_fallback else sorted(known)[rank - 1]
    threshold = candidate if ceiling is None else min(candidate, ceiling)
    accepted = sum(value <= threshold for value in known)
    flagged = sum(value > threshold for value in omitted)
    return BoundedUnknownMassCalibration(
        calibration_score_count=len(known),
        target_specificity=target,
        required_rank=rank,
        rank_candidate=candidate,
        candidate_source=(
            "known_unit_interval_support" if support_fallback else "calibration_order_statistic"
        ),
        hard_ceiling=ceiling,
        policy_threshold=threshold,
        observed_candidate_truncated=threshold < candidate,
        threshold_rule_kind=(
            "uncapped_rank_rule"
            if ceiling is None or ceiling == 1.0
            else "ceiling_modified_rank_rule"
        ),
        accepted_calibration_score_count=accepted,
        empirical_calibration_specificity=accepted / len(known),
        omission_score_count=len(omitted),
        flagged_omission_score_count=flagged,
        empirical_omission_sensitivity=flagged / len(omitted) if omitted else None,
    )
