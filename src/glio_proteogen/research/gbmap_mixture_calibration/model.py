"""Immutable arithmetic summaries, without claims about calibration provenance."""

from __future__ import annotations

import math
from fractions import Fraction
from numbers import Real
from typing import Annotated, Final, Literal, Self

import numpy as np
from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel

POLICY_ID: Final = "bounded-unknown-mass-decimal-rank-v1"
Count = Annotated[int, Field(ge=0)]
UnitInterval = Annotated[float, Field(ge=0.0, le=1.0)]


class MixtureCalibrationError(ValueError):
    """Invalid caller-supplied bounded score or calibration configuration."""


def _unit_interval(value: object, *, name: str) -> float:
    # Test the original value before conversion: out-of-support Fractions can
    # otherwise round to 1.0 or -0.0 and silently pass the normalized check.
    if (
        isinstance(value, (bool, np.bool_))
        or not isinstance(value, Real)
        or value < 0
        or not value <= 1
    ):
        raise MixtureCalibrationError(f"{name} requires a non-Boolean real value in [0, 1]")
    numeric = float(value)
    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
        raise MixtureCalibrationError(f"{name} requires a finite normalized value in [0, 1]")
    return numeric


def _rank(sample_count: int, target_specificity: float) -> int:
    # This is a declared decimal rendering policy, not an interpretation of an
    # original rational input or an exact product of binary floating values.
    requested = Fraction(str(target_specificity)) * (sample_count + 1)
    return math.ceil(requested)


class BoundedUnknownMassCalibration(FrozenModel):
    """Cutoff scalars and empirical counts, without per-observation records.

    The summary checks arithmetic consistency; it cannot authenticate input
    scores, independent sampling units, a fixed scoring rule or exchangeability.
    An observed untruncated cutoff never certifies conditional coverage. A
    ceiling below one changes the declared rank procedure even on runs where
    that ceiling does not truncate the observed candidate.
    """

    policy_id: Literal["bounded-unknown-mass-decimal-rank-v1"] = POLICY_ID
    calibration_score_count: Annotated[int, Field(ge=1)]
    target_specificity: Annotated[float, Field(gt=0.0, lt=1.0)]
    required_rank: Annotated[int, Field(ge=1)]
    rank_candidate: UnitInterval
    candidate_source: Literal["calibration_order_statistic", "known_unit_interval_support"]
    hard_ceiling: UnitInterval | None
    policy_threshold: UnitInterval
    observed_candidate_truncated: bool
    threshold_rule_kind: Literal["uncapped_rank_rule", "ceiling_modified_rank_rule"]
    accepted_calibration_score_count: Count
    empirical_calibration_specificity: UnitInterval
    omission_score_count: Count
    flagged_omission_score_count: Count
    empirical_omission_sensitivity: UnitInterval | None
    exchangeability_verified: Literal[False] = False

    @field_validator("exchangeability_verified", mode="before")
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("a score summary cannot verify exchangeability")
        return value

    @model_validator(mode="after")
    def consistent_policy(self) -> Self:
        rank = _rank(self.calibration_score_count, self.target_specificity)
        support_fallback = rank > self.calibration_score_count
        expected_source = (
            "known_unit_interval_support" if support_fallback else "calibration_order_statistic"
        )
        threshold = (
            self.rank_candidate
            if self.hard_ceiling is None
            else min(self.rank_candidate, self.hard_ceiling)
        )
        truncated = threshold < self.rank_candidate
        rule_kind = (
            "uncapped_rank_rule"
            if self.hard_ceiling is None or self.hard_ceiling == 1.0
            else "ceiling_modified_rank_rule"
        )
        if (
            self.required_rank != rank
            or self.candidate_source != expected_source
            or (support_fallback and self.rank_candidate != 1.0)
            or self.policy_threshold != threshold
            or self.observed_candidate_truncated != truncated
            or self.threshold_rule_kind != rule_kind
        ):
            raise ValueError("calibration summary disagrees with its declared rank and ceiling")
        if (
            self.accepted_calibration_score_count > self.calibration_score_count
            or self.flagged_omission_score_count > self.omission_score_count
            or self.empirical_calibration_specificity
            != self.accepted_calibration_score_count / self.calibration_score_count
            or self.empirical_omission_sensitivity
            != (
                self.flagged_omission_score_count / self.omission_score_count
                if self.omission_score_count
                else None
            )
            or (
                not truncated
                and self.accepted_calibration_score_count < min(rank, self.calibration_score_count)
            )
            or (truncated and self.accepted_calibration_score_count >= rank)
            or (
                threshold == 1.0
                and (
                    self.accepted_calibration_score_count != self.calibration_score_count
                    or self.flagged_omission_score_count != 0
                )
            )
        ):
            raise ValueError("calibration summary does not conserve empirical outcome counts")
        return self

    def accepts(self, score: object) -> bool:
        """Apply the cutoff with the same float64 normalization and inclusive tie rule.

        True means only that this bounded score is below the declared cutoff.
        It does not qualify a patient, authenticate a model or estimate purity.
        """

        return _unit_interval(score, name="unknown-mass score") <= self.policy_threshold
