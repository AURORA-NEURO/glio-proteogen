from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from glio_proteogen.research.longitudinal_gbm import (
    DEFAULT_BOOTSTRAPS,
    REQUIRED_ASSAY_COMPATIBILITY,
    AnalysisSupport,
    AssayCompatibilityAttestation,
    DriverDirection,
    LongitudinalAlgorithmConstants,
    LongitudinalGbmProfile,
    LongitudinalGbmProvenance,
    LongitudinalGbmRequest,
    LongitudinalGbmResult,
    LongitudinalSourceModelCounts,
    LongitudinalSourceModelDigests,
    LongitudinalTimePoint,
    NormalizationReference,
    PeltAnalysis,
    PeltBoundary,
    ProteinEvidenceState,
    ProteinObservation,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    SignedProteinDriver,
    SourceProcessingAblation,
    TopDriverAblation,
    TransitionClassification,
    TransitionEvidence,
    TransitionUncertainty,
    UncertaintyInteraction,
    UncertaintyState,
    UnverifiedLongitudinalGbmResult,
    canonical_json_bytes,
    canonical_request_digest,
    computational_request_digest,
    normalized_request,
    profile_payload_digest,
    result_payload_digest,
    sha256_digest,
)
from glio_proteogen.research.longitudinal_gbm.errors import (
    LongitudinalGbmError,
    LongitudinalInferenceError,
    SourceProfileIntegrityError,
)

DIGEST = sha256_digest({"longitudinal": "contract-test"})
OTHER_DIGEST = sha256_digest({"longitudinal": "other"})


def _normalization() -> NormalizationReference:
    return NormalizationReference(
        reference_id="normalization.reference",
        binding_digest=DIGEST,
        normalization_method="same log-abundance preparation and reference for every point",
    )


def _observation(  # noqa: PLR0913
    gene: str = "EGFR",
    *,
    identifier: str = "obs.1",
    state: ProteinEvidenceState = ProteinEvidenceState.OBSERVED,
    abundance: float | None = 1.0,
    standard_error: float | None = 0.2,
    quality: float = 1.0,
    provenance: str = DIGEST,
) -> ProteinObservation:
    return ProteinObservation(
        observation_id=identifier,
        gene_symbol=gene,
        state=state,
        log_abundance=abundance,
        standard_error=standard_error,
        quality_weight=quality,
        provenance_digest=provenance,
    )


def _time_point(
    identifier: str,
    offset: float,
    *,
    observations: tuple[ProteinObservation, ...] | None = None,
    normalization_digest: str = DIGEST,
) -> LongitudinalTimePoint:
    if observations is None:
        observations = (
            _observation(
                identifier=f"obs.{identifier}",
                abundance=1.0 + offset / 100.0,
            ),
        )
    return LongitudinalTimePoint(
        time_point_id=identifier,
        time_offset_days=offset,
        normalization_reference_digest=normalization_digest,
        observations=observations,
    )


def _request(*, points: tuple[LongitudinalTimePoint, ...] | None = None) -> LongitudinalGbmRequest:
    return LongitudinalGbmRequest(
        series_id="series.contract",
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=_normalization(),
        time_points=points
        or (
            _time_point("time.primary", 0.0),
            _time_point("time.recurrence", 180.0),
        ),
    )


def _uncertainty(
    state: UncertaintyState = UncertaintyState.ESTIMATED,
) -> TransitionUncertainty:
    if state is UncertaintyState.ESTIMATED:
        return TransitionUncertainty(
            state=state,
            standard_error=0.1,
            variance_fraction=0.5,
            bootstrap_replicates_used=128,
        )
    return TransitionUncertainty(
        state=state,
        bootstrap_replicates_used=0,
        reason="insufficient shared active proteins",
    )


def _interaction(
    state: UncertaintyState = UncertaintyState.ESTIMATED,
) -> UncertaintyInteraction:
    if state is UncertaintyState.ESTIMATED:
        return UncertaintyInteraction(
            state=state,
            covariance=-0.01,
            variance_contribution=-0.02,
            combined_variance=0.03,
            decomposition_residual=0.0,
            bootstrap_replicates_used=128,
        )
    return UncertaintyInteraction(
        state=state,
        bootstrap_replicates_used=0,
        reason="insufficient paired bootstrap projections",
    )


def _transition(  # noqa: PLR0913
    *,
    identifier: str = "transition.0",
    index: int = 0,
    from_id: str = "time.primary",
    to_id: str = "time.recurrence",
    support: AnalysisSupport = AnalysisSupport.SUPPORTED,
    classification: TransitionClassification = TransitionClassification.SOURCE_RECURRENCE_ALIGNED,
    score: float | None = 0.8,
    lower: float | None = 0.5,
    upper: float | None = 1.1,
    replicates: int = 128,
    percentile: float | None = 0.8,
    measurement: TransitionUncertainty | None = None,
    coefficient: TransitionUncertainty | None = None,
    interaction: UncertaintyInteraction | None = None,
    reasons: tuple[str, ...] = (),
) -> TransitionEvidence:
    return TransitionEvidence(
        transition_id=identifier,
        transition_index=index,
        from_time_point_id=from_id,
        to_time_point_id=to_id,
        support=support,
        classification=classification,
        score=score,
        lower_bound=lower,
        upper_bound=upper,
        bootstrap_replicates_used=replicates,
        shared_active_gene_count=100,
        effective_sample_size=80.0,
        coverage=0.5,
        source_support_percentile=percentile,
        measurement_uncertainty=measurement or _uncertainty(),
        coefficient_uncertainty=coefficient or _uncertainty(),
        uncertainty_interaction=interaction or _interaction(),
        abstention_reasons=reasons,
    )


def _provenance() -> LongitudinalGbmProvenance:
    return LongitudinalGbmProvenance(
        request_digest=DIGEST,
        profile_digest=DIGEST,
        source_profile_content_digest=DIGEST,
        source_profile_artifact_digest=DIGEST,
        source_file_lock_digest=DIGEST,
        cohort_oracle_digest=DIGEST,
        feature_space_digest=DIGEST,
        transition_model_digest=DIGEST,
        coefficient_digest=DIGEST,
        bootstrap_digest=DIGEST,
        source_processing_ablation_digest=DIGEST,
        hgnc_complete_set_digest=DIGEST,
        source_to_hgnc_mapping_digest=DIGEST,
        engine_semantic_digest=DIGEST,
        demo_semantic_oracle_digest=DIGEST,
        assay_compatibility_digest=sha256_digest(
            REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json")
        ),
        normalization_reference_digest=DIGEST,
        numpy_version="2.5.2",
        computational_digest=DIGEST,
        numerical_seed_digest=DIGEST,
        bootstrap_seed=42,
        observation_source_digests=(DIGEST,),
        source_attribution=(
            "Kim et al., Integrated proteogenomic characterization of glioblastoma evolution"
        ),
        source_license="source terms",
        source_license_url="https://proteomic.datacommons.cancer.gov/",
        source_transformation_notice="Derived source projection; no patient identifiers retained.",
    )


def _unverified_result(  # noqa: PLR0913
    *,
    time_ids: tuple[str, ...] = ("time.primary", "time.recurrence"),
    transitions: tuple[TransitionEvidence, ...] | None = None,
    pelt: PeltAnalysis | None = None,
    provenance: LongitudinalGbmProvenance | None = None,
    profile_digest: str = DIGEST,
    request_digest: str = DIGEST,
    normalization: NormalizationReference | None = None,
) -> UnverifiedLongitudinalGbmResult:
    return UnverifiedLongitudinalGbmResult(
        profile_digest=profile_digest,
        request_digest=request_digest,
        result_digest=OTHER_DIGEST,
        series_id="series.contract",
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=normalization or _normalization(),
        time_point_ids=time_ids,
        transitions=transitions or (_transition(),),
        pelt_analysis=pelt,
        provenance=provenance or _provenance(),
        limitations=("Research evidence only; not a patient-evolution claim.",),
    )


def _verified_result(**kwargs: Any) -> LongitudinalGbmResult:
    unverified = _unverified_result(**kwargs)
    document = unverified.model_dump(mode="python")
    document["result_digest"] = result_payload_digest(unverified)
    return LongitudinalGbmResult.model_validate(document)


def test_assay_compatibility_attestation_is_explicit_versioned_and_fail_closed() -> None:
    expected = {
        "schema_version": "glio-proteogen.kncc-assay-compatibility-attestation/1.0.0",
        "compatibility_profile_id": "kncc-pdc000514-tmt11-unshared-log2-ratio/1.0.0",
        "source_profile_content_digest": (
            "sha256:5583ee3a1d75bcd3997d12ff2102ec19fd83e49b2ec98f4f2bd9a0b6475d92a3"
        ),
        "assay": "tmt11_plexed_mass_spectrometry",
        "quantification": "unshared_peptide_protein_abundance_ratio",
        "value_transformation": "log2_ratio",
        "log_base": 2,
        "invariant_across_time_points": True,
        "attested_compatible": True,
    }
    assert REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json") == expected
    assert AssayCompatibilityAttestation.model_validate(expected) == (REQUIRED_ASSAY_COMPATIBILITY)
    assert _request().normalization_reference.abundance_scale == (
        "caller_supplied_log2_protein_abundance_ratio"
    )

    for field in expected:
        incomplete = dict(expected)
        incomplete.pop(field)
        with pytest.raises(ValidationError, match=field):
            AssayCompatibilityAttestation.model_validate(incomplete)

    incompatible_values: dict[str, object] = {
        "schema_version": "glio-proteogen.kncc-assay-compatibility-attestation/2.0.0",
        "compatibility_profile_id": "other-profile/1.0.0",
        "source_profile_content_digest": OTHER_DIGEST,
        "assay": "label_free_mass_spectrometry",
        "quantification": "shared_peptide_protein_abundance_ratio",
        "value_transformation": "natural_log_ratio",
        "log_base": 10,
        "invariant_across_time_points": False,
        "attested_compatible": False,
    }
    for field, value in incompatible_values.items():
        incompatible = dict(expected)
        incompatible[field] = value
        with pytest.raises(ValidationError, match=field):
            AssayCompatibilityAttestation.model_validate(incompatible)

    request_document = _request().model_dump(mode="json")
    request_document.pop("assay_compatibility")
    with pytest.raises(ValidationError, match="assay_compatibility"):
        LongitudinalGbmRequest.model_validate(request_document)


def test_observation_state_machine_accepts_all_explicit_states() -> None:
    assert _observation().state is ProteinEvidenceState.OBSERVED
    assert _observation(state=ProteinEvidenceState.LEFT_CENSORED).log_abundance == 1.0
    missing = _observation(
        state=ProteinEvidenceState.MISSING,
        abundance=None,
        standard_error=None,
        quality=0.0,
    )
    unsupported = _observation(
        state=ProteinEvidenceState.UNSUPPORTED,
        abundance=None,
        standard_error=None,
        quality=0.0,
    )
    assert missing.log_abundance is None
    assert unsupported.quality_weight == 0.0


@pytest.mark.parametrize(
    ("state", "abundance", "standard_error", "quality", "message"),
    [
        (ProteinEvidenceState.OBSERVED, None, 0.2, 1.0, "require log abundance"),
        (ProteinEvidenceState.LEFT_CENSORED, 1.0, None, 1.0, "require log abundance"),
        (ProteinEvidenceState.OBSERVED, 1.0, 0.2, 0.0, "positive quality"),
        (ProteinEvidenceState.MISSING, 1.0, None, 0.0, "cannot carry numeric"),
        (ProteinEvidenceState.UNSUPPORTED, None, 0.2, 0.0, "cannot carry numeric"),
        (ProteinEvidenceState.MISSING, None, None, 1.0, "must have zero quality"),
    ],
)
def test_observation_state_machine_rejects_incompatible_values(
    state: ProteinEvidenceState,
    abundance: float | None,
    standard_error: float | None,
    quality: float,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _observation(
            state=state,
            abundance=abundance,
            standard_error=standard_error,
            quality=quality,
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_observations_and_offsets_reject_nonfinite_numbers(value: float) -> None:
    with pytest.raises(ValidationError):
        _observation(abundance=value)
    with pytest.raises(ValidationError):
        _time_point("time.nonfinite", value)


def test_observation_numeric_domain_is_bounded_for_safe_log2_computation() -> None:
    assert _observation(abundance=-100.0, standard_error=20.0).log_abundance == -100.0
    with pytest.raises(ValidationError):
        _observation(abundance=-100.000001)
    with pytest.raises(ValidationError):
        _observation(abundance=100.000001)
    with pytest.raises(ValidationError):
        _observation(standard_error=20.000001)


def test_time_point_rejects_duplicate_observation_and_gene_ids() -> None:
    with pytest.raises(ValidationError, match="observation identifiers must be unique"):
        _time_point(
            "time.duplicate-observation",
            0.0,
            observations=(
                _observation("EGFR", identifier="obs.same"),
                _observation("PTEN", identifier="obs.same"),
            ),
        )
    with pytest.raises(ValidationError, match="HGNC gene symbols must be unique"):
        _time_point(
            "time.duplicate-gene",
            0.0,
            observations=(
                _observation("EGFR", identifier="obs.a"),
                _observation("EGFR", identifier="obs.b"),
            ),
        )


def test_request_enforces_order_identity_reference_and_total_limit() -> None:
    request = _request()
    assert request.bootstrap_replicates == DEFAULT_BOOTSTRAPS
    assert request.request_digest == canonical_request_digest(request)

    with pytest.raises(ValidationError, match="time-point identifiers must be unique"):
        _request(points=(_time_point("time.same", 0.0), _time_point("time.same", 1.0)))
    with pytest.raises(ValidationError, match="strictly increasing"):
        _request(points=(_time_point("time.a", 1.0), _time_point("time.b", 1.0)))
    with pytest.raises(ValidationError, match="strictly increasing"):
        _request(points=(_time_point("time.a", 2.0), _time_point("time.b", 1.0)))
    with pytest.raises(ValidationError, match="invariant request normalization"):
        _request(
            points=(
                _time_point("time.a", 0.0),
                _time_point("time.b", 1.0, normalization_digest=OTHER_DIGEST),
            )
        )
    with pytest.raises(ValidationError, match="unique across the series"):
        _request(
            points=(
                _time_point(
                    "time.a",
                    0.0,
                    observations=(_observation(identifier="obs.same"),),
                ),
                _time_point(
                    "time.b",
                    1.0,
                    observations=(_observation(identifier="obs.same"),),
                ),
            )
        )

    points: list[LongitudinalTimePoint] = []
    for point_index in range(3):
        observations = tuple(
            _observation(
                f"G{gene_index:04d}",
                identifier=f"obs.{point_index}.{gene_index:04d}",
            )
            for gene_index in range(4_001)
        )
        points.append(
            _time_point(f"time.{point_index}", float(point_index), observations=observations)
        )
    with pytest.raises(ValidationError, match="limited to 12000"):
        _request(points=tuple(points))


def test_request_cardinality_bootstrap_and_hgnc_constraints_are_strict() -> None:
    with pytest.raises(ValidationError):
        LongitudinalGbmRequest(
            series_id="series.too-short",
            assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
            normalization_reference=_normalization(),
            time_points=(_time_point("time.only", 0.0),),
        )
    with pytest.raises(ValidationError):
        LongitudinalGbmRequest(
            series_id="series.low-bootstrap",
            assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
            normalization_reference=_normalization(),
            time_points=(
                _time_point("time.low.a", 0.0),
                _time_point("time.low.b", 1.0),
            ),
            bootstrap_replicates=31,
        )
    with pytest.raises(ValidationError):
        LongitudinalGbmRequest.model_validate(
            {**_request().model_dump(mode="json"), "bootstrap_replicates": 257}
        )
    with pytest.raises(ValidationError):
        _observation("egfr")
    with pytest.raises(ValidationError):
        _observation(standard_error=0.0)
    with pytest.raises(ValidationError):
        _observation(quality=1.01)


def test_canonical_request_preserves_time_and_normalizes_protein_order() -> None:
    request = _request(
        points=(
            _time_point(
                "time.primary",
                0.0,
                observations=(
                    _observation("PTEN", identifier="obs.pten.primary"),
                    _observation("EGFR", identifier="obs.egfr.primary"),
                ),
            ),
            _time_point(
                "time.recurrence",
                1.0,
                observations=(
                    _observation("PTEN", identifier="obs.pten.recurrence"),
                    _observation("EGFR", identifier="obs.egfr.recurrence"),
                ),
            ),
        )
    )
    reordered_document = request.model_dump(mode="json")
    for point in reordered_document["time_points"]:
        point["observations"].reverse()
    assert canonical_request_digest(reordered_document) == request.request_digest
    assert [point["time_point_id"] for point in normalized_request(request)["time_points"]] == [
        "time.primary",
        "time.recurrence",
    ]

    original = deepcopy(reordered_document)
    normalized = normalized_request(reordered_document)
    assert reordered_document == original
    assert normalized is not reordered_document
    assert normalized["time_points"][0]["observations"][0]["gene_symbol"] == "EGFR"


def test_computational_digest_uses_only_active_numeric_evidence() -> None:
    request = _request(
        points=(
            _time_point(
                "time.primary",
                0.0,
                observations=(
                    _observation("EGFR", identifier="obs.egfr.primary"),
                    _observation(
                        "PTEN",
                        identifier="obs.pten.primary",
                        state=ProteinEvidenceState.MISSING,
                        abundance=None,
                        standard_error=None,
                        quality=0.0,
                    ),
                ),
            ),
            _time_point(
                "time.recurrence",
                1.0,
                observations=(
                    _observation(
                        "EGFR",
                        identifier="obs.egfr.recurrence",
                        state=ProteinEvidenceState.LEFT_CENSORED,
                    ),
                ),
            ),
        )
    )
    digest = computational_request_digest(request, profile_digest=DIGEST)
    document = request.model_dump(mode="json")
    document["series_id"] = "series.changed"
    document["time_points"][0]["observations"][0]["provenance_digest"] = OTHER_DIGEST
    document["time_points"][0]["observations"][1]["provenance_digest"] = OTHER_DIGEST
    assert computational_request_digest(document, profile_digest=DIGEST) == digest
    assert computational_request_digest(document, profile_digest=OTHER_DIGEST) != digest
    document["assay_compatibility"]["assay"] = "incompatible_assay"
    assert computational_request_digest(document, profile_digest=DIGEST) != digest


def test_canonical_json_is_sorted_unicode_finite_and_typed() -> None:
    assert canonical_json_bytes({"z": "PKCδ", "a": 1}) == b'{"a":1,"z":"PKC\xce\xb4"}'
    assert sha256_digest({"a": 1}).startswith("sha256:")
    with pytest.raises(ValueError, match="Out of range float"):
        canonical_json_bytes({"bad": math.nan})


@pytest.mark.parametrize(
    "candidate",
    [
        {"state": UncertaintyState.ESTIMATED, "standard_error": None, "replicates": 128},
        {"state": UncertaintyState.ESTIMATED, "standard_error": 0.1, "replicates": 0},
    ],
)
def test_estimated_uncertainty_requires_statistics(candidate: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="requires a standard error"):
        TransitionUncertainty(
            state=candidate["state"],
            standard_error=candidate["standard_error"],
            bootstrap_replicates_used=candidate["replicates"],
        )


def test_uncertainty_state_machine_rejects_other_invalid_combinations() -> None:
    with pytest.raises(ValidationError, match="cannot carry an abstention reason"):
        TransitionUncertainty(
            state=UncertaintyState.ESTIMATED,
            standard_error=0.1,
            bootstrap_replicates_used=32,
            reason="not allowed",
        )
    with pytest.raises(ValidationError, match="cannot carry numeric"):
        TransitionUncertainty(
            state=UncertaintyState.NOT_ESTIMABLE,
            standard_error=0.1,
            bootstrap_replicates_used=0,
            reason="unsupported",
        )
    with pytest.raises(ValidationError, match="reason and zero"):
        TransitionUncertainty(
            state=UncertaintyState.NOT_ESTIMABLE,
            bootstrap_replicates_used=1,
            reason="unsupported",
        )
    with pytest.raises(ValidationError, match="reason and zero"):
        TransitionUncertainty(
            state=UncertaintyState.NOT_ESTIMABLE,
            bootstrap_replicates_used=0,
        )
    assert _uncertainty().variance_fraction == 0.5
    assert _uncertainty(UncertaintyState.NOT_ESTIMABLE).reason is not None

    with pytest.raises(ValidationError, match="requires covariance statistics"):
        UncertaintyInteraction(
            state=UncertaintyState.ESTIMATED,
            covariance=0.1,
            bootstrap_replicates_used=32,
        )
    with pytest.raises(ValidationError, match="cannot carry a reason"):
        UncertaintyInteraction.model_validate(
            {
                **_interaction().model_dump(mode="python"),
                "reason": "not allowed",
            }
        )
    with pytest.raises(ValidationError, match="cannot carry numeric statistics"):
        UncertaintyInteraction(
            state=UncertaintyState.NOT_ESTIMABLE,
            covariance=0.1,
            bootstrap_replicates_used=0,
            reason="unsupported",
        )
    with pytest.raises(ValidationError, match="reason and zero"):
        UncertaintyInteraction(
            state=UncertaintyState.NOT_ESTIMABLE,
            bootstrap_replicates_used=1,
            reason="unsupported",
        )
    with pytest.raises(ValidationError, match="reason and zero"):
        UncertaintyInteraction(
            state=UncertaintyState.NOT_ESTIMABLE,
            bootstrap_replicates_used=0,
        )
    assert _interaction().variance_contribution == -0.02


def _source_processing_ablation(**overrides: Any) -> SourceProcessingAblation:
    values: dict[str, Any] = {
        "comparison": "ordinary Log versus Unshared Log source processing",
        "support": AnalysisSupport.SUPPORTED,
        "score_without_component": 0.7,
        "score_delta": 0.1,
        "classification_without_component": TransitionClassification.SOURCE_RECURRENCE_ALIGNED,
    }
    values.update(overrides)
    return SourceProcessingAblation(**values)


def test_ablation_state_machine_is_explicit() -> None:
    assert _source_processing_ablation().score_delta == 0.1
    assert (
        _source_processing_ablation(
            support=AnalysisSupport.LIMITED,
            reason="ordinary Log support is sparse",
        ).support
        is AnalysisSupport.LIMITED
    )
    assert (
        _source_processing_ablation(
            support=AnalysisSupport.ABSTAINED,
            score_without_component=None,
            score_delta=None,
            classification_without_component=TransitionClassification.NOT_ESTIMABLE,
            reason="alternate source processing unavailable",
        ).reason
        == "alternate source processing unavailable"
    )

    invalid: list[tuple[dict[str, Any], str]] = [
        ({"support": AnalysisSupport.ABSTAINED, "reason": "x"}, "cannot carry numeric"),
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "score_without_component": None,
                "score_delta": None,
                "reason": "x",
            },
            "must be not_estimable",
        ),
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "score_without_component": None,
                "score_delta": None,
                "classification_without_component": TransitionClassification.NOT_ESTIMABLE,
                "reason": None,
            },
            "require a reason",
        ),
        ({"score_without_component": None}, "require score and score delta"),
        (
            {"classification_without_component": TransitionClassification.NOT_ESTIMABLE},
            "cannot be not_estimable",
        ),
        ({"reason": "x"}, "supported ablations cannot"),
        ({"support": AnalysisSupport.LIMITED}, "limited ablations require"),
    ]
    for overrides, message in invalid:
        with pytest.raises(ValidationError, match=message):
            _source_processing_ablation(**overrides)


def test_driver_and_top_driver_ablation_preserve_evidence_identity() -> None:
    driver = SignedProteinDriver(
        gene_symbol="EGFR",
        source_gene_label="EGFR",
        from_observation_id="obs.egfr.primary",
        to_observation_id="obs.egfr.recurrence",
        from_provenance_digest=DIGEST,
        to_provenance_digest=OTHER_DIGEST,
        from_state=ProteinEvidenceState.OBSERVED,
        to_state=ProteinEvidenceState.LEFT_CENSORED,
        value_semantics="upper_bound",
        standardized_delta=1.0,
        model_coefficient=0.4,
        signed_contribution=0.4,
        direction=DriverDirection.SOURCE_RECURRENCE_ALIGNED,
        reliability_weight=0.8,
        source_feature_support=104,
    )
    ablation = TopDriverAblation(
        omitted_gene_symbol="EGFR",
        omitted_signed_contribution=driver.signed_contribution,
        support=AnalysisSupport.SUPPORTED,
        score_without_component=0.4,
        score_delta=0.4,
        classification_without_component=TransitionClassification.INDETERMINATE,
    )
    assert driver.to_provenance_digest == OTHER_DIGEST
    assert ablation.omitted_gene_symbol == "EGFR"


def _abstained_transition(**overrides: Any) -> TransitionEvidence:
    values: dict[str, Any] = {
        "support": AnalysisSupport.ABSTAINED,
        "classification": TransitionClassification.NOT_ESTIMABLE,
        "score": None,
        "lower": None,
        "upper": None,
        "replicates": 0,
        "percentile": None,
        "measurement": _uncertainty(UncertaintyState.NOT_ESTIMABLE),
        "coefficient": _uncertainty(UncertaintyState.NOT_ESTIMABLE),
        "interaction": _interaction(UncertaintyState.NOT_ESTIMABLE),
        "reasons": ("insufficient overlap",),
    }
    values.update(overrides)
    return _transition(**values)


def test_transition_state_machine_accepts_supported_limited_and_abstained() -> None:
    assert _transition().score == 0.8
    assert (
        _transition(
            support=AnalysisSupport.LIMITED,
            reasons=("coverage below supported threshold",),
        ).support
        is AnalysisSupport.LIMITED
    )
    assert _abstained_transition().classification is TransitionClassification.NOT_ESTIMABLE


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"classification": TransitionClassification.INDETERMINATE}, "must be not_estimable"),
        ({"score": 0.0}, "cannot carry an interval"),
        ({"lower": 0.0}, "cannot carry an interval"),
        ({"upper": 0.0}, "cannot carry an interval"),
        ({"percentile": 0.5}, "cannot carry a source-support"),
        ({"replicates": 1}, "reasons and zero"),
        ({"reasons": ()}, "reasons and zero"),
        ({"measurement": _uncertainty()}, "non-estimable uncertainty"),
        ({"coefficient": _uncertainty()}, "non-estimable uncertainty"),
        ({"interaction": _interaction()}, "non-estimable uncertainty"),
    ],
)
def test_abstained_transition_rejects_incompatible_outputs(
    overrides: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _abstained_transition(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"score": None}, "complete 90%"),
        ({"lower": None}, "complete 90%"),
        ({"upper": None}, "complete 90%"),
        ({"lower": 0.9, "upper": 1.1}, "must contain"),
        ({"classification": TransitionClassification.NOT_ESTIMABLE}, "cannot be not_estimable"),
        ({"percentile": None}, "source-support percentile"),
        ({"replicates": 0}, "require bootstrap"),
        (
            {"measurement": _uncertainty(UncertaintyState.NOT_ESTIMABLE)},
            "both uncertainty components",
        ),
        (
            {"coefficient": _uncertainty(UncertaintyState.NOT_ESTIMABLE)},
            "both uncertainty components",
        ),
        (
            {"interaction": _interaction(UncertaintyState.NOT_ESTIMABLE)},
            "both uncertainty components",
        ),
        ({"reasons": ("unexpected",)}, "supported transitions cannot"),
        ({"support": AnalysisSupport.LIMITED}, "limited transitions require"),
    ],
)
def test_estimated_transition_rejects_incompatible_outputs(
    overrides: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _transition(**overrides)


def _boundary(index: int = 1, left: str = "time.0", right: str = "time.1") -> PeltBoundary:
    return PeltBoundary(
        boundary_index=index,
        left_time_point_id=left,
        right_time_point_id=right,
        cost_reduction=0.2,
        bootstrap_frequency=0.75,
    )


def _pelt(**overrides: Any) -> PeltAnalysis:
    values: dict[str, Any] = {
        "support": AnalysisSupport.SUPPORTED,
        "penalty": 1.0,
        "objective_value": 0.4,
        "bootstrap_replicates_used": 128,
        "boundaries": (_boundary(),),
    }
    values.update(overrides)
    return PeltAnalysis(**values)


def test_pelt_state_machine_and_unique_boundaries() -> None:
    assert _pelt().method == "exact_pelt_duration_normalized_transition_rate_huber_v2"
    assert _pelt(support=AnalysisSupport.LIMITED, reason="short series").reason == "short series"
    assert (
        _pelt(
            support=AnalysisSupport.ABSTAINED,
            objective_value=None,
            bootstrap_replicates_used=0,
            boundaries=(),
            reason="not requested",
        ).support
        is AnalysisSupport.ABSTAINED
    )

    invalid: list[tuple[dict[str, Any], str]] = [
        ({"support": AnalysisSupport.ABSTAINED, "reason": "x"}, "cannot carry results"),
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "objective_value": None,
                "bootstrap_replicates_used": 1,
                "boundaries": (),
                "reason": "x",
            },
            "reason and zero",
        ),
        (
            {
                "support": AnalysisSupport.ABSTAINED,
                "objective_value": None,
                "bootstrap_replicates_used": 0,
                "boundaries": (),
                "reason": None,
            },
            "reason and zero",
        ),
        ({"objective_value": None}, "requires objective and bootstraps"),
        ({"bootstrap_replicates_used": 0}, "requires objective and bootstraps"),
        ({"reason": "x"}, "supported PELT analysis cannot"),
        ({"support": AnalysisSupport.LIMITED}, "limited PELT analysis requires"),
        (
            {"boundaries": (_boundary(), _boundary())},
            "boundary indices must be unique",
        ),
    ]
    for overrides, message in invalid:
        with pytest.raises(ValidationError, match=message):
            _pelt(**overrides)


def _replace_provenance(**updates: Any) -> LongitudinalGbmProvenance:
    document = _provenance().model_dump(mode="python")
    document.update(updates)
    return LongitudinalGbmProvenance.model_validate(document)


def test_result_topology_provenance_and_digest_are_content_bound() -> None:
    result = _verified_result()
    assert result.result_digest == result_payload_digest(result)
    with pytest.raises(ValidationError, match="canonical result content"):
        LongitudinalGbmResult.model_validate(_unverified_result().model_dump(mode="python"))

    with pytest.raises(ValidationError, match="profile digest does not match"):
        _unverified_result(profile_digest=OTHER_DIGEST)
    with pytest.raises(ValidationError, match="request digest does not match"):
        _unverified_result(request_digest=OTHER_DIGEST)
    with pytest.raises(ValidationError, match="assay compatibility attestation digest"):
        _unverified_result(provenance=_replace_provenance(assay_compatibility_digest=OTHER_DIGEST))
    with pytest.raises(ValidationError, match="normalization/reference digest"):
        _unverified_result(
            normalization=NormalizationReference(
                reference_id="normalization.other",
                binding_digest=OTHER_DIGEST,
                normalization_method="other",
            )
        )
    with pytest.raises(ValidationError, match="time-point identifiers must be unique"):
        _unverified_result(time_ids=("time.primary", "time.primary"))
    with pytest.raises(ValidationError, match="exactly one transition"):
        _unverified_result(
            time_ids=("time.0", "time.1", "time.2"),
            transitions=(_transition(from_id="time.0", to_id="time.1"),),
        )
    with pytest.raises(ValidationError, match="transition identifiers must be unique"):
        _unverified_result(
            time_ids=("time.0", "time.1", "time.2"),
            transitions=(
                _transition(identifier="transition.same", from_id="time.0", to_id="time.1"),
                _transition(
                    identifier="transition.same",
                    index=1,
                    from_id="time.1",
                    to_id="time.2",
                ),
            ),
        )
    with pytest.raises(ValidationError, match="indices must be consecutive"):
        _unverified_result(transitions=(_transition(index=1),))
    with pytest.raises(ValidationError, match="endpoints must match"):
        _unverified_result(transitions=(_transition(from_id="time.wrong"),))


def test_result_validates_exact_pelt_boundaries_against_time_series() -> None:
    with pytest.raises(ValidationError, match="at least four"):
        _unverified_result(pelt=_pelt())

    transitions = (
        _transition(identifier="transition.0", from_id="time.0", to_id="time.1"),
        _transition(
            identifier="transition.1",
            index=1,
            from_id="time.1",
            to_id="time.2",
        ),
        _transition(
            identifier="transition.2",
            index=2,
            from_id="time.2",
            to_id="time.3",
        ),
        _transition(
            identifier="transition.3",
            index=3,
            from_id="time.3",
            to_id="time.4",
        ),
    )
    result = _unverified_result(
        time_ids=("time.0", "time.1", "time.2", "time.3", "time.4"),
        transitions=transitions,
        pelt=_pelt(boundaries=(_boundary(2, "time.1", "time.2"),)),
    )
    assert result.pelt_analysis is not None

    with pytest.raises(ValidationError, match="outside the time series"):
        _unverified_result(
            time_ids=("time.0", "time.1", "time.2", "time.3", "time.4"),
            transitions=transitions,
            pelt=_pelt(boundaries=(_boundary(4, "time.3", "time.4"),)),
        )
    with pytest.raises(ValidationError, match="endpoints do not match"):
        _unverified_result(
            time_ids=("time.0", "time.1", "time.2", "time.3", "time.4"),
            transitions=transitions,
            pelt=_pelt(boundaries=(_boundary(2, "time.wrong", "time.2"),)),
        )
    with pytest.raises(ValidationError, match="at least two transitions"):
        _unverified_result(
            time_ids=("time.0", "time.1", "time.2", "time.3", "time.4"),
            transitions=transitions,
            pelt=_pelt(boundaries=(_boundary(1, "time.0", "time.1"),)),
        )


def _constants(**updates: Any) -> LongitudinalAlgorithmConstants:
    values: dict[str, Any] = {
        "transition_estimator": "nested cross-fitted elastic-net source projection",
        "feature_scaling_policy": "source median and MAD",
        "missing_evidence_policy": "missing_and_unsupported_never_become_negative_v1",
        "censoring_policy": "one-sided left-censor bound",
        "measurement_uncertainty_policy": "request-digest deterministic bootstrap",
        "coefficient_uncertainty_policy": "frozen source coefficient bootstrap",
        "uncertainty_interaction_policy": "paired_bootstrap_covariance_identity_v1",
        "source_processing_ablation_policy": "ordinary versus unshared log source processing",
        "top_driver_ablation_policy": "exact leave-one-driver-out rescore",
        "change_point_estimator": "exact_pelt_duration_normalized_transition_rate_huber_v2",
        "pelt_time_axis_policy": "duration_normalized_transition_rates_per_90_days_v2",
        "huber_delta": 1.345,
        "location_ridge": 1e-6,
        "location_solver_iterations": 80,
        "location_search_bound": 20.0,
        "standard_error_floor": 0.05,
        "alignment_threshold": 0.25,
        "stable_threshold": 0.1,
        "supported_minimum_shared_genes": 20,
        "supported_minimum_coverage": 0.1,
        "supported_minimum_effective_sample_size": 10.0,
        "pelt_penalty": 1.0,
        "maximum_top_drivers": 10,
        "quantization_decimals": 8,
        "random_seed_bytes": 8,
    }
    values.update(updates)
    return LongitudinalAlgorithmConstants(**values)


def _counts(**updates: Any) -> LongitudinalSourceModelCounts:
    values: dict[str, Any] = {
        "excluded_specimen_label_count": 6,
        "excluded_patient_group_count": 5,
        "source_file_count": 2,
        "fitted_feature_count": 100,
        "nonzero_coefficient_count": 20,
        "nested_cv_outer_folds": 5,
        "nested_cv_inner_folds": 5,
    }
    values.update(updates)
    return LongitudinalSourceModelCounts(**values)


def _digests() -> LongitudinalSourceModelDigests:
    return LongitudinalSourceModelDigests(
        source_profile_content_digest=DIGEST,
        source_profile_artifact_digest=DIGEST,
        source_file_lock_digest=DIGEST,
        cohort_oracle_digest=DIGEST,
        feature_space_digest=DIGEST,
        transition_model_digest=DIGEST,
        coefficient_digest=DIGEST,
        bootstrap_digest=DIGEST,
        source_processing_ablation_digest=DIGEST,
        hgnc_complete_set_digest=DIGEST,
        source_to_hgnc_mapping_digest=DIGEST,
        engine_semantic_digest=DIGEST,
    )


def _profile_document() -> dict[str, Any]:
    return {
        "algorithm_id": "kncc-gbm-longitudinal-concordance",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-gbm-longitudinal-concordance/1.0.0",
        "model_id": "kncc-paired-protein-transition/1.0.0",
        "required_assay_compatibility": REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json"),
        "constants": _constants().model_dump(mode="json"),
        "counts": _counts().model_dump(mode="json"),
        "digests": _digests().model_dump(mode="json"),
        "numpy_version": "2.5.2",
        "demo_id": "kncc.synthetic.demo.v1",
        "demo_request_digest": DIGEST,
        "demo_semantic_oracle_digest": DIGEST,
        "source_attribution": (
            "Kim et al., Integrated proteogenomic characterization of glioblastoma evolution"
        ),
        "source_license": "source terms",
        "source_license_url": "https://proteomic.datacommons.cancer.gov/",
        "source_transformation_notice": "Derived model projection; source patient IDs omitted.",
        "profile_digest": OTHER_DIGEST,
        "safety_class": "research_use_only",
        "claim_ceiling": "protein_level_longitudinal_concordance_research_only_non_prescriptive",
        "interpretation": "source_aligned_transition_evidence_not_patient_evolution",
    }


def test_profile_counts_constants_and_digest_are_frozen() -> None:
    assert _counts().pdc_source_row_label_count == 11_323
    assert _counts().pdc_biological_row_label_count == 11_320
    assert _counts().aggregate_row_label_count == 3
    assert _counts().strict_paired_transition_count == 104
    assert _counts().hgnc_exact_approved_source_label_count == 11_232
    assert _counts().hgnc_unique_alias_source_label_count == 80
    assert _counts().hgnc_admitted_feature_count == 11_312
    with pytest.raises(ValidationError, match="cannot exceed HGNC-mapped"):
        _counts(fitted_feature_count=11_313, nonzero_coefficient_count=20)
    with pytest.raises(ValidationError, match="cannot exceed fitted features"):
        _counts(fitted_feature_count=10, nonzero_coefficient_count=11)
    with pytest.raises(ValidationError, match="stable threshold"):
        _constants(stable_threshold=0.25)

    document = _profile_document()
    document["profile_digest"] = profile_payload_digest(document)
    profile = LongitudinalGbmProfile.model_validate(document)
    assert profile.profile_digest == profile_payload_digest(profile)
    assert "not_patient_evolution" in profile.interpretation
    with pytest.raises(ValidationError, match="canonical profile content"):
        LongitudinalGbmProfile.model_validate(_profile_document())


def test_replay_union_accepts_unverified_receipts_and_outputs_exact_flags() -> None:
    unverified = _unverified_result()
    replay = ReplayVerificationRequest(request=_request(), result=unverified)
    assert isinstance(replay.result, UnverifiedLongitudinalGbmResult)
    verification = ReplayVerificationResult(
        verified=False,
        request_digest_match=False,
        profile_digest_match=True,
        result_digest_match=False,
        transition_semantic_match=False,
        pelt_semantic_match=True,
        semantic_match=False,
        recomputed_request_digest=DIGEST,
        recomputed_result_digest=OTHER_DIGEST,
        message="receipt differs from deterministic replay",
    )
    assert verification.verified is False


def test_models_are_strict_frozen_and_errors_share_one_lane_base() -> None:
    request = _request()
    with pytest.raises(ValidationError):
        LongitudinalGbmRequest.model_validate({**request.model_dump(mode="json"), "unknown": True})
    with pytest.raises(ValidationError):
        LongitudinalGbmRequest.model_validate(
            {**request.model_dump(mode="json"), "bootstrap_replicates": "128"}
        )
    with pytest.raises(ValidationError):
        request.bootstrap_replicates = 32  # type: ignore[misc]
    assert issubclass(SourceProfileIntegrityError, LongitudinalGbmError)
    assert issubclass(LongitudinalInferenceError, LongitudinalGbmError)
