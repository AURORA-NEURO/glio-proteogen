"""Focused semantic tests for the pure M01-01 conformance algorithm."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m01_01.v1 import (
    Cardinality,
    CompatibilityPredicate,
    CompatibilityRule,
    ConformanceDecision,
    FieldSpecification,
    IssueAction,
    IssueSeverity,
    MetadataDocument,
    MetadataEntry,
    MissingnessState,
    NumericBounds,
    ObservedValue,
    PredicateOperator,
    ProtocolSchema,
    UnitDefinition,
    UnresolvedValue,
    ValueKind,
    VocabularyDefinition,
    VocabularyTerm,
)
from glio_proteogen.kernel.models import ConsentState, Limitation
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    ValidationReport,
    validate_metadata,
    validate_protocol_schema,
)

_EXPECTED_ISSUE_LIMIT = 256
_EXPECTED_MESSAGE_LIMIT = 512


def _field(path, value_kind, **updates):
    definition = {
        "path": path,
        "title": f"Field {path}",
        "description": "Synthetic field used only for validator tests.",
        "value_kind": value_kind,
        "required": False,
        "cardinality": Cardinality(minimum=0, maximum=1),
    }
    definition.update(updates)
    return FieldSpecification.model_validate(definition)


def _identity_field():
    return _field(
        "/sample/key",
        ValueKind.IDENTIFIER,
        required=True,
        cardinality=Cardinality(minimum=1, maximum=1),
        identity_key=True,
        pattern=r"^SYN-[0-9]{3}$",
    )


def _mode_field():
    return _field(
        "/assay/mode",
        ValueKind.TERM,
        required=True,
        cardinality=Cardinality(minimum=1, maximum=1),
        vocabulary_id="vocabulary.synthetic_mode",
    )


def _mass_field():
    return _field(
        "/sample/input_mass",
        ValueKind.NUMBER,
        unit_dimension="mass",
        allowed_units=("ug",),
        reference_unit="ug",
        numeric_bounds=NumericBounds(minimum=0.1, maximum=10_000.0),
    )


def _batch_field():
    return _field(
        "/sample/batch",
        ValueKind.IDENTIFIER,
        allowed_missingness=(MissingnessState.UNKNOWN, MissingnessState.REDACTED),
        pattern=r"^BATCH-[A-Z]{2}$",
    )


def _mode_vocabulary():
    return VocabularyDefinition(
        vocabulary_id="vocabulary.synthetic_mode",
        version="1.0.0",
        terms=(
            VocabularyTerm(code="direct", label="Direct", definition="Direct synthetic mode."),
            VocabularyTerm(
                code="enriched",
                label="Enriched",
                definition="Enriched synthetic mode.",
            ),
        ),
    )


def _units():
    return (
        UnitDefinition(
            code="ug",
            system="UCUM",
            system_version="2.2",
            dimension="mass",
            definition="Synthetic microgram.",
        ),
        UnitDefinition(
            code="mg",
            system="UCUM",
            system_version="2.2",
            dimension="mass",
            definition="Synthetic milligram.",
        ),
        UnitDefinition(
            code="s",
            system="UCUM",
            system_version="2.2",
            dimension="time",
            definition="Synthetic second.",
        ),
    )


def _enriched_rule(action=IssueAction.QUARANTINE):
    return CompatibilityRule(
        rule_id="rule.synthetic.enriched_input",
        description="Enriched mode requires a synthetic input quantity.",
        when_all=(
            CompatibilityPredicate(
                path="/assay/mode",
                operator=PredicateOperator.EQUALS,
                values=("enriched",),
            ),
        ),
        require_all=(
            CompatibilityPredicate(
                path="/sample/input_mass",
                operator=PredicateOperator.PRESENT,
            ),
        ),
        on_failure=action,
    )


def _schema(**updates):
    definition = {
        "schema_id": "protocol.synthetic",
        "version": "1.0.0",
        "title": "Synthetic protocol",
        "description": "Non-clinical protocol used only for deterministic tests.",
        "assay_versions": ("1.0.0",),
        "specimen_versions": ("1.0.0",),
        "fields": (_identity_field(), _mode_field(), _mass_field(), _batch_field()),
        "vocabularies": (_mode_vocabulary(),),
        "units": _units(),
        "compatibility_rules": (_enriched_rule(),),
        "limitations": (
            Limitation(code="synthetic_only", statement="Synthetic validation data only."),
        ),
    }
    definition.update(updates)
    return ProtocolSchema.model_validate(definition)


def _entry(path, *values):
    return MetadataEntry(path=path, values=values)


def _document(entries=None, **updates):
    if entries is None:
        entries = (
            _entry("/sample/key", ObservedValue(value="SYN-001")),
            _entry("/assay/mode", ObservedValue(value="direct")),
            _entry("/sample/input_mass", ObservedValue(value=12.5, unit="ug")),
        )
    definition = {
        "document_id": "document.synthetic",
        "schema_id": "protocol.synthetic",
        "schema_version": "1.0.0",
        "assay_version": "1.0.0",
        "specimen_version": "1.0.0",
        "entries": entries,
    }
    definition.update(updates)
    return MetadataDocument.model_validate(definition)


def _codes(report):
    return {issue.code for issue in report.issues}


def test_conformant_validation_is_pure_deterministic_and_immutable():
    schema = _schema()
    document = _document()
    schema_before = schema.model_dump(mode="python")
    document_before = document.model_dump(mode="python")

    first = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)
    second = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert first == second == ValidationReport(
        decision=ConformanceDecision.CONFORMANT,
        issues=(),
        human_review_required=False,
    )
    assert schema.model_dump(mode="python") == schema_before
    assert document.model_dump(mode="python") == document_before
    with pytest.raises(FrozenInstanceError):
        first.decision = ConformanceDecision.NONCONFORMANT


def test_document_headers_unknown_fields_identity_and_cardinality_are_checked():
    document = _document(
        entries=(
            _entry(
                "/assay/mode",
                ObservedValue(value="direct"),
                ObservedValue(value="direct"),
            ),
            _entry("/not/in/schema", ObservedValue(value="opaque")),
        ),
        schema_id="protocol.other",
        schema_version="2.0.0",
        assay_version="9.0.0",
        specimen_version="9.0.0",
    )

    report = validate_metadata(_schema(), document, consent_state=ConsentState.GRANTED)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert {
        "document.schema_id_mismatch",
        "document.schema_version_mismatch",
        "document.assay_version_unsupported",
        "document.specimen_version_unsupported",
        "field.cardinality_above_maximum",
        "field.unknown",
        "identity.missing",
    }.issubset(_codes(report))
    keys = [
        (issue.code, issue.path, issue.severity.value, issue.action.value, issue.message)
        for issue in report.issues
    ]
    assert keys == sorted(keys)


def test_present_entry_is_checked_against_minimum_cardinality():
    repeated = _field(
        "/repeated",
        ValueKind.TEXT,
        cardinality=Cardinality(minimum=2, maximum=3),
    )
    schema = _schema(fields=(repeated,), vocabularies=(), units=(), compatibility_rules=())
    document = _document(entries=(_entry("/repeated", ObservedValue(value="one")),))

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert _codes(report) == {"field.cardinality_below_minimum"}


def test_identity_cardinality_and_unresolved_values_cannot_pass():
    too_many = _document(
        entries=(
            _entry(
                "/sample/key",
                ObservedValue(value="SYN-001"),
                ObservedValue(value="SYN-002"),
            ),
            _entry("/assay/mode", ObservedValue(value="direct")),
        )
    )
    unresolved = _document(
        entries=(
            _entry(
                "/sample/key",
                UnresolvedValue(
                    state="unknown",
                    reason_code="not_supplied",
                    explanation="Synthetic identity intentionally unresolved.",
                ),
            ),
            _entry("/assay/mode", ObservedValue(value="direct")),
        )
    )

    cardinality_report = validate_metadata(
        _schema(), too_many, consent_state=ConsentState.GRANTED
    )
    unresolved_report = validate_metadata(
        _schema(), unresolved, consent_state=ConsentState.GRANTED
    )

    assert "identity.cardinality_invalid" in _codes(cardinality_report)
    assert unresolved_report.decision is ConformanceDecision.QUARANTINED
    assert {
            "identity.unresolved",
            "value.missingness_not_allowed",
            "value.unresolved_unknown",
    }.issubset(_codes(unresolved_report))


def test_strict_kinds_patterns_bounds_vocabularies_and_missingness():
    timestamp = _field("/taken", ValueKind.TIMESTAMP)
    note = _field("/note", ValueKind.TEXT, pattern=r"^[A-Z]{2}$")
    count = _field("/count", ValueKind.INTEGER)
    flag = _field("/flag", ValueKind.BOOLEAN)
    schema = _schema(fields=(*_schema().fields, timestamp, note, count, flag))
    document = _document(
        entries=(
            _entry("/sample/key", ObservedValue(value="bad identity")),
            _entry("/assay/mode", ObservedValue(value="other")),
            _entry("/sample/input_mass", ObservedValue(value=0.01)),
            _entry(
                "/sample/batch",
                UnresolvedValue(
                    state="not_applicable",
                    reason_code="synthetic_na",
                    explanation="Synthetic disallowed state.",
                ),
            ),
            _entry("/taken", ObservedValue(value="2026-08-11")),
            _entry("/note", ObservedValue(value="lower", unit="ug")),
            _entry("/count", ObservedValue(value=True)),
            _entry("/flag", ObservedValue(value=1)),
        )
    )

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert {
        "value.identifier_invalid",
        "value.kind_mismatch",
        "value.missingness_not_allowed",
            "value.pattern_mismatch",
        "value.term_unknown",
        "value.timestamp_invalid",
        "value.unit_required",
        "value.unit_unexpected",
            "value.unresolved_not_applicable",
    }.issubset(_codes(report))


def test_allowed_missingness_still_quarantines_unresolved_input():
    document = _document(
        entries=(
            _entry("/sample/key", ObservedValue(value="SYN-001")),
            _entry("/assay/mode", ObservedValue(value="direct")),
            _entry(
                "/sample/batch",
                UnresolvedValue(
                    state="unknown",
                    reason_code="not_supplied",
                    explanation="Synthetic source intentionally omitted the value.",
                ),
            ),
        )
    )

    report = validate_metadata(_schema(), document, consent_state=ConsentState.GRANTED)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert _codes(report) == {"value.unresolved_unknown"}
    assert report.issues[0].action is IssueAction.QUARANTINE
    assert report.human_review_required is True


@pytest.mark.parametrize(
    ("unit", "expected_codes"),
    [
        (None, {"value.unit_required"}),
        ("kg", {"value.unit_unknown"}),
        ("mg", {"value.unit_not_allowed"}),
        ("s", {"value.unit_not_allowed", "value.unit_dimension_mismatch"}),
    ],
)
def test_ucum_code_allowlist_and_dimension_are_enforced(unit, expected_codes):
    observed = (
        ObservedValue(value=1.0, unit="ug").model_copy(update={"unit": unit})
        if unit == "kg"
        else ObservedValue(value=1.0, unit=unit)
    )
    if unit == "kg":
        document = _document()
        mass_entry = document.entries[2].model_copy(update={"values": (observed,)})
        document = document.model_copy(
            update={"entries": (*document.entries[:2], mass_entry)}
        )
    else:
        document = _document(
            entries=(
                _entry("/sample/key", ObservedValue(value="SYN-001")),
                _entry("/assay/mode", ObservedValue(value="direct")),
                _entry("/sample/input_mass", observed),
            )
        )

    report = validate_metadata(_schema(), document, consent_state=ConsentState.GRANTED)

    assert _codes(report) == expected_codes


def test_numeric_bounds_are_evaluated_in_the_declared_reference_unit() -> None:
    mass_field = _mass_field().model_copy(
        update={
            "allowed_units": ("ug", "mg"),
            "numeric_bounds": NumericBounds(minimum=500.0, maximum=1_500.0),
        }
    )
    schema = _schema(fields=(_identity_field(), _mode_field(), mass_field, _batch_field()))

    microgram_report = validate_metadata(
        schema,
        _document(
            entries=(
                _entry("/sample/key", ObservedValue(value="SYN-001")),
                _entry("/assay/mode", ObservedValue(value="direct")),
                _entry("/sample/input_mass", ObservedValue(value=1.0, unit="ug")),
            )
        ),
        consent_state=ConsentState.GRANTED,
    )
    milligram_report = validate_metadata(
        schema,
        _document(
            entries=(
                _entry("/sample/key", ObservedValue(value="SYN-001")),
                _entry("/assay/mode", ObservedValue(value="direct")),
                _entry("/sample/input_mass", ObservedValue(value=1.0, unit="mg")),
            )
        ),
        consent_state=ConsentState.GRANTED,
    )

    assert _codes(microgram_report) == {"value.numeric_below_minimum"}
    assert milligram_report.issues == ()


def test_unitful_predicates_convert_into_the_field_reference_unit() -> None:
    mass_field = _mass_field().model_copy(update={"allowed_units": ("ug", "mg")})
    rule = CompatibilityRule(
        rule_id="rule.synthetic.converted_mass",
        description="Converted mass equality activates the synthetic requirement.",
        when_all=(
            CompatibilityPredicate(
                path="/sample/input_mass",
                operator=PredicateOperator.EQUALS,
                values=(1,),
                unit="mg",
            ),
        ),
        require_all=(
            CompatibilityPredicate(
                path="/sample/batch",
                operator=PredicateOperator.PRESENT,
            ),
        ),
        on_failure=IssueAction.REJECT,
    )
    schema = _schema(
        fields=(_identity_field(), _mode_field(), mass_field, _batch_field()),
        compatibility_rules=(rule,),
    )
    matching = _document(
        entries=(
            _entry("/sample/key", ObservedValue(value="SYN-001")),
            _entry("/assay/mode", ObservedValue(value="direct")),
            _entry("/sample/input_mass", ObservedValue(value=1_000.0, unit="ug")),
        )
    )
    nonmatching = matching.model_copy(
        update={
            "entries": (
                *matching.entries[:2],
                _entry("/sample/input_mass", ObservedValue(value=1.0, unit="ug")),
            )
        }
    )

    matched_report = validate_metadata(schema, matching, consent_state=ConsentState.GRANTED)
    unmatched_report = validate_metadata(
        schema,
        nonmatching,
        consent_state=ConsentState.GRANTED,
    )

    assert _codes(matched_report) == {"compatibility.requirement_failed"}
    assert unmatched_report.issues == ()


def test_number_predicates_normalize_integer_and_float_representations() -> None:
    score_field = _field("/synthetic/score", ValueKind.NUMBER)
    rule = CompatibilityRule(
        rule_id="rule.synthetic.numeric_equivalence",
        description="Integer predicate and float observation represent one number.",
        when_all=(
            CompatibilityPredicate(
                path=score_field.path,
                operator=PredicateOperator.EQUALS,
                values=(10,),
            ),
        ),
        require_all=(
            CompatibilityPredicate(
                path="/sample/batch",
                operator=PredicateOperator.PRESENT,
            ),
        ),
        on_failure=IssueAction.REJECT,
    )
    schema = _schema(
        fields=(*_schema().fields, score_field),
        compatibility_rules=(rule,),
    )
    document = _document(
        entries=(*_document().entries, _entry(score_field.path, ObservedValue(value=10.0)))
    )

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert _codes(report) == {"compatibility.requirement_failed"}


def test_registration_quarantines_unsafe_invalid_and_semantically_wrong_schema():
    unsafe = _field("/unsafe", ValueKind.TEXT, pattern=r"^(a+)+$")
    invalid = _field("/invalid", ValueKind.TEXT, pattern=r"^[z-a]$")
    wrong_dimension = _field(
        "/wrong_dimension",
        ValueKind.NUMBER,
        unit_dimension="mass",
        allowed_units=("s",),
        reference_unit="s",
    )
    numeric_unit_field = _field(
        "/wrong_kind",
        ValueKind.NUMBER,
        unit_dimension="mass",
        allowed_units=("ug",),
        reference_unit="ug",
    )
    schema = _schema(
        fields=(unsafe, invalid, wrong_dimension, numeric_unit_field),
        vocabularies=(),
        compatibility_rules=(),
    )
    wrong_kind = numeric_unit_field.model_copy(update={"value_kind": ValueKind.TEXT})
    schema = schema.model_copy(
        update={"fields": (unsafe, invalid, wrong_dimension, wrong_kind)}
    )

    report = validate_protocol_schema(schema)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert _codes(report) == {
        "schema.pattern_invalid",
        "schema.pattern_unsafe",
        "schema.unit_dimension_mismatch",
        "schema.unit_kind_invalid",
    }
    assert all(issue.severity is IssueSeverity.CRITICAL for issue in report.issues)
    assert all(issue.action is IssueAction.QUARANTINE for issue in report.issues)


def test_safe_pattern_input_has_a_bounded_evaluation_size():
    field = _field("/bounded", ValueKind.TEXT, pattern=r"^[A-Z]{4096}$")
    schema = _schema(fields=(field,), vocabularies=(), units=(), compatibility_rules=())
    document = _document(
        entries=(_entry("/bounded", ObservedValue(value="A" * 16_385)),)
    )

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert _codes(report) == {"value.pattern_input_too_long"}


def test_compatibility_comparison_is_type_strict_and_actions_are_typed():
    trigger = _field(
        "/trigger",
        ValueKind.BOOLEAN,
        required=True,
        cardinality=Cardinality(minimum=1, maximum=1),
    )
    dependent = _field("/dependent", ValueKind.TEXT)
    integer_rule = CompatibilityRule(
        rule_id="rule.integer_does_not_equal_boolean",
        description="An integer predicate must not equal a boolean observation.",
        when_all=(
            CompatibilityPredicate(
                path="/trigger",
                operator=PredicateOperator.EQUALS,
                values=(1,),
            ),
        ),
        require_all=(
            CompatibilityPredicate(path="/dependent", operator=PredicateOperator.PRESENT),
        ),
        on_failure=IssueAction.QUARANTINE,
    )
    boolean_rule = CompatibilityRule(
        rule_id="rule.boolean_matches_boolean",
        description="A boolean predicate activates its dependency.",
        when_all=(
            CompatibilityPredicate(
                path="/trigger",
                operator=PredicateOperator.IN,
                values=(False, True),
            ),
        ),
        require_all=(
            CompatibilityPredicate(path="/dependent", operator=PredicateOperator.PRESENT),
        ),
        on_failure=IssueAction.HUMAN_REVIEW,
    )
    with pytest.raises(ValidationError, match="value kind does not match"):
        _schema(
            fields=(trigger, dependent),
            vocabularies=(),
            units=(),
            compatibility_rules=(integer_rule,),
        )
    schema = _schema(
        fields=(trigger, dependent),
        vocabularies=(),
        units=(),
        compatibility_rules=(boolean_rule,),
    )
    document = _document(entries=(_entry("/trigger", ObservedValue(value=True)),))

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert report.decision is ConformanceDecision.REVIEW_REQUIRED
    assert len(report.issues) == 1
    issue = report.issues[0]
    assert issue.code == "compatibility.requirement_failed"
    assert issue.action is IssueAction.HUMAN_REVIEW
    assert "rule.boolean_matches_boolean" in issue.message


def test_quarantine_dominates_reject_for_mixed_failures():
    document = _document(schema_id="protocol.other", assay_version="9.0.0")

    report = validate_metadata(_schema(), document, consent_state=ConsentState.UNKNOWN)

    assert {IssueAction.REJECT, IssueAction.QUARANTINE}.issubset(
        {issue.action for issue in report.issues}
    )
    assert report.decision is ConformanceDecision.QUARANTINED
    assert report.human_review_required is True


@pytest.mark.parametrize(
    ("consent_state", "decision", "code", "review_required"),
    [
        (ConsentState.WITHHELD, ConformanceDecision.NONCONFORMANT, "consent.withheld", True),
        (ConsentState.REVOKED, ConformanceDecision.NONCONFORMANT, "consent.revoked", True),
        (ConsentState.UNKNOWN, ConformanceDecision.QUARANTINED, "consent.unknown", True),
    ],
)
def test_consent_state_is_never_inferred(
    consent_state,
    decision,
    code,
    review_required,
):
    report = validate_metadata(_schema(), _document(), consent_state=consent_state)

    assert report.decision is decision
    assert _codes(report) == {code}
    assert report.human_review_required is review_required


def test_issue_count_and_messages_are_deterministically_bounded():
    field = _field(
        "/many",
        ValueKind.TEXT,
        cardinality=Cardinality(minimum=0, maximum=1_000),
        pattern=r"^[A-Z]{2}$",
    )
    schema = _schema(fields=(field,), vocabularies=(), units=(), compatibility_rules=())
    values = tuple(ObservedValue(value="invalid") for _ in range(300))
    document = _document(entries=(_entry("/many", *values),))

    report = validate_metadata(schema, document, consent_state=ConsentState.GRANTED)

    assert len(report.issues) == _EXPECTED_ISSUE_LIMIT
    assert "validation.issue_limit_reached" in _codes(report)
    assert max(len(issue.message) for issue in report.issues) <= _EXPECTED_MESSAGE_LIMIT
    assert report.decision is ConformanceDecision.QUARANTINED
