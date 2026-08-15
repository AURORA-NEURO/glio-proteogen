"""Additional negative-path locks for M07-07 safety and replay closure."""

# ruff: noqa: INP001

from __future__ import annotations

import json

import pytest
from evals.m07_07.fixtures import policy, request
from pydantic import ValidationError

from glio_proteogen.contracts.m07_07 import (
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrationStatus,
    OutOfDistributionStatus,
    SelectiveCandidate,
    SelectivePredictionStatus,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c07_copy_number_dosage.m07_07_calibration_selective_prediction import (
    CalibrationAuthorizationError,
    CalibrationInputError,
    M0707CalibrationEngine,
    M0707Plugin,
    M0707Service,
    calibrate_selective_copy_number_dosage,
    preflight_calibration_authorization,
)


def test_mapping_and_hostile_preflight_fail_closed() -> None:
    active = request().model_dump(mode="python")
    preflight_calibration_authorization(active)
    with pytest.raises(CalibrationAuthorizationError):
        preflight_calibration_authorization({})

    class Hostile:
        @property
        def context(self) -> object:
            raise RuntimeError("do not inspect")  # noqa: TRY003

    with pytest.raises(CalibrationAuthorizationError):
        preflight_calibration_authorization(Hostile())


def test_invalid_request_and_public_wrapper_are_locked() -> None:
    with pytest.raises(CalibrationInputError):
        M0707CalibrationEngine().calibrate(b"{}")
    result = calibrate_selective_copy_number_dosage(request())
    assert result.status is CalibrationStatus.CALIBRATED


def test_each_selective_rejection_reason_is_auditable() -> None:
    active_policy = policy()
    strata = tuple(item.stratum_id for item in active_policy.strata)
    candidates = tuple(
        SelectiveCandidate(
            feature_id=feature_id,
            category="unknown",
            support_score=support,
            ood_score=ood,
            calibration_error=error,
            stratum_ids=ids,
        )
        for feature_id, support, ood, error, ids in (
            ("feature.unknown", 0.9, 0.1, 0.01, ("stratum.missing",)),
            ("feature.low", 0.1, 0.1, 0.01, strata),
            ("feature.ood", 0.9, 0.9, 0.01, strata),
            ("feature.error", 0.9, 0.1, 0.9, strata),
        )
    )
    result = M0707Service().execute(request(candidates=candidates))
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert len(result.diagnostics) == len(candidates)


def test_contract_selected_and_abstained_shapes_are_closed() -> None:
    with pytest.raises(ValidationError):
        CalibratedPredictionSet(
            prediction_set_id="prediction.bad",
            feature_id="feature.bad",
            labels=("a", "a"),
            target_coverage=0.9,
        )
    with pytest.raises(ValidationError):
        CalibratedEstimate(
            feature_id="feature.bad",
            estimate_value=1.0,
            support_score=0.9,
            ood_status=OutOfDistributionStatus.OOD,
            calibration_error=0.01,
            selection_status=SelectivePredictionStatus.SELECTED,
        )
    with pytest.raises(ValidationError):
        CalibratedEstimate(
            feature_id="feature.bad",
            support_score=0.9,
            ood_status=OutOfDistributionStatus.IN_DOMAIN,
            selection_status=SelectivePredictionStatus.SELECTED,
        )
    with pytest.raises(ValidationError):
        CalibratedEstimate(
            feature_id="feature.bad",
            estimate_value=1.0,
            support_score=0.9,
            ood_status=OutOfDistributionStatus.IN_DOMAIN,
            calibration_error=0.01,
            selection_status=SelectivePredictionStatus.ABSTAINED,
        )


def test_plugin_bytes_path_descriptor_and_forged_token() -> None:
    plugin = M0707Plugin(M0707Service())
    payload = json.dumps(request().model_dump(mode="json")).encode()
    token = plugin.validate(payload)
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M07-07"
    assert plugin.run(token).status is CalibrationStatus.CALIBRATED
    with pytest.raises(TypeError):
        plugin.run(object())  # type: ignore[arg-type]


def test_request_binding_rejects_wrong_version_or_coverage() -> None:
    active = request()
    bad_policy = active.policy.model_copy(update={"target_coverage": 0.89})
    with pytest.raises(ValidationError):
        type(active).model_validate(active.model_copy(update={"policy": bad_policy}), strict=True)
    bad_upstream = active.uncertainty_result.model_copy(update={"result_version": "0.2.0"})
    with pytest.raises(ValidationError):
        type(active).model_validate(
            active.model_copy(update={"uncertainty_result": bad_upstream}), strict=True
        )
