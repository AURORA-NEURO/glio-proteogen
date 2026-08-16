"""Focused schema and constraint-report smoke for provisional M08-05."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m08_05 import (
    M0805_BASELINE_MEDIA_TYPE,
    M0805_OUTPUT_MEDIA_TYPE,
    ConstraintEvaluationStatus,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    contract_json_schemas,
)

_VIOLATION_SCORE = 0.75


def test_schema_inventory_is_strict_and_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "estimate",
        "constraint",
        "report",
        "policy",
        "verification",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["hardConstraintsRequired"] is True
        assert metadata["softConflictsQuantified"] is True
        assert metadata["hiddenPriorDominance"] is False
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0805_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["baselineInputMediaType"] == (
        M0805_BASELINE_MEDIA_TYPE
    )


def test_constraint_report_requires_explicit_violation_score() -> None:
    report = ConstraintSatisfactionReport(
        constraint_id="constraint.conservation",
        severity=ConstraintSeverity.HARD,
        status=ConstraintEvaluationStatus.VIOLATED,
        violation_score=_VIOLATION_SCORE,
        message="Conservation constraint is violated in the provisional fixture.",
    )
    assert report.status is ConstraintEvaluationStatus.VIOLATED
    assert report.violation_score == _VIOLATION_SCORE
