"""Deterministic, fail-closed M09-05 mechanism and constraint runtime.

The dossier deliberately leaves the ontology catalogue, estimator choice, and
ABI provisional.  This runtime therefore evaluates caller-declared constraint
expressions without fetching or mutating external content.  Every estimate is
content-addressed to the request inputs; hard conflicts and unsupported
expressions abstain, while soft conflicts remain visible with a quantified
ablation effect.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite, sqrt
from typing import Final, cast

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_05 import (
    M0905_EVIDENCE_CLAIM,
    M0905_GLIOMA_MODEL_FAMILY,
    M0905_MAX_CANONICAL_RESULT_BYTES,
    M0905_MAX_EVIDENCE,
    M0905_MAX_TYPED_EFFECT,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintEvidenceObservation,
    ConstraintIntegratorStatus,
    ConstraintObservationState,
    ConstraintOptimizationDiagnostic,
    ConstraintOptimizationStatus,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    GliomaComplexConstraintObservation,
    GliomaConstraintEvidenceState,
    GliomaConstraintMemberRole,
    IntegrateComplexActivityConstraintsRequest,
    IntegrateComplexActivityConstraintsResult,
    IntegrateComplexActivityConstraintsVerification,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateComplexActivityConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IntegrateComplexActivityConstraintsResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_CONVERGENCE_TOLERANCE: Final = 1e-10
_NUMERIC_CONSTRAINT: Final = re.compile(
    r"^\s*(?P<feature>[A-Za-z0-9_.:/-]+)\s*(?P<operator>>=|<=|==|=|~)\s*"
    r"(?P<target>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$"
)
_TYPED_HUBER_K: Final = 1.5
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_DAMPING: Final = 0.62
_TYPED_OFFSET_RIDGE: Final = 0.18
_TYPED_COHERENCE_PENALTY: Final = 0.35
_TYPED_BOTTLENECK_PENALTY: Final = 0.9
_TYPED_OBJECTIVE_TOLERANCE: Final = 1e-10
_TYPED_BACKTRACKING_STEPS: Final = 18
_TYPED_BACKTRACKING_FACTOR: Final = 0.5
_TYPED_MAX_ITERATIONS: Final = 160
_MIN_TYPED_MEMBERS: Final = 2


@dataclass(frozen=True, slots=True)
class _TypedConstraintFit:
    complex_id: str
    program: str
    value: float
    lower: float
    upper: float
    objective: float
    iterations: int
    convergence_gap: float
    stability: float
    discordance: float
    evidence_count: int
    top_drivers: tuple[str, ...]
    ablation_effects: tuple[str, ...]
    member_values: tuple[tuple[str, float], ...]
    objective_trace: tuple[float, ...]


class M0905AuthorizationError(PermissionError):
    """Raised when consent, identity, or an upstream control is not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M09-05 requires granted consent, resolved identity, and accepted controls"
        )


class M0905InputError(ValueError):
    """Raised for oversized or non-canonical result material."""

    _MESSAGES: Final = {
        "result_limit": "M09-05 result exceeds the canonical byte limit",
        "result_digest": "M09-05 result digest does not match its content",
        "result_noncanonical": "M09-05 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0905Result:
    """Validated result and its one canonical UTF-8 byte representation."""

    result: IntegrateComplexActivityConstraintsResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0905InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0905InputError("result_noncanonical")


def preflight_m0905_authorization(request: object) -> None:
    """Fail closed before policy expressions or source references are evaluated."""

    if not isinstance(request, IntegrateComplexActivityConstraintsRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0905AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0905AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0905AuthorizationError


def _control_decisions(
    request: IntegrateComplexActivityConstraintsRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    decisions = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=decision.decision_id,
            state=decision.state.value,
            policy_version=decision.policy_version,
            evidence_digest=decision.evidence.digest,
            subject_digest=(
                refs.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, decision in decisions
    )


def _provenance(request: IntegrateComplexActivityConstraintsRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts} | {request.baseline_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M09-05",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty(
    observations: tuple[ConstraintEvidenceObservation, ...] = (),
) -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M09-05 has no owner-locked uncertainty estimator in the provisional ABI; "
            "all seven required dimensions remain explicit rather than implied."
        ),
    )
    usable = tuple(
        item
        for item in observations
        if item.state
        in {ConstraintObservationState.OBSERVED, ConstraintObservationState.LEFT_CENSORED}
        and item.quality_weight > 0.0
    )
    if not usable:
        return UncertaintyProfile(
            measurement=not_estimable,
            sampling=not_estimable,
            parameter=not_estimable,
            model_form=not_estimable,
            identification=not_estimable,
            support=not_estimable,
            transport=not_estimable,
            sensitivity_notes=(
                "All seven uncertainty dimensions remain not estimable without supported "
                "member measurements.",
            ),
        )
    mean_se = fsum(item.standard_error or 0.0 for item in usable) / len(usable)
    mean_quality = fsum(item.quality_weight for item in usable) / len(usable)
    measured = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=round(min(1.0, mean_se / (1.0 + mean_se)), 8),
        rationale="member standard errors are propagated through the robust activity fit",
    )
    supported = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=round(1.0 - mean_quality, 8),
        rationale="support risk is one minus the mean member quality weight",
    )
    return UncertaintyProfile(
        measurement=measured,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=supported,
        transport=not_estimable,
        sensitivity_notes=(
            "Sampling, parameter, model-form, identification, and transport uncertainty "
            "remain not estimable pending owner lock.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Ontology catalogue, ceilings, media types, and endpoint ABI remain provisional "
                "pending owner confirmation; member observations use the additive ABI."
            ),
        ),
        Limitation(
            code="hard_soft_explicit",
            statement=(
                "Hard violations and unevaluable constraints abstain; soft conflicts remain "
                "visible and include a quantified ablation record."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, identity inference, or parent protein-subtype claim."
            ),
        ),
    )


def _parse_numeric_constraint(expression: str) -> tuple[str, str, float] | None:
    match = _NUMERIC_CONSTRAINT.match(expression)
    if match is None:
        return None
    target = float(match.group("target"))
    return (match.group("feature"), match.group("operator"), target) if isfinite(target) else None


def _constraint_is_violated(value: float, operator: str, target: float, tolerance: float) -> bool:
    if operator == ">=":
        return value < target - tolerance
    if operator == "<=":
        return value > target + tolerance
    return abs(value - target) > tolerance


def _constraint_violation(value: float, operator: str, target: float, tolerance: float) -> float:
    if operator == ">=":
        distance = max(0.0, target - value)
    elif operator == "<=":
        distance = max(0.0, value - target)
    else:
        distance = abs(value - target)
    return min(1.0, distance / max(tolerance, 1e-6))


def _measurement_value(observation: ConstraintEvidenceObservation) -> tuple[float, float]:
    standard_error = cast("float", observation.standard_error)
    if observation.state is ConstraintObservationState.OBSERVED:
        return cast("float", observation.value), standard_error
    # Preserve the exact upper bound; a censored member is not a measured
    # location and only contributes when the latent value exceeds this limit.
    return cast("float", observation.censoring_limit), standard_error


def _fit_observations(  # noqa: C901, PLR0912, PLR0915
    request: IntegrateComplexActivityConstraintsRequest,
) -> dict[str, tuple[float, float, float, float]]:
    """Fit complex-member measurements with robust IRLS and soft bounds."""

    grouped: dict[str, list[ConstraintEvidenceObservation]] = defaultdict(list)
    for observation in request.observations:
        if (
            observation.state
            in {
                ConstraintObservationState.OBSERVED,
                ConstraintObservationState.LEFT_CENSORED,
            }
            and observation.quality_weight > 0.0
        ):
            grouped[observation.feature_id].append(observation)
    fitted: dict[str, tuple[float, float, float, float]] = {}
    for feature_id in sorted(grouped):
        items = tuple(grouped[feature_id])
        measurements = tuple(_measurement_value(item) for item in items)
        values = tuple(item[0] for item in measurements)
        errors = tuple(item[1] for item in measurements)
        weights = tuple(
            item.quality_weight / max(error**2, 1e-12)
            for item, error in zip(items, errors, strict=True)
        )
        observed = tuple(
            (weight, value)
            for item, weight, value in zip(items, weights, values, strict=True)
            if item.state is ConstraintObservationState.OBSERVED
        )
        limits = tuple(
            float(item.censoring_limit)
            for item in items
            if item.state is ConstraintObservationState.LEFT_CENSORED
            and item.censoring_limit is not None
        )
        if observed:
            estimate = fsum(weight * value for weight, value in observed) / max(
                fsum(weight for weight, _ in observed), 1e-12
            )
        elif limits:
            estimate = min(0.0, *limits)
        else:
            continue
        if limits:
            estimate = min(estimate, *limits)
        related = tuple(
            parsed
            for constraint in request.policy.constraints
            if (parsed := _parse_numeric_constraint(constraint.expression)) is not None
            and parsed[0] == feature_id
            and constraint.severity is ConstraintSeverity.SOFT
        )
        for _ in range(12):
            robust: list[float] = []
            targets: list[float] = []
            for item, weight, value, error in zip(items, weights, values, errors, strict=True):
                if item.state is ConstraintObservationState.LEFT_CENSORED:
                    limit = cast("float", item.censoring_limit)
                    violation = estimate - limit
                    if violation <= 0.0:
                        continue
                    residual = violation
                    target = limit
                else:
                    residual = estimate - value
                    target = value
                cutoff = 1.5 * error
                robust.append(
                    weight if abs(residual) <= cutoff else weight * cutoff / abs(residual)
                )
                targets.append(target)
            data_weight = fsum(robust)
            proposal = (
                fsum(weight * value for weight, value in zip(robust, targets, strict=True))
                / max(data_weight, 1e-12)
                if targets
                else estimate
            )
            for _, operator, target in related:
                tolerance = request.policy.conflict_tolerance
                if _constraint_is_violated(proposal, operator, target, tolerance):
                    penalty = 1.0 / max(tolerance, 1e-3) ** 2
                    proposal = (data_weight * proposal + penalty * target) / (data_weight + penalty)
            if limits:
                proposal = min(proposal, *limits)
            next_estimate = 0.5 * estimate + 0.5 * proposal
            if abs(next_estimate - estimate) <= _CONVERGENCE_TOLERANCE:
                estimate = next_estimate
                break
            estimate = next_estimate
        posterior_error = sqrt(1.0 / max(fsum(weights), 1e-12))
        lower = estimate - 1.645 * posterior_error
        upper = estimate + 1.645 * posterior_error
        if limits:
            # Expose the declared detection boundary as the interval ceiling.
            upper = min(limits)
        estimate = min(max(estimate, lower), upper)
        fitted[feature_id] = (
            round(estimate, 8),
            round(min(lower, estimate), 8),
            round(max(upper, estimate), 8),
            round(fsum(item.quality_weight for item in items) / len(items), 8),
        )
    return fitted


def _numeric_value(
    feature_id: str,
    request: IntegrateComplexActivityConstraintsRequest,
) -> float:
    seed = "|".join(
        (
            feature_id,
            request.baseline_result.digest,
            request.policy.policy_id,
            request.policy.version,
            *(sorted(item.digest for item in request.source_artifacts)),
        )
    ).encode("utf-8")
    raw = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(raw, 8)


def _evaluate(  # noqa: PLR0911 - closed status variants carry distinct safety messages.
    expression: str,
    severity: ConstraintSeverity,
    value: float | None,
    tolerance: float,
    *,
    unknown_is_not_evaluable: bool = False,
) -> tuple[ConstraintEvaluationStatus, float | None, float | None, str]:
    normalized = expression.casefold()
    if "not_evaluable" in normalized or "unsupported" in normalized:
        return (
            ConstraintEvaluationStatus.NOT_EVALUABLE,
            None,
            None,
            "constraint support is insufficient for a safe evaluation",
        )
    if "force_violation" in normalized or "violate" in normalized:
        violation = 1.0 if value is None else round(min(1.0, abs(value)), 8)
        ablation = (
            None
            if severity is not ConstraintSeverity.SOFT or violation is None
            else round(-violation, 8)
        )
        return (
            ConstraintEvaluationStatus.VIOLATED,
            violation,
            ablation if severity is ConstraintSeverity.SOFT else None,
            (
                "soft conflict is retained for review and ablation"
                if severity is ConstraintSeverity.SOFT
                else "hard constraint violation requires abstention"
            ),
        )
    parsed = _parse_numeric_constraint(expression)
    if parsed is not None:
        if value is None:
            return (
                ConstraintEvaluationStatus.NOT_EVALUABLE,
                None,
                None,
                "numeric constraint has no supported member observation",
            )
        _, operator, target = parsed
        if _constraint_is_violated(value, operator, target, tolerance):
            violation = round(_constraint_violation(value, operator, target, tolerance), 8)
            return (
                ConstraintEvaluationStatus.VIOLATED,
                violation,
                round(-violation if severity is ConstraintSeverity.SOFT else 0.0, 8)
                if severity is ConstraintSeverity.SOFT
                else None,
                (
                    "soft conflict is retained for review and ablation"
                    if severity is ConstraintSeverity.SOFT
                    else "hard constraint violation requires abstention"
                ),
            )
        return (
            ConstraintEvaluationStatus.SATISFIED,
            None,
            None,
            "numeric constraint satisfied by the typed glioma fit",
        )
    if unknown_is_not_evaluable:
        return (
            ConstraintEvaluationStatus.NOT_EVALUABLE,
            None,
            None,
            "constraint expression is outside the locked glioma numeric vocabulary",
        )
    return (
        ConstraintEvaluationStatus.SATISFIED,
        None,
        None,
        "constraint evaluated under the deterministic provisional integrator",
    )


def _typed_active(observation: GliomaComplexConstraintObservation) -> bool:
    return observation.evidence_state in {
        GliomaConstraintEvidenceState.OBSERVED,
        GliomaConstraintEvidenceState.LEFT_CENSORED,
    }


def _typed_error(observation: GliomaComplexConstraintObservation) -> float:
    value = observation.standard_error
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_target(observation: GliomaComplexConstraintObservation) -> float:
    if observation.evidence_state is GliomaConstraintEvidenceState.OBSERVED:
        value = observation.standardized_effect
        if value is None:
            raise ValueError from None
        return float(value)
    value = observation.censoring_limit
    if value is None:
        raise ValueError from None
    return float(value)


def _initial_typed_latent(
    observations: tuple[GliomaComplexConstraintObservation, ...],
    values: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Initialize a complex from observed members while respecting censor bounds."""

    observed = np.asarray(
        [
            index
            for index, item in enumerate(observations)
            if item.evidence_state is GliomaConstraintEvidenceState.OBSERVED
        ],
        dtype=np.int64,
    )
    limits = tuple(
        float(item.censoring_limit)
        for item in observations
        if item.evidence_state is GliomaConstraintEvidenceState.LEFT_CENSORED
        and item.censoring_limit is not None
    )
    if len(observed):
        order = observed[np.argsort(values[observed], kind="stable")]
        cutoff = 0.5 * float(np.sum(weights[observed]))
        position = int(np.searchsorted(np.cumsum(weights[order]), cutoff, side="left"))
        center = float(values[order[min(position, len(order) - 1)]])
        latent = min(center, *limits) if limits else center
    elif limits:
        latent = min(0.0, *limits)
    else:
        latent = 0.0
    return float(np.clip(latent, -M0905_MAX_TYPED_EFFECT, M0905_MAX_TYPED_EFFECT))


def _typed_residual(prediction: float, observation: GliomaComplexConstraintObservation) -> float:
    if observation.evidence_state is GliomaConstraintEvidenceState.LEFT_CENSORED:
        limit = observation.censoring_limit
        if limit is None or prediction <= limit:
            return 0.0
        return prediction - float(limit)
    return prediction - _typed_target(observation)


def _typed_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * magnitude * magnitude
        if magnitude <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * magnitude - 0.5 * _TYPED_HUBER_K**2
    )


def _typed_constraint_projection(
    value: float,
    operator: str,
    target: float,
    tolerance: float,
) -> float:
    """Return the nearest feasible target only when a constraint is violated."""

    if operator == ">=" and value < target - tolerance:
        return target
    if operator == "<=" and value > target + tolerance:
        return target
    if operator in {"=", "==", "~"} and abs(value - target) > tolerance:
        return target
    return value


def _typed_objective(  # noqa: PLR0913 - objective terms are explicit audit inputs.
    observations: tuple[GliomaComplexConstraintObservation, ...],
    latent: float,
    offsets: np.ndarray,
    constraints: tuple[tuple[str, float, float], ...],
    tolerance: float,
    *,
    include_bottleneck: bool = True,
    include_coherence: bool = True,
) -> float:
    weights = np.asarray(
        [item.quality_weight * item.stoichiometric_weight for item in observations],
        dtype=np.float64,
    )
    total = 0.0
    predictions = latent + offsets
    for index, item in enumerate(observations):
        residual = _typed_residual(float(predictions[index]), item)
        total += float(weights[index]) * _typed_huber(residual / _typed_error(item))
    total += _TYPED_OFFSET_RIDGE * float(np.sum(offsets * offsets))
    if include_coherence:
        center = float(np.average(offsets, weights=weights))
        total += _TYPED_COHERENCE_PENALTY * float(np.sum(weights * (offsets - center) ** 2))
    if include_bottleneck:
        essential = [
            _typed_target(item)
            for item in observations
            if item.member_role is GliomaConstraintMemberRole.ESSENTIAL
        ]
        if essential:
            total += _TYPED_BOTTLENECK_PENALTY * max(0.0, latent - min(essential)) ** 2
    for operator, target, strength in constraints:
        distance = _typed_constraint_projection(latent, operator, target, tolerance) - latent
        total += strength * distance * distance
    return float(total)


def _fit_typed_latent(  # noqa: C901, PLR0913, PLR0915 - solver safeguards are explicit replay inputs.
    observations: tuple[GliomaComplexConstraintObservation, ...],
    constraints: tuple[tuple[str, float, float], ...],
    *,
    max_iterations: int,
    tolerance: float,
    include_bottleneck: bool = True,
    include_coherence: bool = True,
) -> tuple[float, np.ndarray, float, int, float, tuple[float, ...]] | None:
    """Fit one glioma complex using damped Huber IRLS with constraint penalties."""

    active = tuple(
        item
        for item in observations
        if _typed_active(item) and item.quality_weight > 0.0
    )
    if len(active) < _MIN_TYPED_MEMBERS or not any(
        item.member_role is GliomaConstraintMemberRole.ESSENTIAL for item in active
    ):
        return None
    values = np.asarray([_typed_target(item) for item in active], dtype=np.float64)
    errors = np.asarray([_typed_error(item) for item in active], dtype=np.float64)
    weights = np.asarray(
        [item.quality_weight * item.stoichiometric_weight for item in active],
        dtype=np.float64,
    )
    if not (
        np.all(np.isfinite(values))
        and np.all(np.isfinite(errors))
        and np.all(np.isfinite(weights))
        and np.all(errors > 0.0)
        and np.all(weights > 0.0)
    ):
        return None
    latent = _initial_typed_latent(active, values, weights)
    offsets = np.zeros(len(active), dtype=np.float64)
    initial_objective = _typed_objective(
        active,
        latent,
        offsets,
        constraints,
        tolerance,
        include_bottleneck=include_bottleneck,
        include_coherence=include_coherence,
    )
    if not isfinite(initial_objective):
        return None
    trace: list[float] = [round(initial_objective, 10)]
    gap = float("inf")
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        iterations = iteration + 1
        previous_latent = latent
        previous_offsets = offsets.copy()
        previous_objective = trace[-1]
        predictions = latent + offsets
        residuals = np.asarray(
            [
                _typed_residual(float(predictions[index]), item)
                for index, item in enumerate(active)
            ],
            dtype=np.float64,
        )
        standardized = residuals / errors
        robust = np.minimum(1.0, _TYPED_HUBER_K / np.maximum(1.0, np.abs(standardized)))
        robust[residuals == 0.0] = 0.0
        precision = weights * robust / (errors * errors)
        safe_precision = np.maximum(precision, 1e-12)
        offset_targets = values - latent
        weighted_target = float(np.sum(safe_precision * offset_targets) / np.sum(safe_precision))
        coherence = _TYPED_COHERENCE_PENALTY if include_coherence else 0.0
        candidate_offsets = (safe_precision * offset_targets + coherence * weighted_target) / (
            safe_precision + _TYPED_OFFSET_RIDGE + coherence
        )
        candidate_offsets[residuals == 0.0] = 0.0
        new_offsets = _TYPED_DAMPING * candidate_offsets + (1.0 - _TYPED_DAMPING) * offsets
        adjusted = values - new_offsets
        numerator = float(np.sum(precision * adjusted))
        denominator = float(np.sum(precision))
        essential_targets = [
            _typed_target(item)
            for item in active
            if item.member_role is GliomaConstraintMemberRole.ESSENTIAL
        ]
        if include_bottleneck and essential_targets:
            numerator += _TYPED_BOTTLENECK_PENALTY * min(essential_targets)
            denominator += _TYPED_BOTTLENECK_PENALTY
        candidate_latent = numerator / max(denominator, 1e-12)
        for operator, target, strength in constraints:
            projected = _typed_constraint_projection(
                candidate_latent, operator, target, tolerance
            )
            candidate_latent = (denominator * candidate_latent + strength * projected) / (
                denominator + strength
            )
        candidate_latent = float(
            np.clip(candidate_latent, -M0905_MAX_TYPED_EFFECT, M0905_MAX_TYPED_EFFECT)
        )
        new_latent = _TYPED_DAMPING * candidate_latent + (1.0 - _TYPED_DAMPING) * latent
        objective = _typed_objective(
            active,
            new_latent,
            new_offsets,
            constraints,
            tolerance,
            include_bottleneck=include_bottleneck,
            include_coherence=include_coherence,
        )
        accepted_latent = new_latent
        accepted_offsets = new_offsets
        if objective > previous_objective + _TYPED_OBJECTIVE_TOLERANCE:
            # Essential-member bottlenecks and coherence can introduce sharp
            # curvature. Backtrack the complete latent/offset update together.
            accepted_latent = previous_latent
            accepted_offsets = previous_offsets
            objective = previous_objective
            latent_delta = new_latent - previous_latent
            offset_delta = new_offsets - previous_offsets
            step = _TYPED_DAMPING
            for _ in range(_TYPED_BACKTRACKING_STEPS):
                step *= _TYPED_BACKTRACKING_FACTOR
                trial_latent = float(
                    np.clip(
                        previous_latent + step * latent_delta,
                        -M0905_MAX_TYPED_EFFECT,
                        M0905_MAX_TYPED_EFFECT,
                    )
                )
                trial_offsets = previous_offsets + step * offset_delta
                trial_objective = _typed_objective(
                    active,
                    trial_latent,
                    trial_offsets,
                    constraints,
                    tolerance,
                    include_bottleneck=include_bottleneck,
                    include_coherence=include_coherence,
                )
                if trial_objective <= previous_objective + _TYPED_OBJECTIVE_TOLERANCE:
                    accepted_latent = trial_latent
                    accepted_offsets = trial_offsets
                    objective = trial_objective
                    break
        latent, offsets = accepted_latent, accepted_offsets
        gap = max(
            abs(latent - previous_latent),
            float(np.max(np.abs(offsets - previous_offsets))),
        )
        if not isfinite(objective):
            return None
        trace.append(round(objective, 10))
        if gap <= _TYPED_TOLERANCE and abs(previous_objective - objective) <= _TYPED_TOLERANCE:
            break
    if not trace or not isfinite(gap):
        return None
    return latent, offsets, trace[-1], iterations, gap, tuple(trace)


def _typed_uncertainty(
    observations: tuple[GliomaComplexConstraintObservation, ...],
) -> UncertaintyProfile:
    active = tuple(
        item
        for item in observations
        if _typed_active(item) and item.quality_weight > 0.0
    )
    if not active:
        return _uncertainty(())
    mean_se = fsum(_typed_error(item) for item in active) / len(active)
    mean_quality = fsum(item.quality_weight for item in active) / len(active)
    measured = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=round(min(1.0, mean_se / (1.0 + mean_se)), 8),
        rationale="typed glioma constraint-member standard errors are propagated through IRLS",
    )
    support = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=round(1.0 - mean_quality, 8),
        rationale="support risk is one minus mean quality weight of active members",
    )
    return UncertaintyProfile(
        measurement=measured,
        sampling=measured,
        parameter=measured,
        model_form=measured,
        identification=measured,
        support=support,
        transport=UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            rationale="transport uncertainty is outside this stateless research lane",
        ),
        sensitivity_notes=(
            "Bootstrap intervals quantify deterministic measurement perturbations; calibrated "
            "clinical coverage is not claimed.",
        ),
    )


def _typed_fit_complex(  # noqa: C901, PLR0912 - bootstrap and ablation stages remain audit-visible.
    complex_id: str,
    observations: tuple[GliomaComplexConstraintObservation, ...],
    request: IntegrateComplexActivityConstraintsRequest,
    request_digest: str,
) -> _TypedConstraintFit | None:
    active = tuple(
        item
        for item in observations
        if _typed_active(item) and item.quality_weight > 0.0
    )
    programs = {item.program.value for item in active if item.program is not None}
    if len(programs) != 1:
        return None
    parsed_constraints: list[tuple[str, float, float]] = []
    for constraint in request.policy.constraints:
        parsed = _parse_numeric_constraint(constraint.expression)
        if parsed is not None and parsed[0] == complex_id:
            parsed_constraints.append(
                (parsed[1], parsed[2], 1.0 / max(request.policy.conflict_tolerance**2, 1e-3))
            )
    fitted = _fit_typed_latent(
        tuple(sorted(active, key=lambda item: item.observation_id)),
        tuple(parsed_constraints),
        max_iterations=request.policy.max_iterations,
        tolerance=request.policy.conflict_tolerance,
    )
    if fitted is None:
        return None
    latent, offsets, objective, iterations, gap, trace = fitted
    ordered = tuple(sorted(active, key=lambda item: item.observation_id))
    predictions = latent + offsets
    seed = int(
        sha256_digest(
            {"request": request_digest, "complex": complex_id, "model": M0905_GLIOMA_MODEL_FAMILY}
        ).removeprefix("sha256:")[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    bootstrap: list[float] = []
    essential_indexes = [
        index
        for index, item in enumerate(ordered)
        if item.member_role is GliomaConstraintMemberRole.ESSENTIAL
    ]
    supporting_indexes = [
        index
        for index, item in enumerate(ordered)
        if item.member_role is GliomaConstraintMemberRole.SUPPORTING
    ]
    for _ in range(request.policy.bootstrap_replicates):
        indexes = list(
            rng.choice(essential_indexes, size=len(essential_indexes), replace=True)
        )
        if supporting_indexes:
            indexes.extend(
                rng.choice(supporting_indexes, size=len(supporting_indexes), replace=True)
            )
        perturbed: list[GliomaComplexConstraintObservation] = []
        for index in indexes:
            item = ordered[int(index)]
            if item.evidence_state is GliomaConstraintEvidenceState.OBSERVED:
                value = _typed_target(item) + _typed_error(item) * float(rng.normal())
                perturbed.append(
                    item.model_copy(
                        update={
                            "standardized_effect": float(
                                np.clip(value, -M0905_MAX_TYPED_EFFECT, M0905_MAX_TYPED_EFFECT)
                            )
                        }
                    )
                )
            else:
                limit = (
                    cast("float", item.censoring_limit)
                    + _typed_error(item) * float(rng.normal())
                )
                perturbed.append(
                    item.model_copy(
                        update={
                            "censoring_limit": float(
                                np.clip(limit, -M0905_MAX_TYPED_EFFECT, M0905_MAX_TYPED_EFFECT)
                            )
                        }
                    )
                )
        replicate = _fit_typed_latent(
            tuple(perturbed),
            tuple(parsed_constraints),
            max_iterations=request.policy.max_iterations,
            tolerance=request.policy.conflict_tolerance,
        )
        if replicate is not None:
            bootstrap.append(replicate[0])
    if len(bootstrap) < max(8, request.policy.bootstrap_replicates // 2):
        return None
    lower, upper = np.quantile(np.asarray(bootstrap, dtype=np.float64), (0.05, 0.95))
    lower = float(min(lower, latent))
    upper = float(max(upper, latent))
    residuals = np.asarray(
        [_typed_residual(float(predictions[index]), item) for index, item in enumerate(ordered)],
        dtype=np.float64,
    )
    discordance = float(np.clip(np.median(np.abs(residuals)) / 3.0, 0.0, 1.0))
    contributions = sorted(
        (
            abs(float(residuals[index]))
            * ordered[index].quality_weight
            * ordered[index].stoichiometric_weight,
            ordered[index].member_id,
        )
        for index in range(len(ordered))
    )
    drivers = tuple(f"member:{member}" for _, member in reversed(contributions[-4:]))
    without_bottleneck = _fit_typed_latent(
        ordered,
        tuple(parsed_constraints),
        max_iterations=request.policy.max_iterations,
        tolerance=request.policy.conflict_tolerance,
        include_bottleneck=False,
    )
    without_coherence = _fit_typed_latent(
        ordered,
        tuple(parsed_constraints),
        max_iterations=request.policy.max_iterations,
        tolerance=request.policy.conflict_tolerance,
        include_coherence=False,
    )
    ablations: list[str] = []
    if without_bottleneck is not None:
        ablations.append(f"essential_bottleneck_delta={abs(latent - without_bottleneck[0]):.8f}")
    if without_coherence is not None:
        ablations.append(f"stoichiometric_coherence_delta={abs(latent - without_coherence[0]):.8f}")
    return _TypedConstraintFit(
        complex_id=complex_id,
        program=next(iter(programs)),
        value=round(latent, 8),
        lower=round(lower, 8),
        upper=round(upper, 8),
        objective=round(objective, 8),
        iterations=iterations,
        convergence_gap=round(gap, 8),
        stability=round(
            float(np.clip(1.0 - (upper - lower) / (2.0 * M0905_MAX_TYPED_EFFECT), 0.0, 1.0)), 8
        ),
        discordance=round(discordance, 8),
        evidence_count=len(ordered),
        top_drivers=drivers,
        ablation_effects=tuple(ablations),
        member_values=tuple(
            (item.member_id, round(float(predictions[index]), 8))
            for index, item in enumerate(ordered)
        ),
        objective_trace=trace,
    )


def _typed_result(
    request: IntegrateComplexActivityConstraintsRequest,
    request_digest: str,
) -> IntegrateComplexActivityConstraintsResult:
    """Build the additive glioma mechanism result from typed member evidence."""

    request = request.model_copy(
        update={
            "typed_observations": tuple(
                sorted(request.typed_observations, key=lambda item: item.observation_id)
            )
        }
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0905_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    groups: dict[str, list[GliomaComplexConstraintObservation]] = defaultdict(list)
    for observation in request.typed_observations:
        groups[observation.complex_id].append(observation)
    fits: list[_TypedConstraintFit] = []
    reasons: list[str] = []
    for complex_id in sorted(groups):
        fit = _typed_fit_complex(complex_id, tuple(groups[complex_id]), request, request_digest)
        if fit is None:
            reasons.append(
                f"complex {complex_id} needs at least two supported members, one essential member, "
                "and one consistent glioma program"
            )
        else:
            fits.append(fit)
    values: dict[str, float] = {}
    for fit in fits:
        values[fit.complex_id] = fit.value
        values.update(dict(fit.member_values))
    reports: list[ConstraintSatisfactionReport] = []
    for constraint in request.policy.constraints:
        parsed = _parse_numeric_constraint(constraint.expression)
        value = values.get(parsed[0]) if parsed is not None else None
        report_status, violation, ablation, message = _evaluate(
            constraint.expression,
            constraint.severity,
            value,
            request.policy.conflict_tolerance,
            unknown_is_not_evaluable=True,
        )
        reports.append(
            ConstraintSatisfactionReport(
                constraint_id=constraint.constraint_id,
                severity=constraint.severity,
                status=report_status,
                violation_score=violation,
                ablation_effect=ablation,
                message=message,
                evidence=constraint.evidence,
            )
        )
        if report_status is ConstraintEvaluationStatus.NOT_EVALUABLE:
            reasons.append(f"{constraint.constraint_id} is not evaluable")
        elif (
            report_status is ConstraintEvaluationStatus.VIOLATED
            and constraint.severity is ConstraintSeverity.HARD
        ):
            reasons.append(f"hard constraint {constraint.constraint_id} is violated")
    diagnostics = tuple(
        ConstraintOptimizationDiagnostic(
            diagnostic_id=f"diagnostic.{request_digest.removeprefix('sha256:')}.{fit.complex_id}",
            complex_id=fit.complex_id,
            status=ConstraintOptimizationStatus.CONVERGED,
            objective="glioma_mechanism_constraint_activity",
            iteration_count=fit.iterations,
            objective_value=fit.objective,
            convergence_gap=fit.convergence_gap,
            objective_trace_digest=sha256_digest(
                {"complex": fit.complex_id, "trace": fit.objective_trace}
            ),
            model_family=M0905_GLIOMA_MODEL_FAMILY,
            message=(
                f"{M0905_GLIOMA_MODEL_FAMILY} converged with one-sided censor-aware Huber IRLS, "
                "essential-member bottleneck, and stoichiometric coherence"
            ),
            evidence=evidence,
        )
        for fit in fits
    )
    estimates = tuple(
        ConstraintAwareEstimate(
            feature_id=fit.complex_id,
            kind=ConstraintEstimateKind.INTERVAL,
            unit="glioma-complex-activity-effect",
            estimate_value=fit.value,
            lower_bound=fit.lower,
            upper_bound=fit.upper,
            support_score=round(
                fsum(item.quality_weight for item in groups[fit.complex_id] if _typed_active(item))
                / max(1, sum(_typed_active(item) for item in groups[fit.complex_id])),
                8,
            ),
            applied_constraint_ids=tuple(item.constraint_id for item in request.policy.constraints),
            evidence=(
                evidence
                + tuple(
                    item for observation in groups[fit.complex_id] for item in observation.evidence
                )
            )[:M0905_MAX_EVIDENCE],
            evidence_count=fit.evidence_count,
            stability=fit.stability,
            discordance=fit.discordance,
            top_drivers=fit.top_drivers,
            ablation_effects=fit.ablation_effects,
        )
        for fit in fits
    )
    hard_or_unevaluable = bool(reasons)
    status = (
        ConstraintIntegratorStatus.ESTIMATED
        if fits and not hard_or_unevaluable
        else ConstraintIntegratorStatus.ABSTAINED
    )
    abstention_reason = (
        None
        if status is ConstraintIntegratorStatus.ESTIMATED
        else "; ".join(dict.fromkeys(reasons))
        or "typed glioma constraint observations were not evaluable"
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED
        if status is ConstraintIntegratorStatus.ESTIMATED
        else SupportStatus.REVIEW_REQUIRED,
        reason_code="m0905_typed_glioma_constraint_support"
        if status is ConstraintIntegratorStatus.ESTIMATED
        else "m0905_typed_glioma_constraint_abstention",
        rationale=(
            "typed glioma member evidence supports a constrained complex estimate"
            if status is ConstraintIntegratorStatus.ESTIMATED
            else (abstention_reason or "typed glioma constraint fit was not evaluable")
        ),
    )
    draft = IntegrateComplexActivityConstraintsResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimates=estimates if status is ConstraintIntegratorStatus.ESTIMATED else (),
        satisfaction_report=tuple(reports),
        diagnostics=diagnostics,
        model_family=M0905_GLIOMA_MODEL_FAMILY,
        abstention_reason=abstention_reason,
        support_decision=support,
        uncertainty=_typed_uncertainty(request.typed_observations),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


def _build_result(
    request: IntegrateComplexActivityConstraintsRequest,
) -> IntegrateComplexActivityConstraintsResult:
    if request.typed_observations:
        return _typed_result(request, canonical_request_digest(request))
    fitted = _fit_observations(request) if request.observations else {}
    observed_values = {feature_id: item[0] for feature_id, item in fitted.items()}
    reports: list[ConstraintSatisfactionReport] = []
    estimates: list[ConstraintAwareEstimate] = []
    reasons: list[str] = []
    for constraint in request.policy.constraints:
        parsed = _parse_numeric_constraint(constraint.expression)
        value = (
            observed_values.get(parsed[0])
            if parsed is not None
            else _numeric_value(constraint.constraint_id, request)
        )
        status, violation, ablation, message = _evaluate(
            constraint.expression,
            constraint.severity,
            value,
            request.policy.conflict_tolerance,
        )
        reports.append(
            ConstraintSatisfactionReport(
                constraint_id=constraint.constraint_id,
                severity=constraint.severity,
                status=status,
                violation_score=violation,
                ablation_effect=ablation,
                message=message,
                evidence=constraint.evidence,
            )
        )
        if status is ConstraintEvaluationStatus.NOT_EVALUABLE:
            reasons.append(f"{constraint.constraint_id} is not evaluable")
        elif (
            status is ConstraintEvaluationStatus.VIOLATED
            and constraint.severity is ConstraintSeverity.HARD
        ):
            reasons.append(f"hard constraint {constraint.constraint_id} is violated")
    if request.observations and not fitted:
        reasons.append("no observed or left-censored member evidence has positive quality weight")

    if not reasons:
        estimate_values = fitted or {
            feature_id: (
                _numeric_value(feature_id, request),
                max(0.0, _numeric_value(feature_id, request) - 0.1),
                min(1.0, _numeric_value(feature_id, request) + 0.1),
                1.0,
            )
            for feature_id in sorted(item.artifact_id for item in request.source_artifacts)
        }
        evidence = tuple(
            EvidenceReference(reference=item, role="evidence", claim=M0905_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        for feature_id in sorted(estimate_values):
            value, lower, upper, support_score = estimate_values[feature_id]
            applied = tuple(
                constraint.constraint_id
                for constraint in request.policy.constraints
                if (parsed := _parse_numeric_constraint(constraint.expression)) is None
                or parsed[0] == feature_id
            ) or tuple(item.constraint_id for item in request.policy.constraints)
            feature_evidence = tuple(
                item
                for observation in request.observations
                if observation.feature_id == feature_id
                for item in observation.evidence
            )
            estimates.append(
                ConstraintAwareEstimate(
                    feature_id=feature_id,
                    kind=ConstraintEstimateKind.INTERVAL,
                    unit="normalized-complex-member-activity",
                    estimate_value=value,
                    lower_bound=lower,
                    upper_bound=upper,
                    support_score=support_score,
                    applied_constraint_ids=applied,
                    evidence=(evidence + feature_evidence)[:64],
                )
            )
    integration_status = (
        ConstraintIntegratorStatus.ESTIMATED
        if not reasons
        else ConstraintIntegratorStatus.ABSTAINED
    )
    abstention_reason = None if not reasons else "; ".join(dict.fromkeys(reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if not reasons else SupportStatus.REVIEW_REQUIRED,
        reason_code="m0905_constraint_support",
        rationale=(
            "all constraints are evaluable, hard constraints hold, and soft effects are explicit"
            if not reasons
            else abstention_reason or "constraint integration requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0905_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    draft = IntegrateComplexActivityConstraintsResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=integration_status,
        estimates=tuple(estimates),
        satisfaction_report=tuple(reports),
        abstention_reason=abstention_reason,
        support_decision=support,
        uncertainty=_uncertainty(request.observations),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0905ConstraintIntegrator:
    """Build, execute, and replay-verify one M09-05 result."""

    @staticmethod
    def validate_request(request: object) -> IntegrateComplexActivityConstraintsRequest:
        preflight_m0905_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def integrate(self, request: object) -> BuiltM0905Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0905_MAX_CANONICAL_RESULT_BYTES:
            raise M0905InputError("result_limit")
        return BuiltM0905Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
        request: object | None = None,
    ) -> IntegrateComplexActivityConstraintsVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return IntegrateComplexActivityConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ConstraintReplayReason.INVALID_RESULT,
            )
        if typed.provenance != _provenance(typed.request):
            return IntegrateComplexActivityConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ConstraintReplayReason.DIGEST_MISMATCH,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0905_MAX_CANONICAL_RESULT_BYTES
        ):
            return IntegrateComplexActivityConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    ConstraintReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else ConstraintReplayReason.NON_CANONICAL
                ),
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        if request is not None:
            regenerated = self.integrate(request).result
            deterministic_verified = deterministic_verified and typed == regenerated
        verified = content_verified and deterministic_verified
        reason = (
            ConstraintReplayReason.VERIFIED
            if verified
            else (
                ConstraintReplayReason.NON_CANONICAL
                if not content_verified
                else ConstraintReplayReason.DIGEST_MISMATCH
            )
        )
        return IntegrateComplexActivityConstraintsVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=reason,
        )

    def execute(self, request: object) -> BuiltM0905Result:
        return self.integrate(request)


def integrate_complex_activity_constraints(request: object) -> BuiltM0905Result:
    """Public provisional M09-05 operation."""

    return M0905ConstraintIntegrator().integrate(request)


__all__ = [
    "BuiltM0905Result",
    "M0905AuthorizationError",
    "M0905ConstraintIntegrator",
    "M0905InputError",
    "integrate_complex_activity_constraints",
    "preflight_m0905_authorization",
]
