"""Deterministic, fail-closed M14-07 plausibility adjudicator."""

from __future__ import annotations

# ruff: noqa: TRY003, TRY301
from collections.abc import Mapping
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_07 import (
    AdjudicateProteinSubtypePlausibilityRequest,
    ControlEvaluation,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityFinding,
    PlausibilityFindingCode,
    PlausibilityGrade,
    ProteinSubtypePlausibilityAdjudicationResult,
    UnresolvedConflict,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(AdjudicateProteinSubtypePlausibilityRequest)
_RESULT_ADAPTER = TypeAdapter(ProteinSubtypePlausibilityAdjudicationResult)
_SUPPORTED_KINDS: Final = frozenset(ControlKind)
_BLOCKING_OUTCOMES: Final = frozenset(
    {ControlOutcome.FAILED, ControlOutcome.NOT_EVALUABLE, ControlOutcome.ABSTAINED}
)


class M1407AuthorizationError(ValueError):
    """Raised when required upstream controls do not authorize adjudication."""


class M1407InferenceError(ValueError):
    """Raised when a typed plausibility request cannot be safely evaluated."""


class M1407ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _control_state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1407AuthorizationError("M14-07 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1407AuthorizationError("M14-07 controls are unavailable")
    return state


def preflight_plausibility_authorization(request: object) -> None:
    """Check seven upstream controls without traversing arbitrary opaque objects."""

    try:
        if isinstance(request, AdjudicateProteinSubtypePlausibilityRequest):
            references = request.context.references
            if (
                references.approved_configuration.state.value != "accepted"
                or references.identity_lineage.state.value != "resolved"
                or references.provenance.state.value != "accepted"
                or references.consent.state.value != "granted"
                or references.quality.state.value != "accepted"
                or references.support.state.value != "accepted"
                or references.intended_use.state.value != "accepted"
            ):
                raise M1407AuthorizationError("M14-07 controls do not authorize adjudication")
            return
        if not isinstance(request, Mapping):
            raise M1407AuthorizationError("M14-07 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1407AuthorizationError("M14-07 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1407AuthorizationError("M14-07 request controls are unavailable")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        for role, state in expected.items():
            if _control_state(raw_references.get(role)) != state:
                raise M1407AuthorizationError("M14-07 controls do not authorize adjudication")
    except M1407AuthorizationError:
        raise
    except Exception as error:
        raise M1407AuthorizationError("M14-07 controls are unavailable") from error


def _evidence(
    request: AdjudicateProteinSubtypePlausibilityRequest,
) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [
        request.mechanism_inference_result,
        *request.source_artifacts,
        *(item.reference for control in request.controls for item in control.required_evidence),
    ]
    unique: dict[str, ArtifactReference] = {item.digest: item for item in references}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M14-07 plausibility and negative-control evidence.",
        )
        for artifact in unique.values()
    )


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="m1407_no_kinase_or_treatment",
            statement=(
                "Plausibility adjudication does not infer kinase activity or recommend treatment."
            ),
        ),
        Limitation(
            code="m1407_provisional_abi",
            statement=(
                "The M14-07 ABI and control vocabulary remain provisional pending owner review."
            ),
        ),
        Limitation(
            code=("m1407_controls_passed" if supported else "m1407_controls_blocked"),
            statement=(
                "All release-blocking controls passed in the declared support domain."
                if supported
                else "Failed, unresolved, conflicted, or unsupported controls block release."
            ),
        ),
    )


def _finding(
    finding_id: str,
    code: PlausibilityFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> PlausibilityFinding:
    return PlausibilityFinding(
        finding_id=finding_id, code=code, message=message, evidence=evidence[:1]
    )


def _evaluate_control(
    control_id: str,
    criterion: str,
    expected_direction: str | None,
    evidence: tuple[EvidenceReference, ...],
) -> ControlEvaluation:
    lowered = criterion.casefold()
    outcome = ControlOutcome.PASSED
    if any(
        token in lowered
        for token in ("not_evaluable", "not evaluable", "unsupported", "unresolved", "unknown")
    ):
        outcome = ControlOutcome.NOT_EVALUABLE
    elif "abstain" in lowered:
        outcome = ControlOutcome.ABSTAINED
    elif any(token in lowered for token in ("fail", "incompatible", "negative control")):
        outcome = ControlOutcome.FAILED
    return ControlEvaluation(
        control_id=control_id,
        outcome=outcome,
        observed_direction=expected_direction or "consistent",
        rationale=(
            "Declared criterion is consistent with the deterministic negative-control gate."
            if outcome is ControlOutcome.PASSED
            else "Declared criterion is outside the safely passing control domain."
        ),
        evidence=evidence[:1],
    )


class M1407PlausibilityAdjudicator:
    """Stateless deterministic control adjudicator and plausibility grader."""

    def infer(self, request: object) -> ProteinSubtypePlausibilityAdjudicationResult:
        preflight_plausibility_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1407InferenceError from error
        request_digest = sha256_digest(typed.model_dump(mode="json"))
        evidence = _evidence(typed)
        evaluations = tuple(
            _evaluate_control(
                control.control_id,
                control.criterion,
                control.expected_direction,
                tuple(
                    EvidenceReference(
                        reference=item.reference,
                        role="evidence",
                        claim=item.claim,
                    )
                    for item in control.required_evidence
                ),
            )
            for control in typed.controls
        )
        control_kinds = {control.kind for control in typed.controls}
        missing_kinds = _SUPPORTED_KINDS - control_kinds
        conflict_controls = tuple(
            control
            for control in typed.controls
            if control.criterion.casefold().startswith("conflict:")
        )
        conflicts = tuple(
            UnresolvedConflict(
                conflict_id=f"conflict.{control.control_id}",
                description=(
                    "Competing mechanisms remain unresolved under a release-blocking control."
                ),
                competing_mechanisms=("mechanism.primary", "mechanism.alternate"),
                evidence=evidence[:1],
            )
            for control in conflict_controls
        )
        blocking = bool(
            missing_kinds
            or conflicts
            or any(item.outcome in _BLOCKING_OUTCOMES for item in evaluations)
        )
        findings: list[PlausibilityFinding] = [
            _finding(
                "finding.provisional-abi",
                PlausibilityFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "M14-07 ABI remains provisional pending owner confirmation.",
                evidence,
            )
        ]
        if missing_kinds:
            findings.append(
                _finding(
                    "finding.controls-missing",
                    PlausibilityFindingCode.CONTROL_NOT_EVALUABLE,
                    "All six plausibility control kinds are required for adjudication.",
                    evidence,
                )
            )
        if any(item.outcome is ControlOutcome.FAILED for item in evaluations):
            findings.append(
                _finding(
                    "finding.control-failed",
                    PlausibilityFindingCode.CONTROL_FAILED,
                    "A release-blocking plausibility control failed.",
                    evidence,
                )
            )
        if any(
            item.outcome in {ControlOutcome.NOT_EVALUABLE, ControlOutcome.ABSTAINED}
            for item in evaluations
        ):
            findings.append(
                _finding(
                    "finding.control-not-evaluable",
                    PlausibilityFindingCode.CONTROL_NOT_EVALUABLE,
                    "A release-blocking plausibility control was not safely evaluable.",
                    evidence,
                )
            )
        if conflicts:
            findings.append(
                _finding(
                    "finding.unresolved-conflict",
                    PlausibilityFindingCode.UNRESOLVED_CONFLICT,
                    "Competing mechanisms remain visible and block release.",
                    evidence,
                )
            )
        supported = not blocking
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": PlausibilityAdjudicationStatus.ADJUDICATED
            if supported
            else PlausibilityAdjudicationStatus.ABSTAINED,
            "grade": PlausibilityGrade.HIGH if supported else None,
            "evaluations": evaluations,
            "conflicts": conflicts,
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "One or more release-blocking plausibility controls failed or were unresolved.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1407_controls_passed" if supported else "m1407_controls_blocked",
                rationale=(
                    "All required negative-control checks passed."
                    if supported
                    else "Release is blocked pending control resolution or human review."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported),
            "human_review_required": not supported,
        }
        constructed = ProteinSubtypePlausibilityAdjudicationResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1407InferenceError from error

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ProteinSubtypePlausibilityAdjudicationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1407ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1407ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1407ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1407ReplayVerificationError
        return validated


def adjudicate_protein_subtype_plausibility(
    request: object,
) -> ProteinSubtypePlausibilityAdjudicationResult:
    """Public provisional M14-07 operation."""

    return M1407PlausibilityAdjudicator().infer(request)


__all__ = [
    "M1407AuthorizationError",
    "M1407InferenceError",
    "M1407PlausibilityAdjudicator",
    "M1407ReplayVerificationError",
    "adjudicate_protein_subtype_plausibility",
    "preflight_plausibility_authorization",
]
