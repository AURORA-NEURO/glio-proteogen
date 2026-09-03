"""Deterministic, replay-bound M11-05 trajectory runtime.

The public ABI remains provisional, but typed proteomic effects now have a
real computational path.  The engine fits robust weighted local states and
scores candidate evolutionary transitions with a loss-reduction test.  Opaque
artifact references still remain lineage handles and are never dereferenced.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import exp, isfinite, sqrt
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m11_05 import (
    M1105_CONTRACT_VERSION,
    M1105_EVIDENCE_CLAIM,
    M1105_PARENT,
    ChangePoint,
    ChangePointStatus,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    LongitudinalObservationState,
    ModelVariantPeptideLongitudinalEvolutionRequest,
    TrajectoryState,
    TrajectoryStatus,
    VariantPeptideLongitudinalEvolutionResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m11_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)
from glio_proteogen.kernel.models import (
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ModelVariantPeptideLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(VariantPeptideLongitudinalEvolutionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_HUBER_DELTA: Final = 1.5
_MINIMUM_STANDARD_ERROR: Final = 1e-6
_MINIMUM_WEIGHT_DENOMINATOR: Final = 1e-12
_MAD_SCALE_FACTOR: Final = 1.4826
_IRLS_TOLERANCE: Final = 1e-10
_IRLS_ITERATIONS: Final = 24
_IRLS_DAMPING: Final = 0.65
_MIN_MEASUREMENTS_PER_SIDE: Final = 2
_NUMERIC_TRANSITION_POSTERIOR: Final = 0.8
_MINIMUM_TREND_EFFECT: Final = 0.1
_DEFAULT_CENSORED_STANDARD_ERROR: Final = 0.5
_EFFECT_LIMIT: Final = 100.0
_CI_Z: Final = 1.96


class M1105AuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for trajectory evaluation."""

    def __init__(self) -> None:
        super().__init__(
            "M11-05 requires accepted configuration, resolved identity, accepted provenance, "
            "granted consent, accepted quality/support/intended-use controls"
        )


class M1105ReplayVerificationError(ValueError):
    """A trajectory result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M11-05 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1105_authorization(candidate: object) -> None:
    """Check seven controls before touching observation or upstream fields."""

    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {role: _state(_member(_member(references, role), "state")) for role in expected}
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M1105AuthorizationError from None
    if states != expected:
        raise M1105AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1105_authorization(candidate)
    return candidate


def _evidence(
    request: ModelVariantPeptideLongitudinalEvolutionRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.network_state_result,
        *request.source_artifacts,
        *(observation.feature_artifact for observation in request.observations),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="evidence",
            claim=M1105_EVIDENCE_CLAIM,
        )
        for artifact in artifacts[:64]
    )


def _state_label(territory: str, treatment_era: str) -> str:
    """Encode only explicit caller labels; this function never reads artifacts."""

    return f"territory={territory};treatment_era={treatment_era}"


@dataclass(frozen=True, slots=True)
class _Measurement:
    """A validated effect used by the closed-form trajectory fit."""

    index: int
    value: float
    standard_error: float
    quality_weight: float
    censored: bool


def _measurements(
    request: ModelVariantPeptideLongitudinalEvolutionRequest,
) -> tuple[_Measurement, ...]:
    values: list[_Measurement] = []
    for index, observation in enumerate(request.observations):
        if observation.measurement_state is LongitudinalObservationState.OBSERVED:
            if observation.effect is None or observation.standard_error is None:
                continue
            value = observation.effect
            error = observation.standard_error
            censored = False
        elif observation.measurement_state is LongitudinalObservationState.LEFT_CENSORED:
            if observation.censoring_limit is None:
                continue
            # A left-censored peptide contributes a one-sided upper-bound
            # constraint.  The optimizer never treats an unobserved value as a
            # negative effect; the fallback scale only controls its influence
            # when the current state violates the detection limit.
            error = observation.standard_error or _DEFAULT_CENSORED_STANDARD_ERROR
            value = observation.censoring_limit - 0.5 * error
            censored = True
        else:
            continue
        if (
            isfinite(value)
            and isfinite(error)
            and isfinite(observation.quality_weight)
            and error > 0.0
            and observation.quality_weight > 0.0
        ):
            values.append(_Measurement(index, value, error, observation.quality_weight, censored))
    return tuple(values)


def _weighted_huber_location(values: Sequence[_Measurement]) -> tuple[float, float]:
    """Fit a robust local level with precision and quality weighting.

    Iteratively reweighted Huber updates protect evolutionary calls from one
    contaminated peptide while retaining assay standard errors.  The returned
    scale is the standard error of the weighted location, not a fixed proxy.
    """

    if not values:
        return 0.0, float("inf")
    base = [
        item.quality_weight / max(item.standard_error**2, _MINIMUM_WEIGHT_DENOMINATOR)
        for item in values
    ]
    estimate = sum(
        weight * item.value for weight, item in zip(base, values, strict=True)
    ) / sum(base)
    for _ in range(_IRLS_ITERATIONS):
        residuals = [
            item.value - estimate
            if not item.censored
            else min(0.0, item.value - estimate)
            for item in values
        ]
        mad = sorted(abs(item) for item in residuals)[len(residuals) // 2]
        scale = max(
            _MAD_SCALE_FACTOR * mad,
            sum(item.standard_error for item in values) / len(values),
            _MINIMUM_STANDARD_ERROR,
        )
        robust_weights = []
        for weight, residual, item in zip(base, residuals, values, strict=True):
            standardized = abs(residual) / scale
            if item.censored and estimate <= item.value:
                robust_weights.append(0.0)
            else:
                robust_weights.append(
                    weight
                    * (_HUBER_DELTA / standardized if standardized > _HUBER_DELTA else 1.0)
                )
        total = sum(robust_weights)
        if total <= 0.0:
            break
        updated = sum(
            weight * item.value
            for weight, item in zip(robust_weights, values, strict=True)
        ) / total
        damped = _IRLS_DAMPING * updated + (1.0 - _IRLS_DAMPING) * estimate
        if abs(damped - estimate) <= _IRLS_TOLERANCE:
            estimate = damped
            break
        estimate = damped
    return estimate, sqrt(1.0 / max(sum(base), _MINIMUM_WEIGHT_DENOMINATOR))


def _weighted_loss(values: Sequence[_Measurement], estimate: float) -> float:
    loss = 0.0
    for item in values:
        residual = (
            max(0.0, estimate - item.value) if item.censored else abs(item.value - estimate)
        ) / max(item.standard_error, _MINIMUM_STANDARD_ERROR)
        huber = (
            0.5 * residual * residual
            if residual <= _HUBER_DELTA
            else _HUBER_DELTA * residual - 1.125
        )
        loss += item.quality_weight * huber
    return loss


def _change_score(
    measurements: Sequence[_Measurement],
    boundary: int,
) -> tuple[float, float, float]:
    """Return (posterior, standardized delta, relative loss improvement)."""

    left = tuple(item for item in measurements if item.index < boundary)
    right = tuple(item for item in measurements if item.index >= boundary)
    # Require replicate support on both sides before a *numeric* transition is
    # allowed to split a trajectory.  Explicit territory/treatment labels are
    # still honoured even when a recurrence has only one sample.
    if len(left) < _MIN_MEASUREMENTS_PER_SIDE or len(right) < _MIN_MEASUREMENTS_PER_SIDE:
        return 0.0, 0.0, 0.0
    whole = tuple(measurements)
    whole_location, _ = _weighted_huber_location(whole)
    left_location, left_error = _weighted_huber_location(left)
    right_location, right_error = _weighted_huber_location(right)
    delta = right_location - left_location
    standardized = abs(delta) / max(sqrt(left_error**2 + right_error**2), 1e-6)
    baseline = _weighted_loss(whole, whole_location)
    split = _weighted_loss(left, left_location) + _weighted_loss(right, right_location)
    improvement = max(0.0, (baseline - split) / max(baseline, 1e-6))
    # A calibrated probability is deliberately not claimed: this is a stable
    # evidence score mapped to [0, 1] for the provisional ABI.
    posterior = 1.0 / (1.0 + exp(-0.9 * (standardized - 1.75) - 3.0 * improvement))
    return min(0.999, max(0.001, posterior)), delta, improvement


def _segment_trend(values: Sequence[_Measurement]) -> str:
    if len(values) < _MIN_MEASUREMENTS_PER_SIDE:
        return "stable"
    center, _ = _weighted_huber_location(values)
    # A robust sign trend avoids fitting an unconstrained high-order curve to
    # sparse recurrence samples: compare the first/last residuals to the
    # fitted local level and require a meaningful effect separation.
    first = values[0].value - center
    last = values[-1].value - center
    threshold = max(sum(item.standard_error for item in values) / len(values), 0.1)
    if last - first > threshold + _MINIMUM_TREND_EFFECT:
        return "rising"
    if first - last > threshold + _MINIMUM_TREND_EFFECT:
        return "falling"
    return "stable"


def _limitations(*, supported: bool) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_feature_artifacts",
            statement=(
                "Feature and upstream artifacts are immutable references and are never traversed."
            ),
        ),
        Limitation(
            code="typed_effects_are_subject_level",
            statement=(
                "Typed effects are standardized within the supplied subject history; no cohort "
                "normalization or raw mzML/FASTA traversal is performed."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, all-omics fusion, treatment recommendation, identity "
                "inference, consent inference, or parent-output mutation is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No trajectory or change point is published after a failed quality gate.",
            )
        )
    return tuple(values)


class M1105LongitudinalEngine:
    """Evaluate a strictly ordered, caller-declared longitudinal history."""

    __slots__ = ()

    def infer(self, request: object) -> VariantPeptideLongitudinalEvolutionResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: ModelVariantPeptideLongitudinalEvolutionRequest,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        measurements = _measurements(request)
        typed_measurements = any(
            observation.measurement_state is not LongitudinalObservationState.UNSUPPORTED
            for observation in request.observations
        )
        if typed_measurements and len(measurements) < request.policy.minimum_observations:
            return self._abstained_result(
                request,
                request_hash,
                evidence,
                "Typed longitudinal history has insufficient observed or left-censored effects.",
            )

        explicit_boundaries = {
            index
            for index in range(1, len(request.observations))
            if _state_label(
                request.observations[index - 1].territory,
                request.observations[index - 1].treatment_era,
            )
            != _state_label(
                request.observations[index].territory,
                request.observations[index].treatment_era,
            )
        }
        numeric_scores: dict[int, tuple[float, float, float]] = {}
        if typed_measurements:
            numeric_scores = {
                boundary: _change_score(measurements, boundary)
                for boundary in range(1, len(request.observations))
            }
            # Keep the strongest measured transition in addition to explicit
            # territory/treatment boundaries.  This captures molecular drift
            # before a caller has relabeled a recurrence sample.
            best_boundary, best_score = max(
                numeric_scores.items(), key=lambda item: (item[1][0], -item[0])
            )
            if (
                best_score[0] >= _NUMERIC_TRANSITION_POSTERIOR
                and best_boundary not in explicit_boundaries
            ):
                explicit_boundaries.add(best_boundary)

        trajectory: list[TrajectoryState] = []
        segment_starts = (0, *sorted(explicit_boundaries))
        segment_ends = (*sorted(explicit_boundaries), len(request.observations))
        for start, end in zip(segment_starts, segment_ends, strict=True):
            first = request.observations[start]
            segment_observations = request.observations[start:end]
            segment_measurements = tuple(
                item for item in measurements if start <= item.index < end
            )
            label = _state_label(first.territory, first.treatment_era)
            posterior = 1.0
            estimate: float | None = None
            lower: float | None = None
            upper: float | None = None
            if typed_measurements:
                trend = _segment_trend(segment_measurements)
                label = f"{label};trend={trend}"
                if segment_measurements:
                    estimate, estimate_error = _weighted_huber_location(segment_measurements)
                    posterior = min(
                        0.999,
                        max(0.5, 1.0 - 1.0 / sqrt(len(segment_measurements) + 1.0)),
                    )
                    lower = max(-_EFFECT_LIMIT, estimate - _CI_Z * estimate_error)
                    upper = min(_EFFECT_LIMIT, estimate + _CI_Z * estimate_error)
            state_evidence = tuple(
                item
                for observation in segment_observations
                for item in (
                    KernelEvidenceReference(
                        reference=observation.feature_artifact,
                        role="evidence",
                        claim=M1105_EVIDENCE_CLAIM,
                    ),
                    *observation.evidence,
                )
            )
            trajectory.append(
                TrajectoryState(
                    state_id=f"state.{first.sequence}",
                    sequence=first.sequence,
                    label=label,
                    posterior_probability=posterior,
                    observation_ids=tuple(item.observation_id for item in segment_observations),
                    evidence=state_evidence,
                    effect_estimate=estimate,
                    effect_lower=lower,
                    effect_upper=upper,
                    measurement_count=len(segment_measurements),
                )
            )

        change_points: list[ChangePoint] = []
        for before, after in pairwise(trajectory):
            boundary = after.sequence
            score = numeric_scores.get(boundary)
            posterior = score[0] if score is not None and score[0] > 0.0 else 0.9
            if score is None or score[0] <= 0.0:
                rationale = (
                    "Explicit territory or treatment-era label changed between ordered "
                    "observations."
                )
            else:
                rationale = (
                    "Robust quality-weighted effect shift exceeded the provisional change "
                    f"evidence threshold (standardized delta={abs(score[1]):.3f}, "
                    f"relative loss reduction={score[2]:.3f})."
                )
            change_points.append(
                ChangePoint(
                    change_point_id=f"change.{after.sequence}",
                    sequence=boundary,
                    status=ChangePointStatus.DETECTED,
                    before_state_id=before.state_id,
                    after_state_id=after.state_id,
                    posterior_probability=posterior,
                    rationale=rationale,
                    evidence=after.evidence,
                )
            )
        diagnostics = (
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.temporal-order",
                code=LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                message="Observation sequence and aware timestamps are strictly ordered.",
                evidence=evidence[:1],
            ),
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.future-leakage",
                code=LongitudinalDiagnosticCode.FUTURE_LEAKAGE_BLOCKED,
                message=(
                    "Only caller-declared ordered observations are used; typed effects are "
                    "fit without dereferencing feature artifacts."
                    if typed_measurements
                    else "Only caller-declared ordered observations are used by the baseline."
                ),
                evidence=evidence[:1],
            ),
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.provisional-abi",
                code=LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
                message="Public module ABI remains provisional pending owner confirmation.",
                evidence=(),
            ),
        )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_longitudinal_evolution",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1105_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": TrajectoryStatus.MODELED,
            "trajectory": tuple(trajectory),
            "change_points": tuple(change_points),
            "diagnostics": diagnostics,
            "abstention_reason": None,
            "parent_target": M1105_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m1105_trajectory_supported",
                rationale="All temporal, future-leakage, and caller-control gates passed.",
            ),
            "uncertainty": expected_uncertainty(supported=True, measured=typed_measurements),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=True),
            "human_review_required": True,
        }
        constructed = VariantPeptideLongitudinalEvolutionResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def _abstained_result(
        self,
        request: ModelVariantPeptideLongitudinalEvolutionRequest,
        request_hash: str,
        evidence: tuple[KernelEvidenceReference, ...],
        reason: str,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        """Build a digest-bound safe result when typed evidence cannot support a fit."""

        diagnostics = (
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.temporal-order",
                code=LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                message="Observation sequence and aware timestamps are strictly ordered.",
                evidence=evidence[:1],
            ),
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.insufficient-history",
                code=LongitudinalDiagnosticCode.INSUFFICIENT_HISTORY,
                message=reason,
                evidence=evidence[:1],
            ),
        )
        payload: dict[str, object] = {
            "output_type": "variant_peptide_longitudinal_evolution",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1105_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": TrajectoryStatus.ABSTAINED,
            "trajectory": (),
            "change_points": (),
            "diagnostics": diagnostics,
            "abstention_reason": reason,
            "parent_target": M1105_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="m1105_insufficient_typed_history",
                rationale=reason,
            ),
            "uncertainty": expected_uncertainty(supported=False, measured=True),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=False),
            "human_review_required": True,
        }
        constructed = VariantPeptideLongitudinalEvolutionResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> VariantPeptideLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1105ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1105ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1105ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1105ReplayVerificationError
        return validated


def infer_variant_peptide_longitudinal_evolution(
    request: object,
) -> VariantPeptideLongitudinalEvolutionResult:
    """Public provisional M11-05 operation."""

    return M1105LongitudinalEngine().infer(request)


__all__ = [
    "M1105AuthorizationError",
    "M1105LongitudinalEngine",
    "M1105ReplayVerificationError",
    "infer_variant_peptide_longitudinal_evolution",
    "preflight_m1105_authorization",
]
