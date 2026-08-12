"""Focused tests for the pure M02-01 conformance kernel."""

from __future__ import annotations

import pytest

from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    FieldDefinition,
    FieldObservation,
    ObservationState,
    ProtocolRule,
    ResultState,
    RuleKind,
    validate_protocol,
)


def _fields() -> tuple[FieldDefinition, ...]:
    return (
        FieldDefinition("acquisition_mode", required=True, min_items=1),
        FieldDefinition("precursor_tolerance", required=True, min_items=1, unit_id="ppm"),
        FieldDefinition(
            "label_reagent", required=False, allow_not_applicable=True
        ),
    )


def _rules() -> tuple[ProtocolRule, ...]:
    return (
        ProtocolRule(
            "rule.acquisition",
            "acquisition_mode",
            RuleKind.TERM_IN_SET,
            "acquisition_mode_unsupported",
            allowed_terms=("dda", "dia"),
        ),
        ProtocolRule(
            "rule.tolerance",
            "precursor_tolerance",
            RuleKind.NUMERIC_RANGE,
            "precursor_tolerance_out_of_range",
            minimum=0.0,
            maximum=50.0,
        ),
    )


def _observations() -> tuple[FieldObservation, ...]:
    return (
        FieldObservation("acquisition_mode", ObservationState.OBSERVED, ("dia",)),
        FieldObservation(
            "precursor_tolerance", ObservationState.OBSERVED, (10.0,), "ppm"
        ),
        FieldObservation("label_reagent", ObservationState.NOT_APPLICABLE),
    )


def test_valid_metadata_is_order_independent_and_conformant() -> None:
    result = validate_protocol(_fields(), _observations(), _rules())
    replay = validate_protocol(
        tuple(reversed(_fields())),
        tuple(reversed(_observations())),
        tuple(reversed(_rules())),
    )

    assert result == replay
    assert result.state is ResultState.CONFORMANT
    assert not result.quarantined


@pytest.mark.parametrize(
    "state",
    [ObservationState.MISSING, ObservationState.UNKNOWN, ObservationState.CONFLICTING],
)
def test_unresolved_required_state_is_indeterminate_never_negative(
    state: ObservationState,
) -> None:
    observations = (
        FieldObservation("acquisition_mode", state),
        *_observations()[1:],
    )

    result = validate_protocol(_fields(), observations, _rules())

    assert result.state is ResultState.INDETERMINATE
    assert result.quarantined
    assert result.human_review_required
    assert f"field_{state.value}" in result.reason_codes


def test_exact_unit_mismatch_is_not_converted() -> None:
    observations = (
        _observations()[0],
        FieldObservation(
            "precursor_tolerance", ObservationState.OBSERVED, (0.01,), "dalton"
        ),
        _observations()[2],
    )

    result = validate_protocol(_fields(), observations, _rules())

    assert result.state is ResultState.NONCONFORMANT
    assert "unit_mismatch" in result.reason_codes


def test_unsupported_term_and_range_are_explicit() -> None:
    observations = (
        FieldObservation("acquisition_mode", ObservationState.OBSERVED, ("other",)),
        FieldObservation(
            "precursor_tolerance", ObservationState.OBSERVED, (100.0,), "ppm"
        ),
        _observations()[2],
    )

    result = validate_protocol(_fields(), observations, _rules())

    assert result.reason_codes == (
        "acquisition_mode_unsupported",
        "precursor_tolerance_out_of_range",
    )


def test_duplicate_or_unknown_fields_fail_closed() -> None:
    duplicate = (_observations()[0], _observations()[0])
    with pytest.raises(ValueError, match="unique"):
        validate_protocol(_fields(), duplicate, _rules())
    with pytest.raises(ValueError, match="undefined"):
        validate_protocol(
            _fields(),
            (*_observations(), FieldObservation("unknown", ObservationState.OBSERVED)),
            _rules(),
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        (FieldDefinition("bad", required=False, min_items=-1), "cardinality"),
        (FieldDefinition("bad", required=False, max_items=0), "cardinality"),
        (
            FieldDefinition("bad", required=False, min_items=2, max_items=1),
            "cardinality",
        ),
        (FieldDefinition("bad", required=True, min_items=0), "positive minimum"),
        (
            FieldDefinition(
                "bad", required=True, min_items=1, allow_not_applicable=True
            ),
            "cannot allow",
        ),
    ],
)
def test_invalid_field_definitions_fail_closed(
    field: FieldDefinition,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_protocol((field,), (), ())


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        (
            ProtocolRule(
                "rule.missing", "absent", RuleKind.TERM_IN_SET, "bad"
            ),
            "undefined fields",
        ),
        (
            ProtocolRule(
                "rule.term", "field", RuleKind.TERM_IN_SET, "bad"
            ),
            "unique allowed terms",
        ),
        (
            ProtocolRule(
                "rule.term",
                "field",
                RuleKind.TERM_IN_SET,
                "bad",
                allowed_terms=("a", "a"),
            ),
            "unique allowed terms",
        ),
        (
            ProtocolRule(
                "rule.range", "field", RuleKind.NUMERIC_RANGE, "bad"
            ),
            "require a bound",
        ),
        (
            ProtocolRule(
                "rule.range",
                "field",
                RuleKind.NUMERIC_RANGE,
                "bad",
                minimum=2.0,
                maximum=1.0,
            ),
            "ordered",
        ),
        (
            ProtocolRule(
                "rule.boolean", "field", RuleKind.BOOLEAN_EQUALS, "bad"
            ),
            "expected value",
        ),
    ],
)
def test_invalid_rules_fail_closed(rule: ProtocolRule, message: str) -> None:
    field = FieldDefinition("field", required=False)
    with pytest.raises(ValueError, match=message):
        validate_protocol((field,), (), (rule,))


def test_duplicate_definitions_and_rules_fail_closed() -> None:
    field = FieldDefinition("field", required=False)
    rule = ProtocolRule(
        "rule.term",
        "field",
        RuleKind.TERM_IN_SET,
        "bad",
        allowed_terms=("a",),
    )
    with pytest.raises(ValueError, match="definitions must have unique"):
        validate_protocol((field, field), (), ())
    with pytest.raises(ValueError, match="rule identifiers must be unique"):
        validate_protocol((field,), (), (rule, rule))


def test_optional_absence_and_explicit_not_applicable_are_distinct() -> None:
    optional = FieldDefinition("optional", required=False)
    optional_absent = validate_protocol((optional,), (), ())
    disallowed = validate_protocol(
        (optional,),
        (FieldObservation("optional", ObservationState.NOT_APPLICABLE),),
        (),
    )

    assert optional_absent.state is ResultState.CONFORMANT
    assert disallowed.state is ResultState.NONCONFORMANT
    assert disallowed.reason_codes == ("not_applicable_not_allowed",)


def test_boolean_and_open_numeric_rules_are_exact() -> None:
    fields = (
        FieldDefinition("enabled", required=True, min_items=1),
        FieldDefinition("score", required=True, min_items=1),
    )
    rules = (
        ProtocolRule(
            "rule.enabled",
            "enabled",
            RuleKind.BOOLEAN_EQUALS,
            "enabled_mismatch",
            expected_bool=True,
        ),
        ProtocolRule(
            "rule.score",
            "score",
            RuleKind.NUMERIC_RANGE,
            "score_too_large",
            maximum=10.0,
        ),
    )
    invalid = validate_protocol(
        fields,
        (
            FieldObservation("enabled", ObservationState.OBSERVED, (False,)),
            FieldObservation("score", ObservationState.OBSERVED, (True,)),
        ),
        rules,
    )
    valid = validate_protocol(
        fields,
        (
            FieldObservation("enabled", ObservationState.OBSERVED, (True,)),
            FieldObservation("score", ObservationState.OBSERVED, (-100.0,)),
        ),
        rules,
    )

    assert invalid.reason_codes == ("enabled_mismatch", "score_too_large")
    assert valid.state is ResultState.CONFORMANT


def test_cardinality_mismatch_is_explicit() -> None:
    field = FieldDefinition("items", required=True, min_items=1, max_items=1)
    observation = FieldObservation(
        "items", ObservationState.OBSERVED, ("a", "b")
    )

    result = validate_protocol((field,), (observation,), ())

    assert result.reason_codes == ("cardinality_mismatch",)
