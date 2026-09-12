"""Deterministic, replay-bound M15-06 sensitivity simulation."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m15_06 import (
    M1506_CONTRACT_VERSION,
    M1506_EVIDENCE_CLAIM,
    M1506_MAX_EFFECT,
    M1506_PARENT,
    ComplexActivitySensitivitySimulationResult,
    GliomaPerturbationProgram,
    PerturbationEvidenceState,
    PerturbationKind,
    PerturbationResponseStatus,
    PerturbationSpecification,
    SensitivityDiagnostic,
    SensitivityDiagnosticStatus,
    SensitivityFindingCode,
    SensitivityResponse,
    SensitivitySimulationStatus,
    SensitivitySurface,
    SimulateComplexActivityPerturbationsRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m15_06.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateComplexActivityPerturbationsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivitySensitivitySimulationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_MODELS: Final = frozenset(
    {
        "curated_rule",
        "enrichment",
        "mechanistic_baseline",
        "bayesian_graph",
        "state_space",
        "mechanistic_model",
        "foundation_assisted",
        "orthogonal_consensus",
    }
)
_MAX_ABS_RESPONSE: Final = 10.0
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_EDGE_STRENGTH: Final = 0.45
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
_PROGRAM_ORDER: Final = tuple(GliomaPerturbationProgram)
_PROGRAM_EDGES: Final = (
    (GliomaPerturbationProgram.RTK_PI3K_AKT_MTOR, GliomaPerturbationProgram.PROLIFERATION, 1.0),
    (GliomaPerturbationProgram.P53_CELL_CYCLE, GliomaPerturbationProgram.PROLIFERATION, -1.0),
    (GliomaPerturbationProgram.IDH_HIF1A, GliomaPerturbationProgram.MESENCHYMAL_PROGRAM, -1.0),
    (
        GliomaPerturbationProgram.RTK_PI3K_AKT_MTOR,
        GliomaPerturbationProgram.MESENCHYMAL_PROGRAM,
        1.0,
    ),
    (GliomaPerturbationProgram.MESENCHYMAL_PROGRAM, GliomaPerturbationProgram.PROLIFERATION, 1.0),
)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    scenario_id: str
    program: GliomaPerturbationProgram
    state: PerturbationEvidenceState
    delta: float
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


class M1506AuthorizationError(PermissionError):
    """Caller controls do not authorize sensitivity simulation."""

    def __init__(self) -> None:
        super().__init__(
            "M15-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1506ReplayVerificationError(ValueError):
    """A sensitivity result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M15-06 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1506_authorization(candidate: object) -> None:
    """Check all seven controls before traversing perturbation material."""

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
    except Exception:  # noqa: BLE001
        raise M1506AuthorizationError from None
    if states != expected:
        raise M1506AuthorizationError


def _prepare(candidate: object) -> object:
    preflight_m1506_authorization(candidate)
    return candidate


def _evidence(
    request: SimulateComplexActivityPerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: list[ArtifactReference] = [
        request.upstream_result,
        *request.source_artifacts,
        request.configuration.reference_artifact,
        *(item.reference for item in request.configuration.evidence),
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
    ]
    for perturbation in request.perturbations:
        artifacts.extend(item.reference for item in perturbation.evidence)
        if perturbation.alternative_prior is not None:
            artifacts.append(perturbation.alternative_prior)
        if perturbation.assay_artifact is not None:
            artifacts.append(perturbation.assay_artifact)
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1506_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _failure_diagnostic(
    code: SensitivityDiagnosticStatus, message: str, evidence: tuple[EvidenceReference, ...]
) -> SensitivityDiagnostic:
    return SensitivityDiagnostic(
        diagnostic_id="diagnostic.m1506",
        status=code,
        message=message,
        evidence=evidence,
    )


def _evaluate_request(
    request: SimulateComplexActivityPerturbationsRequest,
) -> tuple[bool, SensitivityFindingCode | None, str | None]:
    if request.configuration.model_family not in _SUPPORTED_MODELS:
        return (
            False,
            SensitivityFindingCode.UPSTREAM_UNSUPPORTED,
            "Model family is outside the closed sensitivity support domain.",
        )
    for perturbation in request.perturbations:
        if (
            perturbation.kind is PerturbationKind.MECHANISM_STRESS
            and "negative control" not in perturbation.rationale.lower()
        ):
            return (
                False,
                SensitivityFindingCode.NEGATIVE_CONTROL_FAILED,
                "Mechanism stress perturbations require explicit negative-control gating.",
            )
        try:
            baseline = float(perturbation.baseline_value)
            perturbed = float(perturbation.perturbed_value)
        except ValueError:
            return (
                False,
                SensitivityFindingCode.INPUT_INCOMPLETE,
                "Perturbation values must be numeric for the deterministic bounded simulator.",
            )
        if not math.isfinite(baseline) or not math.isfinite(perturbed):
            return (
                False,
                SensitivityFindingCode.INPUT_INCOMPLETE,
                "Perturbation values must be finite for the deterministic bounded simulator.",
            )
        if abs(perturbed - baseline) > _MAX_ABS_RESPONSE:
            return (
                False,
                SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE,
                "Perturbation response exceeds the declared bounded envelope.",
            )
    return True, None, None


def _has_typed_fields(
    perturbations: tuple[PerturbationSpecification, ...],
) -> bool:
    return any(
        item.program is not None
        or item.evidence_state is not None
        or item.standard_error is not None
        for item in perturbations
    )


def _typed_terms(
    perturbations: tuple[PerturbationSpecification, ...],
) -> tuple[_TypedTerm, ...]:
    active = {
        PerturbationEvidenceState.OBSERVED,
        PerturbationEvidenceState.LEFT_CENSORED,
    }
    terms: list[_TypedTerm] = []
    for item in perturbations:
        if item.program is None or item.evidence_state not in active:
            continue
        if item.standard_error is None:
            continue
        try:
            delta = float(Decimal(item.perturbed_value) - Decimal(item.baseline_value))
        except (InvalidOperation, ValueError):
            continue
        if not math.isfinite(delta):
            continue
        terms.append(
            _TypedTerm(
                scenario_id=item.perturbation_id,
                program=item.program,
                state=item.evidence_state,
                delta=max(-M1506_MAX_EFFECT, min(M1506_MAX_EFFECT, delta)),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
        )
    return tuple(sorted(terms, key=lambda item: (item.program.value, item.scenario_id)))


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


def _typed_objective(
    values: list[float], terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        residual = (
            max(0.0, values[index[term.program]] - term.delta)
            if term.state is PerturbationEvidenceState.LEFT_CENSORED
            else values[index[term.program]] - term.delta
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    if include_edges:
        for source, target, sign in _PROGRAM_EDGES:
            residual = values[index[target]] - sign * _EDGE_STRENGTH * values[index[source]]
            objective += _huber_loss(residual)
    return objective


def _initial_measurement_objective(
    center: float,
    terms: tuple[_TypedTerm, ...],
) -> float:
    """Evaluate the frozen-scale robust objective for one perturbation start."""

    return float(
        sum(
            term.quality_weight
            * _huber_loss((center - term.delta) / max(_MIN_SCALE, term.standard_error))
            for term in terms
        )
    )


def _robust_initial_center(terms: tuple[_TypedTerm, ...]) -> float:
    """Find a deterministic inverse-variance Huber center for repeated deltas."""

    if len(terms) == 1:
        return terms[0].delta
    information = tuple(
        term.quality_weight / max(_MIN_SCALE, term.standard_error**2) for term in terms
    )
    denominator = max(sum(information), _MIN_SCALE)
    estimate = (
        sum(weight * term.delta for weight, term in zip(information, terms, strict=True))
        / denominator
    )
    for _ in range(_INITIAL_HUBER_ITERATIONS):
        residuals = tuple(
            (term.delta - estimate) / max(_MIN_SCALE, term.standard_error) for term in terms
        )
        robust_weights = tuple(
            weight * _huber_weight(residual)
            for weight, residual in zip(information, residuals, strict=True)
        )
        robust_denominator = max(sum(robust_weights), _MIN_SCALE)
        proposal = sum(
            weight * term.delta
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
    grouped: dict[GliomaPerturbationProgram, list[_TypedTerm]],
) -> list[float]:
    """Build a feasible start without converting censor limits to effects.

    Left-censored deltas encode only an upper bound.  Observed scenario deltas
    therefore seed a quality-weighted location that is projected onto the
    tightest bound, while censor-only programs begin at the ridge-neutral
    feasible value.  This keeps longitudinal perturbation propagation from
    manufacturing a negative observation out of a detection limit.
    """

    values = [0.0] * len(_PROGRAM_ORDER)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    for program, program_terms in grouped.items():
        observed = tuple(
            term for term in program_terms if term.state is PerturbationEvidenceState.OBSERVED
        )
        limits = tuple(
            term.delta
            for term in program_terms
            if term.state is PerturbationEvidenceState.LEFT_CENSORED
        )
        if observed:
            center = _robust_initial_center(observed)
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index[program]] = max(-M1506_MAX_EFFECT, min(M1506_MAX_EFFECT, initial))
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaPerturbationProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    values = _initial_typed_values(grouped)
    initial_objective = _typed_objective(values, terms, include_edges=include_edges)
    if not math.isfinite(initial_objective):
        return _TypedFit(
            values=tuple(_quantize(value) for value in values),
            converged=False,
            iterations=0,
            objective=0.0,
            max_update=0.0,
            objective_trace=(),
        )
    # Keep solver state below the public eight-decimal receipt precision so
    # backtracking never compares against a rounded-up or rounded-down floor.
    trace = [round(initial_objective, 12)]
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
                    term.state is PerturbationEvidenceState.LEFT_CENSORED
                    and current <= term.delta
                ):
                    continue
                residual = (
                    max(0.0, current - term.delta)
                    if term.state is PerturbationEvidenceState.LEFT_CENSORED
                    else current - term.delta
                ) / max(_MIN_SCALE, term.standard_error)
                information = (
                    term.quality_weight
                    * _huber_weight(residual)
                    / max(_MIN_SCALE, term.standard_error**2)
                )
                gradient += information * (current - term.delta)
                hessian += information
            if include_edges:
                for source, target, sign in _PROGRAM_EDGES:
                    if program is source:
                        residual = old[index[target]] - sign * _EDGE_STRENGTH * current
                        gradient += -sign * _EDGE_STRENGTH * _huber_weight(residual) * residual
                        hessian += _EDGE_STRENGTH**2
                    elif program is target:
                        residual = current - sign * _EDGE_STRENGTH * old[index[source]]
                        gradient += _huber_weight(residual) * residual
                        hessian += 1.0
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            proposals[position] = max(
                -M1506_MAX_EFFECT,
                min(M1506_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        objective = _typed_objective(proposals, terms, include_edges=include_edges)
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
                    max(-M1506_MAX_EFFECT, min(M1506_MAX_EFFECT, before + step * change))
                    for before, change in zip(old, delta, strict=True)
                ]
                trial_objective = _typed_objective(trial, terms, include_edges=include_edges)
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
        trace.append(round(objective, 12))
        if max_update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            break
    return _TypedFit(
        values=tuple(_quantize(value) for value in values),
        converged=converged,
        iterations=iterations,
        objective=_quantize(trace[-1]),
        max_update=_quantize(max_update if math.isfinite(max_update) else 0.0),
        objective_trace=tuple(trace),
    )


def _hash_uniform(material: str) -> float:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return (int.from_bytes(digest[:8], "big") + 1.0) / (2.0**64 + 1.0)


def _hash_normal(material: str) -> float:
    first = max(_MIN_SCALE, _hash_uniform(material + ":u1"))
    second = _hash_uniform(material + ":u2")
    return math.sqrt(-2.0 * math.log(first)) * math.cos(2.0 * math.pi * second)


def _typed_trace_digest(fit: _TypedFit) -> str:
    material = ",".join(str(value) for value in fit.objective_trace)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _surface(
    request: SimulateComplexActivityPerturbationsRequest,
    evidence: tuple[EvidenceReference, ...],
) -> SensitivitySurface:
    responses: list[SensitivityResponse] = []
    for perturbation in request.perturbations:
        baseline = float(perturbation.baseline_value)
        perturbed = float(perturbation.perturbed_value)
        response = perturbed - baseline
        responses.append(
            SensitivityResponse(
                scenario_id=perturbation.perturbation_id,
                status=PerturbationResponseStatus.BOUNDED,
                response_value=response,
                lower_bound=response - 0.01,
                upper_bound=response + 0.01,
                assumptions=(
                    "Caller-declared numeric perturbation values are deterministic inputs.",
                    "The bounded interval is a software envelope and not biological calibration.",
                ),
                evidence=evidence[:1],
            )
        )
    return SensitivitySurface(
        surface_id="surface.m1506",
        version=request.configuration.version,
        baseline_result=request.upstream_result,
        perturbations=request.perturbations,
        responses=tuple(responses),
        configuration=request.configuration,
        evidence=evidence,
    )


def _typed_surface(
    request: SimulateComplexActivityPerturbationsRequest,
    evidence: tuple[EvidenceReference, ...],
    request_digest: str,
) -> tuple[SensitivitySurface, _TypedFit]:
    terms = _typed_terms(request.perturbations)
    if not terms:
        raise ValueError(  # noqa: TRY003
            "missing or unsupported typed perturbations are excluded; no observed or "
            "left-censored evidence remains"
        )
    if {term.scenario_id for term in terms} != {
        item.perturbation_id for item in request.perturbations
    }:
        raise ValueError(  # noqa: TRY003
            "missing or unsupported typed perturbations are excluded; complete surface required"
        )
    fit = _fit_typed(terms)
    if not fit.converged:
        raise ValueError("typed complex-activity solver did not converge")  # noqa: TRY003
    topology_free = _fit_typed(terms, include_edges=False)
    if not topology_free.converged:
        raise ValueError("typed topology ablation solver did not converge")  # noqa: TRY003
    measurement_free = _fit_typed((), include_edges=True)
    if not measurement_free.converged:
        raise ValueError("typed measurement ablation solver did not converge")  # noqa: TRY003
    draws: list[tuple[float, ...]] = []
    for draw in range(request.configuration.bootstrap_replicates):
        perturbed = tuple(
            _TypedTerm(
                scenario_id=term.scenario_id,
                program=term.program,
                state=term.state,
                delta=max(
                    -M1506_MAX_EFFECT,
                    min(
                        M1506_MAX_EFFECT,
                        term.delta
                        + 0.5
                        * term.standard_error
                        * _hash_normal(f"{request_digest}:{draw}:{term.scenario_id}"),
                    ),
                ),
                standard_error=term.standard_error,
                quality_weight=term.quality_weight,
            )
            for term in terms
        )
        draw_fit = _fit_typed(perturbed)
        if not draw_fit.converged:
            raise ValueError(  # noqa: TRY003
                "typed complex-activity bootstrap solver did not converge"
            )
        draws.append(draw_fit.values)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    drivers = tuple(
        program.value
        for program, value in sorted(
            zip(_PROGRAM_ORDER, fit.values, strict=True),
            key=lambda pair: (-abs(pair[1]), pair[0].value),
        )[:3]
    )
    responses: list[SensitivityResponse] = []
    for scenario in request.perturbations:
        if scenario.program is None:
            raise ValueError("typed perturbation has no program")  # noqa: TRY003
        position = index[scenario.program]
        samples = tuple(draw[position] for draw in draws)
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
        width = max(_MIN_SCALE, upper - lower)
        topology_delta = fit.values[position] - topology_free.values[position]
        measurement_delta = fit.values[position] - measurement_free.values[position]
        quality = scenario.quality_weight
        perturbation_evidence = tuple((*evidence, *scenario.evidence)[:64])
        responses.append(
            SensitivityResponse(
                scenario_id=scenario.perturbation_id,
                status=PerturbationResponseStatus.BOUNDED,
                response_value=fit.values[position],
                lower_bound=lower,
                upper_bound=upper,
                assumptions=(
                    "Typed effects are fitted with robust Huber loss, ridge regularization, "
                    "and signed glioma complex-activity coupling.",
                    "Bootstrap intervals quantify measurement and topology sensitivity, not "
                    "causal or treatment effects.",
                ),
                evidence=perturbation_evidence,
                stability=_quantize(max(0.0, min(1.0, 1.0 - width / (2.0 * M1506_MAX_EFFECT)))),
                discordance=_quantize(min(1.0, abs(topology_delta))),
                top_drivers=drivers,
                ablation_effects=(
                    f"measurement_ablation_delta={_quantize(measurement_delta):.8f}",
                    f"topology_ablation_delta={_quantize(topology_delta):.8f}",
                    f"measurement_quality={_quantize(quality):.8f}",
                ),
            )
        )
    return (
        SensitivitySurface(
            surface_id=f"surface.m1506.{request_digest.removeprefix('sha256:')}",
            version=request.configuration.version,
            baseline_result=request.upstream_result,
            perturbations=request.perturbations,
            responses=tuple(responses),
            configuration=request.configuration,
            evidence=evidence,
            typed_model=True,
            solver_iterations=fit.iterations,
            solver_objective=fit.objective,
            solver_max_update=fit.max_update,
            objective_trace_digest=_typed_trace_digest(fit),
        ),
        fit,
    )


def _limitations(*, supported: bool, typed: bool = False) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="caller_declared_perturbations",
            statement=(
                "Perturbation values and evidence are caller-declared and not externally "
                "authenticated."
            ),
        ),
        Limitation(
            code="software_envelope",
            statement=(
                "Bounds are deterministic software envelopes, not biological calibration or "
                "treatment effect estimates."
            ),
        ),
        Limitation(
            code="prohibited_outputs",
            statement=(
                "No kinase activity, generic all-omics fusion, treatment recommendation, "
                "identity inference, or consent inference is emitted."
            ),
        ),
    ]
    if not supported:
        values.append(
            Limitation(
                code="safe_abstention",
                statement="No sensitivity surface is published outside the closed support domain.",
            )
        )
    if typed:
        values.extend(
            (
                Limitation(
                    code="typed_glioma_complex_activity_graph",
                    statement=(
                        "Typed perturbations use robust signed glioma program coupling "
                        "with deterministic bootstrap intervals."
                    ),
                ),
                Limitation(
                    code="research_use_only",
                    statement=(
                        "Complex-activity sensitivity intervals are research-use-only and "
                        "are not causal, clinical, or treatment claims."
                    ),
                ),
            )
        )
    return tuple(values)


class M1506SensitivitySimulatorEngine:
    """Simulate bounded perturbation responses with replay and safe abstention."""

    __slots__ = ()

    def infer(self, request: object) -> ComplexActivitySensitivitySimulationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: SimulateComplexActivityPerturbationsRequest
    ) -> ComplexActivitySensitivitySimulationResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        supported, failure_code, failure_message = _evaluate_request(request)
        typed_model = _has_typed_fields(request.perturbations)
        if supported and typed_model:
            try:
                surface, _ = _typed_surface(request, evidence, request_hash)
            except ValueError as error:
                supported = False
                failure_code = SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE
                failure_message = str(error)
                surface = None
        else:
            surface = _surface(request, evidence) if supported else None
        diagnostics = (
            (
                _failure_diagnostic(
                    SensitivityDiagnosticStatus.PASS,
                    "All perturbations are bounded and assumptions are explicit.",
                    evidence,
                ),
            )
            if supported
            else (
                _failure_diagnostic(
                    SensitivityDiagnosticStatus.FAIL,
                    failure_message or "Sensitivity request was not safely evaluable.",
                    evidence,
                ),
            )
        )
        payload: dict[str, object] = {
            "output_type": "complex_activity_sensitivity_surface",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1506_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": SensitivitySimulationStatus.SIMULATED
            if supported
            else SensitivitySimulationStatus.ABSTAINED,
            "surface": surface,
            "diagnostics": diagnostics,
            "findings": ()
            if supported
            else (failure_code or SensitivityFindingCode.INPUT_INCOMPLETE,),
            "abstention_reason": None
            if supported
            else (failure_message or "Sensitivity request was not safely evaluable."),
            "parent_target": M1506_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.SUPPORTED if supported else SupportStatus.REVIEW_REQUIRED,
                reason_code="m1506_simulation_supported"
                if supported
                else "m1506_simulation_abstained",
                rationale="All perturbations have bounded responses and explicit assumptions."
                if supported
                else "The perturbation request is outside the safely simulated support domain.",
            ),
            "uncertainty": expected_uncertainty(supported=supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported, typed=typed_model),
            "human_review_required": not supported,
        }
        constructed = ComplexActivitySensitivitySimulationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self, result: object, *, replay: bool = True
    ) -> ComplexActivitySensitivitySimulationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1506ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1506ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1506ReplayVerificationError
        return validated


def simulate_complex_activity_perturbations(
    request: object,
) -> ComplexActivitySensitivitySimulationResult:
    """Public provisional M15-06 operation."""

    return M1506SensitivitySimulatorEngine().infer(request)


__all__ = [
    "M1506AuthorizationError",
    "M1506ReplayVerificationError",
    "M1506SensitivitySimulatorEngine",
    "preflight_m1506_authorization",
    "simulate_complex_activity_perturbations",
]
