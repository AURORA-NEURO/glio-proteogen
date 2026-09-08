"""Deterministic, replay-bound M12-05 longitudinal trajectory runtime.

Typed requests use a glioma-specific robust temporal program fit with explicit
censoring, bootstrap intervals, and objective-trace replay evidence. The
provisional opaque objective grammar remains available only as a compatibility
path. References stay opaque: this module never reads an artifact, infers
consent or identity, joins unrelated omics, or turns unsupported data into a
negative biological finding.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from pydantic import TypeAdapter

from glio_proteogen.contracts.m12_05 import (
    M1205_CONTRACT_VERSION,
    M1205_PARENT,
    BiomarkerPanelLongitudinalEvolutionResult,
    ChangePoint,
    ChangePointStatus,
    GliomaTrajectoryProgram,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    LongitudinalEvidenceState,
    ModelBiomarkerPanelLongitudinalEvolutionRequest,
    TimePointObservation,
    TrajectoryState,
    TrajectoryStatus,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m12_05.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)
from glio_proteogen.kernel.models import (
    EvidenceReference as KernelEvidenceReference,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ModelBiomarkerPanelLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(BiomarkerPanelLongitudinalEvolutionResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_OBJECTIVES: Final = frozenset(
    {
        "stable",
        "alternating",
        "territory",
        "treatment_era",
        "time_course",
        "primary_recurrence",
        "clone",
        "state_transition",
    }
)
_TWO_PART_OBJECTIVE: Final = 2
_CHANGE_POINT_PARTS: Final = 4
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.02
_TEMPORAL_SMOOTHING: Final = 0.35
_TEMPORAL_CURVATURE: Final = 0.12
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_STATE_THRESHOLD: Final = 0.25
_CHANGE_POINT_PROBABILITY: Final = 0.5
_MIN_TYPED_POINTS: Final = 2
_MAX_EFFECT: Final = 20.0
_PROGRAM_ORDER: Final = tuple(GliomaTrajectoryProgram)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    sequence: int
    program: GliomaTrajectoryProgram
    state: LongitudinalEvidenceState
    value: float
    standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _TemporalFit:
    values: tuple[float, ...]
    converged: bool
    iterations: int
    objective: float
    max_update: float
    objective_trace: tuple[float, ...]


def _quantize(value: float) -> float:
    """Round numeric outputs so replay receipts are stable across platforms."""

    return float(f"{value:.8f}")


class M1205AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize longitudinal inference."""

    def __init__(self) -> None:
        super().__init__(
            "M12-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1205ReplayVerificationError(ValueError):
    """A trajectory result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M12-05 replay verification failed")


class M1205InferenceError(ValueError):
    """A caller-declared trajectory objective cannot be evaluated safely."""


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_longitudinal_authorization(candidate: object) -> None:
    """Check every control before traversing typed or opaque request data."""

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
    except Exception as error:
        raise M1205AuthorizationError from error
    if states != expected:
        raise M1205AuthorizationError


def _evidence(
    request: ModelBiomarkerPanelLongitudinalEvolutionRequest,
) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.network_state_result,
        *request.source_artifacts,
        *(item.feature_artifact for item in request.observations),
        request.policy.configuration.model_reference,
        *(item.reference for item in request.policy.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="evidence",
            claim=(
                "Caller-declared longitudinal observation, model, control, and upstream "
                "evidence; artifact content is not authenticated by this module."
            ),
        )
        for artifact in tuple(unique.values())[:64]
    )


def _limitations(*, supported: bool, typed: bool = False) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_artifacts",
            statement="Artifact references are immutable and their content is never traversed.",
        ),
        Limitation(
            code="future_leakage_blocked",
            statement=(
                "Only caller-declared ordered observations are projected; future values are "
                "not read."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The result emits only a time-indexed trajectory and change-point object; "
                "it does not infer kinase activity, treatment, identity, or consent."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement=(
                "The estimator grammar and endpoint metadata remain provisional pending "
                "owner confirmation."
            ),
        ),
    ]
    if typed:
        values.extend(
            (
                Limitation(
                    code="typed_glioma_temporal_fit",
                    statement=(
                        "Typed observations are fitted as signed RTK/PI3K/AKT/mTOR, "
                        "p53/cell-cycle, IDH/HIF1A, mesenchymal, and proliferation program "
                        "trajectories with robust temporal smoothing."
                    ),
                ),
                Limitation(
                    code="research_use_only",
                    statement=(
                        "Program states and intervals are research-use-only signals; they are "
                        "not a diagnosis, prognosis, or treatment recommendation."
                    ),
                ),
            )
        )
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement=(
                    "Unsupported objectives and unresolved histories are quarantined for human "
                    "review."
                ),
            )
        )
    return tuple(values)


def _objective_kind(objective: str) -> tuple[str, int | None, str | None, str | None]:
    """Parse the closed deterministic objective grammar."""

    parts = objective.split(":")
    if len(parts) == 1 and parts[0] in _SUPPORTED_OBJECTIVES:
        return parts[0], None, None, None
    if (
        len(parts) == _TWO_PART_OBJECTIVE
        and parts[0] in {"trajectory", "mode"}
        and parts[1] in (_SUPPORTED_OBJECTIVES - {"time_course"})
    ):
        return parts[1], None, None, None
    if len(parts) == _CHANGE_POINT_PARTS and parts[0] in {"change_point", "changepoint"}:
        try:
            sequence = int(parts[1])
        except ValueError:
            return "", None, None, None
        if sequence < 1 or not parts[2] or not parts[3]:
            return "", None, None, None
        return "change_point", sequence, parts[2], parts[3]
    return "", None, None, None


def _label_for(  # noqa: PLR0911 - each supported dimension has an explicit label policy.
    kind: str,
    observation: TimePointObservation,
    index: int,
    *,
    change_spec: tuple[int, str, str] | None = None,
) -> str:
    if kind == "stable":
        return "stable"
    if kind in {"alternating", "clone"}:
        return "state_a" if index % 2 == 0 else "state_b"
    if kind == "territory":
        return observation.territory
    if kind == "treatment_era":
        return observation.treatment_era
    if kind == "primary_recurrence":
        return "primary" if index == 0 else "recurrence"
    if kind == "state_transition":
        return f"state_{observation.sequence}"
    if kind == "change_point":
        if change_spec is None:
            raise M1205InferenceError
        before_sequence, before_label, after_label = change_spec
        return before_label if observation.sequence < before_sequence else after_label
    return "time_course"


def _huber_weight(residual: float) -> float:
    absolute = abs(residual)
    if absolute <= _HUBER_DELTA:
        return 1.0
    return _HUBER_DELTA / absolute


def _huber_loss(residual: float) -> float:
    absolute = abs(residual)
    if absolute <= _HUBER_DELTA:
        return 0.5 * residual * residual
    return _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)


def _typed_terms(
    observations: tuple[TimePointObservation, ...],
) -> tuple[_TypedTerm, ...]:
    terms: list[_TypedTerm] = []
    for observation in observations:
        state = observation.evidence_state
        if (
            state not in {
                LongitudinalEvidenceState.OBSERVED,
                LongitudinalEvidenceState.LEFT_CENSORED,
            }
            or observation.program is None
            or observation.standardized_effect is None
            or observation.standard_error is None
        ):
            continue
        terms.append(
            _TypedTerm(
                sequence=observation.sequence,
                program=observation.program,
                state=state,
                value=observation.standardized_effect,
                standard_error=observation.standard_error,
                quality_weight=observation.quality_weight,
            )
        )
    return tuple(sorted(terms, key=lambda item: (item.sequence, item.program.value)))


def _has_typed_fields(observations: tuple[TimePointObservation, ...]) -> bool:
    return any(
        item.evidence_state is not None
        or item.program is not None
        or item.standardized_effect is not None
        or item.standard_error is not None
        for item in observations
    )


def _median(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def _temporal_objective(
    values: list[float],
    terms: tuple[_TypedTerm, ...],
    index_by_sequence: dict[int, int],
) -> float:
    objective = _RIDGE * sum(value * value for value in values)
    for item in terms:
        index = index_by_sequence[item.sequence]
        if item.state is LongitudinalEvidenceState.LEFT_CENSORED:
            residual = max(0.0, values[index] - item.value) / max(
                _MIN_SCALE, item.standard_error
            )
        else:
            residual = (values[index] - item.value) / max(_MIN_SCALE, item.standard_error)
        objective += item.quality_weight * _huber_loss(residual)
    for index in range(1, len(values)):
        objective += _TEMPORAL_SMOOTHING * _huber_loss(values[index] - values[index - 1])
    for index in range(len(values) - 2):
        curvature = values[index + 2] - 2.0 * values[index + 1] + values[index]
        objective += _TEMPORAL_CURVATURE * _huber_loss(curvature)
    return objective


def _fit_temporal(  # noqa: C901, PLR0912, PLR0915 - explicit solver is intentionally branch-rich.
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> _TemporalFit:
    """Fit a robust local-level trajectory with smoothness and curvature penalties."""

    index_by_sequence = {sequence: index for index, sequence in enumerate(sequences)}
    grouped: dict[int, list[_TypedTerm]] = defaultdict(list)
    for item in terms:
        grouped[index_by_sequence[item.sequence]].append(item)
    values = np.zeros(len(sequences), dtype=np.float64)
    known: set[int] = set()
    for index, group in grouped.items():
        values[index] = _median(tuple(item.value for item in group))
        known.add(index)
    for index in range(len(values)):
        if index in known:
            continue
        before = max((candidate for candidate in known if candidate < index), default=None)
        after = min((candidate for candidate in known if candidate > index), default=None)
        if before is not None and after is not None:
            fraction = (index - before) / (after - before)
            values[index] = values[before] + fraction * (values[after] - values[before])
        elif before is not None:
            values[index] = values[before]
        elif after is not None:
            values[index] = values[after]
    previous_objective = _temporal_objective(values.tolist(), terms, index_by_sequence)
    objective_trace = [_quantize(previous_objective)]
    converged = False
    max_update = math.inf
    iterations = 0
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        iterations = iteration
        old = values.copy()
        for index in range(len(values)):
            current = values[index]
            gradient = 2.0 * _RIDGE * current
            hessian = 2.0 * _RIDGE
            for item in grouped.get(index, ()):
                if (
                    item.state is LongitudinalEvidenceState.LEFT_CENSORED
                    and current <= item.value
                ):
                    continue
                residual = (
                    max(0.0, current - item.value)
                    if item.state is LongitudinalEvidenceState.LEFT_CENSORED
                    else current - item.value
                ) / max(_MIN_SCALE, item.standard_error)
                information = (
                    item.quality_weight
                    * _huber_weight(residual)
                    / max(_MIN_SCALE, item.standard_error**2)
                )
                gradient += information * (current - item.value)
                hessian += information
            if index > 0:
                gradient += 2.0 * _TEMPORAL_SMOOTHING * (current - values[index - 1])
                hessian += 2.0 * _TEMPORAL_SMOOTHING
            if index + 1 < len(values):
                gradient += 2.0 * _TEMPORAL_SMOOTHING * (current - values[index + 1])
                hessian += 2.0 * _TEMPORAL_SMOOTHING
            for start in range(max(0, index - 2), min(index + 1, len(values) - 2)):
                coefficients = (1.0, -2.0, 1.0)
                offset = index - start
                curvature = (
                    values[start + 2] - 2.0 * values[start + 1] + values[start]
                )
                coefficient = coefficients[offset]
                gradient += _TEMPORAL_CURVATURE * coefficient * curvature
                hessian += _TEMPORAL_CURVATURE * coefficient * coefficient
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            values[index] = max(
                -_MAX_EFFECT,
                min(_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        max_update = float(np.max(np.abs(values - old)))
        objective = _temporal_objective(values.tolist(), terms, index_by_sequence)
        objective_trace.append(_quantize(objective))
        if (
            max_update <= _SOLVER_TOLERANCE
            and abs(previous_objective - objective) <= _SOLVER_TOLERANCE
        ):
            converged = True
            previous_objective = objective
            break
        previous_objective = objective
    return _TemporalFit(
        values=tuple(_quantize(float(value)) for value in values),
        converged=converged,
        iterations=iterations,
        objective=_quantize(previous_objective),
        max_update=_quantize(max_update if math.isfinite(max_update) else 0.0),
        objective_trace=tuple(objective_trace),
    )


def _fit_programs(
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> dict[GliomaTrajectoryProgram, _TemporalFit]:
    grouped: dict[GliomaTrajectoryProgram, list[_TypedTerm]] = defaultdict(list)
    for item in terms:
        grouped[item.program].append(item)
    return {
        program: _fit_temporal(tuple(grouped[program]), sequences)
        for program in _PROGRAM_ORDER
        if program in grouped
    }


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _objective_trace_digest(
    fits: dict[GliomaTrajectoryProgram, _TemporalFit],
) -> str:
    material = "|".join(
        f"{program.value}:{','.join(str(value) for value in fit.objective_trace)}"
        for program, fit in sorted(fits.items(), key=lambda pair: pair[0].value)
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _aggregate_programs(
    fits: dict[GliomaTrajectoryProgram, _TemporalFit],
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> tuple[float, ...]:
    weights = {
        program: sum(item.quality_weight for item in terms if item.program is program)
        for program in fits
    }
    values: list[float] = []
    for index in range(len(sequences)):
        denominator = sum(weights.values())
        values.append(
            _quantize(
                sum(weights[program] * fit.values[index] for program, fit in fits.items())
                / max(_MIN_SCALE, denominator)
            )
        )
    return tuple(values)


def _bootstrap_typed(
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
    replicates: int,
    request_digest: str,
) -> tuple[tuple[float, ...], ...]:
    # NumPy's PCG64 generator is seeded only from the canonical request digest;
    # this keeps perturbations replayable while making the interval construction
    # explicit and independent of input iteration order.
    seed = int(request_digest.removeprefix("sha256:")[:16], 16)
    rng = np.random.default_rng(seed)
    draws: list[tuple[float, ...]] = []
    for _draw in range(replicates):
        perturbations = rng.normal(0.0, 1.0, size=len(terms))
        perturbed = tuple(
            _TypedTerm(
                sequence=item.sequence,
                program=item.program,
                state=item.state,
                value=max(
                    -_MAX_EFFECT,
                    min(
                        _MAX_EFFECT,
                        item.value
                        + 0.5 * item.standard_error * float(perturbations[index]),
                    ),
                ),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
            for index, item in enumerate(terms)
        )
        fits = _fit_programs(perturbed, sequences)
        draws.append(_aggregate_programs(fits, perturbed, sequences))
    return tuple(draws)


def _classify_interval(lower: float, upper: float) -> str:
    if lower > _STATE_THRESHOLD:
        return "activated"
    if upper < -_STATE_THRESHOLD:
        return "suppressed"
    if lower >= -_STATE_THRESHOLD and upper <= _STATE_THRESHOLD:
        return "neutral"
    return "indeterminate"


def _clamp_probability(value: float) -> float:
    return _quantize(max(0.0, min(1.0, value)))


def _typed_outputs(  # noqa: PLR0913 - explicit result construction keeps the ABI visible.
    request: ModelBiomarkerPanelLongitudinalEvolutionRequest,
    terms: tuple[_TypedTerm, ...],
    kind: str,
    change_sequence: int | None,
    before_label: str | None,
    after_label: str | None,
    request_digest: str,
    evidence: tuple[KernelEvidenceReference, ...],
) -> tuple[
    tuple[TrajectoryState, ...],
    tuple[ChangePoint, ...],
    bool,
    str | None,
    LongitudinalDiagnostic | None,
]:
    sequences = tuple(item.sequence for item in request.observations)
    fits = _fit_programs(terms, sequences)
    if not fits or any(not fit.converged for fit in fits.values()):
        return (), (), False, "typed glioma temporal solver did not converge", None
    aggregate = _aggregate_programs(fits, terms, sequences)
    bootstrap = _bootstrap_typed(
        terms,
        sequences,
        request.policy.configuration.bootstrap_replicates,
        request_digest,
    )
    by_sequence: dict[int, tuple[_TypedTerm, ...]] = defaultdict(tuple)
    for item in terms:
        by_sequence[item.sequence] = (*by_sequence[item.sequence], item)
    trajectories: list[TrajectoryState] = []
    change_spec = (
        (change_sequence, before_label, after_label)
        if kind == "change_point"
        and change_sequence is not None
        and before_label is not None
        and after_label is not None
        else None
    )
    for index, observation in enumerate(request.observations):
        samples = tuple(draw[index] for draw in bootstrap)
        lower = _quantile(samples, _BOOTSTRAP_LOW)
        upper = _quantile(samples, _BOOTSTRAP_HIGH)
        lower = min(lower, aggregate[index])
        upper = max(upper, aggregate[index])
        label = _classify_interval(lower, upper)
        if kind not in {"stable", "time_course", "state_transition"}:
            label = _label_for(kind, observation, index, change_spec=change_spec)
        probabilities = sum(
            _classify_interval(value, value) == _classify_interval(lower, upper)
            for value in samples
        ) / max(1, len(samples))
        program_scores = tuple(fit.values[index] for fit in fits.values())
        mean = _median(program_scores)
        deviation = math.sqrt(
            sum((value - mean) ** 2 for value in program_scores) / max(1, len(program_scores))
        )
        discordance = _clamp_probability(deviation / max(1.0, abs(mean) + 1.0))
        stability = _clamp_probability(1.0 - (upper - lower) / (2.0 * _MAX_EFFECT))
        drivers = tuple(
            program.value
            for program, _ in sorted(
                fits.items(), key=lambda pair: (-abs(pair[1].values[index]), pair[0].value)
            )[:3]
        )
        trajectories.append(
            TrajectoryState(
                state_id=f"state.{observation.observation_id}",
                sequence=observation.sequence,
                label=label,
                posterior_probability=_clamp_probability(probabilities),
                observation_ids=(observation.observation_id,),
                evidence=evidence[:1],
                standardized_state=aggregate[index],
                lower_bound=lower,
                upper_bound=upper,
                evidence_count=len(by_sequence.get(observation.sequence, ())),
                stability=stability,
                discordance=discordance,
                top_drivers=drivers,
            )
        )
    changes: tuple[ChangePoint, ...] = ()
    if kind == "change_point":
        if change_sequence is None or before_label is None or after_label is None:
            return (), (), False, "typed change-point specification is incomplete", None
        before_index = max(
            index for index, sequence in enumerate(sequences) if sequence < change_sequence
        )
        after_index = min(
            index for index, sequence in enumerate(sequences) if sequence >= change_sequence
        )
        delta = max(
            -_MAX_EFFECT,
            min(_MAX_EFFECT, aggregate[after_index] - aggregate[before_index]),
        )
        delta_samples = tuple(draw[after_index] - draw[before_index] for draw in bootstrap)
        lower_delta = max(
            -_MAX_EFFECT,
            min(_MAX_EFFECT, _quantile(delta_samples, _BOOTSTRAP_LOW)),
        )
        upper_delta = max(
            -_MAX_EFFECT,
            min(_MAX_EFFECT, _quantile(delta_samples, _BOOTSTRAP_HIGH)),
        )
        probability = sum(abs(value) > _STATE_THRESHOLD for value in delta_samples) / max(
            1, len(delta_samples)
        )
        if probability >= _CHANGE_POINT_PROBABILITY:
            changes = (
                ChangePoint(
                    change_point_id=f"change-point.{change_sequence}",
                    sequence=change_sequence,
                    status=ChangePointStatus.DETECTED,
                    before_state_id=trajectories[before_index].state_id,
                    after_state_id=trajectories[after_index].state_id,
                    posterior_probability=_clamp_probability(probability),
                    rationale="Bootstrap perturbations support a signed glioma temporal shift.",
                    evidence=evidence[:1],
                    effect_delta=delta,
                    lower_bound=lower_delta,
                    upper_bound=upper_delta,
                ),
            )
        else:
            changes = (
                ChangePoint(
                    change_point_id=f"change-point.{change_sequence}",
                    sequence=change_sequence,
                    status=ChangePointStatus.NOT_DETECTED,
                    rationale=(
                        "Bootstrap perturbations do not support a thresholded temporal shift."
                    ),
                    evidence=evidence[:1],
                    effect_delta=delta,
                    lower_bound=lower_delta,
                    upper_bound=upper_delta,
                ),
            )
    diagnostic = LongitudinalDiagnostic(
        diagnostic_id="diagnostic.typed-glioma-temporal-fit",
        code=LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
        message=(
            "Typed glioma program trajectories were fitted with robust temporal coordinate "
            "descent and deterministic bootstrap intervals; the trace digest binds every "
            "objective value for replay."
        ),
        evidence=evidence[:1],
        solver_iterations=max(fit.iterations for fit in fits.values()),
        solver_objective=_quantize(sum(fit.objective for fit in fits.values())),
        solver_max_update=_quantize(max(fit.max_update for fit in fits.values())),
        objective_trace_digest=_objective_trace_digest(fits),
    )
    return tuple(trajectories), changes, True, None, diagnostic


class M1205LongitudinalEngine:
    """Infer a caller-declared longitudinal trajectory with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> BiomarkerPanelLongitudinalEvolutionResult:
        preflight_longitudinal_authorization(request)
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return self._result(validated)

    def _result(  # noqa: C901, PLR0912, PLR0915 - explicit ABI assembly is intentionally visible.
        self, request: ModelBiomarkerPanelLongitudinalEvolutionRequest
    ) -> BiomarkerPanelLongitudinalEvolutionResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        kind, change_sequence, before_label, after_label = _objective_kind(
            request.policy.configuration.objective
        )
        supported = kind in _SUPPORTED_OBJECTIVES or kind == "change_point"
        reason = ""
        typed_terms = _typed_terms(request.observations)
        typed_requested = _has_typed_fields(request.observations)
        typed_outputs: tuple[
            tuple[TrajectoryState, ...],
            tuple[ChangePoint, ...],
            bool,
            str | None,
            LongitudinalDiagnostic | None,
        ] | None = None
        if supported and kind == "change_point":
            if change_sequence is None:
                raise M1205InferenceError
            sequences = tuple(item.sequence for item in request.observations)
            supported = min(sequences) < change_sequence <= max(sequences)
            if not supported:
                reason = "Change-point objective is outside the observed temporal support domain."
        if not supported:
            reason = reason or (
                "Objective is outside the closed provisional longitudinal grammar; no trajectory "
                "or negative biological finding is emitted."
            )
        if supported and typed_requested:
            if len({item.sequence for item in typed_terms}) < _MIN_TYPED_POINTS:
                supported = False
                reason = (
                    "Typed glioma temporal evidence requires at least two supported time points."
                )
            else:
                typed_outputs = _typed_outputs(
                    request,
                    typed_terms,
                    kind,
                    change_sequence,
                    before_label,
                    after_label,
                    request_hash,
                    evidence,
                )
                if not typed_outputs[2]:
                    supported = False
                    reason = typed_outputs[3] or "Typed glioma temporal model abstained."
        trajectory: tuple[TrajectoryState, ...] = ()
        changes: tuple[ChangePoint, ...] = ()
        diagnostics: list[LongitudinalDiagnostic] = [
            LongitudinalDiagnostic(
                diagnostic_id="diagnostic.temporal-ordering",
                code=LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                message="Observation sequences and timestamps are strictly ordered.",
                evidence=evidence[:1],
            )
        ]
        if supported and typed_outputs is not None:
            trajectory, changes = typed_outputs[:2]
            if typed_outputs[4] is not None:
                diagnostics.append(typed_outputs[4])
        elif supported:
            change_spec: tuple[int, str, str] | None = None
            if kind == "change_point":
                if change_sequence is None or before_label is None or after_label is None:
                    raise M1205InferenceError
                change_spec = (change_sequence, before_label, after_label)
            states: list[TrajectoryState] = []
            for index, observation in enumerate(request.observations):
                label = _label_for(kind, observation, index, change_spec=change_spec)
                states.append(
                    TrajectoryState(
                        state_id=f"state.{observation.observation_id}",
                        sequence=observation.sequence,
                        label=label,
                        posterior_probability=0.9,
                        observation_ids=(observation.observation_id,),
                        evidence=evidence[:1],
                    )
                )
            trajectory = tuple(states)
            if kind == "change_point":
                if change_sequence is None:
                    raise M1205InferenceError
                before = next(
                    (state for state in trajectory if state.sequence < change_sequence), None
                )
                after = next(
                    (state for state in trajectory if state.sequence >= change_sequence), None
                )
                if before is None or after is None:
                    raise M1205InferenceError
                changes = (
                    ChangePoint(
                        change_point_id=f"change-point.{change_sequence}",
                        sequence=change_sequence,
                        status=ChangePointStatus.DETECTED,
                        before_state_id=before.state_id,
                        after_state_id=after.state_id,
                        posterior_probability=0.9,
                        rationale=(
                            "The locked change-point objective separates ordered pre/post states."
                        ),
                        evidence=evidence[:1],
                    ),
                )
            diagnostics.append(
                LongitudinalDiagnostic(
                    diagnostic_id="diagnostic.provisional-abi",
                    code=LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    message=(
                        "Trajectory labels and probabilities use the provisional deterministic "
                        "grammar."
                    ),
                    evidence=evidence[:1],
                )
            )
        else:
            diagnostics.append(
                LongitudinalDiagnostic(
                    diagnostic_id="diagnostic.not-evaluable",
                    code=LongitudinalDiagnosticCode.INSUFFICIENT_HISTORY,
                    message=reason,
                    evidence=evidence[:1],
                )
            )
        payload: dict[str, Any] = {
            "output_type": "biomarker_panel_longitudinal_evolution",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1205_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": TrajectoryStatus.MODELED if supported else TrajectoryStatus.NOT_EVALUABLE,
            "trajectory": trajectory,
            "change_points": changes,
            "diagnostics": tuple(diagnostics),
            "abstention_reason": None if supported else reason,
            "parent_target": M1205_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code=(
                    "m1205_trajectory_modeled" if supported else "m1205_trajectory_abstained"
                ),
                rationale=(
                    (
                        "Typed glioma program evidence, ordered observations, locked "
                        "configuration, and solver convergence checks passed."
                        if typed_requested
                        else "Ordered observations, locked configuration, and closed objective "
                        "grammar passed."
                    )
                    if supported
                    else (
                        "The trajectory is outside the safely evaluable support domain and "
                        "requires review."
                    )
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported, typed=typed_requested),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported, typed=typed_requested),
            "human_review_required": not supported,
        }
        constructed = BiomarkerPanelLongitudinalEvolutionResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> BiomarkerPanelLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1205ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1205ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1205ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1205ReplayVerificationError
        return validated


def infer_biomarker_panel_longitudinal_evolution(
    request: object,
) -> BiomarkerPanelLongitudinalEvolutionResult:
    """Public provisional M12-05 operation."""

    return M1205LongitudinalEngine().infer(request)


__all__ = [
    "M1205AuthorizationError",
    "M1205InferenceError",
    "M1205LongitudinalEngine",
    "M1205ReplayVerificationError",
    "infer_biomarker_panel_longitudinal_evolution",
    "preflight_longitudinal_authorization",
]
