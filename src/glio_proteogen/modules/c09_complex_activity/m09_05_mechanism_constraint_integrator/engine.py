"""Deterministic, fail-closed M09-05 mechanism and constraint runtime.

The dossier deliberately leaves the ontology catalogue, estimator choice, and
ABI provisional.  This runtime therefore evaluates caller-declared constraint
expressions without fetching or mutating external content.  Every estimate is
content-addressed to the request inputs; hard conflicts and unsupported
expressions abstain, while soft conflicts remain visible with a quantified
ablation effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_05 import (
    M0905_EVIDENCE_CLAIM,
    M0905_MAX_CANONICAL_RESULT_BYTES,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintIntegratorStatus,
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


def _uncertainty() -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M09-05 has no owner-locked uncertainty estimator in the provisional ABI; "
            "all seven required dimensions remain explicit rather than implied."
        ),
    )
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
            "and transport uncertainty are not estimable pending owner lock.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Ontology catalogue, estimator, ceilings, media types, and endpoint ABI "
                "remain provisional pending owner confirmation."
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
    value: float,
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
        violation = round(value, 8)
        ablation = round(-value if severity is ConstraintSeverity.SOFT else 0.0, 8)
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
    return (
        ConstraintEvaluationStatus.SATISFIED,
        None,
        None,
        "constraint evaluated under the deterministic provisional integrator",
    )


def _build_result(
    request: IntegrateComplexActivityConstraintsRequest,
) -> IntegrateComplexActivityConstraintsResult:
    reports: list[ConstraintSatisfactionReport] = []
    estimates: list[ConstraintAwareEstimate] = []
    reasons: list[str] = []
    for constraint in request.policy.constraints:
        value = _numeric_value(constraint.constraint_id, request)
        status, violation, ablation, message = _evaluate(
            constraint.expression, constraint.severity, value
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

    if not reasons:
        applied = tuple(item.constraint_id for item in request.policy.constraints)
        evidence = tuple(
            EvidenceReference(reference=item, role="evidence", claim=M0905_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        for feature_id in sorted(item.artifact_id for item in request.source_artifacts):
            value = _numeric_value(feature_id, request)
            estimates.append(
                ConstraintAwareEstimate(
                    feature_id=feature_id,
                    kind=ConstraintEstimateKind.INTERVAL,
                    unit="provisional-normalized-complex-activity",
                    estimate_value=value,
                    lower_bound=round(max(0.0, value - 0.1), 8),
                    upper_bound=round(min(1.0, value + 0.1), 8),
                    support_score=1.0,
                    applied_constraint_ids=applied,
                    evidence=evidence,
                )
            )
    status = (
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
        status=status,
        estimates=tuple(estimates),
        satisfaction_report=tuple(reports),
        abstention_reason=abstention_reason,
        support_decision=support,
        uncertainty=_uncertainty(),
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
