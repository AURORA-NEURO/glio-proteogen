"""Adversarial checks for the provisional M06-05 contract spine."""

import pytest

from glio_proteogen.contracts.m06_05 import (
    M0605_MAX_EVIDENCE,
    M0605_OUTPUT_MEDIA_TYPE,
    ConstraintAblationRecord,
    ConstraintAwareEstimate,
    ConstraintEvaluation,
    ConstraintEvaluationOutcome,
    ConstraintIntegrationReplayReason,
    ConstraintIntegrationStatus,
    IntegrateProteinAbundanceConstraintsVerification,
    MechanismConstraint,
    MechanismConstraintHardness,
    MechanismConstraintKind,
    MechanismConstraintSet,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7
_WITH_EFFECT = 0.8
_WITHOUT_EFFECT = 0.5
_DELTA = _WITH_EFFECT - _WITHOUT_EFFECT


def test_constraint_set_keeps_hard_and_soft_controls_explicit() -> None:
    hard = MechanismConstraint(
        constraint_id="constraint.nonnegative",
        version="0.1.0",
        kind=MechanismConstraintKind.CHEMISTRY,
        hardness=MechanismConstraintHardness.HARD,
        expression="abundance >= 0",
        feature_ids=("protein.abundance",),
    )
    soft = MechanismConstraint(
        constraint_id="constraint.pathway",
        version="0.1.0",
        kind=MechanismConstraintKind.GRAPH,
        hardness=MechanismConstraintHardness.SOFT,
        expression="pathway coherence is favored",
        feature_ids=("protein.abundance",),
        weight=0.5,
    )
    constraint_set = MechanismConstraintSet(
        constraint_set_id="constraint-set.reviewed",
        version="0.1.0",
        constraints=(hard, soft),
        reviewed_by="reviewer.constraints",
    )
    assert {item.hardness for item in constraint_set.constraints} == {
        MechanismConstraintHardness.HARD,
        MechanismConstraintHardness.SOFT,
    }


def test_soft_constraint_ablation_delta_is_checked() -> None:
    record = ConstraintAblationRecord(
        constraint_id="constraint.pathway",
        with_constraint_effect=_WITH_EFFECT,
        without_constraint_effect=_WITHOUT_EFFECT,
        effect_delta=_DELTA,
    )
    assert record.effect_delta == _DELTA


def test_schema_exports_are_provisional_and_bounded() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0605_OUTPUT_MEDIA_TYPE
    assert M0605_MAX_EVIDENCE > 0


def _hard() -> MechanismConstraint:
    return MechanismConstraint(
        constraint_id="constraint.nonnegative",
        version="0.1.0",
        kind=MechanismConstraintKind.CHEMISTRY,
        hardness=MechanismConstraintHardness.HARD,
        expression="abundance >= 0",
        feature_ids=("protein.abundance",),
    )


def _soft() -> MechanismConstraint:
    return MechanismConstraint(
        constraint_id="constraint.pathway",
        version="0.1.0",
        kind=MechanismConstraintKind.GRAPH,
        hardness=MechanismConstraintHardness.SOFT,
        expression="pathway coherence is favored",
        feature_ids=("protein.abundance",),
        weight=0.5,
    )


def test_hard_constraint_rejects_weight() -> None:
    with pytest.raises(ValueError, match="hard constraint"):
        MechanismConstraint(
            constraint_id="constraint.bad",
            version="0.1.0",
            kind=MechanismConstraintKind.CHEMISTRY,
            hardness=MechanismConstraintHardness.HARD,
            expression="x >= 0",
            feature_ids=("x",),
            weight=0.2,
        )


def test_soft_constraint_requires_weight() -> None:
    with pytest.raises(ValueError, match="soft constraint requires"):
        MechanismConstraint(
            constraint_id="constraint.bad",
            version="0.1.0",
            kind=MechanismConstraintKind.GRAPH,
            hardness=MechanismConstraintHardness.SOFT,
            expression="x is coherent",
            feature_ids=("x",),
        )


def test_constraint_feature_ids_are_unique() -> None:
    with pytest.raises(ValueError, match="feature ids"):
        MechanismConstraint(
            constraint_id="constraint.bad",
            version="0.1.0",
            kind=MechanismConstraintKind.GRAPH,
            hardness=MechanismConstraintHardness.SOFT,
            expression="x is coherent",
            feature_ids=("x", "x"),
            weight=0.5,
        )


def test_constraint_set_ids_are_unique() -> None:
    duplicate = _hard().model_copy(update={"constraint_id": "constraint.other"})
    with pytest.raises(ValueError, match="constraint ids"):
        MechanismConstraintSet(
            constraint_set_id="set.bad",
            version="0.1.0",
            constraints=(_hard(), _hard()),
            reviewed_by="reviewer.constraints",
        )
    assert duplicate.constraint_id == "constraint.other"


def test_ablation_delta_must_be_with_minus_without() -> None:
    with pytest.raises(ValueError, match="effect delta"):
        ConstraintAblationRecord(
            constraint_id="constraint.pathway",
            with_constraint_effect=0.8,
            without_constraint_effect=0.5,
            effect_delta=0.4,
        )


@pytest.mark.parametrize(
    "outcome",
    [ConstraintEvaluationOutcome.SATISFIED, ConstraintEvaluationOutcome.VIOLATED],
)
def test_positive_evaluation_requires_numeric_result(outcome: ConstraintEvaluationOutcome) -> None:
    with pytest.raises(ValueError, match="numeric result"):
        ConstraintEvaluation(
            constraint_id="constraint.x",
            outcome=outcome,
            message="no measurement",
        )


def test_non_evaluable_evaluation_rejects_numeric_result() -> None:
    with pytest.raises(ValueError, match="cannot carry"):
        ConstraintEvaluation(
            constraint_id="constraint.x",
            outcome=ConstraintEvaluationOutcome.NOT_EVALUABLE,
            residual=0.0,
            message="not supported",
        )


def test_estimate_bounds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="bounds"):
        ConstraintAwareEstimate(
            feature_id="protein.abundance",
            unit="normalized-abundance",
            estimate_value=0.2,
            lower_bound=1.0,
            upper_bound=0.0,
        )


def test_estimate_must_lie_inside_bounds() -> None:
    with pytest.raises(ValueError, match="within"):
        ConstraintAwareEstimate(
            feature_id="protein.abundance",
            unit="normalized-abundance",
            estimate_value=2.0,
            lower_bound=0.0,
            upper_bound=1.0,
        )


def test_failed_replay_cannot_expose_digest() -> None:
    with pytest.raises(ValueError, match="trusted result digest"):
        # Verification closure is intentionally impossible to bypass with a stale digest.
        IntegrateProteinAbundanceConstraintsVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest="sha256:" + "a" * 64,
            reason=ConstraintIntegrationReplayReason.DIGEST_MISMATCH,
        )


def test_verified_replay_requires_verified_reason() -> None:
    with pytest.raises(ValueError, match="verified reason"):
        IntegrateProteinAbundanceConstraintsVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            result_digest="sha256:" + "a" * 64,
            reason=ConstraintIntegrationReplayReason.DIGEST_MISMATCH,
        )


def test_verification_cannot_claim_true_without_both_checks() -> None:
    with pytest.raises(ValueError, match="content and deterministic"):
        IntegrateProteinAbundanceConstraintsVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            reason=ConstraintIntegrationReplayReason.VERIFIED,
        )


def test_status_enum_remains_explicit() -> None:
    assert ConstraintIntegrationStatus.INTEGRATED.value == "integrated"
