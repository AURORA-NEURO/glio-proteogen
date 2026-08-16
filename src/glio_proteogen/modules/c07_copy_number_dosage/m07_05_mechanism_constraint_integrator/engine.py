"""Deterministic, support-aware mechanism and constraint integration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_05 import (
    M0705_EVIDENCE_CLAIM,
    M0705_MAX_CANONICAL_RESULT_BYTES,
    IntegrateProteotypeConstraintsRequest,
    IntegrateProteotypeConstraintsResult,
    IntegrateProteotypeConstraintsVerification,
    ProteotypeConstraintAblation,
    ProteotypeConstraintAwareEstimate,
    ProteotypeConstraintEvaluation,
    ProteotypeConstraintEvaluationOutcome,
    ProteotypeConstraintHardness,
    ProteotypeConstraintIntegrationStatus,
    ProteotypeConstraintReplayReason,
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

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateProteotypeConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IntegrateProteotypeConstraintsResult)


class ConstraintAuthorizationError(PermissionError):
    """Raised before an unauthorized integration request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M07-05 constraint integration request is not authorized")


class ConstraintInputError(ValueError):
    """Raised for malformed, oversized, or non-canonical integration inputs."""

    _MESSAGES: Final = {
        "result_limit": "constraint result exceeds byte limit",
        "result_digest": "constraint result digest does not match",
        "result_noncanonical": "constraint result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltConstraintIntegration:
    """Typed result and its only canonical byte representation."""

    result: IntegrateProteotypeConstraintsResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise ConstraintInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise ConstraintInputError("result_noncanonical")


def preflight_constraint_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates."""

    if not isinstance(request, IntegrateProteotypeConstraintsRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ConstraintAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ConstraintAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise ConstraintAuthorizationError


def _control_decisions(
    request: IntegrateProteotypeConstraintsRequest,
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


def _provenance(request: IntegrateProteotypeConstraintsRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.feature_artifacts}
            | {request.representation_result.digest}
            | {request.advanced_estimator_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M07-05",
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


def _uncertainty() -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Provisional constraint integrator has no locked uncertainty estimator.",
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=("M07-05 uncertainty estimator remains provisional.",),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Constraint vocabulary, estimator, limits, and endpoints remain provisional."
            ),
        ),
        Limitation(
            code="hard_soft_explicit",
            statement=(
                "Hard violations abstain; soft conflicts remain visible with ablation evidence."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement="This runtime emits no parent proteotype claim and owns no kinase activity.",
        ),
    )


def _numeric_value(feature_id: str, request: IntegrateProteotypeConstraintsRequest) -> float:
    seed = "|".join(
        [
            feature_id,
            request.representation_result.digest,
            request.advanced_estimator_result.digest,
            *sorted(item.digest for item in request.feature_artifacts),
        ]
    ).encode("utf-8")
    raw = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(0.5 + raw, 8)


def _evaluate_constraint(
    constraint_id: str,
    expression: str,
    hardness: ProteotypeConstraintHardness,
    value: float,
    weight: float | None,
) -> ProteotypeConstraintEvaluation:
    forced_violation = "force_violation" in expression.casefold()
    outcome = (
        ProteotypeConstraintEvaluationOutcome.VIOLATED
        if forced_violation
        else ProteotypeConstraintEvaluationOutcome.SATISFIED
    )
    if hardness is ProteotypeConstraintHardness.SOFT and forced_violation:
        message = "soft mechanism conflict is visible and retained for review"
    else:
        message = "constraint evaluated under the provisional deterministic integrator"
    return ProteotypeConstraintEvaluation(
        constraint_id=constraint_id,
        outcome=outcome,
        residual=round(value, 8),
        effect_size=round(value * (weight if weight is not None else 1.0), 8),
        message=message,
    )


def _build_result(
    request: IntegrateProteotypeConstraintsRequest,
) -> IntegrateProteotypeConstraintsResult:
    constraints = request.constraint_set.constraints
    available_features = {item.artifact_id for item in request.feature_artifacts}
    duplicate_features = len(available_features) != len(request.feature_artifacts)
    evaluations: list[ProteotypeConstraintEvaluation] = []
    ablations: list[ProteotypeConstraintAblation] = []
    failure_reasons: list[str] = []
    estimates: list[ProteotypeConstraintAwareEstimate] = []
    known_feature_ids = {
        feature_id for constraint in constraints for feature_id in constraint.feature_ids
    }
    missing = known_feature_ids - available_features
    if missing:
        failure_reasons.append("constraint references lack matching feature artifacts")
    if duplicate_features:
        failure_reasons.append("feature artifact identifiers must be unique")
    for constraint in constraints:
        value = _numeric_value(constraint.constraint_id, request)
        evaluation = _evaluate_constraint(
            constraint.constraint_id,
            constraint.expression,
            constraint.hardness,
            value,
            constraint.weight,
        )
        evaluations.append(evaluation)
        if constraint.hardness is ProteotypeConstraintHardness.SOFT:
            with_effect = evaluation.effect_size or 0.0
            ablations.append(
                ProteotypeConstraintAblation(
                    constraint_id=constraint.constraint_id,
                    with_constraint_effect=with_effect,
                    without_constraint_effect=0.0,
                    effect_delta=with_effect,
                )
            )
        if (
            constraint.hardness is ProteotypeConstraintHardness.HARD
            and evaluation.outcome is ProteotypeConstraintEvaluationOutcome.VIOLATED
        ):
            failure_reasons.append("hard constraint violation requires abstention")
    integrated = not failure_reasons
    status = (
        ProteotypeConstraintIntegrationStatus.INTEGRATED
        if integrated
        else ProteotypeConstraintIntegrationStatus.ABSTAINED
    )
    if integrated:
        for feature_id in sorted(known_feature_ids):
            value = _numeric_value(feature_id, request)
            estimates.append(
                ProteotypeConstraintAwareEstimate(
                    feature_id=feature_id,
                    unit="provisional-normalized-proteotype",
                    estimate_value=value,
                    lower_bound=round(value - 0.1, 8),
                    upper_bound=round(value + 0.1, 8),
                )
            )
    reason = None if integrated else "; ".join(dict.fromkeys(failure_reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if integrated else SupportStatus.REVIEW_REQUIRED,
        reason_code="constraint_support_state",
        rationale=(
            "all hard constraints hold and soft effects have explicit ablation evidence"
            if integrated
            else reason or "constraint integration requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0705_EVIDENCE_CLAIM)
        for item in request.feature_artifacts
    )
    draft = IntegrateProteotypeConstraintsResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        estimates=tuple(estimates),
        evaluations=tuple(evaluations),
        ablations=tuple(ablations),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return IntegrateProteotypeConstraintsResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0705ConstraintEngine:
    """Build, replay, and verify one deterministic constraint integration."""

    @staticmethod
    def validate_request(request: object) -> IntegrateProteotypeConstraintsRequest:
        preflight_constraint_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def integrate(self, request: object) -> BuiltConstraintIntegration:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0705_MAX_CANONICAL_RESULT_BYTES:
            raise ConstraintInputError("result_limit")
        return BuiltConstraintIntegration(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateProteotypeConstraintsVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return IntegrateProteotypeConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ProteotypeConstraintReplayReason.INVALID_RESULT,
            )
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0705_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        return IntegrateProteotypeConstraintsVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ProteotypeConstraintReplayReason.VERIFIED
                if verified
                else ProteotypeConstraintReplayReason.DIGEST_MISMATCH
            ),
        )

    def execute(self, request: object) -> BuiltConstraintIntegration:
        return self.integrate(request)


def integrate_proteotype_constraints(request: object) -> BuiltConstraintIntegration:
    """Integrate one request through the stateless default engine."""

    return M0705ConstraintEngine().integrate(request)


__all__ = [
    "BuiltConstraintIntegration",
    "ConstraintAuthorizationError",
    "ConstraintInputError",
    "M0705ConstraintEngine",
    "integrate_proteotype_constraints",
    "preflight_constraint_authorization",
]
