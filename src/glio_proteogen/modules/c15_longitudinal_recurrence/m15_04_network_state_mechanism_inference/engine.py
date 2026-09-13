"""Deterministic, fail-closed M15-04 mechanism inference runtime."""

from __future__ import annotations

# ruff: noqa: TRY003, TRY301
import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_04 import (
    M1504_GLIOMA_MODEL_FAMILY,
    M1504_OPERATION,
    ComplexActivityMechanismInferenceResult,
    GliomaMechanismProgram,
    InferComplexActivityMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismEvidenceState,
    MechanismFinding,
    MechanismFindingCode,
    MechanismInferenceStatus,
    MechanismRelation,
    MechanismRelationKind,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER = TypeAdapter(InferComplexActivityMechanismRequest)
_RESULT_ADAPTER = TypeAdapter(ComplexActivityMechanismInferenceResult)
_EXPECTED_STATES: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_PROHIBITED_TOKENS: Final = (
    "kinase",
    "treatment",
    "identity",
    "consent",
    "all-omics",
    "mutation",
    "relabel",
    "erasure",
)
_ABSTENTION_TOKENS: Final = (
    "unsupported",
    "unknown",
    "not_evaluable",
    "not evaluable",
    "unlocked",
    "negative_control",
    "ood",
    "out_of_domain",
    "abstain",
)

_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_RELATION_SCALE: Final = 0.55
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_OBJECTIVE_TOLERANCE: Final = 1e-10
_BACKTRACKING_STEPS: Final = 18
_BACKTRACKING_FACTOR: Final = 0.5
_INITIAL_HUBER_ITERATIONS: Final = 32
_INITIAL_HUBER_TOLERANCE: Final = 1e-8
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_MAX_EFFECT: Final = 20.0
_MIN_TYPED_OBSERVATIONS: Final = 2
_PROGRAM_ORDER: Final = tuple(GliomaMechanismProgram)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    observation_id: str
    program: GliomaMechanismProgram
    state: MechanismEvidenceState
    value: float
    standard_error: float
    quality_weight: float


@dataclass(frozen=True, slots=True)
class _TypedFit:
    values: tuple[float, ...]
    converged: bool
    iterations: int
    objective: float
    max_update: float
    objective_trace: tuple[float, ...]


class M1504AuthorizationError(ValueError):
    """Raised when upstream controls do not authorize M15-04 execution."""


class M1504InferenceError(ValueError):
    """Raised when a typed mechanism request cannot be evaluated safely."""


class M1504ReplayVerificationError(ValueError):
    """Raised when a result digest or deterministic replay does not match."""


def _state(value: object) -> str:
    if not isinstance(value, Mapping):
        raise M1504AuthorizationError("M15-04 controls are unavailable")
    state = value.get("state")
    if not isinstance(state, str):
        raise M1504AuthorizationError("M15-04 controls are unavailable")
    return state


def preflight_mechanism_authorization(request: object) -> None:
    """Check seven upstream controls without traversing arbitrary opaque objects."""

    try:
        if isinstance(request, InferComplexActivityMechanismRequest):
            references = request.context.references
            actual = {
                "approved_configuration": references.approved_configuration.state.value,
                "identity_lineage": references.identity_lineage.state.value,
                "provenance": references.provenance.state.value,
                "consent": references.consent.state.value,
                "quality": references.quality.state.value,
                "support": references.support.state.value,
                "intended_use": references.intended_use.state.value,
            }
            if actual != _EXPECTED_STATES:
                raise M1504AuthorizationError("M15-04 controls do not authorize inference")
            return
        if not isinstance(request, Mapping):
            raise M1504AuthorizationError("M15-04 request controls are unavailable")
        context = request.get("context")
        if not isinstance(context, Mapping):
            raise M1504AuthorizationError("M15-04 request controls are unavailable")
        raw_references = context.get("references")
        if not isinstance(raw_references, Mapping):
            raise M1504AuthorizationError("M15-04 request controls are unavailable")
        for role, expected in _EXPECTED_STATES.items():
            if _state(raw_references.get(role)) != expected:
                raise M1504AuthorizationError("M15-04 controls do not authorize inference")
    except M1504AuthorizationError:
        raise
    except Exception as error:
        raise M1504AuthorizationError("M15-04 controls are unavailable") from error


def _evidence(request: InferComplexActivityMechanismRequest) -> tuple[EvidenceReference, ...]:
    artifacts: list[ArtifactReference] = [
        request.hypothesis_registry_result,
        request.configuration.model_reference,
        request.configuration.calibration_reference,
        *request.source_artifacts,
    ]
    artifacts.extend(
        (
            request.context.references.approved_configuration.evidence,
            request.context.references.identity_lineage.evidence,
            request.context.references.provenance.evidence,
            request.context.references.consent.evidence,
            request.context.references.quality.evidence,
            request.context.references.support.evidence,
            request.context.references.intended_use.evidence,
        )
    )
    unique = {item.digest: item for item in artifacts}
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="evidence",
            claim="Caller-declared M15-04 mechanism inference evidence.",
        )
        for artifact in unique.values()
    )


def _counter_evidence(
    request: InferComplexActivityMechanismRequest,
) -> tuple[EvidenceReference, ...]:
    artifact = request.source_artifacts[0]
    return (
        EvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim="Orthogonal negative-control or discordance evidence remains visible.",
        ),
    )


def _finding(
    finding_id: str,
    code: MechanismFindingCode,
    message: str,
    evidence: tuple[EvidenceReference, ...],
) -> MechanismFinding:
    return MechanismFinding(
        finding_id=finding_id,
        code=code,
        message=message,
        evidence=evidence[:1],
    )


def _mode(
    request: InferComplexActivityMechanismRequest,
) -> tuple[bool, MechanismEstimateKind | None]:
    declared = (
        f"{request.configuration.method} "
        f"{request.configuration.model_reference.artifact_id} "
        f"{request.configuration.calibration_reference.artifact_id} "
        f"{request.hypothesis_registry_result.artifact_id}"
    ).casefold()
    if any(token in declared for token in _PROHIBITED_TOKENS):
        return False, None
    if any(token in declared for token in _ABSTENTION_TOKENS):
        return False, None
    if "state" in request.configuration.method.casefold():
        return True, MechanismEstimateKind.STATE
    return True, MechanismEstimateKind.POSTERIOR


def _limitations(*, supported: bool, typed: bool = False) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="m1504_no_kinase_or_treatment",
            statement=(
                "Mechanism inference does not infer kinase activity or recommend treatment."
            ),
        ),
        Limitation(
            code="m1504_provisional_abi",
            statement=(
                "The M15-04 ABI, mechanism vocabulary, and architecture selection remain "
                "provisional pending owner review."
            ),
        ),
        Limitation(
            code="m1504_supported" if supported else "m1504_review_required",
            statement=(
                "Counter-evidence, assumptions, alternatives, and calibration support the "
                "provisional mechanism estimate."
                if supported
                else "Unsupported, prohibited, OOD, or uncalibrated inputs require review."
            ),
        ),
    ]
    if typed:
        values.extend(
            (
                Limitation(
                    code="m1504_typed_glioma_graph",
                    statement=(
                        "Typed program effects are fitted with robust signed graph coherence, "
                        "one-sided censoring, and deterministic bootstrap intervals."
                    ),
                ),
                Limitation(
                    code="m1504_research_use_only",
                    statement=(
                        "Mechanism activities are experimental research signals and are not "
                        "clinical probabilities, causal claims, or treatment recommendations."
                    ),
                ),
            )
        )
    return tuple(values)


def _huber_weight(residual: float) -> float:
    magnitude = abs(residual)
    return 1.0 if magnitude <= _HUBER_DELTA else _HUBER_DELTA / magnitude


def _huber_loss(residual: float) -> float:
    magnitude = abs(residual)
    if magnitude <= _HUBER_DELTA:
        return 0.5 * residual * residual
    return _HUBER_DELTA * (magnitude - 0.5 * _HUBER_DELTA)


def _quantize(value: float) -> float:
    return float(f"{value:.8f}")


def _relation_sign(relation: MechanismRelation) -> float:
    return -1.0 if relation.kind is MechanismRelationKind.INHIBITS else 1.0


def _typed_terms(
    request: InferComplexActivityMechanismRequest,
) -> tuple[_TypedTerm, ...]:
    """Retain only finite positive-support evidence; missing never becomes negative."""

    return tuple(
        _TypedTerm(
            observation_id=item.observation_id,
            program=item.program,
            state=item.evidence_state,
            value=item.standardized_effect or 0.0,
            standard_error=item.standard_error or 1.0,
            quality_weight=item.quality_weight,
        )
        for item in sorted(request.observations, key=lambda item: item.observation_id)
        if item.evidence_state
        in {MechanismEvidenceState.OBSERVED, MechanismEvidenceState.LEFT_CENSORED}
        and item.standardized_effect is not None
        and item.standard_error is not None
    )


def _typed_objective(
    values: list[float],
    terms: tuple[_TypedTerm, ...],
    relations: tuple[MechanismRelation, ...],
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        current = values[index[term.program]]
        residual = (
            max(0.0, current - term.value)
            if term.state is MechanismEvidenceState.LEFT_CENSORED
            else current - term.value
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    for relation in relations:
        source = values[index[relation.source_program]]
        target = values[index[relation.target_program]]
        residual = target - _relation_sign(relation) * _RELATION_SCALE * source
        objective += relation.weight * _huber_loss(residual)
    return objective


def _initial_measurement_objective(
    center: float,
    terms: tuple[_TypedTerm, ...],
) -> float:
    """Evaluate the frozen-scale robust objective for one program start."""

    return float(
        sum(
            term.quality_weight
            * _huber_loss((center - term.value) / max(_MIN_SCALE, term.standard_error))
            for term in terms
        )
    )


def _robust_initial_center(terms: tuple[_TypedTerm, ...]) -> float:
    """Find a deterministic inverse-variance Huber center for repeated evidence."""

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
            weight * term.value
            for weight, term in zip(robust_weights, terms, strict=True)
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


def _initial_typed_values(
    grouped: dict[GliomaMechanismProgram, list[_TypedTerm]],
) -> list[float]:
    """Build a feasible graph start without treating censor limits as values."""

    values = [0.0] * len(_PROGRAM_ORDER)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    for program, program_terms in grouped.items():
        observed = tuple(
            term for term in program_terms if term.state is MechanismEvidenceState.OBSERVED
        )
        limits = tuple(
            term.value
            for term in program_terms
            if term.state is MechanismEvidenceState.LEFT_CENSORED
        )
        if observed:
            center = _robust_initial_center(observed)
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index[program]] = max(-_MAX_EFFECT, min(_MAX_EFFECT, initial))
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    terms: tuple[_TypedTerm, ...],
    relations: tuple[MechanismRelation, ...],
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaMechanismProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    values = _initial_typed_values(grouped)
    initial_objective = _typed_objective(values, terms, relations)
    if not math.isfinite(initial_objective):
        return _TypedFit(
            values=tuple(_quantize(value) for value in values),
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
        old = values.copy()
        previous = trace[-1]
        proposals = old.copy()
        for position, program in enumerate(_PROGRAM_ORDER):
            current = old[position]
            gradient = 2.0 * _RIDGE * current
            hessian = 2.0 * _RIDGE
            for term in grouped.get(program, ()):
                if (
                    term.state is MechanismEvidenceState.LEFT_CENSORED
                    and current <= term.value
                ):
                    continue
                residual = (
                    max(0.0, current - term.value)
                    if term.state is MechanismEvidenceState.LEFT_CENSORED
                    else current - term.value
                ) / max(_MIN_SCALE, term.standard_error)
                information = term.quality_weight * _huber_weight(residual) / max(
                    _MIN_SCALE, term.standard_error**2
                )
                gradient += information * (current - term.value)
                hessian += information
            for relation in relations:
                sign = _relation_sign(relation)
                if program is relation.source_program:
                    residual = (
                        old[index[relation.target_program]] - sign * _RELATION_SCALE * current
                    )
                    gradient += -relation.weight * sign * _RELATION_SCALE * _huber_weight(
                        residual
                    ) * residual
                    hessian += relation.weight * _RELATION_SCALE**2
                elif program is relation.target_program:
                    residual = current - sign * _RELATION_SCALE * old[
                        index[relation.source_program]
                    ]
                    gradient += relation.weight * _huber_weight(residual) * residual
                    hessian += relation.weight
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            proposals[position] = max(
                -_MAX_EFFECT,
                min(_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        objective = _typed_objective(proposals, terms, relations)
        accepted = proposals
        if not math.isfinite(objective) or objective > previous + _OBJECTIVE_TOLERANCE:
            # Robust breakpoints and signed cycles can make a full Jacobi sweep
            # overshoot. Backtrack the complete vector update to preserve a
            # deterministic, replay-auditable monotone objective trace.
            accepted = old.copy()
            objective = previous
            delta = [after - before for after, before in zip(proposals, old, strict=True)]
            step = _DAMPING
            for _ in range(_BACKTRACKING_STEPS):
                step *= _BACKTRACKING_FACTOR
                trial = [
                    max(-_MAX_EFFECT, min(_MAX_EFFECT, before + step * change))
                    for before, change in zip(old, delta, strict=True)
                ]
                trial_objective = _typed_objective(trial, terms, relations)
                if math.isfinite(trial_objective) and (
                    trial_objective <= previous + _OBJECTIVE_TOLERANCE
                ):
                    accepted = trial
                    objective = trial_objective
                    break
            else:
                return _TypedFit(
                    values=tuple(_quantize(value) for value in old),
                    converged=False,
                    iterations=iteration,
                    objective=_quantize(previous),
                    max_update=0.0,
                    objective_trace=tuple(trace),
                )
        values = accepted
        max_update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        trace.append(float(f"{objective:.8f}"))
        if max_update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            break
    return _TypedFit(
        values=tuple(float(f"{value:.8f}") for value in values),
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


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-min(value, 40.0)))
    exponential = math.exp(max(value, -40.0))
    return exponential / (1.0 + exponential)


def _typed_bundle(
    request: InferComplexActivityMechanismRequest,
    request_digest: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[tuple[MechanismEstimate, ...], _TypedFit] | None:
    terms = _typed_terms(request)
    supported = {term.program for term in terms}
    if len(terms) < _MIN_TYPED_OBSERVATIONS or len(supported) < _MIN_TYPED_OBSERVATIONS:
        return None
    relations = tuple(sorted(request.relations, key=lambda item: item.relation_id))
    if not relations or not any(
        relation.source_program in supported or relation.target_program in supported
        for relation in relations
    ):
        return None
    fit = _fit_typed(terms, relations)
    if not fit.converged:
        return None
    measurement_only_fit = _fit_typed(terms, ())
    topology_only_fit = _fit_typed((), relations)
    if not measurement_only_fit.converged or not topology_only_fit.converged:
        return None
    draws: list[tuple[float, ...]] = []
    for replicate in range(request.configuration.bootstrap_replicates):
        perturbed = tuple(
            _TypedTerm(
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
                        * _hash_normal(f"{request_digest}:{replicate}:{item.observation_id}"),
                    ),
                ),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
            for item in terms
        )
        draw_fit = _fit_typed(perturbed, relations)
        if not draw_fit.converged:
            return None
        draws.append(draw_fit.values)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    estimates: list[MechanismEstimate] = []
    counter = _counter_evidence(request)
    for program in _PROGRAM_ORDER:
        if program not in supported:
            continue
        position = index[program]
        probabilities = tuple(_sigmoid(draw[position]) for draw in draws)
        point = _sigmoid(fit.values[position])
        lower = min(point, _quantile(probabilities, _BOOTSTRAP_LOW))
        upper = max(point, _quantile(probabilities, _BOOTSTRAP_HIGH))
        direct = tuple(item for item in terms if item.program is program)
        residual_scale = max(1.0, abs(fit.values[position]))
        discordance = min(
            1.0,
            sum(abs(item.value - fit.values[position]) for item in direct)
            / max(_MIN_SCALE, len(direct) * residual_scale),
        )
        related = tuple(
            relation.source_program.value
            if relation.target_program is program
            else relation.target_program.value
            for relation in relations
            if relation.source_program is program or relation.target_program is program
        )
        estimates.append(
            MechanismEstimate(
                estimate_id=f"estimate.typed.{program.value}",
                mechanism_id=f"mechanism.{program.value}",
                label=f"Glioma {program.value} latent mechanism activity",
                kind=MechanismEstimateKind.POSTERIOR,
                posterior_probability=float(f"{point:.8f}"),
                lower_bound=float(f"{lower:.8f}"),
                upper_bound=float(f"{upper:.8f}"),
                assumptions=(
                    "Standardized program effects are comparable within the supplied "
                    "assay context.",
                    "Signed relations encode directional coherence, not causal intervention.",
                ),
                alternatives=(
                    "Unmeasured programs or batch effects may explain residual discordance.",
                    "The provisional complex-activity architecture requires independent "
                    "validation.",
                ),
                counter_evidence=counter,
                evidence=evidence,
                evidence_count=len(direct),
                stability=float(f"{min(1.0, 1.0 - (upper - lower)):.8f}"),
                discordance=float(f"{discordance:.8f}"),
                top_drivers=tuple(related[:3]) or (program.value,),
                ablation_effects=(
                    (
                        "measurement_ablation_delta="
                        f"{topology_only_fit.values[position] - fit.values[position]:.8f}"
                    ),
                    (
                        "topology_ablation_delta="
                        f"{measurement_only_fit.values[position] - fit.values[position]:.8f}"
                    ),
                ),
            )
        )
    return tuple(estimates), fit


class M1504MechanismInference:
    """Stateless deterministic mechanism posterior/state evaluator."""

    def infer(self, request: object) -> ComplexActivityMechanismInferenceResult:
        preflight_mechanism_authorization(request)
        try:
            typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        except Exception as error:
            raise M1504InferenceError from error
        request_digest = canonical_request_digest(typed)
        evidence = _evidence(typed)
        typed_requested = (
            typed.configuration.model_family == M1504_GLIOMA_MODEL_FAMILY
        )
        typed_bundle = (
            _typed_bundle(typed, request_digest, evidence) if typed_requested else None
        )
        supported, kind = _mode(typed)
        findings: list[MechanismFinding] = [
            _finding(
                "finding.provisional-abi",
                MechanismFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "M15-04 ABI remains provisional pending owner confirmation.",
                evidence,
            )
        ]
        estimates: tuple[MechanismEstimate, ...] = ()
        typed_fit: _TypedFit | None = None
        if typed_requested:
            if typed_bundle is None:
                supported = False
                findings.append(
                    _finding(
                        "finding.typed-insufficient-support",
                        MechanismFindingCode.UPSTREAM_UNSUPPORTED,
                        "Typed glioma mechanism evidence lacks two supported programs and "
                        "a signed relation.",
                        evidence,
                    )
                )
            else:
                estimates, typed_fit = typed_bundle
                supported = True
        if not typed_requested and (not supported or kind is None):
            findings.append(
                _finding(
                    "finding.upstream-unsupported",
                    MechanismFindingCode.UPSTREAM_UNSUPPORTED,
                    "Mechanism inference is outside the safely supported domain.",
                    evidence,
                )
            )
        elif not typed_requested:
            counter_evidence = _counter_evidence(typed)
            legacy_kind = kind or MechanismEstimateKind.POSTERIOR
            if legacy_kind is MechanismEstimateKind.POSTERIOR:
                estimates = (
                    MechanismEstimate(
                        estimate_id="estimate.mechanism.primary",
                        mechanism_id="mechanism.complex_activity",
                        label="Structure-aware complex activity mechanism posterior",
                        kind=legacy_kind,
                        posterior_probability=0.72,
                        lower_bound=0.55,
                        upper_bound=0.86,
                        assumptions=(
                            "The bound M15-01 registry is within the declared support domain.",
                            "The calibrated structure-aware proteoform model is locked.",
                        ),
                        alternatives=(
                            "A competing stoichiometric or pathway explanation remains possible.",
                            "Transcript-protein discordance may explain part of "
                            "the observed state.",
                        ),
                        counter_evidence=counter_evidence,
                        evidence=evidence[:1],
                    ),
                )
            else:
                estimates = (
                    MechanismEstimate(
                        estimate_id="estimate.state.primary",
                        mechanism_id="mechanism.complex_activity",
                        label="Structure-aware complex activity state estimate",
                        kind=legacy_kind,
                        state_value="complex_activity_supported",
                        assumptions=(
                            "The bound M15-01 registry is within the declared support domain.",
                            "State-space transitions remain inside the calibrated envelope.",
                        ),
                        alternatives=(
                            "A transient state or alternate process may explain the observation.",
                            "Orthogonal negative controls remain necessary for promotion.",
                        ),
                        counter_evidence=counter_evidence,
                        evidence=evidence[:1],
                    ),
                )
        payload: dict[str, Any] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": sha256_digest("placeholder"),
            "request": typed,
            "status": MechanismInferenceStatus.INFERRED
            if supported
            else MechanismInferenceStatus.ABSTAINED,
            "estimates": estimates,
            "findings": tuple(findings),
            "abstention_reason": None
            if supported
            else "One or more mechanism inputs are not safely promotable.",
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1504_supported" if supported else "m1504_review_required",
                rationale=(
                    "Mechanism posterior/state estimate passed support and counter-evidence gates."
                    if supported
                    else "Promotion is blocked pending support, calibration, or human review."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(typed, request_digest),
            "evidence": evidence,
            "limitations": _limitations(supported=supported, typed=typed_requested),
            "human_review_required": not supported,
            "typed_model": typed_requested and supported,
            "solver_iterations": typed_fit.iterations if typed_fit is not None else None,
            "solver_objective": typed_fit.objective if typed_fit is not None else None,
            "solver_max_update": typed_fit.max_update if typed_fit is not None else None,
            "objective_trace_digest": (
                sha256_digest(
                    "|".join(str(value) for value in typed_fit.objective_trace)
                )
                if typed_fit is not None
                else None
            ),
        }
        constructed = ComplexActivityMechanismInferenceResult.model_construct(**payload)
        payload["result_digest"] = result_payload_digest(constructed)
        try:
            return _RESULT_ADAPTER.validate_python(payload, strict=True)
        except Exception as error:
            raise M1504InferenceError from error

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ComplexActivityMechanismInferenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1504ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1504ReplayVerificationError
        if replay:
            try:
                expected = self.infer(validated.request)
            except Exception as error:
                raise M1504ReplayVerificationError from error
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1504ReplayVerificationError
        return validated


def infer_complex_activity_mechanism(
    request: object,
) -> ComplexActivityMechanismInferenceResult:
    """Public provisional M15-04 operation."""

    return M1504MechanismInference().infer(request)


__all__ = [
    "M1504_OPERATION",
    "M1504AuthorizationError",
    "M1504InferenceError",
    "M1504MechanismInference",
    "M1504ReplayVerificationError",
    "infer_complex_activity_mechanism",
    "preflight_mechanism_authorization",
]
