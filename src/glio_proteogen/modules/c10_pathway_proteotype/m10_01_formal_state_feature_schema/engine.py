"""Deterministic, fail-closed M10-01 formal-state validation runtime."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m10_01 import (
    M1001_MAX_CANONICAL_RESULT_BYTES,
    M1001_MODULE_ID,
    ProteinRnaFeatureValue,
    ProteinRnaInvariant,
    ProteinRnaInvariantResult,
    ProteinRnaInvariantSeverity,
    ProteinRnaInvariantStatus,
    ProteinRnaMissingness,
    ProteinRnaReplayReason,
    ProteinRnaValidationStatus,
    ValidateProteinRnaDiscordanceStateRequest,
    ValidateProteinRnaDiscordanceStateResult,
    ValidateProteinRnaDiscordanceStateVerification,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ValidateProteinRnaDiscordanceStateRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ValidateProteinRnaDiscordanceStateResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_COMPARISON = re.compile(
    r"^(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{0,127})\s*"
    r"(?P<operator>==|>=|<=|>|<)\s*(?P<value>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)$"
)
_BETWEEN = re.compile(
    r"^(?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{0,127})\s+between\s+"
    r"(?P<lower>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+and\s+"
    r"(?P<upper>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)$"
)
_PRESENCE = re.compile(
    r"^(?P<kind>present|missing)\((?P<feature>[a-zA-Z][a-zA-Z0-9._:-]{0,127})\)$"
)


class M1001AuthorizationError(PermissionError):
    """Raised before any formal state value is evaluated when controls fail."""

    def __init__(self) -> None:
        super().__init__(
            "M10-01 requires granted consent, resolved identity, and accepted controls"
        )


class M1001InputError(ValueError):
    """Raised when a replay payload exceeds or violates its canonical boundary."""

    _MESSAGES: Final = {
        "result_limit": "M10-01 result exceeds the canonical byte limit",
        "result_digest": "M10-01 result digest does not match its content",
        "result_noncanonical": "M10-01 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM1001Result:
    """Result object paired with the exact canonical bytes used for replay."""

    result: ValidateProteinRnaDiscordanceStateResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M1001InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M1001InputError("result_noncanonical")


def preflight_m1001_authorization(request: object) -> None:
    """Check caller-declared controls before touching feature or invariant content."""

    if not isinstance(request, ValidateProteinRnaDiscordanceStateRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M1001AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M1001AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M1001AuthorizationError


def _control_decisions(
    request: ValidateProteinRnaDiscordanceStateRequest,
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


def _provenance(request: ValidateProteinRnaDiscordanceStateRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(sorted(item.digest for item in request.source_artifacts))
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1001_MODULE_ID,
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
    dimensions = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M10-01 validates formal state but has no owner-locked estimator for uncertainty."
        ),
    )
    return UncertaintyProfile(
        measurement=dimensions,
        sampling=dimensions,
        parameter=dimensions,
        model_form=dimensions,
        identification=dimensions,
        support=dimensions,
        transport=dimensions,
        sensitivity_notes=(
            "All seven uncertainty dimensions are explicit and not estimable at "
            "this schema-only boundary.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Feature catalogue, endpoint, media type, capacities, and implementation metadata "
                "remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="declarative_only",
            statement=(
                "Invariant expressions are bounded declarative comparisons; no code or external "
                "content "
                "is executed or traversed."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, "
                "identity inference, or parent protein-RNA discordance claim."
            ),
        ),
    )


def _value_bounds(value: ProteinRnaFeatureValue) -> tuple[float, float] | None:
    if value.state is not ProteinRnaMissingness.OBSERVED:
        return None
    if value.scalar_value is not None:
        return value.scalar_value, value.scalar_value
    if value.interval_lower is not None and value.interval_upper is not None:
        return value.interval_lower, value.interval_upper
    return None


def _evaluate_invariant(
    invariant: ProteinRnaInvariant,
    values: dict[str, ProteinRnaFeatureValue],
) -> ProteinRnaInvariantStatus:
    expression = invariant.expression
    status = ProteinRnaInvariantStatus.NOT_EVALUABLE
    presence = _PRESENCE.fullmatch(expression)
    if presence:
        value = values[presence.group("feature")]
        if presence.group("kind") == "present":
            status = (
                ProteinRnaInvariantStatus.SATISFIED
                if value.state is ProteinRnaMissingness.OBSERVED
                else ProteinRnaInvariantStatus.NOT_EVALUABLE
            )
        else:
            status = (
                ProteinRnaInvariantStatus.SATISFIED
                if value.state is not ProteinRnaMissingness.OBSERVED
                else ProteinRnaInvariantStatus.VIOLATED
            )
    elif comparison := _COMPARISON.fullmatch(expression):
        bounds = _value_bounds(values[comparison.group("feature")])
        if bounds is not None:
            threshold = float(comparison.group("value"))
            lower, upper = bounds
            operator = comparison.group("operator")
            checks = {
                "==": lower == upper == threshold,
                ">=": lower >= threshold,
                "<=": upper <= threshold,
                ">": lower > threshold,
                "<": upper < threshold,
            }
            status = (
                ProteinRnaInvariantStatus.SATISFIED
                if checks[operator]
                else ProteinRnaInvariantStatus.VIOLATED
            )
    elif between := _BETWEEN.fullmatch(expression):
        bounds = _value_bounds(values[between.group("feature")])
        if bounds is not None:
            lower, upper = bounds
            status = (
                ProteinRnaInvariantStatus.SATISFIED
                if lower >= float(between.group("lower")) and upper <= float(between.group("upper"))
                else ProteinRnaInvariantStatus.VIOLATED
            )
    return status


def _build_result(
    request: ValidateProteinRnaDiscordanceStateRequest,
) -> ValidateProteinRnaDiscordanceStateResult:
    values = {item.feature_id: item for item in request.values}
    reports = tuple(
        _invariant_result(invariant, _evaluate_invariant(invariant, values))
        for invariant in request.state_schema.invariants
    )
    statuses = {item.status for item in reports}
    hard_ids = {
        item.invariant_id
        for item in request.state_schema.invariants
        if item.severity is ProteinRnaInvariantSeverity.ERROR
    }
    if ProteinRnaInvariantStatus.NOT_EVALUABLE in statuses:
        status = ProteinRnaValidationStatus.ABSTAINED
        support_status = SupportStatus.REVIEW_REQUIRED
        rationale = "one or more invariants cannot be evaluated without unsupported assumptions"
    elif any(
        item.status is ProteinRnaInvariantStatus.VIOLATED and item.invariant_id in hard_ids
        for item in reports
    ):
        status = ProteinRnaValidationStatus.INVALID
        support_status = SupportStatus.LIMITED
        rationale = "one or more hard formal invariants are violated"
    elif ProteinRnaInvariantStatus.VIOLATED in statuses:
        status = ProteinRnaValidationStatus.VALID
        support_status = SupportStatus.LIMITED
        rationale = "soft invariant conflicts are visible and do not become hidden negatives"
    else:
        status = ProteinRnaValidationStatus.VALID
        support_status = SupportStatus.SUPPORTED
        rationale = "all supplied formal invariants are satisfied"
    support = SupportDecision(
        status=support_status,
        reason_code="m1001_formal_state_support",
        rationale=rationale,
    )
    evidence = tuple(
        EvidenceReference(
            reference=item,
            role="evidence",
            claim="caller-declared formal-state input",
        )
        for item in request.source_artifacts
    )
    draft = ValidateProteinRnaDiscordanceStateResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        support_decision=support,
        invariant_results=reports,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


def _invariant_result(
    invariant: ProteinRnaInvariant,
    status: ProteinRnaInvariantStatus,
) -> ProteinRnaInvariantResult:
    messages = {
        ProteinRnaInvariantStatus.SATISFIED: "declarative invariant satisfied",
        ProteinRnaInvariantStatus.VIOLATED: (
            "hard invariant violation is retained as an invalid formal state"
            if invariant.severity is ProteinRnaInvariantSeverity.ERROR
            else "soft invariant conflict is retained for review"
        ),
        ProteinRnaInvariantStatus.NOT_EVALUABLE: (
            "invariant is not evaluable because required evidence is missing or unsupported"
        ),
    }
    return ProteinRnaInvariantResult(
        invariant_id=invariant.invariant_id,
        status=status,
        message=messages[status],
    )


class M1001FormalStateEngine:
    """Build and verify one deterministic formal-state validation result."""

    @staticmethod
    def validate_request(request: object) -> ValidateProteinRnaDiscordanceStateRequest:
        preflight_m1001_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def validate(self, request: object) -> ValidateProteinRnaDiscordanceStateRequest:
        return self.validate_request(request)

    def execute(self, request: object) -> BuiltM1001Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M1001_MAX_CANONICAL_RESULT_BYTES:
            raise M1001InputError("result_limit")
        return BuiltM1001Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ValidateProteinRnaDiscordanceStateVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ValidateProteinRnaDiscordanceStateVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ProteinRnaReplayReason.INVALID_RESULT,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M1001_MAX_CANONICAL_RESULT_BYTES
        ):
            return ValidateProteinRnaDiscordanceStateVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    ProteinRnaReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else ProteinRnaReplayReason.NON_CANONICAL
                ),
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        verified = content_verified and deterministic_verified
        return ValidateProteinRnaDiscordanceStateVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            reason=(
                ProteinRnaReplayReason.VERIFIED
                if verified
                else (
                    ProteinRnaReplayReason.NON_CANONICAL
                    if not content_verified
                    else ProteinRnaReplayReason.DIGEST_MISMATCH
                )
            ),
            result_digest=typed.result_digest if verified else None,
        )

    def integrate(self, request: object) -> BuiltM1001Result:
        return self.execute(request)


def validate_protein_rna_discordance_state(request: object) -> BuiltM1001Result:
    """Public provisional M10-01 operation."""

    return M1001FormalStateEngine().execute(request)


__all__ = [
    "BuiltM1001Result",
    "M1001AuthorizationError",
    "M1001FormalStateEngine",
    "M1001InputError",
    "preflight_m1001_authorization",
    "validate_protein_rna_discordance_state",
]
