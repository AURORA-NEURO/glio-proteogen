"""Deterministic independent concordance inference over frozen SPHINKS signatures."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
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
from .catalog import MasterKinase, SignatureEdge, master_kinase_catalog
from .contracts import (
    AnalysisSupport,
    EdgeAblation,
    GbmSubtype,
    KinaseEvidence,
    KinaseEvidenceCounts,
    MasterKinaseProvenance,
    MasterKinaseRequest,
    MasterKinaseResult,
    MethodAgreement,
    MethodEstimate,
    PhosphositeDriver,
    PhosphositeEvidenceState,
    RankEnrichmentEstimate,
    SourceMasterKinaseReference,
    StateClassification,
    SubtypeAblation,
    SubtypeEvidence,
    SubtypeKinaseDriver,
)
from .profile import CONSTANTS, algorithm_profile

_SUBTYPE_ORDER: Final = (GbmSubtype.GPM, GbmSubtype.MTC, GbmSubtype.NEU, GbmSubtype.PPR)
_RESIDUE_PATTERN: Final = re.compile(r"([STY])\d+[sty]?")


@dataclass(frozen=True, slots=True)
class _Observation:
    observation_id: str
    phosphosite_id: str
    state: PhosphositeEvidenceState
    effect: float | None
    standard_error: float | None
    quality_weight: float
    provenance_digest: str
    residue_stratum: str


@dataclass(frozen=True, slots=True)
class _SiteSpec:
    phosphosite_id: str
    source_edges: tuple[SignatureEdge, ...]
    source_svm_weight: float
    residue_stratum: str


@dataclass(frozen=True, slots=True)
class _RawLocation:
    support: AnalysisSupport
    score: float | None
    effective_sample_size: float
    reason: str | None
    active: tuple[tuple[_SiteSpec, _Observation, float], ...]
    supporting: tuple[tuple[_SiteSpec, _Observation, float], ...]


@dataclass(frozen=True, slots=True)
class _RawRank:
    support: AnalysisSupport
    score: float | None
    effective_sample_size: float
    reason: str | None
    mapped: tuple[tuple[_SiteSpec, _Observation, float], ...]
    observed_background_sites: int


def _quantize(value: float) -> float:
    result = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if result == 0.0 else result


def _quantize_positive(value: float) -> float:
    result = _quantize(value)
    return result if result > 0.0 else 10.0**-CONSTANTS.quantization_decimals


def _seed(digest: str) -> int:
    byte_count = CONSTANTS.random_seed_bytes
    value = int.from_bytes(bytes.fromhex(digest.removeprefix("sha256:")[: byte_count * 2]))
    return value % 2**53


def _component_seed(computational_digest: str, component: str) -> int:
    return _seed(sha256_digest({"component": component, "request": computational_digest}))


def _residue_stratum(site: str) -> str:
    residues = sorted(set(_RESIDUE_PATTERN.findall(site.rsplit("-", 1)[-1])))
    return "".join(residues) or "OTHER"


def _observation_map(request: MasterKinaseRequest) -> dict[str, _Observation]:
    return {
        item.phosphosite_id: _Observation(
            observation_id=item.observation_id,
            phosphosite_id=item.phosphosite_id,
            state=item.state,
            effect=item.standardized_effect,
            standard_error=item.standard_error,
            quality_weight=item.quality_weight,
            provenance_digest=item.provenance_digest,
            residue_stratum=_residue_stratum(item.phosphosite_id),
        )
        for item in sorted(request.observations, key=lambda value: value.phosphosite_id)
    }


def _site_specs(master: MasterKinase) -> tuple[_SiteSpec, ...]:
    grouped: dict[str, list[SignatureEdge]] = defaultdict(list)
    for edge in master_kinase_catalog().edges_by_kinase[master.hgnc_symbol]:
        grouped[edge.source_site_label].append(edge)
    return tuple(
        _SiteSpec(
            phosphosite_id=site,
            source_edges=tuple(sorted(edges, key=lambda item: item.source_row_id)),
            source_svm_weight=math.fsum(edge.svm_probability for edge in edges) / len(edges),
            residue_stratum=_residue_stratum(site),
        )
        for site, edges in sorted(grouped.items())
    )


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


def _active_sites(
    specs: tuple[_SiteSpec, ...],
    observations: dict[str, _Observation],
    *,
    omitted_strata: frozenset[str] = frozenset(),
) -> tuple[tuple[_SiteSpec, _Observation, float], ...]:
    active: list[tuple[_SiteSpec, _Observation, float]] = []
    for spec in specs:
        if spec.residue_stratum in omitted_strata:
            continue
        observation = observations.get(spec.phosphosite_id)
        if observation is None or observation.state not in {
            PhosphositeEvidenceState.OBSERVED,
            PhosphositeEvidenceState.LEFT_CENSORED,
        }:
            continue
        standard_error = cast("float", observation.standard_error)
        reliability = (
            spec.source_svm_weight
            * observation.quality_weight
            / (standard_error**2 + CONSTANTS.standard_error_floor**2)
        )
        active.append((spec, observation, reliability))
    return tuple(active)


def _robust_location(
    specs: tuple[_SiteSpec, ...],
    observations: dict[str, _Observation],
    *,
    omitted_strata: frozenset[str] = frozenset(),
) -> _RawLocation:
    active = _active_sites(specs, observations, omitted_strata=omitted_strata)
    location = 0.0
    if active:
        effects = np.fromiter(
            (cast("float", item[1].effect) for item in active),
            dtype=np.float64,
            count=len(active),
        )
        bounds = np.fromiter(
            (
                CONSTANTS.huber_delta
                * max(
                    cast("float", item[1].standard_error),
                    CONSTANTS.standard_error_floor,
                )
                for item in active
            ),
            dtype=np.float64,
            count=len(active),
        )
        reliabilities = np.fromiter(
            (item[2] for item in active),
            dtype=np.float64,
            count=len(active),
        )
        directly_observed = np.fromiter(
            (item[1].state is PhosphositeEvidenceState.OBSERVED for item in active),
            dtype=np.bool_,
            count=len(active),
        )
        lower = -CONSTANTS.location_search_bound
        upper = CONSTANTS.location_search_bound
        for _ in range(CONSTANTS.location_solver_iterations):
            midpoint = (lower + upper) / 2.0
            binding = np.logical_or(directly_observed, midpoint > effects)
            gradient = CONSTANTS.location_ridge * midpoint + float(
                np.dot(
                    reliabilities[binding],
                    np.clip(midpoint - effects[binding], -bounds[binding], bounds[binding]),
                )
            )
            if gradient > 0.0:
                upper = midpoint
            else:
                lower = midpoint
        location = (lower + upper) / 2.0
    supporting = tuple(
        item
        for item in active
        if item[1].state is PhosphositeEvidenceState.OBSERVED
        or location > cast("float", item[1].effect)
    )
    observed_count = sum(item[1].state is PhosphositeEvidenceState.OBSERVED for item in supporting)
    ess = _effective_sample_size(tuple(item[2] for item in supporting))
    eligible_count = sum(spec.residue_stratum not in omitted_strata for spec in specs)
    coverage = len(supporting) / max(1, eligible_count)
    if len(supporting) < CONSTANTS.minimum_location_sites or observed_count == 0:
        return _RawLocation(
            support=AnalysisSupport.ABSTAINED,
            score=None,
            effective_sample_size=ess,
            reason="fewer than three independent location-supporting sites or no observed site",
            active=active,
            supporting=supporting,
        )
    limitations: list[str] = []
    if len(supporting) < CONSTANTS.supported_minimum_sites:
        limitations.append("fewer than five independent location-supporting sites")
    if observed_count < CONSTANTS.supported_minimum_observed_sites:
        limitations.append("fewer than three directly observed signature sites")
    if coverage < CONSTANTS.supported_minimum_coverage:
        limitations.append("signature-site coverage below two percent")
    if ess < CONSTANTS.supported_minimum_effective_sample_size:
        limitations.append("effective sample size below four")
    nonbinding = len(active) - len(supporting)
    if nonbinding:
        limitations.append(f"{nonbinding} nonbinding left-censored limits excluded from support")
    return _RawLocation(
        support=AnalysisSupport.LIMITED if limitations else AnalysisSupport.SUPPORTED,
        score=location,
        effective_sample_size=ess,
        reason="; ".join(limitations) if limitations else None,
        active=active,
        supporting=supporting,
    )


def _percentile_scores(observations: dict[str, _Observation]) -> dict[str, float]:
    groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for site, observation in observations.items():
        if observation.state is PhosphositeEvidenceState.OBSERVED:
            groups[observation.residue_stratum].append((site, cast("float", observation.effect)))
    scores: dict[str, float] = {}
    for values in groups.values():
        ordered = sorted(values, key=lambda item: (item[1], item[0]))
        size = len(ordered)
        cursor = 0
        while cursor < size:
            end = cursor + 1
            while end < size and ordered[end][1] == ordered[cursor][1]:
                end += 1
            average_rank = (cursor + (end - 1)) / 2.0
            percentile = 0.0 if size == 1 else 2.0 * average_rank / (size - 1) - 1.0
            for site, _effect in ordered[cursor:end]:
                scores[site] = percentile
            cursor = end
    return scores


def _rank_enrichment(
    specs: tuple[_SiteSpec, ...],
    observations: dict[str, _Observation],
    percentiles: dict[str, float],
    *,
    omitted_strata: frozenset[str] = frozenset(),
    background_by_stratum: Counter[str] | None = None,
) -> _RawRank:
    mapped: list[tuple[_SiteSpec, _Observation, float]] = []
    for spec in specs:
        if spec.residue_stratum in omitted_strata or spec.phosphosite_id not in percentiles:
            continue
        observation = observations[spec.phosphosite_id]
        standard_error = cast("float", observation.standard_error)
        reliability = (
            spec.source_svm_weight
            * observation.quality_weight
            / (standard_error**2 + CONSTANTS.standard_error_floor**2)
        )
        mapped.append((spec, observation, reliability))
    ess = _effective_sample_size(tuple(item[2] for item in mapped))
    mapped_by_stratum = Counter(item[0].residue_stratum for item in mapped)
    if background_by_stratum is None:
        background_by_stratum = Counter(observations[site].residue_stratum for site in percentiles)
    inadequate_strata = tuple(
        sorted(
            stratum
            for stratum, count in mapped_by_stratum.items()
            if background_by_stratum[stratum] - count
            < CONSTANTS.minimum_residue_stratum_competitors
        )
    )
    if (
        len(mapped) < CONSTANTS.minimum_rank_signature_sites
        or len(percentiles) < CONSTANTS.minimum_rank_background
        or inadequate_strata
    ):
        residue_reason = (
            f"; inadequate independent residue competitors for {', '.join(inadequate_strata)}"
            if inadequate_strata
            else ""
        )
        return _RawRank(
            support=AnalysisSupport.ABSTAINED,
            score=None,
            effective_sample_size=ess,
            reason=(
                "rank enrichment requires three mapped observed sites, 20 observed background "
                f"sites, and three non-signature competitors per represented residue stratum{residue_reason}"
            ),
            mapped=tuple(mapped),
            observed_background_sites=len(percentiles),
        )
    total = math.fsum(item[2] for item in mapped)
    score = math.fsum(item[2] * percentiles[item[0].phosphosite_id] for item in mapped) / total
    limited = (
        len(mapped) < CONSTANTS.supported_minimum_sites
        or ess < CONSTANTS.supported_minimum_effective_sample_size
        or len(percentiles) < CONSTANTS.supported_minimum_rank_background
    )
    return _RawRank(
        support=AnalysisSupport.LIMITED if limited else AnalysisSupport.SUPPORTED,
        score=score,
        effective_sample_size=ess,
        reason=(
            "rank enrichment has fewer than five sites, effective sample size below four, "
            "or fewer than 64 observed background sites"
        )
        if limited
        else None,
        mapped=tuple(mapped),
        observed_background_sites=len(percentiles),
    )


def _perturb_observations(
    observations: dict[str, _Observation],
    rng: np.random.Generator,
) -> dict[str, _Observation]:
    perturbed: dict[str, _Observation] = {}
    for site, observation in observations.items():
        if observation.state in {
            PhosphositeEvidenceState.OBSERVED,
            PhosphositeEvidenceState.LEFT_CENSORED,
        }:
            effect = cast("float", observation.effect) + float(
                rng.normal(0.0, cast("float", observation.standard_error))
            )
            perturbed[site] = replace(observation, effect=min(max(effect, -20.0), 20.0))
        else:
            perturbed[site] = observation
    return perturbed


def _bootstrap_scores(
    request: MasterKinaseRequest,
    observations: dict[str, _Observation],
    masters: tuple[MasterKinase, ...],
    specs_by_kinase: dict[str, tuple[_SiteSpec, ...]],
    *,
    computational_digest: str,
    cancellation: CancellationContext | None,
) -> tuple[dict[str, list[float | None]], dict[str, list[float | None]], int]:
    seed = _component_seed(computational_digest, "measurement-bootstrap")
    rng = np.random.default_rng(seed)
    locations: dict[str, list[float | None]] = {master.hgnc_symbol: [] for master in masters}
    ranks: dict[str, list[float | None]] = {master.hgnc_symbol: [] for master in masters}
    for _ in range(request.bootstrap_replicates):
        checkpoint(cancellation)
        perturbed = _perturb_observations(observations, rng)
        percentiles = _percentile_scores(perturbed)
        background_by_stratum = Counter(perturbed[site].residue_stratum for site in percentiles)
        for master in masters:
            specs = specs_by_kinase[master.hgnc_symbol]
            location = _robust_location(specs, perturbed)
            rank = _rank_enrichment(
                specs,
                perturbed,
                percentiles,
                background_by_stratum=background_by_stratum,
            )
            locations[master.hgnc_symbol].append(location.score)
            ranks[master.hgnc_symbol].append(rank.score)
    return locations, ranks, seed


def _benjamini_hochberg(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    total = len(ordered)
    adjusted: dict[str, float] = {}
    running = 1.0
    for rank, (identifier, p_value) in reversed(tuple(enumerate(ordered, start=1))):
        running = min(running, p_value * total / rank)
        adjusted[identifier] = min(1.0, running)
    return adjusted


def _permutation_nulls(
    request: MasterKinaseRequest,
    observations: dict[str, _Observation],
    raw_ranks: dict[str, _RawRank],
    *,
    computational_digest: str,
    cancellation: CancellationContext | None,
) -> tuple[dict[str, list[float]], int]:
    """Generate a conditional random-set null over complete observation tuples.

    Source-edge SVM weights remain fixed because they define the tested signature.
    Residue-matched background draws move percentile, quality, and standard error
    together, preventing heteroscedastic measurement metadata from leaking across
    randomized site identities.
    """

    seed = _component_seed(computational_digest, "residue-stratified-rank-permutation")
    rng = np.random.default_rng(seed)
    percentiles = _percentile_scores(observations)
    background_groups: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for site, percentile in sorted(percentiles.items()):
        observation = observations[site]
        standard_error = cast("float", observation.standard_error)
        background_groups[observation.residue_stratum].append(
            (percentile, standard_error, observation.quality_weight)
        )
    background_by_stratum = {
        stratum: (
            np.asarray([item[0] for item in values], dtype=np.float64),
            np.asarray([item[1] for item in values], dtype=np.float64),
            np.asarray([item[2] for item in values], dtype=np.float64),
        )
        for stratum, values in sorted(background_groups.items())
    }
    nulls: dict[str, list[float]] = {
        identifier: [] for identifier, raw in raw_ranks.items() if raw.score is not None
    }
    sampling_specs: dict[
        str,
        tuple[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray], ...],
    ] = {}
    for identifier, raw in raw_ranks.items():
        if raw.score is None:
            continue
        by_stratum: dict[str, list[float]] = defaultdict(list)
        for spec, _observation, _reliability in raw.mapped:
            by_stratum[spec.residue_stratum].append(spec.source_svm_weight)
        sampling_specs[identifier] = tuple(
            (
                background_by_stratum[stratum][0],
                background_by_stratum[stratum][1],
                background_by_stratum[stratum][2],
                np.asarray(sorted(source_weights), dtype=np.float64),
            )
            for stratum, source_weights in sorted(by_stratum.items())
        )
    for _ in range(request.permutation_replicates):
        checkpoint(cancellation)
        for identifier, sampling_spec in sampling_specs.items():
            weighted_total = 0.0
            weight_total = 0.0
            for population, standard_errors, quality_weights, source_weights in sampling_spec:
                indices = rng.choice(len(population), size=len(source_weights), replace=False)
                selected_percentiles = population[indices]
                selected_standard_errors = standard_errors[indices]
                selected_quality_weights = quality_weights[indices]
                randomized_reliability = (
                    source_weights
                    * selected_quality_weights
                    / (selected_standard_errors**2 + CONSTANTS.standard_error_floor**2)
                )
                weighted_total += float(np.dot(randomized_reliability, selected_percentiles))
                weight_total += float(np.sum(randomized_reliability))
            nulls[identifier].append(weighted_total / weight_total)
    return nulls, seed


def _successful_samples(samples: list[float | None]) -> tuple[float, ...]:
    return tuple(item for item in samples if item is not None)


def _bootstrap_support(
    support: AnalysisSupport,
    reason: str | None,
    samples: list[float | None],
    requested: int,
) -> tuple[AnalysisSupport, str | None, tuple[float, ...]]:
    if requested <= 0:
        raise ValueError("requested bootstrap count must be positive")
    if len(samples) != requested:
        raise ValueError("bootstrap track length does not match requested replicate count")
    successful = _successful_samples(samples)
    fraction = len(successful) / requested
    bootstrap_reason: str | None = None
    if fraction < CONSTANTS.minimum_bootstrap_success_fraction:
        support = AnalysisSupport.ABSTAINED
        bootstrap_reason = (
            f"bootstrap success fraction {len(successful)}/{requested} is below "
            f"{CONSTANTS.minimum_bootstrap_success_fraction:.2f}"
        )
    elif len(successful) < requested:
        support = AnalysisSupport.LIMITED
        bootstrap_reason = f"bootstrap success fraction {len(successful)}/{requested} is incomplete"
    reasons = tuple(dict.fromkeys(item for item in (reason, bootstrap_reason) if item is not None))
    return support, "; ".join(reasons) if reasons else None, successful


def _interval(score: float, samples: tuple[float, ...]) -> tuple[float, float]:
    if not samples:
        return score, score
    lower = min(score, float(np.quantile(samples, CONSTANTS.interval_lower_quantile)))
    upper = max(score, float(np.quantile(samples, CONSTANTS.interval_upper_quantile)))
    return lower, upper


def _method_estimate(
    raw: _RawLocation,
    samples: list[float | None],
    requested: int,
) -> MethodEstimate:
    if len(samples) != requested:
        raise ValueError("location bootstrap track length does not match the request")
    successful = _successful_samples(samples)
    if raw.score is None:
        return MethodEstimate(
            support=AnalysisSupport.ABSTAINED,
            effective_sample_size=_quantize(raw.effective_sample_size),
            bootstrap_replicates_requested=requested,
            bootstrap_replicates_successful=len(successful),
            bootstrap_replicates_used=0,
            reason=cast("str", raw.reason),
        )
    support, reason, successful = _bootstrap_support(
        raw.support,
        raw.reason,
        samples,
        requested,
    )
    if support is AnalysisSupport.ABSTAINED:
        return MethodEstimate(
            support=support,
            effective_sample_size=_quantize(raw.effective_sample_size),
            bootstrap_replicates_requested=requested,
            bootstrap_replicates_successful=len(successful),
            bootstrap_replicates_used=0,
            reason=cast("str", reason),
        )
    lower, upper = _interval(raw.score, successful)
    return MethodEstimate(
        support=support,
        score=_quantize(raw.score),
        lower_bound=_quantize(lower),
        upper_bound=_quantize(upper),
        effective_sample_size=_quantize(raw.effective_sample_size),
        bootstrap_replicates_requested=requested,
        bootstrap_replicates_successful=len(successful),
        bootstrap_replicates_used=len(successful),
        reason=reason,
    )


def _rank_estimate(
    raw: _RawRank,
    samples: list[float | None],
    *,
    requested: int,
    nulls: list[float],
    q_value: float | None,
) -> RankEnrichmentEstimate:
    if len(samples) != requested:
        raise ValueError("rank bootstrap track length does not match the request")
    successful = _successful_samples(samples)
    if raw.score is None:
        return RankEnrichmentEstimate(
            support=AnalysisSupport.ABSTAINED,
            effective_sample_size=_quantize(raw.effective_sample_size),
            bootstrap_replicates_requested=requested,
            bootstrap_replicates_successful=len(successful),
            bootstrap_replicates_used=0,
            mapped_signature_sites=len(raw.mapped),
            observed_background_sites=raw.observed_background_sites,
            permutation_replicates_used=0,
            reason=cast("str", raw.reason),
        )
    support, reason, successful = _bootstrap_support(
        raw.support,
        raw.reason,
        samples,
        requested,
    )
    if support is AnalysisSupport.ABSTAINED:
        return RankEnrichmentEstimate(
            support=support,
            effective_sample_size=_quantize(raw.effective_sample_size),
            bootstrap_replicates_requested=requested,
            bootstrap_replicates_successful=len(successful),
            bootstrap_replicates_used=0,
            mapped_signature_sites=len(raw.mapped),
            observed_background_sites=raw.observed_background_sites,
            permutation_replicates_used=0,
            reason=cast("str", reason),
        )
    lower, upper = _interval(raw.score, successful)
    p_value = (1.0 + sum(abs(item) >= abs(raw.score) for item in nulls)) / (len(nulls) + 1.0)
    return RankEnrichmentEstimate(
        support=support,
        score=_quantize(raw.score),
        lower_bound=_quantize(lower),
        upper_bound=_quantize(upper),
        effective_sample_size=_quantize(raw.effective_sample_size),
        bootstrap_replicates_requested=requested,
        bootstrap_replicates_successful=len(successful),
        bootstrap_replicates_used=len(successful),
        mapped_signature_sites=len(raw.mapped),
        observed_background_sites=raw.observed_background_sites,
        permutation_replicates_used=len(nulls),
        null_standard_deviation=_quantize(float(np.std(nulls, ddof=0))),
        p_value=_quantize(p_value),
        q_value=_quantize(cast("float", q_value)),
        reason=reason,
    )


def _classification(estimate: MethodEstimate) -> StateClassification:
    if estimate.support is AnalysisSupport.ABSTAINED:
        return StateClassification.NOT_ESTIMABLE
    lower = cast("float", estimate.lower_bound)
    upper = cast("float", estimate.upper_bound)
    threshold = CONSTANTS.activation_threshold
    if lower > threshold:
        return StateClassification.ACTIVATED
    if upper < -threshold:
        return StateClassification.SUPPRESSED
    if lower >= -threshold and upper <= threshold:
        return StateClassification.NEUTRAL
    return StateClassification.INDETERMINATE


def _direction(score: float | None) -> int:
    if score is None or abs(score) <= CONSTANTS.activation_threshold:
        return 0
    return 1 if score > 0.0 else -1


def _agreement(
    location: MethodEstimate,
    rank: RankEnrichmentEstimate,
) -> MethodAgreement:
    if location.support is AnalysisSupport.ABSTAINED and rank.support is AnalysisSupport.ABSTAINED:
        return MethodAgreement.INSUFFICIENT
    if location.support is AnalysisSupport.ABSTAINED or rank.support is AnalysisSupport.ABSTAINED:
        return MethodAgreement.SINGLE_METHOD
    if cast("float", rank.q_value) > CONSTANTS.rank_q_threshold:
        return MethodAgreement.UNCERTAIN
    left = _direction(location.score)
    right = _direction(rank.score)
    if left == right and left != 0:
        return MethodAgreement.CONCORDANT
    if left != right and 0 not in (left, right):
        return MethodAgreement.DISCORDANT
    return MethodAgreement.UNCERTAIN


def _combined_support(location: MethodEstimate, rank: RankEnrichmentEstimate) -> AnalysisSupport:
    if location.support is AnalysisSupport.ABSTAINED and rank.support is AnalysisSupport.ABSTAINED:
        return AnalysisSupport.ABSTAINED
    if location.support is AnalysisSupport.SUPPORTED and rank.support is AnalysisSupport.SUPPORTED:
        return AnalysisSupport.SUPPORTED
    return AnalysisSupport.LIMITED


def _discordance(raw: _RawLocation) -> float | None:
    if raw.score is None or not raw.supporting:
        return None
    direction = _direction(raw.score)
    threshold = CONSTANTS.activation_threshold
    total = math.fsum(item[2] for item in raw.supporting)
    if direction > 0:
        discordant = math.fsum(
            item[2] for item in raw.supporting if cast("float", item[1].effect) < -threshold
        )
    elif direction < 0:
        discordant = math.fsum(
            item[2] for item in raw.supporting if cast("float", item[1].effect) > threshold
        )
    else:
        discordant = math.fsum(
            item[2] for item in raw.supporting if abs(cast("float", item[1].effect)) > threshold
        )
    return discordant / total


def _stability(score: float | None, samples: list[float | None]) -> float | None:
    successful = _successful_samples(samples)
    if score is None or not successful:
        return None
    target_direction = _direction(score)
    return sum(_direction(item) == target_direction for item in successful) / len(successful)


def _counts(
    master: MasterKinase,
    specs: tuple[_SiteSpec, ...],
    observations: dict[str, _Observation],
    raw: _RawLocation,
    observed_background: int,
) -> KinaseEvidenceCounts:
    states = Counter(
        observations[spec.phosphosite_id].state
        for spec in specs
        if spec.phosphosite_id in observations
    )
    binding = sum(
        item[1].state is PhosphositeEvidenceState.LEFT_CENSORED for item in raw.supporting
    )
    source_rows = len(master_kinase_catalog().edges_by_kinase[master.hgnc_symbol])
    return KinaseEvidenceCounts(
        source_signature_edge_rows=source_rows,
        signature_unique_sites=len(specs),
        repeated_source_edge_rows=source_rows - len(specs),
        observed_signature_sites=states[PhosphositeEvidenceState.OBSERVED],
        left_censored_signature_sites=states[PhosphositeEvidenceState.LEFT_CENSORED],
        binding_left_censored_sites=binding,
        explicitly_missing_signature_sites=states[PhosphositeEvidenceState.MISSING],
        unsupported_signature_sites=states[PhosphositeEvidenceState.UNSUPPORTED],
        unreported_signature_sites=len(specs) - sum(states.values()),
        active_coverage=len(raw.supporting) / len(specs),
        observed_background_sites=observed_background,
    )


def _top_drivers(
    raw_location: _RawLocation,
    raw_rank: _RawRank,
    percentiles: dict[str, float],
) -> tuple[PhosphositeDriver, ...]:
    if raw_location.score is None:
        return ()
    rank_total = math.fsum(item[2] for item in raw_rank.mapped)
    rank_weights = (
        {item[0].phosphosite_id: item[2] / rank_total for item in raw_rank.mapped}
        if rank_total > 0.0
        else {}
    )
    drivers: list[tuple[float, PhosphositeDriver]] = []
    for spec, observation, reliability in raw_location.supporting:
        effect = cast("float", observation.effect)
        residual = effect - raw_location.score
        standard_error = cast("float", observation.standard_error)
        bound = CONSTANTS.huber_delta * max(standard_error, CONSTANTS.standard_error_floor)
        influence = reliability * min(max(residual, -bound), bound)
        rank_influence = None
        if spec.phosphosite_id in rank_weights:
            rank_influence = rank_weights[spec.phosphosite_id] * percentiles[spec.phosphosite_id]
        driver = PhosphositeDriver(
            observation_id=observation.observation_id,
            observation_provenance_digest=observation.provenance_digest,
            phosphosite_id=spec.phosphosite_id,
            source_edge_row_ids=tuple(edge.source_row_id for edge in spec.source_edges),
            evidence_state=observation.state,
            value_role="observed_point"
            if observation.state is PhosphositeEvidenceState.OBSERVED
            else "left_censored_upper_limit",
            standardized_effect=_quantize(effect),
            source_svm_weight=_quantize_positive(spec.source_svm_weight),
            reliability_weight=_quantize_positive(reliability),
            location_influence=_quantize(influence),
            rank_influence=None if rank_influence is None else _quantize(rank_influence),
        )
        drivers.append((abs(influence) + abs(rank_influence or 0.0), driver))
    return tuple(
        item[1] for item in sorted(drivers, key=lambda item: (-item[0], item[1].phosphosite_id))[:5]
    )


def _edge_ablations(
    specs: tuple[_SiteSpec, ...],
    observations: dict[str, _Observation],
    percentiles: dict[str, float],
    base_location: _RawLocation,
    base_rank: _RawRank,
) -> tuple[EdgeAblation, ...]:
    effects: list[EdgeAblation] = []
    for stratum in sorted({spec.residue_stratum for spec, _obs, _weight in base_location.active}):
        removed_specs = tuple(spec for spec in specs if spec.residue_stratum == stratum)
        source_rows_removed = sum(len(spec.source_edges) for spec in removed_specs)
        location = _robust_location(specs, observations, omitted_strata=frozenset({stratum}))
        rank = _rank_enrichment(
            specs,
            observations,
            percentiles,
            omitted_strata=frozenset({stratum}),
        )
        effects.append(
            EdgeAblation(
                omitted_residue_stratum=stratum,
                source_edge_rows_removed=source_rows_removed,
                unique_sites_removed=len(removed_specs),
                location_delta=None
                if base_location.score is None or location.score is None
                else _quantize(location.score - base_location.score),
                rank_delta=None
                if base_rank.score is None or rank.score is None
                else _quantize(rank.score - base_rank.score),
            )
        )
    return tuple(effects)


def _robust_scalar_location(values: tuple[float, ...], weights: tuple[float, ...]) -> float:
    lower = -CONSTANTS.location_search_bound
    upper = CONSTANTS.location_search_bound
    for _ in range(CONSTANTS.location_solver_iterations):
        midpoint = (lower + upper) / 2.0
        gradient = CONSTANTS.location_ridge * midpoint
        for value, weight in zip(values, weights, strict=True):
            residual = midpoint - value
            gradient += weight * min(max(residual, -CONSTANTS.huber_delta), CONSTANTS.huber_delta)
        if gradient > 0.0:
            upper = midpoint
        else:
            lower = midpoint
    return (lower + upper) / 2.0


def _subtype_bootstrap_samples(
    estimated: tuple[str, ...],
    weights: tuple[float, ...],
    location_samples: dict[str, list[float | None]],
    bootstrap_replicates: int,
) -> list[float | None]:
    for identifier in estimated:
        if len(location_samples[identifier]) != bootstrap_replicates:
            raise ValueError(
                f"kinase {identifier} bootstrap track does not match the subtype request"
            )
    samples: list[float | None] = []
    for replicate in range(bootstrap_replicates):
        values = tuple(location_samples[identifier][replicate] for identifier in estimated)
        if any(value is None for value in values):
            samples.append(None)
        else:
            samples.append(
                _robust_scalar_location(
                    tuple(cast("float", value) for value in values),
                    weights,
                )
            )
    return samples


def _subtype_outputs(
    masters: tuple[MasterKinase, ...],
    kinase_outputs: tuple[KinaseEvidence, ...],
    location_samples: dict[str, list[float | None]],
    bootstrap_replicates: int,
) -> tuple[SubtypeEvidence, ...]:
    by_id = {item.kinase_id: item for item in kinase_outputs}
    master_by_id = {item.hgnc_symbol: item for item in masters}
    outputs: list[SubtypeEvidence] = []
    for subtype in _SUBTYPE_ORDER:
        member_ids = tuple(
            master.hgnc_symbol for master in masters if master.subtype == subtype.value
        )
        estimated = tuple(
            identifier for identifier in member_ids if by_id[identifier].location.score is not None
        )
        if not estimated:
            outputs.append(
                SubtypeEvidence(
                    subtype_id=subtype,
                    support=AnalysisSupport.ABSTAINED,
                    classification=StateClassification.NOT_ESTIMABLE,
                    aggregate=MethodEstimate(
                        support=AnalysisSupport.ABSTAINED,
                        effective_sample_size=0.0,
                        bootstrap_replicates_requested=bootstrap_replicates,
                        bootstrap_replicates_successful=0,
                        bootstrap_replicates_used=0,
                        reason="no member kinase has estimable location evidence",
                    ),
                    member_kinases=member_ids,
                    supported_member_count=0,
                    estimated_member_count=0,
                    abstention_reasons=("no member kinase has estimable location evidence",),
                )
            )
            continue
        values = tuple(cast("float", by_id[item].location.score) for item in estimated)
        weights = tuple(
            master_by_id[item].source_reference.kinase_activity_mww_score
            * max(1.0, by_id[item].location.effective_sample_size)
            for item in estimated
        )
        score = _robust_scalar_location(values, weights)
        samples = _subtype_bootstrap_samples(
            estimated,
            weights,
            location_samples,
            bootstrap_replicates,
        )
        supported_count = sum(
            by_id[item].support is AnalysisSupport.SUPPORTED for item in member_ids
        )
        reasons: list[str] = []
        if len(estimated) < CONSTANTS.subtype_minimum_estimated_kinases:
            reasons.append("fewer than two estimable signature-concordance kinase summaries")
        if len(estimated) / len(member_ids) < CONSTANTS.subtype_minimum_estimated_fraction:
            reasons.append("fewer than half of source subtype kinases are estimable")
        if supported_count < min(
            CONSTANTS.subtype_minimum_supported_kinases,
            len(member_ids),
        ):
            reasons.append("too few fully supported member kinases")
        point_support = AnalysisSupport.LIMITED if reasons else AnalysisSupport.SUPPORTED
        support, aggregate_reason, successful_samples = _bootstrap_support(
            point_support,
            "; ".join(reasons) if reasons else None,
            samples,
            bootstrap_replicates,
        )
        if aggregate_reason is not None:
            reasons = aggregate_reason.split("; ")
        if support is AnalysisSupport.ABSTAINED:
            aggregate = MethodEstimate(
                support=support,
                effective_sample_size=_quantize(_effective_sample_size(weights)),
                bootstrap_replicates_requested=bootstrap_replicates,
                bootstrap_replicates_successful=len(successful_samples),
                bootstrap_replicates_used=0,
                reason=cast("str", aggregate_reason),
            )
        else:
            lower, upper = _interval(score, successful_samples)
            aggregate = MethodEstimate(
                support=support,
                score=_quantize(score),
                lower_bound=_quantize(lower),
                upper_bound=_quantize(upper),
                effective_sample_size=_quantize(_effective_sample_size(weights)),
                bootstrap_replicates_requested=bootstrap_replicates,
                bootstrap_replicates_successful=len(successful_samples),
                bootstrap_replicates_used=len(successful_samples),
                reason=aggregate_reason,
            )
        weight_total = math.fsum(weights)
        discordant_weight = math.fsum(
            weight
            for value, weight in zip(values, weights, strict=True)
            if _direction(value) not in {0, _direction(score)}
        )
        drivers = tuple(
            SubtypeKinaseDriver(
                kinase_id=identifier,
                score=_quantize(value),
                aggregation_weight=_quantize_positive(weight / weight_total),
                influence=_quantize(weight / weight_total * (value - score)),
            )
            for identifier, value, weight in sorted(
                zip(estimated, values, weights, strict=True),
                key=lambda item: (-abs(item[2] * (item[1] - score)), item[0]),
            )[:5]
        )
        ablations: list[SubtypeAblation] = []
        for omitted in estimated:
            retained = tuple(item for item in estimated if item != omitted)
            if not retained:
                delta = None
            else:
                retained_values = tuple(
                    cast("float", by_id[item].location.score) for item in retained
                )
                retained_weights = tuple(
                    master_by_id[item].source_reference.kinase_activity_mww_score
                    * max(1.0, by_id[item].location.effective_sample_size)
                    for item in retained
                )
                delta = _quantize(
                    _robust_scalar_location(retained_values, retained_weights) - score
                )
            ablations.append(SubtypeAblation(omitted_kinase_id=omitted, subtype_score_delta=delta))
        outputs.append(
            SubtypeEvidence(
                subtype_id=subtype,
                support=support,
                classification=_classification(aggregate),
                aggregate=aggregate,
                member_kinases=member_ids,
                supported_member_count=supported_count,
                estimated_member_count=len(estimated),
                discordance=_quantize(discordant_weight / weight_total),
                stability=(
                    None
                    if _stability(score, samples) is None
                    else _quantize(cast("float", _stability(score, samples)))
                ),
                top_kinases=drivers,
                subtype_ablations=tuple(ablations),
                abstention_reasons=tuple(reasons),
            )
        )
    return tuple(outputs)


def infer_master_kinases(
    request: MasterKinaseRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> MasterKinaseResult:
    """Infer independent signature concordance from a standardized phosphosite contrast."""

    checkpoint(cancellation)
    profile = algorithm_profile()
    catalog = master_kinase_catalog()
    request_digest = canonical_request_digest(request)
    computational_digest = computational_request_digest(
        request,
        profile_digest=profile.profile_digest,
    )
    observations = _observation_map(request)
    masters = catalog.masters
    specs_by_kinase = {master.hgnc_symbol: _site_specs(master) for master in masters}
    percentiles = _percentile_scores(observations)
    background_by_stratum = Counter(observations[site].residue_stratum for site in percentiles)
    raw_locations = {
        master.hgnc_symbol: _robust_location(specs_by_kinase[master.hgnc_symbol], observations)
        for master in masters
    }
    raw_ranks = {
        master.hgnc_symbol: _rank_enrichment(
            specs_by_kinase[master.hgnc_symbol],
            observations,
            percentiles,
            background_by_stratum=background_by_stratum,
        )
        for master in masters
    }
    location_samples, rank_samples, bootstrap_seed = _bootstrap_scores(
        request,
        observations,
        masters,
        specs_by_kinase,
        computational_digest=computational_digest,
        cancellation=cancellation,
    )
    nulls, permutation_seed = _permutation_nulls(
        request,
        observations,
        raw_ranks,
        computational_digest=computational_digest,
        cancellation=cancellation,
    )
    p_values = {
        master.hgnc_symbol: (
            (
                1.0
                + sum(
                    abs(item) >= abs(cast("float", raw_ranks[master.hgnc_symbol].score))
                    for item in nulls[master.hgnc_symbol]
                )
            )
            / (len(nulls[master.hgnc_symbol]) + 1.0)
            if master.hgnc_symbol in nulls
            else 1.0
        )
        for master in masters
    }
    q_values = _benjamini_hochberg(p_values)
    outputs: list[KinaseEvidence] = []
    for master in masters:
        checkpoint(cancellation)
        identifier = master.hgnc_symbol
        raw_location = raw_locations[identifier]
        raw_rank = raw_ranks[identifier]
        location = _method_estimate(
            raw_location,
            location_samples[identifier],
            request.bootstrap_replicates,
        )
        rank = _rank_estimate(
            raw_rank,
            rank_samples[identifier],
            requested=request.bootstrap_replicates,
            nulls=nulls.get(identifier, []),
            q_value=q_values.get(identifier),
        )
        support = _combined_support(location, rank)
        reasons = tuple(
            dict.fromkeys(reason for reason in (location.reason, rank.reason) if reason is not None)
        )
        outputs.append(
            KinaseEvidence(
                kinase_id=identifier,
                source_kinase_label=master.source_kinase_label,
                source_subtype=GbmSubtype(master.subtype),
                support=support,
                classification=_classification(location),
                source_reference=SourceMasterKinaseReference(
                    kinase_activity_mww_score=master.source_reference.kinase_activity_mww_score,
                    log2fc_activity_subtype_vs_others=(
                        master.source_reference.log2fc_activity_subtype_vs_others
                    ),
                    p_value=master.source_reference.p_value,
                ),
                location=location,
                rank_enrichment=rank,
                method_agreement=_agreement(location, rank),
                discordance=None
                if _discordance(raw_location) is None
                else _quantize(cast("float", _discordance(raw_location))),
                stability=None
                if location.support is AnalysisSupport.ABSTAINED
                or _stability(raw_location.score, location_samples[identifier]) is None
                else _quantize(
                    cast("float", _stability(raw_location.score, location_samples[identifier]))
                ),
                evidence_counts=_counts(
                    master,
                    specs_by_kinase[identifier],
                    observations,
                    raw_location,
                    len(percentiles),
                ),
                top_drivers=_top_drivers(raw_location, raw_rank, percentiles),
                edge_ablations=_edge_ablations(
                    specs_by_kinase[identifier],
                    observations,
                    percentiles,
                    raw_location,
                    raw_rank,
                ),
                abstention_reasons=reasons if support is not AnalysisSupport.SUPPORTED else (),
            )
        )
    kinase_outputs = tuple(outputs)
    subtype_outputs = _subtype_outputs(
        masters,
        kinase_outputs,
        location_samples,
        request.bootstrap_replicates,
    )
    provenance = MasterKinaseProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        catalog_content_digest=catalog.content_digest,
        catalog_artifact_digest=catalog.artifact_digest,
        source_workbook_digest=catalog.source_sha256,
        table5a_background_tuple_digest=catalog.background_tuple_digest,
        table5a_background_label_digest=catalog.background_label_digest,
        table5d_signature_edge_digest=catalog.signature_edge_digest,
        table5e_master_kinase_digest=catalog.master_kinase_digest,
        kinase_alias_digest=catalog.alias_digest,
        engine_source_digest=profile.engine_source_digest,
        demo_result_oracle_digest=profile.demo_result_oracle_digest,
        numpy_version=np.__version__,
        computational_digest=computational_digest,
        bootstrap_seed=bootstrap_seed,
        permutation_seed=permutation_seed,
        bootstrap_replicates_requested=request.bootstrap_replicates,
        permutation_replicates_requested=request.permutation_replicates,
        observation_source_digests=tuple(
            sorted({item.provenance_digest for item in request.observations})
        ),
        source_article_doi=catalog.article_doi,
        source_article_title=catalog.article_title,
        source_article_authors=catalog.article_authors,
        source_url=catalog.source_url,
        source_license="CC-BY-4.0",
        source_license_url="https://creativecommons.org/licenses/by/4.0/",
        source_transformation_notice=catalog.transformation_notice,
    )
    limitations = (
        "This is an independent GLIO-PROTEOGEN signature-concordance engine, not a port or retraining of SPHINKS/MK.",
        "Scores are not calibrated kinase activities, subtype probabilities, causal estimates, diagnoses, or treatment guidance.",
        "The frozen signatures come from Migliozzi et al. Nature Cancer 2023 Supplementary Tables 5d/e.",
        "Active rank-background identifiers must exactly match the pinned Table 5a source-label universe; fake sites never enter the null.",
        "Repeated kinase-site source rows remain in provenance but are collapsed by mean SVM probability before any evidence count or inference.",
        "Missing and unsupported values are ignored and never converted into negative observations.",
        "Left-censored values use one-sided location loss and only binding limits count as location support; they are excluded from exact ranks.",
        "Bootstrap intervals use independent perturbations at caller-supplied fixed standard errors; censored standard errors describe uncertainty in the reported upper limit. Tracks preserve global replicate identity, abstain below the profile-bound success fraction, and do not model covariance or biological variance.",
        "Repository-defined rank p/q values use residue-stratified complete-observation-tuple permutations under a conditional fixed source-edge-weight null and require an effect-independent assay/background inclusion process; prefiltering or cherry-picking sites invalidates their calibration.",
        "Subtype kinase summaries can share phosphosites and are therefore correlated; subtype effective sample size is Kish ESS over aggregation weights, not an independent site or sample count.",
        "Activated and suppressed mean higher or lower concordance relative to the caller-declared contrast, not absolute biological activation.",
        "Outputs are synchronous, deterministic, stateless, research-use-only, and non-prescriptive.",
    )
    payload = {
        "algorithm_id": "sphinks-gbm-master-kinase-concordance",
        "algorithm_version": "1.0.0",
        "profile_id": "sphinks-gbm-master-kinase-concordance/1.0.0",
        "profile_digest": profile.profile_digest,
        "request_digest": request_digest,
        "sample_id": request.sample_id,
        "contrast_reference": request.contrast_reference.model_dump(mode="json"),
        "kinase_evidence": [item.model_dump(mode="json") for item in kinase_outputs],
        "subtype_evidence": [item.model_dump(mode="json") for item in subtype_outputs],
        "provenance": provenance.model_dump(mode="json"),
        "output_semantics": "independent_signature_concordance_evidence",
        "limitations": list(limitations),
        "research_use_only": True,
        "non_prescriptive": True,
    }
    result = MasterKinaseResult(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest=result_payload_digest(payload),
        sample_id=request.sample_id,
        contrast_reference=request.contrast_reference,
        kinase_evidence=kinase_outputs,
        subtype_evidence=subtype_outputs,
        provenance=provenance,
        limitations=limitations,
    )
    checkpoint(cancellation)
    return result


__all__ = ["infer_master_kinases"]
