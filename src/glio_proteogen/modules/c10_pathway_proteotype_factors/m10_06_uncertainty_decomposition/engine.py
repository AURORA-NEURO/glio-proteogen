"""Deterministic, fail-closed provisional M10-06 runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import numpy as np
from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m10_06 import (
    M1006_BOOTSTRAP_REPLICATES,
    M1006_CONTRACT_VERSION,
    M1006_EVIDENCE_CLAIM,
    M1006_MAX_COVERAGE,
    M1006_MIN_COMPONENTS,
    M1006_MIN_COVERAGE,
    M1006_PARENT,
    DecomposeProteinRnaDiscordanceUncertaintyRequest,
    ProteinRnaDiscordanceUncertaintyDecompositionResult,
    SensitivityEnvelope,
    SensitivityEnvelopeStatus,
    UncertaintyComponent,
    UncertaintyDecomposition,
    UncertaintyDecompositionStatus,
    UncertaintyDimension,
    UncertaintyFinding,
    UncertaintyFindingCode,
    UncertaintyObservation,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_06.canonical import (
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import (
    EstimateState,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(DecomposeProteinRnaDiscordanceUncertaintyRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceUncertaintyDecompositionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_HUBER_K: Final = 1.5
_IRLS_ITERATIONS: Final = 25
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_IRLS_TOLERANCE: Final = 1e-9


class M1006UncertaintyDecompositionAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for decomposition."""

    def __init__(self) -> None:
        super().__init__(
            "M10-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1006UncertaintyDecompositionReplayError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M10-06 replay verification failed: {detail}")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_uncertainty_decomposition_authorization(candidate: object) -> None:
    """Check seven control decisions before strict model validation."""

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
        raise M1006UncertaintyDecompositionAuthorizationError from None
    if states != expected:
        raise M1006UncertaintyDecompositionAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_uncertainty_decomposition_authorization(candidate)
    return candidate


def _evidence(
    request: DecomposeProteinRnaDiscordanceUncertaintyRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.integrator_result,
        request.policy.calibration_reference,
        *request.source_artifacts,
    )
    artifact_evidence = tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1006_EVIDENCE_CLAIM)
        for artifact in artifacts
    )
    observation_evidence = tuple(
        evidence
        for observation in request.uncertainty_observations
        for evidence in observation.evidence
    )
    return artifact_evidence + observation_evidence


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Deterministic weighted median used to initialize the robust estimator."""

    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    ordered_weights = weights[order]
    cutoff = 0.5 * float(np.sum(ordered_weights))
    index = int(np.searchsorted(np.cumsum(ordered_weights), cutoff, side="left"))
    return float(ordered_values[min(index, len(ordered_values) - 1)])


def _robust_location(scores: tuple[float, ...], quality_weight: float) -> float:
    """Estimate uncertainty propensity with damped Huber IRLS, not a proxy mean."""

    values = np.asarray(scores, dtype=np.float64)
    weights = np.full(values.shape, quality_weight, dtype=np.float64)
    location = _weighted_median(values, weights)
    for _ in range(_IRLS_ITERATIONS):
        residual = values - location
        scale = 1.4826 * _weighted_median(np.abs(residual), weights) + 1e-6
        influence = np.minimum(1.0, _HUBER_K * scale / np.maximum(np.abs(residual), 1e-12))
        effective = weights * influence
        candidate = float(np.sum(effective * values) / np.sum(effective))
        damped = 0.7 * candidate + 0.3 * location
        if abs(damped - location) <= _IRLS_TOLERANCE:
            return float(np.clip(damped, 0.0, 1.0))
        location = damped
    return float(np.clip(location, 0.0, 1.0))


def _bootstrap_interval(
    observation: UncertaintyObservation,
    seed: int,
) -> tuple[float, float]:
    """Return a deterministic percentile interval over replicate IRLS fits."""

    rng = np.random.default_rng(seed)
    values = np.asarray(observation.scores, dtype=np.float64)
    replicates = rng.integers(
        0,
        len(values),
        size=(M1006_BOOTSTRAP_REPLICATES, len(values)),
    )
    locations = tuple(
        _robust_location(
            tuple(float(value) for value in values[indexes]), observation.quality_weight
        )
        for indexes in replicates
    )
    lower, upper = np.quantile(locations, (_BOOTSTRAP_LOW, _BOOTSTRAP_HIGH))
    return float(np.clip(lower, 0.0, 1.0)), float(np.clip(upper, 0.0, 1.0))


def _measured_components(
    request: DecomposeProteinRnaDiscordanceUncertaintyRequest,
    request_hash: str,
) -> tuple[UncertaintyComponent, ...] | None:
    by_dimension = {
        observation.dimension: observation for observation in request.uncertainty_observations
    }
    if len(by_dimension) != M1006_MIN_COMPONENTS or set(by_dimension) != set(UncertaintyDimension):
        return None
    seed_base = int(request_hash.removeprefix("sha256:")[:16], 16)
    components: list[UncertaintyComponent] = []
    for offset, dimension in enumerate(UncertaintyDimension):
        observation = by_dimension[dimension]
        location = _robust_location(observation.scores, observation.quality_weight)
        lower, upper = _bootstrap_interval(observation, seed_base + offset)
        components.append(
            UncertaintyComponent(
                dimension=dimension,
                estimate=UncertaintyEstimate(
                    state=EstimateState.ESTIMATED,
                    probability=round(location, 8),
                    rationale=(
                        "Quality-weighted Huber IRLS location of repeated glioma "
                        "proteotype residual instability scores."
                    ),
                ),
                rationale=(
                    "Deterministic bootstrap interval over robust replicate fits; "
                    "higher propensity indicates less stable evidence for this dimension."
                ),
                lower_bound=round(lower, 8),
                upper_bound=round(upper, 8),
                replicate_count=len(observation.scores),
                stability=round(max(0.0, 1.0 - (upper - lower)), 8),
                evidence=observation.evidence,
            )
        )
    return tuple(components)


def _measured_sensitivity(
    request: DecomposeProteinRnaDiscordanceUncertaintyRequest,
    request_hash: str,
    evidence: tuple[EvidenceReference, ...],
) -> SensitivityEnvelope:
    hits = np.asarray(
        [
            hit
            for observation in request.uncertainty_observations
            for hit in observation.coverage_hits
        ],
        dtype=np.float64,
    )
    observed = float(np.mean(hits))
    if not M1006_MIN_COVERAGE <= observed <= M1006_MAX_COVERAGE:
        return SensitivityEnvelope(
            status=SensitivityEnvelopeStatus.ABSTAINED,
            rationale=(
                "Measured calibration coverage falls outside the locked provisional "
                "85-95 percent sensitivity gate."
            ),
            evidence=evidence,
        )
    seed = int(request_hash.removeprefix("sha256:")[-16:], 16)
    rng = np.random.default_rng(seed)
    indexes = rng.integers(0, len(hits), size=(M1006_BOOTSTRAP_REPLICATES, len(hits)))
    coverages = tuple(float(np.mean(hits[index])) for index in indexes)
    lower, upper = np.quantile(coverages, (_BOOTSTRAP_LOW, _BOOTSTRAP_HIGH))
    return SensitivityEnvelope(
        status=SensitivityEnvelopeStatus.EVALUATED,
        lower_bound=round(float(lower), 8),
        upper_bound=round(float(upper), 8),
        observed_coverage=round(observed, 8),
        rationale=(
            "Deterministic bootstrap coverage envelope over repeated glioma "
            "proteotype calibration indicators."
        ),
        evidence=evidence,
    )


def _limitations(*, measured: bool = False) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="decomposition_not_published",
            statement=(
                "Opaque or incomplete requests remain abstained; measured requests use only "
                "the typed replicate lane."
            ),
        ),
        Limitation(
            code="coverage_not_evaluable",
            statement=(
                "Nominal 90 percent coverage cannot be claimed without locked benchmark evidence."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no parent protein-RNA discordance claim, kinase state, "
                "generic all-omics fusion, or treatment advice."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "Uncertainty ABI, sensitivity representation, and M10-05 handoff remain "
                "provisional."
            ),
        ),
        *(
            (
                Limitation(
                    code="measured_lane_research_only",
                    statement=(
                        "Measured decomposition is a research diagnostic for glioma "
                        "proteotype stability and is not a clinical confidence claim."
                    ),
                ),
            )
            if measured
            else ()
        ),
    )


def _findings(evidence: tuple[EvidenceReference, ...]) -> tuple[UncertaintyFinding, ...]:
    return tuple(
        UncertaintyFinding(
            finding_id=f"finding.m1006.{code.value}",
            code=code,
            message=message,
            evidence=evidence,
        )
        for code, message in (
            (
                UncertaintyFindingCode.CALIBRATION_NOT_LOCKED,
                "Calibration and nominal coverage evidence are not owner-locked.",
            ),
            (
                UncertaintyFindingCode.SENSITIVITY_NOT_EVALUABLE,
                "Sensitivity envelope is not evaluable before the locked benchmark lane.",
            ),
            (
                UncertaintyFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The uncertainty decomposition ABI awaits owner confirmation.",
            ),
        )
    )


class M1006UncertaintyDecompositionEngine:
    """Bind deterministic inputs and abstain until calibration gates are locked."""

    __slots__ = ()

    def decompose(self, request: object) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: DecomposeProteinRnaDiscordanceUncertaintyRequest
    ) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        components = _measured_components(request, request_hash)
        sensitivity = (
            _measured_sensitivity(request, request_hash, evidence)
            if components is not None
            else SensitivityEnvelope(
                status=SensitivityEnvelopeStatus.ABSTAINED,
                rationale=(
                    "Sensitivity is abstained until all seven dimensions provide aligned "
                    "replicate coverage indicators."
                ),
                evidence=evidence,
            )
        )
        measured = (
            components is not None
            and sensitivity.status is SensitivityEnvelopeStatus.EVALUATED
        )
        if measured and components is not None:
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
                    "64-replicate deterministic bootstrap; request digest seeds all draws.",
                    "IRLS influence weights downweight unstable replicate outliers.",
                ),
            )
            measured_payload: dict[str, object] = {
                "output_type": "protein_rna_discordance_uncertainty_decomposition",
                "result_id": f"result.{request_hash.removeprefix('sha256:')}",
                "result_version": M1006_CONTRACT_VERSION,
                "request_digest": request_hash,
                "result_digest": _ZERO_DIGEST,
                "request": request,
                "status": UncertaintyDecompositionStatus.DECOMPOSED,
                "decomposition": UncertaintyDecomposition(
                    decomposition_id=f"decomposition.{request_hash.removeprefix('sha256:')}",
                    components=components,
                    method=(
                        f"{request.policy.method}; quality-weighted Huber IRLS with "
                        "deterministic bootstrap"
                    ),
                    model_reference=request.policy.calibration_reference,
                    evidence=evidence,
                ),
                "sensitivity_envelope": sensitivity,
                "findings": (),
                "abstention_reason": None,
                "parent_target": M1006_PARENT,
                "support_decision": SupportDecision(
                    status=SupportStatus.SUPPORTED,
                    reason_code="m1006_measured_replicate_support",
                    rationale=(
                        "All seven uncertainty dimensions have aligned measured replicates "
                        "and the calibration envelope passes the 85-95 percent gate."
                    ),
                ),
                "uncertainty": uncertainty,
                "provenance": expected_provenance(request, request_hash),
                "evidence": evidence,
                "limitations": _limitations(measured=True),
                "human_review_required": False,
            }
            constructed = ProteinRnaDiscordanceUncertaintyDecompositionResult.model_construct(
                **measured_payload,  # type: ignore[arg-type]
            )
            measured_payload["result_digest"] = result_payload_digest(constructed)
            return _RESULT_ADAPTER.validate_python(measured_payload, strict=True)
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_uncertainty_decomposition",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1006_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": UncertaintyDecompositionStatus.ABSTAINED,
            "decomposition": None,
            "sensitivity_envelope": sensitivity,
            "findings": _findings(evidence),
            "abstention_reason": (
                "Uncertainty decomposition is abstained until calibration, sensitivity, "
                "and transport gates are owner-locked."
            ),
            "parent_target": M1006_PARENT,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1006_decomposition_review_required",
                rationale=(
                    "Seven uncertainty dimensions are explicit, but decomposition is not "
                    "supported before calibration and benchmark evidence are locked."
                ),
            ),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(),
            "human_review_required": True,
        }
        constructed = ProteinRnaDiscordanceUncertaintyDecompositionResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
        """Verify receipt digests and optionally replay its exact request."""

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if replay:
            expected = self.decompose(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1006UncertaintyDecompositionReplayError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def decompose_protein_rna_discordance_uncertainty(
    request: object,
) -> ProteinRnaDiscordanceUncertaintyDecompositionResult:
    """Public provisional M10-06 operation."""

    return M1006UncertaintyDecompositionEngine().decompose(request)


__all__ = [
    "M1006UncertaintyDecompositionAuthorizationError",
    "M1006UncertaintyDecompositionEngine",
    "M1006UncertaintyDecompositionReplayError",
    "decompose_protein_rna_discordance_uncertainty",
    "preflight_uncertainty_decomposition_authorization",
]
