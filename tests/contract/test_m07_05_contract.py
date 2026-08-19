"""Lightweight checks for the provisional M07-05 contract spine."""

from typing import Any, cast

import pytest

from glio_proteogen.contracts.m07_05 import (
    M0705_MAX_EVIDENCE,
    M0705_OUTPUT_MEDIA_TYPE,
    ProteotypeConstraintAblation,
    ProteotypeConstraintEvaluation,
    ProteotypeConstraintEvaluationOutcome,
    ProteotypeConstraintHardness,
    ProteotypeConstraintKind,
    ProteotypeMechanismConstraint,
    ProteotypeMechanismConstraintSet,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7
_WITH_EFFECT = 0.8
_WITHOUT_EFFECT = 0.5
_DELTA = _WITH_EFFECT - _WITHOUT_EFFECT


def test_proteotype_constraint_set_keeps_hard_and_soft_controls_explicit() -> None:
    hard = ProteotypeMechanismConstraint(
        constraint_id="constraint.nonnegative",
        version="0.1.0",
        kind=ProteotypeConstraintKind.CHEMISTRY,
        hardness=ProteotypeConstraintHardness.HARD,
        expression="abundance >= 0",
        feature_ids=("feature.proteotype",),
    )
    soft = ProteotypeMechanismConstraint(
        constraint_id="constraint.pathway",
        version="0.1.0",
        kind=ProteotypeConstraintKind.GRAPH,
        hardness=ProteotypeConstraintHardness.SOFT,
        expression="pathway coherence is favored",
        feature_ids=("feature.proteotype",),
        weight=0.5,
    )
    constraint_set = ProteotypeMechanismConstraintSet(
        constraint_set_id="constraint-set.reviewed",
        version="0.1.0",
        constraints=(hard, soft),
        reviewed_by="reviewer.constraints",
    )
    assert {item.hardness for item in constraint_set.constraints} == {
        ProteotypeConstraintHardness.HARD,
        ProteotypeConstraintHardness.SOFT,
    }


def test_soft_constraint_ablation_delta_is_checked() -> None:
    record = ProteotypeConstraintAblation(
        constraint_id="constraint.pathway",
        with_constraint_effect=_WITH_EFFECT,
        without_constraint_effect=_WITHOUT_EFFECT,
        effect_delta=_DELTA,
    )
    assert record.effect_delta == _DELTA


def test_non_evaluable_constraint_cannot_carry_numeric_evidence() -> None:
    with pytest.raises(ValueError, match="cannot carry a numeric result"):
        ProteotypeConstraintEvaluation(
            constraint_id="constraint.missing",
            outcome=ProteotypeConstraintEvaluationOutcome.NOT_EVALUABLE,
            residual=0.0,
            message="feature artifact is unavailable",
        )


def test_schema_exports_are_provisional_and_bounded() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    metadata = [cast("dict[str, Any]", schema["x-glio-contract"]) for schema in schemas.values()]
    assert all(item["provisionalAbi"] for item in metadata)
    output_metadata = cast("dict[str, Any]", schemas["output"]["x-glio-contract"])
    assert output_metadata["outputMediaType"] == M0705_OUTPUT_MEDIA_TYPE
    assert M0705_MAX_EVIDENCE > 0
