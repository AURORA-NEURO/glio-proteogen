"""Focused tests for the pure M01-06 normalization kernel."""

from __future__ import annotations

import pytest

from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.kernel import (
    NormalizationStage,
    ScalarValue,
    ShiftState,
    ValueState,
    normalize,
)


def _value(target: str, feature: str, value: float) -> ScalarValue:
    return ScalarValue(target, feature, ValueState.OBSERVED, value)


def _stage(
    *,
    cap: float = 10.0,
    minimum: int = 1,
) -> NormalizationStage:
    return NormalizationStage(
        stage_id="stage.batch",
        factor_id="batch",
        reference_level_id="batch.a",
        control_feature_ids=("control.a", "control.b"),
        levels_by_target={"sample.1": "batch.a", "sample.2": "batch.b"},
        maximum_absolute_shift=cap,
        minimum_control_observations=minimum,
    )


def test_control_median_shift_removes_level_spread_and_is_uniform() -> None:
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.1", "control.b", 22.0),
        _value("sample.1", "biology", 7.0),
        _value("sample.2", "control.a", 8.0),
        _value("sample.2", "control.b", 18.0),
        _value("sample.2", "biology", 3.0),
    )

    result = normalize(values, (_stage(),))

    assert tuple(item.value for item in result.values) == (12.0, 22.0, 7.0, 12.0, 22.0, 7.0)
    assert result.stages[0].pre_level_spread == pytest.approx(4.0)
    assert result.stages[0].post_level_spread == 0.0
    assert tuple(item.applied_shift for item in result.stages[0].level_shifts) == (0.0, 4.0)


@pytest.mark.parametrize(
    "state",
    [ValueState.MISSING, ValueState.BELOW_DETECTION_LIMIT, ValueState.NOT_APPLICABLE],
)
def test_nonobserved_values_are_preserved_exactly(state: ValueState) -> None:
    absent = ScalarValue("sample.1", "biology", state)
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.2", "control.a", 8.0),
        absent,
    )

    result = normalize(values, (_stage(),))

    assert result.values[-1] is absent
    assert result.values[-1].value is None


def test_only_declared_control_features_estimate_shift() -> None:
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.2", "control.a", 8.0),
        _value("sample.1", "undeclared", 1_000.0),
        _value("sample.2", "undeclared", -1_000.0),
    )

    result = normalize(values, (_stage(),))

    assert tuple(item.applied_shift for item in result.stages[0].level_shifts) == (0.0, 4.0)


def test_only_declared_control_targets_estimate_shift() -> None:
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.2", "control.a", 8.0),
        _value("sample.outlier", "control.a", 1_000.0),
    )
    stage = NormalizationStage(
        stage_id="stage.batch",
        factor_id="batch",
        reference_level_id="batch.a",
        control_feature_ids=("control.a",),
        levels_by_target={
            "sample.1": "batch.a",
            "sample.2": "batch.b",
            "sample.outlier": "batch.a",
        },
        maximum_absolute_shift=10.0,
        control_target_ids=("sample.1", "sample.2"),
    )

    result = normalize(values, (stage,))

    assert tuple(item.applied_shift for item in result.stages[0].level_shifts) == (0.0, 4.0)
    assert result.values[-1].value == pytest.approx(1_000.0)


def test_shift_is_capped_and_remaining_spread_is_reported() -> None:
    values = (
        _value("sample.1", "control.a", 20.0),
        _value("sample.2", "control.a", 0.0),
    )

    result = normalize(values, (_stage(cap=3.0),))

    shifts = result.stages[0].level_shifts
    assert tuple(item.state for item in shifts) == (ShiftState.ESTIMATED, ShiftState.CAPPED)
    assert tuple(item.estimated_shift for item in shifts) == (0.0, 20.0)
    assert tuple(item.applied_shift for item in shifts) == (0.0, 3.0)
    assert result.stages[0].pre_level_spread == pytest.approx(20.0)
    assert result.stages[0].post_level_spread == pytest.approx(17.0)


def test_insufficient_control_data_is_explicit_and_not_applied() -> None:
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.2", "control.a", 8.0),
        _value("sample.1", "biology", 3.0),
    )

    result = normalize(values, (_stage(minimum=2),))

    assert all(item.state is ShiftState.NOT_EVALUABLE for item in result.stages[0].level_shifts)
    assert result.values == values
    assert result.stages[0].pre_level_spread is None
    assert result.stages[0].post_level_spread is None


def test_stages_are_sequential_and_replayable() -> None:
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.2", "control.a", 8.0),
    )
    first = _stage(cap=1.0)
    second = NormalizationStage(
        stage_id="stage.platform",
        factor_id="platform",
        reference_level_id="batch.a",
        control_feature_ids=("control.a",),
        levels_by_target=first.levels_by_target,
        maximum_absolute_shift=10.0,
    )

    result = normalize(values, (first, second))

    assert tuple(item.value for item in result.values) == (12.0, 12.0)
    assert tuple(item.post_level_spread for item in result.stages) == (3.0, 0.0)


def test_input_order_does_not_change_estimates() -> None:
    values = (
        _value("sample.1", "control.a", 12.0),
        _value("sample.1", "control.b", 22.0),
        _value("sample.2", "control.a", 8.0),
        _value("sample.2", "control.b", 18.0),
    )

    forward = normalize(values, (_stage(),))
    reverse = normalize(tuple(reversed(values)), (_stage(),))

    assert forward.stages == reverse.stages
    assert {(item.target_id, item.feature_id, item.value) for item in forward.values} == {
        (item.target_id, item.feature_id, item.value) for item in reverse.values
    }


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            (
                ScalarValue("sample.1", "feature.a", ValueState.OBSERVED, 1.0),
                ScalarValue("sample.1", "feature.a", ValueState.OBSERVED, 2.0),
            ),
            "must be unique",
        ),
        ((ScalarValue("sample.1", "feature.a", ValueState.OBSERVED),), "must be finite"),
        (
            (ScalarValue("sample.1", "feature.a", ValueState.MISSING, 0.0),),
            "cannot carry",
        ),
    ],
)
def test_invalid_value_shapes_fail_closed(
    values: tuple[ScalarValue, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize(values, ())


def test_invalid_stage_configuration_fails_closed() -> None:
    stage = NormalizationStage(
        stage_id="stage.bad",
        factor_id="batch",
        reference_level_id="batch.a",
        control_feature_ids=(),
        levels_by_target={},
        maximum_absolute_shift=1.0,
    )

    with pytest.raises(ValueError, match="control features"):
        normalize((), (stage,))
