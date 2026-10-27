"""Closed, aggregate-only comparison on the prespecified all-policy intersection."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_mixture_benchmark import (
    LabelPointMetrics,
    MixtureBenchmarkReceipt,
    MixturePointPolicy,
)
from glio_proteogen.research.gbmap_mixture_benchmark.contracts import ROUNDING_TOLERANCE

Count = Annotated[int, Field(ge=0)]


class PolicySensitivityError(ValueError):
    """Sanitized failure of a private matched-policy comparison."""


class MatchedPolicyMetrics(FrozenModel):
    policy: MixturePointPolicy
    original_scored_case_count: Count
    excluded_from_common_case_count: Count
    mean_total_variation: float | None
    mean_unknown_signed_error: float | None
    mean_unknown_absolute_error: float | None
    labels: tuple[LabelPointMetrics, ...] = Field(min_length=20, max_length=20)

    @property
    def common_case_count(self) -> int:
        return self.original_scored_case_count - self.excluded_from_common_case_count

    @model_validator(mode="after")
    def conserve_errors(self) -> Self:
        common = self.common_case_count
        metrics = (
            self.mean_total_variation,
            self.mean_unknown_signed_error,
            self.mean_unknown_absolute_error,
        )
        if (
            common < 0
            or tuple(row.modeled_label for row in self.labels) != PRODUCTION_SOURCE_LABELS
            or any(row.scored_visibility.total != common for row in self.labels)
            or any((value is not None) != (common > 0) for value in metrics)
        ):
            raise ValueError("matched metrics must conserve the common denominator")
        if common:
            tv, bias, mae = metrics
            if tv is None or bias is None or mae is None:
                raise ValueError("positive common support requires finite errors")
            expected_tv = 0.5 * math.fsum(
                [mae]
                + [
                    row.mean_absolute_error
                    for row in self.labels
                    if row.mean_absolute_error is not None
                ]
            )
            closure = math.fsum(
                [bias]
                + [
                    row.mean_signed_error
                    for row in self.labels
                    if row.mean_signed_error is not None
                ]
            )
            if (
                not 0.0 <= tv <= 1.0 + ROUNDING_TOLERANCE
                or not 0.0 <= mae <= 1.0 + ROUNDING_TOLERANCE
                or abs(bias) > mae + ROUNDING_TOLERANCE
                or abs(tv - expected_tv) > ROUNDING_TOLERANCE
                or abs(closure) > ROUNDING_TOLERANCE
            ):
                raise ValueError("matched errors violate the common shared simplex")
        return self


class ScenarioMatchedSupport(FrozenModel):
    omitted_labels: tuple[str, ...]
    offered_case_count: Count
    all_policy_scored_case_count: Count
    some_policy_scored_case_count: Count
    no_policy_scored_case_count: Count
    mean_unknown_mass_spread: float | None
    max_unknown_mass_spread: float | None
    policies: tuple[MatchedPolicyMetrics, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def conserve_intersection(self) -> Self:
        common = self.all_policy_scored_case_count
        some = self.some_policy_scored_case_count
        any_scored = common + some
        offered = self.offered_case_count
        keys = tuple(row.policy.sort_key for row in self.policies)
        exclusions = tuple(row.excluded_from_common_case_count for row in self.policies)
        if (
            self.omitted_labels != tuple(sorted(set(self.omitted_labels)))
            or set(self.omitted_labels) - set(PRODUCTION_SOURCE_LABELS)
            or keys != tuple(sorted(set(keys)))
            or offered != common + some + self.no_policy_scored_case_count
            or any(
                row.common_case_count != common
                or row.original_scored_case_count > any_scored
                or row.excluded_from_common_case_count > some
                or any(label.offered_visibility.total != offered for label in row.labels)
                for row in self.policies
            )
            or not some <= sum(exclusions) <= (len(self.policies) - 1) * some
        ):
            raise ValueError("policy support does not conserve the offered intersection")
        first = self.policies[0]
        if any(
            tuple(label.scored_visibility for label in row.labels)
            != tuple(label.scored_visibility for label in first.labels)
            for row in self.policies[1:]
        ):
            raise ValueError("all policies require the same common label visibility")
        spread = (self.mean_unknown_mass_spread, self.max_unknown_mass_spread)
        if any((value is not None) != (common > 0) for value in spread):
            raise ValueError("unknown spread is unavailable without common support")
        if common:
            mean, maximum = spread
            if mean is None or maximum is None:
                raise ValueError("positive common support requires finite spread")
            biases = tuple(row.mean_unknown_signed_error for row in self.policies)
            available = tuple(value for value in biases if value is not None)
            bias_range = max(available) - min(available)
            maes = tuple(
                row.mean_unknown_absolute_error
                for row in self.policies
                if row.mean_unknown_absolute_error is not None
            )
            if (
                not 0.0 <= mean <= maximum + ROUNDING_TOLERANCE
                or not 0.0 <= maximum <= 1.0 + ROUNDING_TOLERANCE
                or maximum > common * mean + ROUNDING_TOLERANCE
                or mean + ROUNDING_TOLERANCE < bias_range
                or mean > math.fsum(maes) + ROUNDING_TOLERANCE
                or mean + ROUNDING_TOLERANCE < max(maes) - min(maes)
                or (common == 1 and abs(mean - maximum) > ROUNDING_TOLERANCE)
                or (common == 1 and abs(mean - bias_range) > ROUNDING_TOLERANCE)
                or (len(self.policies) == 1 and maximum > ROUNDING_TOLERANCE)
            ):
                raise ValueError("unknown spread contradicts common error arithmetic")
        return self


def _visibility_values(row: LabelPointMetrics, *, common: bool) -> tuple[int, int, int]:
    counts = row.scored_visibility if common else row.offered_visibility
    return counts.source_zero, counts.source_positive_selected_zero, counts.selected_positive


def _validate_error_mass(
    original_count: int,
    common_count: int,
    original: tuple[float | None, float | None, float | None],
    matched: tuple[float | None, float | None, float | None],
) -> None:
    """Bound excluded TV/bias/MAE sums, without inferring hidden case identity.

    A missing TV slot supports label-only bias/MAE checks. Empty original
    support needs no available means. Full support preserves exact fields
    because the scoring reductions use identical case order.
    """
    if common_count == original_count:
        if original != matched:
            raise ValueError("full common support must preserve exact parent error means")
        return
    if original_count == 0:
        return
    excluded = original_count - common_count
    tolerance = max(1, original_count) * ROUNDING_TOLERANCE
    residuals: list[float | None] = []
    for index, (old_mean, common_mean) in enumerate(zip(original, matched, strict=True)):
        if old_mean is None:
            if common_mean is not None:
                raise ValueError("unavailable parent errors cannot become matched observations")
            residuals.append(None)
            continue
        if common_count > 0 and common_mean is None:
            raise ValueError("positive common support requires corresponding error means")
        common_sum = 0.0 if common_mean is None else common_count * common_mean
        residual = original_count * old_mean - common_sum
        if (
            not math.isfinite(residual)
            or residual > excluded + tolerance
            or residual < (-excluded - tolerance if index == 1 else -tolerance)
        ):
            raise ValueError("common errors exceed the parent excluded-case error mass")
        residuals.append(residual)
    bias, mae = residuals[1:]
    if bias is not None and mae is not None and abs(bias) > mae + tolerance:
        raise ValueError("excluded-case signed error cannot exceed excluded absolute error")


class MatchedPolicySensitivityReceipt(FrozenModel):
    """Common-support diagnostics, never per-case parity or inference proof.

    Full reconstructed parent aggregate equality does not authenticate its
    original case masks. The common intersection is measured in the new
    deterministic casewise replay. Saved arithmetic is not execution authority.
    Spread summarizes declared policies, not a calibrated uncertainty interval.
    """

    scope_version: Literal["gbmap-matched-policy-sensitivity/1.0.0"] = (
        "gbmap-matched-policy-sensitivity/1.0.0"
    )
    parent_benchmark: MixtureBenchmarkReceipt
    scenarios: tuple[ScenarioMatchedSupport, ...] = Field(min_length=1, max_length=21)
    policy_selection_performed: Literal[False] = False
    calibration_performed: Literal[False] = False
    empirical_unit_independence_established: Literal[False] = False
    clinical_validity_established: Literal[False] = False

    @field_validator(
        "policy_selection_performed",
        "calibration_performed",
        "empirical_unit_independence_established",
        "clinical_validity_established",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("matched sensitivity cannot establish a broader inference claim")
        return value

    @model_validator(mode="after")
    def bind_parent(self) -> Self:
        parent = self.parent_benchmark
        expected_scenarios = ((), *parent.omissions)
        if (
            type(parent) is not MixtureBenchmarkReceipt
            or tuple(row.omitted_labels for row in self.scenarios) != expected_scenarios
            or any(
                tuple(row.policy for row in scenario.policies) != parent.policies
                for scenario in self.scenarios
            )
        ):
            raise ValueError("matched scenarios must preserve the full parent policy product")
        lookup = {(row.policy.sort_key, row.omitted_labels): row for row in parent.results}
        for scenario in self.scenarios:
            originals = tuple(
                lookup[(matched.policy.sort_key, scenario.omitted_labels)]
                for matched in scenario.policies
            )
            for index, label in enumerate(scenario.policies[0].labels):
                offered = _visibility_values(originals[0].labels[index], common=False)
                common = _visibility_values(label, common=True)
                for category, (offered_count, common_count) in enumerate(
                    zip(offered, common, strict=True)
                ):
                    parent_total = sum(
                        _visibility_values(original.labels[index], common=True)[category]
                        for original in originals
                    )
                    lower = max(0, parent_total - (len(originals) - 1) * offered_count)
                    if common_count < lower:
                        raise ValueError("common label visibility violates its intersection bound")
            for matched, original in zip(scenario.policies, originals, strict=True):
                if (
                    scenario.offered_case_count != original.offered_case_count
                    or matched.original_scored_case_count != original.scored_case_count
                    or matched.excluded_from_common_case_count
                    != original.scored_case_count - scenario.all_policy_scored_case_count
                ):
                    raise ValueError("matched counts differ from the retained original parent")
                _validate_error_mass(
                    original.scored_case_count,
                    scenario.all_policy_scored_case_count,
                    (
                        original.mean_total_variation,
                        original.mean_unknown_signed_error,
                        original.mean_unknown_absolute_error,
                    ),
                    (
                        matched.mean_total_variation,
                        matched.mean_unknown_signed_error,
                        matched.mean_unknown_absolute_error,
                    ),
                )
                for label, old_label in zip(matched.labels, original.labels, strict=True):
                    if (
                        label.modeled != old_label.modeled
                        or label.offered_visibility != old_label.offered_visibility
                        or any(
                            value > old_value
                            for value, old_value in zip(
                                _visibility_values(label, common=True),
                                _visibility_values(old_label, common=True),
                                strict=True,
                            )
                        )
                    ):
                        raise ValueError(
                            "common visibility must be a subset of each parent support"
                        )
                    _validate_error_mass(
                        original.scored_case_count,
                        scenario.all_policy_scored_case_count,
                        (None, old_label.mean_signed_error, old_label.mean_absolute_error),
                        (None, label.mean_signed_error, label.mean_absolute_error),
                    )
        return self
