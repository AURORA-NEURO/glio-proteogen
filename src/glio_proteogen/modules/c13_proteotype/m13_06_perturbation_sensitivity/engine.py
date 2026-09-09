"""Deterministic, replay-bound M13-06 perturbation sensitivity runtime.

Typed scenarios use a glioma program interaction graph with robust coordinate
descent and deterministic perturbation intervals. The original bounded replay
path remains available for compatibility, but it is never presented as a
biological perturbation model. Unsupported or out-of-envelope scenarios close
as an explicit abstention.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m13_06 import (
    M1306_CONTRACT_VERSION,
    M1306_MODULE_ID,
    M1306_PARENT,
    GliomaPerturbationProgram,
    PerturbationEvidenceState,
    PerturbationFinding,
    PerturbationFindingCode,
    PerturbationResponse,
    PerturbationResponseStatus,
    PerturbationScenario,
    PerturbationStatus,
    ProteotypePerturbationSensitivityResult,
    SensitivityMetric,
    SensitivitySurface,
    SimulateProteotypePerturbationRequest,
    SimulatorStatus,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
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


class M1306ReplayError(ValueError):
    """Raised when a perturbation result fails deterministic replay."""


class M1306TypedInferenceError(ValueError):
    """Raised when typed perturbation evidence cannot be fitted safely."""

_EXPECTED_CONTROL_STATES: Final = {
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
        code="no_calibration",
        statement=(
            "Responses are bounded deterministic replay values, not calibrated probabilities."
        ),
    ),
    Limitation(
        code="no_biological_inference",
        statement="The simulator does not infer subtype, mechanism, identity, or treatment effect.",
    ),
    Limitation(
        code="no_kinase_or_all_omics",
        statement=(
            "Kinase activity, all-omics fusion, and treatment recommendation remain out of scope."
        ),
    ),
)
_TYPED_LIMITATIONS: Final = (
    *_LIMITATIONS,
    Limitation(
        code="typed_glioma_perturbation_graph",
        statement=(
            "Typed effects are fitted over signed RTK/PI3K/AKT/mTOR, p53/cell-cycle, "
            "IDH/HIF1A, mesenchymal, and proliferation program edges."
        ),
    ),
    Limitation(
        code="research_use_only",
        statement=(
            "Program perturbation states are research-use-only and are not causal, clinical, "
            "or treatment recommendations."
        ),
    ),
)
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_EDGE_STRENGTH: Final = 0.45
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_MAX_EFFECT: Final = 20.0
_PROGRAM_ORDER: Final = tuple(GliomaPerturbationProgram)
_PROGRAM_EDGES: Final = (
    (GliomaPerturbationProgram.RTK_PI3K_AKT_MTOR, GliomaPerturbationProgram.PROLIFERATION, 1.0),
    (GliomaPerturbationProgram.P53_CELL_CYCLE, GliomaPerturbationProgram.PROLIFERATION, -1.0),
    (
        GliomaPerturbationProgram.IDH_HIF1A,
        GliomaPerturbationProgram.MESENCHYMAL_PROGRAM,
        -1.0,
    ),
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
    scenarios: tuple[PerturbationScenario, ...],
) -> tuple[_TypedTerm, ...]:
    terms: list[_TypedTerm] = []
    for scenario in scenarios:
        if (
            scenario.program is None
            or scenario.evidence_state
            not in {
                PerturbationEvidenceState.OBSERVED,
                PerturbationEvidenceState.LEFT_CENSORED,
            }
            or scenario.standard_error is None
        ):
            continue
        terms.append(
            _TypedTerm(
                scenario_id=scenario.scenario_id,
                program=scenario.program,
                state=scenario.evidence_state,
                delta=scenario.perturbed_value - scenario.baseline_value,
                standard_error=scenario.standard_error,
                quality_weight=scenario.quality_weight,
            )
        )
    return tuple(sorted(terms, key=lambda item: (item.program.value, item.scenario_id)))


def _has_typed_fields(scenarios: tuple[PerturbationScenario, ...]) -> bool:
    return any(
        scenario.program is not None
        or scenario.evidence_state is not None
        or scenario.standard_error is not None
        for scenario in scenarios
    )


def _typed_objective(values: list[float], terms: tuple[_TypedTerm, ...]) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        residual = (
            max(0.0, values[index[term.program]] - term.delta)
            if term.state is PerturbationEvidenceState.LEFT_CENSORED
            else values[index[term.program]] - term.delta
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    for source, target, sign in _PROGRAM_EDGES:
        residual = values[index[target]] - sign * _EDGE_STRENGTH * values[index[source]]
        objective += _huber_loss(residual)
    return objective


def _initial_typed_values(
    grouped: dict[GliomaPerturbationProgram, list[_TypedTerm]],
) -> list[float]:
    """Build a feasible perturbation start without treating censor limits as values."""

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
            total = sum(term.quality_weight for term in observed)
            center = sum(term.quality_weight * term.delta for term in observed) / max(
                _MIN_SCALE, total
            )
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index[program]] = max(-_MAX_EFFECT, min(_MAX_EFFECT, initial))
    return values


def _fit_typed(
    terms: tuple[_TypedTerm, ...],
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaPerturbationProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    values = _initial_typed_values(grouped)
    previous = _typed_objective(values, terms)
    trace = [_quantize(previous)]
    converged = False
    max_update = math.inf
    iterations = 0
    for iteration in range(1, _SOLVER_ITERATIONS + 1):
        iterations = iteration
        old = values.copy()
        for position, program in enumerate(_PROGRAM_ORDER):
            current = values[position]
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
            for source, target, sign in _PROGRAM_EDGES:
                if program is source:
                    residual = values[index[target]] - sign * _EDGE_STRENGTH * current
                    gradient += -sign * _EDGE_STRENGTH * _huber_weight(residual) * residual
                    hessian += _EDGE_STRENGTH**2
                elif program is target:
                    residual = current - sign * _EDGE_STRENGTH * values[index[source]]
                    gradient += _huber_weight(residual) * residual
                    hessian += 1.0
            proposal = current - gradient / max(_MIN_SCALE, hessian)
            values[position] = max(
                -_MAX_EFFECT,
                min(_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        max_update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        objective = _typed_objective(values, terms)
        trace.append(_quantize(objective))
        if max_update <= _SOLVER_TOLERANCE and abs(previous - objective) <= _SOLVER_TOLERANCE:
            converged = True
            previous = objective
            break
        previous = objective
    return _TypedFit(
        values=tuple(_quantize(value) for value in values),
        converged=converged,
        iterations=iterations,
        objective=_quantize(previous),
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


def _typed_surface(
    request: SimulateProteotypePerturbationRequest,
    request_digest: str,
) -> SensitivitySurface:
    terms = _typed_terms(request.scenarios)
    if not terms:
        raise M1306TypedInferenceError(  # noqa: TRY003
            "typed perturbation requires at least one supported measurement"
        )
    fit = _fit_typed(terms)
    if not fit.converged:
        raise M1306TypedInferenceError(  # noqa: TRY003
            "typed perturbation solver did not converge"
        )
    replicates = request.policy.configuration.bootstrap_replicates
    draws: list[tuple[float, ...]] = []
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    for draw in range(replicates):
        perturbed = tuple(
            _TypedTerm(
                scenario_id=term.scenario_id,
                program=term.program,
                state=term.state,
                delta=max(
                    -_MAX_EFFECT,
                    min(
                        _MAX_EFFECT,
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
            raise M1306TypedInferenceError(  # noqa: TRY003
                "typed perturbation bootstrap solver did not converge"
            )
        draws.append(draw_fit.values)
    responses: list[PerturbationResponse] = []
    for scenario in request.scenarios:
        if scenario.evidence_state not in {
            PerturbationEvidenceState.OBSERVED,
            PerturbationEvidenceState.LEFT_CENSORED,
        } or scenario.program is None:
            continue
        position = index[scenario.program]
        samples = tuple(draw[position] for draw in draws)
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
        width = max(_MIN_SCALE, upper - lower)
        drivers = tuple(
            program.value
            for program, value in sorted(
                zip(_PROGRAM_ORDER, fit.values, strict=True),
                key=lambda pair: (-abs(pair[1]), pair[0].value),
            )[:3]
        )
        responses.append(
            _response(
                scenario,
                request,
            ).model_copy(
                update={
                    "standardized_effect": fit.values[position],
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "stability": _quantize(
                        max(0.0, min(1.0, 1.0 - width / (2.0 * _MAX_EFFECT)))
                    ),
                    "discordance": _quantize(
                        min(
                            1.0,
                            abs(
                                fit.values[position]
                                - (scenario.perturbed_value - scenario.baseline_value)
                            ),
                        )
                    ),
                    "top_drivers": drivers,
                }
            )
        )
    if not responses:
        raise M1306TypedInferenceError(  # noqa: TRY003
            "typed perturbation has no evaluable scenarios"
        )
    return SensitivitySurface(
        surface_id=f"surface.m1306.{request_digest.removeprefix('sha256:')}",
        axes=tuple(sorted({scenario.parameter for scenario in request.scenarios})),
        responses=tuple(responses),
        assumptions=tuple(sorted({scenario.assumption for scenario in request.scenarios})),
        evidence=request.scenarios[0].evidence,
        typed_model=True,
        solver_iterations=fit.iterations,
        solver_objective=fit.objective,
        solver_max_update=fit.max_update,
        objective_trace_digest=_typed_trace_digest(fit),
    )


class M1306AuthorizationError(PermissionError):
    """Raised before scenario traversal when caller controls are not accepted."""

    def __init__(self) -> None:
        super().__init__("M13-06 requires accepted upstream controls")


def _member(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value[name]
    return cast("object", getattr(value, name))


def _state_text(value: object) -> str:
    return str(getattr(value, "value", value))


def preflight_m1306_authorization(candidate: object) -> None:
    """Check the seven caller controls without traversing scenario payloads."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state_text(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROL_STATES
        }
    except Exception as error:
        raise M1306AuthorizationError from error
    if states != _EXPECTED_CONTROL_STATES:
        raise M1306AuthorizationError


def _as_request(candidate: object) -> SimulateProteotypePerturbationRequest:
    if type(candidate) is SimulateProteotypePerturbationRequest:
        return candidate
    if isinstance(candidate, Mapping):
        return TypeAdapter(SimulateProteotypePerturbationRequest).validate_python(candidate)
    raise TypeError


def _controls(request: SimulateProteotypePerturbationRequest) -> tuple[ControlDecisionRecord, ...]:
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
    records: list[ControlDecisionRecord] = []
    for role, reference in values:
        evidence = reference.evidence
        subject_digest = getattr(reference, "binding_digest", None)
        records.append(
            ControlDecisionRecord(
                role=role,
                decision_id=reference.decision_id,
                state=_state_text(reference.state),
                policy_version=reference.policy_version,
                evidence_digest=evidence.digest,
                subject_digest=subject_digest,
            )
        )
    return tuple(records)


def _uncertainty(*, typed: bool = False, stability: float | None = None) -> UncertaintyProfile:
    dimensions = {
        "measurement": "Measurement uncertainty is not estimable from caller-declared bounds.",
        "sampling": "Sampling uncertainty is not estimable from a bounded scenario request.",
        "parameter": "Parameter uncertainty is represented only by explicit perturbations.",
        "model_form": "Model-form uncertainty is not estimable while the ABI is provisional.",
        "identification": "Identification uncertainty is inherited and not inferred here.",
        "support": "Support uncertainty is governed by the caller controls and policy envelope.",
        "transport": "Transport uncertainty is not estimable from synthetic replay evidence.",
    }
    probability = stability if typed and stability is not None else None
    state = (
        EstimateState.ESTIMATED
        if typed and stability is not None
        else EstimateState.NOT_ESTIMABLE
    )
    value = UncertaintyEstimate(
        state=state,
        probability=probability,
        rationale=(
            "Deterministic perturbation intervals quantify measurement and signed graph "
            "sensitivity; they are not causal or clinical probabilities."
            if typed
            else "placeholder"
        ),
    )
    return UncertaintyProfile(
        **{
            name: value.model_copy(
                update={
                    "rationale": (
                        f"Typed signed-graph perturbation {name} is quantified by the "
                        "request-bound interval and remains research-use-only."
                        if typed
                        else rationale
                    )
                }
            )
            for name, rationale in dimensions.items()
        },
        sensitivity_notes=(
            (
                "Typed intervals are request-digest-seeded and replayable; they quantify "
                "measurement and topology sensitivity only."
                if typed
                else "No calibration, prevalence, clinical performance, or biological effect "
                "is estimated."
            ),
            (
                "Missing and unsupported typed scenarios are excluded rather than treated as "
                "negative evidence."
                if typed
                else "Sensitivity is limited to the caller-declared perturbation envelope."
            ),
        ),
    )


def _provenance(request: SimulateProteotypePerturbationRequest) -> ProvenanceRecord:
    input_digests = tuple(
        [request.variant_peptide_result.digest]
        + [artifact.digest for artifact in request.source_artifacts]
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1306.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M1306_MODULE_ID,
        module_version=M1306_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.policy.configuration.model_dump(mode="json")),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _finding(
    code: PerturbationFindingCode,
    message: str,
    request: SimulateProteotypePerturbationRequest,
) -> PerturbationFinding:
    evidence = request.source_artifacts[0]
    return PerturbationFinding(
        finding_id=f"finding.m1306.{code.value}",
        code=code,
        message=message,
        evidence=(
            EvidenceReference(
                reference=evidence,
                role=(
                    "evidence"
                    if code is not PerturbationFindingCode.NEGATIVE_CONTROL_FAILED
                    else "counter_evidence"
                ),
                claim="Caller-declared bounded perturbation evidence.",
            ),
        ),
    )


def _response(
    scenario: PerturbationScenario,
    request: SimulateProteotypePerturbationRequest,
) -> PerturbationResponse:
    lower = request.policy.response_lower_bound
    upper = request.policy.response_upper_bound
    baseline = scenario.baseline_value
    perturbed = scenario.perturbed_value
    if not lower <= baseline <= upper or not lower <= perturbed <= upper:
        raise ValueError
    metric = SensitivityMetric.ABSOLUTE_DELTA
    return PerturbationResponse(
        scenario_id=scenario.scenario_id,
        status=PerturbationResponseStatus.EVALUATED,
        metric=metric,
        baseline_response=baseline,
        perturbed_response=perturbed,
        delta=perturbed - baseline,
        envelope_lower=lower,
        envelope_upper=upper,
        evidence=scenario.evidence,
    )


class M1306PerturbationSensitivityEngine:
    """Execute one bounded, deterministic M13-06 request."""

    __slots__ = ()

    def compute(  # noqa: C901, PLR0912 - typed and compatibility lanes stay explicit.
        self, candidate: object
    ) -> ProteotypePerturbationSensitivityResult:
        preflight_m1306_authorization(candidate)
        request = _as_request(candidate)
        request_digest = canonical_request_digest(request)
        typed_requested = _has_typed_fields(request.scenarios)
        findings: list[PerturbationFinding] = [
            _finding(
                PerturbationFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                "The M13-06 ABI remains provisional pending owner confirmation.",
                request,
            )
        ]
        if typed_requested:
            findings.append(
                _finding(
                    PerturbationFindingCode.PROVISIONAL_ABI_PENDING_REVIEW,
                    "Typed glioma program perturbations use the signed interaction graph and "
                    "deterministic interval solver.",
                    request,
                )
            )
        responses: list[PerturbationResponse] = []
        typed_surface: SensitivitySurface | None = None
        failure: str | None = None
        if typed_requested:
            for scenario in request.scenarios:
                if scenario.status is not PerturbationStatus.SUPPORTED:
                    findings.append(
                        _finding(
                            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
                            (
                                f"Scenario {scenario.scenario_id} is not supported and "
                                "cannot be scored."
                            ),
                            request,
                        )
                    )
                    failure = "one or more perturbation scenarios are unsupported"
                    break
                if not (
                    request.policy.response_lower_bound
                    <= scenario.baseline_value
                    <= request.policy.response_upper_bound
                    and request.policy.response_lower_bound
                    <= scenario.perturbed_value
                    <= request.policy.response_upper_bound
                ):
                    failure = "one or more perturbation responses exceed the configured envelope"
                    break
            if failure is None:
                try:
                    typed_surface = _typed_surface(request, request_digest)
                    responses = list(typed_surface.responses)
                except ValueError as error:
                    failure = str(error)
        else:
            for scenario in request.scenarios:
                if scenario.status is not PerturbationStatus.SUPPORTED:
                    findings.append(
                        _finding(
                            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
                            (
                                f"Scenario {scenario.scenario_id} is not supported and "
                                "cannot be scored."
                            ),
                            request,
                        )
                    )
                    failure = "one or more perturbation scenarios are unsupported"
                    break
                try:
                    responses.append(_response(scenario, request))
                except ValueError:
                    findings.append(
                        _finding(
                            PerturbationFindingCode.OUTSIDE_SUPPORT_ENVELOPE,
                            (
                                f"Scenario {scenario.scenario_id} falls outside the bounded "
                                "response envelope."
                            ),
                            request,
                        )
                    )
                    failure = "one or more perturbation responses exceed the configured envelope"
                    break
        if failure is None:
            surface = (
                typed_surface
                if typed_requested
                else SensitivitySurface(
                    surface_id=f"surface.m1306.{request_digest.removeprefix('sha256:')}",
                    axes=tuple(sorted({scenario.parameter for scenario in request.scenarios})),
                    responses=tuple(responses),
                    assumptions=tuple(
                        sorted({scenario.assumption for scenario in request.scenarios})
                    ),
                    evidence=request.scenarios[0].evidence,
                )
            )
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="bounded_replay",
                rationale=(
                    "Every caller-declared scenario is supported and within the locked envelope."
                ),
            )
            status = SimulatorStatus.SIMULATED
            abstention_reason = None
        else:
            surface = None
            support = SupportDecision(
                status=SupportStatus.UNSUPPORTED,
                reason_code="explicit_abstention",
                rationale=failure,
            )
            status = SimulatorStatus.ABSTAINED
            abstention_reason = failure
        payload: dict[str, object] = {
            "output_type": "proteotype_perturbation_sensitivity",
            "result_id": f"result.m1306.{request_digest.removeprefix('sha256:')}",
            "result_version": M1306_CONTRACT_VERSION,
            "request_digest": request_digest,
            "request": request,
            "status": status,
            "sensitivity_surface": surface,
            "findings": tuple(findings),
            "abstention_reason": abstention_reason,
            "material_assumptions": tuple(
                sorted({scenario.assumption for scenario in request.scenarios})
            ),
            "parent_target": M1306_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(
                typed=typed_requested,
                stability=(
                    min(
                        response.stability
                        for response in responses
                        if response.stability is not None
                    )
                    if typed_requested
                    and any(response.stability is not None for response in responses)
                    else None
                ),
            ),
            "provenance": _provenance(request),
            "evidence": request.scenarios[0].evidence,
            "limitations": _TYPED_LIMITATIONS if typed_requested else _LIMITATIONS,
            "human_review_required": True,
        }
        digest_source = ProteotypePerturbationSensitivityResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(digest_source)
        return ProteotypePerturbationSensitivityResult.model_validate(payload)

    def verify(
        self, result: ProteotypePerturbationSensitivityResult
    ) -> ProteotypePerturbationSensitivityResult:
        """Recompute the bounded surface and reject semantic self-rehashes."""
        validated = ProteotypePerturbationSensitivityResult.model_validate(result, strict=True)
        if validated.request_digest != canonical_request_digest(validated.request):
            raise M1306ReplayError
        if validated.result_digest != result_payload_digest(validated):
            raise M1306ReplayError
        expected = self.compute(validated.request)
        if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
            raise M1306ReplayError
        return validated


def simulate_proteotype_perturbation_sensitivity(
    candidate: object,
) -> ProteotypePerturbationSensitivityResult:
    """Public stateless M13-06 operation."""

    return M1306PerturbationSensitivityEngine().compute(candidate)


__all__ = [
    "M1306AuthorizationError",
    "M1306PerturbationSensitivityEngine",
    "M1306ReplayError",
    "preflight_m1306_authorization",
    "simulate_proteotype_perturbation_sensitivity",
]
