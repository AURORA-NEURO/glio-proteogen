"""Deterministic, replay-closed runtime for provisional M07-01 validation.

The dossier assigns this module the formal state and executable invariant
library beneath copy-number dosage/attenuation.  This implementation keeps the
boundary deliberately narrow: it validates caller-declared feature values,
evaluates a small auditable expression vocabulary, and abstains whenever the
state cannot be evaluated without guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_01 import (
    M0701_CONTRACT_VERSION,
    M0701_EVIDENCE_CLAIM,
    M0701_MAX_CANONICAL_REQUEST_BYTES,
    M0701_MAX_CANONICAL_RESULT_BYTES,
    M0701_MODULE_ID,
    CopyNumberFeatureValue,
    CopyNumberInvariant,
    CopyNumberInvariantResult,
    CopyNumberInvariantSeverity,
    CopyNumberInvariantStatus,
    CopyNumberMissingness,
    CopyNumberValidationStatus,
    ValidateCopyNumberStateRequest,
    ValidateCopyNumberStateResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateCopyNumberStateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ValidateCopyNumberStateResult)
_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
_COMPARISON = re.compile(
    rf"^(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{{0,127}})\s*"
    rf"(?P<operator>>=|<=|==|>|<)\s*(?P<value>{_NUMBER})$"
)
_BETWEEN = re.compile(
    rf"^(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{{0,127}})\s+between\s+"
    rf"(?P<lower>{_NUMBER})\s+and\s+(?P<upper>{_NUMBER})$",
    re.IGNORECASE,
)


class FormalStateAuthorizationError(PermissionError):
    """Raised before an unauthorized request is evaluated."""

    def __init__(self) -> None:
        super().__init__("M07-01 formal-state request is not authorized")


class FormalStateInputError(ValueError):
    """Raised for bounded/canonical runtime input failures."""

    _MESSAGES: Final = {
        "request_limit": "formal-state request exceeds byte limit",
        "result_limit": "formal-state result exceeds byte limit",
        "result_digest": "formal-state result digest does not match",
        "result_noncanonical": "formal-state result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltFormalStateResult:
    """Validated result together with its sole canonical byte encoding."""

    result: ValidateCopyNumberStateResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise FormalStateInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise FormalStateInputError("result_noncanonical")


def preflight_formal_state_authorization(candidate: object) -> None:
    """Check consent, identity, and upstream controls without fact traversal."""

    if not isinstance(candidate, ValidateCopyNumberStateRequest):
        return
    refs = candidate.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise FormalStateAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise FormalStateAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise FormalStateAuthorizationError


def _control_decisions(
    request: ValidateCopyNumberStateRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    controls = (
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
        for role, decision in controls
    )


def _provenance(request: ValidateCopyNumberStateRequest) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M0701_MODULE_ID,
        module_version=M0701_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted({item.digest for item in request.source_artifacts})),
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M07-01 validates formal state; it does not estimate a biological posterior.",
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
            "Biological uncertainty remains caller-owned; failed support gates abstain.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Feature catalogue, expression vocabulary, capacities, and endpoints "
                "are provisional."
            ),
        ),
        Limitation(
            code="formal_state_only",
            statement=(
                "This module validates formal copy-number state and emits no proteotype claim."
            ),
        ),
        Limitation(
            code="no_kinase_activity",
            statement="KINOPHOS owns kinase activity; this module does not infer it.",
        ),
        Limitation(
            code="no_imputation",
            statement="Missing, not-applicable, unknown, and unsupported states are never imputed.",
        ),
    )


def _numeric_value(value: CopyNumberFeatureValue) -> float | None:
    """Project a numeric observed value without pretending missingness is zero."""

    if value.scalar_value is not None:
        return value.scalar_value
    if value.interval_lower is not None and value.interval_upper is not None:
        return (value.interval_lower + value.interval_upper) / 2.0
    return None


def _evaluate_invariant(
    invariant: CopyNumberInvariant,
    values: dict[str, CopyNumberFeatureValue],
) -> CopyNumberInvariantResult:
    """Evaluate a bounded expression subset; unknown grammar is not evaluable."""

    expression = invariant.expression
    if expression.casefold() == "all_present":
        missing = [
            feature_id
            for feature_id in invariant.feature_ids
            if values[feature_id].state is not CopyNumberMissingness.OBSERVED
        ]
        if missing:
            return CopyNumberInvariantResult(
                invariant_id=invariant.invariant_id,
                status=CopyNumberInvariantStatus.NOT_EVALUABLE,
                message="required feature is not observed; no missingness was imputed",
            )
        return CopyNumberInvariantResult(
            invariant_id=invariant.invariant_id,
            status=CopyNumberInvariantStatus.SATISFIED,
            message="all invariant features are observed",
        )
    comparison = _COMPARISON.fullmatch(expression) or _BETWEEN.fullmatch(expression)
    if comparison is None:
        return CopyNumberInvariantResult(
            invariant_id=invariant.invariant_id,
            status=CopyNumberInvariantStatus.NOT_EVALUABLE,
            message="expression is outside the provisional safe grammar",
        )
    feature_id = comparison.group("feature")
    if feature_id not in invariant.feature_ids or feature_id not in values:
        return CopyNumberInvariantResult(
            invariant_id=invariant.invariant_id,
            status=CopyNumberInvariantStatus.NOT_EVALUABLE,
            message="expression feature is not declared by this invariant",
        )
    feature = values[feature_id]
    number = _numeric_value(feature)
    if feature.state is not CopyNumberMissingness.OBSERVED or number is None:
        return CopyNumberInvariantResult(
            invariant_id=invariant.invariant_id,
            status=CopyNumberInvariantStatus.NOT_EVALUABLE,
            message="numeric invariant cannot evaluate a non-observed or categorical value",
        )
    if "operator" in comparison.groupdict():
        expected = float(comparison.group("value"))
        operator = comparison.group("operator")
        satisfied = {
            ">=": number >= expected,
            "<=": number <= expected,
            "==": number == expected,
            ">": number > expected,
            "<": number < expected,
        }[operator]
    else:
        lower = float(comparison.group("lower"))
        upper = float(comparison.group("upper"))
        satisfied = lower <= number <= upper
    return CopyNumberInvariantResult(
        invariant_id=invariant.invariant_id,
        status=(
            CopyNumberInvariantStatus.SATISFIED
            if satisfied
            else CopyNumberInvariantStatus.VIOLATED
        ),
        message=(
            "expression satisfied by the observed value"
            if satisfied
            else f"hard/declared expression violated for {invariant.invariant_id}"
        ),
    )


def _build_result(request: ValidateCopyNumberStateRequest) -> ValidateCopyNumberStateResult:
    values = {item.feature_id: item for item in request.values}
    invariant_results = tuple(
        _evaluate_invariant(item, values) for item in request.state_schema.invariants
    )
    violated = {
        item.invariant_id
        for item in invariant_results
        if item.status is CopyNumberInvariantStatus.VIOLATED
    }
    not_evaluable = {
        item.invariant_id
        for item in invariant_results
        if item.status is CopyNumberInvariantStatus.NOT_EVALUABLE
    }
    declared_severity = {
        item.invariant_id: item.severity for item in request.state_schema.invariants
    }
    hard_violation = any(
        declared_severity[item] is CopyNumberInvariantSeverity.ERROR for item in violated
    )
    warning_violation = any(
        declared_severity[item] is CopyNumberInvariantSeverity.WARNING for item in violated
    )
    if hard_violation or warning_violation:
        status = CopyNumberValidationStatus.INVALID
        support_status = SupportStatus.LIMITED
        rationale = "one or more error-severity formal invariants were violated"
    elif not_evaluable:
        status = CopyNumberValidationStatus.ABSTAINED
        support_status = SupportStatus.REVIEW_REQUIRED
        rationale = "one or more invariants could not be evaluated without imputing evidence"
    else:
        status = CopyNumberValidationStatus.VALID
        support_status = SupportStatus.SUPPORTED
        rationale = "all declared formal invariants were evaluated and satisfied"
    support = SupportDecision(
        status=support_status,
        reason_code="formal_state_validation",
        rationale=rationale,
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0701_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    draft = ValidateCopyNumberStateResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        support_decision=support,
        invariant_results=invariant_results,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return ValidateCopyNumberStateResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0701FormalStateEngine:
    """Validate, execute, and verify deterministic M07-01 results."""

    __slots__ = ()

    @staticmethod
    def validate_request(request: object) -> ValidateCopyNumberStateRequest:
        preflight_formal_state_authorization(request)
        typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        encoded = canonical_json_bytes(typed.model_dump(mode="json"))
        if len(encoded) > M0701_MAX_CANONICAL_REQUEST_BYTES:
            raise FormalStateInputError("request_limit")
        return typed

    def validate(self, request: object) -> BuiltFormalStateResult:
        typed = self.validate_request(request)
        result = _build_result(typed)
        encoded = canonical_json_bytes(result.model_dump(mode="json"))
        if len(encoded) > M0701_MAX_CANONICAL_RESULT_BYTES:
            raise FormalStateInputError("result_limit")
        return BuiltFormalStateResult(result=result, canonical_bytes=encoded)

    def execute(self, request: object) -> BuiltFormalStateResult:
        return self.validate(request)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ValidateCopyNumberStateResult:
        """Return the typed result only when both content and digest replay verify."""

        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError) as error:
            raise FormalStateInputError("result_digest") from error
        expected = canonical_json_bytes(typed.model_dump(mode="json"))
        if len(expected) > M0701_MAX_CANONICAL_RESULT_BYTES:
            raise FormalStateInputError("result_limit")
        if typed.result_digest != result_payload_digest(typed):
            raise FormalStateInputError("result_digest")
        if canonical_bytes is not None and canonical_bytes != expected:
            raise FormalStateInputError("result_noncanonical")
        return typed


def validate_copy_number_formal_state(request: object) -> BuiltFormalStateResult:
    """Execute the stateless provisional M07-01 operation."""

    return M0701FormalStateEngine().execute(request)


__all__ = [
    "BuiltFormalStateResult",
    "FormalStateAuthorizationError",
    "FormalStateInputError",
    "M0701FormalStateEngine",
    "preflight_formal_state_authorization",
    "validate_copy_number_formal_state",
]
