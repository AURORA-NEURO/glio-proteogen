"""Strict contract/schema smoke for the provisional M06-07 scaffold."""

from __future__ import annotations

from typing import cast

import pytest
from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m06_07 import (
    M0607_OUTPUT_MEDIA_TYPE,
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrateSelectiveProteinAbundanceVerification,
    CalibrationMethod,
    CalibrationPolicy,
    CalibrationReplayReason,
    CalibrationStratum,
    CalibrationStratumDimension,
    OutOfDistributionStatus,
    SelectivePredictionStatus,
    SelectiveSupportThreshold,
    canonical_request_digest,
    contract_json_schemas,
)
from glio_proteogen.kernel.models import ArtifactReference, SupportStatus
from glio_proteogen.modules.c06_protein_abundance.m06_07_calibration_selective_prediction import (
    M0607CalibrationEngine,
    M0607Service,
)

_EXPECTED_COVERAGE = 0.90
_EXPECTED_ERROR = 0.02


def test_schema_inventory_is_explicitly_provisional() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "policy",
        "stratum",
        "threshold",
        "estimate",
        "prediction-set",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["abiStatus"] == "dossier-behavioral-brief-only"
        assert metadata["calibrationMetricsFrozen"] is False
        assert metadata["coverageCeilingsFrozen"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M0607_OUTPUT_MEDIA_TYPE


def test_calibration_selective_prediction_and_runtime_import_smoke() -> None:
    stratum = CalibrationStratum(
        stratum_id="stratum.m0607.site",
        dimension=CalibrationStratumDimension.SITE,
        label="site-a",
        sample_count=10,
        observed_coverage=_EXPECTED_COVERAGE,
        calibration_error=_EXPECTED_ERROR,
    )
    prediction_set = CalibratedPredictionSet(
        prediction_set_id="prediction-set.m0607.smoke",
        feature_id="feature.m0607.smoke",
        labels=("high", "low"),
        target_coverage=_EXPECTED_COVERAGE,
        observed_coverage=_EXPECTED_COVERAGE,
    )
    estimate = CalibratedEstimate(
        feature_id="feature.m0607.smoke",
        estimate_value=1.0,
        prediction_set_id=prediction_set.prediction_set_id,
        support_score=0.95,
        ood_status=OutOfDistributionStatus.IN_DOMAIN,
        calibration_error=_EXPECTED_ERROR,
        selection_status=SelectivePredictionStatus.SELECTED,
    )
    assert stratum.observed_coverage == _EXPECTED_COVERAGE
    assert estimate.prediction_set_id == prediction_set.prediction_set_id
    assert canonical_request_digest({"stratum": stratum.model_dump(mode="json")}).startswith(
        "sha256:"
    )
    assert M0607Service is not None
    assert M0607CalibrationEngine is not None


def _artifact_for_contract(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.m0607.{label}",
        version="1.0.0",
        digest="sha256:" + "a" * 64,
        media_type="application/json",
    )


def test_empty_stratum_metrics_are_rejected() -> None:
    with pytest.raises(ValueError, match="coverage metrics"):
        CalibrationStratum(
            stratum_id="stratum.empty",
            dimension=CalibrationStratumDimension.SITE,
            label="empty",
            sample_count=0,
            observed_coverage=0.9,
        )


def test_policy_strata_ids_and_target_binding_are_closed() -> None:
    stratum = CalibrationStratum(
        stratum_id="stratum.duplicate",
        dimension=CalibrationStratumDimension.SITE,
        label="site",
        sample_count=10,
    )
    threshold = SelectiveSupportThreshold(
        threshold_id="threshold.test",
        version="1.0.0",
        minimum_support_score=0.8,
        maximum_ood_score=0.2,
        maximum_calibration_error=0.1,
        target_coverage=0.9,
    )
    with pytest.raises(ValueError, match="stratum ids"):
        CalibrationPolicy(
            policy_id="policy.duplicate",
            version="1.0.0",
            method=CalibrationMethod.CONFORMAL,
            calibration_reference=_artifact_for_contract("policy"),
            strata=(stratum, stratum),
            support_threshold=threshold,
        )
    bad_threshold = threshold.model_copy(update={"target_coverage": 0.8})
    with pytest.raises(ValueError, match="bind policy"):
        CalibrationPolicy(
            policy_id="policy.bad-target",
            version="1.0.0",
            method=CalibrationMethod.CONFORMAL,
            calibration_reference=_artifact_for_contract("policy-bad"),
            strata=(stratum,),
            support_threshold=bad_threshold,
        )


def test_prediction_labels_must_be_unique() -> None:
    with pytest.raises(ValueError, match="labels"):
        CalibratedPredictionSet(
            prediction_set_id="prediction-set.bad",
            feature_id="feature.bad",
            labels=("a", "a"),
            target_coverage=0.9,
        )


def test_selected_estimate_requires_domain_value_and_error() -> None:
    with pytest.raises(ValueError, match="in-domain"):
        CalibratedEstimate(
            feature_id="feature.bad",
            estimate_value=1.0,
            support_score=0.9,
            ood_status=OutOfDistributionStatus.OOD,
            calibration_error=0.02,
            selection_status=SelectivePredictionStatus.SELECTED,
        )
    with pytest.raises(ValueError, match="value or category"):
        CalibratedEstimate(
            feature_id="feature.bad",
            support_score=0.9,
            ood_status=OutOfDistributionStatus.IN_DOMAIN,
            calibration_error=0.02,
            selection_status=SelectivePredictionStatus.SELECTED,
        )
    with pytest.raises(ValueError, match="calibration error"):
        CalibratedEstimate(
            feature_id="feature.bad",
            estimate_value=1.0,
            support_score=0.9,
            ood_status=OutOfDistributionStatus.IN_DOMAIN,
            selection_status=SelectivePredictionStatus.SELECTED,
        )


def test_abstained_estimate_cannot_carry_value() -> None:
    with pytest.raises(ValueError, match="scientific value"):
        CalibratedEstimate(
            feature_id="feature.bad",
            estimate_value=1.0,
            support_score=0.2,
            ood_status=OutOfDistributionStatus.OOD,
            selection_status=SelectivePredictionStatus.ABSTAINED,
        )


def test_replay_verification_closure_is_fail_closed() -> None:
    digest = "sha256:" + "a" * 64
    with pytest.raises(ValueError, match="content and deterministic"):
        CalibrateSelectiveProteinAbundanceVerification(
            content_verified=True,
            deterministic_verified=False,
            verified=True,
            result_digest=digest,
            reason=CalibrationReplayReason.VERIFIED,
        )
    with pytest.raises(ValueError, match="trusted result"):
        CalibrateSelectiveProteinAbundanceVerification(
            content_verified=False,
            deterministic_verified=False,
            verified=False,
            result_digest=digest,
            reason=CalibrationReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValueError, match="verified reason"):
        CalibrateSelectiveProteinAbundanceVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            result_digest=digest,
            reason=CalibrationReplayReason.DIGEST_MISMATCH,
        )
    with pytest.raises(ValueError, match="requires a result digest"):
        CalibrateSelectiveProteinAbundanceVerification(
            content_verified=True,
            deterministic_verified=True,
            verified=True,
            reason=CalibrationReplayReason.VERIFIED,
        )


def test_support_status_enum_is_explicit() -> None:
    assert SupportStatus.REVIEW_REQUIRED.value == "review_required"
