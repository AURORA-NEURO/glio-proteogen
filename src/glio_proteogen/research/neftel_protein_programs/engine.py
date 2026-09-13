"""Deterministic bulk-protein evidence engine for Neftel Table S2 programs."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Final, cast

import numpy as np

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
from .catalog import CatalogMarker, marker_catalog, normalize_symbol
from .contracts import (
    AnalysisSupport,
    ExactProgramId,
    MarkerDriver,
    MarkerFamilyAblation,
    MethodAgreement,
    MethodEstimate,
    ProgramClassification,
    ProgramEvidence,
    ProgramEvidenceCounts,
    ProgramFamilyId,
    ProgramKind,
    ProteinEvidenceState,
    ProteinProgramProvenance,
    ProteinProgramRequest,
    ProteinProgramResult,
    RankEnrichmentEstimate,
)
from .profile import CONSTANTS, algorithm_profile

_FAMILY_SOURCES: Final = (
    (ProgramFamilyId.ASTROCYTE_LIKE, ("AC",)),
    (ProgramFamilyId.OLIGODENDROCYTE_PROGENITOR_LIKE, ("OPC",)),
    (ProgramFamilyId.NEURAL_PROGENITOR_LIKE, ("NPC1", "NPC2")),
    (ProgramFamilyId.MESENCHYMAL_LIKE, ("MES1", "MES2")),
    (ProgramFamilyId.CELL_CYCLE, ("G1/S", "G2/M")),
)


@dataclass(frozen=True, slots=True)
class _Observation:
    observation_id: str
    normalized_symbol: str
    state: ProteinEvidenceState
    effect: float | None
    standard_error: float | None
    quality_weight: float
    provenance_digest: str


@dataclass(frozen=True, slots=True)
class _MarkerSpec:
    normalized_symbol: str
    raw_symbols: tuple[str, ...]
    source_ranks: tuple[int, ...]
    source_programs: tuple[str, ...]
    prior_weight: float


@dataclass(frozen=True, slots=True)
class _Target:
    program_id: ExactProgramId | ProgramFamilyId
    kind: ProgramKind
    source_programs: tuple[str, ...]
    source_marker_count: int
    catalog_non_protein_loci: int
    markers: tuple[_MarkerSpec, ...]


@dataclass(frozen=True, slots=True)
class _RawEstimate:
    support: AnalysisSupport
    score: float | None
    effective_sample_size: float
    reason: str | None


def _quantize(value: float) -> float:
    result = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if result == 0.0 else result


def _quantize_positive(value: float) -> float:
    """Quantize a positive value without violating positive-output contracts."""

    result = _quantize(value)
    if result > 0.0:
        return result
    return 10.0 ** -CONSTANTS.quantization_decimals


def _seed(digest: str) -> int:
    byte_count = CONSTANTS.random_seed_bytes
    value = int.from_bytes(bytes.fromhex(digest.removeprefix("sha256:")[: byte_count * 2]))
    return value % 2**53


def _observation_map(request: ProteinProgramRequest) -> dict[str, _Observation]:
    return {
        normalize_symbol(item.gene_symbol): _Observation(
            observation_id=item.observation_id,
            normalized_symbol=normalize_symbol(item.gene_symbol),
            state=item.state,
            effect=item.standardized_effect,
            standard_error=item.standard_error,
            quality_weight=item.quality_weight,
            provenance_digest=item.provenance_digest,
        )
        for item in sorted(request.observations, key=lambda value: normalize_symbol(value.gene_symbol))
    }


def _build_target(
    program_id: ExactProgramId | ProgramFamilyId,
    kind: ProgramKind,
    source_programs: tuple[str, ...],
) -> _Target:
    catalog = marker_catalog()
    contributions: dict[str, list[tuple[CatalogMarker, str, float]]] = {}
    source_marker_count = 0
    non_protein = 0
    for source_program in source_programs:
        source_markers = catalog.programs[source_program]
        source_marker_count += len(source_markers)
        non_protein += sum(not marker.protein_eligible for marker in source_markers)
        eligible = tuple(marker for marker in source_markers if marker.protein_eligible)
        for marker in eligible:
            equal_program_mass_weight = 1.0 / len(eligible) / len(source_programs)
            contributions.setdefault(marker.normalized_symbol, []).append(
                (marker, source_program, equal_program_mass_weight)
            )
    specs = tuple(
        _MarkerSpec(
            normalized_symbol=symbol,
            raw_symbols=tuple(item[0].raw_symbol for item in entries),
            source_ranks=tuple(item[0].rank for item in entries),
            source_programs=tuple(item[1] for item in entries),
            prior_weight=sum(item[2] for item in entries),
        )
        for symbol, entries in sorted(contributions.items())
    )
    return _Target(
        program_id=program_id,
        kind=kind,
        source_programs=source_programs,
        source_marker_count=source_marker_count,
        catalog_non_protein_loci=non_protein,
        markers=specs,
    )


def _targets() -> tuple[_Target, ...]:
    exact = tuple(
        _build_target(
            ExactProgramId(program_id),
            ProgramKind.SOURCE_META_MODULE,
            (program_id,),
        )
        for program_id in marker_catalog().programs
    )
    families = tuple(
        _build_target(program_id, ProgramKind.DERIVED_PROGRAM_FAMILY, source_programs)
        for program_id, source_programs in _FAMILY_SOURCES
    )
    return exact + families


def _active_observations(
    target: _Target,
    observations: dict[str, _Observation],
    omitted: frozenset[str] = frozenset(),
) -> tuple[tuple[_MarkerSpec, _Observation, float], ...]:
    active: list[tuple[_MarkerSpec, _Observation, float]] = []
    for marker in target.markers:
        if marker.normalized_symbol in omitted:
            continue
        observation = observations.get(marker.normalized_symbol)
        if observation is None or observation.state not in {
            ProteinEvidenceState.OBSERVED,
            ProteinEvidenceState.LEFT_CENSORED,
        }:
            continue
        standard_error = cast("float", observation.standard_error)
        scale_squared = standard_error**2 + CONSTANTS.standard_error_floor**2
        reliability = marker.prior_weight * observation.quality_weight / scale_squared
        active.append((marker, observation, reliability))
    return tuple(active)


def _effective_sample_size(weights: tuple[float, ...]) -> float:
    if not weights:
        return 0.0
    maximum = max(weights)
    if maximum <= 0.0:
        return 0.0
    scaled = tuple(weight / maximum for weight in weights)
    total = math.fsum(scaled)
    squared_total = math.fsum(weight * weight for weight in scaled)
    return total * total / squared_total


def _location_gradient(
    location: float,
    active: tuple[tuple[_MarkerSpec, _Observation, float], ...],
) -> float:
    gradient = CONSTANTS.location_ridge * location
    for _, observation, reliability in active:
        effect = cast("float", observation.effect)
        standard_error = cast("float", observation.standard_error)
        scale = max(standard_error, CONSTANTS.standard_error_floor)
        if observation.state is ProteinEvidenceState.LEFT_CENSORED and location <= effect:
            continue
        residual = location - effect
        bound = CONSTANTS.huber_delta * scale
        gradient += reliability * min(max(residual, -bound), bound)
    return gradient


def _robust_location(
    target: _Target,
    observations: dict[str, _Observation],
    omitted: frozenset[str] = frozenset(),
) -> _RawEstimate:
    active = _active_observations(target, observations, omitted)
    observed_count = sum(
        observation.state is ProteinEvidenceState.OBSERVED for _, observation, _ in active
    )
    lower = -20.0
    upper = 20.0
    for _ in range(96):
        midpoint = (lower + upper) / 2.0
        if _location_gradient(midpoint, active) > 0.0:
            upper = midpoint
        else:
            lower = midpoint
    location = (lower + upper) / 2.0
    support_evidence = tuple(
        item
        for item in active
        if item[1].state is ProteinEvidenceState.OBSERVED
        or location > cast("float", item[1].effect)
    )
    nonbinding_censored_count = len(active) - len(support_evidence)
    coverage = len(support_evidence) / max(1, len(target.markers) - len(omitted))
    ess = _effective_sample_size(tuple(item[2] for item in support_evidence))
    exploratory_reasons: list[str] = []
    if len(support_evidence) < CONSTANTS.exploratory_minimum_active_markers:
        exploratory_reasons.append("fewer than five location-supporting protein markers")
    if observed_count < CONSTANTS.exploratory_minimum_observed_markers:
        exploratory_reasons.append("fewer than three exact observed protein markers")
    if coverage < CONSTANTS.exploratory_minimum_active_coverage:
        exploratory_reasons.append("location-supporting marker coverage below 0.10")
    if ess < CONSTANTS.exploratory_minimum_effective_sample_size:
        exploratory_reasons.append("effective location-supporting sample size below 3.0")
    if exploratory_reasons:
        if nonbinding_censored_count:
            exploratory_reasons.append(
                "nonbinding left-censored limits excluded from support gate"
            )
        return _RawEstimate(
            support=AnalysisSupport.ABSTAINED,
            score=None,
            effective_sample_size=ess,
            reason="; ".join(exploratory_reasons),
        )
    supported = (
        len(support_evidence) >= CONSTANTS.supported_minimum_active_markers
        and observed_count >= CONSTANTS.supported_minimum_observed_markers
        and coverage >= CONSTANTS.supported_minimum_active_coverage
        and ess >= CONSTANTS.supported_minimum_effective_sample_size
    )
    limitation_reasons: list[str] = []
    if not supported:
        limitation_reasons.append(
            "exploratory estimate below the 10-marker, 5-observed, "
            "0.30-coverage, or 8.0-effective-sample supported gate"
        )
        if nonbinding_censored_count:
            limitation_reasons.append(
                "nonbinding left-censored limits excluded from support gate"
            )
    return _RawEstimate(
        support=AnalysisSupport.SUPPORTED if supported else AnalysisSupport.LIMITED,
        score=location,
        effective_sample_size=ess,
        reason=None if supported else "; ".join(limitation_reasons),
    )


def _average_percentile_ranks(observations: dict[str, _Observation]) -> dict[str, float]:
    observed = sorted(
        (
            (cast("float", item.effect), symbol)
            for symbol, item in observations.items()
            if item.state is ProteinEvidenceState.OBSERVED
        ),
        key=lambda item: (item[0], item[1]),
    )
    if len(observed) <= 1:
        return {symbol: 0.5 for _, symbol in observed}
    percentiles: dict[str, float] = {}
    index = 0
    while index < len(observed):
        end = index + 1
        while end < len(observed) and observed[end][0] == observed[index][0]:
            end += 1
        average_rank = (index + end - 1) / 2.0
        percentile = average_rank / (len(observed) - 1)
        for _, symbol in observed[index:end]:
            percentiles[symbol] = percentile
        index = end
    return percentiles


def _weighted_rank_enrichment(
    target: _Target,
    observations: dict[str, _Observation],
    percentiles: dict[str, float],
    omitted: frozenset[str] = frozenset(),
) -> _RawEstimate:
    marker_values: list[tuple[float, float]] = []
    for marker in target.markers:
        if marker.normalized_symbol in omitted:
            continue
        observation = observations.get(marker.normalized_symbol)
        if observation is None or observation.state is not ProteinEvidenceState.OBSERVED:
            continue
        standard_error = cast("float", observation.standard_error)
        reliability = (
            marker.prior_weight
            * observation.quality_weight
            / (standard_error**2 + CONSTANTS.standard_error_floor**2)
        )
        marker_values.append((percentiles[marker.normalized_symbol], reliability))
    ess = _effective_sample_size(tuple(weight for _, weight in marker_values))
    coverage = len(marker_values) / max(1, len(target.markers) - len(omitted))
    exploratory_reasons: list[str] = []
    if len(percentiles) < CONSTANTS.minimum_rank_background:
        exploratory_reasons.append("fewer than twenty exact observed background proteins")
    if len(marker_values) < CONSTANTS.exploratory_minimum_active_markers:
        exploratory_reasons.append("fewer than five exact observed program markers")
    if coverage < CONSTANTS.exploratory_minimum_active_coverage:
        exploratory_reasons.append("observed rank-marker coverage below 0.10")
    if ess < CONSTANTS.exploratory_minimum_effective_sample_size:
        exploratory_reasons.append("effective rank-marker sample size below 3.0")
    if exploratory_reasons:
        return _RawEstimate(
            support=AnalysisSupport.ABSTAINED,
            score=None,
            effective_sample_size=ess,
            reason="; ".join(exploratory_reasons),
        )
    total_weight = sum(weight for _, weight in marker_values)
    weighted_percentile = sum(value * weight for value, weight in marker_values) / total_weight
    supported = (
        len(marker_values) >= CONSTANTS.supported_minimum_active_markers
        and coverage >= CONSTANTS.supported_minimum_active_coverage
        and ess >= CONSTANTS.supported_minimum_effective_sample_size
    )
    return _RawEstimate(
        support=AnalysisSupport.SUPPORTED if supported else AnalysisSupport.LIMITED,
        score=2.0 * (weighted_percentile - 0.5),
        effective_sample_size=ess,
        reason=(
            None
            if supported
            else "exploratory rank estimate below the 10-marker, 0.30-coverage, or 8.0-effective-sample supported gate"
        ),
    )


def _perturb_observations(
    observations: dict[str, _Observation],
    normal_draws: np.ndarray,
) -> dict[str, _Observation]:
    perturbed: dict[str, _Observation] = {}
    active_index = 0
    for symbol, observation in observations.items():
        if observation.state in {
            ProteinEvidenceState.OBSERVED,
            ProteinEvidenceState.LEFT_CENSORED,
        }:
            effect = cast("float", observation.effect) + cast(
                "float", observation.standard_error
            ) * float(normal_draws[active_index])
            perturbed[symbol] = replace(observation, effect=min(max(effect, -20.0), 20.0))
            active_index += 1
        else:
            perturbed[symbol] = observation
    return perturbed


def _bootstrap_scores(
    request: ProteinProgramRequest,
    observations: dict[str, _Observation],
    targets: tuple[_Target, ...],
    *,
    computational_digest: str,
    cancellation: CancellationContext | None,
) -> tuple[dict[object, list[float]], dict[object, list[float]], int]:
    seed = _seed(
        sha256_digest({"computational_digest": computational_digest, "domain": "bootstrap"})
    )
    rng = np.random.default_rng(seed)
    active_count = sum(
        item.state in {ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED}
        for item in observations.values()
    )
    draws = rng.standard_normal((request.bootstrap_replicates, active_count))
    location_samples: dict[object, list[float]] = {target.program_id: [] for target in targets}
    rank_samples: dict[object, list[float]] = {target.program_id: [] for target in targets}
    for replicate in range(request.bootstrap_replicates):
        checkpoint(cancellation)
        perturbed = _perturb_observations(observations, draws[replicate])
        percentiles = _average_percentile_ranks(perturbed)
        for target in targets:
            location = _robust_location(target, perturbed)
            rank = _weighted_rank_enrichment(target, perturbed, percentiles)
            if location.score is not None:
                location_samples[target.program_id].append(location.score)
            if rank.score is not None:
                rank_samples[target.program_id].append(rank.score)
    checkpoint(cancellation)
    return location_samples, rank_samples, seed


def _method_estimate(raw: _RawEstimate, samples: list[float]) -> MethodEstimate:
    if raw.score is None:
        return MethodEstimate(
            support=AnalysisSupport.ABSTAINED,
            effective_sample_size=_quantize(raw.effective_sample_size),
            bootstrap_replicates_used=0,
            reason=cast("str", raw.reason),
        )
    if not samples:
        raise RuntimeError("supported estimate has no deterministic bootstrap samples")
    lower = float(np.quantile(samples, CONSTANTS.interval_lower_quantile, method="linear"))
    upper = float(np.quantile(samples, CONSTANTS.interval_upper_quantile, method="linear"))
    return MethodEstimate(
        support=raw.support,
        score=_quantize(raw.score),
        lower_bound=_quantize(min(lower, raw.score)),
        upper_bound=_quantize(max(upper, raw.score)),
        effective_sample_size=_quantize(raw.effective_sample_size),
        bootstrap_replicates_used=len(samples),
        reason=raw.reason,
    )


def _benjamini_hochberg(p_values: dict[object, float]) -> dict[object, float]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], str(item[0])))
    adjusted: dict[object, float] = {}
    running = 1.0
    count = len(ordered)
    for reverse_index in range(count - 1, -1, -1):
        identifier, p_value = ordered[reverse_index]
        rank = reverse_index + 1
        running = min(running, p_value * count / rank)
        adjusted[identifier] = min(1.0, running)
    return adjusted


def _empirical_two_sided_p_value(observed_score: float, null_scores: list[float]) -> float:
    """Return the finite-null, plus-one-corrected two-sided empirical p-value."""

    if not null_scores:
        raise ValueError("an empirical p-value requires at least one null score")
    extreme = sum(abs(value) >= abs(observed_score) for value in null_scores)
    return (extreme + 1.0) / (len(null_scores) + 1.0)


def _rank_hypothesis_key(target: _Target) -> tuple[tuple[str, float], ...]:
    """Identify a unique numerical rank hypothesis independent of its display label."""

    return tuple(
        (marker.normalized_symbol, marker.prior_weight) for marker in target.markers
    )


def _rank_null_statistics(
    request: ProteinProgramRequest,
    observations: dict[str, _Observation],
    targets: tuple[_Target, ...],
    raw_ranks: dict[object, _RawEstimate],
    *,
    computational_digest: str,
    cancellation: CancellationContext | None,
) -> tuple[dict[object, float], dict[object, float], dict[object, float], int]:
    percentiles = _average_percentile_ranks(observations)
    symbols = tuple(sorted(percentiles))
    values = np.array([percentiles[symbol] for symbol in symbols], dtype=np.float64)
    seed = _seed(
        sha256_digest(
            {"computational_digest": computational_digest, "domain": "rank_permutation"}
        )
    )
    rng = np.random.default_rng(seed)
    hypotheses: dict[tuple[tuple[str, float], ...], list[_Target]] = {}
    for target in targets:
        if raw_ranks[target.program_id].score is not None:
            hypotheses.setdefault(_rank_hypothesis_key(target), []).append(target)
    nulls: dict[tuple[tuple[str, float], ...], list[float]] = {
        hypothesis: [] for hypothesis in hypotheses
    }
    for _ in range(request.permutation_replicates):
        checkpoint(cancellation)
        permutation = rng.permutation(values)
        permuted = dict(zip(symbols, permutation.tolist(), strict=True))
        for hypothesis, grouped_targets in hypotheses.items():
            representative = grouped_targets[0]
            estimate = _weighted_rank_enrichment(representative, observations, permuted)
            nulls[hypothesis].append(cast("float", estimate.score))
    hypothesis_p_values: dict[object, float] = {}
    hypothesis_standard_deviations: dict[object, float] = {}
    for hypothesis, values_for_target in nulls.items():
        representative = hypotheses[hypothesis][0]
        observed_score = cast("float", raw_ranks[representative.program_id].score)
        hypothesis_p_values[hypothesis] = _empirical_two_sided_p_value(
            observed_score,
            values_for_target,
        )
        hypothesis_standard_deviations[hypothesis] = float(
            np.std(values_for_target, ddof=1)
        )
    hypothesis_q_values = _benjamini_hochberg(hypothesis_p_values)
    p_values: dict[object, float] = {}
    q_values: dict[object, float] = {}
    null_standard_deviations: dict[object, float] = {}
    for hypothesis, grouped_targets in hypotheses.items():
        for target in grouped_targets:
            p_values[target.program_id] = hypothesis_p_values[hypothesis]
            q_values[target.program_id] = hypothesis_q_values[hypothesis]
            null_standard_deviations[target.program_id] = hypothesis_standard_deviations[
                hypothesis
            ]
    checkpoint(cancellation)
    return p_values, q_values, null_standard_deviations, seed


def _rank_method_estimate(
    raw: _RawEstimate,
    samples: list[float],
    *,
    p_value: float | None,
    q_value: float | None,
    null_standard_deviation: float | None,
    permutation_replicates: int,
) -> RankEnrichmentEstimate:
    base = _method_estimate(raw, samples)
    return RankEnrichmentEstimate(
        **base.model_dump(mode="python"),
        permutation_replicates_used=(0 if raw.score is None else permutation_replicates),
        null_standard_deviation=(
            None if null_standard_deviation is None else _quantize(null_standard_deviation)
        ),
        p_value=None if p_value is None else _quantize(p_value),
        q_value=None if q_value is None else _quantize(q_value),
    )


def _counts(
    target: _Target,
    observations: dict[str, _Observation],
    background_count: int,
) -> ProgramEvidenceCounts:
    state_counts = dict.fromkeys(ProteinEvidenceState, 0)
    unreported = 0
    for marker in target.markers:
        observation = observations.get(marker.normalized_symbol)
        if observation is None:
            unreported += 1
        else:
            state_counts[observation.state] += 1
    active = (
        state_counts[ProteinEvidenceState.OBSERVED]
        + state_counts[ProteinEvidenceState.LEFT_CENSORED]
    )
    return ProgramEvidenceCounts(
        source_marker_count=target.source_marker_count,
        eligible_protein_markers=len(target.markers),
        catalog_non_protein_loci=target.catalog_non_protein_loci,
        observed_markers=state_counts[ProteinEvidenceState.OBSERVED],
        left_censored_markers=state_counts[ProteinEvidenceState.LEFT_CENSORED],
        explicitly_missing_markers=state_counts[ProteinEvidenceState.MISSING],
        unsupported_markers=state_counts[ProteinEvidenceState.UNSUPPORTED],
        unreported_markers=unreported,
        active_coverage=_quantize(active / len(target.markers)),
        observed_background_proteins=background_count,
    )


def _location_classification(estimate: MethodEstimate) -> ProgramClassification:
    if estimate.support is AnalysisSupport.ABSTAINED:
        return ProgramClassification.NOT_ESTIMABLE
    lower = cast("float", estimate.lower_bound)
    upper = cast("float", estimate.upper_bound)
    threshold = CONSTANTS.activation_threshold
    if lower > threshold:
        return ProgramClassification.ACTIVATED
    if upper < -threshold:
        return ProgramClassification.SUPPRESSED
    if lower >= -threshold and upper <= threshold:
        return ProgramClassification.NEUTRAL
    return ProgramClassification.INDETERMINATE


def _rank_direction(estimate: MethodEstimate) -> str:
    if estimate.support is AnalysisSupport.ABSTAINED:
        return "not_estimable"
    lower = cast("float", estimate.lower_bound)
    upper = cast("float", estimate.upper_bound)
    if lower > 0.0:
        return "positive"
    if upper < 0.0:
        return "negative"
    if (
        lower >= -CONSTANTS.rank_neutral_threshold
        and upper <= CONSTANTS.rank_neutral_threshold
    ):
        return "neutral"
    return "uncertain"


def _hybrid_interpretation(
    location: MethodEstimate,
    rank: RankEnrichmentEstimate,
) -> tuple[AnalysisSupport, ProgramClassification, MethodAgreement]:
    location_class = _location_classification(location)
    rank_direction = _rank_direction(rank)
    if location.support is AnalysisSupport.ABSTAINED and rank.support is AnalysisSupport.ABSTAINED:
        return (
            AnalysisSupport.ABSTAINED,
            ProgramClassification.NOT_ESTIMABLE,
            MethodAgreement.INSUFFICIENT,
        )
    if location.support is AnalysisSupport.ABSTAINED:
        return (
            AnalysisSupport.LIMITED,
            ProgramClassification.INDETERMINATE,
            MethodAgreement.SINGLE_METHOD,
        )
    if rank.support is AnalysisSupport.ABSTAINED:
        return AnalysisSupport.LIMITED, location_class, MethodAgreement.SINGLE_METHOD
    expected_direction = {
        ProgramClassification.ACTIVATED: "positive",
        ProgramClassification.SUPPRESSED: "negative",
        ProgramClassification.NEUTRAL: "neutral",
    }.get(location_class)
    if expected_direction is not None and rank_direction == expected_direction:
        direction_is_supported = (
            expected_direction == "neutral"
            or cast("float", rank.q_value) <= CONSTANTS.rank_q_threshold
        )
        method_support = (
            AnalysisSupport.SUPPORTED
            if location.support is AnalysisSupport.SUPPORTED
            and rank.support is AnalysisSupport.SUPPORTED
            and direction_is_supported
            else AnalysisSupport.LIMITED
        )
        return method_support, location_class, MethodAgreement.CONCORDANT
    opposite = (expected_direction, rank_direction) in {
        ("positive", "negative"),
        ("negative", "positive"),
        ("neutral", "positive"),
        ("neutral", "negative"),
    }
    if opposite:
        return (
            AnalysisSupport.LIMITED,
            ProgramClassification.INDETERMINATE,
            MethodAgreement.DISCORDANT,
        )
    return (
        AnalysisSupport.LIMITED,
        ProgramClassification.INDETERMINATE,
        MethodAgreement.UNCERTAIN,
    )


def _top_drivers(
    target: _Target,
    observations: dict[str, _Observation],
    percentiles: dict[str, float],
    base_location: _RawEstimate,
    base_rank: _RawEstimate,
) -> tuple[MarkerDriver, ...]:
    drivers: list[tuple[float, MarkerDriver]] = []
    for marker, observation, reliability in _active_observations(target, observations):
        omitted = frozenset({marker.normalized_symbol})
        without_location = _robust_location(target, observations, omitted)
        without_rank = _weighted_rank_enrichment(target, observations, percentiles, omitted)
        location_influence = (
            None
            if base_location.score is None or without_location.score is None
            else _quantize(base_location.score - without_location.score)
        )
        rank_influence = (
            None
            if base_rank.score is None or without_rank.score is None
            else _quantize(base_rank.score - without_rank.score)
        )
        magnitude = max(abs(location_influence or 0.0), abs(rank_influence or 0.0))
        drivers.append(
            (
                magnitude,
                MarkerDriver(
                    normalized_symbol=marker.normalized_symbol,
                    source_symbols=marker.raw_symbols,
                    source_ranks=marker.source_ranks,
                    evidence_state=observation.state,
                    value_role=(
                        "observed_point"
                        if observation.state is ProteinEvidenceState.OBSERVED
                        else "left_censored_upper_limit"
                    ),
                    standardized_effect=_quantize(cast("float", observation.effect)),
                    reliability_weight=_quantize_positive(reliability),
                    location_influence=location_influence,
                    rank_influence=rank_influence,
                ),
            )
        )
    drivers.sort(key=lambda item: (-item[0], item[1].normalized_symbol))
    return tuple(item[1] for item in drivers[:5])


def _rank_band_ablations(
    target: _Target,
    observations: dict[str, _Observation],
    percentiles: dict[str, float],
    base_location: _RawEstimate,
    base_rank: _RawEstimate,
) -> tuple[MarkerFamilyAblation, ...]:
    marker_count = target.source_marker_count
    boundaries = (math.ceil(marker_count / 3), math.ceil(2 * marker_count / 3))
    groups = (
        ("source_rank_band.top", 0, boundaries[0]),
        ("source_rank_band.middle", boundaries[0], boundaries[1]),
        ("source_rank_band.tail", boundaries[1], marker_count),
    )
    effects: list[MarkerFamilyAblation] = []
    for family, lower_rank, upper_rank in groups:
        omitted = frozenset(
            marker.normalized_symbol
            for marker in target.markers
            if any(lower_rank < rank <= upper_rank for rank in marker.source_ranks)
        )
        location = _robust_location(target, observations, omitted)
        rank = _weighted_rank_enrichment(target, observations, percentiles, omitted)
        effects.append(
            MarkerFamilyAblation(
                omitted_family=family,
                markers_removed=len(omitted),
                location_delta=(
                    None
                    if base_location.score is None or location.score is None
                    else _quantize(location.score - base_location.score)
                ),
                rank_delta=(
                    None
                    if base_rank.score is None or rank.score is None
                    else _quantize(rank.score - base_rank.score)
                ),
            )
        )
    return tuple(effects)


def _source_program_ablations(
    target: _Target,
    observations: dict[str, _Observation],
    percentiles: dict[str, float],
    base_location: _RawEstimate,
    base_rank: _RawEstimate,
) -> tuple[MarkerFamilyAblation, ...]:
    if len(target.source_programs) < 2:
        return ()
    effects: list[MarkerFamilyAblation] = []
    for omitted_source in target.source_programs:
        retained = tuple(item for item in target.source_programs if item != omitted_source)
        alternative = _build_target(target.program_id, target.kind, retained)
        location = _robust_location(alternative, observations)
        rank = _weighted_rank_enrichment(alternative, observations, percentiles)
        original_symbols = {marker.normalized_symbol for marker in target.markers}
        retained_symbols = {marker.normalized_symbol for marker in alternative.markers}
        effects.append(
            MarkerFamilyAblation(
                omitted_family=f"source_meta_module.{omitted_source.replace('/', '')}",
                markers_removed=max(1, len(original_symbols - retained_symbols)),
                location_delta=(
                    None
                    if base_location.score is None or location.score is None
                    else _quantize(location.score - base_location.score)
                ),
                rank_delta=(
                    None
                    if base_rank.score is None or rank.score is None
                    else _quantize(rank.score - base_rank.score)
                ),
            )
        )
    return tuple(effects)


def infer_neftel_protein_programs(
    request: ProteinProgramRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ProteinProgramResult:
    """Infer robust program evidence from standardized bulk-protein effects."""

    checkpoint(cancellation)
    profile = algorithm_profile()
    catalog = marker_catalog()
    request_digest = canonical_request_digest(request)
    computational_digest = computational_request_digest(
        request,
        profile_digest=profile.profile_digest,
        symbol_aliases=catalog.aliases,
    )
    observations = _observation_map(request)
    targets = _targets()
    percentiles = _average_percentile_ranks(observations)
    raw_locations = {
        target.program_id: _robust_location(target, observations) for target in targets
    }
    raw_ranks: dict[object, _RawEstimate] = {
        target.program_id: _weighted_rank_enrichment(target, observations, percentiles)
        for target in targets
    }
    location_samples, rank_samples, bootstrap_seed = _bootstrap_scores(
        request,
        observations,
        targets,
        computational_digest=computational_digest,
        cancellation=cancellation,
    )
    p_values, q_values, null_standard_deviations, permutation_seed = _rank_null_statistics(
        request,
        observations,
        targets,
        raw_ranks,
        computational_digest=computational_digest,
        cancellation=cancellation,
    )
    outputs: list[ProgramEvidence] = []
    for target in targets:
        checkpoint(cancellation)
        raw_location = raw_locations[target.program_id]
        raw_rank = raw_ranks[target.program_id]
        location = _method_estimate(raw_location, location_samples[target.program_id])
        rank = _rank_method_estimate(
            raw_rank,
            rank_samples[target.program_id],
            p_value=p_values.get(target.program_id),
            q_value=q_values.get(target.program_id),
            null_standard_deviation=null_standard_deviations.get(target.program_id),
            permutation_replicates=request.permutation_replicates,
        )
        support, classification, agreement = _hybrid_interpretation(location, rank)
        reasons = tuple(
            reason
            for reason in (raw_location.reason, raw_rank.reason)
            if reason is not None
        )
        ablations = (
            _rank_band_ablations(
                target,
                observations,
                percentiles,
                raw_location,
                raw_rank,
            )
            if target.kind is ProgramKind.SOURCE_META_MODULE
            else _source_program_ablations(
                target,
                observations,
                percentiles,
                raw_location,
                raw_rank,
            )
        )
        outputs.append(
            ProgramEvidence(
                program_id=target.program_id,
                program_kind=target.kind,
                source_programs=tuple(ExactProgramId(item) for item in target.source_programs),
                support=support,
                classification=classification,
                location=location,
                rank_enrichment=rank,
                method_agreement=agreement,
                evidence_counts=_counts(target, observations, len(percentiles)),
                top_drivers=_top_drivers(
                    target,
                    observations,
                    percentiles,
                    raw_location,
                    raw_rank,
                ),
                marker_family_ablations=ablations,
                abstention_reasons=reasons,
            )
        )
    provenance = ProteinProgramProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        catalog_content_digest=catalog.content_digest,
        catalog_artifact_digest=catalog.artifact_digest,
        exact_source_program_digest=catalog.source_program_digest,
        table_s2_source_digest=catalog.source_sha256,
        hgnc_source_digest=catalog.hgnc_sha256,
        numpy_version=np.__version__,
        computational_digest=computational_digest,
        bootstrap_seed=bootstrap_seed,
        rank_permutation_seed=permutation_seed,
        observation_source_digests=tuple(
            sorted({item.provenance_digest for item in request.observations})
        ),
    )
    limitations = (
        "Outputs are bulk protein program evidence, not cell fractions, diagnoses, or clinical molecular subtypes.",
        "Neftel Table S2 was derived from single-cell RNA programs; protein-level transfer is an experimental research interpretation.",
        "Bulk abundance can reflect tumor, immune, vascular, and other microenvironmental sources that this model cannot separate.",
        "Missing model proteins are ignored and trigger coverage abstention; they are never treated as negative observations.",
        "Left-censored values remain one-sided upper-limit evidence and are excluded from exact rank placement.",
        "HGNC aliases are limited to the content-pinned normalization table; ambiguous or unlisted identifiers are not inferred.",
        "Active rank-background identifiers are restricted to the content-pinned HGNC-to-UniProt protein universe; unsupported identifiers never become background negatives.",
        "Bootstrap intervals use independent Gaussian perturbations at caller-supplied fixed standard errors and a conservative score envelope; they do not model covariance, biological variance, or establish calibrated external validity.",
        "Rank enrichment is a repository-defined weighted mean-percentile statistic with a deterministic permutation null; it is not labeled as ssGSEA or independently validated enrichment software.",
        "Activated and suppressed mean higher or lower than the caller-declared standardized log2 reference contrast, never absolute biological activation.",
        "This deterministic research result is non-prescriptive and must not guide treatment or clinical classification.",
    )
    payload = {
        "algorithm_id": "neftel-bulk-protein-programs",
        "algorithm_version": "1.0.0",
        "profile_id": "neftel-bulk-protein-programs/1.0.0",
        "profile_digest": profile.profile_digest,
        "request_digest": request_digest,
        "sample_id": request.sample_id,
        "program_evidence": [item.model_dump(mode="json") for item in outputs],
        "provenance": provenance.model_dump(mode="json"),
        "output_semantics": "bulk_protein_program_evidence",
        "limitations": list(limitations),
        "research_use_only": True,
        "non_prescriptive": True,
    }
    result = ProteinProgramResult(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest=result_payload_digest(payload),
        sample_id=request.sample_id,
        program_evidence=tuple(outputs),
        provenance=provenance,
        limitations=limitations,
    )
    checkpoint(cancellation)
    return result


__all__ = ["infer_neftel_protein_programs"]
