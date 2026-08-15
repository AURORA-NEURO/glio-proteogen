"""Deterministic, conflict-preserving M13-07 plausibility engine."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m13_07 import (
    M1307_CONTRACT_VERSION,
    M1307_MODULE_ID,
    AdjudicateProteotypePlausibilityRequest,
    ControlEvaluation,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityFinding,
    PlausibilityFindingCode,
    PlausibilityGrade,
    ProteotypePlausibilityAdjudicationResult,
    UnresolvedConflict,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    IdentityLineageReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_AUTHORIZATION_MESSAGE: Final = (
    "M13-07 plausibility adjudication requires accepted upstream controls"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}


class PlausibilityAuthorizationError(PermissionError):
    """Raised when execution controls are not accepted."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_MESSAGE)


class PlausibilityReplayError(ValueError):
    """Raised when a result cannot be reproduced from the exact request."""

    def __init__(self, code: str) -> None:
        messages = {
            "request": "result request digest does not match request",
            "result": "result digest does not match deterministic replay",
        }
        super().__init__(messages[code])


class _ContractValidationError(ValueError):
    def __init__(self, subject: str) -> None:
        super().__init__(f"{subject} does not match the M13-07 contract")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M13-07 request values require exact string-keyed JSON objects")


class M1307PlausibilityEngine:
    """Run caller-declared controls without traversing opaque evidence artifacts."""

    __slots__ = ()

    def adjudicate(self, request: object) -> ProteotypePlausibilityAdjudicationResult:
        """Validate, authorize and deterministically seal one adjudication."""

        typed = _validate_typed_request(request)
        return _compute_result(typed)

    def verify(
        self,
        request: object,
        result: object,
    ) -> ProteotypePlausibilityAdjudicationResult:
        """Replay the request and require byte-stable result identity."""

        typed_request = _validate_typed_request(request)
        typed_result = _validate_result(result)
        replayed = _compute_result(typed_request)
        if typed_result.request_digest != canonical_request_digest(typed_request):
            raise PlausibilityReplayError("request")
        if typed_result.result_digest != replayed.result_digest:
            raise PlausibilityReplayError("result")
        return typed_result


def adjudicate_proteotype_plausibility(
    request: object,
) -> ProteotypePlausibilityAdjudicationResult:
    """Public stateless M13-07 operation."""

    return M1307PlausibilityEngine().adjudicate(request)


def verify_plausibility_replay(request: object, result: object) -> bool:
    """Return true only when the complete result is reproducible."""

    M1307PlausibilityEngine().verify(request, result)
    return True


def preflight_plausibility_authorization(candidate: object) -> None:
    """Check seven controls before touching any upstream or evidence payload."""

    authorized = False
    try:
        candidate_type = type(candidate)
        supported = (
            candidate_type is AdjudicateProteotypePlausibilityRequest or candidate_type is dict
        )
        context = _member(candidate, "context") if supported else None
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_STATES
        }
        authorized = supported and states == _EXPECTED_STATES
    except Exception:  # noqa: BLE001 - hostile caller objects fail closed.
        raise PlausibilityAuthorizationError from None
    if not authorized:
        raise PlausibilityAuthorizationError


def _validate_typed_request(candidate: object) -> AdjudicateProteotypePlausibilityRequest:
    preflight_plausibility_authorization(candidate)
    try:
        materialized = _plain_value(candidate)
        return AdjudicateProteotypePlausibilityRequest.model_validate(materialized)
    except (TypeError, ValueError, ValidationError) as error:
        raise _ContractValidationError("request") from error


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> AdjudicateProteotypePlausibilityRequest:
    """Validate the already strict-parsed document without a second raw parse."""

    preflight_plausibility_authorization(candidate)
    try:
        return AdjudicateProteotypePlausibilityRequest.model_validate_json(serialized)
    except (TypeError, ValueError, ValidationError) as error:
        raise _ContractValidationError("request") from error


def _validate_result(candidate: object) -> ProteotypePlausibilityAdjudicationResult:
    try:
        materialized = _plain_value(candidate)
        return ProteotypePlausibilityAdjudicationResult.model_validate(materialized)
    except (TypeError, ValueError, ValidationError) as error:
        raise _ContractValidationError("result") from error


def _compute_result(
    request: AdjudicateProteotypePlausibilityRequest,
) -> ProteotypePlausibilityAdjudicationResult:
    request_digest = canonical_request_digest(request)
    evaluations = tuple(
        ControlEvaluation(
            control_id=control.control_id,
            outcome=control.declared_outcome,
            observed_direction=control.observed_direction,
            rationale=_rationale(control.declared_outcome, control.kind),
            evidence=control.required_evidence,
        )
        for control in request.controls
    )
    blocking = tuple(
        evaluation for evaluation in evaluations if evaluation.outcome is not ControlOutcome.PASSED
    )
    conflicts = _conflicts(request) if request.conflict_declared else ()
    abstained = bool(blocking or conflicts)
    findings = _findings(blocking, conflicts)
    all_evidence = tuple(
        evidence for control in request.controls for evidence in control.required_evidence
    )[:64]
    status = (
        PlausibilityAdjudicationStatus.ABSTAINED
        if abstained
        else PlausibilityAdjudicationStatus.ADJUDICATED
    )
    support_status = (
        SupportStatus.REVIEW_REQUIRED
        if conflicts
        else SupportStatus.UNSUPPORTED
        if blocking
        else SupportStatus.SUPPORTED
    )
    grade = None if abstained else PlausibilityGrade.HIGH
    abstention_reason = None if not abstained else _abstention_reason(blocking, conflicts)
    limitations = (
        _limitation(
            "caller_declared_evidence", "Referenced artifacts are opaque and are not authenticated."
        ),
        _limitation(
            "provisional_abi", "The M13-07 ABI remains provisional pending owner confirmation."
        ),
        _limitation(
            "no_negative_inference",
            "Unsupported or non-evaluable controls never become negative findings.",
        ),
    )
    payload: dict[str, object] = {
        "output_type": "proteotype_plausibility_adjudication",
        "result_id": f"result.m1307.{request_digest.removeprefix('sha256:')}",
        "result_version": M1307_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "grade": grade,
        "evaluations": evaluations,
        "conflicts": conflicts,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": "proteotype",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=support_status,
            reason_code="m1307_conflict" if conflicts else "m1307_control_gate",
            rationale=(
                "All required controls passed with no unresolved conflict."
                if not abstained
                else abstention_reason or "M13-07 cannot safely adjudicate this request."
            ),
        ),
        "uncertainty": _uncertainty(abstained=abstained),
        "provenance": _provenance(request),
        "evidence": all_evidence,
        "limitations": limitations,
        "human_review_required": bool(conflicts or blocking),
    }
    partial = ProteotypePlausibilityAdjudicationResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(partial)
    return ProteotypePlausibilityAdjudicationResult.model_validate(payload)


def _rationale(outcome: ControlOutcome, kind: ControlKind) -> str:
    if outcome is ControlOutcome.PASSED:
        return f"Caller-declared {kind.value} control passed; evidence remains opaque."
    if outcome is ControlOutcome.FAILED:
        return f"Caller-declared {kind.value} control failed; release is blocked."
    if outcome is ControlOutcome.ABSTAINED:
        return f"Caller-declared {kind.value} control abstained; no negative finding is emitted."
    return f"Caller-declared {kind.value} control is not evaluable; support is withheld."


def _conflicts(
    request: AdjudicateProteotypePlausibilityRequest,
) -> tuple[UnresolvedConflict, ...]:
    evidence = tuple(
        evidence for control in request.controls for evidence in control.required_evidence
    )[:64]
    return (
        UnresolvedConflict(
            conflict_id="conflict.m1307.mechanisms",
            description=(
                "Caller declared competing mechanisms that cannot be resolved by this adjudicator."
            ),
            competing_mechanisms=request.candidate_mechanisms,
            evidence=evidence,
        ),
    )


def _findings(
    blocking: tuple[ControlEvaluation, ...],
    conflicts: tuple[UnresolvedConflict, ...],
) -> tuple[PlausibilityFinding, ...]:
    findings = [
        PlausibilityFinding(
            finding_id=f"finding.m1307.{evaluation.control_id}",
            code=(
                PlausibilityFindingCode.CONTROL_FAILED
                if evaluation.outcome is ControlOutcome.FAILED
                else PlausibilityFindingCode.CONTROL_NOT_EVALUABLE
            ),
            message=evaluation.rationale,
            evidence=evaluation.evidence,
        )
        for evaluation in blocking
    ]
    findings.extend(
        PlausibilityFinding(
            finding_id=f"finding.m1307.{conflict.conflict_id}",
            code=PlausibilityFindingCode.UNRESOLVED_CONFLICT,
            message=conflict.description,
            evidence=conflict.evidence,
        )
        for conflict in conflicts
    )
    return tuple(findings)


def _abstention_reason(
    blocking: tuple[ControlEvaluation, ...],
    conflicts: tuple[UnresolvedConflict, ...],
) -> str:
    if conflicts:
        return "Unresolved competing mechanisms require human review."
    if any(item.outcome is ControlOutcome.FAILED for item in blocking):
        return "One or more release-blocking plausibility controls failed."
    return "Required plausibility evidence is unsupported or not evaluable."


def _uncertainty(*, abstained: bool) -> UncertaintyProfile:
    state = EstimateState.NOT_ESTIMABLE if abstained else EstimateState.ESTIMATED
    probability = None if abstained else 0.9
    rationale = (
        "No safe estimate because the support domain is incomplete or conflicting."
        if abstained
        else "Caller-declared controls passed; uncertainty remains explicit and provisional."
    )
    estimate = UncertaintyEstimate(state=state, probability=probability, rationale=rationale)
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Measurement, sampling, parameter, model-form, identification, support and transport "
            "dimensions are reported.",
            "No external artifact content was traversed.",
        ),
    )


def _limitation(code: str, statement: str) -> Limitation:
    return Limitation(code=code, statement=statement)


def _provenance(request: AdjudicateProteotypePlausibilityRequest) -> ProvenanceRecord:
    refs = request.context.references
    entries = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=(
                cast("IdentityLineageReference", reference).binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, reference in entries
    )
    input_digests = (
        request.mechanism_inference_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1307.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1307_MODULE_ID,
        module_version=M1307_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _member(candidate: object, field: str) -> object:
    if type(candidate) is dict:
        return dict.get(cast("dict[object, object]", candidate), field)
    if isinstance(candidate, BaseModel):
        return dict.get(
            cast("dict[object, object]", object.__getattribute__(candidate, "__dict__")), field
        )
    return None


def _state_text(candidate: object) -> object:
    if type(candidate) is str:
        return candidate
    candidate_type = type(candidate)
    if StrEnum in type.__getattribute__(candidate_type, "__mro__"):
        value = object.__getattribute__(candidate, "_value_")
        return value if type(value) is str else None
    return None


def _plain_value(candidate: object) -> object:
    if isinstance(candidate, BaseModel):
        return _plain_value(candidate.model_dump(mode="python"))
    if type(candidate) is dict:
        mapping = cast("dict[object, object]", candidate)
        if any(type(key) is not str for key in mapping):
            raise _InvalidPlainValueError
        return {key: _plain_value(value) for key, value in mapping.items()}
    if type(candidate) is list:
        return [_plain_value(value) for value in cast("list[object]", candidate)]
    if type(candidate) is tuple:
        return tuple(_plain_value(value) for value in cast("tuple[object, ...]", candidate))
    if isinstance(candidate, Mapping):
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M1307PlausibilityEngine",
    "PlausibilityAuthorizationError",
    "PlausibilityReplayError",
    "adjudicate_proteotype_plausibility",
    "preflight_plausibility_authorization",
    "verify_plausibility_replay",
]
