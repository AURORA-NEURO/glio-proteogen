"""Locked semantic outcomes for the public M01-01 validator."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m01_01.v1 import (
    ConformanceDecision,
    EvaluateMetadataRequest,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c01_preanalytic.m01_01_protocol_metadata.validator import (
    validate_metadata,
    validate_protocol_schema,
)
from tests.m01_01_support import load_manifest, load_protocol_schema, load_request

pytestmark = pytest.mark.contract


def _validation_cases() -> list[dict[str, object]]:
    return [
        case
        for case in load_manifest()["cases"]
        if case["expected"] == "accept" and "expected_decision" in case
    ]


@pytest.mark.parametrize("case", _validation_cases(), ids=lambda case: case["case_id"])
def test_locked_validation_cases_match_their_manifest(case: dict[str, object]) -> None:
    request = load_request(str(case["file"]))
    assert isinstance(request, EvaluateMetadataRequest)

    report = validate_metadata(
        load_protocol_schema(),
        request.document,
        consent_state=request.context.references.consent.state,
    )

    assert report.decision.value == case["expected_decision"]
    assert [issue.code for issue in report.issues] == case["expected_issue_codes"]


def test_reference_protocol_passes_semantic_registration_validation() -> None:
    report = validate_protocol_schema(load_protocol_schema())

    assert report.decision is ConformanceDecision.CONFORMANT
    assert report.issues == ()


def test_unsafe_pattern_quarantines_protocol_before_registration() -> None:
    schema = load_protocol_schema()
    unsafe_field = schema.fields[0].model_copy(update={"pattern": "^(a+)+$"})
    unsafe_schema = schema.model_copy(update={"fields": (unsafe_field, *schema.fields[1:])})

    report = validate_protocol_schema(unsafe_schema)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert "schema.pattern_unsafe" in {issue.code for issue in report.issues}


def test_unit_dimension_mismatch_quarantines_protocol_before_registration() -> None:
    schema = load_protocol_schema()
    mass_field = schema.fields[2].model_copy(update={"unit_dimension": "length"})
    mismatched_schema = schema.model_copy(
        update={"fields": (*schema.fields[:2], mass_field, *schema.fields[3:])}
    )

    report = validate_protocol_schema(mismatched_schema)

    assert report.decision is ConformanceDecision.QUARANTINED
    assert "schema.unit_dimension_mismatch" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("field", "value", "code", "decision"),
    [
        (
            "schema_id",
            "protocol.other",
            "document.schema_id_mismatch",
            ConformanceDecision.NONCONFORMANT,
        ),
        (
            "schema_version",
            "2.0.0",
            "document.schema_version_mismatch",
            ConformanceDecision.NONCONFORMANT,
        ),
        (
            "assay_version",
            "2.0.0",
            "document.assay_version_unsupported",
            ConformanceDecision.QUARANTINED,
        ),
        (
            "specimen_version",
            "2.0.0",
            "document.specimen_version_unsupported",
            ConformanceDecision.QUARANTINED,
        ),
    ],
)
def test_exact_compatibility_versions_are_required(
    field: str,
    value: str,
    code: str,
    decision: ConformanceDecision,
) -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    document = request.document.model_copy(update={field: value})

    report = validate_metadata(
        load_protocol_schema(),
        document,
        consent_state=ConsentState.GRANTED,
    )

    assert report.decision is decision
    assert code in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("consent", "decision", "code"),
    [
        (ConsentState.UNKNOWN, ConformanceDecision.QUARANTINED, "consent.unknown"),
        (ConsentState.WITHHELD, ConformanceDecision.NONCONFORMANT, "consent.withheld"),
        (ConsentState.REVOKED, ConformanceDecision.NONCONFORMANT, "consent.revoked"),
    ],
)
def test_consent_can_only_tighten_the_decision(
    consent: ConsentState,
    decision: ConformanceDecision,
    code: str,
) -> None:
    request = load_request("evaluate_conformant.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)

    report = validate_metadata(load_protocol_schema(), request.document, consent_state=consent)

    assert report.decision is decision
    assert [issue.code for issue in report.issues] == [code]


def test_quarantine_precedes_reject_without_erasing_rejection_evidence() -> None:
    request = load_request("evaluate_quarantine.valid.json")
    assert isinstance(request, EvaluateMetadataRequest)
    document = request.document.model_copy(update={"entries": request.document.entries[1:]})

    report = validate_metadata(
        load_protocol_schema(),
        document,
        consent_state=ConsentState.UNKNOWN,
    )

    assert report.decision is ConformanceDecision.QUARANTINED
    assert report.human_review_required is True
    assert {issue.code for issue in report.issues} == {
        "compatibility.requirement_failed",
        "consent.unknown",
        "identity.missing",
    }
