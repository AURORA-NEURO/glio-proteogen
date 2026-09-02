"""Focused contract/schema smoke for provisional M10-05."""

# Constraint values are intentionally literal fixtures.
# ruff: noqa: PLR2004

import pytest

from glio_proteogen.contracts.m10_05 import (
    M1005_MAX_EVIDENCE,
    M1005_OUTPUT_MEDIA_TYPE,
    ConstraintAblation,
    ConstraintHardness,
    ConstraintKind,
    FeatureObservation,
    FeatureObservationState,
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


def test_feature_observation_closes_missing_and_censored_shapes() -> None:
    observed = FeatureObservation(
        feature_id="feature.x",
        state=FeatureObservationState.OBSERVED,
        value=0.25,
        standard_error=0.05,
    )
    censored = FeatureObservation(
        feature_id="feature.y",
        state=FeatureObservationState.LEFT_CENSORED,
        censoring_limit=0.1,
    )
    missing = FeatureObservation(feature_id="feature.z", state=FeatureObservationState.MISSING)
    assert observed.value == 0.25
    assert censored.censoring_limit == 0.1
    assert missing.value is None
    with pytest.raises(ValueError, match="observed feature"):
        FeatureObservation(
            feature_id="feature.bad",
            state=FeatureObservationState.OBSERVED,
            value=None,
        )
    with pytest.raises(ValueError, match="missing or unsupported"):
        FeatureObservation(
            feature_id="feature.bad",
            state=FeatureObservationState.UNSUPPORTED,
            value=1.0,
        )
