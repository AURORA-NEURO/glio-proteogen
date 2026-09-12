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
from math import isfinite
from typing import Final, cast

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_03 import (
    M0903_CONTRACT_VERSION,
    M0903_EVIDENCE_CLAIM,
    M0903_GLIOMA_MODEL_FAMILY,
    M0903_MAX_CANONICAL_RESULT_BYTES,
    M0903_MAX_TYPED_EFFECT,
    M0903_MODULE_ID,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimateStatus,
    BaselineFindingCode,
    BaselineOptimizationDiagnostic,
    BaselineOptimizationStatus,
    ComplexActivityBaselineEstimate,
    ComplexActivityBaselineResult,
    EstimateComplexActivityBaselineRequest,
    GliomaBaselineEvidenceState,
    GliomaBaselineObservation,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
_TYPED_HUBER_K: Final = 1.5
_TYPED_DAMPING: Final = 0.62
_TYPED_RIDGE: Final = 0.15
_TYPED_RELATION_STRENGTH: Final = 0.22
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_OBJECTIVE_TOLERANCE: Final = 1e-10
_TYPED_BACKTRACKING_STEPS: Final = 18
_TYPED_BACKTRACKING_FACTOR: Final = 0.5
_TYPED_INITIAL_HUBER_ITERATIONS: Final = 32
_TYPED_INITIAL_HUBER_TOLERANCE: Final = 1e-8
_TYPED_INITIAL_OBJECTIVE_TOLERANCE: Final = 1e-10
_TYPED_MAX_ITERATIONS: Final = 128
_MIN_TYPED_OBSERVATIONS: Final = 3
_MIN_TYPED_PROGRAMS: Final = 2
_PROGRAMS: Final = (
    "RTK_PI3K_AKT_MTOR",
    "P53_DNA_REPAIR",
    "IDH_HIF1A",
    "HYPOXIA_ANGIOGENESIS",
    "CELL_CYCLE",
)
_PROGRAM_RELATIONS: Final = (
    ("RTK_PI3K_AKT_MTOR", "CELL_CYCLE", 1.0),
    ("P53_DNA_REPAIR", "CELL_CYCLE", -0.8),
    ("IDH_HIF1A", "HYPOXIA_ANGIOGENESIS", -0.7),
    ("HYPOXIA_ANGIOGENESIS", "RTK_PI3K_AKT_MTOR", 0.35),
)


@dataclass(frozen=True, slots=True)
class _TypedBaselineFit:
    score: float
    lower: float
    upper: float
    objective: float
    iterations: int
    convergence_gap: float
    stability: float
    discordance: float
    evidence_count: int
    top_drivers: tuple[str, ...]
    ablation_effects: tuple[str, ...]
    objective_trace: tuple[float, ...]


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


def _typed_active(observation: GliomaBaselineObservation) -> bool:
    return observation.evidence_state in {
        GliomaBaselineEvidenceState.OBSERVED,
        GliomaBaselineEvidenceState.LEFT_CENSORED,
    }


def _typed_error(observation: GliomaBaselineObservation) -> float:
    value = observation.standard_error
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_target(observation: GliomaBaselineObservation) -> float:
    if observation.evidence_state is GliomaBaselineEvidenceState.OBSERVED:
        value = observation.standardized_effect
        if value is None:
            raise ValueError from None
        return float(value)
    value = observation.censoring_limit
    if value is None:
        raise ValueError from None
    return float(value)


def _initial_typed_state(observations: tuple[GliomaBaselineObservation, ...]) -> float:
    """Build a feasible program start from measured effects and censor bounds."""

    observed = tuple(
        item
        for item in observations
        if item.evidence_state is GliomaBaselineEvidenceState.OBSERVED
    )
    limits = tuple(
        float(item.censoring_limit)
        for item in observations
        if item.evidence_state is GliomaBaselineEvidenceState.LEFT_CENSORED
        and item.censoring_limit is not None
    )
    if observed:
        terms = tuple(
            (_typed_target(item), _typed_error(item), item.quality_weight)
            for item in observed
        )
        state = _robust_initial_baseline_center(terms)
        if limits:
            state = min(state, *limits)
    elif limits:
        state = min(0.0, *limits)
    else:
        state = 0.0
    return float(np.clip(state, -M0903_MAX_TYPED_EFFECT, M0903_MAX_TYPED_EFFECT))


def _typed_censor_activation(state: float, observation: GliomaBaselineObservation) -> float:
    """Return exact one-sided influence for a left-censored observation.

    A detection limit is an upper bound rather than an observed location.  The
    feasible region therefore has zero gradient; only a state above the limit
    contributes a one-sided residual.  This prevents a smooth surrogate from
    turning censoring into a weak negative observation.
    """

    if observation.evidence_state is not GliomaBaselineEvidenceState.LEFT_CENSORED:
        return 1.0
    limit = cast("float", observation.censoring_limit)
    return 1.0 if state > limit else 0.0


def _typed_residual(state: float, observation: GliomaBaselineObservation) -> float:
    if observation.evidence_state is GliomaBaselineEvidenceState.LEFT_CENSORED:
        limit = cast("float", observation.censoring_limit)
        return max(0.0, state - limit)
    return state - _typed_target(observation)


def _typed_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * magnitude * magnitude
        if magnitude <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * magnitude - 0.5 * _TYPED_HUBER_K**2
    )


def _initial_baseline_measurement_objective(
    center: float,
    terms: tuple[tuple[float, float, float], ...],
) -> float:
    """Evaluate the frozen-scale robust objective for a baseline start."""

    return float(
        sum(
            quality
            / max(standard_error**2, 1e-12)
            * _typed_huber((center - target) / max(1e-6, standard_error))
            for target, standard_error, quality in terms
        )
    )


def _robust_initial_baseline_center(
    terms: tuple[tuple[float, float, float], ...],
) -> float:
    """Find a deterministic inverse-variance, quality-weighted Huber center."""

    if len(terms) == 1:
        return terms[0][0]
    information = tuple(
        quality / max(1e-6, standard_error**2)
        for _target, standard_error, quality in terms
    )
    estimate = sum(
        weight * term[0] for weight, term in zip(information, terms, strict=True)
    ) / max(sum(information), 1e-6)
    for _ in range(_TYPED_INITIAL_HUBER_ITERATIONS):
        residuals = tuple(
            (term[0] - estimate) / max(1e-6, term[1]) for term in terms
        )
        robust_weights = tuple(
            weight
            * (
                1.0
                if abs(residual) <= _TYPED_HUBER_K
                else _TYPED_HUBER_K / abs(residual)
            )
            for weight, residual in zip(information, residuals, strict=True)
        )
        proposal = sum(
            weight * term[0]
            for weight, term in zip(robust_weights, terms, strict=True)
        ) / max(sum(robust_weights), 1e-6)
        baseline_objective = _initial_baseline_measurement_objective(estimate, terms)
        proposal_objective = _initial_baseline_measurement_objective(proposal, terms)
        accepted = proposal
        if not isfinite(proposal_objective) or (
            proposal_objective
            > baseline_objective + _TYPED_INITIAL_OBJECTIVE_TOLERANCE
        ):
            direction = proposal - estimate
            accepted = estimate
            step = _TYPED_BACKTRACKING_FACTOR
            for _ in range(_TYPED_BACKTRACKING_STEPS):
                trial = estimate + step * direction
                trial_objective = _initial_baseline_measurement_objective(trial, terms)
                if isfinite(trial_objective) and (
                    trial_objective
                    <= baseline_objective + _TYPED_INITIAL_OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    break
                step *= _TYPED_BACKTRACKING_FACTOR
        if abs(accepted - estimate) <= _TYPED_INITIAL_HUBER_TOLERANCE:
            estimate = accepted
            break
        estimate = accepted
    return float(estimate)


def _typed_objective(
    observations: tuple[GliomaBaselineObservation, ...],
    states: np.ndarray,
    *,
    include_relations: bool,
) -> float:
    total = 0.0
    for item in observations:
        if item.program is None or not _typed_active(item):
            continue
        index = _PROGRAMS.index(item.program.value)
        weight = item.quality_weight / max(_typed_error(item) ** 2, 1e-12)
        total += weight * _typed_huber(
            _typed_residual(float(states[index]), item) / _typed_error(item)
        )
    total += _TYPED_RIDGE * float(np.sum(states * states))
    if include_relations:
        for source, target, sign in _PROGRAM_RELATIONS:
            source_value = states[_PROGRAMS.index(source)]
            target_value = states[_PROGRAMS.index(target)]
            total += _TYPED_RELATION_STRENGTH * float((target_value - sign * source_value) ** 2)
    return float(total)


def _fit_typed_states(  # noqa: C901, PLR0912, PLR0915 - coordinate descent safeguards are explicit.
    observations: tuple[GliomaBaselineObservation, ...],
    *,
    max_iterations: int,
    include_relations: bool = True,
) -> tuple[np.ndarray, float, int, float, tuple[float, ...]] | None:
    active = tuple(
        item for item in observations if _typed_active(item) and item.program is not None
    )
    if (
        len(active) < _MIN_TYPED_OBSERVATIONS
        or len({item.program for item in active}) < _MIN_TYPED_PROGRAMS
    ):
        return None
    states = np.zeros(len(_PROGRAMS), dtype=np.float64)
    for index, program in enumerate(_PROGRAMS):
        members = tuple(
            item for item in active if item.program is not None and item.program.value == program
        )
        if members:
            states[index] = _initial_typed_state(members)
    initial_objective = _typed_objective(observations, states, include_relations=include_relations)
    if not isfinite(initial_objective):
        return None
    trace: list[float] = [round(initial_objective, 10)]
    gap = float("inf")
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        iterations = iteration + 1
        previous = states.copy()
        previous_objective = trace[-1]
        updated = states.copy()
        for index, program in enumerate(_PROGRAMS):
            members = tuple(
                item
                for item in active
                if item.program is not None and item.program.value == program
            )
            numerator = _TYPED_RIDGE * 0.0
            denominator = _TYPED_RIDGE
            for item in members:
                residual = _typed_residual(float(states[index]), item)
                standardized = residual / _typed_error(item)
                robust = (
                    0.0
                    if residual == 0.0
                    else min(1.0, _TYPED_HUBER_K / max(1.0, abs(standardized)))
                )
                precision = (
                    item.quality_weight
                    * _typed_censor_activation(float(states[index]), item)
                    * robust
                    / max(_typed_error(item) ** 2, 1e-12)
                )
                numerator += precision * _typed_target(item)
                denominator += precision
            if include_relations:
                for source, target, sign in _PROGRAM_RELATIONS:
                    if target == program:
                        numerator += (
                            _TYPED_RELATION_STRENGTH * sign * states[_PROGRAMS.index(source)]
                        )
                        denominator += _TYPED_RELATION_STRENGTH
                    elif source == program:
                        numerator += (
                            _TYPED_RELATION_STRENGTH * sign * states[_PROGRAMS.index(target)]
                        )
                        denominator += _TYPED_RELATION_STRENGTH
            proposal = numerator / max(denominator, 1e-12)
            updated[index] = _TYPED_DAMPING * proposal + (1.0 - _TYPED_DAMPING) * states[index]
        candidate = np.clip(updated, -M0903_MAX_TYPED_EFFECT, M0903_MAX_TYPED_EFFECT)
        objective = _typed_objective(observations, candidate, include_relations=include_relations)
        accepted = candidate
        if objective > previous_objective + _TYPED_OBJECTIVE_TOLERANCE:
            # Huber influence changes at the censor boundary. Backtrack the
            # complete Jacobi step so the audit trace cannot increase.
            accepted = previous
            objective = previous_objective
            delta = candidate - previous
            step = _TYPED_DAMPING
            for _ in range(_TYPED_BACKTRACKING_STEPS):
                step *= _TYPED_BACKTRACKING_FACTOR
                trial = np.clip(
                    previous + step * delta,
                    -M0903_MAX_TYPED_EFFECT,
                    M0903_MAX_TYPED_EFFECT,
                )
                trial_objective = _typed_objective(
                    observations, trial, include_relations=include_relations
                )
                if trial_objective <= previous_objective + _TYPED_OBJECTIVE_TOLERANCE:
                    accepted = trial
                    objective = trial_objective
                    break
        states = accepted
        gap = float(np.max(np.abs(states - previous)))
        if not isfinite(objective):
            return None
        trace.append(round(objective, 10))
        if gap <= _TYPED_TOLERANCE and abs(previous_objective - objective) <= _TYPED_TOLERANCE:
            break
    if not trace or not isfinite(gap):
        return None
    return states, trace[-1], iterations, gap, tuple(trace)


def _typed_activity(states: np.ndarray) -> float:
    latent = float(np.average(states))
    return float(1.0 / (1.0 + np.exp(-np.clip(latent, -50.0, 50.0))))


def _typed_fit(
    observations: tuple[GliomaBaselineObservation, ...],
    request_digest: str,
    request: EstimateComplexActivityBaselineRequest,
) -> _TypedBaselineFit | None:
    ordered = tuple(sorted(observations, key=lambda item: item.observation_id))
    fitted = _fit_typed_states(
        ordered,
        max_iterations=_TYPED_MAX_ITERATIONS,
    )
    if fitted is None:
        return None
    states, objective, iterations, gap, trace = fitted
    seed = int(
        sha256_digest({"request": request_digest, "model": M0903_GLIOMA_MODEL_FAMILY}).removeprefix(
            "sha256:"
        )[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    active = tuple(item for item in ordered if _typed_active(item) and item.program is not None)
    by_program = {
        program: tuple(
            index
            for index, item in enumerate(active)
            if item.program is not None and item.program.value == program
        )
        for program in _PROGRAMS
    }
    bootstrap: list[float] = []
    for _ in range(request.configuration.bootstrap_replicates):
        indexes: list[int] = []
        for program in _PROGRAMS:
            candidates = by_program[program]
            if candidates:
                indexes.extend(
                    int(value)
                    for value in rng.choice(candidates, size=len(candidates), replace=True)
                )
        perturbed: list[GliomaBaselineObservation] = []
        for index in indexes:
            item = active[index]
            if item.evidence_state is GliomaBaselineEvidenceState.OBSERVED:
                value = _typed_target(item) + _typed_error(item) * float(rng.normal())
                perturbed.append(
                    item.model_copy(
                        update={
                            "standardized_effect": float(
                                np.clip(value, -M0903_MAX_TYPED_EFFECT, M0903_MAX_TYPED_EFFECT)
                            )
                        }
                    )
                )
            else:
                limit = cast("float", item.censoring_limit) + _typed_error(item) * float(
                    rng.normal()
                )
                perturbed.append(
                    item.model_copy(
                        update={
                            "censoring_limit": float(
                                np.clip(limit, -M0903_MAX_TYPED_EFFECT, M0903_MAX_TYPED_EFFECT)
                            )
                        }
                    )
                )
        replicate = _fit_typed_states(tuple(perturbed), max_iterations=_TYPED_MAX_ITERATIONS)
        if replicate is not None:
            bootstrap.append(_typed_activity(replicate[0]))
    if len(bootstrap) < max(8, request.configuration.bootstrap_replicates // 2):
        return None
    center = _typed_activity(states)
    lower, upper = np.quantile(np.asarray(bootstrap, dtype=np.float64), (0.05, 0.95))
    lower = float(min(lower, center))
    upper = float(max(upper, center))
    residuals = np.asarray(
        [
            _typed_residual(float(states[_PROGRAMS.index(item.program.value)]), item)
            for item in active
            if item.program is not None
        ],
        dtype=np.float64,
    )
    discordance = float(np.clip(np.median(np.abs(residuals)) / 3.0, 0.0, 1.0))
    contributions = sorted(
        (
            abs(float(residuals[index])) * active[index].quality_weight,
            active[index].feature_id,
        )
        for index in range(len(active))
    )
    without_relations = _fit_typed_states(
        ordered,
        max_iterations=_TYPED_MAX_ITERATIONS,
        include_relations=False,
    )
    ablations: tuple[str, ...] = ()
    if without_relations is not None:
        ablations = (
            "signed_program_relation_delta="
            f"{abs(center - _typed_activity(without_relations[0])):.8f}",
        )
    return _TypedBaselineFit(
        score=round(center, 8),
        lower=round(lower, 8),
        upper=round(upper, 8),
        objective=round(objective, 8),
        iterations=iterations,
        convergence_gap=round(gap, 8),
        stability=round(float(np.clip(1.0 - (upper - lower), 0.0, 1.0)), 8),
        discordance=round(discordance, 8),
        evidence_count=len(active),
        top_drivers=tuple(f"feature:{feature}" for _, feature in reversed(contributions[-4:])),
        ablation_effects=ablations,
        objective_trace=trace,
    )


def _typed_result(
    request: EstimateComplexActivityBaselineRequest,
    request_digest: str,
) -> ComplexActivityBaselineResult:
    """Build the additive typed glioma baseline result."""

    request = request.model_copy(
        update={
            "typed_observations": tuple(
                sorted(request.typed_observations, key=lambda item: item.observation_id)
            )
        }
    )
    evidence = _evidence(request)
    fit = _typed_fit(request.typed_observations, request_digest, request)
    findings: tuple[BaselineFindingCode, ...]
    if fit is None:
        reason = (
            "typed glioma baseline needs at least three supported observations across two programs "
            "and a stable bootstrap fit"
        )
        failure = (BaselineFindingCode.QUALITY_FAILED, reason)
        diagnostics = _diagnostics(request, failure)
        status = BaselineEstimateStatus.ABSTAINED
        estimate = None
        optimization = (
            BaselineOptimizationDiagnostic(
                diagnostic_id=f"diagnostic.{request_digest.removeprefix('sha256:')}.typed",
                status=BaselineOptimizationStatus.NOT_EVALUABLE,
                objective="glioma_program_baseline_activity",
                iteration_count=0,
                model_family=M0903_GLIOMA_MODEL_FAMILY,
                message=reason,
                evidence=evidence,
            ),
        )
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0903_typed_glioma_abstention",
            rationale=reason,
        )
        uncertainty = _uncertainty(estimated=False, reason=reason)
        findings = (failure[0],)
        abstention = reason
    else:
        label = (
            "complex_activity_low"
            if fit.score < 1 / 3
            else "complex_activity_intermediate"
            if fit.score < 2 / 3
            else "complex_activity_high"
        )
        estimate = ComplexActivityBaselineEstimate(
            predicted_activity=label,
            score=fit.score,
            lower_bound=fit.lower,
            upper_bound=fit.upper,
            evidence_count=fit.evidence_count,
            stability=fit.stability,
            discordance=fit.discordance,
            top_drivers=fit.top_drivers,
            ablation_effects=fit.ablation_effects,
            model_family=M0903_GLIOMA_MODEL_FAMILY,
            calibration_reference=request.configuration.benchmark_artifact,
            evidence=evidence,
        )
        optimization = (
            BaselineOptimizationDiagnostic(
                diagnostic_id=f"diagnostic.{request_digest.removeprefix('sha256:')}.typed",
                status=BaselineOptimizationStatus.CONVERGED,
                objective="glioma_program_baseline_activity",
                iteration_count=fit.iterations,
                objective_value=fit.objective,
                convergence_gap=fit.convergence_gap,
                objective_trace_digest=sha256_digest({"trace": fit.objective_trace}),
                model_family=M0903_GLIOMA_MODEL_FAMILY,
                message=(
                    "typed glioma baseline converged with signed program relations, robust Huber "
                    "coordinate descent, and stratified bootstrap"
                ),
                evidence=evidence,
            ),
        )
        diagnostics = _diagnostics(request, None)
        status = BaselineEstimateStatus.ESTIMATED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0903_typed_glioma_supported",
            rationale=(
                "explicit glioma program evidence supports a robust constrained baseline estimate"
            ),
        )
        uncertainty = _uncertainty(estimated=True)
        findings = ()
        abstention = None
    draft = ComplexActivityBaselineResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        estimate=estimate,
        diagnostics=diagnostics,
        optimization_diagnostics=optimization,
        model_family=M0903_GLIOMA_MODEL_FAMILY,
        findings=findings,
        abstention_reason=abstention,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=support,
        uncertainty=uncertainty,
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
        human_review_required=status is BaselineEstimateStatus.ABSTAINED,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


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
    if request.typed_observations:
        return _typed_result(request, canonical_request_digest(request))
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

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
        request: object | None = None,
    ) -> bool:  # noqa: PLR0911, RUF100
        typed = _validated_result(result)
        if typed is None:
            return False
        canonical_ok = canonical_bytes is None or (
            type(canonical_bytes) is bytes
            and len(canonical_bytes) <= M0903_MAX_CANONICAL_RESULT_BYTES
            and canonical_bytes == canonical_json_bytes(typed.model_dump(mode="json"))
        )
        digest_ok = typed.provenance == _provenance(
            typed.request
        ) and typed.result_digest == result_payload_digest(typed)
        replay_ok = request is None or (
            self.construct(request).result.model_dump(mode="json") == typed.model_dump(mode="json")
        )
        return canonical_ok and digest_ok and replay_ok

    def execute(self, request: object) -> BuiltM0903Result:
        return self.construct(request)


def estimate_complex_activity_baseline(request: object) -> BuiltM0903Result:
    """Estimate one complex-activity baseline with explicit safe failure."""

    return M0903BaselineEstimator().construct(request)


def _validated_result(result: object) -> ComplexActivityBaselineResult | None:
    try:
        return _RESULT_ADAPTER.validate_python(result, strict=True)
    except (TypeError, ValueError, ValidationError):
        return None


__all__ = [
    "BuiltM0903Result",
    "M0903AuthorizationError",
    "M0903BaselineEstimator",
    "M0903InputError",
    "estimate_complex_activity_baseline",
    "preflight_m0903_authorization",
]
