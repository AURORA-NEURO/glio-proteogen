"""Deterministic, replay-bound M14-04 mechanism inference runtime.

The dossier does not freeze an implementation ABI.  This runtime therefore
accepts only an explicit, documented caller-declared method grammar.  It never
opens artifact references, infers identity or consent, or treats an unknown
method as a negative biological finding.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_04 import (
    M1404_CONTRACT_VERSION,
    M1404_EVIDENCE_CLAIM,
    M1404_MAX_EFFECT,
    M1404_PARENT,
    GliomaMechanismProgram,
    InferProteinSubtypeMechanismRequest,
    MechanismEstimate,
    MechanismEstimateKind,
    MechanismEvidenceState,
    MechanismFinding,
    MechanismFindingCode,
    MechanismInferenceStatus,
    MechanismObservation,
    ProteinSubtypeMechanismInferenceResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m14_04.canonical import (
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

_REQUEST_ADAPTER: Final = TypeAdapter(InferProteinSubtypeMechanismRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeMechanismInferenceResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_SUPPORTED_METHODS: Final = frozenset({"posterior", "state"})
_ABSTAIN_METHODS: Final = frozenset({"abstain", "unsupported", "not_calibrated"})
_SUPPORTED_STATES: Final = frozenset(
    {"active", "inactive", "present", "absent", "upregulated", "downregulated", "stable"}
)
_POSTERIOR_PARTS: Final = 6
_STATE_PARTS: Final = 4
_HUBER_DELTA: Final = 1.5
_DAMPING: Final = 0.7
_RIDGE: Final = 0.03
_EDGE_STRENGTH: Final = 0.45
_SOLVER_ITERATIONS: Final = 160
_SOLVER_TOLERANCE: Final = 1e-4
_OBJECTIVE_TOLERANCE: Final = 1e-10
_BACKTRACKING_STEPS: Final = 18
_BACKTRACKING_FACTOR: Final = 0.5
_MIN_SCALE: Final = 1e-6
_BOOTSTRAP_LOW: Final = 0.05
_BOOTSTRAP_HIGH: Final = 0.95
_ACTIVE_THRESHOLD: Final = 0.6
_INACTIVE_THRESHOLD: Final = 0.4
_PROGRAM_ORDER: Final = tuple(GliomaMechanismProgram)
_PROGRAM_EDGES: Final = (
    (GliomaMechanismProgram.RTK_PI3K_AKT_MTOR, GliomaMechanismProgram.PROLIFERATION, 1.0),
    (GliomaMechanismProgram.P53_CELL_CYCLE, GliomaMechanismProgram.PROLIFERATION, -1.0),
    (GliomaMechanismProgram.IDH_HIF1A, GliomaMechanismProgram.MESENCHYMAL_PROGRAM, -1.0),
    (GliomaMechanismProgram.RTK_PI3K_AKT_MTOR, GliomaMechanismProgram.MESENCHYMAL_PROGRAM, 1.0),
    (GliomaMechanismProgram.MESENCHYMAL_PROGRAM, GliomaMechanismProgram.PROLIFERATION, 1.0),
)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    observation_id: str
    program: GliomaMechanismProgram
    state: MechanismEvidenceState
    effect: float
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


class M1404MechanismAuthorizationError(PermissionError):
    """Caller-owned controls do not authorize mechanism inference."""

    def __init__(self) -> None:
        super().__init__(
            "M14-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1404ReplayVerificationError(ValueError):
    """A mechanism result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-04 replay verification failed")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_mechanism_authorization(candidate: object) -> None:
    """Check seven controls before any opaque artifact or method traversal."""

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
        raise M1404MechanismAuthorizationError from None
    if states != expected:
        raise M1404MechanismAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_mechanism_authorization(candidate)
    return candidate


def _evidence(request: InferProteinSubtypeMechanismRequest) -> tuple[KernelEvidenceReference, ...]:
    refs = request.context.references
    artifacts = (
        request.hypothesis_registry_result,
        *request.source_artifacts,
        request.configuration.model_reference,
        request.configuration.calibration_reference,
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
        KernelEvidenceReference(reference=artifact, role="evidence", claim=M1404_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:64]
    )


def _counter_evidence(
    request: InferProteinSubtypeMechanismRequest,
) -> tuple[KernelEvidenceReference, ...]:
    # The references are caller-declared and are deliberately not opened.
    return tuple(
        KernelEvidenceReference(
            reference=artifact,
            role="counter_evidence",
            claim="Caller-declared counter-evidence; issuer authority is not authenticated.",
        )
        for artifact in request.source_artifacts[:64]
    )


def _decimal(value: str) -> float:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("mechanism probability is not numeric") from error  # noqa: TRY003
    if not number.is_finite() or not 0 <= number <= 1:
        raise ValueError(  # noqa: TRY003
            "mechanism probability must be finite and within [0, 1]"
        )
    return float(number)


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


def _typed_terms(observations: tuple[MechanismObservation, ...]) -> tuple[_TypedTerm, ...]:
    active = {
        MechanismEvidenceState.OBSERVED,
        MechanismEvidenceState.LEFT_CENSORED,
    }
    terms = [
        _TypedTerm(
            observation_id=item.observation_id,
            program=item.program,
            state=item.evidence_state,
            effect=item.standardized_effect if item.standardized_effect is not None else 0.0,
            standard_error=item.standard_error if item.standard_error is not None else 1.0,
            quality_weight=item.quality_weight,
        )
        for item in observations
        if item.evidence_state in active
    ]
    return tuple(sorted(terms, key=lambda item: (item.program.value, item.observation_id)))


def _typed_objective(
    values: list[float], terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        residual = (
            max(0.0, values[index[term.program]] - term.effect)
            if term.state is MechanismEvidenceState.LEFT_CENSORED
            else values[index[term.program]] - term.effect
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    if include_edges:
        for source, target, sign in _PROGRAM_EDGES:
            residual = values[index[target]] - sign * _EDGE_STRENGTH * values[index[source]]
            objective += _huber_loss(residual)
    return objective


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
            term.effect
            for term in program_terms
            if term.state is MechanismEvidenceState.LEFT_CENSORED
        )
        if observed:
            total = sum(term.quality_weight for term in observed)
            center = sum(term.quality_weight * term.effect for term in observed) / max(
                _MIN_SCALE, total
            )
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index[program]] = max(-M1404_MAX_EFFECT, min(M1404_MAX_EFFECT, initial))
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    terms: tuple[_TypedTerm, ...], *, include_edges: bool = True
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaMechanismProgram, list[_TypedTerm]] = defaultdict(list)
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
    trace = [_quantize(initial_objective)]
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
                    and current <= term.effect
                ):
                    continue
                residual = (
                    max(0.0, current - term.effect)
                    if term.state is MechanismEvidenceState.LEFT_CENSORED
                    else current - term.effect
                ) / max(_MIN_SCALE, term.standard_error)
                information = (
                    term.quality_weight
                    * _huber_weight(residual)
                    / max(_MIN_SCALE, term.standard_error**2)
                )
                gradient += information * (current - term.effect)
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
                -M1404_MAX_EFFECT,
                min(M1404_MAX_EFFECT, current + _DAMPING * (proposal - current)),
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
                    max(
                        -M1404_MAX_EFFECT,
                        min(M1404_MAX_EFFECT, before + step * change),
                    )
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
        trace.append(_quantize(objective))
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


def _sigmoid(value: float) -> float:
    bounded = max(-40.0, min(40.0, value))
    return 1.0 / (1.0 + math.exp(-bounded))


def _parse_method(  # noqa: PLR0911
    method: str,
    *,
    counter_evidence: tuple[KernelEvidenceReference, ...],
    evidence: tuple[KernelEvidenceReference, ...],
) -> tuple[MechanismEstimate | None, MechanismFindingCode | None, str | None]:
    """Parse only the explicit provisional method grammar.

    ``posterior:mechanism-id:label:probability:lower:upper`` and
    ``state:mechanism-id:label:state`` are the only evaluable forms.  Labels
    and IDs cannot contain colons.  ``abstain:<reason>`` is an explicit safe
    failure path.
    """

    parts = method.split(":")
    kind = parts[0].lower() if parts else ""
    if kind in _ABSTAIN_METHODS:
        return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "Caller requested safe abstention."
    if kind not in _SUPPORTED_METHODS:
        return (
            None,
            MechanismFindingCode.MODEL_NOT_CALIBRATED,
            "Method is outside the closed grammar.",
        )
    if kind == "posterior":
        if len(parts) != _POSTERIOR_PARTS:
            return (
                None,
                MechanismFindingCode.MODEL_NOT_CALIBRATED,
                "Posterior method shape is invalid.",
            )
        mechanism_id, label = parts[1], parts[2]
        try:
            probability, lower, upper = (_decimal(value) for value in parts[3:])
        except ValueError:
            return (
                None,
                MechanismFindingCode.MODEL_NOT_CALIBRATED,
                "Posterior probability is invalid.",
            )
        if not mechanism_id or not label or lower > upper or not lower <= probability <= upper:
            return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "Posterior bounds are invalid."
        return (
            MechanismEstimate(
                estimate_id=f"estimate.{mechanism_id}",
                mechanism_id=mechanism_id,
                label=label,
                kind=MechanismEstimateKind.POSTERIOR,
                posterior_probability=probability,
                lower_bound=lower,
                upper_bound=upper,
                assumptions=(
                    "The approved model and calibration references are caller-declared.",
                    "The upstream variant-peptide hypothesis result is treated as opaque evidence.",
                ),
                alternatives=(
                    "Alternative mechanisms remain possible and require independent evidence.",
                ),
                counter_evidence=counter_evidence,
                evidence=evidence,
            ),
            None,
            None,
        )
    if len(parts) != _STATE_PARTS:
        return None, MechanismFindingCode.MODEL_NOT_CALIBRATED, "State method shape is invalid."
    mechanism_id, label, state_value = parts[1], parts[2], parts[3].lower()
    if not mechanism_id or not label or state_value not in _SUPPORTED_STATES:
        return (
            None,
            MechanismFindingCode.MODEL_NOT_CALIBRATED,
            "State value is outside the closed vocabulary.",
        )
    return (
        MechanismEstimate(
            estimate_id=f"estimate.{mechanism_id}",
            mechanism_id=mechanism_id,
            label=label,
            kind=MechanismEstimateKind.STATE,
            state_value=state_value,
            assumptions=(
                "The approved model and calibration references are caller-declared.",
                "The upstream variant-peptide hypothesis result is treated as opaque evidence.",
            ),
            alternatives=(
                "Alternative mechanisms remain possible and require independent evidence.",
            ),
            counter_evidence=counter_evidence,
            evidence=evidence,
        ),
        None,
        None,
    )


class M1404TypedInferenceError(ValueError):
    """Raised when typed glioma network evidence cannot be fitted safely."""


def _typed_estimates(
    request: InferProteinSubtypeMechanismRequest,
    *,
    evidence: tuple[KernelEvidenceReference, ...],
    counter_evidence: tuple[KernelEvidenceReference, ...],
    request_digest: str,
) -> tuple[tuple[MechanismEstimate, ...], _TypedFit]:
    terms = _typed_terms(request.observations)
    if not terms:
        raise M1404TypedInferenceError(  # noqa: TRY003
            "typed network inference requires observed or left-censored evidence"
        )
    fit = _fit_typed(terms)
    if not fit.converged:
        raise M1404TypedInferenceError("typed network solver did not converge")  # noqa: TRY003
    topology_free = _fit_typed(terms, include_edges=False)
    if not topology_free.converged:
        raise M1404TypedInferenceError(  # noqa: TRY003
            "typed network topology ablation did not converge"
        )
    measurement_free = _fit_typed((), include_edges=True)
    if not measurement_free.converged:
        raise M1404TypedInferenceError(  # noqa: TRY003
            "typed network measurement ablation did not converge"
        )
    draws: list[tuple[float, ...]] = []
    for draw in range(request.configuration.bootstrap_replicates):
        perturbed = tuple(
            _TypedTerm(
                observation_id=term.observation_id,
                program=term.program,
                state=term.state,
                effect=max(
                    -M1404_MAX_EFFECT,
                    min(
                        M1404_MAX_EFFECT,
                        term.effect
                        + 0.5
                        * term.standard_error
                        * _hash_normal(f"{request_digest}:{draw}:{term.observation_id}"),
                    ),
                ),
                standard_error=term.standard_error,
                quality_weight=term.quality_weight,
            )
            for term in terms
        )
        draw_fit = _fit_typed(perturbed)
        if not draw_fit.converged:
            raise M1404TypedInferenceError(  # noqa: TRY003
                "typed network bootstrap solver did not converge"
            )
        draws.append(draw_fit.values)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaMechanismProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    drivers = tuple(
        program.value
        for program, value in sorted(
            zip(_PROGRAM_ORDER, fit.values, strict=True),
            key=lambda pair: (-abs(pair[1]), pair[0].value),
        )[:3]
    )
    estimates: list[MechanismEstimate] = []
    for program in _PROGRAM_ORDER:
        position = index[program]
        samples = tuple(_sigmoid(draw[position]) for draw in draws)
        center = _quantize(_sigmoid(fit.values[position]))
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), center)
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), center)
        state: Literal["active", "inactive", "stable"] = (
            "active"
            if lower > _ACTIVE_THRESHOLD
            else "inactive"
            if upper < _INACTIVE_THRESHOLD
            else "stable"
        )
        width = max(_MIN_SCALE, upper - lower)
        topology_delta = fit.values[position] - topology_free.values[position]
        measurement_delta = fit.values[position] - measurement_free.values[position]
        mean_quality = _quantize(
            sum(item.quality_weight for item in grouped[program])
            / max(1, len(grouped[program]))
        )
        estimates.append(
            MechanismEstimate(
                estimate_id=f"estimate.glioma.{program.value.lower()}",
                mechanism_id=f"mechanism.glioma.{program.value.lower()}",
                label=program.value.replace("_", " ").title(),
                kind=MechanismEstimateKind.POSTERIOR,
                posterior_probability=center,
                lower_bound=lower,
                upper_bound=upper,
                state_value=None,
                classification=state,
                assumptions=(
                    "Typed protein/PTM effects are fitted with robust Huber loss, ridge "
                    "regularization, and signed glioma network coupling.",
                    "Posterior-like values are calibrated only as bounded research scores, "
                    "not clinical probabilities.",
                ),
                alternatives=(
                    "Alternative mechanisms and unmeasured network edges remain possible.",
                ),
                counter_evidence=counter_evidence,
                evidence=evidence,
                standardized_effect=fit.values[position],
                effect_lower_bound=_quantile(
                    tuple(draw[position] for draw in draws), _BOOTSTRAP_LOW
                ),
                effect_upper_bound=_quantile(
                    tuple(draw[position] for draw in draws), _BOOTSTRAP_HIGH
                ),
                stability=_quantize(max(0.0, min(1.0, 1.0 - width))),
                discordance=_quantize(min(1.0, abs(topology_delta))),
                evidence_count=len(grouped[program]),
                top_drivers=drivers,
                ablation_effects=(
                    f"measurement_ablation_delta={_quantize(measurement_delta):.8f}",
                    f"topology_ablation_delta={_quantize(topology_delta):.8f}",
                    f"mean_measurement_quality={mean_quality:.8f}",
                ),
            )
        )
    return tuple(estimates), fit


def _limitations(*, supported: bool, typed: bool = False) -> tuple[Limitation, ...]:
    values = [
        Limitation(
            code="opaque_inputs",
            statement="Artifact references are immutable and are never traversed by this runtime.",
        ),
        Limitation(
            code="counter_evidence_preserved",
            statement=(
                "Assumptions, alternatives, and counter-evidence remain attached to every estimate."
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
                statement="No mechanism estimate is published outside the closed method grammar.",
            )
        )
    if typed:
        values.extend(
            (
                Limitation(
                    code="typed_glioma_network_model",
                    statement=(
                        "Typed estimates use a signed glioma program graph with robust "
                        "coordinate descent and deterministic bootstrap intervals."
                    ),
                ),
                Limitation(
                    code="research_use_only",
                    statement=(
                        "Network mechanism scores are research-use-only and are not causal, "
                        "clinical, prognostic, or treatment claims."
                    ),
                ),
            )
        )
    return tuple(values)


class M1404MechanismEngine:
    """Infer a caller-declared mechanism estimate with deterministic replay."""

    __slots__ = ()

    def infer(self, request: object) -> ProteinSubtypeMechanismInferenceResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self, request: InferProteinSubtypeMechanismRequest
    ) -> ProteinSubtypeMechanismInferenceResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        counter_evidence = _counter_evidence(request)
        typed_model = bool(request.observations)
        typed_fit: _TypedFit | None = None
        finding_code: MechanismFindingCode | None = None
        finding_message: str | None = None
        if typed_model:
            try:
                estimates, typed_fit = _typed_estimates(
                    request,
                    evidence=evidence,
                    counter_evidence=counter_evidence,
                    request_digest=request_hash,
                )
                safe = bool(counter_evidence)
                if not safe:
                    finding_code = MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED
                    finding_message = "At least one counter-evidence reference is required."
            except ValueError as error:
                estimates = ()
                safe = False
                finding_code = MechanismFindingCode.MODEL_NOT_CALIBRATED
                finding_message = str(error)
        else:
            estimate, finding_code, finding_message = _parse_method(
                request.configuration.method,
                counter_evidence=counter_evidence,
                evidence=evidence,
            )
            safe = estimate is not None and bool(counter_evidence)
            if estimate is None:
                safe = False
                finding_code = finding_code or MechanismFindingCode.MODEL_NOT_CALIBRATED
                finding_message = finding_message or "Mechanism estimate is not evaluable."
            elif not counter_evidence:
                safe = False
                finding_code = MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED
                finding_message = "At least one counter-evidence reference is required."
            estimates = (estimate,) if safe and estimate is not None else ()
        findings = (
            ()
            if safe
            else (
                MechanismFinding(
                    finding_id=f"finding.{request.request_id}",
                    code=finding_code or MechanismFindingCode.COUNTER_EVIDENCE_REQUIRED,
                    message=finding_message or "Mechanism inference abstained.",
                    evidence=evidence,
                ),
            )
        )
        payload: dict[str, object] = {
            "output_type": "protein_subtype_mechanism_inference",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1404_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": MechanismInferenceStatus.INFERRED
            if safe
            else MechanismInferenceStatus.ABSTAINED,
            "estimates": estimates,
            "findings": findings,
            "abstention_reason": None
            if safe
            else (finding_message or "Mechanism inference abstained."),
            "parent_target": M1404_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED if safe else SupportStatus.UNSUPPORTED,
                reason_code=(
                    "m1404_provisional_mechanism_review_required"
                    if safe
                    else "m1404_mechanism_abstained"
                ),
                rationale=(
                    "Explicit posterior/state method, bounds, calibration references, and "
                    "counter-evidence passed."
                    if safe
                    else "The mechanism request is outside the safely evaluable support domain."
                ),
            ),
            "uncertainty": expected_uncertainty(supported=typed_model and safe),
            "provenance": expected_provenance(request, request_hash),
            "evidence": evidence,
            "limitations": _limitations(supported=safe, typed=typed_model),
            "human_review_required": True if safe else not safe,
            "typed_model": typed_model,
            "solver_iterations": typed_fit.iterations if typed_fit is not None else None,
            "solver_objective": typed_fit.objective if typed_fit is not None else None,
            "solver_max_update": typed_fit.max_update if typed_fit is not None else None,
            "objective_trace_digest": (
                _typed_trace_digest(typed_fit) if typed_fit is not None else None
            ),
        }
        constructed = ProteinSubtypeMechanismInferenceResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanismInferenceResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1404ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1404ReplayVerificationError
        if replay:
            expected = self.infer(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1404ReplayVerificationError
        return validated


def infer_protein_subtype_mechanism(
    request: object,
) -> ProteinSubtypeMechanismInferenceResult:
    """Public provisional M14-04 operation."""

    return M1404MechanismEngine().infer(request)


__all__ = [
    "M1404MechanismAuthorizationError",
    "M1404MechanismEngine",
    "M1404ReplayVerificationError",
    "infer_protein_subtype_mechanism",
    "preflight_mechanism_authorization",
    "result_payload_digest",
]
