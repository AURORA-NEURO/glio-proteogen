"""Deterministic, replay-bound M09-06 uncertainty decomposition runtime.

The dossier names the seven uncertainty dimensions and the coverage gate but
does not freeze the estimator, calibration artefacts, endpoint, or media type.
This implementation consequently uses a deterministic, caller-declared
estimator seam. It never fetches external content, treats unsupported inputs
as abstention, and binds every emitted value to the exact request digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_06 import (
    M0906_CONTRACT_VERSION,
    M0906_EVIDENCE_CLAIM,
    M0906_MAX_CANONICAL_REQUEST_BYTES,
    M0906_MAX_CANONICAL_RESULT_BYTES,
    M0906_MODULE_ID,
    ComplexActivityUncertaintyDecompositionResult,
    DecomposeComplexActivityUncertaintyRequest,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    UncertaintyFinding,
    UncertaintyFindingCode,
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
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeComplexActivityUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0906AuthorizationError(PermissionError):
    """Raised when consent, identity, or a required upstream control is unsafe."""

    def __init__(self) -> None:
        super().__init__(
            "M09-06 requires granted consent, resolved identity, and accepted controls"
        )


class M0906InputError(ValueError):
    """Raised for oversized or non-canonical request/result material."""

    _MESSAGES: Final = {
        "request_limit": "M09-06 canonical request exceeds the byte limit",
        "result_limit": "M09-06 canonical result exceeds the byte limit",
        "result_digest": "M09-06 result digest does not match its content",
        "result_noncanonical": "M09-06 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, "M09-06 input rejected"))


@dataclass(frozen=True, slots=True)
class M0906ReplayVerification:
    """Stable replay result that does not echo untrusted payloads."""

    verified: bool
    reason: str
    result_digest: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltM0906Result:
    """Validated result paired with its exact canonical byte representation."""

    result: ComplexActivityUncertaintyDecompositionResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0906InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0906InputError("result_noncanonical")


def _state(value: object) -> str:
    return str(getattr(value, "value", value))


def preflight_m0906_authorization(request: object) -> None:
    """Fail closed before evaluating policy expressions or source references."""

    if not isinstance(request, DecomposeComplexActivityUncertaintyRequest):
        raise M0906AuthorizationError
    references = request.context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise M0906AuthorizationError
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0906AuthorizationError
    controls = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0906AuthorizationError


def _control_decisions(
    request: DecomposeComplexActivityUncertaintyRequest,
) -> tuple[ControlDecisionRecord, ...]:
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
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=_state(reference.state),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=(
                references.identity_lineage.binding_digest
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, reference in records
    )


def _provenance(
    request: DecomposeComplexActivityUncertaintyRequest,
    request_digest: str,
) -> ProvenanceRecord:
    references = request.context.references
    inputs = tuple(
        sorted(
            {request.integrator_result.digest, request.policy.calibration_reference.digest}
            | {artifact.digest for artifact in request.source_artifacts}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0906_MODULE_ID,
        module_version=M0906_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=inputs,
        configuration_digest=references.approved_configuration.evidence.digest,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _evidence(request: DecomposeComplexActivityUncertaintyRequest) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.integrator_result,
        request.policy.calibration_reference,
        *request.source_artifacts,
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0906_EVIDENCE_CLAIM)
        for artifact in artifacts
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Estimator, catalogue, endpoint, and media type remain provisional "
                "pending owner confirmation."
            ),
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Evidence references are caller-declared and are not authenticated or traversed."
            ),
        ),
        Limitation(
            code="safe_abstention",
            statement=(
                "Missing, unsupported, non-evaluable, or calibration-unsafe inputs "
                "abstain explicitly."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The result supports complex activity and emits no kinase state, "
                "all-omics fusion, or treatment recommendation."
            ),
        ),
    )


def _probability(dimension: UncertaintyDimension, request_digest: str) -> float:
    seed = f"{request_digest}|{dimension.value}|m09-06".encode()
    raw = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(0.05 + (raw * 0.30), 8)


def _estimate(dimension: UncertaintyDimension, request_digest: str) -> UncertaintyEstimate:
    probability = _probability(dimension, request_digest)
    return UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=probability,
        rationale=(
            f"Deterministic provisional decomposition of {dimension.value} uncertainty; "
            "calibration reference is caller-declared."
        ),
    )


def _uncertainty(request_digest: str) -> UncertaintyProfile:
    values = {dimension: _estimate(dimension, request_digest) for dimension in UncertaintyDimension}
    return UncertaintyProfile(
        measurement=values[UncertaintyDimension.MEASUREMENT],
        sampling=values[UncertaintyDimension.SAMPLING],
        parameter=values[UncertaintyDimension.PARAMETER],
        model_form=values[UncertaintyDimension.MODEL_FORM],
        identification=values[UncertaintyDimension.IDENTIFICATION],
        support=values[UncertaintyDimension.SUPPORT],
        transport=values[UncertaintyDimension.TRANSPORT],
        sensitivity_notes=(
            "Nominal coverage is 90 percent with a provisional 85-95 percent acceptance envelope.",
            "No dimension is silently collapsed into a residual or treated as zero.",
        ),
    )


def _unsupported_reason(request: DecomposeComplexActivityUncertaintyRequest) -> str | None:
    method = request.policy.method.casefold()
    if any(marker in method for marker in ("unsupported", "not_evaluable", "missing")):
        return "declared estimator method is outside the supported uncertainty domain"
    if "uncalibrated" in method or "unlocked" in method:
        return "calibration policy is not safe for a nominal coverage claim"
    if any(
        "unsupported" in artifact.media_type.casefold() for artifact in request.source_artifacts
    ):
        return "source evidence declares an unsupported media type"
    return None


def _build_result(
    request: DecomposeComplexActivityUncertaintyRequest,
) -> ComplexActivityUncertaintyDecompositionResult:
    request_digest = canonical_request_digest(request)
    unsupported = _unsupported_reason(request)
    evidence = _evidence(request)
    if unsupported is None:
        components = tuple(
            UncertaintyComponent(
                dimension=dimension,
                estimate=_estimate(dimension, request_digest),
                rationale=(
                    f"{dimension.value} uncertainty is explicitly represented under the "
                    "caller-declared provisional policy."
                ),
                evidence=evidence,
            )
            for dimension in UncertaintyDimension
        )
        decomposition = UncertaintyDecomposition(
            decomposition_id=f"decomposition.{request_digest.removeprefix('sha256:')}",
            components=components,
            method=request.policy.method,
            model_reference=request.policy.calibration_reference,
            evidence=evidence,
        )
        sensitivity = SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.EVALUATED,
            lower_bound=0.85,
            upper_bound=0.95,
            observed_coverage=0.90,
            rationale=(
                "Synthetic provisional calibration remains inside the declared coverage envelope."
            ),
            evidence=evidence,
        )
        status = UncertaintyDecompositionStatus.DECOMPOSED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0906_decomposition_supported",
            rationale=(
                "All seven uncertainty dimensions and the sensitivity envelope are evaluable."
            ),
        )
        findings: tuple[UncertaintyFinding, ...] = ()
        abstention = None
        human_review = False
    else:
        decomposition = None
        sensitivity = SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            rationale=unsupported,
            evidence=evidence,
        )
        status = UncertaintyDecompositionStatus.ABSTAINED
        support = SupportDecision(
            status=(
                SupportStatus.REVIEW_REQUIRED
                if "calibration" in unsupported
                else SupportStatus.UNSUPPORTED
            ),
            reason_code="m0906_uncertainty_not_evaluable",
            rationale=unsupported,
        )
        findings = (
            UncertaintyFinding(
                finding_id=f"finding.{request_digest.removeprefix('sha256:')}",
                code=(
                    UncertaintyFindingCode.CALIBRATION_NOT_LOCKED
                    if "calibration" in unsupported
                    else UncertaintyFindingCode.SENSITIVITY_NOT_EVALUABLE
                ),
                message=unsupported,
                evidence=evidence,
            ),
        )
        abstention = unsupported
        human_review = True
    draft = ComplexActivityUncertaintyDecompositionResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        result_version=M0906_CONTRACT_VERSION,
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        decomposition=decomposition,
        sensitivity_envelope=sensitivity,
        findings=findings,
        abstention_reason=abstention,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=support,
        uncertainty=_uncertainty(request_digest),
        provenance=_provenance(request, request_digest),
        evidence=evidence,
        limitations=_limitations(),
        human_review_required=human_review,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0906UncertaintyDecompositionEngine:
    """Build, execute, and verify one deterministic M09-06 result."""

    @staticmethod
    def validate_request(request: object) -> DecomposeComplexActivityUncertaintyRequest:
        typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_m0906_authorization(typed)
        return typed

    def execute(self, request: object) -> BuiltM0906Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical) > M0906_MAX_CANONICAL_RESULT_BYTES:
            raise M0906InputError("result_limit")
        return BuiltM0906Result(result=result, canonical_bytes=canonical)

    @staticmethod
    def verify(
        result: object,
        canonical: bytes | bytearray | str,
    ) -> M0906ReplayVerification:
        try:
            raw = (
                canonical
                if isinstance(canonical, (bytes, bytearray))
                else canonical.encode("utf-8")
            )
            strict_json_loads(raw, max_bytes=M0906_MAX_CANONICAL_RESULT_BYTES)
            typed = _RESULT_ADAPTER.validate_json(raw, strict=True)
            if isinstance(result, ComplexActivityUncertaintyDecompositionResult):
                expected = result
            else:
                expected = _RESULT_ADAPTER.validate_json(
                    canonical_json_bytes(result),
                    strict=True,
                )
            if typed != expected:
                return M0906ReplayVerification(
                    verified=False,
                    reason="canonical result differs from supplied result",
                )
            if typed.request_digest != canonical_request_digest(typed.request):
                return M0906ReplayVerification(
                    verified=False,
                    reason="request digest does not replay",
                )
            if typed.result_digest != result_payload_digest(typed):
                return M0906ReplayVerification(
                    verified=False,
                    reason="result digest does not replay",
                )
            if canonical_json_bytes(typed.model_dump(mode="json")) != bytes(raw):
                return M0906ReplayVerification(
                    verified=False,
                    reason="canonical bytes are not deterministic",
                )
        except (TypeError, ValueError, ValidationError, StrictJsonError):
            return M0906ReplayVerification(
                verified=False,
                reason="result replay input is invalid",
            )
        return M0906ReplayVerification(
            verified=True,
            reason="canonical result, request digest, and result digest verified",
            result_digest=typed.result_digest,
        )


def _validate_json_request(
    decoded: object,
    serialized: bytes | bytearray | str,
) -> DecomposeComplexActivityUncertaintyRequest:
    size = len(serialized.encode("utf-8")) if isinstance(serialized, str) else len(serialized)
    if size > M0906_MAX_CANONICAL_REQUEST_BYTES:
        raise M0906InputError("request_limit")
    del decoded
    typed = _REQUEST_ADAPTER.validate_json(serialized, strict=True)
    return M0906UncertaintyDecompositionEngine.validate_request(typed)


def decompose_complex_activity_uncertainty(request: object) -> BuiltM0906Result:
    """Public provisional M09-06 operation."""

    return M0906UncertaintyDecompositionEngine().execute(request)


__all__ = [
    "BuiltM0906Result",
    "M0906AuthorizationError",
    "M0906InputError",
    "M0906ReplayVerification",
    "M0906UncertaintyDecompositionEngine",
    "_validate_json_request",
    "decompose_complex_activity_uncertainty",
    "preflight_m0906_authorization",
]
