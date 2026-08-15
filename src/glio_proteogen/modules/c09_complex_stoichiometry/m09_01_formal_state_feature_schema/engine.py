"""Deterministic, replay-bound M09-01 formal-state validation runtime."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m09_01 import (
    M0901_CONTRACT_VERSION,
    M0901_EVIDENCE_CLAIM,
    M0901_MAX_CANONICAL_REQUEST_BYTES,
    M0901_MAX_CANONICAL_RESULT_BYTES,
    M0901_MODULE_ID,
    M0901_PARENT,
    ComplexActivityInvariantResult,
    ComplexActivityInvariantStatus,
    ComplexActivityMissingness,
    ComplexActivityValidationStatus,
    ValidateComplexActivityStateRequest,
    ValidateComplexActivityStateResult,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.kernel.strict_json import strict_json_loads

from .kernel import M0901FormalStateKernel

if TYPE_CHECKING:
    from collections.abc import Mapping

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateComplexActivityStateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ValidateComplexActivityStateResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0901AuthorizationError(PermissionError):
    """Raised before formal-state traversal when upstream controls are not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M09-01 requires accepted controls, resolved identity, and granted consent"
        )


class M0901InputError(ValueError):
    """Raised when a replay or bounded-result input is not internally consistent."""

    _MESSAGES: Final = {
        "request_limit": "M09-01 canonical request exceeds its byte limit",
        "result_limit": "M09-01 canonical result exceeds its byte limit",
    }

    def __init__(self, code: str) -> None:
        super().__init__(self._MESSAGES.get(code, "M09-01 input rejected"))


@dataclass(frozen=True, slots=True)
class M0901ReplayVerification:
    """Stable replay verification outcome without exposing submitted payloads."""

    verified: bool
    reason: str


@dataclass(frozen=True, slots=True)
class BuiltM0901Result:
    """Typed result paired with the exact canonical bytes used for its digest."""

    result: ValidateComplexActivityStateResult
    canonical_bytes: bytes


def _member(value: object, field: str) -> object:
    if isinstance(value, MappingABC):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_formal_state_authorization(candidate: object) -> None:
    """Check every required control before reading schema values or evidence."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = {
            "approved_configuration": "accepted",
            "identity_lineage": "resolved",
            "provenance": "accepted",
            "consent": "granted",
            "quality": "accepted",
            "support": "accepted",
            "intended_use": "accepted",
        }
        states = {role: _state(_member(_member(references, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M0901AuthorizationError from None
    if states != expected:
        raise M0901AuthorizationError


def _validate_typed_request(candidate: object) -> ValidateComplexActivityStateRequest:
    preflight_formal_state_authorization(candidate)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> ValidateComplexActivityStateRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0901_MAX_CANONICAL_REQUEST_BYTES:
        raise M0901InputError("request_limit")
    preflight_formal_state_authorization(candidate)
    raw = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M09-01 validates formal state and does not estimate biological quantities.",
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
            "Estimator uncertainty remains owned by downstream complex-activity modules.",
            (
                "Validation abstention is explicit for missing, unsupported, or "
                "non-evaluable evidence."
            ),
        ),
    )


def _evidence(request: ValidateComplexActivityStateRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0901_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _provenance(
    request: ValidateComplexActivityStateRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    records = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage),
        (ControlRole.PROVENANCE, references.provenance),
        (ControlRole.CONSENT, references.consent),
        (ControlRole.QUALITY, references.quality),
        (ControlRole.SUPPORT, references.support),
        (ControlRole.INTENDED_USE, references.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=_state(reference.state),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=(
                reference.binding_digest if role is ControlRole.IDENTITY_LINEAGE else None
            ),
        )
        for role, reference in records
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0901_MODULE_ID,
        module_version=M0901_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(request_digest,),
        configuration_digest=sha256_digest(request.state_schema),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=decisions,
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="formal_state_only",
            statement="Output is limited to schema, units, missingness, and invariant validation.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module supports complex activity but emits no complex activity estimate."
            ),
        ),
        Limitation(
            code="no_kinase_or_treatment",
            statement=(
                "Kinase state and direct treatment recommendation remain outside this boundary."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement="Public ABI, feature catalogue, and migration policy remain provisional.",
        ),
    )


class M0901FormalStateEngine:
    """Validate formal complex-activity states without arbitrary expression execution."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0901FormalStateKernel | None = None) -> None:
        self._kernel = kernel or M0901FormalStateKernel()

    def validate(self, request: object) -> BuiltM0901Result:
        return self.validate_validated(_validate_typed_request(request))

    def validate_validated(
        self,
        request: ValidateComplexActivityStateRequest,
    ) -> BuiltM0901Result:
        if not isinstance(request, ValidateComplexActivityStateRequest):
            raise TypeError("M09-01 requires a validated request")  # noqa: TRY003
        return self._build(request)

    def _build(self, request: ValidateComplexActivityStateRequest) -> BuiltM0901Result:
        request_hash = canonical_request_digest(request)
        values = {value.feature_id: value for value in request.values}
        invariant_results = tuple(
            ComplexActivityInvariantResult(
                invariant_id=invariant.invariant_id,
                status=status,
                message=message,
            )
            for invariant in request.state_schema.invariants
            for status, message in (self._kernel.evaluate_invariant(invariant, values),)
        )
        statuses = {item.status for item in invariant_results}
        missing = any(
            value.state is not ComplexActivityMissingness.OBSERVED for value in request.values
        )
        if missing:
            status = ComplexActivityValidationStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="m0901_missing_or_unsupported_value",
                rationale=(
                    "Missingness is explicit and cannot be converted to a negative "
                    "validation result."
                ),
            )
        elif ComplexActivityInvariantStatus.NOT_EVALUABLE in statuses:
            status = ComplexActivityValidationStatus.ABSTAINED
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0901_invariant_not_evaluable",
                rationale="At least one invariant is outside the bounded declarative evaluator.",
            )
        elif ComplexActivityInvariantStatus.VIOLATED in statuses:
            status = ComplexActivityValidationStatus.INVALID
            support = SupportDecision(
                status=SupportStatus.LIMITED,
                reason_code="m0901_invariant_violated",
                rationale="One or more declared formal-state invariants are violated.",
            )
        else:
            status = ComplexActivityValidationStatus.VALID
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0901_invariants_satisfied",
                rationale="All observed values satisfy the declared formal-state invariants.",
            )
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0901_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "support_decision": support,
            "invariant_results": invariant_results,
            "parent_target": M0901_PARENT,
            "emits_parent": False,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
        }
        constructed = ValidateComplexActivityStateResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        result = _RESULT_ADAPTER.validate_python(payload, strict=True)
        canonical = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical) > M0901_MAX_CANONICAL_RESULT_BYTES:
            raise M0901InputError("result_limit")
        return BuiltM0901Result(result=result, canonical_bytes=canonical)

    @staticmethod
    def verify(
        result: ValidateComplexActivityStateResult | Mapping[str, object],
        canonical: bytes | bytearray | str,
    ) -> M0901ReplayVerification:
        try:
            raw = (
                canonical
                if isinstance(canonical, (bytes, bytearray))
                else canonical.encode("utf-8")
            )
            strict_json_loads(raw, max_bytes=M0901_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(raw, strict=True)
            if isinstance(result, ValidateComplexActivityStateResult):
                expected = result
            else:
                expected = _RESULT_ADAPTER.validate_json(
                    canonical_json_bytes(result),
                    strict=True,
                )
            if typed != expected:
                return M0901ReplayVerification(
                    verified=False,
                    reason="canonical result differs from supplied result",
                )
            if typed.request_digest != canonical_request_digest(typed.request):
                return M0901ReplayVerification(
                    verified=False, reason="request digest does not replay"
                )
            if typed.result_digest != result_payload_digest(typed):
                return M0901ReplayVerification(
                    verified=False, reason="result digest does not replay"
                )
            if canonical_json_bytes(typed.model_dump(mode="json")) != bytes(raw):
                return M0901ReplayVerification(
                    verified=False,
                    reason="canonical bytes are not deterministic",
                )
        except (TypeError, ValueError):
            return M0901ReplayVerification(verified=False, reason="result replay input is invalid")
        return M0901ReplayVerification(
            verified=True,
            reason="canonical result, request digest, and result digest verified",
        )


def validate_complex_activity_formal_state(request: object) -> BuiltM0901Result:
    """Public provisional M09-01 operation."""

    return M0901FormalStateEngine().validate(request)


__all__ = [
    "BuiltM0901Result",
    "M0901AuthorizationError",
    "M0901FormalStateEngine",
    "M0901FormalStateKernel",
    "M0901InputError",
    "M0901ReplayVerification",
    "_validate_json_request",
    "_validate_typed_request",
    "preflight_formal_state_authorization",
    "validate_complex_activity_formal_state",
]
