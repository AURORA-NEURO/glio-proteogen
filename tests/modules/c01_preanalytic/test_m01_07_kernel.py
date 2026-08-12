"""Focused tests for the pure M01-07 routing kernel."""

from __future__ import annotations

import pytest

from glio_proteogen.modules.c01_preanalytic.m01_07_support_router import (
    Criterion,
    CriterionDecision,
    CriterionKind,
    EvidenceState,
    EvidenceValue,
    RouteDecision,
    route_support,
)


def _criterion(kind: CriterionKind, **changes: object) -> Criterion:
    values: dict[str, object] = {
        "criterion_id": f"criterion.{kind.value}",
        "signal_id": f"signal.{kind.value}",
        "kind": kind,
        "remediation_code": f"remediate.{kind.value}",
    }
    values.update(changes)
    return Criterion(**values)  # type: ignore[arg-type]


def test_all_four_rule_kinds_support_valid_evidence() -> None:
    criteria = (
        _criterion(CriterionKind.TERM_IN_SET, allowed_terms=("dia", "dda")),
        _criterion(CriterionKind.NUMERIC_RANGE, minimum=0.5, maximum=1.0),
        _criterion(CriterionKind.BOOLEAN_EQUALS, expected_bool=True),
        _criterion(CriterionKind.REQUIRED_PRESENT),
    )
    evidence = {
        criteria[0].signal_id: EvidenceValue(EvidenceState.OBSERVED, "dia"),
        criteria[1].signal_id: EvidenceValue(EvidenceState.OBSERVED, 0.75),
        criteria[2].signal_id: EvidenceValue(EvidenceState.OBSERVED, value=True),
        criteria[3].signal_id: EvidenceValue(EvidenceState.OBSERVED, "present"),
    }

    result = route_support(criteria, evidence)

    assert result.decision is RouteDecision.SUPPORTED
    assert result.review_required is False
    assert all(item.decision is CriterionDecision.SUPPORTED for item in result.criteria)
    assert result.remediation_codes == ()


@pytest.mark.parametrize(
    "state",
    [EvidenceState.MISSING, EvidenceState.UNKNOWN, EvidenceState.NOT_APPLICABLE],
)
def test_nonobserved_required_evidence_is_indeterminate_and_abstains(
    state: EvidenceState,
) -> None:
    criterion = _criterion(CriterionKind.REQUIRED_PRESENT)

    result = route_support((criterion,), {criterion.signal_id: EvidenceValue(state)})

    assert result.criteria[0].decision is CriterionDecision.INDETERMINATE
    assert result.decision is RouteDecision.ABSTAINED
    assert result.review_required is True
    assert result.remediation_codes == (criterion.remediation_code,)


@pytest.mark.parametrize(
    ("criterion", "value"),
    [
        (_criterion(CriterionKind.TERM_IN_SET, allowed_terms=("dia",)), "dda"),
        (_criterion(CriterionKind.NUMERIC_RANGE, minimum=0.5, maximum=1.0), 0.25),
        (_criterion(CriterionKind.BOOLEAN_EQUALS, expected_bool=True), False),
    ],
)
def test_observed_out_of_domain_evidence_is_unsupported(
    criterion: Criterion,
    value: object,
) -> None:
    assert isinstance(value, str | float | bool)
    result = route_support(
        (criterion,),
        {criterion.signal_id: EvidenceValue(EvidenceState.OBSERVED, value=value)},
    )

    assert result.criteria[0].decision is CriterionDecision.UNSUPPORTED
    assert result.decision is RouteDecision.ABSTAINED


def test_optional_observed_failure_always_abstains() -> None:
    criterion = _criterion(
        CriterionKind.BOOLEAN_EQUALS,
        expected_bool=True,
        required=False,
    )

    result = route_support(
        (criterion,),
        {criterion.signal_id: EvidenceValue(EvidenceState.OBSERVED, value=False)},
    )

    assert result.decision is RouteDecision.ABSTAINED
    assert result.review_required is True
    assert result.criteria[0].decision is CriterionDecision.UNSUPPORTED
    assert result.remediation_codes == (criterion.remediation_code,)


def test_explicitly_allowed_optional_not_applicable_is_nonblocking() -> None:
    criterion = _criterion(
        CriterionKind.BOOLEAN_EQUALS,
        expected_bool=True,
        required=False,
        allow_not_applicable=True,
    )

    result = route_support(
        (criterion,),
        {criterion.signal_id: EvidenceValue(EvidenceState.NOT_APPLICABLE)},
    )

    assert result.decision is RouteDecision.SUPPORTED
    assert result.criteria[0].decision is CriterionDecision.SUPPORTED
    assert result.remediation_codes == ()


def test_optional_missing_is_indeterminate_and_abstains() -> None:
    criterion = _criterion(
        CriterionKind.BOOLEAN_EQUALS,
        expected_bool=True,
        required=False,
        allow_not_applicable=True,
    )

    result = route_support(
        (criterion,),
        {criterion.signal_id: EvidenceValue(EvidenceState.MISSING)},
    )

    assert result.criteria[0].decision is CriterionDecision.INDETERMINATE
    assert result.decision is RouteDecision.ABSTAINED


def test_wrong_observed_value_type_is_indeterminate_never_unsupported() -> None:
    criterion = _criterion(CriterionKind.NUMERIC_RANGE, minimum=0.0)

    result = route_support(
        (criterion,),
        {criterion.signal_id: EvidenceValue(EvidenceState.OBSERVED, value=True)},
    )

    assert result.criteria[0].decision is CriterionDecision.INDETERMINATE
    assert result.decision is RouteDecision.ABSTAINED


def test_remediation_codes_are_deduplicated_in_criterion_order() -> None:
    criteria = (
        _criterion(
            CriterionKind.TERM_IN_SET,
            allowed_terms=("dia",),
            remediation_code="remediate.assay",
        ),
        _criterion(
            CriterionKind.BOOLEAN_EQUALS,
            expected_bool=True,
            remediation_code="remediate.assay",
        ),
    )

    result = route_support(criteria, {})

    assert result.remediation_codes == ("remediate.assay",)


@pytest.mark.parametrize(
    ("criteria", "message"),
    [
        (
            (
                _criterion(CriterionKind.REQUIRED_PRESENT),
                _criterion(CriterionKind.REQUIRED_PRESENT),
            ),
            "identifiers must be unique",
        ),
        ((_criterion(CriterionKind.TERM_IN_SET),), "unique allowed terms"),
        ((_criterion(CriterionKind.NUMERIC_RANGE),), "at least one bound"),
        (
            (_criterion(CriterionKind.NUMERIC_RANGE, minimum=2.0, maximum=1.0),),
            "bounds must be ordered",
        ),
        ((_criterion(CriterionKind.BOOLEAN_EQUALS),), "expected value"),
    ],
)
def test_invalid_criterion_configuration_fails_closed(
    criteria: tuple[Criterion, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        route_support(criteria, {})
