"""Deterministic M08-01 formal-state validation and replay boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_01 import (
    M0801_CONTRACT_VERSION,
    M0801_EVIDENCE_CLAIM,
    M0801_MAX_CANONICAL_REQUEST_BYTES,
    M0801_PARENT,
    TranscriptProteinInvariantResult,
    TranscriptProteinInvariantSeverity,
    TranscriptProteinInvariantStatus,
    TranscriptProteinMissingness,
    TranscriptProteinValidationStatus,
    ValidateTranscriptProteinStateRequest,
    ValidateTranscriptProteinStateResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c08_transcript_protein.m08_01_formal_state.kernel import (
    M0801FormalStateKernel,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateTranscriptProteinStateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ValidateTranscriptProteinStateResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0801FormalStateAuthorizationError(PermissionError):
    """Raised before feature traversal if a required upstream control is unsafe."""

    def __init__(self) -> None:
        super().__init__(
            "M08-01 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_formal_state_authorization(candidate: object) -> None:
    """Check controls before the request schema or feature values are traversed."""

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
        raise M0801FormalStateAuthorizationError from None
    if states != expected:
        raise M0801FormalStateAuthorizationError


def _validate_typed_request(candidate: object) -> ValidateTranscriptProteinStateRequest:
    preflight_formal_state_authorization(candidate)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ValidateTranscriptProteinStateRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0801_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M08-01 canonical request exceeds its byte limit")  # noqa: TRY003
    preflight_formal_state_authorization(candidate)
    raw = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M08-01 validates declared state and does not estimate a biological quantity.",
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
            "Measurement, sampling, parameter, model-form, identification, support, "
            "and transport estimation remain outside this formal-state boundary.",
        ),
    )


def _evidence(request: ValidateTranscriptProteinStateRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0801_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: ValidateTranscriptProteinStateRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    records = (
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
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=(
                getattr(reference, "binding_digest", None)
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, reference in records
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M08-01",
        module_version=M0801_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest,),
        configuration_digest=sha256_digest(request.state_schema),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="formal_state_only",
            statement="Output is limited to schema and executable invariant validation.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no protein subtype, proteotype, or treatment recommendation."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement="ABI, feature catalogue, and migration rules remain provisional.",
        ),
    )


class M0801FormalStateEngine:
    """Validate formal transcript-protein state without arbitrary expression execution."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0801FormalStateKernel | None = None) -> None:
        self._kernel = kernel or M0801FormalStateKernel()

    def validate(self, request: object) -> ValidateTranscriptProteinStateResult:
        return self.validate_validated(_validate_typed_request(request))

    def validate_validated(
        self,
        request: ValidateTranscriptProteinStateRequest,
    ) -> ValidateTranscriptProteinStateResult:
        if not isinstance(request, ValidateTranscriptProteinStateRequest):
            raise TypeError("M08-01 requires a validated request")  # noqa: TRY003
        return self._result(request)

    def _result(
        self,
        request: ValidateTranscriptProteinStateRequest,
    ) -> ValidateTranscriptProteinStateResult:
        request_hash = canonical_request_digest(request)
        values = {value.feature_id: value for value in request.values}
        invariant_results = tuple(
            TranscriptProteinInvariantResult(
                invariant_id=invariant.invariant_id,
                status=status,
                message=message,
            )
            for invariant in request.state_schema.invariants
            for status, message in (self._kernel.evaluate_invariant(invariant, values),)
        )
        statuses = {item.status for item in invariant_results}
        missing = any(
            value.state is not TranscriptProteinMissingness.OBSERVED for value in request.values
        )
        hard_violation = any(
            item.status is TranscriptProteinInvariantStatus.VIOLATED
            and next(
                invariant.severity
                for invariant in request.state_schema.invariants
                if invariant.invariant_id == item.invariant_id
            )
            is TranscriptProteinInvariantSeverity.ERROR
            for item in invariant_results
        )
        if missing:
            status = TranscriptProteinValidationStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="m0801_missing_or_unsupported_value",
                rationale=(
                    "Missingness is explicit and cannot be converted into a negative state claim."
                ),
            )
        elif TranscriptProteinInvariantStatus.NOT_EVALUABLE in statuses:
            status = TranscriptProteinValidationStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0801_invariant_not_evaluable",
                rationale="At least one invariant is outside the safe declarative evaluator.",
            )
        elif hard_violation:
            status = TranscriptProteinValidationStatus.INVALID
            support = SupportDecision(
                status=SupportStatus.LIMITED,
                reason_code="m0801_hard_invariant_violated",
                rationale="One or more error-severity formal-state invariants are violated.",
            )
        else:
            status = TranscriptProteinValidationStatus.VALID
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0801_invariants_satisfied",
                rationale="All executable error-severity invariants are satisfied.",
            )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0801_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "support_decision": support,
            "invariant_results": invariant_results,
            "parent_target": M0801_PARENT,
            "emits_parent": False,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
        }
        constructed = ValidateTranscriptProteinStateResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def verify_m0801_result(result: object) -> ValidateTranscriptProteinStateResult:
    """Revalidate a result and its request/result digests before downstream use."""

    typed = _RESULT_ADAPTER.validate_python(result, strict=True)
    if typed.request_digest != canonical_request_digest(typed.request):
        raise ValueError("M08-01 request digest verification failed")  # noqa: TRY003
    if typed.result_digest != result_payload_digest(typed):
        raise ValueError("M08-01 result digest verification failed")  # noqa: TRY003
    return typed


def validate_transcript_protein_formal_state(
    request: object,
) -> ValidateTranscriptProteinStateResult:
    """Public provisional M08-01 operation."""

    return M0801FormalStateEngine().validate(request)


__all__ = [
    "M0801FormalStateAuthorizationError",
    "M0801FormalStateEngine",
    "_validate_json_request",
    "_validate_typed_request",
    "preflight_formal_state_authorization",
    "validate_transcript_protein_formal_state",
    "verify_m0801_result",
]
