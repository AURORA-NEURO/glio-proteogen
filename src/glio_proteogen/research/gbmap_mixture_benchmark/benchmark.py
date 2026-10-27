"""Explicit-policy scoring of one privately reproduced development fold.

Terminal precedence is source zero, selected zero, selected int64 depth,
no reference columns, conditioning, solver exception, invalid trace, then
nonconvergence/KKT. Omission withholds columns and reclassifies truth only;
features, background and observed counts remain fixed. No policy is selected.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np
import numpy.typing as npt

from glio_proteogen.research.gbmap_deconvolution.errors import GbmapNumericalError
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.simplex import (
    SimplexSolverConfiguration,
    reference_signature_condition_number,
    solve_reference_mixture,
    verify_objective_trace,
)
from glio_proteogen.research.gbmap_held_mixture_truth import EmpiricalMixtureCase
from glio_proteogen.research.gbmap_selected_fold_replay import (
    SelectedFoldReplayReceipt,
    SelectedFoldReplayResult,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .contracts import (
    ROUNDING_TOLERANCE,
    SOLVER_CONFIGURATION_DIGEST,
    TERMINAL_REASONS,
    LabelPointMetrics,
    MixtureBenchmarkError,
    MixtureBenchmarkReceipt,
    MixturePointPolicy,
    PolicyScenarioResult,
    TerminalCount,
    TerminalReason,
    VisibilityCounts,
)

FloatArray = npt.NDArray[np.float64]
_INT64_MAX = int(np.iinfo(np.int64).max)


def _visibility(cases: tuple[EmpiricalMixtureCase, ...], index: int) -> VisibilityCounts:
    source_zero = sum(case.source_label_count_mass[index] == 0 for case in cases)
    selected_positive = sum(case.selected_label_count_mass[index] > 0 for case in cases)
    return VisibilityCounts(
        source_zero=source_zero,
        source_positive_selected_zero=len(cases) - source_zero - selected_positive,
        selected_positive=selected_positive,
    )


def _conditioning_rejected(matrix: FloatArray, config: SimplexSolverConfiguration) -> bool:
    """Apply original signature gates; a failed precheck SVD also rejects safely."""
    try:
        condition = reference_signature_condition_number(matrix)
        if matrix.shape[1] > 1:
            smallest = float(np.linalg.svd(matrix[:, :-1] - matrix[:, [-1]], compute_uv=False)[-1])
            return (
                not math.isfinite(condition)
                or condition > config.signature_condition_limit
                or smallest < config.minimum_signature_contrast
            )
    except (ValueError, np.linalg.LinAlgError):
        return True
    return False


def _score_case(  # noqa: PLR0911 - explicit terminal precedence is the count-conservation contract.
    case: EmpiricalMixtureCase,
    matrix: FloatArray,
    background: FloatArray,
    policy: MixturePointPolicy,
    omitted: tuple[str, ...],
    *,
    conditioning_rejected: bool,
    configuration: SimplexSolverConfiguration,
    cancellation: CancellationContext | None,
) -> TerminalReason | tuple[tuple[float, ...], float, float]:
    if case.source_total_count_mass == 0:
        return "zero_source_count_depth"
    if case.selected_total_count_mass == 0:
        return "zero_selected_count_depth"
    if sum(int(value) for value in case.selected_counts) > _INT64_MAX:
        return "selected_depth_exceeds_int64"
    if matrix.shape[1] == 0:
        return "no_reference_columns"
    if conditioning_rejected:
        return "signature_conditioning_rejected"
    try:
        solution = solve_reference_mixture(
            case.selected_counts,
            matrix,
            background,
            concentration=policy.concentration,
            lambda_mass=policy.lambda_mass,
            lambda_shape=policy.lambda_shape,
            initial_unknown_mass=policy.initial_unknown_mass,
            configuration=configuration,
            cancellation=cancellation,
        )
    except (GbmapNumericalError, FloatingPointError, OverflowError, np.linalg.LinAlgError):
        return "solver_numerical_failure"
    except (TypeError, ValueError):
        return "solver_rejected"
    if not verify_objective_trace(solution):
        return "solver_trace_invalid"
    if not solution.converged or solution.kkt_residual > configuration.kkt_tolerance:
        return "solver_not_converged"
    truth = case.selected_rna_fractions
    view = case.reclassify(omitted)
    if truth is None or view.selected_unknown_fraction is None:
        raise MixtureBenchmarkError("positive selected depth requires finite truth")
    indices = tuple(PRODUCTION_SOURCE_LABELS.index(label) for label in view.remaining_known_labels)
    if solution.known_rna_weights.shape != (len(indices),):
        return "solver_trace_invalid"
    errors = tuple(
        float(weight) - float(truth[index])
        for weight, index in zip(solution.known_rna_weights, indices, strict=True)
    )
    unknown_error = solution.unknown_mass - float(view.selected_unknown_fraction)
    tv = 0.5 * math.fsum((*map(abs, errors), abs(unknown_error)))
    # Only tolerate the declared float64 simplex-closure roundoff; never clip a
    # substantive failure, error, prediction or missing observation.
    if 1.0 < tv <= 1.0 + ROUNDING_TOLERANCE:
        tv = 1.0
    if not math.isfinite(tv) or not 0.0 <= tv <= 1.0:
        return "solver_numerical_failure"
    return errors, unknown_error, tv


def _scenario(
    context: SelectedFoldReplayResult,
    policy: MixturePointPolicy,
    omitted: tuple[str, ...],
    configuration: SimplexSolverConfiguration,
    cancellation: CancellationContext | None,
) -> PolicyScenarioResult:
    columns = tuple(
        index for index, label in enumerate(context.known_labels) if label not in omitted
    )
    remaining = tuple(label for label in context.known_labels if label not in omitted)
    matrix = context.signatures[:, columns]
    rejected = bool(columns) and _conditioning_rejected(matrix, configuration)
    terminal: Counter[TerminalReason] = Counter()
    scored_cases: list[EmpiricalMixtureCase] = []
    errors: list[tuple[float, ...]] = []
    unknown_errors: list[float] = []
    tvs: list[float] = []
    for case in context.held_truth.cases:
        checkpoint(cancellation)
        result = _score_case(
            case,
            matrix,
            context.background,
            policy,
            omitted,
            conditioning_rejected=rejected,
            configuration=configuration,
            cancellation=cancellation,
        )
        if isinstance(result, str):
            terminal[result] += 1
        else:
            error, unknown_error, tv = result
            scored_cases.append(case)
            errors.append(error)
            unknown_errors.append(unknown_error)
            tvs.append(tv)
    scored = tuple(scored_cases)
    count = len(scored)
    labels: list[LabelPointMetrics] = []
    for index, label in enumerate(PRODUCTION_SOURCE_LABELS):
        modeled = label in remaining
        position = remaining.index(label) if modeled else None
        values = tuple(row[position] for row in errors) if position is not None else ()
        labels.append(
            LabelPointMetrics(
                modeled_label=label,
                modeled=modeled,
                mean_signed_error=math.fsum(values) / count if count and modeled else None,
                mean_absolute_error=math.fsum(map(abs, values)) / count
                if count and modeled
                else None,
                offered_visibility=_visibility(context.held_truth.cases, index),
                scored_visibility=_visibility(scored, index),
            )
        )
    return PolicyScenarioResult(
        policy=policy,
        omitted_labels=omitted,
        offered_case_count=len(context.held_truth.cases),
        scored_case_count=count,
        terminal_counts=tuple(
            TerminalCount(reason=reason, count=terminal[reason]) for reason in TERMINAL_REASONS
        ),
        mean_total_variation=math.fsum(tvs) / count if count else None,
        mean_unknown_signed_error=math.fsum(unknown_errors) / count if count else None,
        mean_unknown_absolute_error=math.fsum(map(abs, unknown_errors)) / count if count else None,
        labels=tuple(labels),
    )


def score_replayed_fold(
    context: SelectedFoldReplayResult,
    policies: tuple[MixturePointPolicy, ...],
    *,
    omissions: tuple[tuple[str, ...], ...] = (),
    cancellation: CancellationContext | None = None,
) -> MixtureBenchmarkReceipt:
    """Fit mixture points without training references, selecting or calibrating.

    The context must come from the private selected-fold producer. This API
    accepts neither caller-owned signature requests nor prepared-fold models.
    Its summary reports errors conditional on scored support, not independence
    of repeated donor-fold occurrences or unbiased population performance.
    """
    if type(context) is not SelectedFoldReplayResult:
        raise MixtureBenchmarkError("point scoring requires a private reproduced fold context")
    if (
        type(policies) is not tuple
        or not 1 <= len(policies) <= 64
        or any(type(policy) is not MixturePointPolicy for policy in policies)
        or type(omissions) is not tuple
        or len(omissions) > 20
    ):
        raise MixtureBenchmarkError("explicit bounded policy and omission tuples are required")
    validated = tuple(MixturePointPolicy.model_validate(policy) for policy in policies)
    if (
        len({policy.sort_key for policy in validated}) != len(validated)
        or any(
            type(omitted) is not tuple
            or not omitted
            or any(type(label) is not str for label in omitted)
            or omitted != tuple(sorted(set(omitted)))
            or set(omitted) - set(context.known_labels)
            for omitted in omissions
        )
        or len(omissions) != len(set(omissions))
    ):
        raise MixtureBenchmarkError(
            "unique policies and groups with canonical inner labels are required"
        )
    checked = tuple(sorted(validated, key=lambda policy: policy.sort_key))
    checked_omissions = tuple(sorted(omissions))
    receipt = SelectedFoldReplayReceipt.model_validate(context.receipt)
    if (
        context.held_truth.receipt != receipt.held_truth
        or context.signatures.shape != (receipt.selected_feature_count, len(receipt.known_labels))
        or context.background.shape != (receipt.selected_feature_count,)
        or any(
            type(case) is not EmpiricalMixtureCase
            or case.selected_counts.shape != (receipt.selected_feature_count,)
            or case.reclassify().remaining_known_labels != receipt.known_labels
            for case in context.held_truth.cases
        )
    ):
        raise MixtureBenchmarkError("private held truth differs from its reproduced context")
    checkpoint(cancellation)
    configuration = SimplexSolverConfiguration()
    results = tuple(
        _scenario(context, policy, omitted, configuration, cancellation)
        for policy in checked
        for omitted in ((), *checked_omissions)
    )
    return MixtureBenchmarkReceipt(
        context_receipt=receipt,
        policies=checked,
        omissions=checked_omissions,
        solver_configuration_digest=SOLVER_CONFIGURATION_DIGEST,
        results=results,
    )
