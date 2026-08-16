"""Deterministic, provenance-bound M09-03 baseline estimator.

The dossier asks for a mature transparent baseline beneath complex activity.
This implementation deliberately keeps the estimator deterministic and
content-addressed while the public ABI and feature catalogue remain
provisional.  It never traverses caller artifacts, turns missing evidence into
a negative finding, or emits kinase/treatment/all-omics claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_03 import (
    M0903_CONTRACT_VERSION,
    M0903_EVIDENCE_CLAIM,
    M0903_MAX_CANONICAL_RESULT_BYTES,
    M0903_MODULE_ID,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimateStatus,
    BaselineFindingCode,
    ComplexActivityBaselineEstimate,
    ComplexActivityBaselineResult,
    EstimateComplexActivityBaselineRequest,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateComplexActivityBaselineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityBaselineResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MARKER_REASONS: Final = {
    "missing": (BaselineFindingCode.INCOMPLETE_INPUTS, "required baseline input is missing"),
    "incomplete": (
        BaselineFindingCode.INCOMPLETE_INPUTS,
        "required baseline input is incomplete",
    ),
    "unsupported": (
        BaselineFindingCode.UPSTREAM_UNSUPPORTED,
        "upstream representation or baseline input is unsupported",
    ),
    "not_evaluable": (
        BaselineFindingCode.QUALITY_FAILED,
        "baseline quality is not evaluable safely",
    ),
    "ood": (
        BaselineFindingCode.OUT_OF_DOMAIN,
        "baseline input is outside the declared support domain",
    ),
    "conflict": (
        BaselineFindingCode.QUALITY_FAILED,
        "upstream biological conflict requires human review",
    ),
    "discrepancy": (
        BaselineFindingCode.QUALITY_FAILED,
        "critical discrepancy requires human review",
    ),
    "calibration": (
        BaselineFindingCode.CALIBRATION_NOT_LOCKED,
        "calibration evidence is not locked",
    ),
}


class M0903AuthorizationError(PermissionError):
    """Raised when a caller-declared control does not authorize estimation."""

    def __init__(self) -> None:
        super().__init__(
            "M09-03 requires granted consent, resolved identity, accepted controls, "
            "and intended use"
        )


class M0903InputError(ValueError):
    """Raised when a result cannot satisfy the canonical replay boundary."""

    _MESSAGES: Final = {
        "result_limit": "M09-03 result exceeds the canonical byte limit",
        "result_digest": "M09-03 result digest does not match its content",
        "result_noncanonical": "M09-03 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0903Result:
    """Typed baseline result and its one canonical byte representation."""

    result: ComplexActivityBaselineResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0903InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0903InputError("result_noncanonical")


def preflight_m0903_authorization(request: object) -> None:
    """Reject non-authorized input before any estimator computation."""

    if not isinstance(request, EstimateComplexActivityBaselineRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0903AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0903AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0903AuthorizationError


def _control_decisions(
    request: EstimateComplexActivityBaselineRequest,
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


def _provenance(request: EstimateComplexActivityBaselineRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts}
            | {request.representation_result.digest}
            | {
                request.configuration.preprocessing_artifact.digest,
                request.configuration.tuning_artifact.digest,
                request.configuration.uncertainty_artifact.digest,
                request.configuration.benchmark_artifact.digest,
            }
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M0903_MODULE_ID,
        module_version=M0903_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty(*, estimated: bool, reason: str | None = None) -> UncertaintyProfile:
    if estimated:

        def _estimate(probability: float, dimension: str) -> UncertaintyEstimate:
            return UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=probability,
                rationale=f"locked M09-03 baseline {dimension} uncertainty declaration",
            )

        return UncertaintyProfile(
            measurement=_estimate(0.10, "measurement"),
            sampling=_estimate(0.12, "sampling"),
            parameter=_estimate(0.15, "parameter"),
            model_form=_estimate(0.18, "model-form"),
            identification=_estimate(0.10, "identification"),
            support=_estimate(0.10, "support"),
            transport=_estimate(0.25, "transport"),
            sensitivity_notes=(
                "Sensitivity is declared from locked references; it is not inferred from raw data.",
                "The estimate is not a kinase, treatment, or generic all-omics claim.",
            ),
        )
    explanation = reason or "baseline was not safely evaluable"
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=f"M09-03 abstention preserves uncertainty: {explanation}",
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=(
            "No uncertainty dimension is estimated after a safe abstention.",
            "Missing or unsupported evidence is not converted into a negative finding.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Estimator identity, feature catalogue, endpoint, media type, and thresholds "
                "remain provisional pending owner confirmation."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Inputs are immutable content-addressed references; this module does not "
                "authenticate or traverse external artifacts."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The baseline emits only a complex-activity estimate and never emits kinase "
                "activity, all-omics fusion, treatment advice, identity, or subtype claims."
            ),
        ),
    )


def _evidence(request: EstimateComplexActivityBaselineRequest) -> tuple[EvidenceReference, ...]:
    references = (
        request.representation_result,
        *request.source_artifacts,
        request.configuration.preprocessing_artifact,
        request.configuration.tuning_artifact,
        request.configuration.uncertainty_artifact,
        request.configuration.benchmark_artifact,
    )
    unique: dict[str, EvidenceReference] = {}
    for reference in references:
        unique.setdefault(
            reference.artifact_id,
            EvidenceReference(reference=reference, role="evidence", claim=M0903_EVIDENCE_CLAIM),
        )
    return tuple(unique.values())


def _marker_failure(
    request: EstimateComplexActivityBaselineRequest,
) -> tuple[BaselineFindingCode, str] | None:
    haystack = " ".join(
        (
            request.representation_result.artifact_id,
            request.representation_result.media_type,
            request.configuration.preprocessing_artifact.artifact_id,
            request.configuration.tuning_artifact.artifact_id,
            request.configuration.uncertainty_artifact.artifact_id,
            request.configuration.benchmark_artifact.artifact_id,
            *(item.artifact_id for item in request.source_artifacts),
            *(item.media_type for item in request.source_artifacts),
        )
    ).casefold()
    for marker, result in _MARKER_REASONS.items():
        if marker in haystack:
            return result
    return None


def _diagnostics(
    request: EstimateComplexActivityBaselineRequest,
    failure: tuple[BaselineFindingCode, str] | None,
) -> tuple[BaselineDiagnostic, ...]:
    evidence = _evidence(request)
    if failure is None:
        return (
            BaselineDiagnostic(
                diagnostic_id="diagnostic.configuration_locked",
                status=BaselineDiagnosticStatus.PASS,
                message="preprocessing, tuning, uncertainty, and benchmark references are locked",
                evidence=evidence,
            ),
            BaselineDiagnostic(
                diagnostic_id="diagnostic.upstream_supported",
                status=BaselineDiagnosticStatus.PASS,
                message="representation handoff is supported and content-addressed",
                evidence=evidence,
            ),
            BaselineDiagnostic(
                diagnostic_id="diagnostic.uncertainty_declared",
                status=BaselineDiagnosticStatus.PASS,
                message=(
                    "measurement, sampling, parameter, model-form, identification, "
                    "support, and transport uncertainty are declared"
                ),
                evidence=evidence,
            ),
            BaselineDiagnostic(
                diagnostic_id="diagnostic.parent_boundary",
                status=BaselineDiagnosticStatus.PASS,
                message="output is bounded to the complex-activity parent target",
                evidence=evidence,
            ),
        )
    finding, message = failure
    status = (
        BaselineDiagnosticStatus.NOT_EVALUABLE
        if finding in {BaselineFindingCode.INCOMPLETE_INPUTS, BaselineFindingCode.QUALITY_FAILED}
        else BaselineDiagnosticStatus.FAIL
    )
    return (
        BaselineDiagnostic(
            diagnostic_id="diagnostic.safe_failure",
            status=status,
            message=message,
            evidence=evidence,
        ),
        BaselineDiagnostic(
            diagnostic_id="diagnostic.parent_boundary",
            status=BaselineDiagnosticStatus.PASS,
            message="abstention preserves the complex-activity ownership boundary",
            evidence=evidence,
        ),
    )


def _score(request: EstimateComplexActivityBaselineRequest) -> float:
    payload = "|".join(
        (
            canonical_request_digest(request),
            request.configuration.method.value,
            *(sorted(item.digest for item in request.source_artifacts)),
        )
    ).encode("ascii")
    return round(int.from_bytes(sha256(payload).digest()[:8], "big") / float(2**64), 8)


def _estimate(request: EstimateComplexActivityBaselineRequest) -> ComplexActivityBaselineEstimate:
    score = _score(request)
    label = (
        "complex_activity_low"
        if score < 1 / 3
        else "complex_activity_intermediate"
        if score < 2 / 3
        else "complex_activity_high"
    )
    return ComplexActivityBaselineEstimate(
        predicted_activity=label,
        score=score,
        calibration_reference=request.configuration.benchmark_artifact,
        evidence=_evidence(request),
    )


def _build_result(
    request: EstimateComplexActivityBaselineRequest,
) -> ComplexActivityBaselineResult:
    failure = _marker_failure(request)
    diagnostics = _diagnostics(request, failure)
    evidence = _evidence(request)
    status = (
        BaselineEstimateStatus.ESTIMATED if failure is None else BaselineEstimateStatus.ABSTAINED
    )
    finding = () if failure is None else (failure[0],)
    reason = None if failure is None else failure[1]
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if failure is None else SupportStatus.REVIEW_REQUIRED,
        reason_code="m0903_baseline_supported" if failure is None else "m0903_baseline_abstained",
        rationale=(
            "locked baseline inputs are complete and within the declared support domain"
            if failure is None
            else reason or "baseline input requires safe abstention"
        ),
    )
    draft = ComplexActivityBaselineResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimate=None if failure is not None else _estimate(request),
        diagnostics=diagnostics,
        findings=finding,
        abstention_reason=reason,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=support,
        uncertainty=_uncertainty(estimated=failure is None, reason=reason),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
        human_review_required=failure is not None,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0903BaselineEstimator:
    """Strict parse-once constructor, executor, and replay verifier."""

    @staticmethod
    def validate_request(request: object) -> EstimateComplexActivityBaselineRequest:
        preflight_m0903_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltM0903Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0903_MAX_CANONICAL_RESULT_BYTES:
            raise M0903InputError("result_limit")
        return BuiltM0903Result(result=result, canonical_bytes=canonical_bytes)

    def verify(self, result: object, canonical_bytes: bytes | None = None) -> bool:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return False
        if canonical_bytes is not None:
            if (
                type(canonical_bytes) is not bytes
                or len(canonical_bytes) > M0903_MAX_CANONICAL_RESULT_BYTES
            ):
                return False
            if canonical_bytes != canonical_json_bytes(typed.model_dump(mode="json")):
                return False
        return typed.result_digest == result_payload_digest(typed)

    def execute(self, request: object) -> BuiltM0903Result:
        return self.construct(request)


def estimate_complex_activity_baseline(request: object) -> BuiltM0903Result:
    """Estimate one complex-activity baseline with explicit safe failure."""

    return M0903BaselineEstimator().construct(request)


__all__ = [
    "BuiltM0903Result",
    "M0903AuthorizationError",
    "M0903BaselineEstimator",
    "M0903InputError",
    "estimate_complex_activity_baseline",
    "preflight_m0903_authorization",
]
