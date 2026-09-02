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

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_05 import (
    M0905_EVIDENCE_CLAIM,
    M0905_MAX_CANONICAL_RESULT_BYTES,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintEvidenceObservation,
    ConstraintIntegratorStatus,
    ConstraintObservationState,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    IntegrateComplexActivityConstraintsRequest,
    IntegrateComplexActivityConstraintsResult,
    IntegrateComplexActivityConstraintsVerification,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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
    return (
        (match.group("feature"), match.group("operator"), target)
        if isfinite(target)
        else None
    )


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
    return cast("float", observation.censoring_limit) - 0.5 * standard_error, standard_error


def _fit_observations(  # noqa: C901
    request: IntegrateComplexActivityConstraintsRequest,
) -> dict[str, tuple[float, float, float, float]]:
    """Fit complex-member measurements with robust IRLS and soft bounds."""

    grouped: dict[str, list[ConstraintEvidenceObservation]] = defaultdict(list)
    for observation in request.observations:
        if observation.state in {
            ConstraintObservationState.OBSERVED,
            ConstraintObservationState.LEFT_CENSORED,
        } and observation.quality_weight > 0.0:
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
        estimate = fsum(
            weight * value for weight, value in zip(weights, values, strict=True)
        ) / fsum(weights)
        related = tuple(
            parsed
            for constraint in request.policy.constraints
            if (parsed := _parse_numeric_constraint(constraint.expression)) is not None
            and parsed[0] == feature_id
            and constraint.severity is ConstraintSeverity.SOFT
        )
        for _ in range(12):
            robust = []
            for weight, value, error in zip(weights, values, errors, strict=True):
                residual = abs(estimate - value)
                cutoff = 1.5 * error
                robust.append(weight if residual <= cutoff else weight * cutoff / residual)
            data_weight = fsum(robust)
            proposal = fsum(
                weight * value for weight, value in zip(robust, values, strict=True)
            ) / max(data_weight, 1e-12)
            for _, operator, target in related:
                tolerance = request.policy.conflict_tolerance
                if _constraint_is_violated(proposal, operator, target, tolerance):
                    penalty = 1.0 / max(tolerance, 1e-3) ** 2
                    proposal = (data_weight * proposal + penalty * target) / (
                        data_weight + penalty
                    )
            limits = tuple(
                item.censoring_limit
                for item in items
                if item.state is ConstraintObservationState.LEFT_CENSORED
                and item.censoring_limit is not None
            )
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
        limits = tuple(
            item.censoring_limit
            for item in items
            if item.state is ConstraintObservationState.LEFT_CENSORED
            and item.censoring_limit is not None
        )
        if limits:
            upper = min(upper, *limits)
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


def _evaluate(
    expression: str,
    severity: ConstraintSeverity,
    value: float | None,
    tolerance: float,
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
        violation = None if value is None else round(min(1.0, abs(value)), 8)
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
        "constraint evaluated under the deterministic provisional integrator",
    )


def _build_result(
    request: IntegrateComplexActivityConstraintsRequest,
) -> IntegrateComplexActivityConstraintsResult:
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
