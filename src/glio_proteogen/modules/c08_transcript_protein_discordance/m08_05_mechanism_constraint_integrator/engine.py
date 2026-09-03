"""Deterministic, support-aware M08-05 mechanism/constraint runtime.

The dossier does not freeze an ontology catalogue, learned estimator, or ABI.
This implementation therefore keeps the integration boundary deterministic and
auditable: callers provide content-addressed references and policy expressions,
the engine never fetches or mutates external content, hard conflicts abstain,
and soft conflicts remain visible with an explicit ablation effect.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite, sqrt
from typing import Final, cast

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_05 import (
    M0805_EVIDENCE_CLAIM,
    M0805_MAX_CANONICAL_RESULT_BYTES,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintEvidenceObservation,
    ConstraintIntegratorStatus,
    ConstraintObservationState,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    IntegrateTranscriptProteinConstraintsRequest,
    IntegrateTranscriptProteinConstraintsResult,
    IntegrateTranscriptProteinConstraintsVerification,
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

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateTranscriptProteinConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IntegrateTranscriptProteinConstraintsResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_CONVERGENCE_TOLERANCE: Final = 1e-10


class M0805AuthorizationError(PermissionError):
    """Raised when consent, identity, or an upstream control is not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M08-05 requires granted consent, resolved identity, and accepted controls"
        )


class M0805InputError(ValueError):
    """Raised for oversized or non-canonical result material."""

    _MESSAGES: Final = {
        "result_limit": "M08-05 result exceeds the canonical byte limit",
        "result_digest": "M08-05 result digest does not match its content",
        "result_noncanonical": "M08-05 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0805Result:
    """Validated result and the one canonical byte representation."""

    result: IntegrateTranscriptProteinConstraintsResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0805InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0805InputError("result_noncanonical")


def preflight_m0805_authorization(request: object) -> None:
    """Fail closed before policy expressions or source references are evaluated."""

    if not isinstance(request, IntegrateTranscriptProteinConstraintsRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0805AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0805AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0805AuthorizationError


def _control_decisions(
    request: IntegrateTranscriptProteinConstraintsRequest,
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


def _provenance(request: IntegrateTranscriptProteinConstraintsRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts} | {request.baseline_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M08-05",
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
        rationale="M08-05 has no owner-locked uncertainty estimator in the provisional ABI.",
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
                "Measurement, sampling, parameter, model-form, identification, support, "
                "and transport uncertainty are explicitly not estimable pending owner lock.",
            ),
        )
    mean_se = fsum(item.standard_error or 0.0 for item in usable) / len(usable)
    mean_quality = fsum(item.quality_weight for item in usable) / len(usable)
    return UncertaintyProfile(
        measurement=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=round(min(1.0, mean_se / (1.0 + mean_se)), 8),
            rationale="reported standard errors are propagated through the robust IRLS fit",
        ),
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=round(1.0 - mean_quality, 8),
            rationale="support risk is one minus the mean caller-supplied quality weight",
        ),
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
                "pending owner confirmation; measured observations use the additive ABI."
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


_NUMERIC_CONSTRAINT = re.compile(
    r"^\s*(?P<feature>[A-Za-z0-9_.:/-]+)\s*(?P<operator>>=|<=|==|=|~)\s*"
    r"(?P<target>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$"
)


def _parse_numeric_constraint(expression: str) -> tuple[str, str, float] | None:
    match = _NUMERIC_CONSTRAINT.match(expression)
    if match is None:
        return None
    target = float(match.group("target"))
    if not isfinite(target):
        return None
    return match.group("feature"), match.group("operator"), target


def _constraint_is_violated(value: float, operator: str, target: float, tolerance: float) -> bool:
    if operator == ">=":
        return value < target - tolerance
    if operator == "<=":
        return value > target + tolerance
    if operator in {"=", "==", "~"}:
        return abs(value - target) > tolerance
    return False


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
    censoring_limit = cast("float", observation.censoring_limit)
    return censoring_limit - 0.5 * standard_error, standard_error


def _fit_observations(  # noqa: C901
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> dict[str, tuple[float, float, float, float]]:
    """Fit declared measurements with robust IRLS and soft constraint damping."""

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
        surrogate = tuple(item[0] for item in measurements)
        standard_errors = tuple(item[1] for item in measurements)
        base_weights = tuple(
            item.quality_weight / max(standard_error**2, 1e-12)
            for item, standard_error in zip(items, standard_errors, strict=True)
        )
        value = fsum(
            weight * datum
            for weight, datum in zip(base_weights, surrogate, strict=True)
        ) / fsum(base_weights)
        related = tuple(
            parsed
            for constraint in request.policy.constraints
            if (parsed := _parse_numeric_constraint(constraint.expression)) is not None
            and parsed[0] == feature_id
            and constraint.severity is ConstraintSeverity.SOFT
        )
        for _ in range(12):
            robust_weights = []
            for weight, datum, standard_error in zip(
                base_weights, surrogate, standard_errors, strict=True
            ):
                residual = abs(value - datum)
                huber_delta = 1.5 * standard_error
                robust_weights.append(
                    weight if residual <= huber_delta else weight * huber_delta / residual
                )
            data_weight = fsum(robust_weights)
            proposal = fsum(
                weight * datum
                for weight, datum in zip(robust_weights, surrogate, strict=True)
            ) / max(data_weight, 1e-12)
            for _, operator, target in related:
                tolerance = request.policy.conflict_tolerance
                if _constraint_is_violated(proposal, operator, target, tolerance):
                    penalty_weight = 1.0 / max(tolerance, 1e-3) ** 2
                    proposal = (data_weight * proposal + penalty_weight * target) / (
                        data_weight + penalty_weight
                    )
            censor_limits = tuple(
                item.censoring_limit
                for item in items
                if item.state is ConstraintObservationState.LEFT_CENSORED
                and item.censoring_limit is not None
            )
            if censor_limits:
                proposal = min(proposal, *censor_limits)
            next_value = 0.5 * value + 0.5 * proposal
            if abs(next_value - value) <= _CONVERGENCE_TOLERANCE:
                value = next_value
                break
            value = next_value
        standard_error = sqrt(1.0 / max(fsum(base_weights), 1e-12))
        lower = value - 1.645 * standard_error
        upper = value + 1.645 * standard_error
        censor_limits = tuple(
            item.censoring_limit
            for item in items
            if item.state is ConstraintObservationState.LEFT_CENSORED
            and item.censoring_limit is not None
        )
        if censor_limits:
            upper = min(upper, *censor_limits)
        value = min(max(value, lower), upper)
        fitted[feature_id] = (
            round(value, 8),
            round(min(lower, value), 8),
            round(max(upper, value), 8),
            round(fsum(item.quality_weight for item in items) / len(items), 8),
        )
    return fitted


def _numeric_value(
    feature_id: str,
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> float:
    seed = "|".join(
        [
            feature_id,
            request.baseline_result.digest,
            request.policy.policy_id,
            request.policy.version,
            *sorted(item.digest for item in request.source_artifacts),
        ]
    ).encode("utf-8")
    raw = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(raw, 8)


def _evaluate(
    constraint_id: str,
    expression: str,
    severity: ConstraintSeverity,
    value: float | None,
    tolerance: float,
) -> tuple[ConstraintEvaluationStatus, float | None, str]:
    normalized = expression.casefold()
    if "not_evaluable" in normalized or "unsupported" in normalized:
        return (
            ConstraintEvaluationStatus.NOT_EVALUABLE,
            None,
            "constraint support is insufficient for a safe evaluation",
        )
    if "force_violation" in normalized or "violate" in normalized:
        violation_score = None if value is None else round(min(1.0, abs(value)), 8)
        return (
            ConstraintEvaluationStatus.VIOLATED,
            violation_score,
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
                "numeric constraint has no supported observation for its feature",
            )
        _, operator, target = parsed
        if _constraint_is_violated(value, operator, target, tolerance):
            return (
                ConstraintEvaluationStatus.VIOLATED,
                round(_constraint_violation(value, operator, target, tolerance), 8),
                (
                    "soft conflict is retained for review and ablation"
                    if severity is ConstraintSeverity.SOFT
                    else "hard constraint violation requires abstention"
                ),
            )
    return (
        ConstraintEvaluationStatus.SATISFIED,
        None,
        f"{constraint_id} evaluated under the deterministic provisional integrator",
    )


def _build_result(
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> IntegrateTranscriptProteinConstraintsResult:
    constraints = request.policy.constraints
    feature_ids = tuple(item.artifact_id for item in request.source_artifacts)
    fitted = _fit_observations(request) if request.observations else {}
    observed_values = {feature_id: item[0] for feature_id, item in fitted.items()}
    duplicate_features = len(set(feature_ids)) != len(feature_ids)
    reports = []
    estimates = []
    reasons: list[str] = []
    for constraint in constraints:
        parsed = _parse_numeric_constraint(constraint.expression)
        value = (
            observed_values.get(parsed[0])
            if parsed is not None
            else _numeric_value(constraint.constraint_id, request)
        )
        status, violation_score, message = _evaluate(
            constraint.constraint_id,
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
                violation_score=violation_score,
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
    if duplicate_features:
        reasons.append("source artifact identifiers must be unique")
    if request.observations and not fitted:
        reasons.append("no observed or left-censored evidence has positive quality weight")
    integrated = not reasons
    if integrated:
        estimate_values = fitted or {
            feature_id: (
                _numeric_value(feature_id, request),
                max(0.0, _numeric_value(feature_id, request) - 0.1),
                min(1.0, _numeric_value(feature_id, request) + 0.1),
                1.0,
            )
            for feature_id in sorted(feature_ids)
        }
        for feature_id in sorted(estimate_values):
            value, lower_bound, upper_bound, support_score = estimate_values[feature_id]
            applied = tuple(
                constraint.constraint_id
                for constraint in constraints
                if (parsed := _parse_numeric_constraint(constraint.expression)) is None
                or parsed[0] == feature_id
            ) or tuple(item.constraint_id for item in constraints)
            feature_observation_evidence = tuple(
                evidence
                for observation in request.observations
                if observation.feature_id == feature_id
                for evidence in observation.evidence
            )
            estimate_evidence = tuple(
                EvidenceReference(reference=item, role="evidence", claim=M0805_EVIDENCE_CLAIM)
                for item in request.source_artifacts
            ) + feature_observation_evidence
            estimates.append(
                ConstraintAwareEstimate(
                    feature_id=feature_id,
                    kind=ConstraintEstimateKind.INTERVAL,
                    unit="normalized-transcript-protein",
                    estimate_value=value,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    support_score=support_score,
                    applied_constraint_ids=applied,
                    evidence=estimate_evidence[:32],
                )
            )
    integration_status = (
        ConstraintIntegratorStatus.ESTIMATED if integrated else ConstraintIntegratorStatus.ABSTAINED
    )
    abstention_reason = None if integrated else "; ".join(dict.fromkeys(reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if integrated else SupportStatus.REVIEW_REQUIRED,
        reason_code="m0805_constraint_support",
        rationale=(
            "all constraints are evaluable, hard constraints hold, and soft effects are explicit"
            if integrated
            else abstention_reason or "constraint integration requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0805_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    draft = IntegrateTranscriptProteinConstraintsResult.model_construct(
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


class M0805ConstraintIntegrator:
    """Build and verify one deterministic M08-05 integration result."""

    @staticmethod
    def validate_request(request: object) -> IntegrateTranscriptProteinConstraintsRequest:
        preflight_m0805_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def integrate(self, request: object) -> BuiltM0805Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0805_MAX_CANONICAL_RESULT_BYTES:
            raise M0805InputError("result_limit")
        return BuiltM0805Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateTranscriptProteinConstraintsVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return IntegrateTranscriptProteinConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ConstraintReplayReason.INVALID_RESULT,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0805_MAX_CANONICAL_RESULT_BYTES
        ):
            return IntegrateTranscriptProteinConstraintsVerification(
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
        verified = content_verified and deterministic_verified
        return IntegrateTranscriptProteinConstraintsVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ConstraintReplayReason.VERIFIED
                if verified
                else (
                    ConstraintReplayReason.NON_CANONICAL
                    if not content_verified
                    else ConstraintReplayReason.DIGEST_MISMATCH
                )
            ),
        )

    def execute(self, request: object) -> BuiltM0805Result:
        return self.integrate(request)


def integrate_transcript_protein_constraints(request: object) -> BuiltM0805Result:
    """Public provisional M08-05 operation."""

    return M0805ConstraintIntegrator().integrate(request)


__all__ = [
    "BuiltM0805Result",
    "M0805AuthorizationError",
    "M0805ConstraintIntegrator",
    "M0805InputError",
    "integrate_transcript_protein_constraints",
    "preflight_m0805_authorization",
]
