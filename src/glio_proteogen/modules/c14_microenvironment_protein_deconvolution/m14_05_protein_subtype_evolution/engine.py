"""Deterministic, leakage-safe M14-05 temporal evolution.

Typed requests use a glioma-specific robust temporal program fit with explicit
censoring, bootstrap intervals, and objective-trace replay evidence. The opaque
ordered-reference path remains compatibility-only and never reads source bytes.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_05 import (
    M1405_CONTRACT_VERSION,
    M1405_EVIDENCE_CLAIM,
    M1405_MODULE_ID,
    M1405_PARENT,
    ChangePoint,
    ChangePointStatus,
    GliomaTrajectoryProgram,
    LongitudinalDiagnostic,
    LongitudinalDiagnosticCode,
    LongitudinalEvidenceState,
    ModelProteinSubtypeLongitudinalEvolutionRequest,
    ProteinSubtypeLongitudinalEvolutionResult,
    TimePointObservation,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ModelProteinSubtypeLongitudinalEvolutionRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeLongitudinalEvolutionResult)
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.02
_OBJECTIVE_TOLERANCE: Final = 1e-10
_BACKTRACKING_STEPS: Final = 8
_BACKTRACKING_FACTOR: Final = 0.5
_INITIAL_HUBER_ITERATIONS: Final = 32
_INITIAL_HUBER_TOLERANCE: Final = 1e-8
_TEMPORAL_SMOOTHING: Final = 0.35
_TEMPORAL_CURVATURE: Final = 0.12
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_STATE_THRESHOLD: Final = 0.25
_CHANGE_POINT_PROBABILITY: Final = 0.5
_MAX_EFFECT: Final = 20.0
_PROGRAM_ORDER: Final = tuple(GliomaTrajectoryProgram)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source and upstream artifacts remain immutable references; this module never "
            "reads their bytes."
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
            "The public ABI remains provisional pending Computational biology confirmation "
            "of the dossier slice."
        ),
    ),
)


class M1405AuthorizationError(PermissionError):
    """Caller-owned controls do not authorize longitudinal replay."""

    def __init__(self) -> None:
        super().__init__(
            "M14-05 requires accepted controls, resolved identity, and granted consent"
        )


class M1405ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-05 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-05 request must be a strict request model or mapping")


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


class M1405InferenceError(ValueError):
    """A typed temporal request cannot be evaluated safely."""


class _TypedEvidenceAbsentError(M1405InferenceError):
    def __init__(self) -> None:
        super().__init__("typed M14-05 evidence has no supported observations")


class _TypedSolverNonConvergenceError(M1405InferenceError):
    def __init__(self) -> None:
        super().__init__("typed M14-05 temporal solver did not converge")


class _TypedBootstrapNonConvergenceError(M1405InferenceError):
    def __init__(self) -> None:
        super().__init__("typed M14-05 bootstrap solver did not converge")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1405_authorization(candidate: object) -> None:
    """Check all seven controls before traversing observations or configuration."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1405AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1405AuthorizationError


def _as_request(candidate: object) -> ModelProteinSubtypeLongitudinalEvolutionRequest:
    preflight_m1405_authorization(candidate)
    if type(candidate) is ModelProteinSubtypeLongitudinalEvolutionRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
) -> tuple[EvidenceReference, ...]:
    references = (
        request.network_state_result,
        *request.source_artifacts,
        request.policy.configuration.model_reference,
        *(item.reference for item in request.policy.configuration.evidence),
        *(observation.feature_artifact for observation in request.observations),
        *(
            evidence.reference
            for observation in request.observations
            for evidence in observation.evidence
        ),
        request.context.references.approved_configuration.evidence,
        request.context.references.identity_lineage.evidence,
        request.context.references.provenance.evidence,
        request.context.references.consent.evidence,
        request.context.references.quality.evidence,
        request.context.references.support.evidence,
        request.context.references.intended_use.evidence,
    )
    unique: list[ArtifactReference] = []
    seen: set[tuple[str, str, str, str]] = set()
    for reference in references:
        key = (reference.artifact_id, reference.version, reference.digest, reference.media_type)
        if key not in seen:
            seen.add(key)
            unique.append(reference)
    return tuple(
        EvidenceReference(reference=reference, role="evidence", claim=M1405_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
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


def _uncertainty(*, typed: bool = False) -> UncertaintyProfile:
    if typed:
        estimates = {
            "measurement": UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=0.9,
                rationale=(
                    "Standard errors and quality weights are propagated through bootstrap refits."
                ),
            ),
            "sampling": UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=0.9,
                rationale=(
                    "Deterministic request-bound bootstrap perturbations provide an interval "
                    "sensitivity estimate."
                ),
            ),
            "parameter": UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=0.9,
                rationale="Robust temporal solver refits provide parameter sensitivity intervals.",
            ),
            "model_form": UncertaintyEstimate(
                state=EstimateState.NOT_ESTIMABLE,
                rationale="Alternative temporal model forms are not calibrated in this lane.",
            ),
            "identification": UncertaintyEstimate(
                state=EstimateState.NOT_APPLICABLE,
                rationale="Trajectory programs and observation identifiers are request supplied.",
            ),
            "support": UncertaintyEstimate(
                state=EstimateState.NOT_ESTIMABLE,
                rationale="Evidence issuer authenticity remains outside this boundary.",
            ),
            "transport": UncertaintyEstimate(
                state=EstimateState.NOT_ESTIMABLE,
                rationale="Cross-cohort and cross-treatment transport is not calibrated.",
            ),
        }
        return UncertaintyProfile(
            **estimates,
            sensitivity_notes=(
                "Intervals quantify measurement and solver sensitivity, not clinical risk.",
                "Typed trajectory labels remain experimental research signals.",
            ),
        )
    values = {
        "measurement": "Measurement values are not read from opaque references.",
        "sampling": "Sampling coverage is not available at this metadata-only boundary.",
        "parameter": "No fitted parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves the longitudinal model ABI open.",
        "identification": "Protein subtype and identity are not inferred.",
        "support": "Support reflects caller controls, not external evidence authenticity.",
        "transport": "Transport across cohorts, assays, or treatment eras is not estimable.",
    }
    estimate = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimate,
        sensitivity_notes=(
            "Trajectory ordering is replay-stable but contains no quantitative state estimate.",
            "Owner review is required before any change-point or subtype claim is promoted.",
        ),
    )


def _limitations(*, supported: bool, typed: bool) -> tuple[Limitation, ...]:
    values = list(_LIMITATIONS)
    if typed:
        values.extend(
            (
                Limitation(
                    code="typed_glioma_temporal_fit",
                    statement=(
                        "Typed observations are fit as signed glioma program trajectories with "
                        "robust temporal smoothing and censor-aware loss."
                    ),
                ),
                Limitation(
                    code="research_use_only",
                    statement=(
                        "Program states and intervals are exploratory research signals, not a "
                        "diagnosis, prognosis, or treatment recommendation."
                    ),
                ),
            )
        )
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="Unsupported typed evidence is quarantined for human review.",
            )
        )
    return tuple(values)


def _provenance(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    input_digests = (
        request.network_state_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
        *(observation.feature_artifact.digest for observation in request.observations),
        request.policy.configuration.model_reference.digest,
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1405.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1405_MODULE_ID,
        module_version=M1405_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.policy.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _quantize(value: float) -> float:
    return float(f"{value:.8f}")


def _huber_weight(residual: float) -> float:
    absolute = abs(residual)
    return 1.0 if absolute <= _HUBER_DELTA else _HUBER_DELTA / absolute


def _huber_loss(residual: float) -> float:
    absolute = abs(residual)
    return (
        0.5 * residual * residual
        if absolute <= _HUBER_DELTA
        else _HUBER_DELTA * (absolute - 0.5 * _HUBER_DELTA)
    )


def _typed_terms(
    observations: tuple[TimePointObservation, ...],
) -> tuple[_TypedTerm, ...]:
    terms: list[_TypedTerm] = []
    for observation in observations:
        if (
            observation.evidence_state
            not in {
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
                state=observation.evidence_state,
                value=observation.standardized_effect,
                standard_error=observation.standard_error,
                quality_weight=observation.quality_weight,
            )
        )
    return tuple(
        sorted(
            terms,
            key=lambda item: (
                item.sequence,
                item.program.value,
                item.state.value,
                item.value,
                item.standard_error,
                item.quality_weight,
            ),
        )
    )


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
    return ordered[middle] if len(ordered) % 2 else 0.5 * (ordered[middle - 1] + ordered[middle])


def _temporal_objective(
    values: list[float],
    terms: tuple[_TypedTerm, ...],
    index_by_sequence: dict[int, int],
) -> float:
    objective = _RIDGE * sum(value * value for value in values)
    for item in terms:
        index = index_by_sequence[item.sequence]
        residual = (
            max(0.0, values[index] - item.value)
            if item.state is LongitudinalEvidenceState.LEFT_CENSORED
            else values[index] - item.value
        ) / max(_MIN_SCALE, item.standard_error)
        objective += item.quality_weight * _huber_loss(residual)
    for index in range(1, len(values)):
        objective += _TEMPORAL_SMOOTHING * _huber_loss(values[index] - values[index - 1])
    for index in range(len(values) - 2):
        curvature = values[index + 2] - 2.0 * values[index + 1] + values[index]
        objective += _TEMPORAL_CURVATURE * _huber_loss(curvature)
    return objective


def _initial_measurement_objective(
    center: float,
    terms: tuple[_TypedTerm, ...],
) -> float:
    """Evaluate the robust replicate loss for one time point."""

    return float(
        sum(
            term.quality_weight
            * _huber_loss((center - term.value) / max(_MIN_SCALE, term.standard_error))
            for term in terms
        )
    )


def _robust_initial_center(terms: tuple[_TypedTerm, ...]) -> float:
    """Fit a deterministic inverse-variance Huber center for repeated assays.

    Longitudinal smoothing should not be seeded by a quality-weighted mean when
    one time-point replicate is a failed batch.  IRLS uses the same Huber loss
    as the temporal objective, with objective-safe backtracking before the
    signed temporal path is propagated.  This center is only initialization;
    the full fit still determines the reported trajectory state.
    """

    if len(terms) == 1:
        return terms[0].value
    information = tuple(
        term.quality_weight / max(_MIN_SCALE, term.standard_error**2) for term in terms
    )
    denominator = max(sum(information), _MIN_SCALE)
    estimate = (
        sum(weight * term.value for weight, term in zip(information, terms, strict=True))
        / denominator
    )
    for _ in range(_INITIAL_HUBER_ITERATIONS):
        residuals = tuple(
            (term.value - estimate) / max(_MIN_SCALE, term.standard_error) for term in terms
        )
        robust_weights = tuple(
            weight * _huber_weight(residual)
            for weight, residual in zip(information, residuals, strict=True)
        )
        robust_denominator = max(sum(robust_weights), _MIN_SCALE)
        proposal = sum(
            weight * term.value for weight, term in zip(robust_weights, terms, strict=True)
        ) / robust_denominator
        baseline_objective = _initial_measurement_objective(estimate, terms)
        proposal_objective = _initial_measurement_objective(proposal, terms)
        accepted = proposal
        if not math.isfinite(proposal_objective) or (
            proposal_objective > baseline_objective + _OBJECTIVE_TOLERANCE
        ):
            direction = proposal - estimate
            accepted = estimate
            step = _BACKTRACKING_FACTOR
            for _ in range(_BACKTRACKING_STEPS):
                trial = estimate + step * direction
                trial_objective = _initial_measurement_objective(trial, terms)
                if math.isfinite(trial_objective) and (
                    trial_objective <= baseline_objective + _OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    break
                step *= _BACKTRACKING_FACTOR
        if abs(accepted - estimate) <= _INITIAL_HUBER_TOLERANCE:
            estimate = accepted
            break
        estimate = accepted
    return estimate


def _initial_temporal_values(
    grouped: dict[int, list[_TypedTerm]],
    sequence_count: int,
) -> list[float]:
    """Seed a feasible temporal path without treating censor limits as values."""

    values = [0.0] * sequence_count
    known: set[int] = set()
    for index, group in grouped.items():
        observed = tuple(
            item for item in group if item.state is LongitudinalEvidenceState.OBSERVED
        )
        limits = tuple(
            item.value for item in group if item.state is LongitudinalEvidenceState.LEFT_CENSORED
        )
        if observed:
            center = _robust_initial_center(observed)
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index] = max(-_MAX_EFFECT, min(_MAX_EFFECT, initial))
        known.add(index)
    for index in range(sequence_count):
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
    return values


def _fit_temporal(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> _TemporalFit:
    index_by_sequence = {sequence: index for index, sequence in enumerate(sequences)}
    grouped: dict[int, list[_TypedTerm]] = defaultdict(list)
    for item in terms:
        grouped[index_by_sequence[item.sequence]].append(item)
    values = _initial_temporal_values(grouped, len(sequences))
    previous = _temporal_objective(values, terms, index_by_sequence)
    if not math.isfinite(previous):
        return _TemporalFit(
            values=tuple(_quantize(value) for value in values),
            converged=False,
            iterations=0,
            objective=0.0,
            max_update=0.0,
            objective_trace=(),
        )
    trace = [_quantize(previous)]
    converged = False
    max_update = math.inf
    iterations = 0
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        iterations = iteration
        old = values.copy()
        previous_trace = trace[-1]
        proposals = old.copy()
        for index in range(len(values)):
            current = old[index]
            gradient = 2.0 * _RIDGE * current
            hessian = 2.0 * _RIDGE
            for item in grouped.get(index, ()):
                if item.state is LongitudinalEvidenceState.LEFT_CENSORED and current <= item.value:
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
                gradient += 2.0 * _TEMPORAL_SMOOTHING * (current - old[index - 1])
                hessian += 2.0 * _TEMPORAL_SMOOTHING
            if index + 1 < len(values):
                gradient += 2.0 * _TEMPORAL_SMOOTHING * (current - old[index + 1])
                hessian += 2.0 * _TEMPORAL_SMOOTHING
            for start in range(max(0, index - 2), min(index + 1, len(values) - 2)):
                curvature = old[start + 2] - 2.0 * old[start + 1] + old[start]
                coefficient = (1.0, -2.0, 1.0)[index - start]
                gradient += _TEMPORAL_CURVATURE * coefficient * curvature
                hessian += _TEMPORAL_CURVATURE * coefficient * coefficient
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            proposals[index] = max(
                -_MAX_EFFECT,
                min(_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        objective = _temporal_objective(proposals, terms, index_by_sequence)
        accepted = proposals
        if not math.isfinite(objective) or objective > previous_trace + _OBJECTIVE_TOLERANCE:
            # A robust breakpoint or curvature term can make a full Jacobi
            # sweep overshoot. Backtrack the complete vector update instead of
            # publishing a non-monotone replay trace.
            accepted = old.copy()
            delta = [after - before for after, before in zip(proposals, old, strict=True)]
            step = _BACKTRACKING_FACTOR
            for _ in range(_BACKTRACKING_STEPS):
                trial = [
                    max(-_MAX_EFFECT, min(_MAX_EFFECT, before + step * change))
                    for before, change in zip(old, delta, strict=True)
                ]
                trial_objective = _temporal_objective(trial, terms, index_by_sequence)
                if math.isfinite(trial_objective) and (
                    trial_objective <= previous_trace + _OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    objective = trial_objective
                    break
                step *= _BACKTRACKING_FACTOR
            else:
                values = old
                max_update = 0.0
                # All tested scales were locally non-improving; retain the
                # finite parent as a stationary replay point.
                converged = True
                break
        values = accepted
        max_update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        trace.append(_quantize(objective))
        if max_update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            previous = objective
            break
        previous = objective
    return _TemporalFit(
        values=tuple(_quantize(value) for value in values),
        converged=converged,
        iterations=iterations,
        objective=_quantize(previous),
        max_update=_quantize(max_update if math.isfinite(max_update) else 0.0),
        objective_trace=tuple(trace),
    )


def _fit_programs(
    terms: tuple[_TypedTerm, ...],
    sequences: tuple[int, ...],
) -> dict[GliomaTrajectoryProgram, _TemporalFit]:
    grouped: dict[GliomaTrajectoryProgram, list[_TypedTerm]] = defaultdict(list)
    for item in terms:
        grouped[item.program].append(item)
    return {
        program: _fit_temporal(
            tuple(grouped[program]),
            sequences,
        )
        for program in _PROGRAM_ORDER
        if grouped.get(program)
    }


def _hash_normal(material: str) -> float:
    def uniform(suffix: str) -> float:
        digest = hashlib.sha256((material + suffix).encode("utf-8")).digest()
        return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)

    first = max(_MIN_SCALE, uniform(":u1"))
    second = uniform(":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _trace_digest(fits: dict[GliomaTrajectoryProgram, _TemporalFit]) -> str:
    material = "|".join(
        f"{program.value}:{','.join(str(value) for value in fits[program].objective_trace)}"
        for program in _PROGRAM_ORDER
        if program in fits
    )
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _classify_interval(lower: float, upper: float) -> str:
    if lower > _STATE_THRESHOLD:
        return "activated"
    if upper < -_STATE_THRESHOLD:
        return "suppressed"
    if lower >= -_STATE_THRESHOLD and upper <= _STATE_THRESHOLD:
        return "neutral"
    return "indeterminate"


def _bootstrap_class_support(value: float, samples: tuple[float, ...]) -> float:
    """Return empirical bootstrap support for the fitted state's threshold class."""

    if not samples:
        return 0.0
    label = _classify_interval(value, value)
    if label == "activated":
        supported = sum(sample > _STATE_THRESHOLD for sample in samples)
    elif label == "suppressed":
        supported = sum(sample < -_STATE_THRESHOLD for sample in samples)
    elif label == "neutral":
        supported = sum(-_STATE_THRESHOLD <= sample <= _STATE_THRESHOLD for sample in samples)
    else:
        return 0.0
    return _quantize(supported / len(samples))


def _typed_trajectory(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[tuple[TrajectoryState, ...], tuple[ChangePoint, ...], LongitudinalDiagnostic]:
    terms = _typed_terms(request.observations)
    if not terms:
        raise _TypedEvidenceAbsentError
    sequences = tuple(observation.sequence for observation in request.observations)
    fits = _fit_programs(terms, sequences)
    if not fits or any(not fit.converged for fit in fits.values()):
        raise _TypedSolverNonConvergenceError
    prefix = request_hash.removeprefix("sha256:")[:12]
    bootstrap: dict[GliomaTrajectoryProgram, list[tuple[float, ...]]] = defaultdict(list)
    for draw in range(request.policy.configuration.bootstrap_replicates):
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
                        + 0.5
                        * item.standard_error
                        * _hash_normal(
                            f"{request_hash}:{draw}:{item.sequence}:{item.program.value}"
                        ),
                    ),
                ),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
            for item in terms
        )
        draw_fits = _fit_programs(perturbed, sequences)
        if any(not fit.converged for fit in draw_fits.values()):
            raise _TypedBootstrapNonConvergenceError
        for program, fit in draw_fits.items():
            bootstrap[program].append(fit.values)
    states: list[TrajectoryState] = []
    for observation in request.observations:
        program_for_sequence = next(
            (item.program for item in terms if item.sequence == observation.sequence), None
        )
        if program_for_sequence is None or program_for_sequence not in fits:
            states.append(
                TrajectoryState(
                    state_id=f"state.m1405.{prefix}.{observation.sequence}",
                    sequence=observation.sequence,
                    label="indeterminate",
                    posterior_probability=0.0,
                    observation_ids=(observation.observation_id,),
                    evidence=evidence[:1],
                )
            )
            continue
        fit = fits[program_for_sequence]
        position = sequences.index(observation.sequence)
        samples = tuple(values[position] for values in bootstrap[program])
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
        active_count = sum(
            item.program is program_for_sequence and item.sequence == observation.sequence
            for item in terms
        )
        label = _classify_interval(lower, upper)
        observed_value = observation.standardized_effect or 0.0
        states.append(
            TrajectoryState(
                state_id=f"state.m1405.{prefix}.{observation.sequence}",
                sequence=observation.sequence,
                label=f"{program_for_sequence.value}:{label}",
                posterior_probability=_bootstrap_class_support(fit.values[position], samples),
                observation_ids=(observation.observation_id,),
                evidence=evidence[:1],
                standardized_state=fit.values[position],
                lower_bound=lower,
                upper_bound=upper,
                evidence_count=active_count,
                stability=_quantize(max(0.0, 1.0 - abs(upper - lower) / (2.0 * _MAX_EFFECT))),
                discordance=_quantize(
                    min(
                        1.0,
                        abs(fit.values[position] - observed_value)
                        / max(_MIN_SCALE, _MAX_EFFECT),
                    )
                ),
                top_drivers=(observation.observation_id,),
            )
        )
    changes: list[ChangePoint] = []
    for before, after in pairwise(states):
        delta = (after.standardized_state or 0.0) - (before.standardized_state or 0.0)
        spread = max(
            abs((after.upper_bound or 0.0) - (before.lower_bound or 0.0)),
            abs((after.lower_bound or 0.0) - (before.upper_bound or 0.0)),
        )
        lower = _quantize(delta - spread * 0.5)
        upper = _quantize(delta + spread * 0.5)
        changes.append(
            ChangePoint(
                change_point_id=f"change-point.m1405.{prefix}.{after.sequence}",
                sequence=after.sequence,
                status=(
                    ChangePointStatus.DETECTED
                    if lower > 0.0 or upper < 0.0
                    else ChangePointStatus.NOT_DETECTED
                ),
                before_state_id=(before.state_id if lower > 0.0 or upper < 0.0 else None),
                after_state_id=(after.state_id if lower > 0.0 or upper < 0.0 else None),
                posterior_probability=(
                    _CHANGE_POINT_PROBABILITY if lower > 0.0 or upper < 0.0 else None
                ),
                rationale="Bootstrap interval for adjacent typed temporal states.",
                evidence=evidence[:1],
                effect_delta=_quantize(delta),
                lower_bound=lower,
                upper_bound=upper,
            )
        )
    first_fit = next(iter(fits.values()))
    diagnostic = LongitudinalDiagnostic(
        diagnostic_id=f"diagnostic.m1405.{prefix}.typed-solver",
        code=LongitudinalDiagnosticCode.TEMPORAL_ORDERING_VERIFIED,
        message=(
            f"Typed glioma temporal solver converged in {first_fit.iterations} iterations; "
            f"objective={first_fit.objective}, max_update={first_fit.max_update}, "
            f"trace_digest={_trace_digest(fits)}."
        ),
        evidence=evidence[:1],
        solver_iterations=first_fit.iterations,
        solver_objective=first_fit.objective,
        solver_max_update=first_fit.max_update,
        objective_trace_digest=_trace_digest(fits),
    )
    return tuple(states), tuple(changes), diagnostic


def _trajectory(
    request: ModelProteinSubtypeLongitudinalEvolutionRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[tuple[TrajectoryState, ...], tuple[ChangePoint, ...]]:
    states = tuple(
        TrajectoryState(
            state_id=f"state.m1405.{request_hash.removeprefix('sha256:')[:12]}.{observation.sequence}",
            sequence=observation.sequence,
            label=f"caller_declared:{observation.feature_artifact.artifact_id}",
            posterior_probability=1.0,
            observation_ids=(observation.observation_id,),
            evidence=(
                EvidenceReference(
                    reference=observation.feature_artifact,
                    role="evidence",
                    claim=M1405_EVIDENCE_CLAIM,
                ),
            ),
        )
        for observation in request.observations
    )
    change_points = tuple(
        ChangePoint(
            change_point_id=(
                f"change-point.m1405.{request_hash.removeprefix('sha256:')[:12]}."
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


class M1405EvolutionEngine:
    """Replay legacy metadata or fit typed glioma temporal program states."""

    __slots__ = ()

    def construct(
        self, request: object
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        validated = _as_request(request)
        request_hash = canonical_request_digest(validated)
        evidence = _evidence(validated)
        typed = _has_typed_fields(validated.observations)
        typed_diagnostic: LongitudinalDiagnostic | None = None
        abstention_diagnostic: LongitudinalDiagnostic | None = None
        if typed:
            try:
                trajectory, change_points, typed_diagnostic = _typed_trajectory(
                    validated, evidence, request_hash
                )
            except M1405InferenceError as error:
                abstention_diagnostic = LongitudinalDiagnostic(
                    diagnostic_id=(
                        f"diagnostic.m1405.{request_hash.removeprefix('sha256:')[:12]}.abstain"
                    ),
                    code=LongitudinalDiagnosticCode.UPSTREAM_UNSUPPORTED,
                    message=str(error),
                    evidence=evidence[:1],
                )
                trajectory = ()
                change_points = ()
                status = TrajectoryStatus.ABSTAINED
            else:
                status = TrajectoryStatus.MODELED
        else:
            trajectory, change_points = _trajectory(validated, evidence, request_hash)
            status = TrajectoryStatus.MODELED
        diagnostics = tuple(
            LongitudinalDiagnostic(
                diagnostic_id=f"diagnostic.m1405.{request_hash.removeprefix('sha256:')[:12]}.{code}",
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
                        "Typed robust temporal program fit executed; legacy requests remain "
                        "metadata-only pending owner review."
                        if typed
                        else (
                            "No owner-frozen scientific model or calibrated change-point ABI "
                            "executes."
                        )
                    ),
                ),
            )
        )
        if typed_diagnostic is not None:
            diagnostics = (*diagnostics, typed_diagnostic)
        if abstention_diagnostic is not None:
            diagnostics = (*diagnostics, abstention_diagnostic)
        payload: dict[str, object] = {
            "output_type": "protein_subtype_longitudinal_evolution",
            "result_id": f"result.m1405.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1405_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": validated,
            "status": status,
            "trajectory": trajectory,
            "change_points": change_points,
            "diagnostics": diagnostics,
            "abstention_reason": (
                None
                if status is TrajectoryStatus.MODELED
                else "M14-05 typed temporal inference abstained safely."
            ),
            "parent_target": M1405_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1405_metadata_replay_review_only",
                rationale=(
                    "Typed temporal program state is experimental and remains subject to human "
                    "review; legacy metadata is caller-declared only."
                    if typed
                    else "Ordered caller-declared trajectory metadata was replayed; no biological "
                    "state or change point was inferred."
                ),
            ),
            "uncertainty": _uncertainty(typed=typed),
            "provenance": _provenance(validated, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=status is TrajectoryStatus.MODELED, typed=typed),
            "temporal_order_verified": True,
            "future_leakage_checked": True,
            "human_review_required": True,
        }
        constructed = ProteinSubtypeLongitudinalEvolutionResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeLongitudinalEvolutionResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1405ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1405ReplayVerificationError
        expected = self.construct(validated.request).model_dump(mode="json")
        if replay and expected != validated.model_dump(mode="json"):
            raise M1405ReplayVerificationError
        return validated


def infer_protein_subtype_longitudinal_evolution(
    request: object,
) -> ProteinSubtypeLongitudinalEvolutionResult:
    """Public provisional M14-05 operation."""

    return M1405EvolutionEngine().construct(request)


__all__ = [
    "M1405AuthorizationError",
    "M1405EvolutionEngine",
    "M1405ReplayVerificationError",
    "infer_protein_subtype_longitudinal_evolution",
    "preflight_m1405_authorization",
]
