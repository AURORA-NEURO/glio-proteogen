"""Deterministic evidence-conserving graph inference for research use only.

The numerical core uses directed, target-conditional IRLS fixed-point updates. Missing and
unsupported measurements never enter the objective; left-censored observations contribute
a one-sided residual only when a latent value exceeds their declared upper bound.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Final, Iterable, Literal, cast

import numpy as np
import numpy.typing as npt

from .cancellation import CancellationContext, checkpoint
from .canonical import (
    canonical_request_digest,
    computational_request_digest,
    result_payload_digest,
    sha256_digest,
)
from .contracts import (
    AblationEffect,
    AblationKind,
    DriverContribution,
    EdgeKind,
    EvidenceModality,
    EvidenceState,
    ExternalKinaseComparison,
    ExternalKinaseMatch,
    InferenceSupport,
    KinaseInference,
    NodeInference,
    NodeKind,
    ProteogenomicStateRequest,
    ProteogenomicStateResult,
    ResearchProvenance,
    SolverDiagnostics,
    SolverPassDiagnostics,
    StateClassification,
)
from .profile import CONSTANTS, algorithm_profile, relation_weight

_FLOAT = np.float64
_PERMUTATION_CHECK_INTERVAL: Final = 32
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_LIMITATIONS: Final = (
    "Research-use-only latent activity estimates; not validated for clinical use.",
    "Graph topology and caller-supplied evidence determine the result; association is not causation.",
    "All estimated states are LIMITED because caller-curated and synthetic-abstraction graphs are not validated glioma models.",
    "Experimental kinase enrichment is local to this research lane and is non-prescriptive.",
    "Bootstrap intervals describe numerical sensitivity, not calibrated biological probability.",
)


class InferenceConvergenceError(ValueError):
    """Raised when a required deterministic inference stage cannot converge."""


def _digest_seed(material: str) -> int:
    seed_bytes = sha256(material.encode()).digest()[: CONSTANTS.random_seed_bytes]
    return int.from_bytes(seed_bytes, "big", signed=False) % CONSTANTS.random_seed_modulus


@dataclass(frozen=True, slots=True)
class _ObservationTerm:
    observation_id: str
    node_index: int
    modality: EvidenceModality
    state: EvidenceState
    value: float
    standard_error: float
    quality: float


@dataclass(frozen=True, slots=True)
class _EdgeTerm:
    edge_id: str
    source_index: int
    target_index: int
    kind: EdgeKind
    sign: int
    weight: float
    essential: bool


@dataclass(frozen=True, slots=True)
class _FeedbackTerm:
    kinase_id: str
    node_index: int
    value: float
    standard_error: float
    weight: float


@dataclass(frozen=True, slots=True)
class _SolveOutcome:
    values: npt.NDArray[np.float64]
    converged: bool
    iterations: int
    objective: float
    max_update: float
    objective_trace: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _KinaseEstimate:
    kinase_id: str
    node_index: int
    mapped_substrates: int
    rank_statistic: float | None
    enrichment_score: float | None
    p_value: float | None
    q_value: float | None
    null_standard_deviation: float | None


@dataclass(frozen=True, slots=True)
class _PipelineOutcome:
    first_pass: _SolveOutcome
    kinase_estimates: tuple[_KinaseEstimate, ...]
    feedback: tuple[_FeedbackTerm, ...]
    second_pass: _SolveOutcome


@dataclass(frozen=True, slots=True)
class _PreparedGraph:
    node_ids: tuple[str, ...]
    node_kinds: tuple[NodeKind, ...]
    node_index: dict[str, int]
    observations: tuple[_ObservationTerm, ...]
    edges: tuple[_EdgeTerm, ...]
    observations_by_node: tuple[tuple[_ObservationTerm, ...], ...]
    incoming_edges_by_node: tuple[tuple[_EdgeTerm, ...], ...]
    outgoing_edges_by_node: tuple[tuple[_EdgeTerm, ...], ...]


def _quantize(value: float) -> float:
    rounded = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if rounded == 0.0 else rounded


def _huber_loss(residual: float) -> float:
    absolute = abs(residual)
    if absolute <= CONSTANTS.huber_delta:
        return 0.5 * residual * residual
    return CONSTANTS.huber_delta * (absolute - 0.5 * CONSTANTS.huber_delta)


def _huber_weight(residual: float) -> float:
    absolute = abs(residual)
    if absolute <= CONSTANTS.huber_delta or absolute == 0.0:
        return 1.0
    return CONSTANTS.huber_delta / absolute


def _prepare(request: ProteogenomicStateRequest) -> _PreparedGraph:
    ordered_nodes = tuple(sorted(request.nodes, key=lambda item: item.node_id))
    node_ids = tuple(node.node_id for node in ordered_nodes)
    node_kinds = tuple(node.kind for node in ordered_nodes)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    observations = tuple(
        _ObservationTerm(
            observation_id=item.observation_id,
            node_index=node_index[item.node_id],
            modality=item.modality,
            state=item.state,
            value=float(item.standardized_effect),
            standard_error=float(item.standard_error),
            quality=item.quality_weight,
        )
        for item in sorted(request.observations, key=lambda value: value.observation_id)
        if item.state in {EvidenceState.OBSERVED, EvidenceState.LEFT_CENSORED}
        and item.standardized_effect is not None
        and item.standard_error is not None
    )
    edges = tuple(
        _EdgeTerm(
            edge_id=edge.edge_id,
            source_index=node_index[edge.source_id],
            target_index=node_index[edge.target_id],
            kind=edge.kind,
            sign=edge.sign,
            weight=edge.weight * relation_weight(edge.kind),
            essential=edge.essential,
        )
        for edge in sorted(request.edges, key=lambda value: value.edge_id)
    )
    observations_by_node_values: list[list[_ObservationTerm]] = [[] for _ in ordered_nodes]
    incoming_edges_by_node: list[list[_EdgeTerm]] = [[] for _ in ordered_nodes]
    outgoing_edges_by_node: list[list[_EdgeTerm]] = [[] for _ in ordered_nodes]
    for observation in observations:
        observations_by_node_values[observation.node_index].append(observation)
    for edge in edges:
        outgoing_edges_by_node[edge.source_index].append(edge)
        incoming_edges_by_node[edge.target_index].append(edge)
    return _PreparedGraph(
        node_ids=node_ids,
        node_kinds=node_kinds,
        node_index=node_index,
        observations=observations,
        edges=edges,
        observations_by_node=tuple(tuple(items) for items in observations_by_node_values),
        incoming_edges_by_node=tuple(tuple(items) for items in incoming_edges_by_node),
        outgoing_edges_by_node=tuple(tuple(items) for items in outgoing_edges_by_node),
    )


def _active_observations(
    graph: _PreparedGraph,
    excluded_modality: EvidenceModality | None,
    overrides: dict[str, float] | None,
) -> tuple[_ObservationTerm, ...]:
    return tuple(
        replace(
            observation,
            value=(
                overrides[observation.observation_id]
                if overrides is not None and observation.observation_id in overrides
                else observation.value
            ),
        )
        for observation in graph.observations
        if observation.modality is not excluded_modality
    )


def _active_edges(
    graph: _PreparedGraph,
    excluded_edge_kinds: frozenset[EdgeKind],
    active_kinase_sources: frozenset[int] | None = None,
) -> tuple[_EdgeTerm, ...]:
    return tuple(
        edge
        for edge in graph.edges
        if edge.kind not in excluded_edge_kinds
        and (
            edge.kind is not EdgeKind.KINASE_SUBSTRATE
            or active_kinase_sources is None
            or edge.source_index in active_kinase_sources
        )
    )


def _objective(
    values: npt.NDArray[np.float64],
    parent_values: npt.NDArray[np.float64],
    observations: tuple[_ObservationTerm, ...],
    edges: tuple[_EdgeTerm, ...],
    feedback: tuple[_FeedbackTerm, ...],
) -> float:
    """Evaluate target-conditional loss with edge parents frozen to one sweep snapshot."""

    total = 0.5 * CONSTANTS.ridge_penalty * float(np.dot(values, values))
    for observation in observations:
        residual = (float(values[observation.node_index]) - observation.value) / (
            observation.standard_error
        )
        if observation.state is EvidenceState.LEFT_CENSORED:
            residual = max(0.0, residual)
        total += observation.quality * _huber_loss(residual)
    for edge in edges:
        source_value = float(parent_values[edge.source_index])
        residual = float(values[edge.target_index] - edge.sign * source_value)
        total += edge.weight * _huber_loss(residual)
        if edge.kind is EdgeKind.MEMBER_OF:
            total += CONSTANTS.complex_coherence_weight * edge.weight * _huber_loss(residual)
            if edge.essential:
                bottleneck = max(
                    0.0,
                    float(values[edge.target_index] - source_value),
                )
                total += (
                    CONSTANTS.essential_bottleneck_weight * edge.weight * _huber_loss(bottleneck)
                )
    for item in feedback:
        residual = (float(values[item.node_index]) - item.value) / item.standard_error
        total += item.weight * _huber_loss(residual)
    return total


def _observation_update(current: float, observation: _ObservationTerm) -> tuple[float, float]:
    residual = (current - observation.value) / observation.standard_error
    if observation.state is EvidenceState.LEFT_CENSORED:
        if residual <= 0.0:
            return 0.0, 0.0
        residual = max(0.0, residual)
    weight = (
        observation.quality
        * _huber_weight(residual)
        / (observation.standard_error * observation.standard_error)
    )
    return weight, weight * observation.value


def _edge_update(parent_values: npt.NDArray[np.float64], edge: _EdgeTerm) -> tuple[float, float]:
    source_value = float(parent_values[edge.source_index])
    target_value = float(parent_values[edge.target_index])
    residual = target_value - edge.sign * source_value
    weight = edge.weight * _huber_weight(residual)
    if edge.kind is EdgeKind.MEMBER_OF:
        weight += CONSTANTS.complex_coherence_weight * edge.weight * _huber_weight(residual)
        if edge.essential and target_value > source_value:
            bottleneck = target_value - source_value
            weight += (
                CONSTANTS.essential_bottleneck_weight * edge.weight * _huber_weight(bottleneck)
            )
    desired = edge.sign * source_value
    return weight, weight * desired


def _feedback_update(current: float, item: _FeedbackTerm) -> tuple[float, float]:
    residual = (current - item.value) / item.standard_error
    weight = item.weight * _huber_weight(residual) / (item.standard_error**2)
    return weight, weight * item.value


def _initial_values(
    node_count: int,
    observations: tuple[_ObservationTerm, ...],
    initial: npt.NDArray[np.float64] | None,
) -> npt.NDArray[np.float64]:
    if initial is not None:
        return np.asarray(initial, dtype=_FLOAT).copy()
    values = np.zeros(node_count, dtype=_FLOAT)
    numerator = np.zeros(node_count, dtype=_FLOAT)
    denominator = np.zeros(node_count, dtype=_FLOAT)
    for item in observations:
        weight = item.quality / (item.standard_error**2)
        numerator[item.node_index] += weight * item.value
        denominator[item.node_index] += weight
    np.divide(numerator, denominator, out=values, where=denominator > 0.0)
    return values


def _solve(  # noqa: PLR0915
    graph: _PreparedGraph,
    *,
    feedback: tuple[_FeedbackTerm, ...] = (),
    excluded_modality: EvidenceModality | None = None,
    excluded_edge_kinds: frozenset[EdgeKind] = frozenset(),
    overrides: dict[str, float] | None = None,
    initial: npt.NDArray[np.float64] | None = None,
    active_kinase_sources: frozenset[int] | None = None,
    relaxed: bool = False,
    cancellation: CancellationContext | None = None,
) -> _SolveOutcome:
    checkpoint(cancellation)
    observations = _active_observations(graph, excluded_modality, overrides)
    edges = _active_edges(graph, excluded_edge_kinds, active_kinase_sources)
    observations_by_node: list[list[_ObservationTerm]] = [[] for _ in graph.node_ids]
    incoming_edges_by_node: list[list[_EdgeTerm]] = [[] for _ in graph.node_ids]
    feedback_by_node: list[list[_FeedbackTerm]] = [[] for _ in graph.node_ids]
    for observation_item in observations:
        observations_by_node[observation_item.node_index].append(observation_item)
    for edge in edges:
        incoming_edges_by_node[edge.target_index].append(edge)
    for feedback_item in feedback:
        feedback_by_node[feedback_item.node_index].append(feedback_item)
    values = _initial_values(len(graph.node_ids), observations, initial)
    trace: list[float] = []
    max_iterations = (
        min(CONSTANTS.max_iterations, CONSTANTS.relaxed_max_iterations)
        if relaxed
        else CONSTANTS.max_iterations
    )
    tolerance = (
        max(CONSTANTS.tolerance, CONSTANTS.relaxed_tolerance) if relaxed else CONSTANTS.tolerance
    )
    converged = False
    maximum_update = 0.0
    iterations = 0
    for _ in range(max_iterations):
        checkpoint(cancellation)
        iterations += 1
        prior = values.copy()
        candidates = prior.copy()
        fixed_point_values = prior.copy()
        for node_index in range(len(values)):
            denominator = CONSTANTS.ridge_penalty
            numerator = 0.0
            current = float(prior[node_index])
            for observation in observations_by_node[node_index]:
                weight, target = _observation_update(current, observation)
                denominator += weight
                numerator += target
            for edge in incoming_edges_by_node[node_index]:
                weight, target = _edge_update(prior, edge)
                denominator += weight
                numerator += target
            for feedback_item in feedback_by_node[node_index]:
                weight, target = _feedback_update(current, feedback_item)
                denominator += weight
                numerator += target
            candidate = numerator / denominator
            fixed_point_values[node_index] = candidate
            candidates[node_index] = current + CONSTANTS.damping * (candidate - current)
        baseline_objective = _objective(prior, prior, observations, edges, feedback)
        candidate_objective = _objective(candidates, prior, observations, edges, feedback)
        if candidate_objective > baseline_objective + CONSTANTS.objective_increase_tolerance:
            direction = candidates - prior
            step = CONSTANTS.backtracking_factor
            accepted = False
            for _ in range(CONSTANTS.backtracking_steps):
                trial = prior + step * direction
                trial_objective = _objective(trial, prior, observations, edges, feedback)
                if trial_objective <= baseline_objective + CONSTANTS.objective_increase_tolerance:
                    candidates = trial
                    candidate_objective = trial_objective
                    accepted = True
                    break
                step *= CONSTANTS.backtracking_factor
            if not accepted:
                candidates = prior
                candidate_objective = baseline_objective
        values = candidates
        maximum_update = float(np.max(np.abs(fixed_point_values - prior), initial=0.0))
        trace.extend((baseline_objective, candidate_objective))
        if maximum_update <= tolerance:
            converged = True
            break
    return _SolveOutcome(
        values=values,
        converged=converged,
        iterations=iterations,
        objective=trace[-1],
        max_update=maximum_update,
        objective_trace=tuple(trace),
    )


def _rank_values(values: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Return deterministic average ranks in [0, 1], including exact ties."""

    order = np.argsort(values, kind="stable")
    ranks = np.empty(len(values), dtype=_FLOAT)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average = (cursor + end - 1) / 2.0
        for ordered_index in order[cursor:end]:
            ranks[ordered_index] = average
        cursor = end
    if len(values) <= 1:
        return np.full(len(values), CONSTANTS.rank_center, dtype=_FLOAT)
    return ranks / (len(values) - 1)


def _site_reliability(
    graph: _PreparedGraph, excluded_modality: EvidenceModality | None = None
) -> dict[int, float]:
    reliability: dict[int, float] = {}
    for node_index, kind in enumerate(graph.node_kinds):
        if kind is not NodeKind.PHOSPHOSITE:
            continue
        terms = tuple(
            item
            for item in graph.observations_by_node[node_index]
            if item.modality is EvidenceModality.PHOSPHOPROTEOMICS
            and item.modality is not excluded_modality
        )
        if terms:
            reliability[node_index] = sum(
                item.quality / (item.standard_error**2) for item in terms
            ) / len(terms)
    return reliability


def _strata(reliabilities: npt.NDArray[np.float64]) -> npt.NDArray[np.int64]:
    if len(reliabilities) < CONSTANTS.min_stratified_site_count:
        return np.zeros(len(reliabilities), dtype=np.int64)
    cut_points = np.quantile(
        reliabilities,
        (
            CONSTANTS.reliability_stratum_q1,
            CONSTANTS.reliability_stratum_q2,
            CONSTANTS.reliability_stratum_q3,
        ),
        method=CONSTANTS.bootstrap_quantile_method,
    )
    return np.searchsorted(cut_points, reliabilities, side="right").astype(np.int64)


def _enrichment_statistic(
    ranks: npt.NDArray[np.float64],
    positions: npt.NDArray[np.int64],
    signs: npt.NDArray[np.float64],
    weights: npt.NDArray[np.float64],
) -> float:
    centered = (ranks[positions] - CONSTANTS.rank_center) / CONSTANTS.rank_center
    return float(np.dot(weights, signs * centered) / np.sum(weights))


def _mapped_substrate_edges(
    graph: _PreparedGraph,
    kinase_index: int,
    reliability_by_index: dict[int, float],
    excluded_edge_kind: EdgeKind | None = None,
) -> tuple[_EdgeTerm, ...]:
    if excluded_edge_kind is EdgeKind.KINASE_SUBSTRATE:
        return ()
    unique_by_target: dict[int, _EdgeTerm] = {}
    for edge in graph.outgoing_edges_by_node[kinase_index]:
        if edge.kind is EdgeKind.KINASE_SUBSTRATE and edge.target_index in reliability_by_index:
            unique_by_target[edge.target_index] = edge
    return tuple(unique_by_target[index] for index in sorted(unique_by_target))


def _kinase_enrichment(
    request_digest: str,
    graph: _PreparedGraph,
    first_pass: npt.NDArray[np.float64],
    permutations: int,
    *,
    excluded_modality: EvidenceModality | None = None,
    excluded_edge_kind: EdgeKind | None = None,
    cancellation: CancellationContext | None = None,
) -> tuple[_KinaseEstimate, ...]:
    checkpoint(cancellation)
    reliability_by_index = _site_reliability(graph, excluded_modality)
    site_indices = np.asarray(sorted(reliability_by_index), dtype=np.int64)
    if len(site_indices) == 0:
        return tuple(
            _KinaseEstimate(node_id, index, 0, None, None, None, None, None)
            for index, (node_id, kind) in enumerate(
                zip(graph.node_ids, graph.node_kinds, strict=True)
            )
            if kind is NodeKind.KINASE
        )
    site_values = first_pass[site_indices]
    ranks = _rank_values(site_values)
    site_position = {int(node_index): position for position, node_index in enumerate(site_indices)}
    reliabilities = np.asarray(
        [reliability_by_index[int(node_index)] for node_index in site_indices], dtype=_FLOAT
    )
    strata = _strata(reliabilities)
    raw: list[_KinaseEstimate] = []
    for kinase_index, (kinase_id, kind) in enumerate(
        zip(graph.node_ids, graph.node_kinds, strict=True)
    ):
        checkpoint(cancellation)
        if kind is not NodeKind.KINASE:
            continue
        mapped = _mapped_substrate_edges(
            graph,
            kinase_index,
            reliability_by_index,
            excluded_edge_kind,
        )
        if len(mapped) < CONSTANTS.kinase_min_substrates:
            raw.append(
                _KinaseEstimate(kinase_id, kinase_index, len(mapped), None, None, None, None, None)
            )
            continue
        positions = np.asarray(
            [site_position[edge.target_index] for edge in mapped], dtype=np.int64
        )
        signs = np.asarray([edge.sign for edge in mapped], dtype=_FLOAT)
        weights = np.asarray(
            [edge.weight * reliability_by_index[edge.target_index] for edge in mapped],
            dtype=_FLOAT,
        )
        observed = _enrichment_statistic(ranks, positions, signs, weights)
        rng = np.random.default_rng(_digest_seed(f"{request_digest}|{kinase_id}|permutation"))
        permutation_scores = np.empty(permutations, dtype=_FLOAT)
        mapped_strata = strata[positions]
        for replicate in range(permutations):
            if replicate % _PERMUTATION_CHECK_INTERVAL == 0:
                checkpoint(cancellation)
            sampled = np.empty(len(positions), dtype=np.int64)
            for stratum in sorted({int(value) for value in mapped_strata}):
                output_positions = np.flatnonzero(mapped_strata == stratum)
                pool = np.flatnonzero(strata == stratum)
                sampled[output_positions] = rng.choice(
                    pool,
                    size=len(output_positions),
                    replace=len(pool) < len(output_positions),
                )
            permutation_scores[replicate] = _enrichment_statistic(ranks, sampled, signs, weights)
        p_value = (
            CONSTANTS.empirical_p_pseudocount
            + float(np.count_nonzero(np.abs(permutation_scores) >= abs(observed)))
        ) / (permutations + CONSTANTS.empirical_p_pseudocount)
        null_deviation = max(
            float(np.std(permutation_scores, ddof=CONSTANTS.kinase_null_ddof)),
            CONSTANTS.kinase_null_sd_floor,
        )
        enrichment_score = float(
            np.clip(
                observed / null_deviation,
                -CONSTANTS.kinase_score_clip,
                CONSTANTS.kinase_score_clip,
            )
        )
        raw.append(
            _KinaseEstimate(
                kinase_id,
                kinase_index,
                len(mapped),
                observed,
                enrichment_score,
                p_value,
                None,
                null_deviation,
            )
        )
    tested = [(index, item.p_value) for index, item in enumerate(raw) if item.p_value is not None]
    if tested:
        ordered = sorted(tested, key=lambda item: (float(item[1]), raw[item[0]].kinase_id))
        adjusted: dict[int, float] = {}
        running = 1.0
        count = len(ordered)
        for reverse_rank, (index, p_value) in enumerate(reversed(ordered), start=1):
            rank = count - reverse_rank + 1
            running = min(running, float(p_value) * count / rank)
            adjusted[index] = min(1.0, running)
        raw = [replace(item, q_value=adjusted.get(index)) for index, item in enumerate(raw)]
    return tuple(raw)


def _feedback(kinases: tuple[_KinaseEstimate, ...]) -> tuple[_FeedbackTerm, ...]:
    return tuple(
        _FeedbackTerm(
            kinase_id=item.kinase_id,
            node_index=item.node_index,
            value=float(item.enrichment_score),
            standard_error=CONSTANTS.kinase_feedback_standard_error,
            weight=CONSTANTS.kinase_feedback_weight,
        )
        for item in kinases
        if item.enrichment_score is not None
        and item.q_value is not None
        and item.q_value <= CONSTANTS.kinase_q_threshold
    )


def _bootstrap_feedback(
    graph: _PreparedGraph,
    first_pass: npt.NDArray[np.float64],
    kinases: tuple[_KinaseEstimate, ...],
) -> tuple[_FeedbackTerm, ...]:
    """Rescore q-supported kinases without repeating selection/permutation testing."""

    supported = tuple(
        item
        for item in kinases
        if item.q_value is not None
        and item.q_value <= CONSTANTS.kinase_q_threshold
        and item.null_standard_deviation is not None
    )
    if not supported:
        return ()
    reliability_by_index = _site_reliability(graph)
    site_indices = np.asarray(sorted(reliability_by_index), dtype=np.int64)
    if len(site_indices) == 0:
        return ()
    ranks = _rank_values(first_pass[site_indices])
    site_position = {int(node_index): position for position, node_index in enumerate(site_indices)}
    feedback: list[_FeedbackTerm] = []
    for item in supported:
        mapped = _mapped_substrate_edges(graph, item.node_index, reliability_by_index)
        if len(mapped) < CONSTANTS.kinase_min_substrates:
            raise ValueError("supported kinase lost its mapped substrates during bootstrap")
        positions = np.asarray(
            [site_position[edge.target_index] for edge in mapped], dtype=np.int64
        )
        signs = np.asarray([edge.sign for edge in mapped], dtype=_FLOAT)
        weights = np.asarray(
            [edge.weight * reliability_by_index[edge.target_index] for edge in mapped],
            dtype=_FLOAT,
        )
        rank_statistic = _enrichment_statistic(ranks, positions, signs, weights)
        null_deviation = cast("float", item.null_standard_deviation)
        score = float(
            np.clip(
                rank_statistic / null_deviation,
                -CONSTANTS.kinase_score_clip,
                CONSTANTS.kinase_score_clip,
            )
        )
        feedback.append(
            _FeedbackTerm(
                kinase_id=item.kinase_id,
                node_index=item.node_index,
                value=score,
                standard_error=CONSTANTS.kinase_feedback_standard_error,
                weight=CONSTANTS.kinase_feedback_weight,
            )
        )
    return tuple(feedback)


def _solve_checked(
    graph: _PreparedGraph,
    *,
    stage: str,
    feedback: tuple[_FeedbackTerm, ...] = (),
    excluded_modality: EvidenceModality | None = None,
    excluded_edge_kinds: frozenset[EdgeKind] = frozenset(),
    overrides: dict[str, float] | None = None,
    initial: npt.NDArray[np.float64] | None = None,
    active_kinase_sources: frozenset[int] | None = None,
    relaxed_first: bool = False,
    cancellation: CancellationContext | None = None,
) -> _SolveOutcome:
    checkpoint(cancellation)
    outcome = _solve(
        graph,
        feedback=feedback,
        excluded_modality=excluded_modality,
        excluded_edge_kinds=excluded_edge_kinds,
        overrides=overrides,
        initial=initial,
        active_kinase_sources=active_kinase_sources,
        relaxed=relaxed_first,
        cancellation=cancellation,
    )
    if not outcome.converged and relaxed_first:
        checkpoint(cancellation)
        outcome = _solve(
            graph,
            feedback=feedback,
            excluded_modality=excluded_modality,
            excluded_edge_kinds=excluded_edge_kinds,
            overrides=overrides,
            initial=outcome.values,
            active_kinase_sources=active_kinase_sources,
            cancellation=cancellation,
        )
    if not outcome.converged:
        raise InferenceConvergenceError(
            f"{stage} failed to converge after {outcome.iterations} iterations"
        )
    return outcome


def _run_pipeline(
    seed_material: str,
    graph: _PreparedGraph,
    permutations: int,
    *,
    stage: str,
    excluded_modality: EvidenceModality | None = None,
    excluded_edge_kind: EdgeKind | None = None,
    initial: npt.NDArray[np.float64] | None = None,
    relaxed_first: bool = False,
    cancellation: CancellationContext | None = None,
) -> _PipelineOutcome:
    checkpoint(cancellation)
    first_exclusions = {EdgeKind.KINASE_SUBSTRATE}
    if excluded_edge_kind is not None:
        first_exclusions.add(excluded_edge_kind)
    first_pass = _solve_checked(
        graph,
        stage=f"{stage}:evidence_graph",
        excluded_modality=excluded_modality,
        excluded_edge_kinds=frozenset(first_exclusions),
        initial=initial,
        relaxed_first=relaxed_first,
        cancellation=cancellation,
    )
    kinase_estimates = _kinase_enrichment(
        seed_material,
        graph,
        first_pass.values,
        permutations,
        excluded_modality=excluded_modality,
        excluded_edge_kind=excluded_edge_kind,
        cancellation=cancellation,
    )
    feedback = _feedback(kinase_estimates)
    active_kinase_sources = frozenset(item.node_index for item in feedback)
    second_exclusions = (
        frozenset({excluded_edge_kind}) if excluded_edge_kind is not None else frozenset()
    )
    second_pass = _solve_checked(
        graph,
        stage=f"{stage}:kinase_feedback",
        feedback=feedback,
        excluded_modality=excluded_modality,
        excluded_edge_kinds=second_exclusions,
        initial=first_pass.values,
        active_kinase_sources=active_kinase_sources,
        relaxed_first=relaxed_first,
        cancellation=cancellation,
    )
    return _PipelineOutcome(first_pass, kinase_estimates, feedback, second_pass)


def _bootstrap(
    request_digest: str,
    graph: _PreparedGraph,
    kinase_estimates: tuple[_KinaseEstimate, ...],
    first_values: npt.NDArray[np.float64],
    replicates: int,
    *,
    cancellation: CancellationContext | None = None,
) -> npt.NDArray[np.float64]:
    checkpoint(cancellation)
    rng = np.random.default_rng(_digest_seed(f"{request_digest}|bootstrap"))
    samples = np.empty((replicates, len(graph.node_ids)), dtype=_FLOAT)
    perturbations = _antithetic_perturbations(rng, graph.observations, replicates)
    for replicate in range(replicates):
        checkpoint(cancellation)
        overrides = {
            item.observation_id: item.value + float(perturbations[replicate, index])
            for index, item in enumerate(graph.observations)
        }
        first = _solve_checked(
            graph,
            stage=f"bootstrap[{replicate}]:evidence_graph",
            excluded_edge_kinds=frozenset({EdgeKind.KINASE_SUBSTRATE}),
            overrides=overrides,
            initial=first_values,
            relaxed_first=True,
            cancellation=cancellation,
        )
        feedback = _bootstrap_feedback(graph, first.values, kinase_estimates)
        active_kinase_sources = frozenset(item.node_index for item in feedback)
        second = _solve_checked(
            graph,
            stage=f"bootstrap[{replicate}]:kinase_feedback",
            feedback=feedback,
            overrides=overrides,
            initial=first.values,
            active_kinase_sources=active_kinase_sources,
            relaxed_first=True,
            cancellation=cancellation,
        )
        samples[replicate] = second.values
    return samples


def _antithetic_perturbations(
    rng: np.random.Generator,
    observations: tuple[_ObservationTerm, ...],
    replicates: int,
) -> npt.NDArray[np.float64]:
    """Generate marginally normal, pair-balanced evidence perturbations."""

    observation_count = len(observations)
    pair_count = replicates // 2
    base_noise = rng.standard_normal((pair_count, observation_count), dtype=_FLOAT)
    unpaired_noise = rng.standard_normal((replicates % 2, observation_count), dtype=_FLOAT)
    perturbations = np.concatenate((unpaired_noise, base_noise, -base_noise), axis=0)
    perturbation_scales = np.asarray(
        [item.standard_error * CONSTANTS.bootstrap_perturbation_scale for item in observations],
        dtype=_FLOAT,
    )
    perturbations *= perturbation_scales
    return perturbations


def _ablation_delta(base: float, ablated: float) -> float:
    """Suppress solver-resolution noise from otherwise inert ablations."""

    delta = float(base - ablated)
    if abs(delta) <= CONSTANTS.relaxed_tolerance:
        return 0.0
    return _quantize(delta)


def _ablations(
    request_digest: str,
    graph: _PreparedGraph,
    base_values: npt.NDArray[np.float64],
    permutations: int,
    *,
    cancellation: CancellationContext | None = None,
) -> tuple[tuple[AblationEffect, ...], ...]:
    checkpoint(cancellation)
    effects: list[list[AblationEffect]] = [[] for _ in graph.node_ids]
    modalities = sorted({item.modality for item in graph.observations}, key=lambda item: item.value)
    edge_kinds = sorted({edge.kind for edge in graph.edges}, key=lambda item: item.value)
    for modality in modalities:
        checkpoint(cancellation)
        pipeline = _run_pipeline(
            request_digest,
            graph,
            permutations,
            stage=f"ablation:modality:{modality.value}",
            excluded_modality=modality,
            relaxed_first=True,
            cancellation=cancellation,
        )
        for index, (base, ablated) in enumerate(
            zip(base_values, pipeline.second_pass.values, strict=True)
        ):
            effects[index].append(
                AblationEffect(
                    kind=AblationKind.MODALITY,
                    omitted=modality.value,
                    activity_delta=_ablation_delta(float(base), float(ablated)),
                )
            )
    for edge_kind in edge_kinds:
        checkpoint(cancellation)
        pipeline = _run_pipeline(
            request_digest,
            graph,
            permutations,
            stage=f"ablation:edge_family:{edge_kind.value}",
            excluded_edge_kind=edge_kind,
            relaxed_first=True,
            cancellation=cancellation,
        )
        for index, (base, ablated) in enumerate(
            zip(base_values, pipeline.second_pass.values, strict=True)
        ):
            effects[index].append(
                AblationEffect(
                    kind=AblationKind.EDGE_FAMILY,
                    omitted=edge_kind.value,
                    activity_delta=_ablation_delta(float(base), float(ablated)),
                )
            )
    return tuple(tuple(items) for items in effects)


def _evidence_reachability(
    graph: _PreparedGraph,
    feedback: tuple[_FeedbackTerm, ...],
    active_kinase_sources: frozenset[int],
) -> set[int]:
    reached = {
        item.node_index
        for item in graph.observations
        if item.state is EvidenceState.OBSERVED
        or (
            item.state is EvidenceState.LEFT_CENSORED
            and item.value < -CONSTANTS.activation_threshold
        )
    } | {item.node_index for item in feedback}
    queue: deque[int] = deque(sorted(reached))
    adjacency: dict[int, set[int]] = defaultdict(set)
    for edge in graph.edges:
        if (
            edge.kind is EdgeKind.KINASE_SUBSTRATE
            and edge.source_index not in active_kinase_sources
        ):
            continue
        adjacency[edge.source_index].add(edge.target_index)
    while queue:
        current = queue.popleft()
        for neighbor in sorted(adjacency[current]):
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return reached


def _classification(lower: float, upper: float) -> StateClassification:
    threshold = CONSTANTS.activation_threshold
    if lower > threshold:
        return StateClassification.ACTIVATED
    if upper < -threshold:
        return StateClassification.SUPPRESSED
    if lower >= -threshold and upper <= threshold:
        return StateClassification.NEUTRAL
    return StateClassification.INDETERMINATE


def _stability(point: float, samples: npt.NDArray[np.float64]) -> float:
    threshold = CONSTANTS.activation_threshold
    if point > threshold:
        return float(np.mean(samples > threshold))
    if point < -threshold:
        return float(np.mean(samples < -threshold))
    return float(np.mean(np.abs(samples) <= threshold))


def _discordance(
    node_index: int,
    values: npt.NDArray[np.float64],
    graph: _PreparedGraph,
    active_kinase_sources: frozenset[int] | None = None,
) -> float:
    residuals: list[float] = []
    value = float(values[node_index])
    for observation in graph.observations_by_node[node_index]:
        residual = (value - observation.value) / observation.standard_error
        if observation.state is EvidenceState.LEFT_CENSORED:
            residual = max(0.0, residual)
        residuals.append(abs(residual) * observation.quality)
    residuals.extend(
        (
            abs(float(values[edge.target_index]) - edge.sign * float(values[edge.source_index]))
            * edge.weight
        )
        for edge in graph.incoming_edges_by_node[node_index]
        if edge.kind is not EdgeKind.KINASE_SUBSTRATE
        or active_kinase_sources is None
        or edge.source_index in active_kinase_sources
    )
    if not residuals:
        return 0.0
    mean = sum(residuals) / len(residuals)
    return mean / (CONSTANTS.discordance_scale + mean)


def _drivers(
    node_index: int,
    values: npt.NDArray[np.float64],
    graph: _PreparedGraph,
    feedback: tuple[_FeedbackTerm, ...],
    active_kinase_sources: frozenset[int] | None = None,
) -> tuple[DriverContribution, ...]:
    point = float(values[node_index])
    drivers: list[DriverContribution] = []
    for item in graph.observations_by_node[node_index]:
        signed = item.quality * (item.value - point) / item.standard_error
        if item.state is EvidenceState.LEFT_CENSORED and point <= item.value:
            signed = 0.0
        drivers.append(
            DriverContribution(
                driver_id=item.observation_id,
                driver_type="observation",
                signed_contribution=_quantize(signed),
                strength=_quantize(abs(signed)),
            )
        )
    for edge in graph.incoming_edges_by_node[node_index]:
        if (
            edge.kind is EdgeKind.KINASE_SUBSTRATE
            and active_kinase_sources is not None
            and edge.source_index not in active_kinase_sources
        ):
            continue
        source = float(values[edge.source_index])
        signed = edge.weight * (edge.sign * source - point)
        drivers.append(
            DriverContribution(
                driver_id=edge.edge_id,
                driver_type="edge",
                signed_contribution=_quantize(signed),
                strength=_quantize(abs(signed)),
            )
        )
    for feedback_item in feedback:
        if feedback_item.node_index == node_index:
            signed = feedback_item.weight * (feedback_item.value - point)
            drivers.append(
                DriverContribution(
                    driver_id=feedback_item.kinase_id,
                    driver_type="kinase_feedback",
                    signed_contribution=_quantize(signed),
                    strength=_quantize(abs(signed)),
                )
            )
    return tuple(
        sorted(drivers, key=lambda item: (-item.strength, item.driver_id))[
            : CONSTANTS.max_top_drivers
        ]
    )


def _observation_counts(
    request: ProteogenomicStateRequest,
) -> dict[str, tuple[int, int, int]]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for item in request.observations:
        if item.state is EvidenceState.OBSERVED:
            counts[item.node_id][0] += 1
            counts[item.node_id][1] += 1
        elif item.state is EvidenceState.LEFT_CENSORED:
            counts[item.node_id][0] += 1
            counts[item.node_id][2] += 1
    return {key: (value[0], value[1], value[2]) for key, value in counts.items()}


def _node_state(
    index: int,
    *,
    graph: _PreparedGraph,
    values: npt.NDArray[np.float64],
    bootstrap: npt.NDArray[np.float64],
    reachability: set[int],
    counts: dict[str, tuple[int, int, int]],
    ablations: tuple[tuple[AblationEffect, ...], ...],
    feedback: tuple[_FeedbackTerm, ...],
    active_kinase_sources: frozenset[int],
) -> NodeInference:
    node_id = graph.node_ids[index]
    evidence_count, observed_count, censored_count = counts.get(node_id, (0, 0, 0))
    if index not in reachability:
        return NodeInference(
            node_id=node_id,
            kind=graph.node_kinds[index],
            classification=StateClassification.NOT_ESTIMABLE,
            support=InferenceSupport.ABSTAINED,
            evidence_count=evidence_count,
            observed_count=observed_count,
            censored_count=censored_count,
            abstention_reason=(
                "No direction-informative measured or feedback evidence is connected to this node."
            ),
        )
    point = _quantize(float(values[index]))
    lower = _quantize(
        min(
            float(
                np.quantile(
                    bootstrap[:, index],
                    CONSTANTS.interval_lower_quantile,
                    method=CONSTANTS.bootstrap_quantile_method,
                )
            ),
            point,
        )
    )
    upper = _quantize(
        max(
            float(
                np.quantile(
                    bootstrap[:, index],
                    CONSTANTS.interval_upper_quantile,
                    method=CONSTANTS.bootstrap_quantile_method,
                )
            ),
            point,
        )
    )
    return NodeInference(
        node_id=node_id,
        kind=graph.node_kinds[index],
        activity=point,
        lower_bound=lower,
        upper_bound=upper,
        classification=_classification(lower, upper),
        support=InferenceSupport.LIMITED,
        evidence_count=evidence_count,
        observed_count=observed_count,
        censored_count=censored_count,
        stability=_quantize(_stability(point, bootstrap[:, index])),
        discordance=_quantize(_discordance(index, values, graph, active_kinase_sources)),
        top_drivers=_drivers(index, values, graph, feedback, active_kinase_sources),
        ablation_effects=ablations[index],
    )


def _kinase_state(
    estimate: _KinaseEstimate,
    *,
    graph: _PreparedGraph,
    values: npt.NDArray[np.float64],
    bootstrap: npt.NDArray[np.float64],
    reachability: set[int],
    counts: dict[str, tuple[int, int, int]],
    ablations: tuple[tuple[AblationEffect, ...], ...],
    feedback: tuple[_FeedbackTerm, ...],
    active_kinase_sources: frozenset[int],
) -> KinaseInference:
    index = estimate.node_index
    node_id = estimate.kinase_id
    evidence_count, observed_count, censored_count = counts.get(node_id, (0, 0, 0))
    if estimate.mapped_substrates < CONSTANTS.kinase_min_substrates:
        return KinaseInference(
            node_id=node_id,
            classification=StateClassification.NOT_ESTIMABLE,
            support=InferenceSupport.ABSTAINED,
            evidence_count=evidence_count,
            observed_count=observed_count,
            censored_count=censored_count,
            abstention_reason="At least three measured kinase substrates are required.",
            mapped_substrates=estimate.mapped_substrates,
        )
    enrichment_score = estimate.enrichment_score
    rank_statistic = estimate.rank_statistic
    null_deviation = estimate.null_standard_deviation
    p_value = estimate.p_value
    q_value = estimate.q_value
    if (
        rank_statistic is None
        or enrichment_score is None
        or null_deviation is None
        or p_value is None
        or q_value is None
    ):
        raise ValueError("mapped kinase estimate is incomplete")
    significant = q_value <= CONSTANTS.kinase_q_threshold
    if not significant or index not in reachability:
        reason = (
            "Local substrate enrichment did not meet the configured q-value support threshold."
            if not significant
            else "Supported kinase feedback was not connected to the directed graph."
        )
        return KinaseInference(
            node_id=node_id,
            classification=StateClassification.NOT_ESTIMABLE,
            support=InferenceSupport.ABSTAINED,
            evidence_count=evidence_count,
            observed_count=observed_count,
            censored_count=censored_count,
            abstention_reason=reason,
            mapped_substrates=estimate.mapped_substrates,
            rank_statistic=_quantize(rank_statistic),
            enrichment_score=_quantize(enrichment_score),
            null_standard_deviation=_quantize(null_deviation),
            p_value=_quantize(p_value),
            q_value=_quantize(q_value),
        )
    point = _quantize(float(values[index]))
    lower = _quantize(
        min(
            float(
                np.quantile(
                    bootstrap[:, index],
                    CONSTANTS.interval_lower_quantile,
                    method=CONSTANTS.bootstrap_quantile_method,
                )
            ),
            point,
        )
    )
    upper = _quantize(
        max(
            float(
                np.quantile(
                    bootstrap[:, index],
                    CONSTANTS.interval_upper_quantile,
                    method=CONSTANTS.bootstrap_quantile_method,
                )
            ),
            point,
        )
    )
    return KinaseInference(
        node_id=node_id,
        activity=point,
        lower_bound=lower,
        upper_bound=upper,
        classification=_classification(lower, upper),
        support=InferenceSupport.LIMITED,
        evidence_count=evidence_count,
        observed_count=observed_count,
        censored_count=censored_count,
        stability=_quantize(_stability(point, bootstrap[:, index])),
        discordance=_quantize(_discordance(index, values, graph, active_kinase_sources)),
        top_drivers=_drivers(index, values, graph, feedback, active_kinase_sources),
        ablation_effects=ablations[index],
        mapped_substrates=estimate.mapped_substrates,
        rank_statistic=_quantize(rank_statistic),
        enrichment_score=_quantize(enrichment_score),
        null_standard_deviation=_quantize(null_deviation),
        p_value=_quantize(p_value),
        q_value=_quantize(q_value),
    )


def _average_ranks(values: Iterable[float]) -> list[float]:
    array = np.asarray(tuple(values), dtype=_FLOAT)
    return [float(value) for value in _rank_values(array)]


def _external_comparison(
    request: ProteogenomicStateRequest,
    kinase_states: tuple[KinaseInference, ...],
) -> ExternalKinaseComparison | None:
    external = request.external_kinase_profile
    if external is None:
        return None
    all_local_ids = {item.node_id for item in kinase_states}
    estimated_local_by_id = {
        item.node_id: item
        for item in kinase_states
        if item.activity is not None
        and item.lower_bound is not None
        and item.upper_bound is not None
    }
    matches: list[ExternalKinaseMatch] = []
    for estimate in sorted(external.estimates, key=lambda item: item.kinase_id):
        local = estimated_local_by_id.get(estimate.kinase_id)
        if local is None:
            continue
        # ``local_by_id`` is constructed only from complete estimated states.
        local_activity = cast("float", local.activity)
        local_lower = cast("float", local.lower_bound)
        local_upper = cast("float", local.upper_bound)
        local_direction = (
            1
            if local_activity > CONSTANTS.activation_threshold
            else -1
            if local_activity < -CONSTANTS.activation_threshold
            else 0
        )
        external_direction = (
            1
            if estimate.activity > CONSTANTS.activation_threshold
            else -1
            if estimate.activity < -CONSTANTS.activation_threshold
            else 0
        )
        matches.append(
            ExternalKinaseMatch(
                kinase_id=estimate.kinase_id,
                local_activity=local_activity,
                external_activity=estimate.activity,
                interval_overlap=(
                    max(local_lower, estimate.lower_bound) <= min(local_upper, estimate.upper_bound)
                ),
                direction_agreement=local_direction == external_direction,
                activity_difference=_quantize(local_activity - estimate.activity),
            )
        )
    correlation: float | None = None
    if len(matches) >= CONSTANTS.min_rank_correlation_pairs:
        local_ranks = np.asarray(_average_ranks(item.local_activity for item in matches))
        external_ranks = np.asarray(_average_ranks(item.external_activity for item in matches))
        if float(np.std(local_ranks)) > 0.0 and float(np.std(external_ranks)) > 0.0:
            correlation = _quantize(float(np.corrcoef(local_ranks, external_ranks)[0, 1]))
    external_ids = {item.kinase_id for item in external.estimates}
    matched_ids = {item.kinase_id for item in matches}
    unmatched = tuple(sorted(all_local_ids - matched_ids))
    abstained_external_ids = tuple(sorted(external_ids - set(estimated_local_by_id)))
    return ExternalKinaseComparison(
        profile_id=external.profile_id,
        source_digest=external.source_digest,
        matches=tuple(matches),
        unmatched_local_ids=unmatched,
        external_ids_with_abstained_local_estimates=abstained_external_ids,
        rank_correlation=correlation,
        note="External values are compared by exact identifier and never merged or substituted.",
    )


def _diagnostics(
    outcome: _SolveOutcome,
    pass_name: Literal["evidence_graph", "kinase_feedback"],
) -> SolverPassDiagnostics:
    trace = tuple(_quantize(value) for value in outcome.objective_trace)
    return SolverPassDiagnostics(
        pass_name=pass_name,
        converged=outcome.converged,
        iterations=outcome.iterations,
        final_objective=_quantize(outcome.objective),
        max_update=_quantize(outcome.max_update),
        objective_trace=trace,
        trace_digest=sha256_digest(list(trace)),
    )


def infer_proteogenomic_state(
    request: ProteogenomicStateRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ProteogenomicStateResult:
    """Run both inference passes, deterministic resampling, and sensitivity ablations."""

    checkpoint(cancellation)
    graph = _prepare(request)
    request_digest = canonical_request_digest(request)
    computational_digest = computational_request_digest(request)
    pipeline = _run_pipeline(
        computational_digest,
        graph,
        request.permutation_replicates,
        stage="analysis",
        cancellation=cancellation,
    )
    first_pass = pipeline.first_pass
    kinase_estimates = pipeline.kinase_estimates
    feedback = pipeline.feedback
    second_pass = pipeline.second_pass
    active_kinase_sources = frozenset(item.node_index for item in feedback)
    bootstrap = _bootstrap(
        computational_digest,
        graph,
        kinase_estimates,
        first_pass.values,
        request.bootstrap_replicates,
        cancellation=cancellation,
    )
    ablations = _ablations(
        computational_digest,
        graph,
        second_pass.values,
        request.permutation_replicates,
        cancellation=cancellation,
    )
    checkpoint(cancellation)
    reachability = _evidence_reachability(graph, feedback, active_kinase_sources)
    counts = _observation_counts(request)
    kinase_by_index = {item.node_index: item for item in kinase_estimates}
    node_states = tuple(
        _node_state(
            index,
            graph=graph,
            values=second_pass.values,
            bootstrap=bootstrap,
            reachability=reachability,
            counts=counts,
            ablations=ablations,
            feedback=feedback,
            active_kinase_sources=active_kinase_sources,
        )
        for index, kind in enumerate(graph.node_kinds)
        if kind is not NodeKind.KINASE
    )
    kinase_states = tuple(
        _kinase_state(
            kinase_by_index[index],
            graph=graph,
            values=second_pass.values,
            bootstrap=bootstrap,
            reachability=reachability,
            counts=counts,
            ablations=ablations,
            feedback=feedback,
            active_kinase_sources=active_kinase_sources,
        )
        for index, kind in enumerate(graph.node_kinds)
        if kind is NodeKind.KINASE
    )
    profile = algorithm_profile()
    deterministic_seed = _digest_seed(f"{computational_digest}|bootstrap")
    provenance = ResearchProvenance(
        numpy_version=np.__version__,
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        computational_digest=computational_digest,
        deterministic_seed=deterministic_seed,
        observation_source_digests=tuple(
            sorted({item.provenance_digest for item in request.observations})
        ),
        topology=request.topology_provenance,
        demo_graph_digest=profile.demo_graph_digest,
    )
    solver_diagnostics = SolverDiagnostics(
        first_pass=_diagnostics(first_pass, "evidence_graph"),
        second_pass=_diagnostics(second_pass, "kinase_feedback"),
    )
    external_comparison = _external_comparison(request, kinase_states)
    unsigned = ProteogenomicStateResult.model_construct(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        sample_id=request.sample_id,
        solver=solver_diagnostics,
        node_states=node_states,
        kinase_states=kinase_states,
        external_kinase_comparison=external_comparison,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    digest = result_payload_digest(unsigned)
    checkpoint(cancellation)
    return ProteogenomicStateResult(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest=digest,
        sample_id=request.sample_id,
        solver=solver_diagnostics,
        node_states=node_states,
        kinase_states=kinase_states,
        external_kinase_comparison=external_comparison,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )


__all__ = ["InferenceConvergenceError", "infer_proteogenomic_state"]
