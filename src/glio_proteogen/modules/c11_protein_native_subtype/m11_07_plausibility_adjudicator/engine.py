"""Deterministic, conflict-preserving M11-07 plausibility engine."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m11_07 import (
    M1107_CONTRACT_VERSION,
    M1107_MODULE_ID,
    AdjudicateVariantPeptidePlausibilityRequest,
    ControlEvaluation,
    ControlKind,
    ControlOutcome,
    PlausibilityAdjudicationStatus,
    PlausibilityFinding,
    PlausibilityFindingCode,
    PlausibilityGrade,
    UnresolvedConflict,
    VariantPeptidePlausibilityAdjudicationResult,
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
    "M11-07 plausibility adjudication requires accepted upstream controls"
)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MAX_PLAIN_DEPTH: Final = 64
_MAX_PLAIN_DICT_ITEMS: Final = 512
_MAX_PLAIN_SEQUENCE_ITEMS: Final = 4_096
_MAX_PLAIN_NODES: Final = 100_000
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
        super().__init__(f"{subject} does not match the M11-07 contract")


class _InvalidPlainValueError(TypeError):
    def __init__(self) -> None:
        super().__init__("M11-07 request values require exact string-keyed JSON objects")


class M1107PlausibilityEngine:
    """Run caller-declared controls without traversing opaque evidence artifacts."""

    __slots__ = ()

    def adjudicate(self, request: object) -> VariantPeptidePlausibilityAdjudicationResult:
        """Validate, authorize and deterministically seal one adjudication."""

        typed = _validate_typed_request(request)
        return _compute_result(typed)

    def verify(
        self,
        request: object,
        result: object,
    ) -> VariantPeptidePlausibilityAdjudicationResult:
        """Replay the request and require byte-stable result identity."""

        typed_request = _validate_typed_request(request)
        typed_result = _validate_result(result)
        replayed = _compute_result(typed_request)
        if typed_result.request_digest != canonical_request_digest(typed_request):
            raise PlausibilityReplayError("request")
        if typed_result.result_digest != replayed.result_digest:
            raise PlausibilityReplayError("result")
        return typed_result


def adjudicate_variant_peptide_plausibility(
    request: object,
) -> VariantPeptidePlausibilityAdjudicationResult:
    """Public stateless M11-07 operation."""

    return M1107PlausibilityEngine().adjudicate(request)


def verify_plausibility_replay(request: object, result: object) -> bool:
    """Return true only when the complete result is reproducible."""

    M1107PlausibilityEngine().verify(request, result)
    return True


def preflight_plausibility_authorization(candidate: object) -> None:
    """Check seven controls before touching any upstream or evidence payload."""

    authorized = False
    try:
        candidate_type = type(candidate)
        supported = (
            candidate_type is AdjudicateVariantPeptidePlausibilityRequest or candidate_type is dict
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


def _validate_typed_request(candidate: object) -> AdjudicateVariantPeptidePlausibilityRequest:
    preflight_plausibility_authorization(candidate)
    try:
        materialized = _plain_value(candidate)
        return AdjudicateVariantPeptidePlausibilityRequest.model_validate(materialized)
    except (TypeError, ValueError, ValidationError) as error:
        raise _ContractValidationError("request") from error


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> AdjudicateVariantPeptidePlausibilityRequest:
    """Validate the already strict-parsed document without a second raw parse."""

    preflight_plausibility_authorization(candidate)
    try:
        return AdjudicateVariantPeptidePlausibilityRequest.model_validate_json(serialized)
    except (TypeError, ValueError, ValidationError) as error:
        raise _ContractValidationError("request") from error


def _validate_result(candidate: object) -> VariantPeptidePlausibilityAdjudicationResult:
    try:
        materialized = _plain_value(candidate)
        return VariantPeptidePlausibilityAdjudicationResult.model_validate(materialized)
    except (TypeError, ValueError, ValidationError) as error:
        raise _ContractValidationError("result") from error


def _compute_result(
    request: AdjudicateVariantPeptidePlausibilityRequest,
) -> VariantPeptidePlausibilityAdjudicationResult:
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
            "provisional_abi", "The M11-07 ABI remains provisional pending owner confirmation."
        ),
        _limitation(
            "no_negative_inference",
            "Unsupported or non-evaluable controls never become negative findings.",
        ),
    )
    payload: dict[str, object] = {
        "output_type": "variant_peptide_plausibility_adjudication",
        "result_id": f"result.m1107.{request_digest.removeprefix('sha256:')}",
        "result_version": M1107_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "grade": grade,
        "evaluations": evaluations,
        "conflicts": conflicts,
        "findings": findings,
        "abstention_reason": abstention_reason,
        "parent_target": "variant_peptide",
        "emits_parent": False,
        "support_decision": SupportDecision(
            status=support_status,
            reason_code="m1107_conflict" if conflicts else "m1107_control_gate",
            rationale=(
                "All required controls passed with no unresolved conflict."
                if not abstained
                else abstention_reason or "M11-07 cannot safely adjudicate this request."
            ),
        ),
        "uncertainty": _uncertainty(abstained=abstained),
        "provenance": _provenance(request),
        "evidence": all_evidence,
        "limitations": limitations,
        "human_review_required": bool(conflicts or blocking),
    }
    partial = VariantPeptidePlausibilityAdjudicationResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(partial)
    return VariantPeptidePlausibilityAdjudicationResult.model_validate(payload)


def _rationale(outcome: ControlOutcome, kind: ControlKind) -> str:
    if outcome is ControlOutcome.PASSED:
        return f"Caller-declared {kind.value} control passed; evidence remains opaque."
    if outcome is ControlOutcome.FAILED:
        return f"Caller-declared {kind.value} control failed; release is blocked."
    if outcome is ControlOutcome.ABSTAINED:
        return f"Caller-declared {kind.value} control abstained; no negative finding is emitted."
    return f"Caller-declared {kind.value} control is not evaluable; support is withheld."


def _conflicts(
    request: AdjudicateVariantPeptidePlausibilityRequest,
) -> tuple[UnresolvedConflict, ...]:
    evidence = tuple(
        evidence for control in request.controls for evidence in control.required_evidence
    )[:64]
    return (
        UnresolvedConflict(
            conflict_id="conflict.m1107.mechanisms",
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
            finding_id=f"finding.m1107.{evaluation.control_id}",
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
            finding_id=f"finding.m1107.{conflict.conflict_id}",
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


def _provenance(request: AdjudicateVariantPeptidePlausibilityRequest) -> ProvenanceRecord:
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
        activity_id=f"activity.m1107.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1107_MODULE_ID,
        module_version=M1107_CONTRACT_VERSION,
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


def _plain_value(  # noqa: C901 - exact built-in traversal firewall.
    candidate: object,
    *,
    _depth: int = 0,
    _budget: list[int] | None = None,
) -> object:
    if _depth > _MAX_PLAIN_DEPTH:
        raise _InvalidPlainValueError
    budget = [_MAX_PLAIN_NODES] if _budget is None else _budget
    budget[0] -= 1
    if budget[0] < 0:
        raise _InvalidPlainValueError
    if isinstance(candidate, BaseModel):
        return _plain_value(
            candidate.model_dump(mode="python"),
            _depth=_depth + 1,
            _budget=budget,
        )
    if type(candidate) is dict:
        mapping = cast("dict[object, object]", candidate)
        if len(mapping) > _MAX_PLAIN_DICT_ITEMS or any(type(key) is not str for key in mapping):
            raise _InvalidPlainValueError
        return {
            key: _plain_value(value, _depth=_depth + 1, _budget=budget)
            for key, value in mapping.items()
        }
    if type(candidate) is list:
        values = cast("list[object]", candidate)
        if len(values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return [_plain_value(value, _depth=_depth + 1, _budget=budget) for value in values]
    if type(candidate) is tuple:
        tuple_values = cast("tuple[object, ...]", candidate)
        if len(tuple_values) > _MAX_PLAIN_SEQUENCE_ITEMS:
            raise _InvalidPlainValueError
        return tuple(
            _plain_value(value, _depth=_depth + 1, _budget=budget) for value in tuple_values
        )
    if isinstance(candidate, Mapping):
        raise _InvalidPlainValueError
    return candidate


__all__ = [
    "M1107PlausibilityEngine",
    "PlausibilityAuthorizationError",
    "PlausibilityReplayError",
    "adjudicate_variant_peptide_plausibility",
    "preflight_plausibility_authorization",
    "verify_plausibility_replay",
]
