"""Deterministic fitted KNCC Reactome conditional-transition engine."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
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
from .contracts import (
    GLOBAL_MIN_ACTIVE_GENES,
    GLOBAL_MIN_COEFFICIENT_MASS,
    GLOBAL_MIN_EFFECTIVE_SAMPLE_SIZE,
    MAX_TOP_CONTRIBUTIONS,
    PATHWAY_MIN_ACTIVE_GENES,
    PATHWAY_MIN_COEFFICIENT_MASS,
    PATHWAY_MIN_EFFECTIVE_SAMPLE_SIZE,
    PATHWAY_MIN_UNIQUE_GENES,
    PATHWAY_MIN_UNIQUE_MASS,
    PI3K_REACTOME_ID,
    AnalysisSupport,
    ConditionalComponentAblation,
    ConditionalPathwayAblations,
    ConditionalProteinContribution,
    ConditionalTransitionClassification,
    ConditionalUncertaintyDecomposition,
    ContributionDirection,
    GlobalRecurrenceClassification,
    GlobalRecurrenceConcordance,
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalGbmReactomeTransitionResult,
    ProteinEvidenceState,
    ProteinObservation,
    ReactomeConditionalTransitionEvidence,
    ReactomePathwayConcordance,
    ReactomeTransitionProvenance,
    UncertaintyState,
    UnverifiedLongitudinalGbmReactomeTransitionResult,
    ValueSemantics,
)
from .demo import EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
from .errors import (
    ReactomeConditionalInferenceError,
    ReactomeConditionalModelIntegrityError,
)
from .fitted_catalog import (
    FittedPathwayLoading,
    ReactomeConditionalFittedCatalog,
    reactome_conditional_fitted_catalog,
)
from .profile import CONSTANTS, algorithm_profile
from .solver import (
    BoundSemantics,
    ConditionalSolverDiagnostics,
    ConditionalSolveResult,
    SolverEvidence,
    solve_conditional_coordinates,
)

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
FloatScale = NDArray[np.float64] | NDArray[np.float32]

_ACTIVE_STATES: Final = frozenset(
    {ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED}
)
_GENE_FOLD_SALT: Final = "kncc-reactome-gene-fold-v1"
_GENE_FOLDS: Final = 5
_MINIMUM_RUNTIME_BOOTSTRAPS: Final = 32
_MAXIMUM_CONDITION: Final = 25.0
_LIMITATIONS: Final = (
    "Research-use-only same-cohort protein-transition concordance; not clinical evidence.",
    "The fitted evaluation is internal reconstruction and is not external validation.",
    "Reactome membership does not establish pathway activation, flux, or causality.",
    "The collective conditional reconstruction advantage in the source cohort is modest.",
    "Cohort leave-pathway-out intervals cross zero for every individual pathway.",
    "Caller held-gene reconstruction is a request-specific stability check, not validation.",
    "One-sided censor limits are retained as bounds; two censored limits are uninformative.",
    "Missing and unsupported observations are excluded and never become negative evidence.",
    "PI3K/AKT has no unique fixed-panel member and remains overlap-confounded.",
    "Bootstrap intervals describe measurement and fitted-source sensitivity, not probability.",
    "Missingness, preprocessing, sampling, and cohort transport remain limitations.",
    "Outputs are non-prescriptive and are not recurrence or treatment predictions.",
)


@dataclass(frozen=True, slots=True)
class _ActivePair:
    local_position: int
    gene_symbol: str
    from_observation: ProteinObservation
    to_observation: ProteinObservation
    raw_delta: float
    semantics: BoundSemantics
    delta_standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _BootstrapCoordinates:
    measurement: tuple[tuple[float, ...], ...]
    fitted_model: tuple[tuple[float, ...], ...]
    combined: tuple[tuple[float, ...], ...]
    selected_row_digests: tuple[str, ...]
    failed_replicates: int

    @property
    def successful_replicates(self) -> int:
        return len(self.combined)


@dataclass(frozen=True, slots=True)
class _MassMetrics:
    active_count: int
    observed_count: int
    left_censored_count: int
    coverage: float
    effective_sample_size: float


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise ReactomeConditionalInferenceError(
            "conditional-transition computation produced a non-finite value"
        )
    result = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if result == 0.0 else result


def _probability(value: float) -> float:
    return min(1.0, max(0.0, _quantize(value)))


def _stream_seed(seed_digest: str, stream: str) -> int:
    payload = f"{seed_digest}:{stream}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _receipt_seed(seed_digest: str) -> int:
    return _stream_seed(seed_digest, "receipt-bootstrap-v1") % (2**53)


def _sample_standard_deviation(values: tuple[float, ...]) -> float:
    if len(values) < 2:
        return 0.0
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / (
        len(values) - 1
    )
    return math.sqrt(max(0.0, variance))


def _sample_covariance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ReactomeConditionalInferenceError(
            "paired uncertainty streams have different lengths"
        )
    if len(left) < 2:
        return 0.0
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    return math.fsum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    ) / (len(left) - 1)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        raise ReactomeConditionalInferenceError("quantile requires fitted values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    fraction = position - lower_index
    return ordered[lower_index] * (1.0 - fraction) + ordered[upper_index] * fraction


def _effective_sample_size(weights: tuple[float, ...]) -> float:
    if not weights:
        return 0.0
    maximum = max(weights)
    if maximum <= 0.0:
        return 0.0
    scaled = tuple(value / maximum for value in weights)
    total = math.fsum(scaled)
    squares = math.fsum(value * value for value in scaled)
    return total * total / squares if squares > 0.0 else 0.0


def _validate_request(
    request: LongitudinalGbmReactomeTransitionRequest,
    catalog: ReactomeConditionalFittedCatalog,
) -> LongitudinalGbmReactomeTransitionRequest:
    validated = LongitudinalGbmReactomeTransitionRequest.model_validate(
        request,
        strict=True,
    )
    if validated.assay_compatibility != algorithm_profile().required_assay_compatibility:
        raise ReactomeConditionalInferenceError(
            "input assay attestation does not match the locked PDC000514 TMT11 "
            "Unshared Log2 source scale"
        )
    unknown = sorted(
        {
            observation.gene_symbol
            for point in validated.time_points
            for observation in point.observations
            if observation.state in _ACTIVE_STATES
            and observation.gene_symbol
            not in catalog.source_catalog.gene_index_by_symbol
        }
    )
    if unknown:
        raise ReactomeConditionalInferenceError(
            "active protein symbols are outside the locked 11,312-gene source axis: "
            + ", ".join(unknown[:5])
        )
    return validated


def _observation_map(
    observations: tuple[ProteinObservation, ...],
) -> dict[str, ProteinObservation]:
    return {observation.gene_symbol: observation for observation in observations}


def _active_pairs(
    request: LongitudinalGbmReactomeTransitionRequest,
    transition_index: int,
    catalog: ReactomeConditionalFittedCatalog,
) -> tuple[_ActivePair, ...]:
    left = _observation_map(request.time_points[transition_index].observations)
    right = _observation_map(request.time_points[transition_index + 1].observations)
    pairs: list[_ActivePair] = []
    for symbol in sorted(left.keys() & right.keys()):
        from_observation = left[symbol]
        to_observation = right[symbol]
        if (
            from_observation.state not in _ACTIVE_STATES
            or to_observation.state not in _ACTIVE_STATES
        ):
            continue
        source_index = catalog.source_catalog.gene_index_by_symbol[symbol]
        local_position = catalog.local_index_by_feature.get(source_index)
        if local_position is None:
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
            semantics: BoundSemantics = "exact_delta"
        elif to_observation.state is ProteinEvidenceState.LEFT_CENSORED:
            semantics = "upper_bound"
        else:
            semantics = "lower_bound"
        from_value = cast("float", from_observation.log_abundance)
        to_value = cast("float", to_observation.log_abundance)
        from_error = cast("float", from_observation.standard_error)
        to_error = cast("float", to_observation.standard_error)
        pairs.append(
            _ActivePair(
                local_position=local_position,
                gene_symbol=symbol,
                from_observation=from_observation,
                to_observation=to_observation,
                raw_delta=to_value - from_value,
                semantics=semantics,
                delta_standard_error=math.hypot(from_error, to_error),
                quality_weight=math.sqrt(
                    from_observation.quality_weight * to_observation.quality_weight
                ),
            )
        )
    return tuple(sorted(pairs, key=lambda item: item.local_position))


def _reliability(pair: _ActivePair, scale: float) -> float:
    standardized_error = pair.delta_standard_error / scale
    return min(
        1.0,
        max(
            np.finfo(np.float64).tiny,
            pair.quality_weight / (1.0 + standardized_error * standardized_error),
        ),
    )


def _solver_evidence(
    active: tuple[_ActivePair, ...],
    scale: FloatScale,
    raw_deltas: FloatArray | None = None,
) -> tuple[SolverEvidence, ...]:
    values = (
        raw_deltas
        if raw_deltas is not None
        else np.asarray([pair.raw_delta for pair in active], dtype=np.float64)
    )
    result: list[SolverEvidence] = []
    for pair, raw_delta in zip(active, values, strict=True):
        feature_scale = float(scale[pair.local_position])
        result.append(
            SolverEvidence(
                feature_position=pair.local_position,
                value=float(raw_delta) / feature_scale,
                semantics=pair.semantics,
                reliability_weight=_reliability(pair, feature_scale),
            )
        )
    return tuple(result)


def _solve_is_valid(result: ConditionalSolveResult) -> bool:
    diagnostics = result.diagnostics
    return (
        diagnostics.converged
        and diagnostics.objective_monotone
        and diagnostics.design_condition_number <= _MAXIMUM_CONDITION
        and all(math.isfinite(value) for value in result.coordinates)
    )


def _selected_draw_indices(
    catalog: ReactomeConditionalFittedCatalog,
    seed_digest: str,
    count: int,
) -> tuple[int, ...]:
    ordered = sorted(
        range(catalog.bootstrap_replicate_count),
        key=lambda index: hashlib.sha256(
            f"{seed_digest}:{catalog.bootstrap_row_digests[index]}".encode()
        ).digest(),
    )
    return tuple(ordered[:count])


def _perturbed_deltas(
    active: tuple[_ActivePair, ...],
    seed_digest: str,
    transition_index: int,
    row_digest: str,
) -> FloatArray:
    values = np.empty(len(active), dtype=np.float64)
    for index, pair in enumerate(active):
        generator = np.random.default_rng(
            _stream_seed(
                seed_digest,
                f"measurement:{transition_index}:{row_digest}:{pair.gene_symbol}",
            )
        )
        values[index] = pair.raw_delta + float(
            generator.normal(0.0, pair.delta_standard_error)
        )
    return values


def _bootstrap_coordinates(
    active: tuple[_ActivePair, ...],
    catalog: ReactomeConditionalFittedCatalog,
    seed_digest: str,
    transition_index: int,
    count: int,
    *,
    cancellation: CancellationContext | None,
) -> _BootstrapCoordinates:
    measurement: list[tuple[float, ...]] = []
    fitted_model: list[tuple[float, ...]] = []
    combined: list[tuple[float, ...]] = []
    successful_digests: list[str] = []
    failures = 0
    fixed_raw = np.asarray([pair.raw_delta for pair in active], dtype=np.float64)
    for draw_index in _selected_draw_indices(catalog, seed_digest, count):
        checkpoint(cancellation)
        draw = catalog.bootstrap_draw(draw_index)
        design = catalog.design_for_bootstrap(draw_index)
        perturbed = _perturbed_deltas(
            active,
            seed_digest,
            transition_index,
            draw.row_digest,
        )
        try:
            measurement_result = solve_conditional_coordinates(
                catalog.reference_design,
                _solver_evidence(active, catalog.reference_scale, perturbed),
                cancellation=cancellation,
            )
            fitted_result = solve_conditional_coordinates(
                design,
                _solver_evidence(active, draw.scale, fixed_raw),
                cancellation=cancellation,
            )
            combined_result = solve_conditional_coordinates(
                design,
                _solver_evidence(active, draw.scale, perturbed),
                cancellation=cancellation,
            )
        except ReactomeConditionalInferenceError:
            failures += 1
            continue
        if not all(
            _solve_is_valid(result)
            for result in (measurement_result, fitted_result, combined_result)
        ):
            failures += 1
            continue
        measurement.append(measurement_result.coordinates)
        fitted_model.append(fitted_result.coordinates)
        combined.append(combined_result.coordinates)
        successful_digests.append(draw.row_digest)
    checkpoint(cancellation)
    return _BootstrapCoordinates(
        measurement=tuple(measurement),
        fitted_model=tuple(fitted_model),
        combined=tuple(combined),
        selected_row_digests=tuple(successful_digests),
        failed_replicates=failures,
    )


def _mass_metrics(
    active: tuple[_ActivePair, ...],
    loading: FloatArray,
    positions: tuple[int, ...],
    scale: FloatArray,
) -> _MassMetrics:
    by_position = {pair.local_position: pair for pair in active}
    total_mass = math.fsum(abs(float(loading[position])) for position in positions)
    present = tuple(position for position in positions if position in by_position)
    present_mass = math.fsum(abs(float(loading[position])) for position in present)
    weights = tuple(
        abs(float(loading[position]))
        * _reliability(by_position[position], float(scale[position]))
        for position in present
    )
    observed_count = sum(
        by_position[position].semantics == "exact_delta" for position in present
    )
    return _MassMetrics(
        active_count=len(present),
        observed_count=observed_count,
        left_censored_count=len(present) - observed_count,
        coverage=present_mass / total_mass if total_mass > 0.0 else 0.0,
        effective_sample_size=_effective_sample_size(weights),
    )


def _global_classification(
    lower: float,
    upper: float,
) -> GlobalRecurrenceClassification:
    if lower > 0.25:
        return GlobalRecurrenceClassification.SOURCE_RECURRENCE_ALIGNED
    if upper < -0.25:
        return GlobalRecurrenceClassification.SOURCE_PRIMARY_ALIGNED
    if lower >= -0.25 and upper <= 0.25:
        return GlobalRecurrenceClassification.STABLE
    return GlobalRecurrenceClassification.INDETERMINATE


def _pathway_classification(
    lower: float,
    upper: float,
) -> ConditionalTransitionClassification:
    if lower > 0.25:
        return (
            ConditionalTransitionClassification.CONDITIONAL_SOURCE_RECURRENCE_ALIGNED
        )
    if upper < -0.25:
        return ConditionalTransitionClassification.CONDITIONAL_SOURCE_PRIMARY_ALIGNED
    if lower >= -0.25 and upper <= 0.25:
        return ConditionalTransitionClassification.CONDITIONALLY_STABLE
    return ConditionalTransitionClassification.INDETERMINATE


def _point_pathway_classification(score: float) -> ConditionalTransitionClassification:
    if score > 0.25:
        return ConditionalTransitionClassification.CONDITIONAL_SOURCE_RECURRENCE_ALIGNED
    if score < -0.25:
        return ConditionalTransitionClassification.CONDITIONAL_SOURCE_PRIMARY_ALIGNED
    return ConditionalTransitionClassification.CONDITIONALLY_STABLE


def _not_estimable_uncertainty(reason: str) -> ConditionalUncertaintyDecomposition:
    return ConditionalUncertaintyDecomposition(
        state=UncertaintyState.NOT_ESTIMABLE,
        reason=reason,
    )


def _uncertainty(
    point_score: float,
    measurement: tuple[float, ...],
    fitted_model: tuple[float, ...],
    combined: tuple[float, ...],
) -> tuple[ConditionalUncertaintyDecomposition, float, float]:
    measurement_se = _sample_standard_deviation(measurement)
    model_se = _sample_standard_deviation(fitted_model)
    combined_se = _sample_standard_deviation(combined)
    measurement_effect = tuple(value - point_score for value in measurement)
    model_effect = tuple(value - point_score for value in fitted_model)
    covariance = _sample_covariance(measurement_effect, model_effect)
    closure = abs(
        combined_se * combined_se
        - measurement_se * measurement_se
        - model_se * model_se
        - 2.0 * covariance
    )
    lower = min(point_score, _quantile(combined, 0.05))
    upper = max(point_score, _quantile(combined, 0.95))
    return (
        ConditionalUncertaintyDecomposition(
            state=UncertaintyState.ESTIMATED,
            measurement_standard_error=_quantize(measurement_se),
            fitted_model_standard_error=_quantize(model_se),
            measurement_model_covariance=_quantize(covariance),
            combined_standard_error=_quantize(combined_se),
            variance_closure_residual=_quantize(closure),
            bootstrap_replicates_used=len(combined),
        ),
        _quantize(lower),
        _quantize(upper),
    )


def _abstained_global(
    metrics: _MassMetrics,
    reasons: tuple[str, ...],
) -> GlobalRecurrenceConcordance:
    return GlobalRecurrenceConcordance(
        support=AnalysisSupport.ABSTAINED,
        classification=GlobalRecurrenceClassification.NOT_ESTIMABLE,
        shared_active_gene_count=metrics.active_count,
        coefficient_mass_coverage=_probability(metrics.coverage),
        effective_sample_size=_quantize(metrics.effective_sample_size),
        bootstrap_replicates_used=0,
        abstention_reasons=reasons[:8],
    )


def _global_result(
    point: ConditionalSolveResult,
    bootstraps: _BootstrapCoordinates,
    metrics: _MassMetrics,
    global_scale: float,
) -> GlobalRecurrenceConcordance:
    reasons: list[str] = []
    if metrics.active_count < GLOBAL_MIN_ACTIVE_GENES:
        reasons.append("fewer than 16 active fitted global genes")
    if metrics.coverage < GLOBAL_MIN_COEFFICIENT_MASS:
        reasons.append("global coefficient-mass coverage is below 0.25")
    if metrics.effective_sample_size < GLOBAL_MIN_EFFECTIVE_SAMPLE_SIZE:
        reasons.append("global effective sample size is below 8")
    if not _solve_is_valid(point):
        reasons.append("primary joint robust solve did not satisfy convergence and condition gates")
    if bootstraps.successful_replicates < _MINIMUM_RUNTIME_BOOTSTRAPS:
        reasons.append("fewer than 32 fitted bootstrap paths converged")
    if reasons:
        return _abstained_global(metrics, tuple(reasons))
    score = float(point.coordinates[0]) / global_scale
    combined = tuple(row[0] / global_scale for row in bootstraps.combined)
    lower = min(score, _quantile(combined, 0.05))
    upper = max(score, _quantile(combined, 0.95))
    score_q = _quantize(score)
    lower_q = _quantize(lower)
    upper_q = _quantize(upper)
    limited: list[str] = []
    if bootstraps.failed_replicates:
        limited.append("one or more requested fitted bootstrap paths were not estimable")
    if bootstraps.successful_replicates < 64:
        limited.append("fewer than 64 fitted bootstrap paths limit stability evidence")
    return GlobalRecurrenceConcordance(
        support=AnalysisSupport.LIMITED if limited else AnalysisSupport.SUPPORTED,
        classification=_global_classification(lower_q, upper_q),
        score=score_q,
        lower_bound=lower_q,
        upper_bound=upper_q,
        shared_active_gene_count=metrics.active_count,
        coefficient_mass_coverage=_probability(metrics.coverage),
        effective_sample_size=_quantize(metrics.effective_sample_size),
        bootstrap_replicates_used=bootstraps.successful_replicates,
        abstention_reasons=tuple(limited),
    )


def _abstained_ablation(
    kind: Literal[
        "global_axis",
        "source_processing",
        "degree_normalization",
        "unique_members",
        "leave_pathway_out",
        "overlapping_pathway",
        "top_contribution",
    ],
    component_id: str,
    reason: str,
    *,
    removed_feature_count: int = 0,
) -> ConditionalComponentAblation:
    return ConditionalComponentAblation(
        component_kind=kind,
        component_id=component_id,
        support=AnalysisSupport.ABSTAINED,
        classification_without_component=(
            ConditionalTransitionClassification.NOT_ESTIMABLE
        ),
        removed_feature_count=removed_feature_count,
        reason=reason,
    )


def _numeric_ablation(
    kind: Literal[
        "global_axis",
        "source_processing",
        "degree_normalization",
        "unique_members",
        "leave_pathway_out",
        "overlapping_pathway",
        "top_contribution",
    ],
    component_id: str,
    score: float,
    without: float,
    reason: str,
    *,
    removed_feature_count: int = 0,
) -> ConditionalComponentAblation:
    without_q = _quantize(without)
    return ConditionalComponentAblation(
        component_kind=kind,
        component_id=component_id,
        support=AnalysisSupport.LIMITED,
        conditional_score_without_component=without_q,
        score_delta=_quantize(score - without),
        classification_without_component=_point_pathway_classification(without_q),
        removed_feature_count=removed_feature_count,
        reason=reason,
    )


def _solve_ablation(  # noqa: PLR0917
    active: tuple[_ActivePair, ...],
    scale: FloatArray,
    design: FloatArray,
    coordinate_index: int,
    score_scale: float,
    kind: Literal[
        "global_axis",
        "source_processing",
        "degree_normalization",
        "unique_members",
        "overlapping_pathway",
    ],
    component_id: str,
    point_score: float,
    *,
    global_ridge_multiplier: float = 0.25,
    removed_feature_count: int = 0,
    cancellation: CancellationContext | None,
) -> ConditionalComponentAblation:
    if not active:
        return _abstained_ablation(
            kind,
            component_id,
            "no active evidence remains for this ablation",
            removed_feature_count=removed_feature_count,
        )
    try:
        result = solve_conditional_coordinates(
            design,
            _solver_evidence(active, scale),
            global_ridge_multiplier=global_ridge_multiplier,
            cancellation=cancellation,
        )
    except ReactomeConditionalInferenceError:
        return _abstained_ablation(
            kind,
            component_id,
            "ablation robust solve failed",
            removed_feature_count=removed_feature_count,
        )
    if not _solve_is_valid(result):
        return _abstained_ablation(
            kind,
            component_id,
            "ablation did not satisfy convergence and condition gates",
            removed_feature_count=removed_feature_count,
        )
    return _numeric_ablation(
        kind,
        component_id,
        point_score,
        float(result.coordinates[coordinate_index]) / score_scale,
        "point sensitivity only; no ablation-specific bootstrap calibration",
        removed_feature_count=removed_feature_count,
    )


def _pathway_ablations(
    active: tuple[_ActivePair, ...],
    catalog: ReactomeConditionalFittedCatalog,
    pathway: FittedPathwayLoading,
    point_score: float,
    overlap_solve_cache: dict[tuple[int, ...], ConditionalSolveResult | None],
    *,
    cancellation: CancellationContext | None,
) -> ConditionalPathwayAblations:
    path_column = pathway.panel_index + 1
    without_global = np.ascontiguousarray(
        catalog.reference_design[:, 1:],
        dtype=np.float64,
    )
    global_axis = _solve_ablation(
        active,
        catalog.reference_scale,
        without_global,
        pathway.panel_index,
        pathway.cross_fitted_mad_scale,
        "global_axis",
        "global_recurrence",
        point_score,
        global_ridge_multiplier=1.0,
        cancellation=cancellation,
    )
    source_processing = _solve_ablation(
        active,
        catalog.reference_scale,
        catalog.ordinary_design,
        path_column,
        pathway.cross_fitted_mad_scale,
        "source_processing",
        "ordinary_log_source_measure",
        point_score,
        cancellation=cancellation,
    )
    degree = _solve_ablation(
        active,
        catalog.reference_scale,
        catalog.no_degree_design,
        path_column,
        pathway.cross_fitted_mad_scale,
        "degree_normalization",
        "no_shared_gene_degree_normalization",
        point_score,
        cancellation=cancellation,
    )
    unique_positions = frozenset(pathway.unique_member_local_indices)
    unique_active = tuple(
        pair for pair in active if pair.local_position in unique_positions
    )
    if len(unique_active) < PATHWAY_MIN_UNIQUE_GENES:
        unique = _abstained_ablation(
            "unique_members",
            pathway.reactome_id,
            "fewer than three active unique pathway members",
            removed_feature_count=max(0, len(active) - len(unique_active)),
        )
    else:
        unique_design = np.ascontiguousarray(
            catalog.reference_design[:, (0, path_column)],
            dtype=np.float64,
        )
        unique = _solve_ablation(
            unique_active,
            catalog.reference_scale,
            unique_design,
            1,
            pathway.cross_fitted_mad_scale,
            "unique_members",
            pathway.reactome_id,
            point_score,
            removed_feature_count=max(0, len(active) - len(unique_active)),
            cancellation=cancellation,
        )
    leave = _numeric_ablation(
        "leave_pathway_out",
        pathway.reactome_id,
        point_score,
        0.0,
        "removed coordinates are defined as zero; held-gene reconstruction reports impact",
    )
    target_members = frozenset(pathway.member_local_indices)
    overlap: list[ConditionalComponentAblation] = []
    for other in catalog.pathways:
        if other.panel_index == pathway.panel_index:
            continue
        shared = target_members & frozenset(other.member_local_indices)
        removed = tuple(pair for pair in active if pair.local_position in shared)
        if not removed:
            continue
        remaining = tuple(pair for pair in active if pair.local_position not in shared)
        remaining_metrics = _mass_metrics(
            remaining,
            pathway.unadjusted_loading,
            pathway.member_local_indices,
            catalog.reference_scale,
        )
        if (
            remaining_metrics.active_count < PATHWAY_MIN_ACTIVE_GENES
            or remaining_metrics.coverage < PATHWAY_MIN_COEFFICIENT_MASS
            or remaining_metrics.effective_sample_size
            < PATHWAY_MIN_EFFECTIVE_SAMPLE_SIZE
        ):
            overlap.append(
                _abstained_ablation(
                    "overlapping_pathway",
                    other.reactome_id,
                    "removing shared active members fails target pathway support gates",
                    removed_feature_count=len(removed),
                )
            )
            continue
        removed_positions = tuple(sorted(pair.local_position for pair in removed))
        checkpoint(cancellation)
        if removed_positions not in overlap_solve_cache:
            try:
                overlap_solve_cache[removed_positions] = solve_conditional_coordinates(
                    catalog.reference_design,
                    _solver_evidence(remaining, catalog.reference_scale),
                    cancellation=cancellation,
                )
            except ReactomeConditionalInferenceError:
                overlap_solve_cache[removed_positions] = None
        overlap_result = overlap_solve_cache[removed_positions]
        if overlap_result is None:
            overlap.append(
                _abstained_ablation(
                    "overlapping_pathway",
                    other.reactome_id,
                    "overlap-removal robust solve failed",
                    removed_feature_count=len(removed),
                )
            )
            continue
        if not _solve_is_valid(overlap_result):
            overlap.append(
                _abstained_ablation(
                    "overlapping_pathway",
                    other.reactome_id,
                    "overlap-removal solve did not satisfy convergence and condition gates",
                    removed_feature_count=len(removed),
                )
            )
            continue
        overlap.append(
            _numeric_ablation(
                "overlapping_pathway",
                other.reactome_id,
                point_score,
                float(overlap_result.coordinates[path_column])
                / pathway.cross_fitted_mad_scale,
                "point sensitivity after refitting without shared active members; "
                "no ablation-specific bootstrap calibration",
                removed_feature_count=len(removed),
            )
        )
    return ConditionalPathwayAblations(
        global_axis=global_axis,
        source_processing=(source_processing,),
        degree_normalization=degree,
        unique_members=unique,
        leave_pathway_out=leave,
        overlap=tuple(overlap),
    )


def _gene_fold(gene_symbol: str) -> int:
    return (
        int.from_bytes(
            hashlib.sha256(f"{_GENE_FOLD_SALT}:{gene_symbol}".encode()).digest()[:2],
            "big",
        )
        % _GENE_FOLDS
    )


def _request_reconstruction(
    active: tuple[_ActivePair, ...],
    catalog: ReactomeConditionalFittedCatalog,
    *,
    cancellation: CancellationContext | None,
) -> tuple[tuple[int, int, float], ...]:
    gains: list[list[float]] = [[] for _ in catalog.pathways]
    exact = tuple(pair for pair in active if pair.semantics == "exact_delta")
    for fold in range(_GENE_FOLDS):
        checkpoint(cancellation)
        inference = tuple(pair for pair in active if _gene_fold(pair.gene_symbol) != fold)
        validation = tuple(pair for pair in exact if _gene_fold(pair.gene_symbol) == fold)
        if len(inference) < GLOBAL_MIN_ACTIVE_GENES or not validation:
            continue
        try:
            full = solve_conditional_coordinates(
                catalog.reference_design,
                _solver_evidence(inference, catalog.reference_scale),
                cancellation=cancellation,
            )
        except ReactomeConditionalInferenceError:
            continue
        if not _solve_is_valid(full):
            continue
        positions = np.asarray(
            [pair.local_position for pair in validation],
            dtype=np.int64,
        )
        targets = np.asarray(
            [
                pair.raw_delta / float(catalog.reference_scale[pair.local_position])
                for pair in validation
            ],
            dtype=np.float64,
        )
        full_prediction = catalog.reference_design[positions] @ np.asarray(
            full.coordinates,
            dtype=np.float64,
        )
        full_mae = float(np.median(np.abs(targets - full_prediction)))
        for pathway in catalog.pathways:
            keep = np.arange(catalog.reference_design.shape[1]) != pathway.panel_index + 1
            omitted_design = np.ascontiguousarray(
                catalog.reference_design[:, keep],
                dtype=np.float64,
            )
            try:
                omitted = solve_conditional_coordinates(
                    omitted_design,
                    _solver_evidence(inference, catalog.reference_scale),
                    cancellation=cancellation,
                )
            except ReactomeConditionalInferenceError:
                continue
            if not _solve_is_valid(omitted):
                continue
            omitted_prediction = omitted_design[positions] @ np.asarray(
                omitted.coordinates,
                dtype=np.float64,
            )
            omitted_mae = float(np.median(np.abs(targets - omitted_prediction)))
            denominator = max(omitted_mae, 1.0e-12)
            gains[pathway.panel_index].append((omitted_mae - full_mae) / denominator)
    return tuple(
        (
            len(pathway_gains),
            sum(value > 0.0 for value in pathway_gains),
            float(np.median(np.asarray(pathway_gains, dtype=np.float64)))
            if pathway_gains
            else 0.0,
        )
        for pathway_gains in gains
    )


def _top_contributions(
    active: tuple[_ActivePair, ...],
    pathway: FittedPathwayLoading,
    scale: FloatArray,
) -> tuple[ConditionalProteinContribution, ...]:
    members = frozenset(pathway.member_local_indices)
    rows: list[tuple[float, ConditionalProteinContribution]] = []
    for pair in active:
        if pair.local_position not in members or pair.semantics != "exact_delta":
            continue
        feature_scale = float(scale[pair.local_position])
        standardized = pair.raw_delta / feature_scale
        reliability = _reliability(pair, feature_scale)
        unadjusted = (
            standardized
            * float(pathway.unadjusted_loading[pair.local_position])
            * reliability
        )
        adjustment = (
            standardized
            * float(pathway.global_adjustment_loading[pair.local_position])
            * reliability
        )
        conditional = unadjusted - adjustment
        conditional_q = _quantize(conditional)
        if conditional_q == 0.0:
            continue
        row = ConditionalProteinContribution(
            gene_symbol=pair.gene_symbol,
            from_observation_id=pair.from_observation.observation_id,
            to_observation_id=pair.to_observation.observation_id,
            from_provenance_digest=pair.from_observation.provenance_digest,
            to_provenance_digest=pair.to_observation.provenance_digest,
            from_state=ProteinEvidenceState.OBSERVED,
            to_state=ProteinEvidenceState.OBSERVED,
            value_semantics=ValueSemantics.EXACT_DELTA,
            standardized_delta=_quantize(standardized),
            pathway_loading=_quantize(
                float(pathway.unadjusted_loading[pair.local_position])
            ),
            global_loading=_quantize(
                float(pathway.global_adjustment_loading[pair.local_position])
            ),
            unadjusted_contribution=_quantize(unadjusted),
            global_adjustment_contribution=_quantize(adjustment),
            conditional_contribution=conditional_q,
            direction=(
                ContributionDirection.CONDITIONAL_SOURCE_RECURRENCE_ALIGNED
                if conditional_q > 0.0
                else ContributionDirection.CONDITIONAL_SOURCE_PRIMARY_ALIGNED
            ),
            reliability_weight=_probability(reliability),
        )
        rows.append((abs(conditional), row))
    rows.sort(key=lambda item: (-item[0], item[1].gene_symbol))
    return tuple(item[1] for item in rows[:MAX_TOP_CONTRIBUTIONS])


def _discordance(
    active: tuple[_ActivePair, ...],
    pathway: FittedPathwayLoading,
    scale: FloatArray,
    score: float,
) -> float:
    if score == 0.0:
        return 0.0
    members = frozenset(pathway.member_local_indices)
    contributions: list[float] = []
    for pair in active:
        if pair.local_position not in members or pair.semantics != "exact_delta":
            continue
        feature_scale = float(scale[pair.local_position])
        contributions.append(
            pair.raw_delta
            / feature_scale
            * float(pathway.conditional_loading[pair.local_position])
            * _reliability(pair, feature_scale)
        )
    mass = math.fsum(abs(value) for value in contributions)
    if mass <= 0.0:
        return 0.0
    opposite = math.fsum(
        abs(value) for value in contributions if value * score < 0.0
    )
    return opposite / mass


def _abstained_pathway(  # noqa: PLR0917
    catalog: ReactomeConditionalFittedCatalog,
    pathway: FittedPathwayLoading,
    metrics: _MassMetrics,
    unique_count: int,
    unique_mass: float,
    reasons: tuple[str, ...],
) -> ReactomePathwayConcordance:
    source = catalog.source_catalog.pathways[pathway.panel_index]
    return ReactomePathwayConcordance(
        panel_index=pathway.panel_index,
        domain_id=pathway.domain_id,
        reactome_id=pathway.reactome_id,
        pathway_name=pathway.name,
        support=AnalysisSupport.ABSTAINED,
        classification=ConditionalTransitionClassification.NOT_ESTIMABLE,
        source_member_count=source.source_member_count,
        mapped_feature_count=source.mapped_feature_count,
        fitted_feature_count=sum(
            bool(catalog.reference_eligible[position])
            for position in pathway.member_local_indices
        ),
        active_feature_count=metrics.active_count,
        observed_count=metrics.observed_count,
        left_censored_count=metrics.left_censored_count,
        coefficient_mass_coverage=_probability(metrics.coverage),
        unique_active_gene_count=unique_count,
        unique_coefficient_mass=_probability(unique_mass),
        effective_sample_size=_quantize(metrics.effective_sample_size),
        uncertainty=_not_estimable_uncertainty(reasons[0]),
        overlap_confounded=pathway.reactome_id == PI3K_REACTOME_ID,
        ablations=ConditionalPathwayAblations(),
        abstention_reasons=reasons[:12],
    )


def _pathway_result(  # noqa: PLR0915, PLR0917
    active: tuple[_ActivePair, ...],
    catalog: ReactomeConditionalFittedCatalog,
    pathway: FittedPathwayLoading,
    point: ConditionalSolveResult,
    bootstraps: _BootstrapCoordinates,
    global_result: GlobalRecurrenceConcordance,
    reconstruction: tuple[int, int, float],
    overlap_solve_cache: dict[tuple[int, ...], ConditionalSolveResult | None],
    *,
    cancellation: CancellationContext | None,
) -> ReactomePathwayConcordance:
    metrics = _mass_metrics(
        active,
        pathway.unadjusted_loading,
        pathway.member_local_indices,
        catalog.reference_scale,
    )
    by_position = {pair.local_position: pair for pair in active}
    unique_positions = tuple(
        position
        for position in pathway.unique_member_local_indices
        if position in by_position
    )
    total_mass = math.fsum(
        abs(float(pathway.unadjusted_loading[position]))
        for position in pathway.member_local_indices
    )
    unique_mass = (
        math.fsum(
            abs(float(pathway.unadjusted_loading[position]))
            for position in unique_positions
        )
        / total_mass
        if total_mass > 0.0
        else 0.0
    )
    reasons: list[str] = []
    if global_result.support is AnalysisSupport.ABSTAINED:
        reasons.append("global recurrence coordinate is not estimable")
    if not _solve_is_valid(point):
        reasons.append("primary joint robust solve did not satisfy convergence and condition gates")
    if metrics.active_count < PATHWAY_MIN_ACTIVE_GENES:
        reasons.append("fewer than five active fitted pathway genes")
    if metrics.coverage < PATHWAY_MIN_COEFFICIENT_MASS:
        reasons.append("pathway coefficient-mass coverage is below 0.50")
    if metrics.effective_sample_size < PATHWAY_MIN_EFFECTIVE_SAMPLE_SIZE:
        reasons.append("pathway effective sample size is below 3")
    if bootstraps.successful_replicates < _MINIMUM_RUNTIME_BOOTSTRAPS:
        reasons.append("fewer than 32 fitted bootstrap paths converged")
    if reasons:
        return _abstained_pathway(
            catalog,
            pathway,
            metrics,
            len(unique_positions),
            unique_mass,
            tuple(reasons),
        )

    path_column = pathway.panel_index + 1
    score = float(point.coordinates[path_column]) / pathway.cross_fitted_mad_scale
    measurement = tuple(
        row[path_column] / pathway.cross_fitted_mad_scale
        for row in bootstraps.measurement
    )
    fitted_model = tuple(
        row[path_column] / pathway.cross_fitted_mad_scale
        for row in bootstraps.fitted_model
    )
    combined = tuple(
        row[path_column] / pathway.cross_fitted_mad_scale
        for row in bootstraps.combined
    )
    uncertainty, lower, upper = _uncertainty(
        score,
        measurement,
        fitted_model,
        combined,
    )
    score_q = _quantize(score)
    classification = _pathway_classification(lower, upper)
    point_class = _point_pathway_classification(score_q)
    stability = math.fsum(
        _point_pathway_classification(_quantize(value)) is point_class
        for value in combined
    ) / len(combined)
    ablations = _pathway_ablations(
        active,
        catalog,
        pathway,
        score_q,
        overlap_solve_cache,
        cancellation=cancellation,
    )
    structural = cast(
        "tuple[ConditionalComponentAblation, ...]",
        ablations.required_structural(),
    )
    evaluable_folds, improved_folds, median_gain = reconstruction
    limited: list[str] = []
    if bootstraps.failed_replicates:
        limited.append("one or more requested fitted bootstrap paths were not estimable")
    if bootstraps.successful_replicates < 64:
        limited.append("fewer than 64 fitted bootstrap paths limit stability evidence")
    if classification is ConditionalTransitionClassification.INDETERMINATE:
        limited.append("the 90% interval does not support a directional or stable class")
    if stability < 0.8:
        limited.append("fewer than 80% of fitted draws retain the point classification")
    if len(unique_positions) < PATHWAY_MIN_UNIQUE_GENES:
        limited.append("fewer than three active unique pathway members")
    if unique_mass < PATHWAY_MIN_UNIQUE_MASS:
        limited.append("unique-member coefficient mass is below 0.20")
    if pathway.reactome_id == PI3K_REACTOME_ID:
        limited.append("PI3K/AKT is overlap-confounded in the fixed panel")
    if evaluable_folds < 5:
        limited.append("fewer than all five held-gene reconstruction folds were evaluable")
    if improved_folds < 4:
        limited.append("the full path improves fewer than four of five held-gene folds")
    if median_gain < 0.01:
        limited.append("median held-gene reconstruction gain is below 1%")
    if any(item.support is AnalysisSupport.ABSTAINED for item in structural):
        limited.append("one or more structural ablations are not estimable")
    if any(
        item.support is not AnalysisSupport.ABSTAINED
        and cast("float", item.conditional_score_without_component) * score_q < 0.0
        for item in structural
    ):
        limited.append("a structural ablation reverses the fitted coordinate direction")
    global_adjustment = (
        pathway.global_projection
        / pathway.residual_norm
        * float(point.coordinates[0])
        / pathway.cross_fitted_mad_scale
    )
    source = catalog.source_catalog.pathways[pathway.panel_index]
    return ReactomePathwayConcordance(
        panel_index=pathway.panel_index,
        domain_id=pathway.domain_id,
        reactome_id=pathway.reactome_id,
        pathway_name=pathway.name,
        support=AnalysisSupport.LIMITED if limited else AnalysisSupport.SUPPORTED,
        classification=classification,
        score=score_q,
        lower_bound=lower,
        upper_bound=upper,
        unadjusted_pathway_coordinate=_quantize(score + global_adjustment),
        global_adjustment=_quantize(global_adjustment),
        source_member_count=source.source_member_count,
        mapped_feature_count=source.mapped_feature_count,
        fitted_feature_count=sum(
            bool(catalog.reference_eligible[position])
            for position in pathway.member_local_indices
        ),
        active_feature_count=metrics.active_count,
        observed_count=metrics.observed_count,
        left_censored_count=metrics.left_censored_count,
        coefficient_mass_coverage=_probability(metrics.coverage),
        unique_active_gene_count=len(unique_positions),
        unique_coefficient_mass=_probability(unique_mass),
        effective_sample_size=_quantize(metrics.effective_sample_size),
        request_reconstruction_evaluable_fold_count=evaluable_folds,
        request_reconstruction_improved_fold_count=improved_folds,
        request_reconstruction_median_relative_gain=_quantize(median_gain),
        stability=_probability(stability),
        discordance=_probability(
            _discordance(active, pathway, catalog.reference_scale, score_q)
        ),
        overlap_confounded=pathway.reactome_id == PI3K_REACTOME_ID,
        uncertainty=uncertainty,
        top_contributions=_top_contributions(
            active,
            pathway,
            catalog.reference_scale,
        ),
        ablations=ablations,
        abstention_reasons=tuple(limited[:12]),
    )


def _invalid_solve(coordinate_count: int) -> ConditionalSolveResult:
    return ConditionalSolveResult(
        coordinates=tuple(0.0 for _ in range(coordinate_count)),
        diagnostics=ConditionalSolverDiagnostics(
            converged=False,
            iterations=0,
            final_max_coordinate_change=math.inf,
            initial_objective=math.inf,
            final_objective=math.inf,
            objective_trace=(),
            objective_monotone=False,
            active_evidence_count=0,
            exact_evidence_count=0,
            upper_bound_count=0,
            lower_bound_count=0,
            design_condition_number=math.inf,
        ),
    )


def _calculate_transition(
    request: LongitudinalGbmReactomeTransitionRequest,
    transition_index: int,
    catalog: ReactomeConditionalFittedCatalog,
    numerical_seed_digest: str,
    *,
    cancellation: CancellationContext | None,
) -> ReactomeConditionalTransitionEvidence:
    active = _active_pairs(request, transition_index, catalog)
    global_loading = np.ascontiguousarray(
        catalog.reference_design[:, 0] / math.sqrt(catalog.union_feature_count),
        dtype=np.float64,
    )
    global_metrics = _mass_metrics(
        active,
        global_loading,
        tuple(range(catalog.union_feature_count)),
        catalog.reference_scale,
    )
    if active:
        try:
            point = solve_conditional_coordinates(
                catalog.reference_design,
                _solver_evidence(active, catalog.reference_scale),
                cancellation=cancellation,
            )
        except ReactomeConditionalInferenceError:
            point = _invalid_solve(catalog.pathway_count + 1)
        can_bootstrap = (
            global_metrics.active_count >= GLOBAL_MIN_ACTIVE_GENES
            and global_metrics.coverage >= GLOBAL_MIN_COEFFICIENT_MASS
            and global_metrics.effective_sample_size
            >= GLOBAL_MIN_EFFECTIVE_SAMPLE_SIZE
            and _solve_is_valid(point)
        )
        bootstraps = (
            _bootstrap_coordinates(
                active,
                catalog,
                numerical_seed_digest,
                transition_index,
                request.bootstrap_replicates,
                cancellation=cancellation,
            )
            if can_bootstrap
            else _BootstrapCoordinates((), (), (), (), 0)
        )
    else:
        point = _invalid_solve(catalog.pathway_count + 1)
        bootstraps = _BootstrapCoordinates((), (), (), (), 0)
    global_scale = catalog.cross_fitted_coordinate_scales["global_recurrence"]
    global_result = _global_result(point, bootstraps, global_metrics, global_scale)
    reconstruction = (
        _request_reconstruction(active, catalog, cancellation=cancellation)
        if global_result.support is not AnalysisSupport.ABSTAINED
        else tuple((0, 0, 0.0) for _ in catalog.pathways)
    )
    overlap_solve_cache: dict[tuple[int, ...], ConditionalSolveResult | None] = {}
    pathways = tuple(
        _pathway_result(
            active,
            catalog,
            pathway,
            point,
            bootstraps,
            global_result,
            reconstruction[pathway.panel_index],
            overlap_solve_cache,
            cancellation=cancellation,
        )
        for pathway in catalog.pathways
    )
    left = request.time_points[transition_index]
    right = request.time_points[transition_index + 1]
    return ReactomeConditionalTransitionEvidence(
        transition_id=f"reactome.transition.{transition_index:02d}",
        transition_index=transition_index,
        from_time_point_id=left.time_point_id,
        to_time_point_id=right.time_point_id,
        duration_days=_quantize(right.time_offset_days - left.time_offset_days),
        global_recurrence=global_result,
        pathways=pathways,
    )


def semantic_result_projection(
    result: LongitudinalGbmReactomeTransitionResult,
) -> dict[str, object]:
    """Project deterministic scientific semantics without receipt circularity."""

    return {
        "assay_compatibility": result.assay_compatibility.model_dump(mode="json"),
        "time_point_ids": result.time_point_ids,
        "transitions": tuple(
            transition.model_dump(mode="json") for transition in result.transitions
        ),
        "output_semantics": result.output_semantics,
        "validation_scope": result.validation_scope,
        "research_use_only": result.research_use_only,
        "non_prescriptive": result.non_prescriptive,
    }


def infer_longitudinal_gbm_reactome_transition(
    request: LongitudinalGbmReactomeTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmReactomeTransitionResult:
    """Infer global and conditional fitted coordinates without persisting inputs."""

    checkpoint(cancellation)
    catalog = reactome_conditional_fitted_catalog()
    profile = algorithm_profile()
    validated = _validate_request(request, catalog)
    request_digest = canonical_request_digest(validated)
    computational_digest = computational_request_digest(
        validated,
        profile_digest=profile.profile_digest,
    )
    numerical_seed_digest = computational_request_digest(
        validated,
        profile_digest=catalog.content_digest,
    )
    transitions = tuple(
        _calculate_transition(
            validated,
            index,
            catalog,
            numerical_seed_digest,
            cancellation=cancellation,
        )
        for index in range(len(validated.time_points) - 1)
    )
    source = catalog.source_catalog
    evidence_digest = sha256_digest(
        tuple(
            tuple(
                observation.model_dump(mode="json")
                for observation in sorted(
                    point.observations,
                    key=lambda item: (item.gene_symbol, item.observation_id),
                )
            )
            for point in validated.time_points
        )
    )
    provenance = ReactomeTransitionProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        computational_digest=computational_digest,
        numerical_seed_digest=numerical_seed_digest,
        source_catalog_artifact_digest=source.artifact_byte_digest,
        source_catalog_content_digest=source.content_digest,
        source_binding_digest=source.source_binding_digest,
        selection_candidate_digest=source.selection_candidate_digest,
        pathway_order_digest=source.pathway_order_digest,
        pathway_membership_digest=source.pathway_membership_digest,
        gene_order_digest=source.gene_order_digest,
        patient_order_rule_digest=source.patient_order_rule_digest,
        fitted_artifact_digest=catalog.artifact_byte_digest,
        fitted_content_digest=catalog.content_digest,
        union_feature_digest=catalog.union_feature_digest,
        reference_tensor_digest=catalog.reference_tensor_digest,
        centering_scaling_digest=catalog.centering_scaling_digest,
        reference_design_digest=catalog.reference_design_digest,
        global_loading_digest=catalog.global_loading_digest,
        conditional_loading_digest=catalog.conditional_loading_digest,
        bootstrap_ensemble_digest=catalog.bootstrap_ensemble_digest,
        training_recipe_digest=catalog.training_recipe_digest,
        fold_policy_digest=catalog.fold_policy_digest,
        source_processing_ablation_digest=catalog.source_processing_ablation_digest,
        evaluation_digest=catalog.evaluation_digest,
        input_contract_schema_digest=profile.digests.input_contract_schema_digest,
        engine_semantic_digest=profile.digests.engine_semantic_digest,
        demo_semantic_oracle_digest=profile.demo_semantic_oracle_digest,
        assay_compatibility_digest=sha256_digest(
            validated.assay_compatibility.model_dump(mode="json")
        ),
        normalization_reference_digest=validated.normalization_reference.binding_digest,
        caller_evidence_set_digest=evidence_digest,
        numpy_version=catalog.numpy_version,
        bootstrap_seed=_receipt_seed(numerical_seed_digest),
        source_attribution=profile.source_attribution,
        source_licenses=profile.source_licenses,
        source_transformation_notice=profile.source_transformation_notice,
    )
    unverified = UnverifiedLongitudinalGbmReactomeTransitionResult(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest="sha256:" + "0" * 64,
        series_id=validated.series_id,
        assay_compatibility=validated.assay_compatibility,
        normalization_reference=validated.normalization_reference,
        time_point_ids=tuple(point.time_point_id for point in validated.time_points),
        transitions=transitions,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    document = unverified.model_dump(mode="python")
    document["result_digest"] = result_payload_digest(unverified)
    result = LongitudinalGbmReactomeTransitionResult.model_validate(document)
    if (
        request_digest == profile.demo_request_digest
        and sha256_digest(semantic_result_projection(result))
        != EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST
    ):
        raise ReactomeConditionalModelIntegrityError(
            "synthetic Reactome demo semantic oracle digest mismatch"
        )
    checkpoint(cancellation)
    return result


__all__ = [
    "infer_longitudinal_gbm_reactome_transition",
    "semantic_result_projection",
]
