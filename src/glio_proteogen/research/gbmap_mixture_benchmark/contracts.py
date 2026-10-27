"""Closed aggregate contracts for explicit, unselected mixture point policies."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Annotated, Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import FrozenModel, Sha256Digest
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.simplex import SimplexSolverConfiguration
from glio_proteogen.research.gbmap_selected_fold_replay import SelectedFoldReplayReceipt

Count = Annotated[int, Field(ge=0)]
TerminalReason = Literal[
    "zero_source_count_depth",
    "zero_selected_count_depth",
    "selected_depth_exceeds_int64",
    "no_reference_columns",
    "signature_conditioning_rejected",
    "solver_rejected",
    "solver_numerical_failure",
    "solver_not_converged",
    "solver_trace_invalid",
]
TERMINAL_REASONS: Final[tuple[TerminalReason, ...]] = (
    "zero_source_count_depth",
    "zero_selected_count_depth",
    "selected_depth_exceeds_int64",
    "no_reference_columns",
    "signature_conditioning_rejected",
    "solver_rejected",
    "solver_numerical_failure",
    "solver_not_converged",
    "solver_trace_invalid",
)
SOLVER_CONFIGURATION_DIGEST: Final = sha256_digest(asdict(SimplexSolverConfiguration()))
ROUNDING_TOLERANCE: Final = 2e-12


class MixtureBenchmarkError(ValueError):
    """A sanitized invalid point-benchmark boundary."""


class MixturePointPolicy(FrozenModel):
    """All scientific tuning values are explicit caller choices, not estimates."""

    concentration: Annotated[float, Field(gt=0.0)]
    lambda_mass: Annotated[float, Field(ge=0.0)]
    lambda_shape: Annotated[float, Field(ge=0.0)]
    initial_unknown_mass: Annotated[float, Field(gt=0.0, lt=1.0)]

    @field_validator(
        "concentration", "lambda_mass", "lambda_shape", "initial_unknown_mass", mode="before"
    )
    @classmethod
    def exact_float(cls, value: object) -> object:
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("point policy requires explicit finite Python floats")
        return value

    @property
    def sort_key(self) -> tuple[float, float, float, float]:
        return (
            self.concentration,
            self.lambda_mass,
            self.lambda_shape,
            self.initial_unknown_mass,
        )


class MixtureBenchmarkPlan(FrozenModel):
    """Prespecified caller working assumptions, without learned provenance."""

    plan_version: Literal["gbmap-mixture-sensitivity-plan/1.0.0"] = (
        "gbmap-mixture-sensitivity-plan/1.0.0"
    )
    policies: tuple[MixturePointPolicy, ...] = Field(min_length=1, max_length=64)
    omissions: tuple[tuple[str, ...], ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def unique_working_assumptions(self) -> Self:
        if (
            len({policy.sort_key for policy in self.policies}) != len(self.policies)
            or len(set(self.omissions)) != len(self.omissions)
            or any(
                not omitted
                or omitted != tuple(sorted(set(omitted)))
                or set(omitted) - set(PRODUCTION_SOURCE_LABELS)
                for omitted in self.omissions
            )
        ):
            raise ValueError("plan requires unique policies and canonical public omission groups")
        return self


class VisibilityCounts(FrozenModel):
    source_zero: Count
    source_positive_selected_zero: Count
    selected_positive: Count

    @property
    def total(self) -> int:
        return self.source_zero + self.source_positive_selected_zero + self.selected_positive


class TerminalCount(FrozenModel):
    reason: TerminalReason
    count: Count


def _error_pair(bias: float | None, mae: float | None, *, available: bool) -> bool:
    if (bias is not None) != available or (mae is not None) != available:
        return False
    if bias is None or mae is None:
        return True
    return (
        abs(bias) <= 1.0 + ROUNDING_TOLERANCE
        and 0.0 <= mae <= 1.0 + ROUNDING_TOLERANCE
        and abs(bias) <= mae + ROUNDING_TOLERANCE
    )


class LabelPointMetrics(FrozenModel):
    modeled_label: str
    modeled: bool
    mean_signed_error: float | None
    mean_absolute_error: float | None
    offered_visibility: VisibilityCounts
    scored_visibility: VisibilityCounts

    @model_validator(mode="after")
    def conserve_label(self) -> Self:
        available = self.modeled and self.scored_visibility.total > 0
        if (
            self.modeled_label not in PRODUCTION_SOURCE_LABELS
            or not _error_pair(
                self.mean_signed_error, self.mean_absolute_error, available=available
            )
            or any(
                scored > offered
                for scored, offered in zip(
                    (
                        self.scored_visibility.source_zero,
                        self.scored_visibility.source_positive_selected_zero,
                        self.scored_visibility.selected_positive,
                    ),
                    (
                        self.offered_visibility.source_zero,
                        self.offered_visibility.source_positive_selected_zero,
                        self.offered_visibility.selected_positive,
                    ),
                    strict=True,
                )
            )
        ):
            raise ValueError("label point metrics do not conserve support and error bounds")
        return self


class PolicyScenarioResult(FrozenModel):
    policy: MixturePointPolicy
    omitted_labels: tuple[str, ...]
    offered_case_count: Count
    scored_case_count: Count
    terminal_counts: tuple[TerminalCount, ...] = Field(min_length=9, max_length=9)
    mean_total_variation: float | None
    mean_unknown_signed_error: float | None
    mean_unknown_absolute_error: float | None
    labels: tuple[LabelPointMetrics, ...] = Field(min_length=20, max_length=20)

    @model_validator(mode="after")
    def conserve_scenario(self) -> Self:
        available = self.scored_case_count > 0
        if (
            self.omitted_labels != tuple(sorted(set(self.omitted_labels)))
            or set(self.omitted_labels) - set(PRODUCTION_SOURCE_LABELS)
            or tuple(row.reason for row in self.terminal_counts) != TERMINAL_REASONS
            or self.offered_case_count
            != self.scored_case_count + sum(row.count for row in self.terminal_counts)
            or tuple(row.modeled_label for row in self.labels) != PRODUCTION_SOURCE_LABELS
            or any(
                row.offered_visibility.total != self.offered_case_count
                or row.scored_visibility.total != self.scored_case_count
                for row in self.labels
            )
            or not _error_pair(
                self.mean_unknown_signed_error,
                self.mean_unknown_absolute_error,
                available=available,
            )
            or (self.mean_total_variation is not None) != available
        ):
            raise ValueError("scenario metrics do not conserve offered and scored cases")
        if available:
            if self.mean_total_variation is None or self.mean_unknown_absolute_error is None:
                raise ValueError("scored cases require finite point errors")
            expected_tv = 0.5 * math.fsum(
                [self.mean_unknown_absolute_error]
                + [
                    row.mean_absolute_error
                    for row in self.labels
                    if row.mean_absolute_error is not None
                ]
            )
            total_bias = math.fsum(
                [self.mean_unknown_signed_error or 0.0]
                + [
                    row.mean_signed_error
                    for row in self.labels
                    if row.mean_signed_error is not None
                ]
            )
            if (
                not 0.0 <= self.mean_total_variation <= 1.0 + ROUNDING_TOLERANCE
                or abs(self.mean_total_variation - expected_tv) > ROUNDING_TOLERANCE
                or abs(total_bias) > ROUNDING_TOLERANCE
            ):
                raise ValueError("point errors violate shared-simplex arithmetic")
        return self


class MixtureBenchmarkReceipt(FrozenModel):
    """Conditional point errors; no individual records or calibrated intervals.

    Omission scenarios have different coarsened targets; cross-scenario TV is
    not an improvement comparison. Policy results may have different scored
    support and are not ranked or selected here.
    """

    scope_version: Literal["gbmap-mixture-point-benchmark/1.0.0"] = (
        "gbmap-mixture-point-benchmark/1.0.0"
    )
    context_receipt: SelectedFoldReplayReceipt
    policies: tuple[MixturePointPolicy, ...] = Field(min_length=1, max_length=64)
    omissions: tuple[tuple[str, ...], ...] = Field(max_length=20)
    solver_configuration_digest: Sha256Digest
    results: tuple[PolicyScenarioResult, ...] = Field(min_length=1, max_length=1344)
    policy_selection_performed: Literal[False] = False
    calibration_performed: Literal[False] = False
    unbiased_performance_established: Literal[False] = False

    @field_validator(
        "policy_selection_performed",
        "calibration_performed",
        "unbiased_performance_established",
        mode="before",
    )
    @classmethod
    def exact_false(cls, value: object) -> object:
        if value is not False:
            raise ValueError("point benchmarking cannot establish selection or calibration")
        return value

    @model_validator(mode="after")
    def conserve_product(self) -> Self:
        known = set(self.context_receipt.known_labels)
        keys = tuple(policy.sort_key for policy in self.policies)
        expected = tuple(
            (policy.sort_key, omitted)
            for policy in self.policies
            for omitted in ((), *self.omissions)
        )
        if (
            type(self.context_receipt) is not SelectedFoldReplayReceipt
            or keys != tuple(sorted(set(keys)))
            or self.omissions != tuple(sorted(set(self.omissions)))
            or any(
                not omitted or omitted != tuple(sorted(set(omitted))) or set(omitted) - known
                for omitted in self.omissions
            )
            or self.solver_configuration_digest != SOLVER_CONFIGURATION_DIGEST
            or tuple((row.policy.sort_key, row.omitted_labels) for row in self.results) != expected
        ):
            raise ValueError("benchmark requires the complete canonical policy-scenario product")
        truth = self.context_receipt.held_truth
        for result in self.results:
            counts = tuple(row.count for row in result.terminal_counts)
            remaining = known - set(result.omitted_labels)
            depth_ready = result.offered_case_count - sum(counts[:3])
            if (
                result.offered_case_count != truth.held_unit_count
                or counts[0] != truth.zero_source_depth_case_count
                or counts[1] != truth.zero_selected_depth_case_count
                or counts[:3] != tuple(row.count for row in self.results[0].terminal_counts[:3])
                or counts[3] != (depth_ready if not remaining else 0)
                or (counts[4] > 0 and counts[4] != depth_ready)
            ):
                raise ValueError("terminal states violate fixed depth and reference precedence")
            for row, offered in zip(result.labels, truth.labels, strict=True):
                if (
                    row.modeled != (row.modeled_label in remaining)
                    or row.offered_visibility.source_zero
                    != offered.held_source_zero_unit_count + offered.held_missing_record_unit_count
                    or row.offered_visibility.source_positive_selected_zero
                    != offered.held_source_positive_selected_zero_unit_count
                    or row.offered_visibility.selected_positive
                    != offered.held_selected_positive_unit_count
                ):
                    raise ValueError("benchmark label coverage differs from replayed truth")
        return self
