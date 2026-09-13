"""Deterministic KNCC longitudinal protein-concordance numerical engine."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Final, Literal, cast

import numpy as np
from numpy.typing import NDArray

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import (
    canonical_request_digest,
    computational_request_digest,
    result_payload_digest,
    sha256_digest,
)
from .catalog import (
    KnccLongitudinalCatalog,
    KnccProteinFeature,
    SparseCoefficientReplicate,
    longitudinal_gbm_catalog,
)
from .contracts import (
    MIN_BOOTSTRAPS,
    AnalysisSupport,
    AssayCompatibilityAttestation,
    DriverDirection,
    LongitudinalGbmProvenance,
    LongitudinalGbmRequest,
    LongitudinalGbmResult,
    PeltAnalysis,
    PeltBoundary,
    ProteinEvidenceState,
    ProteinObservation,
    SignedProteinDriver,
    SourceProcessingAblation,
    TopDriverAblation,
    TransitionClassification,
    TransitionEvidence,
    TransitionUncertainty,
    UncertaintyInteraction,
    UncertaintyState,
    UnverifiedLongitudinalGbmResult,
)
from .demo import EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
from .errors import LongitudinalInferenceError, SourceProfileIntegrityError
from .profile import CONSTANTS, algorithm_profile

FloatMatrix = NDArray[np.float64]

_ACTIVE_STATES: Final = frozenset(
    {ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED}
)
_MINIMUM_ESTIMATION_GENES: Final = 3
_MINIMUM_ESTIMATION_COVERAGE: Final = 0.10
_MINIMUM_ESTIMATION_ESS: Final = 2.0
_HUBER_DELTA: Final = CONSTANTS.huber_delta
_SEGMENT_SE_FLOOR: Final = CONSTANTS.standard_error_floor
_PELT_MIN_SEGMENT_TRANSITIONS: Final = CONSTANTS.pelt_minimum_segment_transitions
_PELT_RATE_REFERENCE_DAYS: Final = CONSTANTS.pelt_rate_reference_days
_LIMITATIONS: Final = (
    "Research-use-only protein concordance evidence; not a tumor-evolution determination.",
    "The score is relative to one frozen paired KNCC source-cohort protein axis.",
    (
        "Inputs must explicitly attest compatibility with PDC000514 TMT11 Unshared Log2 "
        "protein-abundance ratios; other assay or quantification scales are rejected."
    ),
    (
        "Deployment uses a robust bound-aware location over the frozen axis; it does not "
        "reproduce the source article's inference workflow."
    ),
    ("The coefficient ensemble is a fixed-scale, one-step source-cohort bootstrap approximation."),
    (
        "Paired-bootstrap measurement/coefficient covariance is reported explicitly; its "
        "variance decomposition remains descriptive and is not a calibrated probability."
    ),
    "Pairs with two left-censored limits are uninformative; one-sided limits remain bounds.",
    (
        "The source-processing ablation changes only the frozen source projection; caller "
        "quantification is unchanged."
    ),
    "Missingness, sampling, preprocessing, and cohort transport remain limitations.",
    "Interval classifications are descriptive and non-prescriptive.",
    (
        "PELT is exploratory segmentation of duration-normalized transition rates, not a "
        "biological progression or treatment-response detector."
    ),
)


@dataclass(frozen=True, slots=True)
class _ActivePair:
    feature: KnccProteinFeature
    from_observation: ProteinObservation
    to_observation: ProteinObservation
    from_time_point_index: int
    to_time_point_index: int
    expected_raw_delta: float
    value_semantics: Literal["exact_delta", "upper_bound", "lower_bound"]
    delta_standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _TransitionWork:
    evidence: TransitionEvidence
    combined_slots: tuple[float | None, ...]
    active_pairs: tuple[_ActivePair, ...]
    column_by_feature_index: dict[int, int]
    raw_delta_draws: FloatMatrix | None
    selected_replicates: tuple[SparseCoefficientReplicate, ...]


@dataclass(frozen=True, slots=True)
class _Partition:
    objective: float
    boundaries: tuple[int, ...]


def _quantize(value: float) -> float:
    result = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if result == 0.0 else result


def _quantize_probability(value: float) -> float:
    return min(1.0, max(0.0, _quantize(value)))


def _stream_seed(request_digest: str, stream: str) -> int:
    payload = f"{request_digest}:{stream}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[: CONSTANTS.random_seed_bytes], "big")


def _receipt_seed(request_digest: str) -> int:
    return _stream_seed(request_digest, "receipt-bootstrap-v1") % 2**53


def _checkpoint_stride(
    cancellation: CancellationContext | None,
    index: int,
    stride: int,
) -> None:
    if index % stride == 0:
        checkpoint(cancellation)


def _sample_reported_log_value(
    observation: ProteinObservation,
    generator: np.random.Generator,
) -> float:
    """Perturb an exact value or reported censor limit without latent-value imputation."""

    value = cast("float", observation.log_abundance)
    standard_error = cast("float", observation.standard_error)
    return value + float(generator.normal(0.0, standard_error))


def _validate_active_evidence(
    request: LongitudinalGbmRequest,
    catalog: KnccLongitudinalCatalog,
) -> None:
    unknown = sorted(
        {
            observation.gene_symbol
            for point in request.time_points
            for observation in point.observations
            if observation.state in _ACTIVE_STATES
            and observation.gene_symbol not in catalog.features_by_symbol
        }
    )
    if unknown:
        preview = ", ".join(unknown[:5])
        raise LongitudinalInferenceError(
            f"active protein symbols are outside the frozen 11,312-feature HGNC set: {preview}"
        )


def _validate_assay_compatibility(
    request: LongitudinalGbmRequest,
    *,
    required_attestation: AssayCompatibilityAttestation,
) -> None:
    """Defend direct engine callers that bypass normal Pydantic validation."""

    if request.assay_compatibility != required_attestation:
        raise LongitudinalInferenceError(
            "input assay compatibility attestation does not exactly match the frozen "
            "PDC000514 TMT11 Unshared Log2 source scale"
        )


def _selected_replicates(
    catalog: KnccLongitudinalCatalog,
    request_digest: str,
    count: int,
) -> tuple[SparseCoefficientReplicate, ...]:
    ordered = sorted(
        catalog.bootstrap_replicates,
        key=lambda replicate: hashlib.sha256(
            f"{request_digest}:{replicate.replicate_digest}".encode()
        ).digest(),
    )
    return tuple(ordered[:count])


def _observation_map(
    observations: tuple[ProteinObservation, ...],
) -> dict[str, ProteinObservation]:
    return {item.gene_symbol: item for item in observations}


def _active_pairs(
    request: LongitudinalGbmRequest,
    transition_index: int,
    catalog: KnccLongitudinalCatalog,
) -> tuple[_ActivePair, ...]:
    left = _observation_map(request.time_points[transition_index].observations)
    right = _observation_map(request.time_points[transition_index + 1].observations)
    relevant = catalog.ensemble_feature_indices | frozenset(
        catalog.source_processing_sensitivity.feature_indices
    )
    pairs: list[_ActivePair] = []
    for symbol in sorted(left.keys() & right.keys()):
        from_observation = left[symbol]
        to_observation = right[symbol]
        if (
            from_observation.state not in _ACTIVE_STATES
            or to_observation.state not in _ACTIVE_STATES
        ):
            continue
        feature = catalog.features_by_symbol[symbol]
        if feature.index not in relevant:
            continue
        if (
            from_observation.state is ProteinEvidenceState.LEFT_CENSORED
            and to_observation.state is ProteinEvidenceState.LEFT_CENSORED
        ):
            continue
        if (
            from_observation.state is ProteinEvidenceState.OBSERVED
            and to_observation.state is ProteinEvidenceState.OBSERVED
        ):
            value_semantics: Literal["exact_delta", "upper_bound", "lower_bound"] = "exact_delta"
        elif to_observation.state is ProteinEvidenceState.LEFT_CENSORED:
            value_semantics = "upper_bound"
        else:
            value_semantics = "lower_bound"
        from_error = cast("float", from_observation.standard_error)
        to_error = cast("float", to_observation.standard_error)
        pairs.append(
            _ActivePair(
                feature=feature,
                from_observation=from_observation,
                to_observation=to_observation,
                from_time_point_index=transition_index,
                to_time_point_index=transition_index + 1,
                expected_raw_delta=(
                    cast("float", to_observation.log_abundance)
                    - cast("float", from_observation.log_abundance)
                ),
                value_semantics=value_semantics,
                delta_standard_error=math.hypot(from_error, to_error),
                quality_weight=math.sqrt(
                    from_observation.quality_weight * to_observation.quality_weight
                ),
            )
        )
    return tuple(pairs)


def _reliability(pair: _ActivePair, scale: float) -> float:
    standardized_error = pair.delta_standard_error / scale
    return pair.quality_weight / (standardized_error**2 + CONSTANTS.standard_error_floor**2)


def _effective_sample_size(weights: tuple[float, ...]) -> float:
    if not weights:
        return 0.0
    maximum = max(weights)
    if maximum <= 0.0:
        return 0.0
    scaled = tuple(value / maximum for value in weights)
    total = math.fsum(scaled)
    squared = math.fsum(value * value for value in scaled)
    return total * total / squared if squared > 0.0 else 0.0


def _support_metrics(
    active: tuple[_ActivePair, ...],
    catalog: KnccLongitudinalCatalog,
) -> tuple[int, float, float, float]:
    by_index = {pair.feature.index: pair for pair in active}
    reference = tuple(
        feature for feature in catalog.features if feature.ensemble_mean_absolute_coefficient > 0.0
    )
    total_mass = math.fsum(feature.ensemble_mean_absolute_coefficient for feature in reference)
    present = tuple(feature for feature in reference if feature.index in by_index)
    present_mass = math.fsum(feature.ensemble_mean_absolute_coefficient for feature in present)
    weights = tuple(
        feature.ensemble_mean_absolute_coefficient
        * _reliability(by_index[feature.index], feature.transition_scale)
        for feature in present
    )
    coverage = present_mass / total_mass if total_mass > 0.0 else 0.0
    ess = _effective_sample_size(weights)
    if not present or present_mass <= 0.0:
        return 0, coverage, ess, 0.0
    mean_source_support = (
        math.fsum(
            feature.paired_support * feature.ensemble_mean_absolute_coefficient
            for feature in present
        )
        / present_mass
    )
    percentile_mass = math.fsum(
        feature.ensemble_mean_absolute_coefficient
        for feature in reference
        if feature.paired_support <= mean_source_support
    )
    percentile = percentile_mass / total_mass if total_mass > 0.0 else 0.0
    return len(present), coverage, ess, percentile


def _draw_delta_evidence(
    active: tuple[_ActivePair, ...],
    request_digest: str,
    replicates: tuple[SparseCoefficientReplicate, ...],
    *,
    cancellation: CancellationContext | None = None,
) -> FloatMatrix:
    result = np.empty((len(replicates), len(active)), dtype=np.float64)
    for row, replicate in enumerate(replicates):
        checkpoint(cancellation)
        for column, pair in enumerate(active):
            _checkpoint_stride(cancellation, column, 64)
            from_generator = np.random.default_rng(
                _stream_seed(
                    request_digest,
                    (
                        f"measurement:{replicate.replicate_digest}:"
                        f"{pair.from_time_point_index}:{pair.feature.gene_symbol}"
                    ),
                )
            )
            to_generator = np.random.default_rng(
                _stream_seed(
                    request_digest,
                    (
                        f"measurement:{replicate.replicate_digest}:"
                        f"{pair.to_time_point_index}:{pair.feature.gene_symbol}"
                    ),
                )
            )
            from_value = _sample_reported_log_value(pair.from_observation, from_generator)
            to_value = _sample_reported_log_value(pair.to_observation, to_generator)
            delta = to_value - from_value
            if not math.isfinite(delta):
                raise LongitudinalInferenceError(
                    "measurement perturbation produced a non-finite log2 delta"
                )
            result[row, column] = delta
    checkpoint(cancellation)
    return result


def _aligned_semantics(
    semantics: Literal["exact_delta", "upper_bound", "lower_bound"],
    coefficient: float,
) -> Literal["exact_delta", "upper_bound", "lower_bound"]:
    if semantics == "exact_delta" or coefficient > 0.0:
        return semantics
    return "lower_bound" if semantics == "upper_bound" else "upper_bound"


def _location_gradient(
    location: float,
    evidence: tuple[tuple[float, Literal["exact_delta", "upper_bound", "lower_bound"], float], ...],
) -> float:
    gradient = CONSTANTS.location_ridge * location
    for value, semantics, weight in evidence:
        residual = location - value
        if semantics == "upper_bound" and residual <= 0.0:
            continue
        if semantics == "lower_bound" and residual >= 0.0:
            continue
        gradient += weight * min(
            CONSTANTS.huber_delta,
            max(-CONSTANTS.huber_delta, residual),
        )
    return gradient


def _robust_concordance_location(
    evidence: tuple[tuple[float, Literal["exact_delta", "upper_bound", "lower_bound"], float], ...],
    *,
    cancellation: CancellationContext | None = None,
) -> float:
    maximum_weight = max(weight for _, _, weight in evidence)
    normalized = tuple(
        (value, semantics, weight / maximum_weight) for value, semantics, weight in evidence
    )
    lower = -CONSTANTS.location_search_bound
    upper = CONSTANTS.location_search_bound
    for iteration in range(CONSTANTS.location_solver_iterations):
        _checkpoint_stride(cancellation, iteration, 8)
        midpoint = (lower + upper) / 2.0
        if _location_gradient(midpoint, normalized) > 0.0:
            upper = midpoint
        else:
            lower = midpoint
    return (lower + upper) / 2.0


def _project(  # noqa: PLR0917
    raw_deltas: NDArray[np.float64],
    active: tuple[_ActivePair, ...],
    column_by_index: dict[int, int],
    indices: tuple[int, ...],
    coefficients: tuple[float, ...],
    scales: tuple[float, ...],
    *,
    omitted_index: int | None = None,
    cancellation: CancellationContext | None = None,
) -> tuple[float | None, float, int, float]:
    evidence: list[tuple[float, Literal["exact_delta", "upper_bound", "lower_bound"], float]] = []
    weighted_mass: list[float] = []
    covered_mass = 0.0
    total_mass = math.fsum(abs(value) for value in coefficients)
    overlap = 0
    for position, (index, coefficient, scale) in enumerate(
        zip(indices, coefficients, scales, strict=True)
    ):
        _checkpoint_stride(cancellation, position, 32)
        if index == omitted_index:
            continue
        column = column_by_index.get(index)
        if column is None:
            continue
        pair = active[column]
        raw_delta = float(raw_deltas[column])
        if not math.isfinite(raw_delta):
            raise LongitudinalInferenceError("non-finite derived protein delta")
        reliability = _reliability(pair, scale)
        absolute = abs(coefficient)
        covered_mass += absolute
        overlap += 1
        weight = absolute * reliability
        weighted_mass.append(weight)
        evidence.append(
            (
                math.copysign(1.0, coefficient) * raw_delta / scale,
                _aligned_semantics(pair.value_semantics, coefficient),
                weight,
            )
        )
    coverage = covered_mass / total_mass if total_mass > 0.0 else 0.0
    denominator = math.fsum(weighted_mass)
    ess = _effective_sample_size(tuple(weighted_mass))
    if (
        overlap < _MINIMUM_ESTIMATION_GENES
        or coverage < _MINIMUM_ESTIMATION_COVERAGE
        or ess < _MINIMUM_ESTIMATION_ESS
        or denominator <= 0.0
        or not evidence
    ):
        return None, coverage, overlap, ess
    return (
        _robust_concordance_location(tuple(evidence), cancellation=cancellation),
        coverage,
        overlap,
        ess,
    )


def _replicate_scales(
    catalog: KnccLongitudinalCatalog,
    replicate: SparseCoefficientReplicate,
) -> tuple[float, ...]:
    return tuple(catalog.features[index].transition_scale for index in replicate.feature_indices)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    fraction = position - lower_index
    return ordered[lower_index] * (1.0 - fraction) + ordered[upper_index] * fraction


def _sample_standard_deviation(values: tuple[float, ...]) -> float:
    if len(values) < 2:
        return 0.0
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(0.0, variance))


def _sample_covariance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("paired covariance inputs must have equal length")
    if len(left) < 2:
        return 0.0
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    return math.fsum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    ) / (len(left) - 1)


def _classification(lower: float, upper: float) -> TransitionClassification:
    """Classify from the complete 90% interval and never from the point score alone."""

    if lower >= CONSTANTS.alignment_threshold:
        return TransitionClassification.SOURCE_RECURRENCE_ALIGNED
    if upper <= -CONSTANTS.alignment_threshold:
        return TransitionClassification.REVERSE_ALIGNED
    if lower >= -CONSTANTS.stable_threshold and upper <= CONSTANTS.stable_threshold:
        return TransitionClassification.STABLE
    return TransitionClassification.INDETERMINATE


def _not_estimable_uncertainty(reason: str) -> TransitionUncertainty:
    return TransitionUncertainty(
        state=UncertaintyState.NOT_ESTIMABLE,
        bootstrap_replicates_used=0,
        reason=reason,
    )


def _not_estimable_interaction(reason: str) -> UncertaintyInteraction:
    return UncertaintyInteraction(
        state=UncertaintyState.NOT_ESTIMABLE,
        bootstrap_replicates_used=0,
        reason=reason,
    )


def _abstained_transition(
    request: LongitudinalGbmRequest,
    transition_index: int,
    *,
    shared: int,
    coverage: float,
    ess: float,
    reasons: tuple[str, ...],
) -> TransitionEvidence:
    reason = reasons[0]
    left = request.time_points[transition_index]
    right = request.time_points[transition_index + 1]
    return TransitionEvidence(
        transition_id=f"transition.{transition_index:02d}.{request.request_digest[7:23]}",
        transition_index=transition_index,
        from_time_point_id=left.time_point_id,
        to_time_point_id=right.time_point_id,
        support=AnalysisSupport.ABSTAINED,
        classification=TransitionClassification.NOT_ESTIMABLE,
        bootstrap_replicates_used=0,
        shared_active_gene_count=shared,
        effective_sample_size=_quantize(ess),
        coverage=_quantize_probability(coverage),
        measurement_uncertainty=_not_estimable_uncertainty(reason),
        coefficient_uncertainty=_not_estimable_uncertainty(reason),
        uncertainty_interaction=_not_estimable_interaction(reason),
        abstention_reasons=reasons[:8],
    )


def _drivers(
    active: tuple[_ActivePair, ...],
    score: float,
) -> tuple[SignedProteinDriver, ...]:
    contributions: list[tuple[float, _ActivePair, float, float, float]] = []
    denominator = math.fsum(
        abs(pair.feature.ensemble_mean_coefficient)
        * _reliability(pair, pair.feature.transition_scale)
        for pair in active
    )
    if denominator <= 0.0:
        return ()
    for pair in active:
        coefficient = pair.feature.ensemble_mean_coefficient
        if coefficient == 0.0:
            continue
        reliability = _reliability(pair, pair.feature.transition_scale)
        standardized = pair.expected_raw_delta / pair.feature.transition_scale
        aligned = math.copysign(1.0, coefficient) * standardized
        semantics = _aligned_semantics(pair.value_semantics, coefficient)
        if semantics == "exact_delta":
            influence = aligned
        elif semantics == "upper_bound":
            influence = min(0.0, aligned - score)
        else:
            influence = max(0.0, aligned - score)
        contribution = abs(coefficient) * influence * reliability / denominator
        if contribution == 0.0 and semantics != "exact_delta":
            continue
        contributions.append((abs(contribution), pair, standardized, coefficient, contribution))
    contributions.sort(key=lambda item: (-item[0], item[1].feature.gene_symbol))
    return tuple(
        SignedProteinDriver(
            gene_symbol=pair.feature.gene_symbol,
            source_gene_label=pair.feature.source_gene_label,
            from_observation_id=pair.from_observation.observation_id,
            to_observation_id=pair.to_observation.observation_id,
            from_provenance_digest=pair.from_observation.provenance_digest,
            to_provenance_digest=pair.to_observation.provenance_digest,
            from_state=pair.from_observation.state,  # type: ignore[arg-type]
            to_state=pair.to_observation.state,  # type: ignore[arg-type]
            value_semantics=pair.value_semantics,
            standardized_delta=_quantize(standardized),
            model_coefficient=_quantize(coefficient),
            signed_contribution=_quantize(contribution),
            direction=(
                DriverDirection.SOURCE_RECURRENCE_ALIGNED
                if contribution >= 0.0
                else DriverDirection.REVERSE_ALIGNED
            ),
            reliability_weight=_quantize(reliability),
            source_feature_support=pair.feature.paired_support,
        )
        for _, pair, standardized, coefficient, contribution in contributions[
            : CONSTANTS.maximum_top_drivers
        ]
    )


def _ablation_estimate(
    samples: tuple[float, ...],
    *,
    primary_score: float,
    base_support: AnalysisSupport,
    expected_count: int,
    forced_limitation: str | None = None,
) -> tuple[AnalysisSupport, float | None, float | None, TransitionClassification, str | None]:
    if len(samples) < MIN_BOOTSTRAPS:
        return (
            AnalysisSupport.ABSTAINED,
            None,
            None,
            TransitionClassification.NOT_ESTIMABLE,
            "fewer than 32 paired bootstrap projections remained estimable",
        )
    score = _quantile(samples, 0.5)
    lower = _quantile(samples, CONSTANTS.interval_lower_quantile)
    upper = _quantile(samples, CONSTANTS.interval_upper_quantile)
    reasons = []
    if forced_limitation is not None:
        reasons.append(forced_limitation)
    if base_support is AnalysisSupport.LIMITED:
        reasons.append("primary transition support is limited")
    if len(samples) < CONSTANTS.supported_minimum_bootstrap_replicates:
        reasons.append("fewer than 64 paired bootstrap projections for fully supported ablation")
    if len(samples) != expected_count:
        reasons.append("some paired bootstrap projections were not estimable")
    support = AnalysisSupport.LIMITED if reasons else AnalysisSupport.SUPPORTED
    return (
        support,
        _quantize(score),
        _quantize(primary_score - score),
        _classification(lower, upper),
        "; ".join(reasons) if reasons else None,
    )


def _source_processing_ablation(
    work: _TransitionWork,
    primary_score: float,
    base_support: AnalysisSupport,
    catalog: KnccLongitudinalCatalog,
    *,
    cancellation: CancellationContext | None = None,
) -> SourceProcessingAblation:
    projection = catalog.source_processing_sensitivity
    if work.raw_delta_draws is None:
        return SourceProcessingAblation(
            comparison=projection.comparison,
            support=AnalysisSupport.ABSTAINED,
            classification_without_component=TransitionClassification.NOT_ESTIMABLE,
            reason="primary transition did not retain paired measurement draws",
        )
    samples: list[float] = []
    for row in range(work.raw_delta_draws.shape[0]):
        checkpoint(cancellation)
        score, _, _, _ = _project(
            work.raw_delta_draws[row],
            work.active_pairs,
            work.column_by_feature_index,
            projection.feature_indices,
            projection.coefficients,
            projection.transition_scales,
            cancellation=cancellation,
        )
        if score is not None:
            samples.append(score)
    support, score, delta, classification, reason = _ablation_estimate(
        tuple(samples),
        primary_score=primary_score,
        base_support=base_support,
        expected_count=len(work.selected_replicates),
        forced_limitation=(
            "sensitivity to the locked ordinary-Log source-processing projection; "
            "not an independent model validation"
        ),
    )
    return SourceProcessingAblation(
        comparison=projection.comparison,
        support=support,
        score_without_component=score,
        score_delta=delta,
        classification_without_component=classification,
        reason=reason,
    )


def _driver_ablations(
    work: _TransitionWork,
    drivers: tuple[SignedProteinDriver, ...],
    primary_score: float,
    base_support: AnalysisSupport,
    catalog: KnccLongitudinalCatalog,
    *,
    cancellation: CancellationContext | None = None,
) -> tuple[TopDriverAblation, ...]:
    if work.raw_delta_draws is None:
        return ()
    result: list[TopDriverAblation] = []
    for driver in drivers:
        checkpoint(cancellation)
        omitted_index = catalog.features_by_symbol[driver.gene_symbol].index
        samples: list[float] = []
        for row, replicate in enumerate(work.selected_replicates):
            checkpoint(cancellation)
            score, _, _, _ = _project(
                work.raw_delta_draws[row],
                work.active_pairs,
                work.column_by_feature_index,
                replicate.feature_indices,
                replicate.coefficients,
                _replicate_scales(catalog, replicate),
                omitted_index=omitted_index,
                cancellation=cancellation,
            )
            if score is not None:
                samples.append(score)
        support, score, delta, classification, reason = _ablation_estimate(
            tuple(samples),
            primary_score=primary_score,
            base_support=base_support,
            expected_count=len(work.selected_replicates),
        )
        result.append(
            TopDriverAblation(
                omitted_gene_symbol=driver.gene_symbol,
                omitted_signed_contribution=driver.signed_contribution,
                support=support,
                score_without_component=score,
                score_delta=delta,
                classification_without_component=classification,
                reason=reason,
            )
        )
    return tuple(result)


def _calculate_transition(  # noqa: PLR0915
    request: LongitudinalGbmRequest,
    transition_index: int,
    catalog: KnccLongitudinalCatalog,
    request_digest: str,
    numerical_seed_digest: str,
    *,
    cancellation: CancellationContext | None,
) -> _TransitionWork:
    checkpoint(cancellation)
    active = _active_pairs(request, transition_index, catalog)
    shared, coverage, ess, source_percentile = _support_metrics(active, catalog)
    reasons: list[str] = []
    if shared < _MINIMUM_ESTIMATION_GENES:
        reasons.append("fewer than three shared active source-model proteins")
    if coverage < _MINIMUM_ESTIMATION_COVERAGE:
        reasons.append("less than ten percent frozen coefficient-weight coverage")
    if ess < _MINIMUM_ESTIMATION_ESS:
        reasons.append("effective sample size is below two")
    if reasons:
        evidence = _abstained_transition(
            request,
            transition_index,
            shared=shared,
            coverage=coverage,
            ess=ess,
            reasons=tuple(reasons),
        )
        return _TransitionWork(evidence, (), active, {}, None, ())
    selected = _selected_replicates(
        catalog,
        numerical_seed_digest,
        request.bootstrap_replicates,
    )
    column_by_index = {pair.feature.index: index for index, pair in enumerate(active)}
    raw_draws = _draw_delta_evidence(
        active,
        numerical_seed_digest,
        selected,
        cancellation=cancellation,
    )
    expected = np.asarray([pair.expected_raw_delta for pair in active], dtype=np.float64)
    combined_slots: list[float | None] = []
    coefficient_slots: list[float] = []
    measurement_residual_slots: list[float] = []
    for row, replicate in enumerate(selected):
        checkpoint(cancellation)
        scales = _replicate_scales(catalog, replicate)
        combined, _, _, _ = _project(
            raw_draws[row],
            active,
            column_by_index,
            replicate.feature_indices,
            replicate.coefficients,
            scales,
            cancellation=cancellation,
        )
        coefficient_only, _, _, _ = _project(
            expected,
            active,
            column_by_index,
            replicate.feature_indices,
            replicate.coefficients,
            scales,
            cancellation=cancellation,
        )
        if combined is None or coefficient_only is None:
            combined_slots.append(None)
            continue
        combined_slots.append(combined)
        coefficient_slots.append(coefficient_only)
        measurement_residual_slots.append(combined - coefficient_only)
    combined_values = tuple(value for value in combined_slots if value is not None)
    if len(combined_values) < MIN_BOOTSTRAPS:
        evidence = _abstained_transition(
            request,
            transition_index,
            shared=shared,
            coverage=coverage,
            ess=ess,
            reasons=("fewer than 32 frozen bootstrap projections remained estimable",),
        )
        return _TransitionWork(
            evidence, tuple(combined_slots), active, column_by_index, raw_draws, selected
        )
    score = _quantile(combined_values, 0.5)
    lower = _quantile(combined_values, CONSTANTS.interval_lower_quantile)
    upper = _quantile(combined_values, CONSTANTS.interval_upper_quantile)
    measurement_se = _sample_standard_deviation(tuple(measurement_residual_slots))
    coefficient_se = _sample_standard_deviation(tuple(coefficient_slots))
    combined_se = _sample_standard_deviation(combined_values)
    covariance = _sample_covariance(
        tuple(coefficient_slots),
        tuple(measurement_residual_slots),
    )
    measurement_variance = measurement_se**2
    coefficient_variance = coefficient_se**2
    combined_variance = combined_se**2
    total_component_variance = measurement_variance + coefficient_variance
    measurement_fraction = (
        measurement_variance / total_component_variance if total_component_variance > 0.0 else 0.0
    )
    coefficient_fraction = (
        coefficient_variance / total_component_variance if total_component_variance > 0.0 else 0.0
    )
    measurement_se_q = _quantize(measurement_se)
    coefficient_se_q = _quantize(coefficient_se)
    covariance_q = _quantize(covariance)
    interaction_variance_q = _quantize(2.0 * covariance_q)
    combined_variance_q = max(0.0, _quantize(combined_variance))
    decomposition_residual_q = _quantize(
        abs(
            combined_variance_q
            - (measurement_se_q**2 + coefficient_se_q**2 + interaction_variance_q)
        )
    )
    limitations: list[str] = []
    if shared < CONSTANTS.supported_minimum_shared_genes:
        limitations.append("shared active source-model protein count is below 64")
    if coverage < CONSTANTS.supported_minimum_coverage:
        limitations.append("frozen coefficient-weight coverage is below 0.50")
    if ess < CONSTANTS.supported_minimum_effective_sample_size:
        limitations.append("effective sample size is below 32")
    if len(combined_values) != request.bootstrap_replicates:
        limitations.append("some frozen bootstrap projections were not estimable")
    if len(combined_values) < CONSTANTS.supported_minimum_bootstrap_replicates:
        limitations.append(
            "fewer than 64 estimable bootstrap projections for fully supported uncertainty"
        )
    support = AnalysisSupport.LIMITED if limitations else AnalysisSupport.SUPPORTED
    drivers = _drivers(active, score)
    left = request.time_points[transition_index]
    right = request.time_points[transition_index + 1]
    score_q = _quantize(score)
    lower_q = min(_quantize(lower), score_q)
    upper_q = max(_quantize(upper), score_q)
    preliminary = TransitionEvidence(
        transition_id=f"transition.{transition_index:02d}.{request_digest[7:23]}",
        transition_index=transition_index,
        from_time_point_id=left.time_point_id,
        to_time_point_id=right.time_point_id,
        support=support,
        classification=_classification(lower, upper),
        score=score_q,
        lower_bound=lower_q,
        upper_bound=upper_q,
        bootstrap_replicates_used=len(combined_values),
        shared_active_gene_count=shared,
        effective_sample_size=_quantize(ess),
        coverage=_quantize_probability(coverage),
        source_support_percentile=_quantize_probability(source_percentile),
        measurement_uncertainty=TransitionUncertainty(
            state=UncertaintyState.ESTIMATED,
            standard_error=measurement_se_q,
            variance_fraction=_quantize_probability(measurement_fraction),
            bootstrap_replicates_used=len(combined_values),
        ),
        coefficient_uncertainty=TransitionUncertainty(
            state=UncertaintyState.ESTIMATED,
            standard_error=coefficient_se_q,
            variance_fraction=_quantize_probability(coefficient_fraction),
            bootstrap_replicates_used=len(combined_values),
        ),
        uncertainty_interaction=UncertaintyInteraction(
            state=UncertaintyState.ESTIMATED,
            covariance=covariance_q,
            variance_contribution=interaction_variance_q,
            combined_variance=combined_variance_q,
            decomposition_residual=decomposition_residual_q,
            bootstrap_replicates_used=len(combined_values),
        ),
        top_drivers=drivers,
        abstention_reasons=tuple(limitations),
    )
    work = _TransitionWork(
        evidence=preliminary,
        combined_slots=tuple(combined_slots),
        active_pairs=active,
        column_by_feature_index=column_by_index,
        raw_delta_draws=raw_draws,
        selected_replicates=selected,
    )
    final = preliminary.model_copy(
        update={
            "source_processing_ablations": (
                _source_processing_ablation(
                    work,
                    score_q,
                    support,
                    catalog,
                    cancellation=cancellation,
                ),
            ),
            "top_driver_ablations": _driver_ablations(
                work,
                drivers,
                score_q,
                support,
                catalog,
                cancellation=cancellation,
            ),
        }
    )
    checkpoint(cancellation)
    return _TransitionWork(
        evidence=final,
        combined_slots=work.combined_slots,
        active_pairs=active,
        column_by_feature_index=column_by_index,
        raw_delta_draws=raw_draws,
        selected_replicates=selected,
    )


def _huber_loss(residual: float) -> float:
    absolute = abs(residual)
    if absolute <= _HUBER_DELTA:
        return 0.5 * residual * residual
    return _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)


def _segment_location(
    values: tuple[float, ...],
    standard_errors: tuple[float, ...],
    start: int,
    end: int,
    *,
    cancellation: CancellationContext | None = None,
) -> float:
    lower = min(values[start:end])
    upper = max(values[start:end])
    for iteration in range(80):
        _checkpoint_stride(cancellation, iteration, 8)
        midpoint = (lower + upper) / 2.0
        derivative = math.fsum(
            min(
                _HUBER_DELTA,
                max(-_HUBER_DELTA, (midpoint - values[index]) / standard_errors[index]),
            )
            / standard_errors[index]
            for index in range(start, end)
        )
        if derivative > 0.0:
            upper = midpoint
        else:
            lower = midpoint
    return (lower + upper) / 2.0


def heteroscedastic_huber_segment_cost(
    values: tuple[float, ...],
    standard_errors: tuple[float, ...],
    start: int,
    end: int,
    *,
    cancellation: CancellationContext | None = None,
) -> float:
    """Return the exact deterministic segment cost used by the PELT recurrence."""

    if not (0 <= start < end <= len(values)) or len(values) != len(standard_errors):
        raise ValueError("invalid heteroscedastic Huber segment bounds")
    if any(not math.isfinite(value) for value in values) or any(
        not math.isfinite(value) or value <= 0.0 for value in standard_errors
    ):
        raise ValueError("heteroscedastic Huber inputs must be finite with positive errors")
    safe_errors = tuple(max(_SEGMENT_SE_FLOOR, value) for value in standard_errors)
    location = _segment_location(
        values,
        safe_errors,
        start,
        end,
        cancellation=cancellation,
    )
    losses: list[float] = []
    for index in range(start, end):
        _checkpoint_stride(cancellation, index - start, 4)
        losses.append(_huber_loss((values[index] - location) / safe_errors[index]))
    checkpoint(cancellation)
    return math.fsum(losses)


def _prefer_partition(candidate: _Partition, incumbent: _Partition | None) -> bool:
    if incumbent is None:
        return True
    if candidate.objective < incumbent.objective - 1e-12:
        return True
    if math.isclose(candidate.objective, incumbent.objective, abs_tol=1e-12):
        return candidate.boundaries < incumbent.boundaries
    return False


def exact_pelt_segmentation(
    values: tuple[float, ...],
    standard_errors: tuple[float, ...],
    penalty: float,
    *,
    cancellation: CancellationContext | None = None,
) -> tuple[tuple[int, ...], float]:
    """Solve exact PELT for 3--15 transition rates with two-rate segments."""

    partition, _ = _pelt_partition(
        values,
        standard_errors,
        penalty,
        cancellation=cancellation,
    )
    return partition.boundaries, partition.objective


def _pelt_partition(
    values: tuple[float, ...],
    standard_errors: tuple[float, ...],
    penalty: float,
    *,
    cancellation: CancellationContext | None = None,
) -> tuple[_Partition, tuple[int, ...]]:
    """Run exact PELT with the K=0 segment-cost condition checked before pruning."""

    if not 3 <= len(values) <= 15 or len(values) != len(standard_errors) or penalty <= 0.0:
        raise ValueError(
            "exact PELT requires 3-15 aligned transition rates/errors and positive penalty"
        )
    safe_errors = tuple(max(_SEGMENT_SE_FLOOR, value) for value in standard_errors)
    costs: dict[tuple[int, int], float] = {}
    for start in range(len(values)):
        checkpoint(cancellation)
        for end in range(start + _PELT_MIN_SEGMENT_TRANSITIONS, len(values) + 1):
            costs[(start, end)] = heteroscedastic_huber_segment_cost(
                values,
                safe_errors,
                start,
                end,
                cancellation=cancellation,
            )
    for start in range(len(values) - 1):
        checkpoint(cancellation)
        for split in range(
            start + _PELT_MIN_SEGMENT_TRANSITIONS,
            len(values),
        ):
            for end in range(
                split + _PELT_MIN_SEGMENT_TRANSITIONS,
                len(values) + 1,
            ):
                if costs[(start, end)] + 1e-10 < (costs[(start, split)] + costs[(split, end)]):
                    raise ValueError("heteroscedastic Huber cost violates the PELT K=0 condition")
    best: list[_Partition | None] = [_Partition(-penalty, ())] + [None] * len(values)
    candidates = [0]
    candidate_counts: list[int] = []
    for end in range(1, len(values) + 1):
        checkpoint(cancellation)
        candidate_counts.append(len(candidates))
        incumbent: _Partition | None = None
        eligible = [
            start
            for start in candidates
            if best[start] is not None and end - start >= _PELT_MIN_SEGMENT_TRANSITIONS
        ]
        for start in eligible:
            prefix = cast("_Partition", best[start])
            boundaries = prefix.boundaries + (() if start == 0 else (start,))
            candidate = _Partition(
                prefix.objective + costs[(start, end)] + penalty,
                boundaries,
            )
            if _prefer_partition(candidate, incumbent):
                incumbent = candidate
        best[end] = incumbent
        if incumbent is not None:
            optimum = incumbent.objective
            candidates = [
                start
                for start in candidates
                if start not in eligible
                or cast("_Partition", best[start]).objective + costs[(start, end)]
                <= optimum + 1e-12
            ]
            candidates.append(end)
    result = cast("_Partition", best[-1])
    return result, tuple(candidate_counts)


def pelt_candidate_counts(
    values: tuple[float, ...],
    standard_errors: tuple[float, ...],
    penalty: float,
    *,
    cancellation: CancellationContext | None = None,
) -> tuple[int, ...]:
    """Expose deterministic candidate-set sizes for pruning-oracle tests."""

    _, counts = _pelt_partition(
        values,
        standard_errors,
        penalty,
        cancellation=cancellation,
    )
    return counts


def brute_force_segmentation(
    values: tuple[float, ...],
    standard_errors: tuple[float, ...],
    penalty: float,
    *,
    cancellation: CancellationContext | None = None,
) -> tuple[tuple[int, ...], float]:
    """Reference enumerator used to verify the exact PELT recurrence in tests."""

    if not 3 <= len(values) <= 15 or len(values) != len(standard_errors) or penalty <= 0.0:
        raise ValueError("brute-force segmentation requires valid 3-15 transition-rate inputs")
    incumbent: _Partition | None = None
    for mask in range(1 << (len(values) - 1)):
        _checkpoint_stride(cancellation, mask, 32)
        boundaries = tuple(index for index in range(1, len(values)) if mask & (1 << (index - 1)))
        endpoints = (0, *boundaries, len(values))
        if any(end - start < _PELT_MIN_SEGMENT_TRANSITIONS for start, end in pairwise(endpoints)):
            continue
        objective = penalty * len(boundaries) + math.fsum(
            heteroscedastic_huber_segment_cost(
                values,
                standard_errors,
                start,
                end,
                cancellation=cancellation,
            )
            for start, end in pairwise(endpoints)
        )
        candidate = _Partition(objective, boundaries)
        if _prefer_partition(candidate, incumbent):
            incumbent = candidate
    result = cast("_Partition", incumbent)
    checkpoint(cancellation)
    return result.boundaries, result.objective


def _duration_normalized_rates(
    request: LongitudinalGbmRequest,
    transitions: tuple[float, ...],
) -> tuple[float, ...]:
    if len(transitions) != len(request.time_points) - 1:
        raise ValueError("transition rates require exactly one value per consecutive interval")
    rates: list[float] = []
    for index, transition in enumerate(transitions):
        duration = (
            request.time_points[index + 1].time_offset_days
            - request.time_points[index].time_offset_days
        )
        if not math.isfinite(duration) or duration <= 0.0:
            raise LongitudinalInferenceError(
                "duration-normalized PELT requires positive finite consecutive durations"
            )
        rate = transition * _PELT_RATE_REFERENCE_DAYS / duration
        if not math.isfinite(rate):
            raise LongitudinalInferenceError("duration-normalized transition rate is non-finite")
        rates.append(rate)
    return tuple(rates)


def _empirical_rate_standard_errors(
    rate_paths: tuple[tuple[float, ...], ...],
) -> tuple[float, ...]:
    return tuple(
        max(
            _SEGMENT_SE_FLOOR,
            _sample_standard_deviation(tuple(path[index] for path in rate_paths)),
        )
        for index in range(len(rate_paths[0]))
    )


def _pelt_analysis(
    request: LongitudinalGbmRequest,
    works: tuple[_TransitionWork, ...],
    *,
    cancellation: CancellationContext | None,
) -> PeltAnalysis | None:
    if len(request.time_points) < CONSTANTS.pelt_minimum_time_points:
        return None
    if any(work.evidence.support is AnalysisSupport.ABSTAINED for work in works):
        return PeltAnalysis(
            support=AnalysisSupport.ABSTAINED,
            penalty=CONSTANTS.pelt_penalty,
            bootstrap_replicates_used=0,
            reason="at least one consecutive transition is not estimable",
        )
    rate_values = _duration_normalized_rates(
        request,
        tuple(cast("float", work.evidence.score) for work in works),
    )
    common_slots = [
        slot
        for slot in range(request.bootstrap_replicates)
        if all(
            slot < len(work.combined_slots) and work.combined_slots[slot] is not None
            for work in works
        )
    ]
    if len(common_slots) < MIN_BOOTSTRAPS:
        return PeltAnalysis(
            support=AnalysisSupport.ABSTAINED,
            penalty=CONSTANTS.pelt_penalty,
            bootstrap_replicates_used=0,
            reason="fewer than 32 joint transition bootstrap paths are estimable",
        )
    joint_rate_paths = tuple(
        _duration_normalized_rates(
            request,
            tuple(cast("float", work.combined_slots[slot]) for work in works),
        )
        for slot in common_slots
    )
    rate_errors = _empirical_rate_standard_errors(joint_rate_paths)
    boundaries, objective = exact_pelt_segmentation(
        rate_values,
        rate_errors,
        CONSTANTS.pelt_penalty,
        cancellation=cancellation,
    )
    frequencies = dict.fromkeys(range(1, len(rate_values)), 0)
    for rate_path in joint_rate_paths:
        bootstrap_boundaries, _ = exact_pelt_segmentation(
            rate_path,
            rate_errors,
            CONSTANTS.pelt_penalty,
            cancellation=cancellation,
        )
        for boundary in bootstrap_boundaries:
            frequencies[boundary] += 1
        checkpoint(cancellation)
    endpoints = (0, *boundaries, len(rate_values))
    boundary_documents: list[PeltBoundary] = []
    for position, boundary in enumerate(boundaries):
        left_start = endpoints[position]
        right_end = endpoints[position + 2]
        split_cost = heteroscedastic_huber_segment_cost(
            rate_values,
            rate_errors,
            left_start,
            boundary,
            cancellation=cancellation,
        ) + heteroscedastic_huber_segment_cost(
            rate_values,
            rate_errors,
            boundary,
            right_end,
            cancellation=cancellation,
        )
        merged_cost = heteroscedastic_huber_segment_cost(
            rate_values,
            rate_errors,
            left_start,
            right_end,
            cancellation=cancellation,
        )
        boundary_documents.append(
            PeltBoundary(
                boundary_index=boundary,
                left_time_point_id=request.time_points[boundary - 1].time_point_id,
                right_time_point_id=request.time_points[boundary].time_point_id,
                cost_reduction=_quantize(max(0.0, merged_cost - split_cost)),
                bootstrap_frequency=_quantize_probability(
                    frequencies[boundary] / len(common_slots)
                ),
            )
        )
    limited = (
        any(work.evidence.support is AnalysisSupport.LIMITED for work in works)
        or len(common_slots) != request.bootstrap_replicates
        or len(common_slots) < CONSTANTS.supported_minimum_bootstrap_replicates
    )
    limitation_reasons: list[str] = []
    if any(work.evidence.support is AnalysisSupport.LIMITED for work in works):
        limitation_reasons.append("segmentation inherits limited transition support")
    if len(common_slots) != request.bootstrap_replicates:
        limitation_reasons.append("some joint transition bootstrap paths were not estimable")
    if len(common_slots) < CONSTANTS.supported_minimum_bootstrap_replicates:
        limitation_reasons.append("fewer than 64 joint bootstrap rate paths for full support")
    return PeltAnalysis(
        support=AnalysisSupport.LIMITED if limited else AnalysisSupport.SUPPORTED,
        penalty=CONSTANTS.pelt_penalty,
        objective_value=_quantize(objective),
        bootstrap_replicates_used=len(common_slots),
        boundaries=tuple(boundary_documents),
        reason=("; ".join(limitation_reasons) if limited else None),
    )


def semantic_result_projection(result: LongitudinalGbmResult) -> dict[str, object]:
    """Project result semantics without profile/provenance/result-digest circularity."""

    return {
        "assay_compatibility": result.assay_compatibility.model_dump(mode="json"),
        "time_point_ids": result.time_point_ids,
        "transitions": tuple(item.model_dump(mode="json") for item in result.transitions),
        "pelt_analysis": (
            result.pelt_analysis.model_dump(mode="json")
            if result.pelt_analysis is not None
            else None
        ),
        "output_semantics": result.output_semantics,
        "research_use_only": result.research_use_only,
        "non_prescriptive": result.non_prescriptive,
    }


def infer_longitudinal_gbm(
    request: LongitudinalGbmRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmResult:
    """Project consecutive protein changes without persistence or clinical claims."""

    checkpoint(cancellation)
    catalog = longitudinal_gbm_catalog()
    profile = algorithm_profile()
    _validate_assay_compatibility(
        request,
        required_attestation=profile.required_assay_compatibility,
    )
    _validate_active_evidence(request, catalog)
    request_digest = canonical_request_digest(request)
    computational_digest = computational_request_digest(
        request,
        profile_digest=profile.profile_digest,
    )
    numerical_seed_digest = computational_request_digest(
        request,
        profile_digest=catalog.content_digest,
    )
    works = tuple(
        _calculate_transition(
            request,
            index,
            catalog,
            request_digest,
            numerical_seed_digest,
            cancellation=cancellation,
        )
        for index in range(len(request.time_points) - 1)
    )
    pelt = _pelt_analysis(request, works, cancellation=cancellation)
    provenance = LongitudinalGbmProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        source_profile_content_digest=profile.digests.source_profile_content_digest,
        source_profile_artifact_digest=profile.digests.source_profile_artifact_digest,
        source_file_lock_digest=profile.digests.source_file_lock_digest,
        cohort_oracle_digest=profile.digests.cohort_oracle_digest,
        feature_space_digest=profile.digests.feature_space_digest,
        transition_model_digest=profile.digests.transition_model_digest,
        coefficient_digest=profile.digests.coefficient_digest,
        bootstrap_digest=profile.digests.bootstrap_digest,
        source_processing_ablation_digest=(profile.digests.source_processing_ablation_digest),
        hgnc_complete_set_digest=profile.digests.hgnc_complete_set_digest,
        source_to_hgnc_mapping_digest=profile.digests.source_to_hgnc_mapping_digest,
        engine_semantic_digest=profile.digests.engine_semantic_digest,
        demo_semantic_oracle_digest=profile.demo_semantic_oracle_digest,
        assay_compatibility_digest=sha256_digest(
            request.assay_compatibility.model_dump(mode="json")
        ),
        normalization_reference_digest=request.normalization_reference.binding_digest,
        numpy_version=profile.numpy_version,
        computational_digest=computational_digest,
        numerical_seed_digest=numerical_seed_digest,
        bootstrap_seed=_receipt_seed(numerical_seed_digest),
        observation_source_digests=tuple(
            sorted(
                {
                    observation.provenance_digest
                    for point in request.time_points
                    for observation in point.observations
                }
            )
        ),
        source_attribution=profile.source_attribution,
        source_license=profile.source_license,
        source_license_url=profile.source_license_url,
        source_transformation_notice=profile.source_transformation_notice,
    )
    unverified = UnverifiedLongitudinalGbmResult(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest="sha256:" + "0" * 64,
        series_id=request.series_id,
        assay_compatibility=request.assay_compatibility,
        normalization_reference=request.normalization_reference,
        time_point_ids=tuple(point.time_point_id for point in request.time_points),
        transitions=tuple(work.evidence for work in works),
        pelt_analysis=pelt,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    document = unverified.model_dump(mode="python")
    document["result_digest"] = result_payload_digest(unverified)
    result = LongitudinalGbmResult.model_validate(document)
    if (
        request_digest == profile.demo_request_digest
        and sha256_digest(semantic_result_projection(result))
        != EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
    ):
        raise SourceProfileIntegrityError("synthetic KNCC demo semantic oracle digest mismatch")
    checkpoint(cancellation)
    return result


__all__ = [
    "brute_force_segmentation",
    "exact_pelt_segmentation",
    "heteroscedastic_huber_segment_cost",
    "infer_longitudinal_gbm",
    "pelt_candidate_counts",
    "semantic_result_projection",
]
