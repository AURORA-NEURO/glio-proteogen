"""Deterministic, safe mechanism/constraint integration for provisional M06-05.

Only a deliberately tiny, auditable expression subset is interpreted. Unknown
expressions and unsupported feature states become explicit non-evaluable
outcomes and safe abstention; Python evaluation, graph traversal, hidden priors,
and parent-output emission are intentionally absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_01 import (
    FormalStateFeatureValue,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_05 import (
    M0605_EVIDENCE_CLAIM,
    M0605_MAX_CANONICAL_RESULT_BYTES,
    ConstraintAblationRecord,
    ConstraintAwareEstimate,
    ConstraintEvaluation,
    ConstraintEvaluationOutcome,
    ConstraintIntegrationReplayReason,
    ConstraintIntegrationStatus,
    IntegrateProteinAbundanceConstraintsRequest,
    IntegrateProteinAbundanceConstraintsResult,
    IntegrateProteinAbundanceConstraintsVerification,
    MechanismConstraint,
    MechanismConstraintHardness,
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

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteinAbundanceConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IntegrateProteinAbundanceConstraintsResult)
_EXPRESSION: Final = re.compile(
    r"^\s*(?P<feature>[A-Za-z0-9_.:-]+)\s*(?P<operator>>=|<=|==|>|<)\s*"
    r"(?P<target>-?(?:\d+(?:\.\d*)?|\.\d+))\s*$"
)


class ConstraintIntegrationAuthorizationError(PermissionError):
    """Raised before an unauthorized request traverses evidence or features."""

    def __init__(self) -> None:
        super().__init__("M06-05 constraint integration request is not authorized")


class ConstraintIntegrationInputError(ValueError):
    """Raised for malformed, oversized, or non-canonical integration inputs."""

    _MESSAGES: Final = {
        "result_limit": "constraint integration result exceeds byte limit",
        "result_digest": "constraint integration result digest does not match",
        "result_noncanonical": "constraint integration result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltConstraintIntegration:
    """Typed result and the exact bytes that are safe to replay."""

    result: IntegrateProteinAbundanceConstraintsResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise ConstraintIntegrationInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise ConstraintIntegrationInputError("result_noncanonical")


def preflight_constraint_integration_authorization(request: object) -> None:
    """Apply consent, identity, and accepted upstream-control gates."""

    if not isinstance(request, IntegrateProteinAbundanceConstraintsRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ConstraintIntegrationAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ConstraintIntegrationAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise ConstraintIntegrationAuthorizationError


def _control_decisions(
    request: IntegrateProteinAbundanceConstraintsRequest,
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


def _provenance(request: IntegrateProteinAbundanceConstraintsRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts}
            | {request.advanced_estimator_result.digest}
            | {item.reference.digest for item in request.constraint_set.evidence}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M06-05",
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


def _evidence(
    request: IntegrateProteinAbundanceConstraintsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0605_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    ) + request.constraint_set.evidence


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "Calibration, transport, and support cohorts are not frozen in the provisional ABI."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Soft-constraint ablations are exposed; no hidden prior dominance is permitted.",
        ),
    )


def _numeric_value(value: FormalStateFeatureValue) -> float | None:
    if value.state is not FormalStateMissingness.OBSERVED:
        return None
    if value.scalar_value is not None:
        return value.scalar_value
    if value.interval_lower is not None and value.interval_upper is not None:
        return (value.interval_lower + value.interval_upper) / 2.0
    return None


def _compare(value: float, operator: str, target: float) -> bool:
    if operator == ">=":
        return value >= target
    if operator == "<=":
        return value <= target
    if operator == ">":
        return value > target
    if operator == "<":
        return value < target
    return value == target


def _evaluate(
    constraint: MechanismConstraint,
    values: dict[str, FormalStateFeatureValue],
) -> ConstraintEvaluation:
    match = _EXPRESSION.fullmatch(constraint.expression)
    if match is None:
        return ConstraintEvaluation(
            constraint_id=constraint.constraint_id,
            outcome=ConstraintEvaluationOutcome.NOT_EVALUABLE,
            message="expression is outside the auditable numeric comparison subset",
        )
    feature_id = match.group("feature")
    value = values.get(feature_id)
    if value is None or value.state is not FormalStateMissingness.OBSERVED:
        return ConstraintEvaluation(
            constraint_id=constraint.constraint_id,
            outcome=ConstraintEvaluationOutcome.NOT_EVALUABLE,
            message="referenced feature is not observed",
        )
    numeric = _numeric_value(value)
    if numeric is None:
        return ConstraintEvaluation(
            constraint_id=constraint.constraint_id,
            outcome=ConstraintEvaluationOutcome.NOT_EVALUABLE,
            message="referenced feature has no scalar or interval value",
        )
    target = float(match.group("target"))
    satisfied = _compare(numeric, match.group("operator"), target)
    return ConstraintEvaluation(
        constraint_id=constraint.constraint_id,
        outcome=(
            ConstraintEvaluationOutcome.SATISFIED
            if satisfied
            else ConstraintEvaluationOutcome.VIOLATED
        ),
        residual=numeric - target,
        effect_size=1.0 if satisfied else 0.0,
        message="numeric comparison satisfied" if satisfied else "numeric comparison violated",
    )


def _estimate(value: FormalStateFeatureValue) -> ConstraintAwareEstimate | None:
    numeric = _numeric_value(value)
    if numeric is None:
        return None
    return ConstraintAwareEstimate(
        feature_id=value.feature_id,
        unit=value.unit,
        estimate_value=numeric,
        lower_bound=value.interval_lower,
        upper_bound=value.interval_upper,
        evidence=value.evidence,
    )


def _build_result(
    request: IntegrateProteinAbundanceConstraintsRequest,
) -> IntegrateProteinAbundanceConstraintsResult:
    values = {item.feature_id: item for item in request.feature_values}
    evaluations = tuple(
        _evaluate(constraint, values)
        for constraint in request.constraint_set.constraints
    )
    hard_non_evaluable = any(
        constraint.hardness is MechanismConstraintHardness.HARD
        and evaluation.outcome is not ConstraintEvaluationOutcome.SATISFIED
        for constraint, evaluation in zip(
            request.constraint_set.constraints,
            evaluations,
            strict=True,
        )
    )
    unsupported = any(
        item.state is FormalStateMissingness.UNSUPPORTED for item in request.feature_values
    )
    non_observed = any(
        item.state is not FormalStateMissingness.OBSERVED for item in request.feature_values
    )
    estimates = tuple(
        estimate
        for value in request.feature_values
        if (estimate := _estimate(value)) is not None
    )
    status = ConstraintIntegrationStatus.INTEGRATED
    reason: str | None = None
    support_status = SupportStatus.SUPPORTED
    if unsupported:
        status = ConstraintIntegrationStatus.ABSTAINED
        support_status = SupportStatus.UNSUPPORTED
        reason = "one or more feature values are explicitly unsupported"
    elif hard_non_evaluable or non_observed:
        status = ConstraintIntegrationStatus.ABSTAINED
        support_status = SupportStatus.REVIEW_REQUIRED
        reason = "hard constraints or feature support are not fully evaluable"
    elif not estimates:
        status = ConstraintIntegrationStatus.ABSTAINED
        support_status = SupportStatus.REVIEW_REQUIRED
        reason = "no numeric observed features support an estimate"
    ablations = tuple(
        ConstraintAblationRecord(
            constraint_id=constraint.constraint_id,
            with_constraint_effect=(
                (
                    constraint.weight if constraint.weight is not None else 0.0
                )
                if evaluation.outcome is ConstraintEvaluationOutcome.SATISFIED
                else 0.0
            ),
            without_constraint_effect=0.0,
            effect_delta=(
                (
                    constraint.weight if constraint.weight is not None else 0.0
                )
                if evaluation.outcome is ConstraintEvaluationOutcome.SATISFIED
                else 0.0
            ),
        )
        for constraint, evaluation in zip(
            request.constraint_set.constraints,
            evaluations,
            strict=True,
        )
        if constraint.hardness is MechanismConstraintHardness.SOFT
    )
    support = SupportDecision(
        status=support_status,
        reason_code="constraint_support_state",
        rationale=reason or "all declared constraints and numeric features are supported",
    )
    limitations = (
        Limitation(
            code="provisional_abi",
            statement=(
                "M06-05 operation, expression subset, limits, and constraint catalogue "
                "remain provisional."
            ),
        ),
        Limitation(
            code="safe_expression_subset",
            statement="Only numeric comparisons are interpreted; unsupported expressions abstain.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "The integrator does not emit the parent biomarker panel or own kinase activity."
            ),
        ),
    )
    draft = IntegrateProteinAbundanceConstraintsResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        estimates=estimates if status is ConstraintIntegrationStatus.INTEGRATED else (),
        evaluations=evaluations,
        ablations=ablations,
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=_evidence(request),
        limitations=limitations,
    )
    result = draft.model_copy(update={"result_digest": result_payload_digest(draft)})
    return IntegrateProteinAbundanceConstraintsResult.model_validate(result, strict=True)


class M0605MechanismConstraintEngine:
    """Build, replay, and verify one deterministic constraint report."""

    @staticmethod
    def validate_request(request: object) -> IntegrateProteinAbundanceConstraintsRequest:
        preflight_constraint_integration_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0605_MAX_CANONICAL_RESULT_BYTES:
            raise ConstraintIntegrationInputError("result_limit")
        return BuiltConstraintIntegration(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateProteinAbundanceConstraintsVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return IntegrateProteinAbundanceConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ConstraintIntegrationReplayReason.INVALID_RESULT,
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0605_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        try:
            replayed = self.integrate(typed.request)
        except Exception:  # noqa: BLE001 - verification fails closed on replay errors.
            deterministic_verified = False
        else:
            deterministic_verified = typed.result_digest == result_payload_digest(typed) and (
                replayed.result.model_dump(mode="json") == typed.model_dump(mode="json")
            )
        verified = content_verified and deterministic_verified
        return IntegrateProteinAbundanceConstraintsVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ConstraintIntegrationReplayReason.VERIFIED
                if verified
                else ConstraintIntegrationReplayReason.DIGEST_MISMATCH
            ),
        )

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self.integrate(request)


def integrate_protein_abundance_constraints(request: object) -> BuiltConstraintIntegration:
    """Integrate one request through the default stateless engine."""

    return M0605MechanismConstraintEngine().integrate(request)


__all__ = [
    "BuiltConstraintIntegration",
    "ConstraintIntegrationAuthorizationError",
    "ConstraintIntegrationInputError",
    "M0605MechanismConstraintEngine",
    "integrate_protein_abundance_constraints",
    "preflight_constraint_integration_authorization",
]
