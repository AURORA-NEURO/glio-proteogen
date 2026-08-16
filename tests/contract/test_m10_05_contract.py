"""Focused contract/schema smoke for provisional M10-05."""

import pytest

from glio_proteogen.contracts.m10_05 import (
    M1005_MAX_EVIDENCE,
    M1005_OUTPUT_MEDIA_TYPE,
    ConstraintAblation,
    ConstraintHardness,
    ConstraintKind,
    MechanismConstraint,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_constraint_ablation_metadata() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["softConstraintAblationRequired"] for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1005_OUTPUT_MEDIA_TYPE
    assert M1005_MAX_EVIDENCE > 0


def test_hard_soft_constraint_semantics_and_ablation_delta() -> None:
    with pytest.raises(ValueError, match="soft weight"):
        MechanismConstraint(
            constraint_id="constraint.hard",
            kind=ConstraintKind.BIOLOGICAL_PRIOR,
            hardness=ConstraintHardness.HARD,
            expression="x >= 0",
            feature_ids=("feature.x",),
            weight=0.5,
        )
    ablation = ConstraintAblation(
        constraint_id="constraint.soft",
        with_constraint_effect=0.8,
        without_constraint_effect=0.5,
        effect_delta=0.3,
    )
    assert ablation.effect_delta == pytest.approx(0.3)
