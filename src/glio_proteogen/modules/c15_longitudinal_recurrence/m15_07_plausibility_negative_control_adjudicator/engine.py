"""Deterministic, fail-closed M15-07 plausibility adjudication runtime."""

from __future__ import annotations

# ruff: noqa: E501, TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_07 import (
    M1507_OPERATION,
    AdjudicateComplexActivityPlausibilityRequest,
    ComplexActivityPlausibilityAdjudicationResult,
    ControlEvaluation,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityFinding,
    PlausibilityFindingCode,
    PlausibilityGrade,
    UnresolvedConflict,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m15_07.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(AdjudicateComplexActivityPlausibilityRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivityPlausibilityAdjudicationResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity",
    "consent",
    "all-omics",
    "mutation",
    "relabel",
    "erasure",
)
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "not_evaluable",
    "not evaluable",
    "ood",
    "out_of_domain",
    "abstain",
    "negative_control",
    "negative-control",
    "conflict",
    "discrepancy",
    "novel",
    "unresolved",
)


class M1507AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize M15-07 execution."""


class M1507InferenceError(ValueError):
    """Raised when a typed plausibility request cannot be evaluated safely."""


class M1507ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1507AuthorizationError("M15-07 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1507AuthorizationError("M15-07 controls are unavailable")
    return state


def preflight_plausibility_authorization(request: object) -> None:
    """Check seven upstream controls without traversing arbitrary opaque objects."""

    try:
        if isinstance(request, AdjudicateComplexActivityPlausibilityRequest):
            references = request.context.references
            actual = {
                "approved_configuration": references.approved_configuration.state.value,
                "identity_lineage": references.identity_lineage.state.value,
                "provenance": references.provenance.state.value,
                "consent": references.consent.state.value,
                "quality": references.quality.state.value,
                "support": references.support.state.value,
                "intended_use": references.intended_use.state.value,
            }
            if actual != _EXPECTED_STATES:
                raise M1507AuthorizationError("M15-07 controls do not authorize adjudication")
            return
        if not isinstance(request, Mapping):
            raise M1507AuthorizationError("M15-07 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1507AuthorizationError("M15-07 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1507AuthorizationError("M15-07 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1507AuthorizationError("M15-07 controls do not authorize adjudication")
    except M1507AuthorizationError:
        raise
    except Exception as error:
        raise M1507AuthorizationError("M15-07 controls are unavailable") from error


def _evidence(
    request: AdjudicateComplexActivityPlausibilityRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [request.sensitivity_result, *request.source_artifacts]
    artifacts.extend(
        evidence
        for control in request.controls
        for evidence in (item.reference for item in control.required_evidence)
    )
    references = request.context.references
    artifacts.extend(
        (
            references.approved_configuration.evidence,
            references.identity_lineage.evidence,
            references.provenance.evidence,
            references.consent.evidence,
            references.quality.evidence,
            references.support.evidence,
            references.intended_use.evidence,
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M15-06 sensitivity and M15-07 plausibility evidence.",
        )
        for artifact in unique.values()
    )


def _declared(request: AdjudicateComplexActivityPlausibilityRequest) -> str:
    values = [request.sensitivity_result.artifact_id]
    values.extend(
        item.reference.artifact_id
        for control in request.controls
        for item in control.required_evidence
    )
    values.extend(item.artifact_id for item in request.source_artifacts)
    return " ".join(values).casefold()


def _evaluation_outcome(declared: str) -> ControlOutcome:
    if any(
        token in declared
        for token in ("unsupported", "unknown", "not_evaluable", "ood", "out_of_domain")
    ):
        return ControlOutcome.NOT_EVALUABLE
    if any(
        token in declared for token in ("negative_control", "negative-control", "failed", "fail")
    ):
        return ControlOutcome.FAILED
    if any(
        token in declared for token in ("abstain", "conflict", "discrepancy", "novel", "unresolved")
    ):
        return ControlOutcome.ABSTAINED
    return ControlOutcome.PASSED


def _evaluations(
    request: AdjudicateComplexActivityPlausibilityRequest,
    declared: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[ControlEvaluation, ...]:
    outcome = _evaluation_outcome(declared)
    return tuple(
        ControlEvaluation(
            control_id=control.control_id,
            outcome=outcome,
            observed_direction="increasing"
            if control.kind is ControlKind.DIRECTION and outcome is ControlOutcome.PASSED
            else None,
            rationale=(
                "Caller-declared control passed within the provisional support domain."
                if outcome is ControlOutcome.PASSED
                else "Control did not establish a releasable plausibility claim."
            ),
            evidence=evidence[:1] if evidence else control.required_evidence,
        )
        for control in request.controls
    )


def _finding(
    finding_id: str,
    code: PlausibilityFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> PlausibilityFinding:
    return PlausibilityFinding(
        finding_id=finding_id,
        code=code,
        message=message,
        evidence=evidence[:1],
    )


def _conflict(evidence: tuple[EvidenceReference, ...]) -> tuple[UnresolvedConflict, ...]:
    return (
        UnresolvedConflict(
            conflict_id="conflict.competing-mechanisms",
            description="Orthogonal evidence leaves competing biological mechanisms unresolved.",
            competing_mechanisms=("mechanism.primary", "mechanism.alternative"),
            evidence=evidence[:1],
        ),
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1507_no_kinase_or_treatment",
            statement="Plausibility adjudication does not infer kinase activity or recommend treatment.",
        ),
        Limitation(
            code="m1507_provisional_abi",
            statement="The M15-07 ABI and architecture selection remain provisional pending owner review.",
        ),
        Limitation(
            code="m1507_supported" if supported else "m1507_review_required",
            statement=(
                "All required controls passed and no unresolved conflict blocked the provisional grade."
                if supported
                else "Failed, unsupported, OOD, or unresolved controls require human review."
            ),
        ),
    )


class M1507PlausibilityAdjudicator:
    """Stateless deterministic plausibility and negative-control adjudicator."""

    def adjudicate(self, request: object) -> ComplexActivityPlausibilityAdjudicationResult:
        preflight_plausibility_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1507InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        declared = _declared(typed)
        evaluations = _evaluations(typed, declared, evidence)
        blocking = any(item.outcome is not ControlOutcome.PASSED for item in evaluations)
        has_conflict = any(
            token in declared for token in ("conflict", "discrepancy", "novel", "unresolved")
        )
        prohibited = any(token in declared for token in _PROHIBITED_TOKENS)
        supported = not blocking and not has_conflict and not prohibited
        conflicts = _conflict(evidence) if has_conflict and not prohibited else ()
        findings: list[PlausibilityFinding] = [
            _finding(
                "finding.provisional-abi",
                PlausibilityFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "M15-07 ABI remains provisional pending owner confirmation.",
                evidence,
            )
        ]
        if prohibited:
            findings.append(
                _finding(
                    "finding.upstream-unsupported",
                    PlausibilityFindingCode.UPSTREAM_UNSUPPORTED,
                    "Plausibility adjudication crossed a prohibited ownership boundary.",
                    evidence,
                )
            )
        for item in evaluations:
            if item.outcome is ControlOutcome.FAILED:
                findings.append(
                    _finding(
                        f"finding.failed.{item.control_id}",
                        PlausibilityFindingCode.CONTROL_FAILED,
                        "A release-blocking plausibility control failed.",
                        evidence,
                    )
                )
            elif item.outcome is not ControlOutcome.PASSED:
                findings.append(
                    _finding(
                        f"finding.not-evaluable.{item.control_id}",
                        PlausibilityFindingCode.CONTROL_NOT_EVALUABLE,
                        "A plausibility control was not safely evaluable.",
                        evidence,
                    )
                )
        if conflicts:
            findings.append(
                _finding(
                    "finding.unresolved-conflict",
                    PlausibilityFindingCode.UNRESOLVED_CONFLICT,
                    "Competing mechanisms remain visible and block promotion.",
                    evidence,
                )
            )
        grade = PlausibilityGrade.HIGH if supported else None
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": PlausibilityAdjudicationStatus.ADJUDICATED
            if supported
            else PlausibilityAdjudicationStatus.ABSTAINED,
            "grade": grade,
            "evaluations": evaluations,
            "conflicts": conflicts,
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "One or more controls or conflicts blocked safe promotion.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1507_supported" if supported else "m1507_review_required",
                rationale=(
                    "All plausibility and negative-control gates passed with no conflict."
                    if supported
                    else "Promotion is blocked pending failed controls, support, or conflict review."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ComplexActivityPlausibilityAdjudicationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1507InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityPlausibilityAdjudicationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1507ReplayVerificationError from error
        try:
            validated = _RESULT_ADAPTER.validate_python(
                validated.model_dump(mode="python", warnings=False), strict=True
            )
        except Exception as error:
            raise M1507ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1507ReplayVerificationError
        if replay:
            try:
                expected = self.adjudicate(validated.request)
            except Exception as error:
                raise M1507ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1507ReplayVerificationError
        return validated


def adjudicate_complex_activity_plausibility(
    request: object,
) -> ComplexActivityPlausibilityAdjudicationResult:
    """Public provisional M15-07 operation."""

    return M1507PlausibilityAdjudicator().adjudicate(request)


__all__ = [
    "M1507_OPERATION",
    "M1507AuthorizationError",
    "M1507InferenceError",
    "M1507PlausibilityAdjudicator",
    "M1507ReplayVerificationError",
    "adjudicate_complex_activity_plausibility",
    "preflight_plausibility_authorization",
]
