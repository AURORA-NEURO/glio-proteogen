"""Deterministic fitted longitudinal GBM participant-transition engine."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Mapping, cast

import numpy as np

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import (
    canonical_request_digest,
    computational_request_digest,
    result_payload_digest,
)
from .contracts import (
    MIN_ACTIVE_MEMBERS,
    MIN_COEFFICIENT_MASS,
    MIN_EFFECTIVE_SAMPLE_SIZE,
    MIN_MEMBER_RELIABILITY,
    AnalysisSupport,
    ComplexComponentAblation,
    ComplexMemberContribution,
    ComplexMemberTransitionConcordance,
    ComplexTransitionAblations,
    ComplexTransitionClassification,
    ComplexTransitionEvidence,
    ComplexTransitionProvenance,
    ComplexTransitionUncertainty,
    ContributionDirection,
    LongitudinalGbmComplexTransitionRequest,
    LongitudinalGbmComplexTransitionResult,
    ProteinEvidenceState,
    ProteinObservation,
    UncertaintyState,
    UnverifiedLongitudinalGbmComplexTransitionResult,
    ValueSemantics,
    classify_interval,
)
from .errors import ComplexTransitionInferenceError
from .fitted_catalog import (
    ComplexTransitionFittedCatalog,
    FittedComplexModel,
    complex_transition_fitted_catalog,
)
from .profile import algorithm_profile
from .solver import MemberCoordinateSolve, MemberEvidence, solve_member_coordinate

if TYPE_CHECKING:
    from .source_catalog import ReactomeComplexBinding

_ACTIVE_STATES: Final = frozenset(
    {ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED}
)
_MINIMUM_SUCCESSFUL_BOOTSTRAPS: Final = 32
_RIDGE_LAMBDA: Final = 0.075
_LIMITATIONS: Final = (
    "Research-use-only same-cohort participant-transition concordance; not clinical evidence.",
    "Internal held-patient/member reconstruction is not external validation.",
    "Reactome membership does not establish physical assembly, abundance, or activity.",
    "Reactome membership does not identify essential subunits or quantitative stoichiometry.",
    "Names can encode modification, nucleotide, ligand, and compartment states that protein abundance cannot establish.",
    "Alternative and nested member sets are retained; a coordinate is not occupancy.",
    "One-sided censor limits are retained as bounds; one-sided-only evidence abstains.",
    "Missing and unsupported observations are excluded and never become negative evidence.",
    "Members below 0.05 effective reliability cannot satisfy the support-count gate.",
    "Bootstrap intervals capture measurement and fitted-source sensitivity, not probability.",
    "The fixed 28-complex panel is pilot coverage rather than an exhaustive GBM complexome.",
    "Outputs are non-prescriptive and are not recurrence, prognosis, or treatment predictions.",
)


@dataclass(frozen=True, slots=True)
class _ActiveMember:
    member_position: int
    feature_index: int
    gene_symbol: str
    from_observation: ProteinObservation
    to_observation: ProteinObservation
    raw_delta: float
    semantics: ValueSemantics
    delta_standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _BootstrapCoordinates:
    measurement: tuple[float, ...]
    fitted_model: tuple[float, ...]
    combined: tuple[float, ...]
    failed_replicates: int

    @property
    def successful_replicates(self) -> int:
        return len(self.combined)


@dataclass(frozen=True, slots=True)
class _MassMetrics:
    active_count: int
    reliable_count: int
    observed_count: int
    left_censored_count: int
    coverage: float
    effective_sample_size: float


def _quantize(value: float) -> float:
    if not math.isfinite(value):
        raise ComplexTransitionInferenceError(
            "complex-transition computation produced a non-finite value"
        )
    result = round(float(value), 10)
    return 0.0 if result == 0.0 else result


def _probability(value: float) -> float:
    return min(1.0, max(0.0, _quantize(value)))


def _stream_seed(seed_digest: str, stream: str) -> int:
    payload = f"{seed_digest}:{stream}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _receipt_seed(seed_digest: str) -> int:
    return _stream_seed(seed_digest, "complex-receipt-bootstrap-v1") % (2**53)


def _sample_variance(values: tuple[float, ...]) -> float:
    if len(values) < 2:
        return 0.0
    mean = math.fsum(values) / len(values)
    return math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _sample_covariance(
    left: tuple[float, ...],
    right: tuple[float, ...],
) -> float:
    if len(left) != len(right):
        raise ComplexTransitionInferenceError("paired bootstrap streams have unequal lengths")
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
        raise ComplexTransitionInferenceError("quantile requires fitted values")
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
    square_total = math.fsum(value * value for value in scaled)
    return total * total / square_total if square_total > 0.0 else 0.0


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ComplexTransitionInferenceError(f"fitted evaluation {name!r} is not an object")
    return cast("Mapping[str, object]", value)


def _number(value: object, name: str) -> float:
    if type(value) not in {int, float}:
        raise ComplexTransitionInferenceError(f"fitted evaluation {name!r} is not numeric")
    result = float(cast("int | float", value))
    if not math.isfinite(result):
        raise ComplexTransitionInferenceError(f"fitted evaluation {name!r} is non-finite")
    return result


def _source_gain_interval(catalog: ComplexTransitionFittedCatalog) -> tuple[float, float]:
    bootstrap = _mapping(
        catalog.evaluation.get("patient_cluster_bootstrap"),
        "patient_cluster_bootstrap",
    )
    raw = bootstrap.get("nominal_90_percent_interval")
    if not isinstance(raw, list) or len(raw) != 2:
        raise ComplexTransitionInferenceError("fitted source gain interval is malformed")
    return (_number(raw[0], "gain.lower"), _number(raw[1], "gain.upper"))


def _validate_request(
    request: LongitudinalGbmComplexTransitionRequest,
    catalog: ComplexTransitionFittedCatalog,
) -> LongitudinalGbmComplexTransitionRequest:
    validated = LongitudinalGbmComplexTransitionRequest.model_validate(request, strict=True)
    profile = algorithm_profile()
    if validated.assay_compatibility != profile.required_assay_compatibility:
        raise ComplexTransitionInferenceError(
            "input assay attestation does not match the locked PDC000514 TMT11 "
            "Unshared Log2 source scale"
        )
    unknown = sorted(
        {
            observation.gene_symbol
            for point in validated.time_points
            for observation in point.observations
            if observation.state in _ACTIVE_STATES
            and observation.gene_symbol not in catalog.source_catalog.gene_index_by_symbol
        }
    )
    if unknown:
        raise ComplexTransitionInferenceError(
            "active protein symbols are outside the locked 11,312-gene source axis: "
            + ", ".join(unknown[:5])
        )
    return validated


def _observation_map(
    observations: tuple[ProteinObservation, ...],
) -> dict[str, ProteinObservation]:
    return {item.gene_symbol: item for item in observations}


def _pair_semantics(
    left: ProteinObservation,
    right: ProteinObservation,
) -> ValueSemantics | None:
    if left.state is ProteinEvidenceState.OBSERVED:
        return (
            ValueSemantics.EXACT_DELTA
            if right.state is ProteinEvidenceState.OBSERVED
            else ValueSemantics.UPPER_BOUND
        )
    if right.state is ProteinEvidenceState.OBSERVED:
        return ValueSemantics.LOWER_BOUND
    return None


def _active_members(
    request: LongitudinalGbmComplexTransitionRequest,
    transition_index: int,
    model: FittedComplexModel,
    catalog: ComplexTransitionFittedCatalog,
) -> tuple[_ActiveMember, ...]:
    left = _observation_map(request.time_points[transition_index].observations)
    right = _observation_map(request.time_points[transition_index + 1].observations)
    result: list[_ActiveMember] = []
    for member_position, feature_index in enumerate(model.member_feature_indices):
        symbol = catalog.source_catalog.genes[feature_index]
        from_observation = left.get(symbol)
        to_observation = right.get(symbol)
        if (
            from_observation is None
            or to_observation is None
            or from_observation.state not in _ACTIVE_STATES
            or to_observation.state not in _ACTIVE_STATES
        ):
            continue
        semantics = _pair_semantics(from_observation, to_observation)
        if semantics is None:
            continue
        from_value = cast("float", from_observation.log_abundance)
        to_value = cast("float", to_observation.log_abundance)
        result.append(
            _ActiveMember(
                member_position=member_position,
                feature_index=feature_index,
                gene_symbol=symbol,
                from_observation=from_observation,
                to_observation=to_observation,
                raw_delta=to_value - from_value,
                semantics=semantics,
                delta_standard_error=math.hypot(
                    cast("float", from_observation.standard_error),
                    cast("float", to_observation.standard_error),
                ),
                quality_weight=math.sqrt(
                    from_observation.quality_weight * to_observation.quality_weight
                ),
            )
        )
    return tuple(result)


def _reliability(item: _ActiveMember, scale: float, source_reliability: float) -> float:
    relative_error = item.delta_standard_error / scale
    return min(
        1.0,
        max(
            1.0e-12,
            item.quality_weight * source_reliability / (1.0 + relative_error**2),
        ),
    )


def _solver_evidence(
    active: tuple[_ActiveMember, ...],
    scales: np.ndarray[tuple[int], np.dtype[np.float64]],
    source_reliabilities: np.ndarray[tuple[int], np.dtype[np.float64]],
    *,
    perturbed_deltas: tuple[float, ...] | None = None,
    excluded_positions: frozenset[int] = frozenset(),
) -> tuple[MemberEvidence, ...]:
    result: list[MemberEvidence] = []
    for active_index, item in enumerate(active):
        if item.member_position in excluded_positions:
            continue
        scale = float(scales[item.member_position])
        raw_delta = item.raw_delta if perturbed_deltas is None else perturbed_deltas[active_index]
        result.append(
            MemberEvidence(
                member_position=item.member_position,
                value=raw_delta / scale,
                semantics=item.semantics.value,
                reliability_weight=_reliability(
                    item,
                    scale,
                    float(source_reliabilities[item.member_position]),
                ),
            )
        )
    return tuple(result)


def _solve(
    active: tuple[_ActiveMember, ...],
    scales: np.ndarray[tuple[int], np.dtype[np.float64]],
    source_reliabilities: np.ndarray[tuple[int], np.dtype[np.float64]],
    loadings: np.ndarray[tuple[int], np.dtype[np.float64]],
    *,
    perturbed_deltas: tuple[float, ...] | None = None,
    excluded_positions: frozenset[int] = frozenset(),
    cancellation: CancellationContext | None = None,
) -> MemberCoordinateSolve | None:
    evidence = _solver_evidence(
        active,
        scales,
        source_reliabilities,
        perturbed_deltas=perturbed_deltas,
        excluded_positions=excluded_positions,
    )
    if len(evidence) < MIN_ACTIVE_MEMBERS:
        return None
    return solve_member_coordinate(
        loadings,
        evidence,
        ridge_lambda=_RIDGE_LAMBDA,
        cancellation=cancellation,
    )


def _mass_metrics(
    active: tuple[_ActiveMember, ...],
    model: FittedComplexModel,
) -> _MassMetrics:
    total_mass = float(np.sum(np.abs(model.member_loadings)))
    reliabilities = tuple(
        _reliability(
            item,
            float(model.member_scales[item.member_position]),
            float(model.member_reliabilities[item.member_position]),
        )
        for item in active
    )
    weights = tuple(
        abs(float(model.member_loadings[item.member_position])) * reliability
        for item, reliability in zip(active, reliabilities, strict=True)
    )
    reliability_adjusted_mass = math.fsum(weights)
    return _MassMetrics(
        active_count=len(active),
        reliable_count=sum(
            reliability >= MIN_MEMBER_RELIABILITY for reliability in reliabilities
        ),
        observed_count=sum(item.semantics is ValueSemantics.EXACT_DELTA for item in active),
        left_censored_count=sum(
            item.semantics is not ValueSemantics.EXACT_DELTA for item in active
        ),
        coverage=(
            reliability_adjusted_mass / total_mass if total_mass > 0.0 else 0.0
        ),
        effective_sample_size=_effective_sample_size(weights),
    )


def _bootstrap_coordinates(
    active: tuple[_ActiveMember, ...],
    model: FittedComplexModel,
    catalog: ComplexTransitionFittedCatalog,
    *,
    replicates: int,
    seed_digest: str,
    cancellation: CancellationContext | None,
) -> _BootstrapCoordinates:
    measurement: list[float] = []
    fitted: list[float] = []
    combined: list[float] = []
    failed = 0
    for replicate in range(replicates):
        checkpoint(cancellation)
        generator = np.random.default_rng(
            _stream_seed(seed_digest, f"measurement:{model.complex_index}:{replicate}")
        )
        perturbed = tuple(
            item.raw_delta + float(generator.normal(0.0, item.delta_standard_error))
            for item in active
        )
        draw_index = (
            _stream_seed(
                seed_digest,
                f"source-row:{model.complex_index}:{replicate}",
            )
            % catalog.bootstrap_replicate_count
        )
        draw_scales, draw_loadings = catalog.bootstrap_complex_parameters(
            draw_index,
            model.complex_index,
        )
        measurement_solve = _solve(
            active,
            model.member_scales,
            model.member_reliabilities,
            model.member_loadings,
            perturbed_deltas=perturbed,
            cancellation=cancellation,
        )
        fitted_solve = _solve(
            active,
            draw_scales,
            model.member_reliabilities,
            draw_loadings,
            cancellation=cancellation,
        )
        combined_solve = _solve(
            active,
            draw_scales,
            model.member_reliabilities,
            draw_loadings,
            perturbed_deltas=perturbed,
            cancellation=cancellation,
        )
        solves = (measurement_solve, fitted_solve, combined_solve)
        if any(
            item is None
            or not item.diagnostics.converged
            or not item.diagnostics.objective_monotone
            for item in solves
        ):
            failed += 1
            continue
        measurement.append(cast("MemberCoordinateSolve", measurement_solve).coordinate)
        fitted.append(cast("MemberCoordinateSolve", fitted_solve).coordinate)
        combined.append(cast("MemberCoordinateSolve", combined_solve).coordinate)
    return _BootstrapCoordinates(
        measurement=tuple(measurement),
        fitted_model=tuple(fitted),
        combined=tuple(combined),
        failed_replicates=failed,
    )


def _uncertainty(
    bootstrap: _BootstrapCoordinates,
) -> ComplexTransitionUncertainty:
    measurement_variance = _sample_variance(bootstrap.measurement)
    fitted_variance = _sample_variance(bootstrap.fitted_model)
    combined_variance = _sample_variance(bootstrap.combined)
    covariance = _sample_covariance(bootstrap.measurement, bootstrap.fitted_model)
    closure = abs(combined_variance - (measurement_variance + fitted_variance + 2.0 * covariance))
    return ComplexTransitionUncertainty(
        state=UncertaintyState.ESTIMATED,
        measurement_standard_error=_quantize(math.sqrt(max(0.0, measurement_variance))),
        fitted_model_standard_error=_quantize(math.sqrt(max(0.0, fitted_variance))),
        measurement_model_covariance=_quantize(covariance),
        combined_standard_error=_quantize(math.sqrt(max(0.0, combined_variance))),
        variance_closure_residual=_quantize(closure),
        bootstrap_replicates_used=bootstrap.successful_replicates,
    )


def _coherence(
    score: float,
    active: tuple[_ActiveMember, ...],
    model: FittedComplexModel,
) -> tuple[float, float]:
    numerator = 0.0
    denominator = 0.0
    for item in active:
        position = item.member_position
        scale = float(model.member_scales[position])
        value = item.raw_delta / scale
        prediction = float(model.member_loadings[position]) * score
        residual = prediction - value
        if item.semantics is ValueSemantics.UPPER_BOUND and residual <= 0.0:
            residual = 0.0
        if item.semantics is ValueSemantics.LOWER_BOUND and residual >= 0.0:
            residual = 0.0
        weight = _reliability(
            item,
            scale,
            float(model.member_reliabilities[position]),
        )
        numerator += weight * abs(residual)
        denominator += weight * (abs(value) + abs(prediction))
    discordance = min(1.0, numerator / max(denominator, 1.0e-12))
    return _probability(1.0 - discordance), _probability(discordance)


def _contributions(
    active: tuple[_ActiveMember, ...],
    model: FittedComplexModel,
) -> tuple[ComplexMemberContribution, ...]:
    ranked: list[ComplexMemberContribution] = []
    for item in active:
        if item.semantics is not ValueSemantics.EXACT_DELTA:
            continue
        position = item.member_position
        scale = float(model.member_scales[position])
        standardized = item.raw_delta / scale
        loading = float(model.member_loadings[position])
        reliability = _reliability(
            item,
            scale,
            float(model.member_reliabilities[position]),
        )
        contribution = reliability * loading * standardized
        serialized_reliability = _probability(reliability)
        serialized_contribution = _quantize(contribution)
        if serialized_reliability == 0.0 or serialized_contribution == 0.0:
            continue
        ranked.append(
            ComplexMemberContribution(
                gene_symbol=item.gene_symbol,
                from_observation_id=item.from_observation.observation_id,
                to_observation_id=item.to_observation.observation_id,
                from_provenance_digest=item.from_observation.provenance_digest,
                to_provenance_digest=item.to_observation.provenance_digest,
                value_semantics=ValueSemantics.EXACT_DELTA,
                standardized_delta=_quantize(standardized),
                member_loading=_quantize(loading),
                reliability_weight=serialized_reliability,
                contribution=serialized_contribution,
                direction=(
                    ContributionDirection.SOURCE_RECURRENCE_ALIGNED
                    if contribution > 0.0
                    else ContributionDirection.SOURCE_PRIMARY_ALIGNED
                ),
            )
        )
    ranked.sort(key=lambda item: (-abs(item.contribution), item.gene_symbol))
    return tuple(ranked[:8])


def _ablation(
    kind: Literal[
        "source_processing",
        "uniform_member_loading",
        "top_member",
        "nested_family",
    ],
    identifier: str,
    point_score: float,
    solve: MemberCoordinateSolve | None,
    removed: int,
) -> ComplexComponentAblation:
    if solve is None or not solve.diagnostics.converged:
        return ComplexComponentAblation(
            component_kind=kind,
            component_id=identifier,
            support=AnalysisSupport.ABSTAINED,
            classification_without_component=ComplexTransitionClassification.NOT_ESTIMABLE,
            removed_member_count=removed,
            reason="ablation leaves fewer than three informative members",
        )
    score = _quantize(solve.coordinate)
    return ComplexComponentAblation(
        component_kind=kind,
        component_id=identifier,
        support=AnalysisSupport.SUPPORTED,
        score_without_component=score,
        score_delta=_quantize(point_score - score),
        classification_without_component=classify_interval(score, score),
        removed_member_count=removed,
    )


def _ablations(
    active: tuple[_ActiveMember, ...],
    point_score: float,
    contributions: tuple[ComplexMemberContribution, ...],
    model: FittedComplexModel,
    *,
    source: ReactomeComplexBinding,
    catalog: ComplexTransitionFittedCatalog,
    cancellation: CancellationContext | None,
) -> ComplexTransitionAblations:
    source_processing = _solve(
        active,
        model.source_processing_scales,
        model.source_processing_reliabilities,
        model.source_processing_loadings,
        cancellation=cancellation,
    )
    uniform_loading = np.sign(model.member_loadings) * float(np.mean(np.abs(model.member_loadings)))
    uniform = _solve(
        active,
        model.member_scales,
        model.member_reliabilities,
        uniform_loading,
        cancellation=cancellation,
    )
    by_symbol = {item.gene_symbol: item.member_position for item in active}
    top_position = by_symbol.get(contributions[0].gene_symbol) if contributions else None
    top = (
        _solve(
            active,
            model.member_scales,
            model.member_reliabilities,
            model.member_loadings,
            excluded_positions=frozenset({top_position}),
            cancellation=cancellation,
        )
        if top_position is not None
        else None
    )
    family_peers = catalog.source_catalog.complexes_by_domain[source.domain_id]
    peer_members = {
        feature
        for item in family_peers
        if item.reactome_id != source.reactome_id
        for feature in item.eligible_feature_indices
    }
    nested_positions = frozenset(
        index
        for index, feature in enumerate(model.member_feature_indices)
        if feature in peer_members
    )
    nested = (
        _solve(
            active,
            model.member_scales,
            model.member_reliabilities,
            model.member_loadings,
            excluded_positions=nested_positions,
            cancellation=cancellation,
        )
        if nested_positions
        else None
    )
    return ComplexTransitionAblations(
        source_processing=_ablation(
            "source_processing",
            "ordinary-log-source-processing",
            point_score,
            source_processing,
            0,
        ),
        uniform_member_loading=_ablation(
            "uniform_member_loading",
            "signed-uniform-member-loading",
            point_score,
            uniform,
            0,
        ),
        top_member=(
            _ablation(
                "top_member",
                contributions[0].gene_symbol,
                point_score,
                top,
                1,
            )
            if top_position is not None
            else None
        ),
        nested_family=(
            _ablation(
                "nested_family",
                source.ablation_family_id,
                point_score,
                nested,
                len(nested_positions),
            )
            if nested_positions
            else None
        ),
    )


def _abstained_complex(
    model: FittedComplexModel,
    source: ReactomeComplexBinding,
    metrics: _MassMetrics,
    catalog: ComplexTransitionFittedCatalog,
    reasons: tuple[str, ...],
) -> ComplexMemberTransitionConcordance:
    return ComplexMemberTransitionConcordance(
        complex_index=model.complex_index,
        domain_id=model.domain_id,
        reactome_id=model.reactome_id,
        complex_name=model.name,
        family_id=source.ablation_family_id,
        support=AnalysisSupport.ABSTAINED,
        classification=ComplexTransitionClassification.NOT_ESTIMABLE,
        active_member_count=metrics.active_count,
        observed_member_count=metrics.observed_count,
        left_censored_member_count=metrics.left_censored_count,
        coefficient_mass_coverage=_probability(metrics.coverage),
        effective_sample_size=_quantize(metrics.effective_sample_size),
        source_held_member_relative_gain=_quantize(
            model.evaluation.relative_mae_gain_vs_training_center
        ),
        source_panel_patient_cluster_gain_90_interval=(
            _quantize(_source_gain_interval(catalog)[0]),
            _quantize(_source_gain_interval(catalog)[1]),
        ),
        source_direction_accuracy=_probability(model.evaluation.direction_accuracy),
        source_minimum_outer_loading_cosine=_quantize(model.evaluation.minimum_loading_cosine),
        uncertainty=ComplexTransitionUncertainty(
            state=UncertaintyState.NOT_ESTIMABLE,
            reason=reasons[0],
        ),
        ablations=ComplexTransitionAblations(),
        limitations=reasons,
    )


def _support(
    classification: ComplexTransitionClassification,
    stability: float,
    model: FittedComplexModel,
    source: ReactomeComplexBinding,
    catalog: ComplexTransitionFittedCatalog,
) -> tuple[AnalysisSupport, tuple[str, ...]]:
    reasons: list[str] = []
    gain_lower, _ = _source_gain_interval(catalog)
    if classification is ComplexTransitionClassification.INDETERMINATE:
        reasons.append("the request interval does not support a directional or stable state")
    if stability < 0.8:
        reasons.append("fewer than 80% of successful perturbations preserve the interval class")
    if model.evaluation.minimum_loading_cosine < 0.8:
        reasons.append("at least one outer-fold loading is unstable for this participant set")
    if model.evaluation.relative_mae_gain_vs_training_center <= 0.0:
        reasons.append("this participant set does not improve on its training-center baseline")
    if gain_lower <= 0.0:
        reasons.append("the source-panel patient-cluster gain interval crosses zero")
    if source.selected_parent_complex_ids or source.selected_child_complex_ids:
        reasons.append("the participant set is nested with another selected Reactome entity")
    if source.same_family_max_eligible_jaccard >= 0.8:
        reasons.append("the participant set has high same-family member overlap")
    return (AnalysisSupport.LIMITED, tuple(reasons)) if reasons else (AnalysisSupport.SUPPORTED, ())


def _infer_complex(
    request: LongitudinalGbmComplexTransitionRequest,
    transition_index: int,
    *,
    model: FittedComplexModel,
    source: ReactomeComplexBinding,
    catalog: ComplexTransitionFittedCatalog,
    seed_digest: str,
    cancellation: CancellationContext | None,
) -> ComplexMemberTransitionConcordance:
    active = _active_members(request, transition_index, model, catalog)
    metrics = _mass_metrics(active, model)
    reasons: list[str] = []
    if metrics.active_count > 0 and metrics.observed_count == 0:
        reasons.append(
            "one-sided-only member evidence cannot support a point-identified coordinate interval"
        )
    if metrics.active_count < MIN_ACTIVE_MEMBERS:
        reasons.append("fewer than three active member transitions are available")
    if metrics.reliable_count < MIN_ACTIVE_MEMBERS:
        reasons.append(
            "fewer than three active members meet the absolute effective-reliability gate"
        )
    if metrics.coverage < MIN_COEFFICIENT_MASS:
        reasons.append(
            "quality-adjusted active evidence covers less than half of fitted loading mass"
        )
    if metrics.effective_sample_size < MIN_EFFECTIVE_SAMPLE_SIZE:
        reasons.append("effective member support is below two")
    if reasons:
        return _abstained_complex(model, source, metrics, catalog, tuple(reasons))
    point = _solve(
        active,
        model.member_scales,
        model.member_reliabilities,
        model.member_loadings,
        cancellation=cancellation,
    )
    if point is None or not point.diagnostics.converged or not point.diagnostics.objective_monotone:
        return _abstained_complex(
            model,
            source,
            metrics,
            catalog,
            ("robust member-coordinate solve did not converge monotonically",),
        )
    bootstrap = _bootstrap_coordinates(
        active,
        model,
        catalog,
        replicates=request.bootstrap_replicates,
        seed_digest=f"{seed_digest}:{transition_index}",
        cancellation=cancellation,
    )
    if bootstrap.successful_replicates < _MINIMUM_SUCCESSFUL_BOOTSTRAPS:
        return _abstained_complex(
            model,
            source,
            metrics,
            catalog,
            ("fewer than 32 deterministic perturbation replicates converged",),
        )
    score = _quantize(point.coordinate)
    lower = _quantize(min(score, _quantile(bootstrap.combined, 0.05)))
    upper = _quantize(max(score, _quantile(bootstrap.combined, 0.95)))
    classification = classify_interval(lower, upper)
    perturbation_classes = tuple(classify_interval(value, value) for value in bootstrap.combined)
    class_counts = Counter(perturbation_classes)
    stability = _probability(
        (
            class_counts[classification]
            if classification in class_counts
            else max(class_counts.values())
        )
        / bootstrap.successful_replicates
    )
    coherence, discordance = _coherence(score, active, model)
    contributions = _contributions(active, model)
    observed_alignment = [
        (
            item.gene_symbol,
            (item.raw_delta / float(model.member_scales[item.member_position]))
            * float(model.member_loadings[item.member_position]),
        )
        for item in active
        if item.semantics is ValueSemantics.EXACT_DELTA
    ]
    least_aligned = (
        min(observed_alignment, key=lambda item: (item[1], item[0]))[0]
        if observed_alignment
        else None
    )
    support, limitations = _support(
        classification,
        stability,
        model,
        source,
        catalog,
    )
    return ComplexMemberTransitionConcordance(
        complex_index=model.complex_index,
        domain_id=model.domain_id,
        reactome_id=model.reactome_id,
        complex_name=model.name,
        family_id=source.ablation_family_id,
        support=support,
        classification=classification,
        score=score,
        lower_bound=lower,
        upper_bound=upper,
        active_member_count=metrics.active_count,
        observed_member_count=metrics.observed_count,
        left_censored_member_count=metrics.left_censored_count,
        coefficient_mass_coverage=_probability(metrics.coverage),
        effective_sample_size=_quantize(metrics.effective_sample_size),
        coherence=coherence,
        discordance=discordance,
        stability=stability,
        solver_converged=point.diagnostics.converged,
        solver_iterations=point.diagnostics.iterations,
        solver_initial_objective=_quantize(point.diagnostics.initial_objective),
        solver_final_objective=_quantize(point.diagnostics.final_objective),
        solver_objective_monotone=point.diagnostics.objective_monotone,
        bootstrap_failed_replicates=bootstrap.failed_replicates,
        least_source_aligned_observed_member=least_aligned,
        source_held_member_relative_gain=_quantize(
            model.evaluation.relative_mae_gain_vs_training_center
        ),
        source_panel_patient_cluster_gain_90_interval=(
            _quantize(_source_gain_interval(catalog)[0]),
            _quantize(_source_gain_interval(catalog)[1]),
        ),
        source_direction_accuracy=_probability(model.evaluation.direction_accuracy),
        source_minimum_outer_loading_cosine=_quantize(model.evaluation.minimum_loading_cosine),
        uncertainty=_uncertainty(bootstrap),
        top_contributions=contributions,
        ablations=_ablations(
            active,
            score,
            contributions,
            model,
            source=source,
            catalog=catalog,
            cancellation=cancellation,
        ),
        limitations=limitations,
    )


def infer_longitudinal_gbm_complex_transition(
    request: LongitudinalGbmComplexTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmComplexTransitionResult:
    """Infer source-cohort participant-transition concordance without persistence."""

    checkpoint(cancellation)
    catalog = complex_transition_fitted_catalog()
    validated = _validate_request(request, catalog)
    profile = algorithm_profile()
    request_digest = canonical_request_digest(validated)
    seed_digest = computational_request_digest(
        validated,
        profile_digest=profile.profile_digest,
    )
    transitions: list[ComplexTransitionEvidence] = []
    for transition_index, (left, right) in enumerate(
        zip(validated.time_points[:-1], validated.time_points[1:], strict=True)
    ):
        checkpoint(cancellation)
        complexes = tuple(
            _infer_complex(
                validated,
                transition_index,
                model=model,
                source=source,
                catalog=catalog,
                seed_digest=seed_digest,
                cancellation=cancellation,
            )
            for model, source in zip(
                catalog.complexes,
                catalog.source_catalog.complexes,
                strict=True,
            )
        )
        transitions.append(
            ComplexTransitionEvidence(
                transition_id=f"{validated.series_id}.complex.transition.{transition_index}",
                transition_index=transition_index,
                from_time_point_id=left.time_point_id,
                to_time_point_id=right.time_point_id,
                duration_days=_quantize(right.time_offset_days - left.time_offset_days),
                complexes=complexes,
            )
        )
    source = catalog.source_catalog
    provenance = ComplexTransitionProvenance(
        source_study_id="PDC000514",
        source_patient_pair_count=104,
        reactome_release=97,
        source_catalog_digest=source.content_digest,
        fitted_model_digest=catalog.content_digest,
        training_recipe_digest=catalog.training_recipe_digest,
        panel_selection_digest=source.selection_digest,
        participant_membership_digest=source.complex_membership_digest,
        source_licenses=(
            f"PDC000514 article/data: {source.provenance['pdc_license']}",
            f"Reactome annotation: {source.provenance['reactome_annotation_license']}",
            f"HGNC identifiers: {source.provenance['hgnc_license']}",
        ),
        source_attribution=(
            f"{source.provenance['pdc_article']}; "
            f"{source.provenance['reactome_resource']} release 97."
        ),
        validation_scope="internal_patient_grouped_held_member_reconstruction",
    )
    unverified = UnverifiedLongitudinalGbmComplexTransitionResult(
        request_digest=request_digest,
        result_digest="sha256:" + "0" * 64,
        profile_digest=profile.profile_digest,
        source_catalog_digest=source.content_digest,
        fitted_model_digest=catalog.content_digest,
        computational_seed=_receipt_seed(seed_digest),
        series_id=validated.series_id,
        assay_compatibility=validated.assay_compatibility,
        normalization_reference=validated.normalization_reference,
        time_point_ids=tuple(point.time_point_id for point in validated.time_points),
        transitions=tuple(transitions),
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    document = unverified.model_dump(mode="python")
    document["result_digest"] = result_payload_digest(unverified)
    result = LongitudinalGbmComplexTransitionResult.model_validate(document, strict=True)
    checkpoint(cancellation)
    return result


__all__ = ["infer_longitudinal_gbm_complex_transition"]
