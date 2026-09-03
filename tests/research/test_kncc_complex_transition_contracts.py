from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalTimePoint,
    NormalizationReference,
    ProteinEvidenceState,
    ProteinObservation,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.canonical import (
    computational_request_digest,
    result_payload_digest,
    sha256_digest,
)
from glio_proteogen.research.longitudinal_gbm_complex_transition.contracts import (
    AnalysisSupport,
    ComplexMemberTransitionConcordance,
    ComplexTransitionAblations,
    ComplexTransitionClassification,
    ComplexTransitionEvidence,
    ComplexTransitionProvenance,
    ComplexTransitionReplayVerificationResult,
    ComplexTransitionUncertainty,
    LongitudinalGbmComplexTransitionRequest,
    LongitudinalGbmComplexTransitionResult,
    UncertaintyState,
    UnverifiedLongitudinalGbmComplexTransitionResult,
    classify_interval,
)

_DIGEST = "sha256:" + "1" * 64
_PROFILE_DIGEST = "sha256:" + "2" * 64
_OTHER_DIGEST = "sha256:" + "3" * 64


def _observation(
    point: int,
    symbol: str,
    value: float | None,
    *,
    state: ProteinEvidenceState = ProteinEvidenceState.OBSERVED,
) -> ProteinObservation:
    active = state in {ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED}
    return ProteinObservation(
        observation_id=f"complex.test.{point}.{symbol.lower()}",
        gene_symbol=symbol,
        state=state,
        log_abundance=value if active else None,
        standard_error=0.1 if active else None,
        quality_weight=0.9 if active else 0.0,
        provenance_digest=_DIGEST,
    )


def _request(
    *,
    reverse_observations: bool = False,
    include_missing: bool = False,
) -> LongitudinalGbmComplexTransitionRequest:
    reference = NormalizationReference(
        reference_id="complex.test.reference",
        binding_digest=_DIGEST,
        normalization_method="locked test log2 reference",
    )
    points: list[LongitudinalTimePoint] = []
    for index, values in enumerate(((1.0, 2.0), (1.4, 1.8))):
        observations = [
            _observation(index, "MTOR", values[0]),
            _observation(index, "RPTOR", values[1]),
        ]
        if include_missing:
            observations.append(
                _observation(
                    index,
                    "MLST8",
                    None,
                    state=ProteinEvidenceState.MISSING,
                )
            )
        if reverse_observations:
            observations.reverse()
        points.append(
            LongitudinalTimePoint(
                time_point_id=f"complex.test.t{index}",
                time_offset_days=float(index * 90),
                normalization_reference_digest=_DIGEST,
                observations=tuple(observations),
            )
        )
    return LongitudinalGbmComplexTransitionRequest(
        series_id="complex.test.series",
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=reference,
        time_points=tuple(points),
        bootstrap_replicates=32,
    )


def _abstained_complex() -> ComplexMemberTransitionConcordance:
    return ComplexMemberTransitionConcordance(
        complex_index=0,
        domain_id="mtor_energy_sensing",
        reactome_id="R-HSA-377400",
        complex_name="mTORC1",
        family_id="mtorc1_family",
        support=AnalysisSupport.ABSTAINED,
        classification=ComplexTransitionClassification.NOT_ESTIMABLE,
        active_member_count=0,
        observed_member_count=0,
        left_censored_member_count=0,
        coefficient_mass_coverage=0.0,
        effective_sample_size=0.0,
        source_held_member_relative_gain=0.01,
        source_panel_patient_cluster_gain_90_interval=(-0.02, 0.03),
        source_direction_accuracy=0.6,
        source_minimum_outer_loading_cosine=0.85,
        uncertainty=ComplexTransitionUncertainty(
            state=UncertaintyState.NOT_ESTIMABLE,
            reason="fewer than three active protein members",
        ),
        ablations=ComplexTransitionAblations(),
        limitations=("fewer than three active protein members",),
    )


def _unverified_result() -> UnverifiedLongitudinalGbmComplexTransitionResult:
    request = _request()
    transition = ComplexTransitionEvidence(
        transition_id="complex.test.transition.0",
        transition_index=0,
        from_time_point_id=request.time_points[0].time_point_id,
        to_time_point_id=request.time_points[1].time_point_id,
        duration_days=90.0,
        complexes=(_abstained_complex(),),
    )
    return UnverifiedLongitudinalGbmComplexTransitionResult(
        request_digest=request.request_digest,
        result_digest=_OTHER_DIGEST,
        profile_digest=_PROFILE_DIGEST,
        source_catalog_digest=_DIGEST,
        fitted_model_digest=_OTHER_DIGEST,
        computational_seed=42,
        series_id=request.series_id,
        assay_compatibility=request.assay_compatibility,
        normalization_reference=request.normalization_reference,
        time_point_ids=tuple(point.time_point_id for point in request.time_points),
        transitions=(transition,),
        provenance=ComplexTransitionProvenance(
            source_study_id="PDC000514",
            source_patient_pair_count=104,
            reactome_release=97,
            source_catalog_digest=_DIGEST,
            fitted_model_digest=_OTHER_DIGEST,
            training_recipe_digest=_DIGEST,
            panel_selection_digest=_OTHER_DIGEST,
            participant_membership_digest=_DIGEST,
            source_licenses=("PDC source: CC-BY-4.0", "Reactome annotation: CC0-1.0"),
            source_attribution="Synthetic contract test over locked source identities.",
            validation_scope="internal_patient_grouped_held_member_reconstruction",
        ),
        limitations=(
            "Participant transition concordance is not physical complex assembly or activity.",
        ),
    )


def test_request_digest_is_observation_order_invariant() -> None:
    assert _request().request_digest == _request(reverse_observations=True).request_digest


def test_computational_digest_excludes_typed_missing_evidence() -> None:
    assert computational_request_digest(
        _request(),
        profile_digest=_PROFILE_DIGEST,
    ) == computational_request_digest(
        _request(include_missing=True),
        profile_digest=_PROFILE_DIGEST,
    )


def test_result_digest_is_self_bound() -> None:
    unverified = _unverified_result()
    document = unverified.model_dump(mode="python")
    document["result_digest"] = result_payload_digest(unverified)
    result = LongitudinalGbmComplexTransitionResult.model_validate(document, strict=True)

    assert result.result_digest == result_payload_digest(result)
    forged = deepcopy(document)
    forged["computational_seed"] = 43
    with pytest.raises(ValidationError, match="result digest mismatch"):
        LongitudinalGbmComplexTransitionResult.model_validate(forged, strict=True)


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (0.251, 0.9, ComplexTransitionClassification.SOURCE_RECURRENCE_ALIGNED),
        (-0.9, -0.251, ComplexTransitionClassification.SOURCE_PRIMARY_ALIGNED),
        (-0.25, 0.25, ComplexTransitionClassification.STABLE),
        (-0.3, 0.3, ComplexTransitionClassification.INDETERMINATE),
    ],
)
def test_interval_classification_requires_interval_support(
    lower: float,
    upper: float,
    expected: ComplexTransitionClassification,
) -> None:
    assert classify_interval(lower, upper) is expected


def test_abstained_complex_rejects_numeric_estimate() -> None:
    document = _abstained_complex().model_dump(mode="python")
    document.update(score=0.2, lower_bound=0.1, upper_bound=0.3)
    with pytest.raises(ValidationError, match="abstained complex concordance"):
        ComplexMemberTransitionConcordance.model_validate(document, strict=True)


def test_replay_verified_flag_must_close_all_checks() -> None:
    base = {
        "request_digest_match": True,
        "profile_digest_match": True,
        "result_digest_match": True,
        "transition_topology_match": True,
        "complex_semantic_match": True,
        "uncertainty_semantic_match": True,
        "ablation_semantic_match": True,
        "provenance_match": True,
        "document_semantic_match": True,
        "semantic_match": True,
        "recomputed_request_digest": _DIGEST,
        "recomputed_result_digest": _OTHER_DIGEST,
        "authoritative_profile_digest": _PROFILE_DIGEST,
        "message": "exact replay",
    }
    verified = ComplexTransitionReplayVerificationResult(verified=True, **base)
    assert verified.verified
    with pytest.raises(ValidationError, match="verified replay flag"):
        ComplexTransitionReplayVerificationResult(
            verified=True,
            **{**base, "profile_digest_match": False},
        )


def test_sha256_canonicalization_rejects_nonfinite_json() -> None:
    with pytest.raises(ValueError):
        sha256_digest({"bad": float("nan")})
