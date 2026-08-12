"""Contract-independent deterministic normalization kernel for M01-06.

The kernel operates on already-authorized scalar observations.  It estimates each technical
level from declared control features only, applies one additive shift uniformly to every
observed value in that level, and never manufactures values for missing or censored inputs.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

_DUPLICATE_VALUE = "target and feature pairs must be unique"
_INVALID_OBSERVED_VALUE = "observed values must be finite"
_INVALID_ABSENT_VALUE = "non-observed values cannot carry a number"
_INVALID_CONTROLS = "control features must be non-empty and unique"
_INVALID_SHIFT_CAP = "maximum absolute shift must be finite and non-negative"
_INVALID_MINIMUM = "minimum control observations must be positive"
_INVALID_REFERENCE = "reference level must be present in the stage"


class ValueState(StrEnum):
    """Explicit state of one input value."""

    OBSERVED = "observed"
    MISSING = "missing"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    NOT_APPLICABLE = "not_applicable"


class ShiftState(StrEnum):
    """Whether a technical-level shift could be estimated and applied."""

    ESTIMATED = "estimated"
    CAPPED = "capped"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class ScalarValue:
    """One target-by-feature value supplied to the pure kernel."""

    target_id: str
    feature_id: str
    state: ValueState
    value: float | None = None


@dataclass(frozen=True, slots=True)
class NormalizationStage:
    """One ordered technical-factor correction."""

    stage_id: str
    factor_id: str
    reference_level_id: str
    control_feature_ids: tuple[str, ...]
    levels_by_target: dict[str, str]
    maximum_absolute_shift: float
    minimum_control_observations: int = 1
    control_target_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LevelShift:
    """Auditable estimate for one factor level."""

    level: str
    state: ShiftState
    estimated_shift: float | None
    applied_shift: float | None
    control_observation_count: int


@dataclass(frozen=True, slots=True)
class StageResult:
    """Manifest material and technical-spread diagnostic for one stage."""

    stage_id: str
    factor_id: str
    level_shifts: tuple[LevelShift, ...]
    pre_level_spread: float | None
    post_level_spread: float | None


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    """Final values and ordered, replayable stage results."""

    values: tuple[ScalarValue, ...]
    stages: tuple[StageResult, ...]


def normalize(
    values: tuple[ScalarValue, ...],
    stages: tuple[NormalizationStage, ...],
) -> NormalizationResult:
    """Apply sequential control-median shifts without imputing non-observed values."""

    _validate_values(values)
    working = values
    manifests: list[StageResult] = []
    for stage in stages:
        _validate_stage(stage)
        working, manifest = _apply_stage(working, stage)
        manifests.append(manifest)
    return NormalizationResult(values=working, stages=tuple(manifests))


def _apply_stage(
    values: tuple[ScalarValue, ...],
    stage: NormalizationStage,
) -> tuple[tuple[ScalarValue, ...], StageResult]:
    controls = set(stage.control_feature_ids)
    control_targets = set(stage.control_target_ids)
    levels = sorted(set(stage.levels_by_target.values()))
    control_values: dict[str, dict[str, list[float]]] = {
        level: {feature_id: [] for feature_id in controls} for level in levels
    }
    for item in values:
        level = stage.levels_by_target.get(item.target_id)
        if (
            level is not None
            and item.feature_id in controls
            and _is_observed(item)
            and (not control_targets or item.target_id in control_targets)
        ):
            control_values[level][item.feature_id].append(_observed_value(item))

    control_counts = {
        level: sum(len(items) for items in by_feature.values())
        for level, by_feature in control_values.items()
    }
    feature_medians = {
        level: {
            feature_id: statistics.median(items)
            for feature_id, items in by_feature.items()
            if items
        }
        for level, by_feature in control_values.items()
        if control_counts[level] >= stage.minimum_control_observations
    }
    reference_medians = feature_medians.get(stage.reference_level_id)
    estimates = {
        level: _relative_shift(reference_medians, medians)
        for level, medians in feature_medians.items()
    }
    shifts = tuple(
        _level_shift(stage, level, control_counts[level], estimates.get(level))
        for level in levels
    )
    applied_by_level = {
        item.level: item.applied_shift
        for item in shifts
        if item.applied_shift is not None
    }
    transformed = tuple(
        _shift_value(
            item,
            applied_by_level.get(level)
            if (level := stage.levels_by_target.get(item.target_id)) is not None
            else None,
        )
        for item in values
    )
    pre_offsets = {
        level: -estimated
        for level, estimated in estimates.items()
        if estimated is not None
    }
    post_offsets = {
        level: offset + applied_by_level[level]
        for level, offset in pre_offsets.items()
        if level in applied_by_level
    }
    return transformed, StageResult(
        stage_id=stage.stage_id,
        factor_id=stage.factor_id,
        level_shifts=shifts,
        pre_level_spread=_spread(pre_offsets),
        post_level_spread=_spread(post_offsets),
    )


def _relative_shift(
    reference_medians: dict[str, float] | None,
    level_medians: dict[str, float],
) -> float | None:
    if reference_medians is None:
        return None
    differences = [
        reference - level_medians[feature_id]
        for feature_id, reference in reference_medians.items()
        if feature_id in level_medians
    ]
    return statistics.median(differences) if differences else None


def _level_shift(
    stage: NormalizationStage,
    level: str,
    control_count: int,
    estimated: float | None,
) -> LevelShift:
    if estimated is None:
        return LevelShift(level, ShiftState.NOT_EVALUABLE, None, None, control_count)
    applied = max(-stage.maximum_absolute_shift, min(stage.maximum_absolute_shift, estimated))
    state = (
        ShiftState.CAPPED
        if abs(estimated) >= stage.maximum_absolute_shift
        else ShiftState.ESTIMATED
    )
    return LevelShift(level, state, estimated, applied, control_count)


def _shift_value(item: ScalarValue, shift: float | None) -> ScalarValue:
    if shift is None or not _is_observed(item):
        return item
    return ScalarValue(item.target_id, item.feature_id, item.state, _observed_value(item) + shift)


def _spread(level_medians: dict[str, float]) -> float | None:
    if not level_medians:
        return None
    return max(level_medians.values()) - min(level_medians.values())


def _is_observed(item: ScalarValue) -> bool:
    return item.state is ValueState.OBSERVED and item.value is not None


def _observed_value(item: ScalarValue) -> float:
    return cast("float", item.value)


def _validate_values(values: tuple[ScalarValue, ...]) -> None:
    keys: set[tuple[str, str]] = set()
    for item in values:
        key = (item.target_id, item.feature_id)
        if key in keys:
            raise ValueError(_DUPLICATE_VALUE)
        keys.add(key)
        if item.state is ValueState.OBSERVED:
            if item.value is None or not math.isfinite(item.value):
                raise ValueError(_INVALID_OBSERVED_VALUE)
        elif item.value is not None:
            raise ValueError(_INVALID_ABSENT_VALUE)


def _validate_stage(stage: NormalizationStage) -> None:
    if not stage.control_feature_ids or len(set(stage.control_feature_ids)) != len(
        stage.control_feature_ids
    ):
        raise ValueError(_INVALID_CONTROLS)
    if not math.isfinite(stage.maximum_absolute_shift) or stage.maximum_absolute_shift < 0:
        raise ValueError(_INVALID_SHIFT_CAP)
    if stage.minimum_control_observations < 1:
        raise ValueError(_INVALID_MINIMUM)
    if stage.reference_level_id not in set(stage.levels_by_target.values()):
        raise ValueError(_INVALID_REFERENCE)


__all__ = [
    "LevelShift",
    "NormalizationResult",
    "NormalizationStage",
    "ScalarValue",
    "ShiftState",
    "StageResult",
    "ValueState",
    "normalize",
]
