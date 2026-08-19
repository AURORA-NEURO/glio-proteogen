"""Deterministic, support-aware calibration and selective prediction runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m06_07 import (
    M0607_EVIDENCE_CLAIM,
    M0607_MAX_CALIBRATION_ERROR,
    M0607_MAX_CANONICAL_RESULT_BYTES,
    M0607_MAX_COVERAGE,
    M0607_MIN_COVERAGE,
    CalibratedEstimate,
    CalibratedPredictionSet,
    CalibrateSelectiveProteinAbundanceRequest,
    CalibrateSelectiveProteinAbundanceResult,
    CalibrateSelectiveProteinAbundanceVerification,
    CalibrationDiagnostic,
    CalibrationReplayReason,
    CalibrationStatus,
    OutOfDistributionStatus,
    SelectivePredictionStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import (
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
    EvidenceReference,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UpstreamDecisionState,
)

_REQUEST_ADAPTER: Final = TypeAdapter(CalibrateSelectiveProteinAbundanceRequest)
_RESULT_ADAPTER: Final = TypeAdapter(CalibrateSelectiveProteinAbundanceResult)


class CalibrationAuthorizationError(PermissionError):
    """Raised before an unauthorized calibration request traverses inputs."""

    def __init__(self) -> None:
        super().__init__("M06-07 calibration request is not authorized")


class CalibrationInputError(ValueError):
    """Raised for malformed, oversized, or non-canonical calibration inputs."""

    _MESSAGES: Final = {
        "result_limit": "calibration result exceeds byte limit",
        "result_digest": "calibration result digest does not match",
        "result_noncanonical": "calibration result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltCalibration:
    """Typed calibration result plus its sole canonical byte representation."""

    result: CalibrateSelectiveProteinAbundanceResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise CalibrationInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise CalibrationInputError("result_noncanonical")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_calibration_authorization(request: object) -> None:
    """Apply authorization before strict validation for typed or mapping requests."""

    if not isinstance(request, (CalibrateSelectiveProteinAbundanceRequest, Mapping)):
        return
    expected = {
        "approved_configuration": UpstreamDecisionState.ACCEPTED.value,
        "identity_lineage": IdentityLineageState.RESOLVED.value,
        "provenance": UpstreamDecisionState.ACCEPTED.value,
        "consent": ConsentState.GRANTED.value,
        "quality": UpstreamDecisionState.ACCEPTED.value,
        "support": UpstreamDecisionState.ACCEPTED.value,
        "intended_use": UpstreamDecisionState.ACCEPTED.value,
    }
    try:
        context = _member(request, "context")
        refs = _member(context, "references")
        states = {
            role: _state(_member(_member(refs, role), "state"))
            for role in expected
        }
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise CalibrationAuthorizationError from None
    if states != expected:
        raise CalibrationAuthorizationError


def _control_decisions(
    request: CalibrateSelectiveProteinAbundanceRequest,
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


def _provenance(request: CalibrateSelectiveProteinAbundanceRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts}
            | {request.uncertainty_result.result_digest}
            | {request.policy.calibration_reference.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M06-07",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=request.policy.calibration_reference.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: CalibrateSelectiveProteinAbundanceRequest) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0607_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    ) + request.policy.evidence


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "M06-07 strata, calibration method, labels, limits, and metrics remain provisional."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement="Calibration emits no parent biomarker panel and owns no kinase activity.",
        ),
        Limitation(
            code="selective_only",
            statement=(
                "Unsupported, out-of-domain, or uncalibrated inputs abstain without a value."
            ),
        ),
    )


def _quality_gate(
    request: CalibrateSelectiveProteinAbundanceRequest,
) -> tuple[bool, str, float]:
    policy = request.policy
    metrics = [(stratum.observed_coverage, stratum.calibration_error) for stratum in policy.strata]
    if any(coverage is None or error is None for coverage, error in metrics):
        return False, "one or more calibration strata lack locked coverage metrics", 1.0
    coverages = [coverage for coverage, _ in metrics if coverage is not None]
    errors = [error for _, error in metrics if error is not None]
    observed = min(coverages)
    maximum_error = max(errors)
    if not all(M0607_MIN_COVERAGE <= coverage <= M0607_MAX_COVERAGE for coverage in coverages):
        return (
            False,
            "calibration coverage is outside the provisional 85-95 percent envelope",
            maximum_error,
        )
    if maximum_error > min(
        policy.support_threshold.maximum_calibration_error,
        M0607_MAX_CALIBRATION_ERROR,
    ):
        return False, "calibration error exceeds the selective support threshold", maximum_error
    if observed < policy.target_coverage - (1.0 - policy.target_coverage):
        return False, "calibration coverage is below the provisional target", maximum_error
    return True, "locked provisional strata satisfy coverage and calibration gates", maximum_error


def _build_result(
    request: CalibrateSelectiveProteinAbundanceRequest,
) -> CalibrateSelectiveProteinAbundanceResult:
    upstream = request.uncertainty_result
    upstream_supported = (
        upstream.status.value == "decomposed"
        and upstream.support_decision.status is SupportStatus.SUPPORTED
        and upstream.sensitivity_envelope.status.value == "evaluated"
    )
    quality_ok, quality_reason, calibration_error = _quality_gate(request)
    upstream_estimates = upstream.request.constraint_result.estimates
    can_calibrate = upstream_supported and quality_ok and bool(upstream_estimates)
    status = CalibrationStatus.CALIBRATED if can_calibrate else CalibrationStatus.ABSTAINED
    reason = None if can_calibrate else (
        "upstream uncertainty result is not supported for calibration"
        if not upstream_supported
        else quality_reason
        if not quality_ok
        else "upstream result contains no supported estimates"
    )
    support_status = SupportStatus.SUPPORTED if can_calibrate else (
        SupportStatus.UNSUPPORTED
        if not upstream_supported
        and upstream.support_decision.status is SupportStatus.UNSUPPORTED
        else SupportStatus.REVIEW_REQUIRED
    )
    prediction_sets = (
        tuple(
            CalibratedPredictionSet(
                prediction_set_id=f"prediction-set.{estimate.feature_id}",
                feature_id=estimate.feature_id,
                labels=("in_domain",),
                target_coverage=request.policy.target_coverage,
                observed_coverage=min(
                    stratum.observed_coverage
                    for stratum in request.policy.strata
                    if stratum.observed_coverage is not None
                ),
            )
            for estimate in upstream_estimates
        )
        if can_calibrate
        else ()
    )
    estimates = (
        tuple(
            CalibratedEstimate(
                feature_id=estimate.feature_id,
                estimate_value=estimate.estimate_value,
                support_score=1.0,
                ood_status=OutOfDistributionStatus.IN_DOMAIN,
                calibration_error=calibration_error,
                selection_status=SelectivePredictionStatus.SELECTED,
                prediction_set_id=f"prediction-set.{estimate.feature_id}",
                evidence=estimate.evidence,
            )
            for estimate in upstream_estimates
        )
        if can_calibrate
        else ()
    )
    diagnostics = tuple(
        CalibrationDiagnostic(
            diagnostic_id=f"diagnostic.{stratum.stratum_id}",
            status=CalibrationStatus.CALIBRATED
            if can_calibrate
            else CalibrationStatus.ABSTAINED,
            metric_name="coverage_and_calibration_error",
            metric_value=stratum.calibration_error,
            message=(
                "stratum satisfies provisional calibration gate"
                if can_calibrate
                else quality_reason
            ),
        )
        for stratum in request.policy.strata
    )
    support = SupportDecision(
        status=support_status,
        reason_code="calibration_support_state",
        rationale=(
            "all upstream, coverage, and selective support gates are satisfied"
            if can_calibrate
            else reason or "calibration requires review"
        ),
    )
    draft = CalibrateSelectiveProteinAbundanceResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        estimates=estimates,
        prediction_sets=prediction_sets,
        diagnostics=diagnostics,
        abstention_reason=reason,
        support_decision=support,
        uncertainty=upstream.uncertainty,
        provenance=_provenance(request),
        evidence=_evidence(request),
        limitations=_limitations(),
        human_review_required=not can_calibrate,
    )
    result = draft.model_copy(update={"result_digest": result_payload_digest(draft)})
    return CalibrateSelectiveProteinAbundanceResult.model_validate(result, strict=True)


class M0607CalibrationEngine:
    """Build, replay, and verify one deterministic selective calibration result."""

    @staticmethod
    def validate_request(request: object) -> CalibrateSelectiveProteinAbundanceRequest:
        preflight_calibration_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def calibrate(self, request: object) -> BuiltCalibration:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0607_MAX_CANONICAL_RESULT_BYTES:
            raise CalibrationInputError("result_limit")
        return BuiltCalibration(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> CalibrateSelectiveProteinAbundanceVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return CalibrateSelectiveProteinAbundanceVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=CalibrationReplayReason.INVALID_RESULT,
            )
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0607_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        return CalibrateSelectiveProteinAbundanceVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                CalibrationReplayReason.VERIFIED
                if verified
                else CalibrationReplayReason.DIGEST_MISMATCH
            ),
        )

    def execute(self, request: object) -> BuiltCalibration:
        return self.calibrate(request)


def calibrate_selective_protein_abundance(request: object) -> BuiltCalibration:
    """Calibrate one request through the default stateless engine."""

    return M0607CalibrationEngine().calibrate(request)


__all__ = [
    "BuiltCalibration",
    "CalibrationAuthorizationError",
    "CalibrationInputError",
    "M0607CalibrationEngine",
    "calibrate_selective_protein_abundance",
    "preflight_calibration_authorization",
]
