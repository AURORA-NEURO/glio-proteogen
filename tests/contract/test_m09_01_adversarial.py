"""Negative and boundary coverage for the M09-01 contract closure."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m09_01 import (
    ComplexActivityCompatibilityRule,
    ComplexActivityConstraint,
    ComplexActivityFeatureDefinition,
    ComplexActivityFeatureValue,
    ComplexActivityFeatureValueKind,
    ComplexActivityInvariant,
    ComplexActivityInvariantSeverity,
    ComplexActivityMigrationRule,
    ComplexActivityMissingness,
    FormalComplexActivityStateSchema,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    M0901AuthorizationError,
    M0901FormalStateEngine,
    M0901FormalStateKernel,
    M0901Plugin,
    M0901Service,
)
from glio_proteogen.modules.c09_complex_stoichiometry.m09_01_formal_state_feature_schema import (
    engine as m0901_engine,
)
from tests.modules.c09_complex_stoichiometry.test_m09_01_formal_state import _request


def _definition(
    value_kind: ComplexActivityFeatureValueKind = ComplexActivityFeatureValueKind.SCALAR,
    *,
    categories: tuple[str, ...] = (),
    domain_lower: float | None = 0.0,
    domain_upper: float | None = 1.0,
    allowed_missingness: tuple[ComplexActivityMissingness, ...] = (
        ComplexActivityMissingness.OBSERVED,
        ComplexActivityMissingness.MISSING,
    ),
) -> ComplexActivityFeatureDefinition:
    return ComplexActivityFeatureDefinition(
        feature_id="feature.activity",
        version="0.1.0",
        value_kind=value_kind,
        unit="activity",
        allowed_missingness=allowed_missingness,
        domain_lower=domain_lower,
        domain_upper=domain_upper,
        allowed_categories=categories,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "allowed_missingness": (
                    ComplexActivityMissingness.OBSERVED,
                    ComplexActivityMissingness.OBSERVED,
                )
            },
            "missingness",
        ),
        ({"domain_lower": 2.0, "domain_upper": 1.0}, "lower bound"),
        ({"value_kind": "categorical"}, "categorical feature requires"),
        (
            {
                "value_kind": "categorical",
                "categories": ("low",),
                "domain_lower": 0.0,
            },
            "categorical feature cannot",
        ),
        ({"categories": ("low", "low")}, "categories"),
    ],
)
def test_feature_definition_closure_rejects_invalid_domains(
    kwargs: dict[str, object],
    message: str,
) -> None:
    if "value_kind" in kwargs and isinstance(kwargs["value_kind"], str):
        kwargs["value_kind"] = ComplexActivityFeatureValueKind(kwargs["value_kind"])
    with pytest.raises((ValidationError, ValueError), match=message):
        _definition(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            {"scalar_value": 0.5, "category": "high"},
            "exactly one",
        ),
        (
            {"interval_lower": 0.2},
            "ordered bounds",
        ),
        (
            {"interval_lower": 0.9, "interval_upper": 0.1},
            "ordered bounds",
        ),
        (
            {"scalar_value": 0.5},
            "non-observed",
        ),
    ],
)
def test_feature_value_shape_closure(
    value: dict[str, object],
    message: str,
) -> None:
    state = (
        ComplexActivityMissingness.MISSING
        if message == "non-observed"
        else ComplexActivityMissingness.OBSERVED
    )
    with pytest.raises((ValidationError, ValueError), match=message):
        ComplexActivityFeatureValue(
            feature_id="feature.activity",
            state=state,
            unit="activity",
            **value,
        )


def test_feature_value_rejects_nonfinite() -> None:
    with pytest.raises(ValidationError):
        ComplexActivityFeatureValue(
            feature_id="feature.activity",
            state=ComplexActivityMissingness.OBSERVED,
            unit="activity",
            scalar_value=math.inf,
        )


def test_feature_value_accepts_interval_categorical_and_vector_shapes() -> None:
    interval = ComplexActivityFeatureValue(
        feature_id="feature.activity",
        state=ComplexActivityMissingness.OBSERVED,
        unit="activity",
        interval_lower=0.2,
        interval_upper=0.8,
    )
    categorical = ComplexActivityFeatureValue(
        feature_id="feature.activity",
        state=ComplexActivityMissingness.OBSERVED,
        unit="activity",
        category="high",
    )
    vector = ComplexActivityFeatureValue(
        feature_id="feature.activity",
        state=ComplexActivityMissingness.OBSERVED,
        unit="activity",
        vector=(0.2, 0.8),
    )

    assert interval.interval_upper == 0.8  # noqa: PLR2004
    assert categorical.category == "high"
    assert vector.vector == (0.2, 0.8)


def test_invariant_and_constraint_ids_are_unique() -> None:
    with pytest.raises(ValidationError, match="invariant feature ids"):
        ComplexActivityInvariant(
            invariant_id="invariant",
            expression="all_values_observed",
            severity=ComplexActivityInvariantSeverity.ERROR,
            feature_ids=("feature.activity", "feature.activity"),
        )
    with pytest.raises(ValidationError, match="constraint feature ids"):
        ComplexActivityConstraint(
            constraint_id="constraint",
            expression="feature:feature.activity >= 0",
            hard=True,
            feature_ids=("feature.activity", "feature.activity"),
        )
    with pytest.raises(ValidationError, match="bounded feature"):
        ComplexActivityConstraint(
            constraint_id="constraint",
            expression="python:unsafe",
            hard=True,
            feature_ids=("feature.activity",),
        )


def test_compatibility_and_migration_require_distinct_versions() -> None:
    with pytest.raises(ValidationError, match="compatibility"):
        ComplexActivityCompatibilityRule(
            rule_id="compatibility",
            source_version="1.0.0",
            target_version="1.0.0",
            expression="same",
        )
    with pytest.raises(ValidationError, match="migration"):
        ComplexActivityMigrationRule(
            source_version="1.0.0",
            target_version="1.0.0",
            mapped_feature_ids=("feature.activity",),
            lossy=False,
        )


def test_schema_rejects_duplicate_rules_and_unknown_migration_features() -> None:
    feature = _definition()
    compatibility = ComplexActivityCompatibilityRule(
        rule_id="compatibility.one",
        source_version="1.0.0",
        target_version="2.0.0",
        expression="same",
    )
    with pytest.raises(ValidationError, match="unique version pairs"):
        FormalComplexActivityStateSchema(
            schema_id="schema",
            version="1.0.0",
            features=(feature,),
            compatibility_rules=(
                compatibility,
                compatibility.model_copy(update={"rule_id": "compatibility.two"}),
            ),
        )
    migration = ComplexActivityMigrationRule(
        source_version="1.0.0",
        target_version="2.0.0",
        mapped_feature_ids=("unknown.feature",),
        lossy=True,
    )
    with pytest.raises(ValidationError, match="unknown feature"):
        FormalComplexActivityStateSchema(
            schema_id="schema",
            version="1.0.0",
            features=(feature,),
            migrations=(migration,),
        )


def test_schema_rejects_duplicate_features_and_unknown_constraints() -> None:
    feature = _definition()
    constraint = ComplexActivityConstraint(
        constraint_id="constraint.unknown",
        expression="feature:unknown.feature >= 0",
        hard=True,
        feature_ids=("unknown.feature",),
    )
    with pytest.raises(ValidationError, match="feature ids"):
        FormalComplexActivityStateSchema(
            schema_id="schema",
            version="1.0.0",
            features=(feature, feature.model_copy(update={"unit": "different"})),
        )
    with pytest.raises(ValidationError, match="unknown feature"):
        FormalComplexActivityStateSchema(
            schema_id="schema",
            version="1.0.0",
            features=(feature,),
            constraints=(constraint,),
        )


def test_bounded_constraint_and_scalar_category_domain_are_closed() -> None:
    assert ComplexActivityConstraint(
        constraint_id="constraint.valid",
        expression="feature:feature.activity >= 0",
        hard=True,
        feature_ids=("feature.activity",),
    ).hard
    with pytest.raises(ValidationError, match="non-categorical"):
        _definition(categories=("low",))


def test_kernel_all_values_observed_and_operator_paths() -> None:
    value = ComplexActivityFeatureValue(
        feature_id="feature.activity",
        state=ComplexActivityMissingness.OBSERVED,
        unit="activity",
        scalar_value=0.5,
    )
    values = {"feature.activity": value}
    kernel = M0901FormalStateKernel()
    for label, operator in (("ge", ">="), ("le", "<="), ("eq", "=="), ("gt", ">"), ("lt", "<")):
        invariant = ComplexActivityInvariant(
            invariant_id=f"invariant.{label}",
            expression=f"feature:feature.activity {operator} 0.5",
            severity=ComplexActivityInvariantSeverity.ERROR,
            feature_ids=("feature.activity",),
        )
        assert kernel.evaluate_invariant(invariant, values)[0].value in {
            "satisfied",
            "violated",
        }
    observed = ComplexActivityInvariant(
        invariant_id="invariant.observed",
        expression="all_values_observed",
        severity=ComplexActivityInvariantSeverity.ERROR,
        feature_ids=("feature.activity",),
    )
    assert kernel.evaluate_invariant(observed, values)[0].value == "satisfied"
    missing = value.model_copy(update={"state": ComplexActivityMissingness.MISSING})
    assert (
        kernel.evaluate_invariant(observed, {"feature.activity": missing})[0].value
        == "not_evaluable"
    )
    unknown = observed.model_copy(
        update={
            "invariant_id": "invariant.unknown",
            "expression": "feature:unknown.feature >= 0",
            "feature_ids": ("unknown.feature",),
        }
    )
    assert kernel.evaluate_invariant(unknown, values)[0].value == "not_evaluable"


def test_engine_validate_entrypoints_and_result_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    engine = M0901FormalStateEngine()
    assert engine.validate(request).result.status.value == "valid"
    with pytest.raises(TypeError, match="validated request"):
        engine.validate_validated(object())  # type: ignore[arg-type]
    monkeypatch.setattr(m0901_engine, "M0901_MAX_CANONICAL_RESULT_BYTES", 1)
    with pytest.raises(ValueError, match="result"):
        engine.validate_validated(request)


def test_engine_replay_mismatch_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    first = M0901FormalStateEngine().validate(_request())
    second = M0901FormalStateEngine().validate(_request(value=0.25))
    assert (
        m0901_engine.validate_complex_activity_formal_state(_request()).result.status.value
        == "valid"
    )
    mismatch = M0901FormalStateEngine.verify(first.result, second.canonical_bytes)
    assert not mismatch.verified
    monkeypatch.setattr(
        m0901_engine,
        "canonical_request_digest",
        lambda _value: "sha256:" + ("b" * 64),
    )
    request_mismatch = M0901FormalStateEngine.verify(first.result, first.canonical_bytes)
    assert not request_mismatch.verified
    monkeypatch.setattr(
        m0901_engine,
        "canonical_request_digest",
        lambda _value: first.result.request_digest,
    )
    monkeypatch.setattr(
        m0901_engine,
        "result_payload_digest",
        lambda _value: "sha256:" + ("c" * 64),
    )
    result_mismatch = M0901FormalStateEngine.verify(first.result, first.canonical_bytes)
    assert not result_mismatch.verified


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"values": (_request().values[0], _request().values[0])}, "unique"),
        ({"values": ()}, "at least 1"),
        (
            {
                "values": (
                    ComplexActivityFeatureValue(
                        feature_id="complex.activity.scalar",
                        state=ComplexActivityMissingness.OBSERVED,
                        unit="wrong",
                        scalar_value=0.5,
                    ),
                )
            },
            "unit",
        ),
        (
            {
                "values": (
                    ComplexActivityFeatureValue(
                        feature_id="complex.activity.scalar",
                        state=ComplexActivityMissingness.OBSERVED,
                        unit="activity",
                        scalar_value=-0.1,
                    ),
                )
            },
            "outside",
        ),
    ],
)
def test_request_domain_closure(update: dict[str, object], message: str) -> None:
    with pytest.raises((ValidationError, ValueError), match=message):
        M0901Service().validate_request(_request().model_copy(update=update))


def test_authorization_and_json_size_guards_fail_closed() -> None:
    request = _request()
    rejected_context = request.context.model_copy(
        update={
            "references": request.context.references.model_copy(
                update={
                    "support": request.context.references.support.model_copy(
                        update={"state": "rejected"}
                    )
                }
            )
        }
    )
    with pytest.raises(M0901AuthorizationError):
        m0901_engine.preflight_formal_state_authorization(
            request.model_copy(update={"context": rejected_context})
        )
    with pytest.raises(M0901AuthorizationError):
        m0901_engine.preflight_formal_state_authorization(object())
    with pytest.raises(M0901AuthorizationError):
        m0901_engine._validate_json_request({}, b"{}")
    with pytest.raises(ValueError, match="byte limit"):
        m0901_engine._validate_json_request({}, b"{}" * 3_000_000)


def test_plugin_json_path_and_replay_invalid_mapping() -> None:
    request = _request()
    plugin = M0901Plugin(M0901Service())
    encoded = request.model_dump_json()
    token = plugin.validate(encoded)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M09-01"
    assert plugin.run(token).result.status.value == "valid"
    invalid = M0901FormalStateEngine.verify({"bad": "result"}, b"{}")
    assert not invalid.verified
