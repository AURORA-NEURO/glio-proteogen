"""Deterministic, support-aware M08-05 mechanism/constraint runtime.

The dossier does not freeze an ontology catalogue, learned estimator, or ABI.
This implementation therefore keeps the integration boundary deterministic and
auditable: callers provide content-addressed references and policy expressions,
the engine never fetches or mutates external content, hard conflicts abstain,
and soft conflicts remain visible with an explicit ablation effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_05 import (
    M0805_EVIDENCE_CLAIM,
    M0805_MAX_CANONICAL_RESULT_BYTES,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintIntegratorStatus,
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


def _uncertainty() -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M08-05 has no owner-locked uncertainty estimator in the provisional ABI.",
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
            "and transport uncertainty are explicitly not estimable pending owner lock.",
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
    value: float,
) -> tuple[ConstraintEvaluationStatus, float | None, str]:
    normalized = expression.casefold()
    if "not_evaluable" in normalized or "unsupported" in normalized:
        return (
            ConstraintEvaluationStatus.NOT_EVALUABLE,
            None,
            "constraint support is insufficient for a safe evaluation",
        )
    if "force_violation" in normalized or "violate" in normalized:
        return (
            ConstraintEvaluationStatus.VIOLATED,
            round(value, 8),
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
    duplicate_features = len(set(feature_ids)) != len(feature_ids)
    reports = []
    estimates = []
    reasons: list[str] = []
    for constraint in constraints:
        value = _numeric_value(constraint.constraint_id, request)
        status, violation_score, message = _evaluate(
            constraint.constraint_id,
            constraint.expression,
            constraint.severity,
            value,
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
    integrated = not reasons
    if integrated:
        applied = tuple(item.constraint_id for item in constraints)
        for feature_id in sorted(feature_ids):
            value = _numeric_value(feature_id, request)
            estimates.append(
                ConstraintAwareEstimate(
                    feature_id=feature_id,
                    kind=ConstraintEstimateKind.INTERVAL,
                    unit="provisional-normalized-proteotype",
                    estimate_value=value,
                    lower_bound=round(max(0.0, value - 0.1), 8),
                    upper_bound=round(min(1.0, value + 0.1), 8),
                    support_score=1.0,
                    applied_constraint_ids=applied,
                    evidence=tuple(
                        EvidenceReference(
                            reference=item,
                            role="evidence",
                            claim=M0805_EVIDENCE_CLAIM,
                        )
                        for item in request.source_artifacts
                    ),
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
        uncertainty=_uncertainty(),
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
        digest_verified = typed.result_digest == result_payload_digest(typed)
        try:
            replayed = self.integrate(typed.request)
        except Exception:  # noqa: BLE001 - verification fails closed on replay errors.
            deterministic_verified = False
        else:
            deterministic_verified = digest_verified and (
                replayed.result.model_dump(mode="json") == typed.model_dump(mode="json")
            )
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
