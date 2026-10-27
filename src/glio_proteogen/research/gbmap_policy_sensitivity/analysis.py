"""Casewise policy replay with full parent aggregate reconstruction.

Only transient case ordinals connect policies. Neither masks nor individual
outcomes survive in the returned receipt. Equality of the original aggregate
receipt does not prove equality of its unrecorded per-case first-pass outcomes.
"""

from __future__ import annotations

import math
from collections import Counter

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_deconvolution.simplex import SimplexSolverConfiguration
from glio_proteogen.research.gbmap_held_mixture_truth import EmpiricalMixtureCase
from glio_proteogen.research.gbmap_mixture_benchmark import (
    SOLVER_CONFIGURATION_DIGEST,
    TERMINAL_REASONS,
    LabelPointMetrics,
    MixtureBenchmarkPlan,
    MixtureBenchmarkReceipt,
    MixturePointPolicy,
    PolicyScenarioResult,
    TerminalCount,
    VisibilityCounts,
)
from glio_proteogen.research.gbmap_mixture_benchmark import benchmark as point_engine
from glio_proteogen.research.gbmap_mixture_benchmark.contracts import TerminalReason
from glio_proteogen.research.gbmap_selected_fold_replay import (
    SelectedFoldReplayReceipt,
    SelectedFoldReplayResult,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .contracts import (
    MatchedPolicyMetrics,
    MatchedPolicySensitivityReceipt,
    PolicySensitivityError,
    ScenarioMatchedSupport,
)

_Scored = tuple[tuple[float, ...], float, float]
_Outcome = TerminalReason | _Scored


def _visibility(cases: tuple[EmpiricalMixtureCase, ...], index: int) -> VisibilityCounts:
    zero = sum(case.source_label_count_mass[index] == 0 for case in cases)
    positive = sum(case.selected_label_count_mass[index] > 0 for case in cases)
    return VisibilityCounts(
        source_zero=zero,
        source_positive_selected_zero=len(cases) - zero - positive,
        selected_positive=positive,
    )


def _metrics(
    cases: tuple[EmpiricalMixtureCase, ...],
    remaining: tuple[str, ...],
    outcomes: tuple[_Outcome, ...],
    indices: tuple[int, ...],
) -> tuple[float | None, float | None, float | None, tuple[LabelPointMetrics, ...]]:
    scored = tuple(cases[index] for index in indices)
    values = tuple(outcomes[index] for index in indices)
    if any(isinstance(value, str) for value in values):
        raise PolicySensitivityError("common metrics require successful casewise outcomes")
    errors = tuple(value for value in values if not isinstance(value, str))
    count = len(errors)
    labels: list[LabelPointMetrics] = []
    for index, label in enumerate(PRODUCTION_SOURCE_LABELS):
        modeled = label in remaining
        position = remaining.index(label) if modeled else None
        error = tuple(row[0][position] for row in errors) if position is not None else ()
        labels.append(
            LabelPointMetrics(
                modeled_label=label,
                modeled=modeled,
                mean_signed_error=math.fsum(error) / count if count and modeled else None,
                mean_absolute_error=math.fsum(abs(value) for value in error) / count
                if count and modeled
                else None,
                offered_visibility=_visibility(cases, index),
                scored_visibility=_visibility(scored, index),
            )
        )
    return (
        math.fsum(row[2] for row in errors) / count if count else None,
        math.fsum(row[1] for row in errors) / count if count else None,
        math.fsum(abs(row[1]) for row in errors) / count if count else None,
        tuple(labels),
    )


def _original_result(
    cases: tuple[EmpiricalMixtureCase, ...],
    policy: MixturePointPolicy,
    omitted: tuple[str, ...],
    remaining: tuple[str, ...],
    outcomes: tuple[_Outcome, ...],
) -> PolicyScenarioResult:
    accepted = tuple(
        index for index, outcome in enumerate(outcomes) if not isinstance(outcome, str)
    )
    terminal: Counter[TerminalReason] = Counter(
        outcome for outcome in outcomes if isinstance(outcome, str)
    )
    tv, bias, mae, labels = _metrics(cases, remaining, outcomes, accepted)
    return PolicyScenarioResult(
        policy=policy,
        omitted_labels=omitted,
        offered_case_count=len(cases),
        scored_case_count=len(accepted),
        terminal_counts=tuple(
            TerminalCount(reason=reason, count=terminal[reason]) for reason in TERMINAL_REASONS
        ),
        mean_total_variation=tv,
        mean_unknown_signed_error=bias,
        mean_unknown_absolute_error=mae,
        labels=labels,
    )


def _scenario(
    context: SelectedFoldReplayResult,
    policies: tuple[MixturePointPolicy, ...],
    omitted: tuple[str, ...],
    cancellation: CancellationContext | None,
) -> tuple[tuple[PolicyScenarioResult, ...], ScenarioMatchedSupport]:
    cases = context.held_truth.cases
    columns = tuple(
        index for index, label in enumerate(context.known_labels) if label not in omitted
    )
    remaining = tuple(label for label in context.known_labels if label not in omitted)
    matrix = context.signatures[:, columns]
    config = SimplexSolverConfiguration()
    rejected = bool(columns) and point_engine._conditioning_rejected(matrix, config)
    outcome_rows: list[tuple[_Outcome, ...]] = []
    originals: list[PolicyScenarioResult] = []
    for policy in policies:
        collected: list[_Outcome] = []
        for case in cases:
            checkpoint(cancellation)
            collected.append(
                point_engine._score_case(
                    case,
                    matrix,
                    context.background,
                    policy,
                    omitted,
                    conditioning_rejected=rejected,
                    configuration=config,
                    cancellation=cancellation,
                )
            )
        row = tuple(collected)
        outcome_rows.append(row)
        originals.append(_original_result(cases, policy, omitted, remaining, row))
    success_counts = tuple(
        sum(not isinstance(row[index], str) for row in outcome_rows) for index in range(len(cases))
    )
    common = tuple(index for index, count in enumerate(success_counts) if count == len(policies))
    matched: list[MatchedPolicyMetrics] = []
    for policy, outcomes, original in zip(policies, outcome_rows, originals, strict=True):
        tv, bias, mae, labels = _metrics(cases, remaining, outcomes, common)
        matched.append(
            MatchedPolicyMetrics(
                policy=policy,
                original_scored_case_count=original.scored_case_count,
                excluded_from_common_case_count=original.scored_case_count - len(common),
                mean_total_variation=tv,
                mean_unknown_signed_error=bias,
                mean_unknown_absolute_error=mae,
                labels=labels,
            )
        )
    spreads: list[float] = []
    for index in common:
        # Same-case unknown truth cancels: error range equals mass range up to
        # finite-float subtraction roundoff. No mass/error vector is exported.
        common_outcomes = tuple(row[index] for row in outcome_rows)
        errors = tuple(outcome[1] for outcome in common_outcomes if not isinstance(outcome, str))
        spreads.append(max(errors) - min(errors))
    result = ScenarioMatchedSupport(
        omitted_labels=omitted,
        offered_case_count=len(cases),
        all_policy_scored_case_count=len(common),
        some_policy_scored_case_count=sum(0 < count < len(policies) for count in success_counts),
        no_policy_scored_case_count=sum(count == 0 for count in success_counts),
        mean_unknown_mass_spread=math.fsum(spreads) / len(common) if common else None,
        max_unknown_mass_spread=max(spreads) if common else None,
        policies=tuple(matched),
    )
    return tuple(originals), result


def score_matched_policy_sensitivity(
    context: SelectedFoldReplayResult,
    plan: MixtureBenchmarkPlan,
    *,
    parent_benchmark: MixtureBenchmarkReceipt,
    cancellation: CancellationContext | None = None,
) -> MatchedPolicySensitivityReceipt:
    """Replay all policies, require exact parent aggregates, and compare common cases.

    No reference training, policy selection, threshold calibration or independent
    empirical-unit claim occurs. A matching parent receipt does not authenticate
    its unretained first-pass masks; intersection membership comes from this new
    unchanged-kernel replay. No private case outcomes survive the return boundary.
    """
    if (
        type(context) is not SelectedFoldReplayResult
        or type(plan) is not MixtureBenchmarkPlan
        or type(parent_benchmark) is not MixtureBenchmarkReceipt
    ):
        raise PolicySensitivityError("sensitivity requires exact replay, plan and parent types")
    checked_plan = MixtureBenchmarkPlan.model_validate(plan)
    parent = MixtureBenchmarkReceipt.model_validate(parent_benchmark)
    receipt = SelectedFoldReplayReceipt.model_validate(context.receipt)
    policies = tuple(sorted(checked_plan.policies, key=lambda policy: policy.sort_key))
    omissions = tuple(sorted(checked_plan.omissions))
    if (
        receipt != parent.context_receipt
        or policies != parent.policies
        or omissions != parent.omissions
        or context.held_truth.receipt != receipt.held_truth
        or context.signatures.shape != (receipt.selected_feature_count, len(receipt.known_labels))
        or context.background.shape != (receipt.selected_feature_count,)
        or any(
            type(case) is not EmpiricalMixtureCase
            or case.selected_counts.shape != (receipt.selected_feature_count,)
            or case.reclassify().remaining_known_labels != receipt.known_labels
            for case in context.held_truth.cases
        )
    ):
        raise PolicySensitivityError("parent context or policy plan differs from replay")
    checkpoint(cancellation)
    original_by_key: dict[
        tuple[tuple[float, float, float, float], tuple[str, ...]], PolicyScenarioResult
    ] = {}
    scenarios: list[ScenarioMatchedSupport] = []
    for omitted in ((), *omissions):
        originals, matched = _scenario(context, policies, omitted, cancellation)
        for original in originals:
            original_by_key[(original.policy.sort_key, omitted)] = original
        scenarios.append(matched)
    reconstructed = MixtureBenchmarkReceipt(
        context_receipt=receipt,
        policies=policies,
        omissions=omissions,
        solver_configuration_digest=SOLVER_CONFIGURATION_DIGEST,
        results=tuple(
            original_by_key[(policy.sort_key, omitted)]
            for policy in policies
            for omitted in ((), *omissions)
        ),
    )
    if canonical_json_bytes(reconstructed) != canonical_json_bytes(parent):
        raise PolicySensitivityError("casewise replay differs from the full original aggregate")
    checkpoint(cancellation)
    return MatchedPolicySensitivityReceipt(parent_benchmark=parent, scenarios=tuple(scenarios))
