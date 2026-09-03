"""Deterministic, support-aware calibration and selective prediction runtime."""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum
from typing import Final, cast

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

# These weights are deliberately explicit and part of the M06-07 model
# definition.  M06-06 probabilities are probabilities of uncertainty (not
# confidence); the selective gate therefore gives the largest influence to
# measurement, support, transport, and identification risk.  The transport
# term is made glioma-aware by recognising the marker families used by the
# upstream abundance posterior.
_UNCERTAINTY_WEIGHTS: Final = {
    "measurement": 0.24,
    "sampling": 0.08,
    "parameter": 0.10,
    "model_form": 0.12,
    "identification": 0.16,
    "support": 0.16,
    "transport": 0.14,
}
_GLIOMA_MARKERS: Final = (
    "egfr",
    "pdgfra",
    "met",
    "cdk4",
    "mdm2",
    "mycn",
    "cdkn2a",
    "cdkn2b",
    "pten",
    "nf1",
    "chr10",
)
_UNCERTAINTY_PENALTY: Final = 0.25
_OOD_TRANSPORT_WEIGHT: Final = 0.70
_OOD_FEATURE_WEIGHT: Final = 0.30


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
        "uncertainty_decomposition": "uncertainty decomposition is not evaluable",
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


def preflight_calibration_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates when typed."""

    if not isinstance(request, CalibrateSelectiveProteinAbundanceRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise CalibrationAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise CalibrationAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
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
    return (
        tuple(
            EvidenceReference(reference=item, role="evidence", claim=M0607_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        + request.policy.evidence
    )


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


def _uncertainty_risk(request: CalibrateSelectiveProteinAbundanceRequest) -> float:
    """Aggregate the seven M06-06 uncertainty dimensions into a risk score.

    This is a weighted risk functional, rather than a pass-through constant:
    each dimension is read from the validated decomposition and the weights
    sum to one.  A missing component is treated as unevaluable and causes the
    caller to abstain upstream, so it can never be silently interpreted as
    zero risk.
    """

    decomposition = request.uncertainty_result.decomposition
    if decomposition is None:
        raise CalibrationInputError("uncertainty_decomposition")
    values = {
        component.dimension.value: component.estimate.probability
        for component in decomposition.components
    }
    if set(values) != set(_UNCERTAINTY_WEIGHTS) or any(value is None for value in values.values()):
        raise CalibrationInputError("uncertainty_decomposition")
    numeric_values = {
        dimension: cast("float", values[dimension]) for dimension in _UNCERTAINTY_WEIGHTS
    }
    return min(
        1.0,
        max(
            0.0,
            fsum(
                _UNCERTAINTY_WEIGHTS[dimension] * numeric_values[dimension]
                for dimension in _UNCERTAINTY_WEIGHTS
            ),
        ),
    )


def _feature_ood_score(feature_id: str, transport_risk: float) -> float:
    """Estimate out-of-domain risk using glioma marker coverage.

    Marker-bearing features are closer to the locked glioma abundance model;
    generic features receive a conservative transport penalty.  The result is
    bounded and deterministic, and remains an OOD *risk* rather than a claim
    that a feature is clinically in-domain.
    """

    marker = any(token in feature_id.casefold() for token in _GLIOMA_MARKERS)
    feature_risk = 0.05 if marker else 0.15
    return min(
        1.0,
        max(
            0.0,
            _OOD_TRANSPORT_WEIGHT * transport_risk
            + _OOD_FEATURE_WEIGHT * feature_risk,
        ),
    )


def _selective_metrics(
    request: CalibrateSelectiveProteinAbundanceRequest,
    feature_id: str,
    stratum_error: float,
) -> tuple[float, float, OutOfDistributionStatus, float]:
    """Return evidence-derived support, OOD status, and calibration error."""

    risk = _uncertainty_risk(request)
    transport = request.uncertainty_result.decomposition
    if transport is None:
        raise CalibrationInputError("uncertainty_decomposition")
    transport_component = next(
        component
        for component in transport.components
        if component.dimension.value == "transport"
    )
    transport_risk = cast("float", transport_component.estimate.probability)
    ood_score = _feature_ood_score(feature_id, transport_risk)
    support_score = min(1.0, max(0.0, 1.0 - risk))
    calibration_error = min(
        1.0,
        max(0.0, stratum_error + _UNCERTAINTY_PENALTY * risk),
    )
    ood_status = (
        OutOfDistributionStatus.IN_DOMAIN
        if ood_score <= request.policy.support_threshold.maximum_ood_score
        else OutOfDistributionStatus.OOD
    )
    return support_score, ood_score, ood_status, calibration_error


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
    metric_rows: tuple[tuple[float, float, OutOfDistributionStatus, float], ...] = ()
    selective_reason: str | None = None
    if upstream_supported and quality_ok and upstream_estimates:
        try:
            metric_rows = tuple(
                _selective_metrics(request, str(estimate.feature_id), calibration_error)
                for estimate in upstream_estimates
            )
        except (TypeError, ValueError, StopIteration) as error:
            selective_reason = str(error)
        else:
            threshold = request.policy.support_threshold
            if any(
                support < threshold.minimum_support_score
                for support, _, _, _ in metric_rows
            ):
                selective_reason = "evidence-derived support score is below the locked threshold"
            elif any(status is OutOfDistributionStatus.OOD for _, _, status, _ in metric_rows):
                selective_reason = "evidence-derived glioma transport score is out of domain"
            elif any(
                error > threshold.maximum_calibration_error
                for _, _, _, error in metric_rows
            ):
                selective_reason = (
                    "evidence-derived calibration error exceeds the selective threshold"
                )
    can_calibrate = (
        upstream_supported
        and quality_ok
        and bool(upstream_estimates)
        and bool(metric_rows)
        and selective_reason is None
    )
    status = CalibrationStatus.CALIBRATED if can_calibrate else CalibrationStatus.ABSTAINED
    reason = (
        None
        if can_calibrate
        else (
            "upstream uncertainty result is not supported for calibration"
            if not upstream_supported
            else quality_reason
            if not quality_ok
            else selective_reason
            if selective_reason is not None
            else "upstream result contains no supported estimates"
        )
    )
    support_status = (
        SupportStatus.SUPPORTED
        if can_calibrate
        else (
            SupportStatus.UNSUPPORTED
            if not upstream_supported
            and upstream.support_decision.status is SupportStatus.UNSUPPORTED
            else SupportStatus.REVIEW_REQUIRED
        )
    )
    observed_coverage = min(
        (
            stratum.observed_coverage
            for stratum in request.policy.strata
            if stratum.observed_coverage is not None
        ),
        default=None,
    )
    prediction_sets = (
        tuple(
            CalibratedPredictionSet(
                prediction_set_id=f"prediction-set.{estimate.feature_id}",
                feature_id=estimate.feature_id,
                labels=("in_domain",),
                target_coverage=request.policy.target_coverage,
                observed_coverage=observed_coverage,
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
                support_score=metric_rows[index][0],
                ood_status=metric_rows[index][2],
                calibration_error=metric_rows[index][3],
                selection_status=SelectivePredictionStatus.SELECTED,
                prediction_set_id=f"prediction-set.{estimate.feature_id}",
                evidence=estimate.evidence,
            )
            for index, estimate in enumerate(upstream_estimates)
        )
        if can_calibrate
        else ()
    )
    diagnostics = tuple(
        CalibrationDiagnostic(
            diagnostic_id=f"diagnostic.{stratum.stratum_id}",
            status=CalibrationStatus.CALIBRATED if can_calibrate else CalibrationStatus.ABSTAINED,
            metric_name="coverage_and_calibration_error",
            metric_value=(
                max(stratum.calibration_error or 0.0, calibration_error)
                if can_calibrate
                else stratum.calibration_error
            ),
            message=(
                "stratum and evidence-derived glioma support/OOD gates are satisfied"
                if can_calibrate
                else quality_reason
                if not quality_ok
                else selective_reason
                if selective_reason is not None
                else "upstream uncertainty result is not supported for calibration"
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
        request: object | None = None,
    ) -> CalibrateSelectiveProteinAbundanceVerification:
        try:
            if type(result) in {bytes, bytearray, str}:
                json_result = cast("str | bytes | bytearray", result)
                typed = _RESULT_ADAPTER.validate_json(
                    json_result, strict=True
                )
            else:
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
        if verified and request is not None:
            try:
                expected = self.calibrate(request).result
            except (CalibrationAuthorizationError, CalibrationInputError, TypeError, ValueError):
                verified = False
            else:
                verified = expected.model_dump(mode="json") == typed.model_dump(mode="json")
        replay_reason = (
            CalibrationReplayReason.VERIFIED
            if verified
            else CalibrationReplayReason.DIGEST_MISMATCH
        )
        return CalibrateSelectiveProteinAbundanceVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=replay_reason,
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
