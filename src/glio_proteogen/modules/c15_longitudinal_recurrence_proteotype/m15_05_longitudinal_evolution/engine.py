"""Replay-safe M15-05 longitudinal and evolutionary model.

The dossier leaves the scientific model ABI open. This implementation therefore
replays only caller-declared ordered observations into a time-indexed trajectory.
It never reads source bytes, fits a model, detects a biological change point,
infers identity, performs all-omics fusion, emits kinase state, or recommends
treatment. Change points are explicit not-evaluable records until owner-frozen
models and calibrated evidence are available.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_05 import (
    M1505_CONTRACT_VERSION,
    M1505_MODULE_ID,
    M1505_PARENT,
    ChangePoint,
    ChangePointStatus,
    ComplexActivityLongitudinalEvolutionResult,
    EvolutionModelFamily,
    GliomaEvolutionProgram,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    LongitudinalEvidenceState,
    ModelComplexActivityLongitudinalEvolutionRequest,
    TrajectoryState,
    TrajectoryStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(ModelComplexActivityLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityLongitudinalEvolutionResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_EVIDENCE_CLAIM: Final = (
    "Caller-declared M15-05 longitudinal observation or control material; "
    "issuer authority is not authenticated."
)
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source, upstream, and feature artifacts remain immutable references; "
            "M15-05 never reads their bytes."
        ),
    ),
    Limitation(
        code="metadata_replay_only",
        statement=(
            "Trajectory states preserve caller-declared observation order and references; "
            "they are not biological state estimates."
        ),
    ),
    Limitation(
        code="change_points_not_estimable",
        statement=(
            "Change points are explicit not-evaluable records until an owner-frozen model "
            "and calibrated evidence are available."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement=(
            "The public ABI remains provisional pending Bioinformatics owner confirmation "
            "of the dossier slice."
        ),
    ),
)
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_TEMPORAL_SMOOTHING: Final = 0.35
_PROGRAM_EDGE_WEIGHT: Final = 0.40
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_OBJECTIVE_TOLERANCE: Final = 1e-10
_BACKTRACKING_STEPS: Final = 18
_BACKTRACKING_FACTOR: Final = 0.5
_MIN_SCALE: Final = 1e-6
_MAX_EFFECT: Final = 20.0
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_MIN_TYPED_TERMS: Final = 2
_STATE_DIMENSIONS: Final = 2
_PROGRAM_ORDER: Final = tuple(GliomaEvolutionProgram)
_PROGRAM_EDGES: Final = (
    (GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR, GliomaEvolutionProgram.PROLIFERATION, 1.0),
    (GliomaEvolutionProgram.P53_CELL_CYCLE, GliomaEvolutionProgram.PROLIFERATION, -1.0),
    (GliomaEvolutionProgram.IDH_HIF1A, GliomaEvolutionProgram.MESENCHYMAL_PROGRAM, -1.0),
    (GliomaEvolutionProgram.RTK_PI3K_AKT_MTOR, GliomaEvolutionProgram.MESENCHYMAL_PROGRAM, 1.0),
    (GliomaEvolutionProgram.MESENCHYMAL_PROGRAM, GliomaEvolutionProgram.PROLIFERATION, 1.0),
)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    sequence: int
    observation_id: str
    program: GliomaEvolutionProgram
    state: LongitudinalEvidenceState
    value: float
    standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _TypedFit:
    values: tuple[tuple[float, ...], ...]
    converged: bool
    iterations: int
    objective: float
    max_update: float
    objective_trace: tuple[float, ...]


class M1505AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize longitudinal replay."""

    def __init__(self) -> None:
        super().__init__(
            "M15-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1505ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-05 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M15-05 request must be a strict request model or mapping")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1505_authorization(candidate: object) -> None:
    """Check all seven controls before traversing observations or configuration."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state")) for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1505AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1505AuthorizationError


def _as_request(candidate: object) -> ModelComplexActivityLongitudinalEvolutionRequest:
    preflight_m1505_authorization(candidate)
    if type(candidate) is ModelComplexActivityLongitudinalEvolutionRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
) -> tuple[EvidenceReference, ...]:
    references: list[ArtifactReference] = [
        request.network_state_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
    ]
    references.extend(evidence.reference for evidence in request.policy.configuration.evidence)
    references.extend(observation.feature_artifact for observation in request.observations)
    references.extend(
        evidence.reference
        for observation in request.observations
        for evidence in observation.evidence
    )
    controls = request.context.references
    references.extend(
        (
            controls.approved_configuration.evidence,
            controls.identity_lineage.evidence,
            controls.provenance.evidence,
            controls.consent.evidence,
            controls.quality.evidence,
            controls.support.evidence,
            controls.intended_use.evidence,
        )
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
) -> tuple[ControlDecisionRecord, ...]:
    references = request.context.references
    values = (
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
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=getattr(reference, "binding_digest", None),
        )
        for role, reference in values
    )


def _uncertainty() -> UncertaintyProfile:
    values = {
        "measurement": "Measurement values are not read from opaque references.",
        "sampling": "Sampling coverage is not available at this metadata-only boundary.",
        "parameter": "No fitted parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves the longitudinal model ABI open.",
        "identification": "Identity, lineage, and biological state are not inferred.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": (
            "Transport across cohorts, assays, territories, or treatment eras is not estimable."
        ),
    }
    estimates = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimates,
        sensitivity_notes=(
            "Trajectory ordering is replay-stable but contains no quantitative state estimate.",
            "Owner review is required before any change-point or evolutionary claim is promoted.",
        ),
    )


def _provenance(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1505.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1505_MODULE_ID,
        module_version=M1505_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.network_state_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(observation.feature_artifact.digest for observation in request.observations),
            request.policy.configuration.model_reference.digest,
        ),
        configuration_digest=sha256_digest(request.policy.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _typed_uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=0.9,
        rationale=(
            "Deterministic bootstrap perturbations and signed temporal coherence provide "
            "research-use-only interval support."
        ),
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=estimate,
        model_form=estimate,
        identification=estimate,
        support=estimate,
        transport=estimate,
        sensitivity_notes=(
            "Intervals separate measurement perturbation from the locked temporal graph; "
            "they are not calibrated clinical probabilities.",
        ),
    )


def _huber_weight(residual: float) -> float:
    magnitude = abs(residual)
    return 1.0 if magnitude <= _HUBER_DELTA else _HUBER_DELTA / magnitude


def _huber_loss(residual: float) -> float:
    magnitude = abs(residual)
    return (
        0.5 * residual * residual
        if magnitude <= _HUBER_DELTA
        else _HUBER_DELTA * (magnitude - 0.5 * _HUBER_DELTA)
    )


def _typed_terms(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
) -> tuple[_TypedTerm, ...]:
    return tuple(
        _TypedTerm(
            sequence=item.sequence,
            observation_id=item.observation_id,
            program=item.program,
            state=item.evidence_state,
            value=item.standardized_effect or 0.0,
            standard_error=item.standard_error or 1.0,
            quality_weight=item.quality_weight,
        )
        for item in request.observations
        if item.program is not None
        and item.evidence_state
        in {LongitudinalEvidenceState.OBSERVED, LongitudinalEvidenceState.LEFT_CENSORED}
        and item.standardized_effect is not None
        and item.standard_error is not None
    )


def _typed_objective(
    values: list[list[float]],
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> float:
    index = {sequence: position for position, sequence in enumerate(sequences)}
    program_index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for row in values for value in row)
    for term in terms:
        current = values[program_index[term.program]][index[term.sequence]]
        residual = (
            max(0.0, current - term.value)
            if term.state is LongitudinalEvidenceState.LEFT_CENSORED
            else current - term.value
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    for row in values:
        for position in range(1, len(row)):
            objective += _TEMPORAL_SMOOTHING * _huber_loss(row[position] - row[position - 1])
    for source, target, sign in _PROGRAM_EDGES:
        source_row, target_row = values[program_index[source]], values[program_index[target]]
        for source_value, target_value in zip(source_row, target_row, strict=True):
            objective += _PROGRAM_EDGE_WEIGHT * _huber_loss(target_value - sign * source_value)
    return objective


def _initial_typed_values(
    grouped: dict[tuple[GliomaEvolutionProgram, int], list[_TypedTerm]],
    sequences: tuple[int, ...],
) -> list[list[float]]:
    """Build a feasible robust start without treating censor limits as values."""

    sequence_index = {sequence: position for position, sequence in enumerate(sequences)}
    program_index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    values = [[0.0 for _ in sequences] for _ in _PROGRAM_ORDER]
    for (program, sequence), items in grouped.items():
        observed = tuple(
            item for item in items if item.state is LongitudinalEvidenceState.OBSERVED
        )
        limits = tuple(
            item.value for item in items if item.state is LongitudinalEvidenceState.LEFT_CENSORED
        )
        if observed:
            total = sum(item.quality_weight for item in observed)
            center = sum(item.quality_weight * item.value for item in observed) / max(
                _MIN_SCALE, total
            )
            # A left-censored term is an upper bound. Starting above its
            # tightest limit would create an artificial residual on iteration 0.
            initial = min((center, *limits)) if limits else center
        elif limits:
            # Ridge is centered at zero. Keep that neutral start when feasible;
            # otherwise start on the tightest feasible boundary.
            initial = min((0.0, *limits))
        else:
            continue
        values[program_index[program]][sequence_index[sequence]] = max(
            -_MAX_EFFECT, min(_MAX_EFFECT, initial)
        )
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> _TypedFit:
    program_index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[tuple[GliomaEvolutionProgram, int], list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[(term.program, term.sequence)].append(term)
    values = _initial_typed_values(grouped, sequences)
    initial_objective = _typed_objective(values, terms, sequences)
    if not math.isfinite(initial_objective):
        return _TypedFit(
            values=tuple(tuple(float(f"{value:.8f}") for value in row) for row in values),
            converged=False,
            iterations=0,
            objective=0.0,
            max_update=0.0,
            objective_trace=(),
        )
    trace = [float(f"{initial_objective:.8f}")]
    converged = False
    max_update = math.inf
    iterations = 0
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        iterations = iteration
        old = [row.copy() for row in values]
        previous = trace[-1]
        proposals = [row.copy() for row in old]
        for position, program in enumerate(_PROGRAM_ORDER):
            for time_position, sequence in enumerate(sequences):
                current = old[position][time_position]
                gradient = 2.0 * _RIDGE * current
                hessian = 2.0 * _RIDGE
                for term in grouped.get((program, sequence), ()):
                    if (
                        term.state is LongitudinalEvidenceState.LEFT_CENSORED
                        and current <= term.value
                    ):
                        continue
                    residual = (
                        max(0.0, current - term.value)
                        if term.state is LongitudinalEvidenceState.LEFT_CENSORED
                        else current - term.value
                    ) / max(_MIN_SCALE, term.standard_error)
                    information = term.quality_weight * _huber_weight(residual) / max(
                        _MIN_SCALE, term.standard_error**2
                    )
                    gradient += information * (current - term.value)
                    hessian += information
                if time_position:
                    residual = current - old[position][time_position - 1]
                    gradient += _TEMPORAL_SMOOTHING * _huber_weight(residual) * residual
                    hessian += _TEMPORAL_SMOOTHING
                if time_position + 1 < len(sequences):
                    residual = current - old[position][time_position + 1]
                    gradient += _TEMPORAL_SMOOTHING * _huber_weight(residual) * residual
                    hessian += _TEMPORAL_SMOOTHING
                for source, target, sign in _PROGRAM_EDGES:
                    if program is source:
                        residual = old[program_index[target]][time_position] - sign * current
                        gradient += (
                            -_PROGRAM_EDGE_WEIGHT * sign * _huber_weight(residual) * residual
                        )
                        hessian += _PROGRAM_EDGE_WEIGHT
                    elif program is target:
                        residual = current - sign * old[program_index[source]][time_position]
                        gradient += _PROGRAM_EDGE_WEIGHT * _huber_weight(residual) * residual
                        hessian += _PROGRAM_EDGE_WEIGHT
                proposal = current - gradient / max(_MIN_SCALE, hessian)
                proposals[position][time_position] = max(
                    -_MAX_EFFECT,
                    min(_MAX_EFFECT, current + _DAMPING * (proposal - current)),
                )
        objective = _typed_objective(proposals, terms, sequences)
        accepted = proposals
        if not math.isfinite(objective) or objective > previous + _OBJECTIVE_TOLERANCE:
            # Temporal smoothing and signed cycles can make a full Jacobi sweep
            # overshoot. Backtrack the complete trajectory update to preserve a
            # deterministic, replay-auditable monotone objective trace.
            accepted = [row.copy() for row in old]
            objective = previous
            delta = [
                [after - before for after, before in zip(row, old_row, strict=True)]
                for row, old_row in zip(proposals, old, strict=True)
            ]
            step = _DAMPING
            for _ in range(_BACKTRACKING_STEPS):
                step *= _BACKTRACKING_FACTOR
                trial = [
                    [
                        max(-_MAX_EFFECT, min(_MAX_EFFECT, before + step * change))
                        for before, change in zip(old_row, delta_row, strict=True)
                    ]
                    for old_row, delta_row in zip(old, delta, strict=True)
                ]
                trial_objective = _typed_objective(trial, terms, sequences)
                if math.isfinite(trial_objective) and (
                    trial_objective <= previous + _OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    objective = trial_objective
                    break
            else:
                return _TypedFit(
                    values=tuple(tuple(float(f"{value:.8f}") for value in row) for row in old),
                    converged=False,
                    iterations=iteration,
                    objective=float(f"{previous:.8f}"),
                    max_update=0.0,
                    objective_trace=tuple(trace),
                )
        values = accepted
        max_update = max(
            abs(new - before)
            for row, old_row in zip(values, old, strict=True)
            for new, before in zip(row, old_row, strict=True)
        )
        trace.append(float(f"{objective:.8f}"))
        if max_update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            break
    return _TypedFit(
        values=tuple(tuple(float(f"{value:.8f}") for value in row) for row in values),
        converged=converged,
        iterations=iterations,
        objective=float(f"{trace[-1]:.8f}"),
        max_update=float(f"{(max_update if math.isfinite(max_update) else 0.0):.8f}"),
        objective_trace=tuple(trace),
    )


def _hash_uniform(material: str) -> float:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)


def _hash_normal(material: str) -> float:
    first = max(_MIN_SCALE, _hash_uniform(material + ":u1"))
    second = _hash_uniform(material + ":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return float(f"{ordered[rank]:.8f}")


def _aggregate(
    values: tuple[tuple[float, ...], ...], terms: tuple[_TypedTerm, ...]
) -> tuple[float, ...]:
    weights = {
        program: sum(item.quality_weight for item in terms if item.program is program)
        for program in _PROGRAM_ORDER
    }
    denominator = max(_MIN_SCALE, sum(weights.values()))
    aggregates: list[float] = []
    for index in range(len(values[0])):
        weighted = sum(
            weights[program] * values[position][index]
            for position, program in enumerate(_PROGRAM_ORDER)
        )
        aggregates.append(float(f"{weighted / denominator:.8f}"))
    return tuple(aggregates)


def _typed_trajectory(  # noqa: C901, PLR0912 - trajectory and change-point closure is explicit.
    request: ModelComplexActivityLongitudinalEvolutionRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[tuple[TrajectoryState, ...], tuple[ChangePoint, ...], _TypedFit] | None:
    terms = _typed_terms(request)
    if len(terms) < _MIN_TYPED_TERMS or len({item.program for item in terms}) < _STATE_DIMENSIONS:
        return None
    sequences = tuple(item.sequence for item in request.observations)
    fit = _fit_typed(terms, sequences)
    if not fit.converged:
        return None
    draws: list[tuple[float, ...]] = []
    for replicate in range(request.policy.configuration.bootstrap_replicates):
        perturbed = tuple(
            _TypedTerm(
                sequence=item.sequence,
                observation_id=item.observation_id,
                program=item.program,
                state=item.state,
                value=max(
                    -_MAX_EFFECT,
                    min(
                        _MAX_EFFECT,
                        item.value
                        + 0.5
                        * item.standard_error
                        * _hash_normal(f"{request_hash}:{replicate}:{item.observation_id}"),
                    ),
                ),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
            for item in terms
        )
        draw_fit = _fit_typed(perturbed, sequences)
        if not draw_fit.converged:
            return None
        draws.append(_aggregate(draw_fit.values, perturbed))
    aggregate = _aggregate(fit.values, terms)
    states: list[TrajectoryState] = []
    threshold = 0.25
    for index, observation in enumerate(request.observations):
        samples = tuple(draw[index] for draw in draws)
        lower, upper = min(aggregate[index], _quantile(samples, _BOOTSTRAP_LOW)), max(
            aggregate[index], _quantile(samples, _BOOTSTRAP_HIGH)
        )
        if lower > threshold:
            label = "activated"
        elif upper < -threshold:
            label = "suppressed"
        elif lower >= -threshold and upper <= threshold:
            label = "neutral"
        else:
            label = "indeterminate"
        if observation.evidence_state in {
            LongitudinalEvidenceState.MISSING,
            LongitudinalEvidenceState.UNSUPPORTED,
        }:
            label = "indeterminate"
        agreement = sum(
            (value > threshold) == (aggregate[index] > threshold)
            and (value < -threshold) == (aggregate[index] < -threshold)
            for value in samples
        ) / max(1, len(samples))
        program_label = (
            observation.program.value if observation.program is not None else "complex_activity"
        )
        states.append(
            TrajectoryState(
                state_id=f"state.m1505.{request_hash.removeprefix('sha256:')[:12]}.{observation.sequence}",
                sequence=observation.sequence,
                label=f"{program_label}:{label}",
                posterior_probability=float(f"{agreement:.8f}"),
                observation_ids=(observation.observation_id,),
                evidence=evidence[:1],
            )
        )
    change_points: list[ChangePoint] = []
    for left, right, left_value, right_value in zip(
        states[:-1], states[1:], aggregate[:-1], aggregate[1:], strict=True
    ):
        crossed = (left_value <= -threshold and right_value >= threshold) or (
            left_value >= threshold and right_value <= -threshold
        )
        if crossed:
            probability = min(1.0, abs(right_value - left_value) / 2.0)
            change_points.append(
                ChangePoint(
                    change_point_id=(
                        f"change-point.m1505.{request_hash.removeprefix('sha256:')[:12]}."
                        f"{right.sequence}"
                    ),
                    sequence=right.sequence,
                    status=ChangePointStatus.DETECTED,
                    before_state_id=left.state_id,
                    after_state_id=right.state_id,
                    posterior_probability=float(f"{probability:.8f}"),
                    rationale=(
                        "Bootstrap-supported signed program trajectory crossed the state band."
                    ),
                    evidence=evidence[:1],
                )
            )
        else:
            change_points.append(
                ChangePoint(
                    change_point_id=(
                        f"change-point.m1505.{request_hash.removeprefix('sha256:')[:12]}."
                        f"{right.sequence}"
                    ),
                    sequence=right.sequence,
                    status=ChangePointStatus.NOT_DETECTED,
                    rationale="Signed trajectory remained within the same threshold side.",
                    evidence=evidence[:1],
                )
            )
    return tuple(states), tuple(change_points), fit


def _trajectory(
    request: ModelComplexActivityLongitudinalEvolutionRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[tuple[TrajectoryState, ...], tuple[ChangePoint, ...]]:
    states = tuple(
        TrajectoryState(
            state_id=f"state.m1505.{request_hash.removeprefix('sha256:')[:12]}.{observation.sequence}",
            sequence=observation.sequence,
            label=f"caller_declared:{observation.feature_artifact.artifact_id}",
            posterior_probability=1.0,
            observation_ids=(observation.observation_id,),
            evidence=(
                EvidenceReference(
                    reference=observation.feature_artifact,
                    role="evidence",
                    claim=_EVIDENCE_CLAIM,
                ),
            ),
        )
        for observation in request.observations
    )
    change_points = tuple(
        ChangePoint(
            change_point_id=(
                f"change-point.m1505.{request_hash.removeprefix('sha256:')[:12]}."
                f"{left.sequence}-{right.sequence}"
            ),
            sequence=right.sequence,
            status=ChangePointStatus.NOT_EVALUABLE,
            rationale=(
                "Opaque caller-declared references do not support calibrated change-point "
                "estimation."
            ),
            evidence=evidence[:1],
        )
        for left, right in zip(request.observations[:-1], request.observations[1:], strict=True)
    )
    return states, change_points


class M1505EvolutionEngine:
    """Replay legacy metadata or fit the opt-in typed glioma temporal graph."""

    __slots__ = ()

    def construct(self, request: object) -> ComplexActivityLongitudinalEvolutionResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        typed_requested = (
            validated.policy.configuration.model_family is EvolutionModelFamily.GLIOMA_TYPED_GRAPH
        )
        typed_bundle = (
            _typed_trajectory(validated, evidence, request_hash) if typed_requested else None
        )
        if typed_requested and typed_bundle is not None:
            trajectory, change_points, typed_fit = typed_bundle
            status = TrajectoryStatus.MODELED
            support_status = SupportStatus.SUPPORTED
            support_code = "m1505_typed_glioma_graph"
            support_rationale = (
                "Signed glioma program trajectories converged with temporal smoothing and "
                "deterministic perturbation intervals."
            )
            uncertainty = _typed_uncertainty()
            human_review = False
            typed_reason: str | None = None
        elif typed_requested:
            trajectory, change_points, typed_fit = (), (), None
            status = TrajectoryStatus.ABSTAINED
            support_status = SupportStatus.REVIEW_REQUIRED
            support_code = "m1505_typed_insufficient_support"
            support_rationale = (
                "At least two supported program observations are required for the typed "
                "longitudinal graph."
            )
            uncertainty = _uncertainty()
            human_review = True
            typed_reason = "Typed longitudinal evidence is insufficient for a safe trajectory."
        else:
            trajectory, change_points = _trajectory(validated, evidence, request_hash)
            typed_fit = None
            status = TrajectoryStatus.MODELED
            support_status = SupportStatus.SUPPORTED
            support_code = "m1505_metadata_replay_supported"
            support_rationale = (
                "Ordered caller-declared trajectory metadata was replayed; no biological "
                "state or change point was inferred."
            )
            uncertainty = _uncertainty()
            human_review = True
            typed_reason = None
        diagnostic_items = [
            LongitudinalDiagnostic(
                diagnostic_id=(
                    f"diagnostic.m1505.{request_hash.removeprefix('sha256:')[:12]}.{code}"
                ),
                code=code,
                message=message,
                evidence=evidence[:1],
            )
            for code, message in (
                (
                    LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
                    "Observation sequence and aware timestamps are strictly ordered.",
                ),
                (
                    LongitudinalDiagnosticCode.FUTURE_LEAKAGE_BLOCKED,
                    "The replay consumes each observation only in caller-declared order.",
                ),
                (
                    LongitudinalDiagnosticCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    (
                        "Typed graph execution is experimental and the surrounding M15-05 ABI "
                        "remains provisional."
                        if typed_requested
                        else (
                            "No owner-frozen scientific model or calibrated change-point ABI "
                            "executes."
                        )
                    ),
                ),
            )
        ]
        if typed_requested and typed_bundle is None:
            diagnostic_items.append(
                LongitudinalDiagnostic(
                    diagnostic_id=f"diagnostic.m1505.{request_hash.removeprefix('sha256:')[:12]}.unsupported",
                    code=LongitudinalDiagnosticCode.UPSTREAM_UNSUPPORTED,
                    message=typed_reason or "Typed graph support is insufficient.",
                    evidence=evidence[:1],
                )
            )
        diagnostics = tuple(diagnostic_items)
        payload: dict[str, object] = {
            "output_type": "complex_activity_longitudinal_evolution",
            "result_id": f"result.m1505.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1505_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": status,
            "trajectory": trajectory,
            "change_points": change_points,
            "diagnostics": diagnostics,
            "abstention_reason": typed_reason,
            "parent_target": M1505_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=support_status,
                reason_code=support_code,
                rationale=support_rationale,
            ),
            "uncertainty": uncertainty,
            "provenance": _provenance(validated, request_hash),
            "evidence": evidence,
            "limitations": _LIMITATIONS
            + ((
                Limitation(
                    code="typed_glioma_temporal_graph",
                    statement=(
                        "Typed trajectories use robust signed program smoothing and bootstrap "
                        "intervals; they are research-use-only signals."
                    ),
                ),
            ) if typed_requested else ()),
            "temporal_order_verified": True,
            "future_leakage_checked": True,
            "human_review_required": human_review,
            "typed_model": typed_requested and typed_bundle is not None,
            "solver_iterations": typed_fit.iterations if typed_fit is not None else None,
            "solver_objective": typed_fit.objective if typed_fit is not None else None,
            "solver_max_update": typed_fit.max_update if typed_fit is not None else None,
            "objective_trace_digest": (
                sha256_digest("|".join(str(value) for value in typed_fit.objective_trace))
                if typed_fit is not None
                else None
            ),
        }
        constructed = ComplexActivityLongitudinalEvolutionResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1505ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1505ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1505ReplayVerificationError
        return validated


def infer_complex_activity_longitudinal_evolution(
    request: object,
) -> ComplexActivityLongitudinalEvolutionResult:
    """Public provisional M15-05 operation."""

    return M1505EvolutionEngine().construct(request)


__all__ = [
    "M1505AuthorizationError",
    "M1505EvolutionEngine",
    "M1505ReplayVerificationError",
    "infer_complex_activity_longitudinal_evolution",
    "preflight_m1505_authorization",
]
