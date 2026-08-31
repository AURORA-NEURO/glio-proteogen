"""Deterministic inference for Migliozzi GBM functional-proteotype evidence.

The implementation deliberately separates three kinds of information:

* a constrained robust latent fit over exact Table 2d gene symbols;
* an independent competitive rank comparison with a joint stratified null; and
* source-cohort Table 2e pathways, which are returned as context only.

No pathway state, clinical subtype, cellular fraction, prognosis, or treatment
recommendation is inferred by this module.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Final, Literal, cast

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import (
    bootstrap_computational_digest,
    computational_request_digest,
    objective_trace_digest,
    permutation_computational_digest,
    result_payload_digest,
)
from .catalog import CatalogProtein, functional_proteotype_catalog
from .contracts import (
    AXIS_ORDER,
    MAX_JSON_SAFE_INTEGER,
    AblationKind,
    AnalysisSupport,
    AxisAblation,
    AxisClassification,
    AxisEvidence,
    AxisEvidenceCounts,
    ConstrainedAxisCoordinate,
    FunctionalProteotypeProvenance,
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    LatentInterval,
    ObjectiveTraceStep,
    ProteinDriver,
    ProteinEvidence,
    ProteinEvidenceState,
    RankComparison,
    SolverDiagnostics,
    SolverTermination,
    SourceCohortPathwayContext,
)
from .profile import CONSTANTS, algorithm_profile, random_stream_profile_digest
from .solver import (
    SolverConfiguration,
    SolverObservation,
    SolverOutcome,
    solve_constrained_latent,
)
from .statistics import PermutationRankResult, stratified_permutation_rank_test

_FLOAT: Final = np.float64
_ZERO_DIGEST: Final = "sha256:" + "0" * 64
_ACTIVE_STATES: Final = {
    ProteinEvidenceState.OBSERVED,
    ProteinEvidenceState.LEFT_CENSORED,
}
_LIMITATIONS: Final = (
    "Outputs quantify bulk-protein concordance with four source-selected CPTAC GBM proteotype signatures; they are not clinical subtype assignments.",
    "The four latent coordinates are relative, equality-constrained research axes and must not be interpreted as probabilities or cell fractions.",
    "Table 2e pathways are published cohort context only; pathway activity is not evaluated for the submitted sample because member-level pathway topology was not admitted.",
    "Observed effects are caller-standardized contrasts against the declared reference and are not absolute protein activation measurements.",
    "Left-censored evidence is retained as a one-sided upper bound; missing and unsupported evidence is ignored and never converted to a negative observation.",
    "Bootstrap intervals perturb caller-supplied standard errors independently and do not model batch effects, peptide covariance, tumor purity, or external calibration.",
    "Competitive rank evidence is an independent four-axis comparison against a deterministic source-rank-stratified permutation null, not a diagnostic test.",
    "Exact replay is scoped to the pinned Python 3.12.13, NumPy 2.5.2, and container runtime; cross-platform BLAS/LAPACK bit parity is not claimed.",
    "This deterministic result is research-use-only, non-prescriptive, and must not guide diagnosis, prognosis, treatment, or automated clinical action.",
)


@dataclass(frozen=True, slots=True)
class _MappedObservation:
    evidence: ProteinEvidence
    protein: CatalogProtein
    axis_index: int

    def solver_observation(self, *, value: float | None = None) -> SolverObservation:
        effect = self.evidence.standardized_effect if value is None else value
        standard_error = self.evidence.standard_error
        if effect is None or standard_error is None:
            raise AssertionError("only active evidence can enter the numerical solver")
        state: Literal["observed", "left_censored"] = (
            "observed" if self.evidence.state is ProteinEvidenceState.OBSERVED else "left_censored"
        )
        return SolverObservation(
            axis_index=self.axis_index,
            source_loading=self.protein.source_loading,
            state=state,
            value=effect,
            standard_error=standard_error,
            quality_weight=self.evidence.quality_weight,
        )


def _quantize(value: float) -> float:
    rounded = round(float(value), CONSTANTS.quantization_decimals)
    return 0.0 if rounded == 0.0 else rounded


def _digest_seed(material: str) -> int:
    raw = hashlib.sha256(material.encode("utf-8")).digest()[: CONSTANTS.random_seed_bytes]
    return int.from_bytes(raw, "big", signed=False) % (MAX_JSON_SAFE_INTEGER + 1)


def _solver_configuration() -> SolverConfiguration:
    return SolverConfiguration(
        huber_delta=CONSTANTS.huber_delta,
        standard_error_floor=CONSTANTS.standard_error_floor,
        axis_ridge=CONSTANTS.axis_ridge_penalty,
        intercept_ridge=CONSTANTS.intercept_ridge_penalty,
        damping=CONSTANTS.initial_damping,
        tolerance=CONSTANTS.coordinate_tolerance,
        gradient_tolerance=CONSTANTS.gradient_tolerance,
        max_iterations=CONSTANTS.maximum_solver_iterations,
        backtracking_factor=CONSTANTS.backtracking_factor,
        backtracking_steps=CONSTANTS.maximum_backtracking_steps,
        objective_increase_tolerance=CONSTANTS.objective_increase_tolerance,
    )


def _mapped_observations(
    request: FunctionalProteotypeRequest,
) -> tuple[tuple[_MappedObservation, ...], tuple[_MappedObservation, ...]]:
    catalog = functional_proteotype_catalog()
    axis_indices = {axis.value: index for index, axis in enumerate(AXIS_ORDER)}
    declared: list[_MappedObservation] = []
    active: list[_MappedObservation] = []
    for evidence in sorted(
        request.observations,
        key=lambda item: (item.gene_symbol, item.observation_id),
    ):
        protein = catalog.by_gene_symbol.get(evidence.gene_symbol)
        if protein is None:
            # The request contract permits only unresolved `unsupported` declarations.
            continue
        mapped = _MappedObservation(
            evidence=evidence,
            protein=protein,
            axis_index=axis_indices[protein.axis],
        )
        declared.append(mapped)
        if evidence.state in _ACTIVE_STATES:
            active.append(mapped)
    return tuple(declared), tuple(active)


def _solve(
    active: tuple[_MappedObservation, ...],
    configuration: SolverConfiguration,
    *,
    initial: npt.NDArray[np.float64] | None = None,
    cancellation: CancellationContext | None = None,
) -> SolverOutcome:
    return solve_constrained_latent(
        tuple(item.solver_observation() for item in active),
        configuration,
        initial=initial,
        cancellation=cancellation,
    )


def _quantized_axis_coordinates(
    values: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    first = tuple(_quantize(value) for value in values[:3])
    final = _quantize(-math.fsum(first))
    return first[0], first[1], first[2], final


def _empty_diagnostics(termination: SolverTermination) -> SolverDiagnostics:
    trace: tuple[ObjectiveTraceStep, ...] = ()
    return SolverDiagnostics(
        converged=False,
        termination=termination,
        iterations=0,
        intercept=0.0,
        axis_coordinates=tuple(
            ConstrainedAxisCoordinate(axis=axis, estimate=0.0) for axis in AXIS_ORDER
        ),
        sum_to_zero_residual=0.0,
        initial_objective=0.0,
        final_objective=0.0,
        final_gradient_norm=0.0,
        maximum_coordinate_change=0.0,
        objective_trace=trace,
        objective_trace_digest=objective_trace_digest(trace),
    )


def _diagnostics(outcome: SolverOutcome) -> SolverDiagnostics:
    coordinates = _quantized_axis_coordinates(outcome.axis_values)
    trace = tuple(
        ObjectiveTraceStep(
            iteration=item.iteration,
            baseline_objective=_quantize(item.baseline_objective),
            candidate_objective=_quantize(item.candidate_objective),
            accepted_objective=_quantize(item.accepted_objective),
            damping=_quantize(item.damping),
            accepted=item.accepted,
        )
        for item in outcome.objective_trace
    )
    initial_objective = trace[0].baseline_objective if trace else _quantize(outcome.objective)
    final_objective = trace[-1].accepted_objective if trace else initial_objective
    return SolverDiagnostics(
        converged=outcome.converged,
        termination=(
            SolverTermination.CONVERGED
            if outcome.converged
            else SolverTermination.MAXIMUM_ITERATIONS
        ),
        iterations=outcome.iterations,
        intercept=_quantize(outcome.intercept),
        axis_coordinates=tuple(
            ConstrainedAxisCoordinate(axis=axis, estimate=coordinates[index])
            for index, axis in enumerate(AXIS_ORDER)
        ),
        sum_to_zero_residual=sum(coordinates),
        initial_objective=initial_objective,
        final_objective=final_objective,
        final_gradient_norm=_quantize(outcome.final_gradient_norm),
        maximum_coordinate_change=_quantize(outcome.maximum_candidate_update),
        objective_trace=trace,
        objective_trace_digest=objective_trace_digest(trace),
    )


def _bootstrap(
    active: tuple[_MappedObservation, ...],
    configuration: SolverConfiguration,
    point: SolverOutcome,
    *,
    replicates: int,
    seed: int,
    cancellation: CancellationContext | None,
) -> npt.NDArray[np.float64]:
    rng = np.random.default_rng(seed)
    initial = np.asarray((point.intercept, *point.axis_values), dtype=_FLOAT)
    successful: list[tuple[float, float, float, float]] = []
    for replicate in range(replicates):
        if replicate % 8 == 0:
            checkpoint(cancellation)
        perturbed: list[SolverObservation] = []
        for item in active:
            standard_error = cast("float", item.evidence.standard_error)
            value = cast("float", item.evidence.standardized_effect) + float(
                rng.normal(0.0, standard_error)
            )
            perturbed.append(item.solver_observation(value=value))
        try:
            outcome = solve_constrained_latent(
                tuple(perturbed),
                configuration,
                initial=initial,
                cancellation=cancellation,
            )
        except FloatingPointError:
            continue
        if outcome.converged and all(math.isfinite(value) for value in outcome.axis_values):
            successful.append(outcome.axis_values)
    if not successful:
        return np.empty((0, 4), dtype=_FLOAT)
    return np.asarray(successful, dtype=_FLOAT)


def _rank_comparisons(
    active: tuple[_MappedObservation, ...],
    *,
    replicates: int,
    seed: int,
    cancellation: CancellationContext | None,
) -> tuple[
    RankComparison | None, RankComparison | None, RankComparison | None, RankComparison | None
]:
    observed = tuple(
        item for item in active if item.evidence.state is ProteinEvidenceState.OBSERVED
    )
    axis_counts = tuple(
        sum(item.axis_index == axis_index for item in observed) for axis_index in range(4)
    )
    if (
        any(count < CONSTANTS.minimum_rank_signature_proteins for count in axis_counts)
        or any(
            len(observed) - count < CONSTANTS.minimum_rank_background_proteins
            for count in axis_counts
        )
        or len(observed) < 2
    ):
        return None, None, None, None
    values = np.asarray(
        [cast("float", item.evidence.standardized_effect) for item in observed],
        dtype=_FLOAT,
    )
    if float(np.ptp(values)) == 0.0:
        return None, None, None, None
    axis_indices = np.asarray([item.axis_index for item in observed], dtype=np.int64)
    source_ranks = np.asarray([item.protein.source_rank for item in observed], dtype=np.int64)
    try:
        result = stratified_permutation_rank_test(
            values,
            axis_indices,
            source_ranks,
            replicates=replicates,
            seed=seed,
            cancellation=cancellation,
        )
    except ValueError:
        return None, None, None, None
    return _rank_contracts(result)


def _rank_contracts(
    result: PermutationRankResult,
) -> tuple[RankComparison, RankComparison, RankComparison, RankComparison]:
    rows = tuple(
        RankComparison(
            signature_observed_count=statistic.target_count,
            complement_observed_count=statistic.background_count,
            u_statistic=_quantize(statistic.u_statistic),
            rank_biserial=_quantize(statistic.rank_biserial),
            tie_correction=_quantize(statistic.tie_correction),
            null_standard_deviation=_quantize(result.null_standard_deviations[index]),
            empirical_p_value=_quantize(result.p_values[index]),
            q_value=_quantize(result.q_values[index]),
            permutation_replicates_used=result.replicates,
        )
        for index, statistic in enumerate(result.statistics)
    )
    return rows[0], rows[1], rows[2], rows[3]


def _axis_counts(
    axis_index: int,
    declared: tuple[_MappedObservation, ...],
) -> AxisEvidenceCounts:
    signature = tuple(item for item in declared if item.axis_index == axis_index)
    state_counts = {
        state: sum(item.evidence.state is state for item in signature)
        for state in ProteinEvidenceState
    }
    declared_count = len(signature)
    active_count = (
        state_counts[ProteinEvidenceState.OBSERVED]
        + state_counts[ProteinEvidenceState.LEFT_CENSORED]
    )
    observed_background = sum(
        item.axis_index != axis_index and item.evidence.state is ProteinEvidenceState.OBSERVED
        for item in declared
    )
    return AxisEvidenceCounts(
        declared_signature_proteins=declared_count,
        observed_signature_proteins=state_counts[ProteinEvidenceState.OBSERVED],
        left_censored_signature_proteins=state_counts[ProteinEvidenceState.LEFT_CENSORED],
        missing_signature_proteins=state_counts[ProteinEvidenceState.MISSING],
        unsupported_signature_proteins=state_counts[ProteinEvidenceState.UNSUPPORTED],
        unreported_signature_proteins=150 - declared_count,
        observed_background_proteins=observed_background,
        active_signature_fraction=active_count / 150.0,
    )


def _reliability(item: _MappedObservation) -> float:
    standard_error = cast("float", item.evidence.standard_error)
    return item.evidence.quality_weight / (
        standard_error * standard_error
        + CONSTANTS.standard_error_floor * CONSTANTS.standard_error_floor
    )


def _effective_sample_size(items: tuple[_MappedObservation, ...]) -> float:
    if not items:
        return 0.0
    weights = tuple(_reliability(item) for item in items)
    denominator = math.fsum(weight * weight for weight in weights)
    if denominator == 0.0:
        return 0.0
    return _quantize(math.fsum(weights) ** 2 / denominator)


def _classification_from_interval(lower: float, upper: float) -> AxisClassification:
    threshold = CONSTANTS.axis_classification_threshold
    if lower > threshold:
        return AxisClassification.SOURCE_ALIGNED
    if upper < -threshold:
        return AxisClassification.SOURCE_OPPOSED
    if lower >= -threshold and upper <= threshold:
        return AxisClassification.NEUTRAL
    return AxisClassification.INDETERMINATE


def _point_classification(value: float) -> AxisClassification:
    if value > CONSTANTS.axis_classification_threshold:
        return AxisClassification.SOURCE_ALIGNED
    if value < -CONSTANTS.axis_classification_threshold:
        return AxisClassification.SOURCE_OPPOSED
    return AxisClassification.NEUTRAL


def _interval(
    estimate: float,
    bootstrap: npt.NDArray[np.float64],
    axis_index: int,
) -> LatentInterval | None:
    if len(bootstrap) < CONSTANTS.minimum_interval_bootstrap_replicates:
        return None
    lower = _quantize(
        float(np.quantile(bootstrap[:, axis_index], CONSTANTS.interval_lower_quantile))
    )
    upper = _quantize(
        float(np.quantile(bootstrap[:, axis_index], CONSTANTS.interval_upper_quantile))
    )
    lower = min(lower, estimate)
    upper = max(upper, estimate)
    return LatentInterval(
        estimate=estimate,
        lower_bound=lower,
        upper_bound=upper,
        bootstrap_replicates_used=(
            len(bootstrap)
            if len(bootstrap) >= CONSTANTS.minimum_interval_bootstrap_replicates
            else 0
        ),
    )


def _stability(
    estimate: float,
    bootstrap: npt.NDArray[np.float64],
    axis_index: int,
) -> float:
    if len(bootstrap) == 0:
        return 0.0
    point_class = _point_classification(estimate)
    matches = sum(
        _point_classification(float(value)) is point_class for value in bootstrap[:, axis_index]
    )
    return _quantize(matches / len(bootstrap))


def _discordance(estimate: float, rank: RankComparison | None) -> float:
    if rank is None:
        return 0.0
    return _quantize(abs(math.tanh(estimate) - rank.rank_biserial) / 2.0)


def _top_drivers(
    axis_index: int,
    active: tuple[_MappedObservation, ...],
    *,
    intercept: float,
    estimate: float,
) -> tuple[ProteinDriver, ...]:
    candidates: list[tuple[float, int, ProteinDriver]] = []
    for item in active:
        if item.axis_index != axis_index:
            continue
        value = cast("float", item.evidence.standardized_effect)
        reliability = _reliability(item)
        fitted = intercept + item.protein.source_loading * estimate
        scale = math.sqrt(
            cast("float", item.evidence.standard_error) ** 2
            + CONSTANTS.standard_error_floor**2
        )
        if item.evidence.state is ProteinEvidenceState.LEFT_CENSORED and fitted <= value:
            continue
        residual = (value - fitted) / scale
        robust_score = min(max(residual, -CONSTANTS.huber_delta), CONSTANTS.huber_delta)
        signed = _quantize(
            item.protein.source_loading
            * item.evidence.quality_weight
            * robust_score
            / scale
        )
        driver = ProteinDriver(
            observation_id=item.evidence.observation_id,
            gene_symbol=item.protein.gene_symbol,
            source_protein_label=item.protein.source_protein_label,
            axis=AXIS_ORDER[axis_index],
            source_rank=item.protein.source_rank,
            source_rank_quartile=min(4, ((item.protein.source_rank - 1) // 38) + 1),
            source_mww_score=_quantize(item.protein.source_mww_score),
            evidence_state=item.evidence.state,
            value_role=(
                "observed_point"
                if item.evidence.state is ProteinEvidenceState.OBSERVED
                else "left_censored_upper_limit"
            ),
            standardized_effect=value,
            reliability_weight=_quantize(reliability),
            source_loading=_quantize(item.protein.source_loading),
            signed_contribution=signed,
            absolute_contribution=abs(signed),
        )
        candidates.append((driver.absolute_contribution, item.protein.source_rank, driver))
    candidates.sort(key=lambda row: (-row[0], row[1], row[2].gene_symbol))
    return tuple(row[2] for row in candidates[: CONSTANTS.top_driver_limit])


def _pathway_context(axis_index: int) -> tuple[SourceCohortPathwayContext, ...]:
    catalog = functional_proteotype_catalog()
    axis = AXIS_ORDER[axis_index]
    return tuple(
        SourceCohortPathwayContext(
            axis=axis,
            source_rank=item.source_rank,
            pathway_name=item.pathway,
            source_logit_nes=_quantize(item.logit_nes),
            source_p_value=item.p_value,
            source_q_value=item.q_value,
        )
        for item in catalog.source_cohort_pathway_context[axis.value][
            : CONSTANTS.pathway_context_limit
        ]
    )


def _coverage_gate(
    axis_items: tuple[_MappedObservation, ...],
) -> tuple[bool, str | None]:
    observed = sum(item.evidence.state is ProteinEvidenceState.OBSERVED for item in axis_items)
    active = len(axis_items)
    effective = _effective_sample_size(axis_items)
    failures: list[str] = []
    if active < CONSTANTS.supported_minimum_active_proteins:
        failures.append("active-protein coverage")
    if observed < CONSTANTS.supported_minimum_observed_proteins:
        failures.append("observed-protein coverage")
    if active / 150.0 < CONSTANTS.supported_minimum_active_fraction:
        failures.append("source-signature fraction")
    if effective < CONSTANTS.supported_minimum_effective_sample_size:
        failures.append("effective sample size")
    if failures:
        return False, "Ablation refit has limited " + ", ".join(failures) + "."
    return True, None


def _one_ablation(
    *,
    axis_index: int,
    kind: AblationKind,
    target: str,
    removed_symbols: frozenset[str],
    baseline_estimate: float,
    active: tuple[_MappedObservation, ...],
    configuration: SolverConfiguration,
    cancellation: CancellationContext | None,
) -> AxisAblation:
    remaining = tuple(
        item
        for item in active
        if not (item.axis_index == axis_index and item.protein.gene_symbol in removed_symbols)
    )
    remaining_axis = tuple(item for item in remaining if item.axis_index == axis_index)
    removed_count = sum(
        item.axis_index == axis_index and item.protein.gene_symbol in removed_symbols
        for item in active
    )
    if removed_count == 0:
        raise AssertionError("ablation must remove active evidence")
    if len(remaining_axis) < CONSTANTS.exploratory_minimum_active_proteins:
        return AxisAblation(
            kind=kind,
            target=target,
            proteins_removed=removed_count,
            support_after_ablation=AnalysisSupport.ABSTAINED,
            classification_after_ablation=AxisClassification.NOT_ESTIMABLE,
            reason="Fewer than the exploratory minimum active signature proteins remain.",
        )
    try:
        outcome = _solve(remaining, configuration, cancellation=cancellation)
    except FloatingPointError:
        outcome = None
    if outcome is None or not outcome.converged:
        return AxisAblation(
            kind=kind,
            target=target,
            proteins_removed=removed_count,
            support_after_ablation=AnalysisSupport.ABSTAINED,
            classification_after_ablation=AxisClassification.NOT_ESTIMABLE,
            reason="The constrained robust ablation refit did not converge.",
        )
    ablated = _quantized_axis_coordinates(outcome.axis_values)[axis_index]
    strong, reason = _coverage_gate(remaining_axis)
    support = AnalysisSupport.SUPPORTED if strong else AnalysisSupport.LIMITED
    return AxisAblation(
        kind=kind,
        target=target,
        proteins_removed=removed_count,
        support_after_ablation=support,
        baseline_estimate=baseline_estimate,
        ablated_estimate=ablated,
        estimate_delta=_quantize(ablated - baseline_estimate),
        classification_after_ablation=AxisClassification.INDETERMINATE,
        reason=reason,
    )


def _ablations(
    axis_index: int,
    active: tuple[_MappedObservation, ...],
    drivers: tuple[ProteinDriver, ...],
    *,
    baseline_estimate: float,
    configuration: SolverConfiguration,
    cancellation: CancellationContext | None,
) -> tuple[AxisAblation, ...]:
    axis_items = tuple(item for item in active if item.axis_index == axis_index)
    specifications: list[tuple[AblationKind, str, frozenset[str]]]
    quartiles = sorted({min(4, ((item.protein.source_rank - 1) // 38) + 1) for item in axis_items})
    specifications = [
        (
            AblationKind.SOURCE_RANK_QUARTILE,
            f"source_rank_quartile:{quartile}",
            frozenset(
                item.protein.gene_symbol
                for item in axis_items
                if min(4, ((item.protein.source_rank - 1) // 38) + 1) == quartile
            ),
        )
        for quartile in quartiles
    ]
    for state in (ProteinEvidenceState.OBSERVED, ProteinEvidenceState.LEFT_CENSORED):
        symbols = frozenset(
            item.protein.gene_symbol for item in axis_items if item.evidence.state is state
        )
        if symbols:
            specifications.append(
                (AblationKind.EVIDENCE_STATE, f"evidence_state:{state.value}", symbols)
            )
    specifications.extend(
        (
            AblationKind.TOP_DRIVER,
            f"top_driver:{driver.gene_symbol}",
            frozenset((driver.gene_symbol,)),
        )
        for driver in drivers
    )
    return tuple(
        _one_ablation(
            axis_index=axis_index,
            kind=kind,
            target=target,
            removed_symbols=symbols,
            baseline_estimate=baseline_estimate,
            active=active,
            configuration=configuration,
            cancellation=cancellation,
        )
        for kind, target, symbols in specifications
    )


def _support_reasons(
    *,
    counts: AxisEvidenceCounts,
    effective_sample_size: float,
    rank: RankComparison | None,
    interval: LatentInterval | None,
    bootstrap_successes: int,
    requested_bootstraps: int,
) -> tuple[AnalysisSupport, tuple[str, ...]]:
    active = counts.observed_signature_proteins + counts.left_censored_signature_proteins
    if active < CONSTANTS.exploratory_minimum_active_proteins:
        return AnalysisSupport.ABSTAINED, (
            "Fewer than the exploratory minimum active source-signature proteins were supplied.",
        )
    if interval is None:
        return AnalysisSupport.ABSTAINED, (
            "Too few deterministic bootstrap refits converged to construct the locked interval.",
        )
    reasons: list[str] = []
    if active < CONSTANTS.supported_minimum_active_proteins:
        reasons.append("Active source-signature protein coverage is below the support gate.")
    if counts.observed_signature_proteins < CONSTANTS.supported_minimum_observed_proteins:
        reasons.append("Observed source-signature protein coverage is below the support gate.")
    if counts.active_signature_fraction < CONSTANTS.supported_minimum_active_fraction:
        reasons.append("Active source-signature fraction is below the support gate.")
    if effective_sample_size < CONSTANTS.supported_minimum_effective_sample_size:
        reasons.append("Reliability-weighted effective sample size is below the support gate.")
    if bootstrap_successes / requested_bootstraps < CONSTANTS.minimum_bootstrap_success_fraction:
        reasons.append("Bootstrap convergence is below the profile success fraction.")
    if rank is None:
        reasons.append("Independent competitive rank evidence is not estimable.")
    else:
        if rank.q_value > CONSTANTS.rank_q_threshold:
            reasons.append("Competitive rank evidence does not pass the fixed-family q-value gate.")
        if interval.estimate * rank.rank_biserial < 0.0:
            reasons.append("Latent and competitive-rank evidence have opposing directions.")
    if reasons:
        return AnalysisSupport.LIMITED, tuple(reasons[:8])
    return AnalysisSupport.SUPPORTED, ()


def _axis_evidence(
    *,
    axis_index: int,
    declared: tuple[_MappedObservation, ...],
    active: tuple[_MappedObservation, ...],
    diagnostics: SolverDiagnostics,
    bootstrap: npt.NDArray[np.float64],
    ranks: tuple[
        RankComparison | None,
        RankComparison | None,
        RankComparison | None,
        RankComparison | None,
    ],
    requested_bootstraps: int,
    configuration: SolverConfiguration,
    cancellation: CancellationContext | None,
) -> AxisEvidence:
    axis = AXIS_ORDER[axis_index]
    counts = _axis_counts(axis_index, declared)
    axis_items = tuple(item for item in active if item.axis_index == axis_index)
    effective = _effective_sample_size(axis_items)
    pathway_context = _pathway_context(axis_index)
    if not diagnostics.converged:
        return AxisEvidence(
            axis=axis,
            support=AnalysisSupport.ABSTAINED,
            classification=AxisClassification.NOT_ESTIMABLE,
            evidence_counts=counts,
            effective_sample_size=effective,
            stability=0.0,
            discordance=0.0,
            source_cohort_pathway_context=pathway_context,
            abstention_reasons=(
                "The equality-constrained robust solver did not converge; no axis estimate is accepted.",
            ),
        )
    estimate = diagnostics.axis_coordinates[axis_index].estimate
    interval = _interval(estimate, bootstrap, axis_index)
    support, reasons = _support_reasons(
        counts=counts,
        effective_sample_size=effective,
        rank=ranks[axis_index],
        interval=interval,
        bootstrap_successes=len(bootstrap),
        requested_bootstraps=requested_bootstraps,
    )
    if support is AnalysisSupport.ABSTAINED or interval is None:
        return AxisEvidence(
            axis=axis,
            support=AnalysisSupport.ABSTAINED,
            classification=AxisClassification.NOT_ESTIMABLE,
            evidence_counts=counts,
            effective_sample_size=effective,
            stability=0.0,
            discordance=0.0,
            source_cohort_pathway_context=pathway_context,
            abstention_reasons=reasons,
        )
    drivers = _top_drivers(
        axis_index,
        active,
        intercept=diagnostics.intercept,
        estimate=estimate,
    )
    ablations = _ablations(
        axis_index,
        active,
        drivers,
        baseline_estimate=estimate,
        configuration=configuration,
        cancellation=cancellation,
    )
    return AxisEvidence(
        axis=axis,
        support=support,
        classification=_classification_from_interval(interval.lower_bound, interval.upper_bound),
        latent=interval,
        rank=ranks[axis_index],
        evidence_counts=counts,
        effective_sample_size=effective,
        stability=_stability(estimate, bootstrap, axis_index),
        discordance=_discordance(estimate, ranks[axis_index]),
        top_drivers=drivers,
        ablations=ablations,
        source_cohort_pathway_context=pathway_context,
        abstention_reasons=reasons,
    )


def _source_text(source: dict[str, object], field: str) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"functional-proteotype source.{field} is invalid")
    return value


def analyze_functional_proteotype(
    request: FunctionalProteotypeRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> FunctionalProteotypeResult:
    """Infer four research-only GBM source-axis concordance coordinates."""

    checkpoint(cancellation)
    profile = algorithm_profile()
    random_profile_digest = random_stream_profile_digest(profile)
    request_digest = request.request_digest
    computational_digest = computational_request_digest(
        request,
        random_profile_digest=random_profile_digest,
    )
    bootstrap_seed = _digest_seed(
        bootstrap_computational_digest(
            request,
            random_profile_digest=random_profile_digest,
        )
    )
    permutation_seed = _digest_seed(
        permutation_computational_digest(
            request,
            random_profile_digest=random_profile_digest,
        )
    )
    declared, active = _mapped_observations(request)
    configuration = _solver_configuration()
    point: SolverOutcome | None = None
    if not active:
        diagnostics = _empty_diagnostics(SolverTermination.INSUFFICIENT_EVIDENCE)
    else:
        try:
            point = _solve(active, configuration, cancellation=cancellation)
            diagnostics = _diagnostics(point)
        except FloatingPointError:
            diagnostics = _empty_diagnostics(SolverTermination.NUMERICAL_GUARD)

    if point is not None and point.converged:
        bootstrap = _bootstrap(
            active,
            configuration,
            point,
            replicates=request.bootstrap_replicates,
            seed=bootstrap_seed,
            cancellation=cancellation,
        )
    else:
        bootstrap = np.empty((0, 4), dtype=_FLOAT)
    ranks = _rank_comparisons(
        active,
        replicates=request.permutation_replicates,
        seed=permutation_seed,
        cancellation=cancellation,
    )
    axes = tuple(
        _axis_evidence(
            axis_index=index,
            declared=declared,
            active=active,
            diagnostics=diagnostics,
            bootstrap=bootstrap,
            ranks=ranks,
            requested_bootstraps=request.bootstrap_replicates,
            configuration=configuration,
            cancellation=cancellation,
        )
        for index in range(4)
    )
    catalog = functional_proteotype_catalog()
    provenance = FunctionalProteotypeProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        computational_digest=computational_digest,
        catalog_content_digest=catalog.content_digest,
        catalog_artifact_digest=catalog.artifact_digest,
        source_workbook_digest=_source_text(catalog.source, "source_sha256"),
        signature_catalog_digest=catalog.signature_catalog_digest,
        pathway_catalog_digest=catalog.pathway_catalog_digest,
        engine_source_digest=profile.engine_source_digest,
        bootstrap_seed=bootstrap_seed,
        permutation_seed=permutation_seed,
        bootstrap_replicates_used=len(bootstrap),
        permutation_replicates_used=(
            request.permutation_replicates if any(rank is not None for rank in ranks) else 0
        ),
        observation_source_digests=tuple(
            sorted({item.provenance_digest for item in request.observations})
        ),
        source_article_title=_source_text(catalog.source, "article_title"),
        source_article_authors=_source_text(catalog.source, "article_authors"),
        source_url=_source_text(catalog.source, "source_url"),
        source_transformation_notice=_source_text(catalog.source, "transformation_notice"),
    )
    unsigned = FunctionalProteotypeResult.model_construct(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        sample_id=request.sample_id,
        effect_reference_id=request.effect_reference_id,
        solver=diagnostics,
        axis_evidence=axes,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    result_digest = result_payload_digest(unsigned)
    result = FunctionalProteotypeResult(
        profile_digest=profile.profile_digest,
        request_digest=request_digest,
        result_digest=result_digest,
        sample_id=request.sample_id,
        effect_reference_id=request.effect_reference_id,
        solver=diagnostics,
        axis_evidence=axes,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    checkpoint(cancellation)
    return result


__all__ = ["analyze_functional_proteotype"]
