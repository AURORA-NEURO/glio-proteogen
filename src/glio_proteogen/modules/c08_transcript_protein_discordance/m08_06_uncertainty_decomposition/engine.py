"""Deterministic, replay-verifiable, safe-abstaining M08-06 engine."""

# Public diagnostics intentionally collapse hostile input into stable errors.
# ruff: noqa: TRY003

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from math import sqrt
from typing import Final

import numpy as np
from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m08_06 import (
    M0806_CONTRACT_VERSION,
    M0806_EVIDENCE_CLAIM,
    M0806_GLIOMA_MODEL_FAMILY,
    M0806_PARENT,
    DecomposeTranscriptProteinUncertaintyRequest,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    TranscriptProteinUncertaintyDecompositionResult,
    TypedUncertaintyEvidenceState,
    TypedUncertaintyObservation,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    UncertaintyFinding,
    UncertaintyFindingCode,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    EstimateState,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

from .kernel import M0806UncertaintyKernel

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeTranscriptProteinUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(TranscriptProteinUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_TYPED_MIN_OBSERVATIONS: Final = 3
_TYPED_MIN_MODALITIES: Final = 2
_TYPED_MIN_PROGRAMS: Final = 2
_TYPED_HUBER_K: Final = 1.5
_TYPED_RIDGE: Final = 0.05
_TYPED_BOOTSTRAP_LOW: Final = 0.05
_TYPED_BOOTSTRAP_HIGH: Final = 0.95
_TYPED_LOCATION_TOLERANCE: Final = 1e-7
_TYPED_DAMPING: Final = 0.3
_TYPED_OBJECTIVE_TOLERANCE: Final = 1e-10
_TYPED_BACKTRACKING_STEPS: Final = 16
_TYPED_BACKTRACKING_FACTOR: Final = 0.5


@dataclass(frozen=True, slots=True)
class _TypedUncertaintyFit:
    center: float
    modality_centers: tuple[float, ...]
    program_centers: tuple[float, ...]
    draws: tuple[float, ...]
    effective_observations: float


class M0806AuthorizationError(PermissionError):
    """Required identity, consent, provenance, and support controls are not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M08-06 requires accepted configuration, resolved identity, accepted provenance "
            "and quality/support/intended-use controls with granted consent"
        )


class M0806ReplayVerificationError(ValueError):
    """A result is not a canonical receipt for its exact request."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M08-06 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0806_authorization(candidate: object) -> None:
    """Check all seven controls before validating the complete upstream handoff."""

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
        raise M0806AuthorizationError from None
    if states != expected:
        raise M0806AuthorizationError


def _evidence(
    request: DecomposeTranscriptProteinUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0806_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )


def _limitations(*, typed: bool = False) -> tuple[Limitation, ...]:
    limitations = [
        Limitation(
            code="uncertainty_decomposition_only",
            statement="Output is limited to typed uncertainty dimensions and sensitivity metadata.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no kinase state, generic all-omics fusion, "
                "treatment recommendation, or protein subtype estimate."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M08-06 ABI, calibration policy, and M08-05 handoff remain provisional "
                "pending owner confirmation."
            ),
        ),
    ]
    if typed:
        limitations.append(
            Limitation(
                code="glioma_internal_calibration_only",
                statement=(
                    "The typed glioma decomposition reports internal bootstrap sensitivity; "
                    "it is not externally calibrated and cannot support diagnosis, prognosis, "
                    "or treatment decisions."
                ),
            )
        )
    return tuple(limitations)


def _typed_target(
    item: TypedUncertaintyObservation,
    perturbation: float = 0.0,
) -> float:
    if item.state is TypedUncertaintyEvidenceState.OBSERVED:
        return float(item.effect or 0.0) + perturbation
    # A left-censored effect is an upper bound. Keep the exact boundary and
    # let the robust location fit apply influence only when the estimate
    # violates it; subtracting half an error would manufacture a target.
    return float(item.censoring_limit or 0.0) + perturbation


def _typed_huber(value: float) -> float:
    absolute = abs(value)
    return 0.5 * value * value if absolute <= _TYPED_HUBER_K else _TYPED_HUBER_K * (
        absolute - 0.5 * _TYPED_HUBER_K
    )


def _typed_location_objective(
    value: float,
    observations: tuple[TypedUncertaintyObservation, ...],
    targets: tuple[float, ...],
) -> float:
    """Evaluate the robust one-dimensional objective used by the IRLS update."""

    objective = _TYPED_RIDGE * value * value
    for item, target in zip(observations, targets, strict=True):
        residual = (value - target) / float(item.standard_error or 1.0)
        if item.state is TypedUncertaintyEvidenceState.LEFT_CENSORED:
            residual = max(0.0, residual)
        objective += item.quality_weight * _typed_huber(residual)
    return float(objective)


def _typed_active(
    request: DecomposeTranscriptProteinUncertaintyRequest,
) -> tuple[TypedUncertaintyObservation, ...]:
    return tuple(
        item
        for item in sorted(request.typed_observations, key=lambda item: item.observation_id)
        if item.state
        in {TypedUncertaintyEvidenceState.OBSERVED, TypedUncertaintyEvidenceState.LEFT_CENSORED}
        and item.quality_weight > 0.0
    )


def _typed_robust_location(  # noqa: C901, PLR0912, PLR0915 - explicit IRLS branches are auditable.
    observations: tuple[TypedUncertaintyObservation, ...],
    perturbations: Mapping[str, float] | None = None,
) -> float:
    if not observations:
        return 0.0
    targets = tuple(
        _typed_target(item, (perturbations or {}).get(item.observation_id, 0.0))
        for item in observations
    )
    weights = tuple(
        item.quality_weight / max(float(item.standard_error or 1.0) ** 2, 1e-12)
        for item in observations
    )
    observed = tuple(
        (target, weight)
        for item, target, weight in zip(observations, targets, weights, strict=True)
        if item.state is TypedUncertaintyEvidenceState.OBSERVED
    )
    limits = tuple(
        target
        for item, target in zip(observations, targets, strict=True)
        if item.state is TypedUncertaintyEvidenceState.LEFT_CENSORED
    )
    if observed:
        value = sum(target * weight for target, weight in observed) / max(
            sum(weight for _, weight in observed), 1e-12
        )
    elif limits:
        value = min(0.0, *limits)
    else:
        value = 0.0
    if limits:
        value = min(value, *limits)
    objective = _typed_location_objective(value, observations, targets)
    for _ in range(32):
        robust_weights = []
        for item, target, base_weight in zip(observations, targets, weights, strict=True):
            residual = (value - target) / float(item.standard_error or 1.0)
            magnitude = abs(residual)
            influence = 1.0 if magnitude <= _TYPED_HUBER_K else _TYPED_HUBER_K / magnitude
            if item.state is TypedUncertaintyEvidenceState.LEFT_CENSORED:
                # The bootstrap perturbation belongs to the detection boundary,
                # not to a fabricated observed effect.
                limit = target
                if value <= limit:
                    influence = 0.0
                else:
                    residual = (value - limit) / float(item.standard_error or 1.0)
                    magnitude = abs(residual)
                    influence = 1.0 if magnitude <= _TYPED_HUBER_K else _TYPED_HUBER_K / magnitude
            robust_weights.append(base_weight * influence)
        denominator = sum(robust_weights) + _TYPED_RIDGE
        proposal = sum(
            weight * target for weight, target in zip(robust_weights, targets, strict=True)
        ) / max(denominator, 1e-12)
        limits = tuple(
            target
            for item, target in zip(observations, targets, strict=True)
            if item.state is TypedUncertaintyEvidenceState.LEFT_CENSORED
        )
        if limits:
            proposal = min(proposal, *limits)
        candidate = value + _TYPED_DAMPING * (proposal - value)
        next_objective = _typed_location_objective(candidate, observations, targets)
        if next_objective > objective + _TYPED_OBJECTIVE_TOLERANCE:
            # Robust weights can change at censor boundaries. Backtrack the
            # complete scalar step to keep the fit objective-safe.
            next_value = value
            next_objective = objective
            step = _TYPED_DAMPING
            delta = proposal - value
            for _ in range(_TYPED_BACKTRACKING_STEPS):
                step *= _TYPED_BACKTRACKING_FACTOR
                trial = value + step * delta
                if limits:
                    trial = min(trial, *limits)
                trial_objective = _typed_location_objective(trial, observations, targets)
                if trial_objective <= objective + _TYPED_OBJECTIVE_TOLERANCE:
                    next_value = trial
                    next_objective = trial_objective
                    break
        else:
            next_value = candidate
        if abs(next_value - value) <= _TYPED_LOCATION_TOLERANCE:
            value = next_value
            break
        value = next_value
        objective = next_objective
    return float(f"{value:.8f}")


def _typed_fit(
    request: DecomposeTranscriptProteinUncertaintyRequest,
) -> _TypedUncertaintyFit | None:
    active = _typed_active(request)
    modalities = tuple(sorted({item.modality for item in active}))
    programs = tuple(sorted({item.program.value for item in active}))
    if (
        len(active) < _TYPED_MIN_OBSERVATIONS
        or len(modalities) < _TYPED_MIN_MODALITIES
        or len(programs) < _TYPED_MIN_PROGRAMS
    ):
        return None
    center = _typed_robust_location(active)
    modality_centers = tuple(
        _typed_robust_location(tuple(item for item in active if item.modality == modality))
        for modality in modalities
    )
    program_centers = tuple(
        _typed_robust_location(tuple(item for item in active if item.program.value == program))
        for program in programs
    )
    precision = tuple(
        item.quality_weight / max(float(item.standard_error or 1.0) ** 2, 1e-12) for item in active
    )
    effective_observations = sum(precision) ** 2 / max(
        sum(value * value for value in precision), 1e-12
    )
    seed = int.from_bytes(
        hashlib.sha256(canonical_request_digest(request).encode("utf-8")).digest()[:8],
        "big",
        signed=False,
    )
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(request.bootstrap_replicates):
        perturbations = {
            item.observation_id: float(rng.normal(0.0, item.standard_error or 0.0))
            for item in active
        }
        draws.append(_typed_robust_location(active, perturbations))
    return _TypedUncertaintyFit(
        center=center,
        modality_centers=modality_centers,
        program_centers=program_centers,
        draws=tuple(draws),
        effective_observations=effective_observations,
    )


def _typed_probability(value: float) -> float:
    return float(f"{max(0.0, min(1.0, value)):.8f}")


def _typed_decomposition(
    request: DecomposeTranscriptProteinUncertaintyRequest,
    fit: _TypedUncertaintyFit,
) -> tuple[UncertaintyDecomposition, SensitivityEnvelope]:
    active = _typed_active(request)
    mean_se = sum(float(item.standard_error or 0.0) for item in active) / len(active)
    mean_quality = sum(item.quality_weight for item in active) / len(active)
    modality_spread = max(fit.modality_centers) - min(fit.modality_centers)
    program_spread = max(fit.program_centers) - min(fit.program_centers)
    draw_mean = sum(fit.draws) / max(1, len(fit.draws))
    draw_variance = sum((value - draw_mean) ** 2 for value in fit.draws) / max(1, len(fit.draws))
    draw_sd = sqrt(draw_variance)
    lower = min(fit.draws)
    upper = max(fit.draws)
    ordered = sorted(fit.draws)
    low_index = max(
        0,
        min(len(ordered) - 1, int(np.ceil(_TYPED_BOOTSTRAP_LOW * len(ordered))) - 1),
    )
    high_index = max(
        0,
        min(len(ordered) - 1, int(np.ceil(_TYPED_BOOTSTRAP_HIGH * len(ordered))) - 1),
    )
    lower = ordered[low_index]
    upper = ordered[high_index]
    observed_coverage = sum(lower <= value <= upper for value in fit.draws) / max(1, len(fit.draws))
    envelope = SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        nominal_coverage=0.9,
        lower_bound=_typed_probability(max(0.0, observed_coverage - 0.05)),
        upper_bound=_typed_probability(min(1.0, observed_coverage + 0.05)),
        observed_coverage=_typed_probability(observed_coverage),
        rationale=(
            "Internal digest-seeded bootstrap coverage over typed glioma effects; this is "
            "not external calibration or clinical validation."
        ),
        evidence=_evidence(request),
    )
    values = {
        UncertaintyDimension.MEASUREMENT: (
            mean_se / (1.0 + mean_se),
            "reported standard errors propagated through the robust location fit",
        ),
        UncertaintyDimension.SAMPLING: (
            draw_sd / (1.0 + draw_sd),
            "digest-seeded bootstrap dispersion across typed evidence",
        ),
        UncertaintyDimension.PARAMETER: (
            1.0 / sqrt(max(fit.effective_observations, 1.0)),
            "effective precision limits parameter identification",
        ),
        UncertaintyDimension.MODEL_FORM: (
            modality_spread / (1.0 + modality_spread),
            "spread of modality-specific robust fits is a model-form sensitivity",
        ),
        UncertaintyDimension.IDENTIFICATION: (
            program_spread / (1.0 + program_spread),
            "between-program separation limits a single shared coordinate",
        ),
        UncertaintyDimension.SUPPORT: (
            1.0 - mean_quality,
            "one minus mean caller-supplied quality weight",
        ),
        UncertaintyDimension.TRANSPORT: (
            abs(fit.center - draw_mean) / (1.0 + abs(fit.center - draw_mean)),
            "bootstrap center shift is an internal transport sensitivity proxy",
        ),
    }
    components = tuple(
        UncertaintyComponent(
            dimension=dimension,
            estimate=UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=_typed_probability(probability),
                rationale=rationale,
            ),
            rationale=rationale,
            evidence=_evidence(request),
        )
        for dimension, (probability, rationale) in values.items()
    )
    decomposition = UncertaintyDecomposition(
        decomposition_id=f"decomposition.{canonical_request_digest(request).removeprefix('sha256:')}",
        components=components,
        method="digest-seeded robust modality/program bootstrap decomposition",
        model_reference=request.estimator_result,
        evidence=_evidence(request),
    )
    return decomposition, envelope


class M0806UncertaintyDecompositionEngine:
    """Bind M08-05 evidence and abstain until coverage is review-locked."""

    __slots__ = ("_kernel",)

    def __init__(self, kernel: M0806UncertaintyKernel | None = None) -> None:
        self._kernel = kernel or M0806UncertaintyKernel()

    def decompose(
        self,
        request: object,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        preflight_m0806_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        validated = validated.model_copy(
            update={
                "typed_observations": tuple(
                    sorted(validated.typed_observations, key=lambda item: item.observation_id)
                ),
                "source_artifacts": tuple(
                    sorted(validated.source_artifacts, key=lambda item: item.artifact_id)
                ),
            }
        )
        if validated.typed_observations:
            return self._typed_result(validated)
        return self._result(validated)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        """Validate digest closure and optionally replay the exact immutable request."""

        if isinstance(result, BaseModel) and not verify_result_digest(result):
            raise M0806ReplayVerificationError("result digest does not match canonical payload")
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M0806ReplayVerificationError("result is not a strict result envelope") from error
        if not verify_result_digest(validated):
            raise M0806ReplayVerificationError("result digest does not match canonical payload")
        if replay:
            expected = self.decompose(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M0806ReplayVerificationError("replayed request produced a different result")
        return validated

    def _typed_result(
        self,
        request: DecomposeTranscriptProteinUncertaintyRequest,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        fit = _typed_fit(request)
        if fit is None:
            return self._result(request, typed=True)
        decomposition, envelope = _typed_decomposition(request, fit)
        by_dimension = {item.dimension: item.estimate for item in decomposition.components}
        profile = UncertaintyProfile(
            measurement=by_dimension[UncertaintyDimension.MEASUREMENT],
            sampling=by_dimension[UncertaintyDimension.SAMPLING],
            parameter=by_dimension[UncertaintyDimension.PARAMETER],
            model_form=by_dimension[UncertaintyDimension.MODEL_FORM],
            identification=by_dimension[UncertaintyDimension.IDENTIFICATION],
            support=by_dimension[UncertaintyDimension.SUPPORT],
            transport=by_dimension[UncertaintyDimension.TRANSPORT],
            sensitivity_notes=(
                "All probabilities are internal sensitivity scores from typed glioma evidence; "
                "they are not calibrated clinical probabilities.",
            ),
        )
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0806_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.DECOMPOSED,
            "decomposition": decomposition,
            "sensitivity_envelope": envelope,
            "findings": (),
            "abstention_reason": None,
            "parent_target": M0806_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0806_typed_glioma_supported",
                rationale=(
                    "Typed glioma evidence spans the required programs and modalities; "
                    "robust bootstrap sensitivity was computed deterministically."
                ),
            ),
            "uncertainty": profile,
            "provenance": expected_provenance(request, request_hash, policy_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(typed=True),
            "human_review_required": False,
            "typed_model": True,
            "model_family": M0806_GLIOMA_MODEL_FAMILY,
        }
        constructed = TranscriptProteinUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def _result(
        self,
        request: DecomposeTranscriptProteinUncertaintyRequest,
        *,
        typed: bool = False,
    ) -> TranscriptProteinUncertaintyDecompositionResult:
        request_hash = canonical_request_digest(request)
        policy_hash = sha256_digest(request.policy)
        finding = UncertaintyFinding(
            finding_id=f"finding.{request_hash.removeprefix('sha256:')}",
            code=UncertaintyFindingCode.CALIBRATION_NOT_LOCKED,
            message=(
                "Owner-confirmed calibration and synthetic, internal, and external "
                "coverage evidence are not locked."
            ),
            evidence=_evidence(request),
        )
        sensitivity: SensitivityEnvelope = self._kernel.sensitivity_envelope(request.policy)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0806_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.ABSTAINED,
            "decomposition": None,
            "sensitivity_envelope": sensitivity,
            "findings": (finding,),
            "abstention_reason": finding.message,
            "parent_target": M0806_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m0806_uncertainty_review_required",
                rationale=(
                    "Coverage, calibration, and transport evidence require owner review "
                    "before any decomposition is released."
                ),
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash, policy_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(typed=typed),
            "human_review_required": True,
            "typed_model": typed,
            "model_family": M0806_GLIOMA_MODEL_FAMILY if typed else None,
        }
        constructed = TranscriptProteinUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def decompose_transcript_protein_uncertainty(
    request: object,
) -> TranscriptProteinUncertaintyDecompositionResult:
    """Public provisional M08-06 operation."""

    return M0806UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M0806AuthorizationError",
    "M0806ReplayVerificationError",
    "M0806UncertaintyDecompositionEngine",
    "decompose_transcript_protein_uncertainty",
    "preflight_m0806_authorization",
]
