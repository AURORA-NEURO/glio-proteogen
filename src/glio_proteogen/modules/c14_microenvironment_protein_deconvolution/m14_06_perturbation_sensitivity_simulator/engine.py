"""Deterministic, replay-bound M14-06 perturbation simulation runtime.

The dossier does not freeze a numerical model ABI.  This implementation uses a
closed caller-declared numeric perturbation grammar and never opens opaque
artifacts.  It emits a bounded sensitivity surface only when every scenario is
supported, finite, and authorized; otherwise it abstains safely.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_06 import (
    M1406_CONTRACT_VERSION,
    M1406_EVIDENCE_CLAIM,
    M1406_MAX_EFFECT,
    M1406_PARENT,
    GliomaPerturbationProgram,
    PerturbationEvidenceState,
    PerturbationResponseStatus,
    PerturbationSpecification,
    ProteinSubtypeSensitivitySimulationResult,
    SensitivityDiagnostic,
    SensitivityDiagnosticStatus,
    SensitivityFindingCode,
    SensitivityResponse,
    SensitivitySimulationStatus,
    SensitivitySurface,
    SimulateProteinSubtypePerturbationsRequest,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m14_06.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(SimulateProteinSubtypePerturbationsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeSensitivitySimulationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_FAMILIES: Final = frozenset(
    {
        "curated_rule",
        "bayesian_graph",
        "state_space",
        "mechanistic_baseline",
        "proteome_autoencoder",
        "foundation_assisted",
        "orthogonal_consensus",
    }
)
_MISSING_VALUES: Final = frozenset({"", "na", "n/a", "missing", "null", "unsupported"})
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_EDGE_STRENGTH: Final = 0.45
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
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


class M1406SensitivityAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize sensitivity simulation."""

    def __init__(self) -> None:
        super().__init__(
            "M14-06 requires accepted controls, resolved identity, and granted consent"
        )


class M1406ReplayVerificationError(ValueError):
    """A sensitivity result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-06 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_sensitivity_authorization(candidate: object) -> None:
    """Check all seven controls before opaque traversal or numeric parsing."""

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
        raise M1406SensitivityAuthorizationError from None
    if states != expected:
        raise M1406SensitivityAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_sensitivity_authorization(candidate)
    return candidate


def _all_evidence(
    request: SimulateProteinSubtypePerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
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
    )
    unique: dict[str, ArtifactReference] = {}
    for artifact in artifacts:
        unique.setdefault(artifact.digest, artifact)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1406_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: SimulateProteinSubtypePerturbationsRequest,
) -> tuple[EvidenceReference, ...]:
    return tuple(
        EvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim=(
                "Caller-declared negative-control and counter-evidence reference; "
                "issuer authority is not authenticated."
            ),
        )
        for artifact in request.source_artifacts[:64]
    )


def _decimal(value: str) -> Decimal | None:
    if value.strip().lower() in _MISSING_VALUES:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


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
    perturbations: tuple[PerturbationSpecification, ...],
) -> tuple[_TypedTerm, ...]:
    terms: list[_TypedTerm] = []
    active_states = {
        PerturbationEvidenceState.OBSERVED,
        PerturbationEvidenceState.LEFT_CENSORED,
    }
    for item in perturbations:
        if item.program is None or item.evidence_state not in active_states:
            continue
        if item.standard_error is None:
            continue
        baseline = _decimal(item.baseline_value)
        perturbed = _decimal(item.perturbed_value)
        if baseline is None or perturbed is None:
            continue
        delta = float(perturbed - baseline)
        if not math.isfinite(delta):
            continue
        terms.append(
            _TypedTerm(
                scenario_id=item.perturbation_id,
                program=item.program,
                state=item.evidence_state,
                delta=max(-M1406_MAX_EFFECT, min(M1406_MAX_EFFECT, delta)),
                standard_error=item.standard_error,
                quality_weight=item.quality_weight,
            )
        )
    return tuple(sorted(terms, key=lambda item: (item.program.value, item.scenario_id)))


def _has_typed_fields(perturbations: tuple[PerturbationSpecification, ...]) -> bool:
    return any(
        item.program is not None
        or item.evidence_state is not None
        or item.standard_error is not None
        for item in perturbations
    )


def _typed_objective(
    values: list[float], terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        if term.state is PerturbationEvidenceState.LEFT_CENSORED:
            residual = max(0.0, values[index[term.program]] - term.delta)
        else:
            residual = values[index[term.program]] - term.delta
        objective += term.quality_weight * _huber_loss(
            residual / max(_MIN_SCALE, term.standard_error)
        )
    if include_edges:
        for source, target, sign in _PROGRAM_EDGES:
            residual = values[index[target]] - sign * _EDGE_STRENGTH * values[index[source]]
            objective += _huber_loss(residual)
    return objective


def _fit_typed(  # noqa: C901 - explicit coordinate updates keep signed edges auditable.
    terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaPerturbationProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    values = [0.0] * len(_PROGRAM_ORDER)
    for program, program_terms in grouped.items():
        values[index[program]] = sum(
            term.quality_weight * term.delta for term in program_terms
        ) / max(_MIN_SCALE, sum(term.quality_weight for term in program_terms))
    previous = _typed_objective(values, terms, include_edges=include_edges)
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
            if include_edges:
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
                -M1406_MAX_EFFECT,
                min(M1406_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        max_update = max(abs(new - before) for new, before in zip(values, old, strict=True))
        objective = _typed_objective(values, terms, include_edges=include_edges)
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


def _response(
    perturbation: PerturbationSpecification,
    *,
    evidence: tuple[EvidenceReference, ...],
    counter_evidence: tuple[EvidenceReference, ...],
) -> SensitivityResponse | None:
    baseline = _decimal(perturbation.baseline_value)
    perturbed = _decimal(perturbation.perturbed_value)
    if baseline is None or perturbed is None or not counter_evidence:
        return None
    denominator = max(abs(baseline), Decimal(1))
    effect = abs(perturbed - baseline) / denominator
    response = float(effect)
    lower = max(Decimal(0), effect * Decimal("0.9"))
    upper = effect * Decimal("1.1")
    perturbation_evidence = list(evidence) + list(perturbation.evidence)
    if perturbation.alternative_prior is not None:
        perturbation_evidence.append(
            EvidenceReference(
                reference=perturbation.alternative_prior,
                role="evidence",
                claim="Caller-declared alternative prior for sensitivity stress testing.",
            )
        )
    if perturbation.assay_artifact is not None:
        perturbation_evidence.append(
            EvidenceReference(
                reference=perturbation.assay_artifact,
                role="evidence",
                claim="Caller-declared assay perturbation artifact.",
            )
        )
    return SensitivityResponse(
        scenario_id=perturbation.perturbation_id,
        status=PerturbationResponseStatus.BOUNDED,
        response_value=response,
        lower_bound=float(lower),
        upper_bound=float(upper),
        assumptions=(
            (
                "The locked configuration and caller-declared numeric perturbation values "
                "are treated as opaque evidence."
            ),
            (
                "The response is a deterministic sensitivity magnitude, not a treatment "
                "recommendation."
            ),
        ),
        counter_evidence=counter_evidence,
        evidence=tuple(perturbation_evidence[:64]),
    )


class M1406TypedInferenceError(ValueError):
    """Raised when typed glioma perturbations cannot be fitted safely."""


def _typed_surface(  # noqa: C901 - explicit solver, bootstrap, and ablation stages are auditable.
    request: SimulateProteinSubtypePerturbationsRequest,
    request_digest: str,
    *,
    evidence: tuple[EvidenceReference, ...],
    counter_evidence: tuple[EvidenceReference, ...],
) -> SensitivitySurface:
    terms = _typed_terms(request.perturbations)
    if not terms:
        raise M1406TypedInferenceError(  # noqa: TRY003
            "typed perturbation requires at least one observed or left-censored measurement; "
            "missing or unsupported evidence is excluded"
        )
    active_ids = {term.scenario_id for term in terms}
    if active_ids != {item.perturbation_id for item in request.perturbations}:
        raise M1406TypedInferenceError(  # noqa: TRY003
            "missing or unsupported typed perturbations are excluded; a complete evaluable "
            "surface is required for publication"
        )
    fit = _fit_typed(terms)
    if not fit.converged:
        raise M1406TypedInferenceError("typed perturbation solver did not converge")  # noqa: TRY003
    topology_free = _fit_typed(terms, include_edges=False)
    if not topology_free.converged:
        raise M1406TypedInferenceError("typed perturbation ablation solver did not converge")  # noqa: TRY003
    measurement_free = _fit_typed((), include_edges=True)
    if not measurement_free.converged:
        raise M1406TypedInferenceError("typed measurement ablation solver did not converge")  # noqa: TRY003
    replicates = request.configuration.bootstrap_replicates
    draws: list[tuple[float, ...]] = []
    for draw in range(replicates):
        perturbed = tuple(
            _TypedTerm(
                scenario_id=term.scenario_id,
                program=term.program,
                state=term.state,
                delta=max(
                    -M1406_MAX_EFFECT,
                    min(
                        M1406_MAX_EFFECT,
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
            raise M1406TypedInferenceError(  # noqa: TRY003
                "typed perturbation bootstrap solver did not converge"
            )
        draws.append(draw_fit.values)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    responses: list[SensitivityResponse] = []
    for scenario in request.perturbations:
        if scenario.program is None:  # guarded by active_ids above
            raise M1406TypedInferenceError("typed perturbation has no program")  # noqa: TRY003
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
        topology_delta = fit.values[position] - topology_free.values[position]
        measurement_delta = fit.values[position] - measurement_free.values[position]
        base_response = _response(
            scenario,
            evidence=evidence,
            counter_evidence=counter_evidence,
        )
        if base_response is None:
            raise M1406TypedInferenceError("typed perturbation response is not finite")  # noqa: TRY003
        response = base_response.model_copy(
            update={
                "response_value": fit.values[position],
                "lower_bound": lower,
                "upper_bound": upper,
                "stability": _quantize(max(0.0, min(1.0, 1.0 - width / (2.0 * M1406_MAX_EFFECT)))),
                "discordance": _quantize(min(1.0, abs(topology_delta))),
                "top_drivers": drivers,
                "ablation_effects": (
                    f"measurement_ablation_delta={_quantize(measurement_delta):.8f}",
                    f"topology_ablation_delta={_quantize(topology_delta):.8f}",
                    f"measurement_quality={_quantize(scenario.quality_weight):.8f}",
                ),
                "assumptions": (
                    "Typed effects are fitted with robust Huber loss, ridge regularization, "
                    "and signed glioma program coupling.",
                    "Bootstrap intervals quantify measurement sensitivity and are not causal "
                    "or treatment effect probabilities.",
                ),
            }
        )
        responses.append(response)
    if not responses:
        raise M1406TypedInferenceError("typed perturbation has no evaluable scenarios")  # noqa: TRY003
    return SensitivitySurface(
        surface_id=f"surface.m1406.{request_digest.removeprefix('sha256:')}",
        version=M1406_CONTRACT_VERSION,
        baseline_result=request.upstream_result,
        perturbations=request.perturbations,
        responses=tuple(responses),
        configuration=request.configuration,
        evidence=tuple((*evidence, *counter_evidence)[:64]),
        typed_model=True,
        solver_iterations=fit.iterations,
        solver_objective=fit.objective,
        solver_max_update=fit.max_update,
        objective_trace_digest=_typed_trace_digest(fit),
    )


def _limitations(*, supported: bool, typed: bool = False) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Artifact references are immutable and are never traversed by this runtime.",
        ),
        Limitation(
            code="counter_evidence_preserved",
            statement=(
                "Assumptions, alternative priors, assay references, and counter-evidence "
                "remain attached."
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
                statement=(
                    "No sensitivity response is published outside the closed numeric "
                    "support domain."
                ),
            )
        )
    if typed:
        values.extend(
            (
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
                        "Program perturbation intervals are research-use-only and are not "
                        "causal, clinical, or treatment recommendations."
                    ),
                ),
            )
        )
    return tuple(values)


class M1406SensitivityEngine:
    """Simulate caller-declared perturbations with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinSubtypeSensitivitySimulationResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: SimulateProteinSubtypePerturbationsRequest
    ) -> ProteinSubtypeSensitivitySimulationResult:
        request_hash = canonical_request_digest(request)
        evidence = _all_evidence(request)
        counter_evidence = _counter_evidence(request)
        supported = request.configuration.model_family in _SUPPORTED_FAMILIES
        typed_requested = _has_typed_fields(request.perturbations)
        responses: list[SensitivityResponse] = []
        typed_surface: SensitivitySurface | None = None
        failure_code: SensitivityFindingCode | None = None
        failure_message: str | None = None
        if len(request.perturbations) > request.configuration.maximum_scenarios:
            supported = False
            failure_code = SensitivityFindingCode.INPUT_INCOMPLETE
            failure_message = "Perturbation count exceeds the locked scenario budget."
        elif not supported:
            failure_code = SensitivityFindingCode.METHOD_OUTSIDE_SUPPORT
            failure_message = "Model family is outside the declared deterministic support domain."
        elif typed_requested:
            try:
                typed_surface = _typed_surface(
                    request,
                    request_hash,
                    evidence=evidence,
                    counter_evidence=counter_evidence,
                )
                responses = list(typed_surface.responses)
            except ValueError as error:
                supported = False
                failure_code = SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE
                failure_message = str(error)
        else:
            for perturbation in request.perturbations:
                response = _response(
                    perturbation,
                    evidence=evidence,
                    counter_evidence=counter_evidence,
                )
                if response is None:
                    supported = False
                    failure_code = SensitivityFindingCode.RESPONSE_OUT_OF_ENVELOPE
                    failure_message = (
                        "Perturbation values are missing, non-finite, unsupported, or "
                        "lack counter-evidence."
                    )
                    break
                responses.append(response)
        if supported:
            surface = typed_surface or SensitivitySurface(
                surface_id=f"surface.{request_hash.removeprefix('sha256:')}",
                version=M1406_CONTRACT_VERSION,
                baseline_result=request.upstream_result,
                perturbations=request.perturbations,
                responses=tuple(responses),
                configuration=request.configuration,
                evidence=evidence,
            )
            diagnostics = tuple(
                SensitivityDiagnostic(
                    diagnostic_id=f"diagnostic.{item.scenario_id}",
                    status=SensitivityDiagnosticStatus.PASS,
                    message=(
                        "Perturbation response is finite, bounded, and counter-evidence attached."
                    ),
                    evidence=item.evidence,
                )
                for item in responses
            )
            findings: tuple[SensitivityFindingCode, ...] = ()
            abstention_reason = None
        else:
            surface = None
            code = failure_code or SensitivityFindingCode.INPUT_INCOMPLETE
            message = failure_message or "Sensitivity simulation was not safely evaluable."
            diagnostics = (
                SensitivityDiagnostic(
                    diagnostic_id=f"diagnostic.{request.request_id}",
                    status=SensitivityDiagnosticStatus.NOT_EVALUABLE,
                    message=message,
                    evidence=evidence,
                ),
            )
            findings = (code,)
            abstention_reason = message
        payload: dict[str, object] = {
            "output_type": "protein_subtype_sensitivity_surface",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1406_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": SensitivitySimulationStatus.SIMULATED
            if supported
            else SensitivitySimulationStatus.ABSTAINED,
            "surface": surface,
            "diagnostics": diagnostics,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": M1406_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="m1406_sensitivity_simulation_review_required"
                if supported
                else "m1406_sensitivity_abstained",
                rationale=(
                    "All locked perturbations are finite and bounded with counter-evidence."
                    if supported
                    else "The request is outside the safely evaluable perturbation support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=typed_requested and supported),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=supported, typed=typed_requested),
            "human_review_required": True,
        }
        constructed = ProteinSubtypeSensitivitySimulationResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeSensitivitySimulationResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1406ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1406ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1406ReplayVerificationError
        return validated


def simulate_protein_subtype_perturbations(
    request: object,
) -> ProteinSubtypeSensitivitySimulationResult:
    """Public provisional M14-06 operation."""

    return M1406SensitivityEngine().infer(request)


__all__ = [
    "M1406ReplayVerificationError",
    "M1406SensitivityAuthorizationError",
    "M1406SensitivityEngine",
    "preflight_sensitivity_authorization",
    "result_payload_digest",
    "simulate_protein_subtype_perturbations",
]
