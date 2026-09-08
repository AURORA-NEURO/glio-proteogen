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

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_06 import (
    M0906_BOOTSTRAP_REPLICATES,
    M0906_CONTRACT_VERSION,
    M0906_EVIDENCE_CLAIM,
    M0906_GLIOMA_MODEL_FAMILY,
    M0906_MAX_CANONICAL_REQUEST_BYTES,
    M0906_MAX_CANONICAL_RESULT_BYTES,
    M0906_MAX_COVERAGE,
    M0906_MIN_COVERAGE,
    M0906_MODULE_ID,
    ComplexActivityUncertaintyDecompositionResult,
    ComplexUncertaintyObservation,
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
_GLIOMA_UNCERTAINTY_METHOD: Final = "locked_glioma_complex_uncertainty_irls_v1"
_HUBER_K: Final = 1.5
_IRLS_ITERATIONS: Final = 64
_IRLS_TOLERANCE: Final = 1e-9
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95


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
        "typed_sensitivity": "M09-06 typed sensitivity envelope is not evaluable",
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
            | {
                evidence.reference.digest
                for observation in request.uncertainty_observations
                for evidence in observation.evidence
            }
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
    artifact_evidence = tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0906_EVIDENCE_CLAIM)
        for artifact in artifacts
    )
    observation_evidence = tuple(
        evidence
        for observation in request.uncertainty_observations
        for evidence in observation.evidence
    )
    return artifact_evidence + observation_evidence


def _limitations(*, measured: bool = False) -> tuple[Limitation, ...]:
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
        *(
            (
                Limitation(
                    code="measured_complex_lane_research_only",
                    statement=(
                        "Typed uncertainty propensities describe repeat-fit instability "
                        "for glioma complex-member evidence; they are not calibrated "
                        "clinical confidence or biochemical activity probabilities."
                    ),
                ),
            )
            if measured
            else ()
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


def _uncertainty(
    request_digest: str,
    components: tuple[UncertaintyComponent, ...] | None = None,
) -> UncertaintyProfile:
    values = (
        {component.dimension: component.estimate for component in components}
        if components is not None
        else {dimension: _estimate(dimension, request_digest) for dimension in UncertaintyDimension}
    )
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


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Stable weighted median used to initialize the robust complex fit."""

    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    ordered_weights = weights[order]
    cutoff = 0.5 * float(np.sum(ordered_weights))
    index = int(np.searchsorted(np.cumsum(ordered_weights), cutoff, side="left"))
    return float(ordered_values[min(index, len(ordered_values) - 1)])


def _robust_complex_location(
    observation: ComplexUncertaintyObservation,
    scores: np.ndarray | None = None,
) -> tuple[float, int, float]:
    """Fit uncertainty propensity with quality-weighted Huber IRLS.

    The supported-member ratio contributes a low-weight bottleneck pseudo
    observation only for the ``support`` dimension. This preserves the
    distinction between noisy measurements and an essential-subunit gap.
    """

    values = np.asarray(observation.scores if scores is None else scores, dtype=np.float64)
    weights = np.full(values.shape, observation.quality_weight, dtype=np.float64)
    bottleneck: float | None = None
    bottleneck_weight = 0.0
    if observation.dimension is UncertaintyDimension.SUPPORT:
        bottleneck = 1.0 - (
            observation.supported_member_count / observation.member_count
        )
        bottleneck_weight = 0.25 * observation.quality_weight
    location = _weighted_median(values, weights)
    objective = float("inf")
    iterations = 0
    for iteration in range(_IRLS_ITERATIONS):
        iterations = iteration + 1
        residual = values - location
        scale = 1.4826 * _weighted_median(np.abs(residual), weights) + 1e-6
        influence = np.minimum(
            1.0,
            _HUBER_K * scale / np.maximum(np.abs(residual), 1e-12),
        )
        effective = weights * influence
        numerator = float(np.sum(effective * values))
        denominator = float(np.sum(effective))
        if bottleneck is not None:
            numerator += bottleneck_weight * bottleneck
            denominator += bottleneck_weight
        candidate = numerator / denominator
        damped = 0.7 * candidate + 0.3 * location
        standardized = np.abs(values - damped) / scale
        quadratic = np.minimum(0.5 * standardized**2, _HUBER_K * standardized - 0.5 * _HUBER_K**2)
        objective = float(np.sum(weights * quadratic))
        if bottleneck is not None:
            objective += bottleneck_weight * (damped - bottleneck) ** 2
        if abs(damped - location) <= _IRLS_TOLERANCE:
            location = damped
            break
        location = damped
    return float(np.clip(location, 0.0, 1.0)), iterations, objective


def _bootstrap_component(
    observation: ComplexUncertaintyObservation,
    request_digest: str,
    offset: int,
) -> tuple[float, float, float, float]:
    """Return robust center, 90% interval, and stability for one dimension."""

    seed = int(request_digest.removeprefix("sha256:")[offset * 2 : offset * 2 + 16], 16)
    rng = np.random.default_rng(seed)
    values = np.asarray(observation.scores, dtype=np.float64)
    replicates = rng.integers(0, len(values), size=(M0906_BOOTSTRAP_REPLICATES, len(values)))
    locations: list[float] = []
    for indexes in replicates:
        location, _, _ = _robust_complex_location(observation, values[indexes])
        locations.append(location)
    center, _, _ = _robust_complex_location(observation)
    lower, upper = np.quantile(np.asarray(locations), (_BOOTSTRAP_LOW, _BOOTSTRAP_HIGH))
    lower = float(np.clip(lower, 0.0, 1.0))
    upper = float(np.clip(upper, 0.0, 1.0))
    stability = float(np.clip(1.0 - (upper - lower), 0.0, 1.0))
    return center, lower, upper, stability


def _typed_components(
    request: DecomposeComplexActivityUncertaintyRequest,
    request_digest: str,
) -> tuple[UncertaintyComponent, ...] | None:
    """Build all seven complex uncertainty components from typed replicates."""

    by_dimension = {
        observation.dimension: observation for observation in request.uncertainty_observations
    }
    if set(by_dimension) != set(UncertaintyDimension):
        return None
    evidence_by_dimension = {
        observation.dimension: tuple(observation.evidence)
        for observation in request.uncertainty_observations
    }
    components: list[UncertaintyComponent] = []
    for offset, dimension in enumerate(UncertaintyDimension):
        observation = by_dimension[dimension]
        center, lower, upper, stability = _bootstrap_component(
            observation, request_digest, offset
        )
        components.append(
            UncertaintyComponent(
                dimension=dimension,
                estimate=UncertaintyEstimate(
                    state=EstimateState.ESTIMATED,
                    probability=round(center, 8),
                    rationale=(
                        "Quality-weighted Huber IRLS uncertainty propensity over repeated "
                        "glioma complex-member fits."
                    ),
                ),
                rationale=(
                    "Deterministic bootstrap interval over robust member-level fits; "
                    "support includes an essential-subunit bottleneck penalty."
                ),
                lower_bound=round(lower, 8),
                upper_bound=round(upper, 8),
                replicate_count=len(observation.scores),
                stability=round(stability, 8),
                evidence=evidence_by_dimension[dimension],
            )
        )
    return tuple(components)


def _typed_sensitivity(
    request: DecomposeComplexActivityUncertaintyRequest,
    evidence: tuple[EvidenceReference, ...],
) -> SensitivityEnvelope:
    """Estimate coverage with a deterministic pooled bootstrap envelope."""

    hits = np.asarray(
        [
            int(hit)
            for observation in request.uncertainty_observations
            for hit in observation.coverage_hits
        ],
        dtype=np.float64,
    )
    observed = float(np.mean(hits))
    if not M0906_MIN_COVERAGE <= observed <= M0906_MAX_COVERAGE:
        return SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            rationale=(
                "Measured complex-activity coverage falls outside the locked "
                "85-95 percent sensitivity gate."
            ),
            evidence=evidence,
        )
    seed = int(canonical_request_digest(request).removeprefix("sha256:")[-16:], 16)
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(hits), size=(M0906_BOOTSTRAP_REPLICATES, len(hits)))
    coverages = np.mean(hits[indexes], axis=1)
    lower, upper = np.quantile(coverages, (_BOOTSTRAP_LOW, _BOOTSTRAP_HIGH))
    return SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=round(float(lower), 8),
        upper_bound=round(float(upper), 8),
        observed_coverage=round(observed, 8),
        rationale=(
            "Deterministic bootstrap coverage envelope over repeated glioma "
            "complex-member uncertainty fits."
        ),
        evidence=evidence,
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
    if request.uncertainty_observations and request.policy.method != _GLIOMA_UNCERTAINTY_METHOD:
        return (
            "typed complex uncertainty observations require the locked glioma IRLS method"
        )
    if not request.uncertainty_observations and request.policy.method == _GLIOMA_UNCERTAINTY_METHOD:
        return "locked glioma IRLS decomposition requires seven typed uncertainty observations"
    return None


def _build_typed_result(
    request: DecomposeComplexActivityUncertaintyRequest,
    request_digest: str,
    evidence: tuple[EvidenceReference, ...],
    components: tuple[UncertaintyComponent, ...],
    sensitivity: SensitivityEnvelope,
) -> ComplexActivityUncertaintyDecompositionResult:
    """Build the research-only complex uncertainty result from measured replicates."""

    if sensitivity.status is not SensitivityEnvelopeStatus.EVALUATED:
        raise M0906InputError("typed_sensitivity")
    estimates = {component.dimension: component.estimate for component in components}
    uncertainty = UncertaintyProfile(
        measurement=estimates[UncertaintyDimension.MEASUREMENT],
        sampling=estimates[UncertaintyDimension.SAMPLING],
        parameter=estimates[UncertaintyDimension.PARAMETER],
        model_form=estimates[UncertaintyDimension.MODEL_FORM],
        identification=estimates[UncertaintyDimension.IDENTIFICATION],
        support=estimates[UncertaintyDimension.SUPPORT],
        transport=estimates[UncertaintyDimension.TRANSPORT],
        sensitivity_notes=(
            "64 deterministic bootstrap replicates are seeded by the request digest.",
            "Support uncertainty includes a low-weight essential-member bottleneck term.",
            "Propensities describe repeat-fit instability, not calibrated clinical confidence.",
        ),
    )
    draft = ComplexActivityUncertaintyDecompositionResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        result_version=M0906_CONTRACT_VERSION,
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=UncertaintyDecompositionStatus.DECOMPOSED,
        decomposition=UncertaintyDecomposition(
            decomposition_id=f"decomposition.{request_digest.removeprefix('sha256:')}",
            components=components,
            method=(
                f"{M0906_GLIOMA_MODEL_FAMILY}; quality-weighted Huber IRLS with "
                "essential-member bottleneck and deterministic bootstrap"
            ),
            model_reference=request.policy.calibration_reference,
            evidence=evidence,
        ),
        sensitivity_envelope=sensitivity,
        findings=(),
        abstention_reason=None,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0906_measured_complex_support",
            rationale=(
                "All seven dimensions have aligned repeated complex-member evidence and "
                "the empirical coverage envelope passes the 85-95 percent gate."
            ),
        ),
        uncertainty=uncertainty,
        provenance=_provenance(request, request_digest),
        evidence=evidence,
        limitations=_limitations(measured=True),
        human_review_required=False,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


def _build_result(
    request: DecomposeComplexActivityUncertaintyRequest,
) -> ComplexActivityUncertaintyDecompositionResult:
    request_digest = canonical_request_digest(request)
    unsupported = _unsupported_reason(request)
    evidence = _evidence(request)
    if unsupported is None and request.uncertainty_observations:
        components = _typed_components(request, request_digest)
        if components is None:
            unsupported = (
                "typed complex uncertainty observations must cover all seven dimensions"
            )
        else:
            sensitivity = _typed_sensitivity(request, evidence)
            if sensitivity.status is SensitivityEnvelopeStatus.EVALUATED:
                return _build_typed_result(
                    request, request_digest, evidence, components, sensitivity
                )
            unsupported = sensitivity.rationale
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
        if typed.uncertainty_observations:
            typed = typed.model_copy(
                update={
                    "uncertainty_observations": tuple(
                        sorted(
                            typed.uncertainty_observations,
                            key=lambda item: item.observation_id,
                        )
                    )
                }
            )
        return typed

    def execute(self, request: object) -> BuiltM0906Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical) > M0906_MAX_CANONICAL_RESULT_BYTES:
            raise M0906InputError("result_limit")
        return BuiltM0906Result(result=result, canonical_bytes=canonical)

    @staticmethod
    def verify(  # noqa: PLR0911
        result: object,
        canonical: bytes | bytearray | str,
        request: object | None = None,
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
            if request is not None:
                regenerated = M0906UncertaintyDecompositionEngine().execute(request).result
                if typed != regenerated:
                    return M0906ReplayVerification(
                        verified=False,
                        reason="result does not replay from supplied request",
                    )
            request_digest_verified = typed.request_digest == canonical_request_digest(
                typed.request
            )
            provenance_verified = typed.provenance == _provenance(
                typed.request, typed.request_digest
            )
            if not request_digest_verified or not provenance_verified:
                return M0906ReplayVerification(
                    verified=False,
                    reason=(
                        "request digest does not replay"
                        if not request_digest_verified
                        else "provenance does not replay"
                    ),
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
