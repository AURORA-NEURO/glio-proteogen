"""Deterministic, replay-bound M10-05 mechanism integration runtime."""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from math import exp
from typing import Final

from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m10_05 import (
    M1005_CONTRACT_VERSION,
    M1005_EVIDENCE_CLAIM,
    M1005_PARENT,
    ConstraintAblation,
    ConstraintAwareEstimate,
    ConstraintEvaluation,
    ConstraintEvaluationOutcome,
    ConstraintHardness,
    ConstraintIntegrationStatus,
    FeatureObservation,
    FeatureObservationState,
    GliomaConstraintProgram,
    GliomaConstraintProgramState,
    IntegrateProteinRnaConstraintsRequest,
    ProteinRnaConstraintIntegrationResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteinRnaConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaConstraintIntegrationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_TRUE_EXPRESSIONS: Final = frozenset({"true", "always_true", "satisfied", "x >= 0", "1 == 1"})
_FALSE_EXPRESSIONS: Final = frozenset({"false", "always_false", "violated", "x < 0", "0 == 1"})
_NUMERIC_EXPRESSION = re.compile(
    r"^(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{0,127})\s*"
    r"(?P<operator>==|>=|<=|>|<)\s*"
    r"(?P<threshold>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)$"
)
_MINIMUM_SCALE: Final = 1e-6
_PROGRAM_ORDER: Final = tuple(GliomaConstraintProgram)
_PROGRAM_EDGES: Final = (
    (GliomaConstraintProgram.RTK_PI3K_AKT_MTOR, GliomaConstraintProgram.PROLIFERATION, 1.0),
    (GliomaConstraintProgram.P53_CELL_CYCLE, GliomaConstraintProgram.PROLIFERATION, -1.0),
    (GliomaConstraintProgram.IDH_HIF1A, GliomaConstraintProgram.MESENCHYMAL_PROGRAM, -1.0),
    (GliomaConstraintProgram.RTK_PI3K_AKT_MTOR, GliomaConstraintProgram.MESENCHYMAL_PROGRAM, 1.0),
    (GliomaConstraintProgram.MESENCHYMAL_PROGRAM, GliomaConstraintProgram.PROLIFERATION, 1.0),
)
_PROGRAM_EDGE_STRENGTH: Final = 0.35
_PROGRAM_RIDGE: Final = 0.03
_PROGRAM_DAMPING: Final = 0.7
_PROGRAM_HUBER_DELTA: Final = 1.5
_PROGRAM_ITERATIONS: Final = 120
_PROGRAM_TOLERANCE: Final = 1e-5
_PROGRAM_SCORE_LIMIT: Final = 4.0
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95


@dataclass(frozen=True, slots=True)
class _TypedObservation:
    feature_id: str
    program: GliomaConstraintProgram
    direction: int
    state: FeatureObservationState
    value: float
    standard_error: float
    quality_weight: float
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class _TypedFit:
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool


class M1005ConstraintAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for constraint integration."""

    def __init__(self) -> None:
        super().__init__(
            "M10-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1005ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M10-05 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_constraint_authorization(candidate: object) -> None:
    """Read only the seven control states before traversing constraint inputs."""

    try:
        context = _member(candidate, "context")
        refs = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(refs, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M1005ConstraintAuthorizationError from None
    if states != expected:
        raise M1005ConstraintAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_constraint_authorization(candidate)
    return candidate


def _evidence(request: IntegrateProteinRnaConstraintsRequest) -> tuple[EvidenceReference, ...]:
    # ContextReferences is a frozen model rather than an iterable; project its
    # seven evidence records explicitly and bound the output.
    refs = request.context.references
    context_artifacts = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    source = (
        request.representation_result,
        request.advanced_estimator_result,
        *request.feature_artifacts,
        request.constraint_set.evidence[0].reference
        if request.constraint_set.evidence
        else request.representation_result,
        *context_artifacts,
        *(
            item.reference
            for observation in request.feature_observations
            for item in observation.evidence
        ),
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1005_EVIDENCE_CLAIM)
        for artifact in source[:64]
    )


def _evaluate_expression(expression: str) -> ConstraintEvaluationOutcome:
    normalized = expression.strip().lower()
    if normalized in _TRUE_EXPRESSIONS:
        return ConstraintEvaluationOutcome.SATISFIED
    if normalized in _FALSE_EXPRESSIONS:
        return ConstraintEvaluationOutcome.VIOLATED
    return ConstraintEvaluationOutcome.NOT_EVALUABLE


def _numeric_constraint_result(  # noqa: PLR0911
    expression: str,
    feature_ids: tuple[str, ...],
    observations: Mapping[str, FeatureObservation],
) -> tuple[ConstraintEvaluationOutcome, float, float] | None:
    """Evaluate a numeric comparison with an uncertainty-scaled residual.

    Censored observations are used only when their upper bound proves an upper
    constraint. Missing and unsupported values remain not evaluable, never negative.
    """

    match = _NUMERIC_EXPRESSION.fullmatch(expression.strip())
    if match is None or match.group("feature") not in feature_ids:
        return None
    observation = observations.get(match.group("feature"))
    if observation is None:
        return ConstraintEvaluationOutcome.NOT_EVALUABLE, 1.0, 0.0
    threshold = float(match.group("threshold"))
    operator = match.group("operator")
    if observation.state is FeatureObservationState.LEFT_CENSORED:
        limit = observation.censoring_limit
        if limit is None:
            return ConstraintEvaluationOutcome.NOT_EVALUABLE, 1.0, 0.0
        if operator == "<=" and limit <= threshold:
            return ConstraintEvaluationOutcome.SATISFIED, 0.0, 1.0
        if operator == "<" and limit < threshold:
            return ConstraintEvaluationOutcome.SATISFIED, 0.0, 1.0
        return ConstraintEvaluationOutcome.NOT_EVALUABLE, 1.0, 0.0
    if observation.state is not FeatureObservationState.OBSERVED or observation.value is None:
        return ConstraintEvaluationOutcome.NOT_EVALUABLE, 1.0, 0.0
    value = observation.value
    violation = {
        "==": abs(value - threshold),
        ">=": max(0.0, threshold - value),
        "<=": max(0.0, value - threshold),
        ">": (max(threshold - value, 2.0 * _MINIMUM_SCALE) if value <= threshold else 0.0),
        "<": (max(value - threshold, 2.0 * _MINIMUM_SCALE) if value >= threshold else 0.0),
    }[operator]
    scale = max(observation.standard_error or 0.1, _MINIMUM_SCALE)
    residual = violation / scale
    strength = exp(-0.5 * residual * residual)
    outcome = (
        ConstraintEvaluationOutcome.SATISFIED
        if violation <= _MINIMUM_SCALE
        else ConstraintEvaluationOutcome.VIOLATED
    )
    return outcome, residual, strength


def _evaluate_constraint(
    expression: str,
    feature_ids: tuple[str, ...],
    observations: Mapping[str, FeatureObservation],
) -> tuple[ConstraintEvaluationOutcome, float, float]:
    """Evaluate compatibility expressions or measured numeric constraints."""

    closed = _evaluate_expression(expression)
    if closed is not ConstraintEvaluationOutcome.NOT_EVALUABLE:
        return (
            closed,
            0.0 if closed is ConstraintEvaluationOutcome.SATISFIED else 1.0,
            1.0 if closed is ConstraintEvaluationOutcome.SATISFIED else 0.0,
        )
    numeric = _numeric_constraint_result(expression, feature_ids, observations)
    if numeric is not None:
        return numeric
    return ConstraintEvaluationOutcome.NOT_EVALUABLE, 1.0, 0.0


def _support(status: SupportStatus, reason: str) -> SupportDecision:
    return SupportDecision(status=status, reason_code=f"m1005_{reason}", rationale=reason)


def _has_typed_observations(observations: tuple[FeatureObservation, ...]) -> bool:
    return any(item.program is not None for item in observations)


def _median(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def _robust_location_scale(values: tuple[float, ...]) -> tuple[float, float]:
    center = _median(values)
    mad = _median(tuple(abs(value - center) for value in values))
    return center, max(_MINIMUM_SCALE, 1.4826 * mad if mad > _MINIMUM_SCALE else 1.0)


def _hash_normal(material: str) -> float:
    def uniform(suffix: str) -> float:
        digest = hashlib.sha256((material + suffix).encode("utf-8")).digest()
        return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)

    first = max(_MINIMUM_SCALE, uniform(":u1"))
    second = uniform(":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _typed_observations(
    observations: tuple[FeatureObservation, ...],
) -> tuple[_TypedObservation, ...]:
    result: list[_TypedObservation] = []
    for item in sorted(observations, key=lambda value: value.feature_id):
        if item.program is None:
            continue
        if item.state is FeatureObservationState.OBSERVED and item.value is not None:
            value = item.value
        elif (
            item.state is FeatureObservationState.LEFT_CENSORED and item.censoring_limit is not None
        ):
            value = item.censoring_limit
        else:
            continue
        result.append(
            _TypedObservation(
                feature_id=item.feature_id,
                program=item.program,
                direction=item.direction,
                state=item.state,
                value=value,
                standard_error=max(_MINIMUM_SCALE, item.standard_error or 1.0),
                quality_weight=item.quality_weight,
                evidence=item.evidence,
            )
        )
    return tuple(result)


def _program_objective(
    values: list[float],
    observations: tuple[_TypedObservation, ...],
    center: float,
    scale: float,
    *,
    include_edges: bool,
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _PROGRAM_RIDGE * sum(value * value for value in values)
    for item in observations:
        target = item.direction * max(
            -_PROGRAM_SCORE_LIMIT,
            min(_PROGRAM_SCORE_LIMIT, (item.value - center) / scale),
        )
        residual = values[index[item.program]] - target
        if item.state is FeatureObservationState.LEFT_CENSORED:
            residual = max(0.0, residual)
        scaled = residual / max(_MINIMUM_SCALE, item.standard_error / scale)
        absolute = abs(scaled)
        loss = (
            0.5 * scaled * scaled
            if absolute <= _PROGRAM_HUBER_DELTA
            else (_PROGRAM_HUBER_DELTA * (absolute - 0.5 * _PROGRAM_HUBER_DELTA))
        )
        objective += item.quality_weight * loss
    if include_edges:
        for edge_source, edge_target, sign in _PROGRAM_EDGES:
            residual = (
                values[index[edge_target]]
                - sign * _PROGRAM_EDGE_STRENGTH * values[index[edge_source]]
            )
            objective += 0.5 * residual * residual
    return objective


def _fit_programs(  # noqa: C901 - signed program coordinate updates are intentionally explicit.
    observations: tuple[_TypedObservation, ...],
    center: float,
    scale: float,
    *,
    include_edges: bool = True,
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaConstraintProgram, list[_TypedObservation]] = defaultdict(list)
    for item in observations:
        grouped[item.program].append(item)
    values = [0.0] * len(_PROGRAM_ORDER)
    for program, items in grouped.items():
        if items:
            weights = tuple(item.quality_weight for item in items)
            values[index[program]] = sum(
                weight
                * item.direction
                * max(
                    -_PROGRAM_SCORE_LIMIT,
                    min(_PROGRAM_SCORE_LIMIT, (item.value - center) / scale),
                )
                for weight, item in zip(weights, items, strict=True)
            ) / max(_MINIMUM_SCALE, sum(weights))
    objective = _program_objective(values, observations, center, scale, include_edges=include_edges)
    for iteration in range(1, _PROGRAM_ITERATIONS + 1):
        old = values.copy()
        for position, program in enumerate(_PROGRAM_ORDER):
            current = values[position]
            gradient = 2.0 * _PROGRAM_RIDGE * current
            hessian = 2.0 * _PROGRAM_RIDGE
            for item in grouped[program]:
                target_value = item.direction * max(
                    -_PROGRAM_SCORE_LIMIT,
                    min(_PROGRAM_SCORE_LIMIT, (item.value - center) / scale),
                )
                residual = (current - target_value) / max(
                    _MINIMUM_SCALE, item.standard_error / scale
                )
                if item.state is FeatureObservationState.LEFT_CENSORED and current <= target_value:
                    continue
                absolute = abs(residual)
                huber = 1.0 if absolute <= _PROGRAM_HUBER_DELTA else _PROGRAM_HUBER_DELTA / absolute
                information = (
                    item.quality_weight
                    * huber
                    / max(_MINIMUM_SCALE, (item.standard_error / scale) ** 2)
                )
                gradient += information * (current - target_value)
                hessian += information
            if include_edges:
                for edge_source, edge_target, sign in _PROGRAM_EDGES:
                    if program is edge_source:
                        residual = (
                            values[index[edge_target]] - sign * _PROGRAM_EDGE_STRENGTH * current
                        )
                        gradient += -sign * _PROGRAM_EDGE_STRENGTH * residual
                        hessian += _PROGRAM_EDGE_STRENGTH**2
                    elif program is edge_target:
                        residual = (
                            current - sign * _PROGRAM_EDGE_STRENGTH * values[index[edge_source]]
                        )
                        gradient += residual
                        hessian += 1.0
            proposal = current - gradient / max(_MINIMUM_SCALE, hessian)
            values[position] = current + _PROGRAM_DAMPING * (proposal - current)
        update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        next_objective = _program_objective(
            values, observations, center, scale, include_edges=include_edges
        )
        if update <= _PROGRAM_TOLERANCE and abs(objective - next_objective) <= _PROGRAM_TOLERANCE:
            return _TypedFit(
                values=tuple(_quantize(value) for value in values),
                objective=_quantize(next_objective),
                iterations=iteration,
                converged=True,
            )
        objective = next_objective
    return _TypedFit(
        values=tuple(_quantize(value) for value in values),
        objective=_quantize(objective),
        iterations=_PROGRAM_ITERATIONS,
        converged=False,
    )


def _quantize(value: float) -> float:
    return float(f"{value:.8f}")


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _typed_program_states(
    request: IntegrateProteinRnaConstraintsRequest,
    request_digest: str,
) -> tuple[tuple[GliomaConstraintProgramState, ...], _TypedFit | None]:
    observations = _typed_observations(request.feature_observations)
    if not observations:
        return (), None
    center, scale = _robust_location_scale(tuple(item.value for item in observations))
    fit = _fit_programs(observations, center, scale)
    topology_free = _fit_programs(observations, center, scale, include_edges=False)
    if not fit.converged or not topology_free.converged:
        return (), None
    draws: list[tuple[float, ...]] = []
    for draw in range(request.bootstrap_replicates):
        perturbed = tuple(
            _TypedObservation(
                feature_id=item.feature_id,
                program=item.program,
                direction=item.direction,
                state=item.state,
                value=item.value
                + item.standard_error * _hash_normal(f"{request_digest}:{draw}:{item.feature_id}"),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
                evidence=item.evidence,
            )
            for item in observations
        )
        draw_center, draw_scale = _robust_location_scale(tuple(item.value for item in perturbed))
        draw_fit = _fit_programs(perturbed, draw_center, draw_scale)
        if not draw_fit.converged:
            return (), None
        draws.append(draw_fit.values)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    states: list[GliomaConstraintProgramState] = []
    for program in sorted({item.program for item in observations}, key=lambda item: item.value):
        position = index[program]
        program_items = tuple(item for item in observations if item.program is program)
        samples = tuple(draw[position] for draw in draws)
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
        drivers = tuple(
            item.feature_id
            for item in sorted(
                program_items,
                key=lambda item: (
                    -abs(item.quality_weight * item.direction * (item.value - center)),
                    item.feature_id,
                ),
            )[:3]
        )
        edge_delta = fit.values[position] - topology_free.values[position]
        evidence = tuple(item for source in program_items for item in source.evidence)[:64]
        states.append(
            GliomaConstraintProgramState(
                program=program,
                score=fit.values[position],
                lower_bound=lower,
                upper_bound=upper,
                stability=_quantize(max(0.0, min(1.0, 1.0 - (upper - lower) / 8.0))),
                discordance=_quantize(min(1.0, abs(edge_delta))),
                evidence_count=len(program_items),
                top_drivers=drivers or ("no_observed_driver",),
                ablation_effects=(f"signed_program_edges_removed:{_quantize(edge_delta):.8f}",),
                evidence=evidence,
            )
        )
    return tuple(states), fit


def _limitations(
    *, integrated: bool, soft_conflict: bool, typed: bool = False
) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_upstream_inputs",
            statement="Upstream artifacts remain immutable references and are never traversed.",
        ),
        Limitation(
            code="no_prohibited_outputs",
            statement=(
                "This module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, identity inference, or consent inference."
            ),
        ),
        Limitation(
            code="caller_declared_expression_language",
            statement=(
                "Closed true/false expressions and bounded numeric feature comparisons use "
                "declared measurements; all other expressions abstain rather than being "
                "interpreted heuristically."
            ),
        ),
    ]
    if soft_conflict:
        values.append(
            Limitation(
                code="soft_conflict_review",
                statement=(
                    "A soft constraint conflict is quantified by ablation and requires review."
                ),
            )
        )
    if not integrated:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "No estimate is emitted while a hard or non-evaluable constraint remains."
                ),
            )
        )
    if typed:
        values.extend(
            (
                Limitation(
                    code="typed_glioma_constraint_graph",
                    statement=(
                        "Annotated feature observations use robust median/MAD normalization "
                        "and signed glioma program coupling."
                    ),
                ),
                Limitation(
                    code="research_use_only",
                    statement=(
                        "Program states are research-use-only signals, not calibrated clinical "
                        "mechanism or treatment estimates."
                    ),
                ),
            )
        )
    return tuple(values)


class M1005ConstraintEngine:
    """Evaluate a closed expression vocabulary and rederive every result region."""

    __slots__ = ()

    def integrate(self, request: object) -> ProteinRnaConstraintIntegrationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(  # noqa: PLR0915 - legacy envelope and typed lane are rederived together.
        self,
        request: IntegrateProteinRnaConstraintsRequest,
    ) -> ProteinRnaConstraintIntegrationResult:
        request_hash = canonical_request_digest(request)
        evaluations: list[ConstraintEvaluation] = []
        ablations: list[ConstraintAblation] = []
        hard_violated = False
        not_evaluable = False
        soft_conflict = False
        weighted_score = 0.0
        total_weight = 0.0
        observations = {item.feature_id: item for item in request.feature_observations}
        for constraint in request.constraint_set.constraints:
            outcome, residual, strength = _evaluate_constraint(
                constraint.expression,
                constraint.feature_ids,
                observations,
            )
            if outcome is ConstraintEvaluationOutcome.VIOLATED:
                if constraint.hardness is ConstraintHardness.HARD:
                    hard_violated = True
                else:
                    soft_conflict = True
            if outcome is ConstraintEvaluationOutcome.NOT_EVALUABLE:
                not_evaluable = True
            if constraint.hardness is ConstraintHardness.SOFT:
                weight = constraint.weight or 0.0
                total_weight += weight
                weighted_score += weight * strength
                effect = weight * strength
                ablations.append(
                    ConstraintAblation(
                        constraint_id=constraint.constraint_id,
                        with_constraint_effect=effect,
                        without_constraint_effect=0.0,
                        effect_delta=effect,
                        evidence=constraint.evidence,
                    )
                )
            evaluations.append(
                ConstraintEvaluation(
                    constraint_id=constraint.constraint_id,
                    outcome=outcome,
                    residual=residual,
                    effect_size=(
                        constraint.weight if constraint.hardness is ConstraintHardness.SOFT else 1.0
                    ),
                    message=(
                        "constraint satisfied with declared feature evidence"
                        if outcome is ConstraintEvaluationOutcome.SATISFIED
                        else "constraint was violated or not evaluable from declared evidence"
                    ),
                    evidence=constraint.evidence,
                )
            )
        typed_model = _has_typed_observations(request.feature_observations)
        program_states: tuple[GliomaConstraintProgramState, ...] = ()
        typed_fit: _TypedFit | None = None
        typed_failure = False
        if typed_model:
            program_states, typed_fit = _typed_program_states(request, request_hash)
            typed_failure = typed_fit is None or not program_states
        integrated = not hard_violated and not not_evaluable and not typed_failure
        if integrated:
            score = 1.0 if not total_weight else weighted_score / total_weight
            estimates: tuple[ConstraintAwareEstimate, ...] = (
                ConstraintAwareEstimate(
                    estimate_label="constraint_integrated_score",
                    score=score,
                    lower_bound=max(0.0, score - 0.05),
                    upper_bound=min(1.0, score + 0.05),
                    evidence=_evidence(request),
                ),
            )
            status = ConstraintIntegrationStatus.INTEGRATED
            support = _support(SupportStatus.SUPPORTED, "all_constraints_evaluable")
            reason = None
        else:
            estimates = ()
            program_states = ()
            status = ConstraintIntegrationStatus.ABSTAINED
            if hard_violated:
                support_status = SupportStatus.REVIEW_REQUIRED
                support_reason = "hard_constraint_violation"
                reason = "A hard constraint was violated; no estimate is emitted."
            elif not_evaluable:
                support_status = SupportStatus.UNSUPPORTED
                support_reason = "constraint_not_evaluable"
                reason = "At least one constraint is outside the closed evaluation vocabulary."
            else:
                support_status = SupportStatus.REVIEW_REQUIRED
                support_reason = "typed_program_solver_not_converged"
                reason = (
                    "The typed glioma constraint graph did not produce a stable supported "
                    "state; no estimate is emitted."
                )
            support = _support(
                support_status,
                support_reason,
            )
        payload: dict[str, object] = {
            "output_type": "protein_rna_constraint_integration",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1005_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "estimates": estimates,
            "program_states": program_states,
            "typed_model": typed_model,
            "solver_iterations": typed_fit.iterations if typed_fit is not None else None,
            "solver_objective": typed_fit.objective if typed_fit is not None else None,
            "evaluations": tuple(evaluations),
            "ablations": tuple(ablations),
            "abstention_reason": reason,
            "parent_target": M1005_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": expected_uncertainty(integrated=integrated),
            "provenance": expected_provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(
                integrated=integrated,
                soft_conflict=soft_conflict,
                typed=typed_model,
            ),
            "human_review_required": (not integrated) or soft_conflict,
        }
        constructed = ProteinRnaConstraintIntegrationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaConstraintIntegrationResult:
        if isinstance(result, BaseModel):
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M1005ReplayVerificationError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1005ReplayVerificationError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1005ReplayVerificationError(  # noqa: TRY003
                "result digest does not match canonical payload"
            )
        if replay:
            expected = self.integrate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1005ReplayVerificationError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def integrate_protein_rna_constraints(
    request: object,
) -> ProteinRnaConstraintIntegrationResult:
    """Public provisional M10-05 operation."""

    return M1005ConstraintEngine().integrate(request)


__all__ = [
    "M1005ConstraintAuthorizationError",
    "M1005ConstraintEngine",
    "M1005ReplayVerificationError",
    "integrate_protein_rna_constraints",
    "preflight_constraint_authorization",
]
