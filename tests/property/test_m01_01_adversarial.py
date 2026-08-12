"""Adversarial semantic-validation matrix for M01-01."""

from __future__ import annotations

import re

import pytest

from glio_proteogen.contracts.m01_01.v1 import (
    M0101_SCOPE_LIMITATION_CODE,
    Cardinality,
    CompatibilityPredicate,
    CompatibilityRule,
    ConformanceDecision,
    EvaluateMetadataRequest,
    FieldSpecification,
    IssueAction,
    IssueSeverity,
    MetadataEntry,
    NumericBounds,
    ObservedValue,
    PredicateOperator,
    UnitDefinition,
    UnresolvedValue,
    ValueKind,
)
from glio_proteogen.kernel.models import ConsentState, Limitation
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    validate_metadata,
    validate_protocol_schema,
)
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata import (
    validator as validator_module,
)
from tests.m01_01_support import load_protocol_schema, load_request

ISSUE_LIMIT = 256
MESSAGE_LIMIT = 512
EXPECTED_INDETERMINATE_RULES = 2


def _reference():
    schema = load_protocol_schema()
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    return schema, request.document


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        "\\",
        "[^]",
        "[[]",
        "^a^",
        "a$b",
        "a{",
        "a{3,2}",
        "a{1,2,3}",
        "a{99999}",
        "a??",
        "(a)",
        "^" + "a?" * 24 + "a" * 24 + "b$",
    ],
)
def test_unsafe_or_variable_length_patterns_quarantine_at_registration(pattern: str) -> None:
    schema = load_protocol_schema()
    field = schema.fields[0].model_copy(update={"pattern": pattern})
    candidate = schema.model_copy(update={"fields": (field, *schema.fields[1:])})

    report = validate_protocol_schema(candidate)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert "schema.pattern_unsafe" in {issue.code for issue in report.issues}


def test_syntactically_invalid_bounded_pattern_is_quarantined() -> None:
    schema = load_protocol_schema()
    field = schema.fields[0].model_copy(update={"pattern": "^[z-a]{2}$"})
    candidate = schema.model_copy(update={"fields": (field, *schema.fields[1:])})

    report = validate_protocol_schema(candidate)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert "schema.pattern_invalid" in {issue.code for issue in report.issues}


def test_semantic_limitation_guard_survives_unvalidated_model_copy() -> None:
    schema = load_protocol_schema()
    limitations = tuple(
        Limitation(code=f"limit{index}", statement=f"Synthetic limitation {index}.")
        for index in range(1_000)
    )
    reserved = Limitation(
        code=M0101_SCOPE_LIMITATION_CODE,
        statement="Synthetic attempt to claim the module scope ceiling.",
    )
    duplicate_reserved = reserved.model_copy(update={"statement": "Duplicate reserved code."})
    candidate = schema.model_copy(
        update={"limitations": (*limitations, reserved, duplicate_reserved)}
    )

    report = validate_protocol_schema(candidate)

    assert {issue.code for issue in report.issues} >= {
        "schema.limitation_capacity_exceeded",
        "schema.limitation_code_duplicate",
        "schema.limitation_code_reserved",
    }


def test_issue_collection_is_bounded_and_deterministically_truncated() -> None:
    schema, document = _reference()
    unknown_entries = tuple(
        MetadataEntry(
            path=f"/synthetic/unknown_{index:03d}",
            values=(ObservedValue(value=index),),
        )
        for index in range(300)
    )
    candidate = document.model_copy(update={"entries": (*document.entries, *unknown_entries)})

    report = validate_metadata(schema, candidate, consent_state=ConsentState.GRANTED)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert len(report.issues) == ISSUE_LIMIT
    assert "validation.issue_limit_reached" in {issue.code for issue in report.issues}


def test_duplicate_issues_are_deduplicated() -> None:
    schema, document = _reference()
    repeated_rule = schema.compatibility_rules[0]
    duplicated = schema.model_copy(update={"compatibility_rules": (repeated_rule, repeated_rule)})
    enriched = document.model_copy(update={"entries": document.entries[:2]})
    mode = enriched.entries[1].model_copy(
        update={"values": (ObservedValue(value="enriched"),)}
    )
    enriched = enriched.model_copy(update={"entries": (enriched.entries[0], mode)})

    report = validate_metadata(duplicated, enriched, consent_state=ConsentState.GRANTED)

    assert [issue.code for issue in report.issues] == ["compatibility.requirement_failed"]


def test_long_compatible_rule_message_is_bounded() -> None:
    schema, document = _reference()
    rule = schema.compatibility_rules[0].model_copy(update={"rule_id": "r" * 128})
    candidate = schema.model_copy(update={"compatibility_rules": (rule,)})
    enriched_mode = document.entries[1].model_copy(
        update={"values": (ObservedValue(value="enriched"),)}
    )
    candidate_document = document.model_copy(
        update={"entries": (document.entries[0], enriched_mode)}
    )

    report = validate_metadata(candidate, candidate_document, consent_state=ConsentState.GRANTED)

    assert all(len(issue.message) <= MESSAGE_LIMIT for issue in report.issues)


def test_defensive_message_truncation_is_exact_and_marked() -> None:
    message = "x" * (MESSAGE_LIMIT + 1)

    bounded = validator_module._bounded_message(message)

    assert len(bounded) == MESSAGE_LIMIT
    assert bounded.endswith("...")


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (r"^\d{2}$", "safe"),
        (r"^\q{2}$", "unsafe"),
        (r"^[\d]{2}$", "safe"),
        (r"^[\q]{2}$", "unsafe"),
        (r"^[abc", "unsafe"),
        (r"^{2}$", "unsafe"),
        (r"^a{2}{3}$", "unsafe"),
        ("^a{²}$", "unsafe"),
    ],
)
def test_regex_scanner_defensive_edges_are_total(pattern: str, expected: str) -> None:
    assert validator_module._is_bounded_pattern(pattern) is (expected == "safe")


def test_timestamp_parser_rejects_calendar_invalidity_after_shape_check() -> None:
    assert validator_module._valid_timestamp("2026-01-01T00:00:00Z") is True
    assert validator_module._valid_timestamp("2026-99-99T00:00:00Z") is False


def test_constraint_helpers_fail_closed_for_wrong_kinds_and_absent_bounds() -> None:
    numeric_field = load_protocol_schema().fields[2]
    collector = validator_module._IssueCollector()
    assert validator_module._validate_numeric_bounds(
        numeric_field,
        ObservedValue(value=True),
        0,
        collector,
    ) is False
    assert validator_module._validate_numeric_bounds(
        numeric_field.model_copy(update={"numeric_bounds": None}),
        ObservedValue(value=1.0, unit="ug"),
        0,
        collector,
    ) is True
    assert validator_module._validate_pattern(
        load_protocol_schema().fields[0],
        123,
        0,
        re.compile(r"^[A-Z]{2}$"),
        collector,
    ) is False


def test_required_and_minimum_cardinality_absence_have_distinct_codes() -> None:
    schema, document = _reference()
    required = FieldSpecification(
        path="/synthetic/required",
        title="Synthetic required field",
        description="Required-field branch evidence.",
        value_kind=ValueKind.TEXT,
        required=True,
        cardinality=Cardinality(minimum=1, maximum=1),
    )
    minimum = required.model_copy(
        update={"path": "/synthetic/minimum", "required": False}
    )
    candidate = schema.model_copy(update={"fields": (*schema.fields, required, minimum)})

    report = validate_metadata(candidate, document, consent_state=ConsentState.GRANTED)

    assert {issue.code for issue in report.issues} >= {
        "field.required_missing",
        "field.cardinality_below_minimum",
    }


def test_entry_cardinality_reports_identity_minimum_and_maximum_failures() -> None:
    schema, document = _reference()
    duplicate_identity = document.entries[0].model_copy(
        update={
            "values": (
                ObservedValue(value="SYN-001"),
                ObservedValue(value="SYN-002"),
            )
        }
    )
    single_value_field = FieldSpecification(
        path="/synthetic/singular",
        title="Synthetic singular field",
        description="Cardinality branch evidence.",
        value_kind=ValueKind.INTEGER,
        required=False,
        cardinality=Cardinality(minimum=0, maximum=1),
    )
    two_minimum_field = single_value_field.model_copy(
        update={
            "path": "/synthetic/two_minimum",
            "cardinality": Cardinality(minimum=2, maximum=2),
        }
    )
    singular_entry = MetadataEntry(
        path=single_value_field.path,
        values=(ObservedValue(value=1), ObservedValue(value=2)),
    )
    below_entry = MetadataEntry(
        path=two_minimum_field.path,
        values=(ObservedValue(value=1),),
    )
    candidate_schema = schema.model_copy(
        update={"fields": (*schema.fields, single_value_field, two_minimum_field)}
    )
    candidate_document = document.model_copy(
        update={
            "entries": (
                duplicate_identity,
                *document.entries[1:],
                singular_entry,
                below_entry,
            )
        }
    )

    report = validate_metadata(
        candidate_schema,
        candidate_document,
        consent_state=ConsentState.GRANTED,
    )

    assert {issue.code for issue in report.issues} >= {
        "identity.cardinality_invalid",
        "field.cardinality_above_maximum",
        "field.cardinality_below_minimum",
    }


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        (
            FieldSpecification(
                path="/synthetic/timestamp",
                title="Synthetic timestamp",
                description="Timestamp branch evidence.",
                value_kind=ValueKind.TIMESTAMP,
                required=False,
                cardinality=Cardinality(minimum=0, maximum=1),
            ),
            "2026-01-01T00:00:00",
            "value.timestamp_invalid",
        ),
        (
            FieldSpecification(
                path="/synthetic/term",
                title="Synthetic term",
                description="Term-code branch evidence.",
                value_kind=ValueKind.TERM,
                required=False,
                cardinality=Cardinality(minimum=0, maximum=1),
                vocabulary_id="vocabulary.synthetic_mode",
            ),
            "not a code",
            "value.term_code_invalid",
        ),
    ],
)
def test_specialized_scalar_syntax_is_strict(
    field: FieldSpecification,
    value: str,
    code: str,
) -> None:
    schema, document = _reference()
    candidate_schema = schema.model_copy(update={"fields": (*schema.fields, field)})
    entry = MetadataEntry(path=field.path, values=(ObservedValue(value=value),))
    candidate_document = document.model_copy(update={"entries": (*document.entries, entry)})

    report = validate_metadata(
        candidate_schema,
        candidate_document,
        consent_state=ConsentState.GRANTED,
    )

    assert code in {issue.code for issue in report.issues}


def test_identifier_pattern_and_vocabulary_failures_are_all_retained() -> None:
    schema, document = _reference()
    bad_identity = document.entries[0].model_copy(
        update={"values": (ObservedValue(value="1 invalid"),)}
    )
    bad_term = document.entries[1].model_copy(
        update={"values": (ObservedValue(value="unregistered"),)}
    )
    candidate = document.model_copy(
        update={"entries": (bad_identity, bad_term, *document.entries[2:])}
    )

    report = validate_metadata(schema, candidate, consent_state=ConsentState.GRANTED)

    assert {issue.code for issue in report.issues} >= {
        "value.identifier_invalid",
        "value.pattern_mismatch",
        "value.term_unknown",
    }


def test_pattern_input_length_is_bounded_before_matching() -> None:
    schema, document = _reference()
    long_identity = document.entries[0].model_copy(
        update={"values": (ObservedValue(value="a" * 16_385),)}
    )
    candidate = document.model_copy(
        update={"entries": (long_identity, *document.entries[1:])}
    )

    report = validate_metadata(schema, candidate, consent_state=ConsentState.GRANTED)

    assert "value.pattern_input_too_long" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("unit", "code"),
    [
        (None, "value.unit_required"),
        ("mg", "value.unit_unknown"),
    ],
)
def test_numeric_units_are_explicit_and_registered(unit: str | None, code: str) -> None:
    schema, document = _reference()
    mass = document.entries[2].model_copy(
        update={"values": (ObservedValue(value=12.5, unit=unit),)}
    )
    candidate = document.model_copy(
        update={"entries": (*document.entries[:2], mass, *document.entries[3:])}
    )

    report = validate_metadata(schema, candidate, consent_state=ConsentState.GRANTED)

    assert code in {issue.code for issue in report.issues}


def test_unexpected_disallowed_and_wrong_dimension_units_are_reported() -> None:
    schema, document = _reference()
    unexpected_identity = document.entries[0].model_copy(
        update={"values": (ObservedValue(value="SYN-001", unit="ug"),)}
    )
    milligram = UnitDefinition(
        code="mg",
        system="UCUM",
        system_version="2.2",
        dimension="mass",
        definition="Synthetic deliberately mismatched unit.",
    ).model_copy(update={"dimension": "length"})
    candidate_schema = schema.model_copy(update={"units": (*schema.units, milligram)})
    mass = document.entries[2].model_copy(
        update={"values": (ObservedValue(value=12.5, unit="mg"),)}
    )
    candidate_document = document.model_copy(
        update={
            "entries": (
                unexpected_identity,
                document.entries[1],
                mass,
                *document.entries[3:],
            )
        }
    )

    report = validate_metadata(
        candidate_schema,
        candidate_document,
        consent_state=ConsentState.GRANTED,
    )

    assert {issue.code for issue in report.issues} >= {
        "value.unit_unexpected",
        "value.unit_not_allowed",
        "value.unit_dimension_mismatch",
    }


def test_compatibility_operators_and_action_severities_are_typed() -> None:
    schema, document = _reference()
    numeric_field = FieldSpecification(
        path="/synthetic/number",
        title="Synthetic number",
        description="Typed compatibility evidence.",
        value_kind=ValueKind.NUMBER,
        required=False,
        cardinality=Cardinality(minimum=0, maximum=1),
        numeric_bounds=NumericBounds(),
    )
    number_entry = MetadataEntry(
        path=numeric_field.path,
        values=(ObservedValue(value=1.5),),
    )
    review_rule = CompatibilityRule(
        rule_id="rule.synthetic.review",
        description="Exercise IN and ABSENT operators.",
        when_all=(
            CompatibilityPredicate(
                path=numeric_field.path,
                operator=PredicateOperator.IN,
                values=(1.5,),
            ),
        ),
        require_all=(
            CompatibilityPredicate(
                path="/sample/input_mass",
                operator=PredicateOperator.ABSENT,
            ),
        ),
        on_failure=IssueAction.HUMAN_REVIEW,
    )
    candidate_schema = schema.model_copy(
        update={
            "fields": (*schema.fields, numeric_field),
            "compatibility_rules": (*schema.compatibility_rules, review_rule),
        }
    )
    candidate_document = document.model_copy(
        update={"entries": (*document.entries, number_entry)}
    )

    report = validate_metadata(
        candidate_schema,
        candidate_document,
        consent_state=ConsentState.GRANTED,
    )

    issue = next(
        issue
        for issue in report.issues
        if issue.code == "compatibility.requirement_failed"
    )
    assert issue.action is IssueAction.HUMAN_REVIEW
    assert issue.severity.value == "warning"


def test_satisfied_requirement_and_reject_severity_branches_are_explicit() -> None:
    schema, document = _reference()
    enriched_mode = document.entries[1].model_copy(
        update={"values": (ObservedValue(value="enriched"),)}
    )
    satisfied_document = document.model_copy(
        update={"entries": (document.entries[0], enriched_mode, *document.entries[2:])}
    )

    satisfied = validate_metadata(
        schema,
        satisfied_document,
        consent_state=ConsentState.GRANTED,
    )
    reject_rule = schema.compatibility_rules[0].model_copy(
        update={"on_failure": IssueAction.REJECT}
    )
    reject_schema = schema.model_copy(update={"compatibility_rules": (reject_rule,)})
    missing_mass_document = satisfied_document.model_copy(
        update={"entries": satisfied_document.entries[:2]}
    )
    rejected = validate_metadata(
        reject_schema,
        missing_mass_document,
        consent_state=ConsentState.GRANTED,
    )

    assert satisfied.issues == ()
    issue = next(
        issue
        for issue in rejected.issues
        if issue.code == "compatibility.requirement_failed"
    )
    assert issue.action is IssueAction.REJECT
    assert issue.severity is IssueSeverity.ERROR


def test_unresolved_required_predicates_are_indeterminate_not_false() -> None:
    schema, document = _reference()
    enriched_mode = document.entries[1].model_copy(
        update={"values": (ObservedValue(value="enriched"),)}
    )
    unresolved_mass = document.entries[2].model_copy(
        update={
            "values": (
                UnresolvedValue(
                    state="unknown",
                    reason_code="synthetic_unknown",
                    explanation="Synthetic unresolved quantity.",
                ),
            )
        }
    )
    candidate_document = document.model_copy(
        update={
            "entries": (
                document.entries[0],
                enriched_mode,
                unresolved_mass,
                *document.entries[3:],
            )
        }
    )
    absent_rule = schema.compatibility_rules[0].model_copy(
        update={
            "rule_id": "rule.synthetic.absent_input",
            "require_all": (
                CompatibilityPredicate(
                    path="/sample/input_mass",
                    operator=PredicateOperator.ABSENT,
                ),
            ),
        }
    )
    candidate_schema = schema.model_copy(
        update={
            "compatibility_rules": (*schema.compatibility_rules, absent_rule),
        }
    )

    report = validate_metadata(
        candidate_schema,
        candidate_document,
        consent_state=ConsentState.GRANTED,
    )

    assert report.decision is ConformanceDecision.QUARANTINED
    assert [issue.code for issue in report.issues].count(
        "compatibility.requirement_indeterminate"
    ) == EXPECTED_INDETERMINATE_RULES
