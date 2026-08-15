"""Runtime, replay, and gate tests for M08-07."""

from __future__ import annotations

from glio_proteogen.contracts.m08_07 import CalibrationCandidate, CalibrationStatus
from glio_proteogen.modules.c08_transcript_protein_discordance.m08_07_calibration_selective_prediction import (
    M0807Service,
)

from tests.contract.test_m08_07_contract_hardening import _request


def _candidate(**overrides: object) -> CalibrationCandidate:
    values: dict[str, object] = {
        "site": "site-a",
        "platform": "platform-a",
        "disease_class": "glioma",
        "subgroup": "all",
        "predicted_subtype": "subtype_a",
        "score": 0.8,
        "calibrated_confidence": 0.9,
        "labels": ("subtype_a", "subtype_b"),
        "observed_coverage": 0.9,
        "calibration_error": 0.05,
        "support_score": 0.95,
        "ood_score": 0.05,
        "subgroup_disparity": 0.03,
    }
    values.update(overrides)
    return CalibrationCandidate(**values)


def test_supported_candidate_emits_calibrated_estimate_and_prediction_set() -> None:
    request = _request()
    request = request.model_copy(update={"candidate": _candidate()})
    result = M0807Service().execute(request)
    assert result.status is CalibrationStatus.CALIBRATED
    assert result.estimate is not None
    assert result.prediction_set is not None
    assert result.estimate.predicted_subtype in result.prediction_set.labels
    assert result.support_decision.status.value == "supported"
    assert result.human_review_required is False


def test_missing_candidate_abstains_for_review() -> None:
    result = M0807Service().execute(_request())
    assert result.status is CalibrationStatus.ABSTAINED
    assert result.estimate is None
    assert result.prediction_set is None
    assert result.human_review_required is True
    assert result.findings == ("missing_candidate",)


def test_support_and_ood_gates_abstain_as_unsupported() -> None:
    for field, value, finding in (
        ("support_score", 0.1, "support_threshold_not_met"),
        ("ood_score", 0.9, "ood_unsupported"),
    ):
        request = _request().model_copy(update={"candidate": _candidate(**{field: value})})
        result = M0807Service().execute(request)
        assert result.status is CalibrationStatus.ABSTAINED
        assert result.support_decision.status.value == "unsupported"
        assert result.findings == (finding,)


def test_coverage_calibration_and_disparity_gates_require_review() -> None:
    for field, value, finding in (
        ("observed_coverage", 0.5, "coverage_out_of_bounds"),
        ("calibration_error", 0.5, "calibration_error_exceeded"),
        ("subgroup_disparity", 0.5, "subgroup_disparity"),
    ):
        request = _request().model_copy(update={"candidate": _candidate(**{field: value})})
        result = M0807Service().execute(request)
        assert result.status is CalibrationStatus.ABSTAINED
        assert result.support_decision.status.value == "review_required"
        assert result.findings == (finding,)

