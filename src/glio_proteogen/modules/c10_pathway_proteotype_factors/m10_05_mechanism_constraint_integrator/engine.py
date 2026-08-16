"""Deterministic, replay-bound M10-05 mechanism integration runtime."""

from __future__ import annotations

from collections.abc import Mapping
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


def _support(status: SupportStatus, reason: str) -> SupportDecision:
    return SupportDecision(status=status, reason_code=f"m1005_{reason}", rationale=reason)


def _limitations(*, integrated: bool, soft_conflict: bool) -> tuple[Limitation, ...]:
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
                "Only the closed true/false expression vocabulary is evaluated; all other "
                "expressions abstain rather than being interpreted heuristically."
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
    return tuple(values)


class M1005ConstraintEngine:
    """Evaluate a closed expression vocabulary and rederive every result region."""

    __slots__ = ()

    def integrate(self, request: object) -> ProteinRnaConstraintIntegrationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
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
        for constraint in request.constraint_set.constraints:
            outcome = _evaluate_expression(constraint.expression)
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
                if outcome is ConstraintEvaluationOutcome.SATISFIED:
                    weighted_score += weight
                effect = weight if outcome is ConstraintEvaluationOutcome.SATISFIED else 0.0
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
                    residual=(0.0 if outcome is ConstraintEvaluationOutcome.SATISFIED else 1.0),
                    effect_size=(
                        constraint.weight if constraint.hardness is ConstraintHardness.SOFT else 1.0
                    ),
                    message=(
                        "closed expression satisfied"
                        if outcome is ConstraintEvaluationOutcome.SATISFIED
                        else "closed expression was not satisfied or evaluable"
                    ),
                    evidence=constraint.evidence,
                )
            )
        integrated = not hard_violated and not not_evaluable
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
            status = ConstraintIntegrationStatus.ABSTAINED
            support = _support(
                SupportStatus.REVIEW_REQUIRED if hard_violated else SupportStatus.UNSUPPORTED,
                "hard_constraint_violation" if hard_violated else "constraint_not_evaluable",
            )
            reason = (
                "A hard constraint was violated; no estimate is emitted."
                if hard_violated
                else "At least one constraint is outside the closed evaluation vocabulary."
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
            "evaluations": tuple(evaluations),
            "ablations": tuple(ablations),
            "abstention_reason": reason,
            "parent_target": M1005_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": expected_uncertainty(integrated=integrated),
            "provenance": expected_provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(integrated=integrated, soft_conflict=soft_conflict),
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
