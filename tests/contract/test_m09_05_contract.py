"""Focused schema and constraint-report smoke for provisional M09-05."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m09_05 import (
    M0905_BASELINE_MEDIA_TYPE,
    M0905_OUTPUT_MEDIA_TYPE,
    ConstraintEvaluationStatus,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    IntegrateComplexActivityConstraintsVerification,
    canonical_request_digest,
    contract_json_schemas,
    normalized_result_payload,
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
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0905_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["baselineInputMediaType"] == (
        M0905_BASELINE_MEDIA_TYPE
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


def test_canonical_projection_accepts_mapping_and_removes_result_digest() -> None:
    document = {"value": 1, "result_digest": "discarded"}
    assert canonical_request_digest(document).startswith("sha256:")
    assert normalized_result_payload(document) == {"value": 1}


def test_replay_verification_closes_success_and_failure_shapes() -> None:
    verified = IntegrateComplexActivityConstraintsVerification(
        content_verified=True,
        deterministic_verified=True,
        verified=True,
        result_digest="sha256:" + "a" * 64,
        reason=ConstraintReplayReason.VERIFIED,
    )
    assert verified.verified is True
    assert verified.reason is ConstraintReplayReason.VERIFIED

    rejected = IntegrateComplexActivityConstraintsVerification(
        content_verified=False,
        deterministic_verified=True,
        verified=False,
        reason=ConstraintReplayReason.NON_CANONICAL,
    )
    assert rejected.result_digest is None
