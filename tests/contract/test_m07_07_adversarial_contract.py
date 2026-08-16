"""Adversarial closure checks for the provisional M07-07 contract."""

from __future__ import annotations

import pytest
from evals.m07_07.fixtures import policy, request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_07 import (
    CalibrationStratum,
    CalibrationStratumDimension,
    SelectiveCandidate,
)


def test_candidate_requires_exactly_one_value_and_unique_labels() -> None:
    with pytest.raises(ValidationError):
        SelectiveCandidate(
            feature_id="feature.invalid",
            estimate_value=1.0,
            category="also-invalid",
            labels=("x",),
            support_score=0.9,
            ood_score=0.1,
            calibration_error=0.01,
            stratum_ids=("stratum.site",),
        )
    with pytest.raises(ValidationError):
        SelectiveCandidate(
            feature_id="feature.invalid",
            category="x",
            labels=("x", "x"),
            support_score=0.9,
            ood_score=0.1,
            calibration_error=0.01,
            stratum_ids=("stratum.site",),
        )


def test_policy_requires_unique_strata_and_matching_threshold() -> None:
    base = policy()
    with pytest.raises(ValidationError):
        type(base).model_validate(
            base.model_dump(mode="python") | {"strata": (base.strata[0], base.strata[0])},
            strict=True,
        )
    with pytest.raises(ValidationError):
        type(base).model_validate(
            base.model_dump(mode="python")
            | {
                "support_threshold": base.support_threshold.model_copy(
                    update={"target_coverage": 0.89}
                )
            },
            strict=True,
        )


def test_empty_stratum_metrics_are_not_evidence() -> None:
    with pytest.raises(ValidationError):
        CalibrationStratum(
            stratum_id="stratum.empty",
            dimension=CalibrationStratumDimension.SITE,
            label="empty",
            sample_count=0,
            observed_coverage=0.9,
            calibration_error=0.01,
        )
    assert request().policy.support_threshold.locked is True
