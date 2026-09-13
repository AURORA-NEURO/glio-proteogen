"""Deterministic sparse projection for longitudinal PDC000515 phosphosites."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Final, Literal, cast

import numpy as np

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import (
    canonical_json_bytes,
    canonical_request_digest,
    computational_request_digest,
    result_payload_digest,
    sha256_digest,
)
from .catalog import PhosphositeFeature, load_phosphosite_transition_catalog
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    AnalysisSupport,
    CensoredPhosphositeBound,
    DriverDirection,
    FeatureFamilyAblation,
    LongitudinalGbmPhosphoRequest,
    LongitudinalGbmPhosphoResult,
    LongitudinalPhosphoProvenance,
    ModelViewEvidence,
    ModelViewSupport,
    PhosphositeEvidenceState,
    PhosphositeObservation,
    SignedPhosphositeDriver,
    TopDriverAblation,
    TransitionClassification,
    TransitionEvidence,
    TransitionUncertainty,
    UncertaintyInteraction,
    UncertaintyState,
)
from .errors import PhosphositeIdentityMismatchError, UnknownPhosphositeError
from .profile import CONSTANTS, algorithm_profile

_QUALITY_GATE_REASON: Final = (
    "source-model selection stability, full-refit convergence, bootstrap feature-selection "
    "stability, and independent interval calibration are not all affirmatively bound"
)
_BOOTSTRAP_REASON: Final = (
    "fewer than 64 estimable frozen coefficient projections for fully supported uncertainty"
)


@dataclass(frozen=True, slots=True)
class _ExactPair:
    feature: PhosphositeFeature
    from_observation: PhosphositeObservation
    to_observation: PhosphositeObservation
    delta: float
    standard_error: float
    reliability: float


@dataclass(frozen=True, slots=True)
class _CensoredPair:
    feature: PhosphositeFeature
    from_observation: PhosphositeObservation
    to_observation: PhosphositeObservation
    semantics: str | None
    standardized_bound: float | None


def _q(value: float) -> float:
    rounded = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if rounded == 0.0 else rounded


def _seed(digest: str) -> int:
    return int.from_bytes(bytes.fromhex(digest.removeprefix("sha256:"))[:8], "big") % (2**53)


def _transition_seed(numerical_digest: str, transition_index: int, replicate_digest: str) -> int:
    payload = f"{numerical_digest}:{transition_index}:{replicate_digest}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _classify_point(score: float) -> TransitionClassification:
    if score >= CONSTANTS.alignment_threshold:
        return TransitionClassification.SOURCE_RECURRENCE_ALIGNED
    if score <= -CONSTANTS.alignment_threshold:
        return TransitionClassification.REVERSE_ALIGNED
    if abs(score) <= CONSTANTS.stable_threshold:
        return TransitionClassification.STABLE
    return TransitionClassification.INDETERMINATE


def _classify_interval(lower: float, upper: float) -> TransitionClassification:
    if lower >= CONSTANTS.alignment_threshold:
        return TransitionClassification.SOURCE_RECURRENCE_ALIGNED
    if upper <= -CONSTANTS.alignment_threshold:
        return TransitionClassification.REVERSE_ALIGNED
    if lower >= -CONSTANTS.stable_threshold and upper <= CONSTANTS.stable_threshold:
        return TransitionClassification.STABLE
    return TransitionClassification.INDETERMINATE


def _source_quality_gate(catalog: object) -> bool:
    """Require every independently audited runtime gate; absence fails closed."""

    return all(
        getattr(catalog, field, False) is True
        for field in (
            "selection_stability_gate_passed",
            "bootstrap_full_refit_gate_passed",
            "bootstrap_feature_selection_stability_gate_passed",
            "bootstrap_calibration_gate_passed",
        )
    )


def _validate_observation_identity(
    observation: PhosphositeObservation,
    feature_by_id: dict[str, PhosphositeFeature],
) -> PhosphositeFeature:
    feature = feature_by_id.get(observation.phosphosite_id)
    if feature is None:
        raise UnknownPhosphositeError(
            "phosphosite_id is outside the exact source-locked PDC000515 inventory"
        )
    if observation.gene_symbol != feature.approved_gene:
        raise PhosphositeIdentityMismatchError(
            "phosphosite_id and approved HGNC gene symbol do not match the frozen crosswalk"
        )
    return feature


def _paired_evidence(
    from_observations: tuple[PhosphositeObservation, ...],
    to_observations: tuple[PhosphositeObservation, ...],
    feature_by_id: dict[str, PhosphositeFeature],
) -> tuple[dict[int, _ExactPair], tuple[_CensoredPair, ...]]:
    from_by_site: dict[str, PhosphositeObservation] = {}
    to_by_site: dict[str, PhosphositeObservation] = {}
    for observation in from_observations:
        _validate_observation_identity(observation, feature_by_id)
        from_by_site[observation.phosphosite_id] = observation
    for observation in to_observations:
        _validate_observation_identity(observation, feature_by_id)
        to_by_site[observation.phosphosite_id] = observation

    exact: dict[int, _ExactPair] = {}
    censored: list[_CensoredPair] = []
    for site in sorted(from_by_site.keys() & to_by_site.keys()):
        left = from_by_site[site]
        right = to_by_site[site]
        feature = feature_by_id[site]
        if left.state in {PhosphositeEvidenceState.MISSING, PhosphositeEvidenceState.UNSUPPORTED}:
            continue
        if right.state in {PhosphositeEvidenceState.MISSING, PhosphositeEvidenceState.UNSUPPORTED}:
            continue
        if (
            left.state is PhosphositeEvidenceState.OBSERVED
            and right.state is PhosphositeEvidenceState.OBSERVED
        ):
            if (
                left.log_abundance_ratio is None
                or right.log_abundance_ratio is None
                or left.standard_error is None
                or right.standard_error is None
            ):
                raise RuntimeError("validated active evidence lost required numerical values")
            quality = math.sqrt(left.quality_weight * right.quality_weight)
            exact[feature.index] = _ExactPair(
                feature=feature,
                from_observation=left,
                to_observation=right,
                delta=right.log_abundance_ratio - left.log_abundance_ratio,
                standard_error=math.sqrt(
                    left.standard_error**2 / left.quality_weight
                    + right.standard_error**2 / right.quality_weight
                ),
                reliability=quality,
            )
            continue
        semantics: str | None = None
        bound: float | None = None
        if (
            left.state is PhosphositeEvidenceState.LEFT_CENSORED
            and right.state is PhosphositeEvidenceState.OBSERVED
        ):
            if left.log_abundance_ratio is None or right.log_abundance_ratio is None:
                raise RuntimeError("validated censored evidence lost required numerical values")
            semantics = "lower_bound"
            if feature.transition_scale is not None:
                bound = (
                    right.log_abundance_ratio - left.log_abundance_ratio
                ) / feature.transition_scale
        elif (
            left.state is PhosphositeEvidenceState.OBSERVED
            and right.state is PhosphositeEvidenceState.LEFT_CENSORED
        ):
            if left.log_abundance_ratio is None or right.log_abundance_ratio is None:
                raise RuntimeError("validated censored evidence lost required numerical values")
            semantics = "upper_bound"
            if feature.transition_scale is not None:
                bound = (
                    right.log_abundance_ratio - left.log_abundance_ratio
                ) / feature.transition_scale
        censored.append(
            _CensoredPair(
                feature=feature,
                from_observation=left,
                to_observation=right,
                semantics=semantics,
                standardized_bound=bound,
            )
        )
    return exact, tuple(censored)


def _score(
    feature_indices: tuple[int, ...],
    coefficients: tuple[float, ...],
    exact: dict[int, _ExactPair],
    *,
    scales: tuple[float, ...] | None = None,
    perturbations: dict[int, float] | None = None,
    omitted: frozenset[int] = frozenset(),
) -> tuple[float | None, int, float]:
    numerator = 0.0
    denominator = 0.0
    count = 0
    resolved_scales = scales if scales is not None else (None,) * len(feature_indices)
    for index, coefficient, replicate_scale in zip(
        feature_indices, coefficients, resolved_scales, strict=True
    ):
        pair = exact.get(index)
        if pair is None or index in omitted:
            continue
        scale = replicate_scale if replicate_scale is not None else pair.feature.transition_scale
        if scale is None:
            raise RuntimeError("fitted projection referenced a suppressed source scale")
        delta = pair.delta + (perturbations.get(index, 0.0) if perturbations else 0.0)
        numerator += coefficient * delta / scale
        denominator += abs(coefficient)
        count += 1
    minimum_features = max(
        3,
        math.ceil(CONSTANTS.minimum_exact_feature_fraction * len(feature_indices)),
    )
    if count < minimum_features or denominator < CONSTANTS.minimum_coefficient_weight_coverage:
        return None, count, denominator
    return numerator / denominator, count, denominator


def _uncertainty_not_estimable(reason: str) -> TransitionUncertainty:
    return TransitionUncertainty(
        state=UncertaintyState.NOT_ESTIMABLE,
        reason=reason,
    )


def _interaction_not_estimable(reason: str) -> UncertaintyInteraction:
    return UncertaintyInteraction(state=UncertaintyState.NOT_ESTIMABLE, reason=reason)


def _coefficient_weighted_bound(
    semantics: Literal["upper_bound", "lower_bound"],
    standardized_bound: float,
    coefficient: float,
) -> tuple[Literal["upper_bound", "lower_bound"], float]:
    """Apply a signed model coefficient without losing inequality orientation."""

    if coefficient < 0.0:
        semantics = "upper_bound" if semantics == "lower_bound" else "lower_bound"
    return semantics, coefficient * standardized_bound


def _measurement_perturbations(
    exact: dict[int, _ExactPair],
    rng: np.random.Generator,
    cancellation: CancellationContext | None,
) -> dict[int, float]:
    """Draw measurement noise with bounded cooperative-cancellation latency."""

    perturbations: dict[int, float] = {}
    for offset, feature_index in enumerate(sorted(exact)):
        if offset % 64 == 0:
            checkpoint(cancellation)
        perturbations[feature_index] = float(rng.normal(0.0, exact[feature_index].standard_error))
    return perturbations


def _ablation(
    *,
    base_score: float,
    omitted: frozenset[int],
    exact: dict[int, _ExactPair],
    main_indices: tuple[int, ...],
    main_coefficients: tuple[float, ...],
    limited: bool,
) -> tuple[AnalysisSupport, float | None, float | None, TransitionClassification, str | None]:
    score, _, _ = _score(main_indices, main_coefficients, exact, omitted=omitted)
    if score is None:
        return (
            AnalysisSupport.ABSTAINED,
            None,
            None,
            TransitionClassification.NOT_ESTIMABLE,
            "ablation leaves insufficient exact fitted-feature overlap",
        )
    return (
        AnalysisSupport.LIMITED if limited else AnalysisSupport.SUPPORTED,
        _q(score),
        _q(base_score - score),
        _classify_point(score),
        _QUALITY_GATE_REASON if limited else None,
    )


def _abstained_transition(
    request: LongitudinalGbmPhosphoRequest,
    index: int,
    *,
    exact_count: int,
    censored: tuple[_CensoredPair, ...],
    coverage: float,
    reasons: tuple[str, ...],
) -> TransitionEvidence:
    point = request.time_points[index]
    following = request.time_points[index + 1]
    reason = "; ".join(reasons)
    return TransitionEvidence(
        transition_id=f"transition-{index}",
        transition_index=index,
        from_time_point_id=point.time_point_id,
        to_time_point_id=following.time_point_id,
        support=AnalysisSupport.ABSTAINED,
        classification=TransitionClassification.NOT_ESTIMABLE,
        bootstrap_replicates_used=0,
        exact_feature_count=exact_count,
        censored_feature_count=len(censored),
        effective_sample_size=0.0,
        coefficient_weight_coverage=_q(coverage),
        measurement_uncertainty=_uncertainty_not_estimable(reason),
        coefficient_uncertainty=_uncertainty_not_estimable(reason),
        uncertainty_interaction=_interaction_not_estimable(reason),
        abstention_reasons=reasons,
    )


def _transition(  # noqa: PLR0915
    request: LongitudinalGbmPhosphoRequest,
    index: int,
    *,
    numerical_digest: str,
    cancellation: CancellationContext | None,
) -> TransitionEvidence:
    catalog = load_phosphosite_transition_catalog()
    point = request.time_points[index]
    following = request.time_points[index + 1]
    exact, censored = _paired_evidence(
        point.observations, following.observations, catalog.feature_by_id
    )
    main = catalog.selected_features
    main_indices = tuple(feature.index for feature in main)
    main_coefficients = tuple(feature.coefficient for feature in main)
    score, exact_count, coverage = _score(main_indices, main_coefficients, exact)
    if score is None:
        reasons: list[str] = []
        if exact_count < max(
            3,
            math.ceil(CONSTANTS.minimum_exact_feature_fraction * len(main_indices)),
        ):
            reasons.append("fewer than half of fitted phosphosite groups have exact pairs")
        if coverage < CONSTANTS.minimum_coefficient_weight_coverage:
            reasons.append("less than half of the frozen absolute coefficient weight is observed")
        return _abstained_transition(
            request,
            index,
            exact_count=exact_count,
            censored=censored,
            coverage=coverage,
            reasons=tuple(reasons),
        )

    reliabilities = np.asarray(
        [
            exact[feature_index].reliability
            for feature_index in main_indices
            if feature_index in exact
        ]
    )
    ess = float(reliabilities.sum() ** 2 / np.square(reliabilities).sum())

    ordered_projections = sorted(
        catalog.bootstrap_projections,
        key=lambda projection: sha256_digest(
            {"request": numerical_digest, "replicate": projection.replicate_digest}
        ),
    )[: request.bootstrap_replicates]
    measurement_draws: list[float] = []
    coefficient_draws: list[float] = []
    combined_draws: list[float] = []
    for projection in ordered_projections:
        checkpoint(cancellation)
        coefficient_score, _, _ = _score(
            projection.feature_indices,
            projection.coefficients,
            exact,
            scales=projection.scales,
        )
        if coefficient_score is None:
            continue
        rng = np.random.default_rng(
            _transition_seed(numerical_digest, index, projection.replicate_digest)
        )
        perturbations = _measurement_perturbations(exact, rng, cancellation)
        measurement_score, _, _ = _score(
            main_indices,
            main_coefficients,
            exact,
            perturbations=perturbations,
        )
        if measurement_score is None:
            continue
        combined_score, _, _ = _score(
            projection.feature_indices,
            projection.coefficients,
            exact,
            scales=projection.scales,
            perturbations=perturbations,
        )
        if combined_score is None:
            continue
        measurement_draws.append(measurement_score)
        coefficient_draws.append(coefficient_score)
        combined_draws.append(combined_score)

    used = len(combined_draws)
    if used < request.bootstrap_replicates or used < 32:
        bootstrap_failure_reasons = ("insufficient estimable sparse coefficient projections",)
        return _abstained_transition(
            request,
            index,
            exact_count=exact_count,
            censored=censored,
            coverage=coverage,
            reasons=bootstrap_failure_reasons,
        )

    measurement = np.asarray(measurement_draws, dtype=np.float64)
    coefficient = np.asarray(coefficient_draws, dtype=np.float64)
    combined = np.asarray(combined_draws, dtype=np.float64)
    measurement_effect = measurement - score
    coefficient_effect = coefficient - score
    interaction_effect = combined - score - measurement_effect - coefficient_effect
    measurement_variance = float(np.var(measurement_effect, ddof=1))
    coefficient_variance = float(np.var(coefficient_effect, ddof=1))
    interaction_variance = float(np.var(interaction_effect, ddof=1))
    measurement_coefficient_covariance = float(
        np.cov(measurement_effect, coefficient_effect, ddof=1)[0, 1]
    )
    measurement_interaction_covariance = float(
        np.cov(measurement_effect, interaction_effect, ddof=1)[0, 1]
    )
    coefficient_interaction_covariance = float(
        np.cov(coefficient_effect, interaction_effect, ddof=1)[0, 1]
    )
    combined_variance = float(np.var(combined, ddof=1))
    quantized_measurement_variance = _q(max(0.0, measurement_variance))
    quantized_coefficient_variance = _q(max(0.0, coefficient_variance))
    quantized_interaction_variance = _q(max(0.0, interaction_variance))
    quantized_measurement_coefficient_covariance = _q(measurement_coefficient_covariance)
    quantized_measurement_interaction_covariance = _q(measurement_interaction_covariance)
    quantized_coefficient_interaction_covariance = _q(coefficient_interaction_covariance)
    quantized_interaction_contribution = _q(
        quantized_interaction_variance
        + 2.0
        * (
            quantized_measurement_coefficient_covariance
            + quantized_measurement_interaction_covariance
            + quantized_coefficient_interaction_covariance
        )
    )
    quantized_decomposed_variance = _q(
        quantized_measurement_variance
        + quantized_coefficient_variance
        + quantized_interaction_contribution
    )
    quantized_combined_variance = _q(max(0.0, combined_variance))
    quantized_residual = _q(quantized_combined_variance - quantized_decomposed_variance)
    component_total = (
        quantized_measurement_variance
        + quantized_coefficient_variance
        + quantized_interaction_variance
    )
    lower = min(float(np.quantile(combined, 0.05)), score)
    upper = max(float(np.quantile(combined, 0.95)), score)

    source_gate = _source_quality_gate(catalog)
    support_reasons: list[str] = []
    if not source_gate:
        support_reasons.append(_QUALITY_GATE_REASON)
    if used < 64:
        support_reasons.append(_BOOTSTRAP_REASON)
    support = AnalysisSupport.SUPPORTED if not support_reasons else AnalysisSupport.LIMITED

    drivers: list[SignedPhosphositeDriver] = []
    for feature in main:
        pair = exact.get(feature.index)
        if pair is None:
            continue
        if feature.transition_scale is None:
            raise RuntimeError("selected feature lost its released source scale")
        standardized = pair.delta / feature.transition_scale
        contribution = feature.coefficient * standardized / coverage
        drivers.append(
            SignedPhosphositeDriver(
                phosphosite_id=feature.phosphosite_id,
                gene_symbol=feature.approved_gene,
                hgnc_id=feature.hgnc_id,
                site_cardinality=feature.site_cardinality,
                composite_site_group=feature.composite_site_group,
                from_observation_id=pair.from_observation.observation_id,
                to_observation_id=pair.to_observation.observation_id,
                from_provenance_digest=pair.from_observation.provenance_digest,
                to_provenance_digest=pair.to_observation.provenance_digest,
                value_semantics="exact_delta",
                standardized_delta=_q(standardized),
                model_coefficient=_q(feature.coefficient),
                signed_contribution=_q(contribution),
                direction=(
                    DriverDirection.SOURCE_RECURRENCE_ALIGNED
                    if contribution >= 0.0
                    else DriverDirection.REVERSE_ALIGNED
                ),
                reliability_weight=_q(pair.reliability),
                source_pair_support=feature.paired_support,
                bootstrap_selection_stability=_q(feature.bootstrap_selection_stability),
                sphinks_source_site_label=feature.sphinks_source_site_label,
                sphinks_signature_kinases=feature.sphinks_signature_kinases,
            )
        )
    drivers.sort(key=lambda item: (-abs(item.signed_contribution), item.phosphosite_id))
    top_drivers = tuple(drivers[: CONSTANTS.maximum_top_drivers])

    bounds: list[CensoredPhosphositeBound] = []
    selected_index = {feature.index for feature in main}
    for item in censored:
        if (
            item.feature.index not in selected_index
            or item.semantics is None
            or item.standardized_bound is None
        ):
            continue
        source_semantics = cast("Literal['upper_bound', 'lower_bound']", item.semantics)
        bound_semantics, weighted = _coefficient_weighted_bound(
            source_semantics,
            item.standardized_bound,
            item.feature.coefficient,
        )
        bounds.append(
            CensoredPhosphositeBound(
                phosphosite_id=item.feature.phosphosite_id,
                gene_symbol=item.feature.approved_gene,
                value_semantics=bound_semantics,
                standardized_bound=_q(item.standardized_bound),
                coefficient_weighted_bound=_q(weighted),
                from_observation_id=item.from_observation.observation_id,
                to_observation_id=item.to_observation.observation_id,
            )
        )
    bounds.sort(key=lambda item: item.phosphosite_id)

    limited = support is AnalysisSupport.LIMITED
    family_ablations: list[FeatureFamilyAblation] = []
    for component, omitted in (
        (
            "composite_site_groups",
            frozenset(feature.index for feature in main if feature.composite_site_group),
        ),
        (
            "exact_sphinks_crosswalk_sites",
            frozenset(
                feature.index for feature in main if feature.sphinks_source_site_label is not None
            ),
        ),
    ):
        ablation = _ablation(
            base_score=score,
            omitted=omitted,
            exact=exact,
            main_indices=main_indices,
            main_coefficients=main_coefficients,
            limited=limited,
        )
        family_component = cast(
            "Literal['composite_site_groups', 'exact_sphinks_crosswalk_sites']",
            component,
        )
        family_ablations.append(
            FeatureFamilyAblation(
                component=family_component,
                omitted_feature_count=len(omitted),
                support=ablation[0],
                score_without_component=ablation[1],
                score_delta=ablation[2],
                classification_without_component=ablation[3],
                reason=ablation[4],
            )
        )

    top_ablations: list[TopDriverAblation] = []
    by_id = catalog.feature_by_id
    for driver in top_drivers:
        feature = by_id[driver.phosphosite_id]
        ablation = _ablation(
            base_score=score,
            omitted=frozenset({feature.index}),
            exact=exact,
            main_indices=main_indices,
            main_coefficients=main_coefficients,
            limited=limited,
        )
        top_ablations.append(
            TopDriverAblation(
                omitted_phosphosite_id=driver.phosphosite_id,
                omitted_signed_contribution=driver.signed_contribution,
                support=ablation[0],
                score_without_component=ablation[1],
                score_delta=ablation[2],
                classification_without_component=ablation[3],
                reason=ablation[4],
            )
        )

    source_pair_coverage_weighted_mean = (
        sum(
            abs(feature.coefficient) * feature.paired_coverage
            for feature in main
            if feature.index in exact
        )
        / coverage
    )
    return TransitionEvidence(
        transition_id=f"transition-{index}",
        transition_index=index,
        from_time_point_id=point.time_point_id,
        to_time_point_id=following.time_point_id,
        support=support,
        classification=_classify_interval(lower, upper),
        score=_q(score),
        lower_bound=_q(lower),
        upper_bound=_q(upper),
        bootstrap_replicates_used=used,
        exact_feature_count=exact_count,
        censored_feature_count=len(censored),
        effective_sample_size=_q(ess),
        coefficient_weight_coverage=_q(coverage),
        source_pair_coverage_weighted_mean=_q(source_pair_coverage_weighted_mean),
        measurement_uncertainty=TransitionUncertainty(
            state=UncertaintyState.ESTIMATED,
            standard_error=_q(math.sqrt(max(0.0, measurement_variance))),
            variance=quantized_measurement_variance,
            variance_fraction=_q(
                quantized_measurement_variance / component_total if component_total > 0.0 else 0.0
            ),
            bootstrap_replicates_used=used,
        ),
        coefficient_uncertainty=TransitionUncertainty(
            state=UncertaintyState.ESTIMATED,
            standard_error=_q(math.sqrt(max(0.0, coefficient_variance))),
            variance=quantized_coefficient_variance,
            variance_fraction=_q(
                quantized_coefficient_variance / component_total if component_total > 0.0 else 0.0
            ),
            bootstrap_replicates_used=used,
        ),
        uncertainty_interaction=UncertaintyInteraction(
            state=UncertaintyState.ESTIMATED,
            interaction_standard_error=_q(math.sqrt(max(0.0, interaction_variance))),
            interaction_variance=quantized_interaction_variance,
            interaction_variance_fraction=_q(
                quantized_interaction_variance / component_total if component_total > 0.0 else 0.0
            ),
            measurement_coefficient_covariance=(quantized_measurement_coefficient_covariance),
            measurement_interaction_covariance=(quantized_measurement_interaction_covariance),
            coefficient_interaction_covariance=(quantized_coefficient_interaction_covariance),
            variance_contribution=quantized_interaction_contribution,
            combined_variance=quantized_combined_variance,
            decomposed_variance=quantized_decomposed_variance,
            decomposition_residual=quantized_residual,
            bootstrap_replicates_used=used,
        ),
        top_drivers=top_drivers,
        censored_bounds=tuple(bounds),
        feature_family_ablations=tuple(family_ablations),
        top_driver_ablations=tuple(top_ablations),
        abstention_reasons=tuple(support_reasons),
    )


def infer_longitudinal_gbm_phospho(
    request: LongitudinalGbmPhosphoRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmPhosphoResult:
    """Apply the locked raw phosphosite axis without retaining caller evidence."""

    checkpoint(cancellation)
    if request.assay_compatibility != REQUIRED_ASSAY_COMPATIBILITY:
        raise ValueError("request assay compatibility does not match the exact fitted profile")
    profile = algorithm_profile()
    catalog = load_phosphosite_transition_catalog()
    request_digest = canonical_request_digest(request)
    computational_digest = computational_request_digest(
        request, profile_digest=profile.profile_digest
    )
    numerical_digest = sha256_digest(
        {
            "computational_digest": computational_digest,
            "source_artifact": catalog.artifact_digest,
            "bootstrap_ensemble": catalog.bootstrap_digest,
        }
    )
    transitions = tuple(
        _transition(
            request,
            index,
            numerical_digest=numerical_digest,
            cancellation=cancellation,
        )
        for index in range(len(request.time_points) - 1)
    )
    provenance_digests = tuple(
        sorted(
            {
                observation.provenance_digest
                for point in request.time_points
                for observation in point.observations
            }
        )
    )
    payload: dict[str, object] = {
        "algorithm_id": "kncc-gbm-longitudinal-phosphosite-concordance",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-gbm-longitudinal-phosphosite-concordance/1.0.0",
        "profile_digest": profile.profile_digest,
        "request_digest": request_digest,
        "series_id": request.series_id,
        "assay_compatibility": request.assay_compatibility.model_dump(mode="json"),
        "normalization_reference": request.normalization_reference.model_dump(mode="json"),
        "time_point_ids": [point.time_point_id for point in request.time_points],
        "transitions": [transition.model_dump(mode="json") for transition in transitions],
        "model_views": [
            ModelViewEvidence(
                view="raw_phosphosite_transition",
                support=ModelViewSupport.FITTED,
                reason="the frozen PDC000515 raw phosphosite transition axis is fitted",
            ).model_dump(mode="json"),
            ModelViewEvidence(
                view="occupancy_like",
                support=ModelViewSupport.NOT_FITTED,
                reason=(
                    "cognate-protein adjustment has no leakage-safe fitted model in this profile"
                ),
            ).model_dump(mode="json"),
            ModelViewEvidence(
                view="protein_phosphosite_fusion",
                support=ModelViewSupport.NOT_FITTED,
                reason="cross-assay protein/phosphosite fusion is not fitted and is never implicit",
            ).model_dump(mode="json"),
        ],
        "provenance": LongitudinalPhosphoProvenance(
            request_digest=request_digest,
            profile_digest=profile.profile_digest,
            source_artifact_content_digest=catalog.artifact_digest,
            source_artifact_byte_digest=catalog.artifact_sha256,
            source_profile_digest=catalog.source_profile_digest,
            source_manifest_digest=catalog.source_manifest_digest,
            source_attestation_state="verified_exact_snapshots",
            bootstrap_ensemble_digest=catalog.bootstrap_digest,
            sphinks_crosswalk_digest=catalog.crosswalk_digest,
            hgnc_mapping_digest=catalog.hgnc_mapping_digest,
            engine_semantic_digest=profile.digests.engine_semantic_digest,
            assay_compatibility_digest=sha256_digest(
                request.assay_compatibility.model_dump(mode="json")
            ),
            normalization_reference_digest=request.normalization_reference.binding_digest,
            computational_digest=computational_digest,
            numerical_seed_digest=numerical_digest,
            bootstrap_seed=_seed(numerical_digest),
            observation_source_digests=provenance_digests,
            numpy_version=np.__version__,
            source_attribution=catalog.source_attribution,
            source_license=catalog.source_license,
            source_license_url=catalog.source_license_url,
            source_transformation_notice=catalog.source_transformation_notice,
            sphinks_crosswalk_provenance=profile.sphinks_crosswalk_provenance,
        ).model_dump(mode="json"),
        "output_semantics": "raw_phosphosite_longitudinal_source_concordance",
        "limitations": [
            "Research use only; not diagnostic, prognostic, prescriptive, or clinically validated.",
            "The score measures source-cohort raw phosphosite transition concordance, not recurrence prediction.",
            "Composite source site groups remain indivisible and cannot localize independent residues.",
            "Censored bounds are retained but never imputed into the fitted point projection.",
            "Measurement perturbations assume featurewise-independent Gaussians and combine from/to standard errors in quadrature; the request cannot represent shared-reference, TMT, or batch covariance.",
            "The SPHINKS crosswalk annotates exact drivers only; this lane does not infer kinase activity.",
            "Occupancy-like adjustment and protein/phosphosite fusion are explicitly not fitted.",
        ],
        "research_use_only": True,
        "non_prescriptive": True,
        "infers_kinase_activity": False,
    }
    payload["result_digest"] = result_payload_digest(payload)
    checkpoint(cancellation)
    return LongitudinalGbmPhosphoResult.model_validate_json(canonical_json_bytes(payload))


__all__ = ["infer_longitudinal_gbm_phospho"]
