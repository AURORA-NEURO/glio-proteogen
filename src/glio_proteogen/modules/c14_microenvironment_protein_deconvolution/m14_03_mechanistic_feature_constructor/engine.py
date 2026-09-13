"""Deterministic, replay-bound M14-03 mechanistic feature construction.

Typed requests use a glioma microenvironment program graph with robust signed
effect fitting and deterministic intervals. The original categorical feature
path remains compatibility-only; opaque artifacts are never traversed and
unsupported inputs still close as explicit abstentions.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter

from glio_proteogen.contracts.m14_03 import (
    M1403_CONTRACT_VERSION,
    M1403_EVIDENCE_CLAIM,
    M1403_MAX_EFFECT,
    M1403_MODULE_ID,
    M1403_PARENT,
    ConstructProteinSubtypeMechanisticFeaturesRequest,
    GliomaMicroenvironmentProgram,
    MechanisticConstructionStatus,
    MechanisticDiagnosticStatus,
    MechanisticEvidenceState,
    MechanisticFeature,
    MechanisticFeatureDiagnostic,
    MechanisticFeatureKind,
    MechanisticFeatureLineage,
    MechanisticFeatureObject,
    MechanisticFindingCode,
    MechanisticRelation,
    MechanisticRelationKind,
    MechanisticTypedObservation,
    MechanisticValueKind,
    ProteinSubtypeMechanisticFeatureResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructProteinSubtypeMechanisticFeaturesRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeMechanisticFeatureResult)
_EXPECTED_CONTROLS: Final = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_SUPPORTED_MODEL_FAMILIES: Final = frozenset(
    {"caller_declared_feature_replay", "deterministic_metadata_replay"}
)
_FEATURE_KINDS: Final = tuple(MechanisticFeatureKind)
_LIMITATIONS: Final = (
    Limitation(
        code="opaque_references",
        statement=(
            "Source and upstream artifacts are immutable references; this module never reads "
            "their bytes."
        ),
    ),
    Limitation(
        code="no_mechanistic_inference",
        statement=(
            "Categorical feature records preserve caller declarations and do not infer "
            "biological mechanism."
        ),
    ),
    Limitation(
        code="provisional_abi",
        statement=(
            "The public ABI remains provisional pending Platform engineering confirmation "
            "of the dossier slice."
        ),
    ),
)
_TYPED_LIMITATIONS: Final = (
    *_LIMITATIONS,
    Limitation(
        code="typed_glioma_microenvironment_graph",
        statement=(
            "Typed observations are fit against a fixed signed microenvironment program graph; "
            "the lane is experimental and research-use-only."
        ),
    ),
    Limitation(
        code="no_clinical_interpretation",
        statement=(
            "Intervals and directional labels are not diagnostic, prognostic, or treatment "
            "recommendations."
        ),
    ),
)
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
_PROGRAM_ORDER: Final = tuple(GliomaMicroenvironmentProgram)
_PROGRAM_EDGES: Final = (
    (
        GliomaMicroenvironmentProgram.HYPOXIA,
        GliomaMicroenvironmentProgram.ANGIOGENIC,
        1.0,
    ),
    (
        GliomaMicroenvironmentProgram.HYPOXIA,
        GliomaMicroenvironmentProgram.MESENCHYMAL,
        1.0,
    ),
    (
        GliomaMicroenvironmentProgram.MESENCHYMAL,
        GliomaMicroenvironmentProgram.MYELOID,
        1.0,
    ),
    (
        GliomaMicroenvironmentProgram.MYELOID,
        GliomaMicroenvironmentProgram.T_CELL,
        -1.0,
    ),
    (
        GliomaMicroenvironmentProgram.OPC_LIKE,
        GliomaMicroenvironmentProgram.MESENCHYMAL,
        -1.0,
    ),
)


@dataclass(frozen=True, slots=True)
class _TypedTerm:
    observation_id: str
    program: GliomaMicroenvironmentProgram
    state: MechanisticEvidenceState
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


class M1403AuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for feature construction."""

    def __init__(self) -> None:
        super().__init__(
            "M14-03 requires accepted controls, resolved identity, and granted consent"
        )


class M1403ReplayVerificationError(ValueError):
    """A feature result cannot be reconstructed from its exact request."""

    def __init__(self) -> None:
        super().__init__("M14-03 replay verification failed")


class _InvalidRequestError(TypeError):
    def __init__(self) -> None:
        super().__init__("M14-03 request must be a strict request model or mapping")


class _UnsupportedConfigurationError(ValueError):
    def __init__(self) -> None:
        super().__init__("unsupported M14-03 model family")


class _DuplicateNegativeControlError(ValueError):
    def __init__(self) -> None:
        super().__init__("negative control references must be unique")


class _TypedInferenceError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class _TypedEvidenceAbsentError(_TypedInferenceError):
    def __init__(self) -> None:
        super().__init__("typed M14-03 evidence has no supported observations")


class _TypedSolverNonConvergenceError(_TypedInferenceError):
    def __init__(self) -> None:
        super().__init__("typed M14-03 solver did not converge")


class _TypedBootstrapNonConvergenceError(_TypedInferenceError):
    def __init__(self) -> None:
        super().__init__("typed M14-03 bootstrap solver did not converge")


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m1403_authorization(candidate: object) -> None:
    """Check all seven controls before traversing feature configuration."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        states = {
            role: _state(_member(_member(references, role), "state"))
            for role in _EXPECTED_CONTROLS
        }
    except Exception as error:
        raise M1403AuthorizationError from error
    if states != _EXPECTED_CONTROLS:
        raise M1403AuthorizationError


def _as_request(candidate: object) -> ConstructProteinSubtypeMechanisticFeaturesRequest:
    preflight_m1403_authorization(candidate)
    if type(candidate) is ConstructProteinSubtypeMechanisticFeaturesRequest:
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if isinstance(candidate, Mapping):
        return _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    raise _InvalidRequestError


def _evidence(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
) -> tuple[EvidenceReference, ...]:
    references = (
        *request.source_artifacts,
        request.upstream_result,
        request.configuration.stoichiometry_reference,
        *request.configuration.negative_control_artifacts,
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
        EvidenceReference(reference=reference, role="evidence", claim=M1403_EVIDENCE_CLAIM)
        for reference in unique
    )


def _controls(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
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
        estimated = {
            "measurement": (
                "Estimated from supplied standard errors and quality weights; bootstrap "
                "perturbations quantify measurement sensitivity."
            ),
            "sampling": (
                "Estimated by deterministic bootstrap perturbations of the supported typed "
                "observations."
            ),
            "parameter": (
                "Estimated from the converged robust coordinate-descent fit and its bootstrap "
                "refits."
            ),
        }
        estimates: dict[str, UncertaintyEstimate] = {
            name: UncertaintyEstimate(
                state=EstimateState.ESTIMATED,
                probability=0.9,
                rationale=reason,
            )
            for name, reason in estimated.items()
        }
        estimates.update(
            {
                "model_form": UncertaintyEstimate(
                    state=EstimateState.NOT_ESTIMABLE,
                    rationale="External model-form uncertainty is not calibrated in this lane.",
                ),
                "identification": UncertaintyEstimate(
                    state=EstimateState.NOT_APPLICABLE,
                    rationale="Program identifiers are supplied by the typed request.",
                ),
                "support": UncertaintyEstimate(
                    state=EstimateState.NOT_ESTIMABLE,
                    rationale="Evidence issuer authenticity remains outside this boundary.",
                ),
                "transport": UncertaintyEstimate(
                    state=EstimateState.NOT_ESTIMABLE,
                    rationale="Cross-cohort and cross-assay transport is not calibrated.",
                ),
            }
        )
        return UncertaintyProfile(
            **estimates,
            sensitivity_notes=(
                "Bootstrap intervals quantify measurement and solver sensitivity, not "
                "clinical risk.",
                "Ablation and external validation are required before scientific promotion.",
            ),
        )
    values = {
        "measurement": "No measurement values are constructed from opaque references.",
        "sampling": "Sampling coverage is not available at this metadata-only boundary.",
        "parameter": "No fitted parameters or parameter uncertainty are evaluated.",
        "model_form": "The dossier leaves model ABI open and no scientific model executes.",
        "identification": "Identity and upstream subtype identification are not inferred.",
        "support": "Support reflects caller controls and not external evidence authenticity.",
        "transport": "Transport across cohorts, assays, or conditions is not estimable.",
    }
    estimate = {
        name: UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=reason)
        for name, reason in values.items()
    }
    return UncertaintyProfile(
        **estimate,
        sensitivity_notes=(
            "Categorical declarations are replay-stable but are not quantitative "
            "feature estimates.",
            "Owner review is required before any ABI or mechanistic claim is promoted.",
        ),
    )


def _provenance(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    request_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    input_digests = (
        request.upstream_result.digest,
        *(artifact.digest for artifact in request.source_artifacts),
        request.configuration.stoichiometry_reference.digest,
        *(artifact.digest for artifact in request.configuration.negative_control_artifacts),
    )
    return ProvenanceRecord(
        activity_id=f"activity.m1403.{request_hash.removeprefix('sha256:')[:32]}",
        actor_id=request.context.actor_id,
        module_id=M1403_MODULE_ID,
        module_version=M1403_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=sha256_digest(request.configuration.model_dump(mode="json")),
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=_controls(request),
    )


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


def _quantize(value: float) -> float:
    return float(f"{value:.8f}")


def _trace_quantize(value: float) -> float:
    """Keep solver trace precision above the public eight-decimal result ABI."""

    return float(f"{value:.12f}")


def _typed_terms(
    observations: tuple[MechanisticTypedObservation, ...],
) -> tuple[_TypedTerm, ...]:
    terms: list[_TypedTerm] = []
    for observation in observations:
        if (
            observation.evidence_state
            not in {
                MechanisticEvidenceState.OBSERVED,
                MechanisticEvidenceState.LEFT_CENSORED,
            }
            or observation.standardized_effect is None
            or observation.standard_error is None
        ):
            continue
        terms.append(
            _TypedTerm(
                observation_id=observation.observation_id,
                program=observation.program,
                state=observation.evidence_state,
                effect=observation.standardized_effect,
                standard_error=observation.standard_error,
                quality_weight=observation.quality_weight,
            )
        )
    return tuple(sorted(terms, key=lambda item: (item.program.value, item.observation_id)))


def _typed_objective(values: list[float], terms: tuple[_TypedTerm, ...]) -> float:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    objective = _RIDGE * sum(value * value for value in values)
    for term in terms:
        residual = (
            max(0.0, values[index[term.program]] - term.effect)
            if term.state is MechanisticEvidenceState.LEFT_CENSORED
            else values[index[term.program]] - term.effect
        ) / max(_MIN_SCALE, term.standard_error)
        objective += term.quality_weight * _huber_loss(residual)
    for source, target, sign in _PROGRAM_EDGES:
        residual = values[index[target]] - sign * _EDGE_STRENGTH * values[index[source]]
        objective += _huber_loss(residual)
    return objective


def _initial_measurement_objective(
    center: float,
    terms: tuple[_TypedTerm, ...],
) -> float:
    """Evaluate the frozen-scale measurement objective for one program.

    Initialization is deliberately checked against the same robust loss used by
    the graph solver.  Keeping this scalar objective separate makes the
    replicate fit auditable without pretending that a per-program center has
    already incorporated signed network edges.
    """

    return float(
        sum(
            term.quality_weight
            * _huber_loss((center - term.effect) / max(_MIN_SCALE, term.standard_error))
            for term in terms
        )
    )


def _robust_initial_center(terms: tuple[_TypedTerm, ...]) -> float:
    """Find an inverse-variance Huber center for repeated program evidence.

    A quality-weighted arithmetic mean lets one failed phosphoproteomic
    replicate pull the graph start across a signed edge.  This deterministic
    IRLS center uses the supplied standard errors and quality weights, freezes
    the scale per iteration, and backtracks any proposal that would increase
    the replicate Huber objective.  The full graph fit still owns the final
    estimate; this only gives it a contamination-resistant, replay-stable
    starting point.
    """

    if len(terms) == 1:
        return terms[0].effect
    information = tuple(
        term.quality_weight / max(_MIN_SCALE, term.standard_error**2) for term in terms
    )
    denominator = max(sum(information), _MIN_SCALE)
    estimate = (
        sum(weight * term.effect for weight, term in zip(information, terms, strict=True))
        / denominator
    )
    for _ in range(_INITIAL_HUBER_ITERATIONS):
        residuals = tuple(
            (term.effect - estimate) / max(_MIN_SCALE, term.standard_error) for term in terms
        )
        robust_weights = tuple(
            weight * _huber_weight(residual)
            for weight, residual in zip(information, residuals, strict=True)
        )
        robust_denominator = max(sum(robust_weights), _MIN_SCALE)
        proposal = sum(
            weight * term.effect
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
    grouped: dict[GliomaMicroenvironmentProgram, list[_TypedTerm]],
) -> list[float]:
    """Build a feasible graph start without treating censor limits as values."""

    values = [0.0] * len(_PROGRAM_ORDER)
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    for program, program_terms in grouped.items():
        observed = tuple(
            term for term in program_terms if term.state is MechanisticEvidenceState.OBSERVED
        )
        limits = tuple(
            term.effect
            for term in program_terms
            if term.state is MechanisticEvidenceState.LEFT_CENSORED
        )
        if observed:
            center = _robust_initial_center(observed)
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index[program]] = max(-M1403_MAX_EFFECT, min(M1403_MAX_EFFECT, initial))
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    terms: tuple[_TypedTerm, ...],
) -> _TypedFit:
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    grouped: dict[GliomaMicroenvironmentProgram, list[_TypedTerm]] = defaultdict(list)
    for term in terms:
        grouped[term.program].append(term)
    values = _initial_typed_values(grouped)
    initial_objective = _typed_objective(values, terms)
    if not math.isfinite(initial_objective):
        return _TypedFit(
            values=tuple(_quantize(value) for value in values),
            converged=False,
            iterations=0,
            objective=0.0,
            max_update=0.0,
            objective_trace=(),
        )
    trace = [_trace_quantize(initial_objective)]
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
                    term.state is MechanisticEvidenceState.LEFT_CENSORED
                    and current <= term.effect
                ):
                    continue
                residual = (
                    max(0.0, current - term.effect)
                    if term.state is MechanisticEvidenceState.LEFT_CENSORED
                    else current - term.effect
                ) / max(_MIN_SCALE, term.standard_error)
                information = (
                    term.quality_weight
                    * _huber_weight(residual)
                    / max(_MIN_SCALE, term.standard_error**2)
                )
                gradient += information * (current - term.effect)
                hessian += information
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
                -M1403_MAX_EFFECT,
                min(M1403_MAX_EFFECT, current + _DAMPING * (proposal - current)),
            )
        objective = _typed_objective(proposals, terms)
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
                        -M1403_MAX_EFFECT,
                        min(M1403_MAX_EFFECT, before + step * change),
                    )
                    for before, change in zip(old, delta, strict=True)
                ]
                trial_objective = _typed_objective(trial, terms)
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
        trace.append(_trace_quantize(objective))
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


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return _quantize(ordered[index])


def _typed_trace_digest(fit: _TypedFit) -> str:
    material = ",".join(str(value) for value in fit.objective_trace)
    return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _typed_features(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[
    tuple[MechanisticFeature, ...],
    tuple[MechanisticRelation, ...],
    MechanisticFeatureDiagnostic,
]:
    terms = _typed_terms(request.typed_observations)
    if not terms:
        raise _TypedEvidenceAbsentError
    fit = _fit_typed(terms)
    if not fit.converged:
        raise _TypedSolverNonConvergenceError
    index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    draws: list[tuple[float, ...]] = []
    for draw in range(request.configuration.bootstrap_replicates):
        perturbed = tuple(
            _TypedTerm(
                observation_id=term.observation_id,
                program=term.program,
                state=term.state,
                effect=max(
                    -M1403_MAX_EFFECT,
                    min(
                        M1403_MAX_EFFECT,
                        term.effect
                        + 0.5
                        * term.standard_error
                        * _hash_normal(f"{request_hash}:{draw}:{term.observation_id}"),
                    ),
                ),
                standard_error=term.standard_error,
                quality_weight=term.quality_weight,
            )
            for term in terms
        )
        draw_fit = _fit_typed(perturbed)
        if not draw_fit.converged:
            raise _TypedBootstrapNonConvergenceError
        draws.append(draw_fit.values)
    prefix = request_hash.removeprefix("sha256:")[:12]
    features: list[MechanisticFeature] = []
    for program in _PROGRAM_ORDER:
        position = index[program]
        samples = tuple(draw[position] for draw in draws)
        lower = min(_quantile(samples, _BOOTSTRAP_LOW), fit.values[position])
        upper = max(_quantile(samples, _BOOTSTRAP_HIGH), fit.values[position])
        feature_id = f"feature.m1403.{prefix}.program.{program.value.lower()}"
        features.append(
            MechanisticFeature(
                feature_id=feature_id,
                version="0.1.0-provisional",
                kind=MechanisticFeatureKind.STATE,
                value_kind=MechanisticValueKind.INTERVAL,
                unit="standardized_effect",
                lower_bound=lower,
                upper_bound=upper,
                lineage=MechanisticFeatureLineage(
                    feature_id=feature_id,
                    source_artifacts=tuple(request.source_artifacts),
                    claim="Typed glioma microenvironment program state with signed graph support.",
                    transformation_ids=request.configuration.transformation_ids,
                    evidence=evidence[:1],
                ),
                evidence=evidence[:1],
            )
        )
    program_index = {program: position for position, program in enumerate(_PROGRAM_ORDER)}
    relations = tuple(
        MechanisticRelation(
            relation_id=f"relation.m1403.{prefix}.program.{edge_index}",
            source_feature_id=features[program_index[source]].feature_id,
            target_feature_id=features[program_index[target]].feature_id,
            kind=MechanisticRelationKind.ACTIVATES
            if sign > 0.0
            else MechanisticRelationKind.INHIBITS,
            weight=sign * _EDGE_STRENGTH,
            evidence=evidence[:1],
        )
        for edge_index, (source, target, sign) in enumerate(_PROGRAM_EDGES)
    )
    diagnostic = MechanisticFeatureDiagnostic(
        diagnostic_id=f"diagnostic.m1403.{prefix}.typed-solver",
        status=MechanisticDiagnosticStatus.PASS,
        message=(
            f"Typed glioma microenvironment solver converged in {fit.iterations} iterations; "
            f"objective={fit.objective}, max_update={fit.max_update}, "
            f"trace_digest={_typed_trace_digest(fit)}."
        ),
        evidence=evidence[:1],
    )
    return tuple(features), relations, diagnostic


def _feature_object(
    request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    evidence: tuple[EvidenceReference, ...],
    request_hash: str,
) -> tuple[MechanisticFeatureObject, tuple[MechanisticFeatureDiagnostic, ...]]:
    if request.configuration.model_family not in _SUPPORTED_MODEL_FAMILIES:
        raise _UnsupportedConfigurationError
    negative_keys = [
        (
            artifact.artifact_id,
            artifact.version,
            artifact.digest,
            artifact.media_type,
        )
        for artifact in request.configuration.negative_control_artifacts
    ]
    if len(negative_keys) != len(set(negative_keys)):
        raise _DuplicateNegativeControlError
    lineage = tuple(request.source_artifacts)
    features = tuple(
        MechanisticFeature(
            feature_id=(
                f"feature.m1403.{request_hash.removeprefix('sha256:')[:12]}.{kind.value}"
            ),
            version="0.1.0-provisional",
            kind=kind,
            value_kind=MechanisticValueKind.CATEGORICAL,
            unit="caller_declared",
            category=f"caller_declared:{kind.value}",
            lineage=MechanisticFeatureLineage(
                feature_id=(
                    f"feature.m1403.{request_hash.removeprefix('sha256:')[:12]}.{kind.value}"
                ),
                source_artifacts=lineage,
                claim=M1403_EVIDENCE_CLAIM,
                transformation_ids=request.configuration.transformation_ids,
                evidence=evidence[:1],
            ),
            evidence=evidence[:1],
        )
        for kind in _FEATURE_KINDS
    )
    relations = tuple(
        MechanisticRelation(
            relation_id=f"relation.m1403.{request_hash.removeprefix('sha256:')[:12]}.{index}",
            source_feature_id=features[index].feature_id,
            target_feature_id=features[index + 1].feature_id,
            kind=MechanisticRelationKind.PARTICIPATES,
            evidence=evidence[:1],
        )
        for index in range(len(features) - 1)
    )
    typed_features: tuple[MechanisticFeature, ...] = ()
    typed_relations: tuple[MechanisticRelation, ...] = ()
    typed_diagnostic: MechanisticFeatureDiagnostic | None = None
    if request.typed_observations:
        typed_features, typed_relations, typed_diagnostic = _typed_features(
            request, evidence, request_hash
        )
    feature_object = MechanisticFeatureObject(
        object_id=f"features.m1403.{request_hash.removeprefix('sha256:')[:32]}",
        version="0.1.0-provisional",
        features=(*features, *typed_features),
        relations=(*relations, *typed_relations),
        configuration=request.configuration,
        evidence=evidence,
    )
    diagnostics = tuple(
        MechanisticFeatureDiagnostic(
            diagnostic_id=f"diagnostic.m1403.{request_hash.removeprefix('sha256:')[:12]}.{code}",
            status=MechanisticDiagnosticStatus.PASS,
            message=message,
            evidence=evidence[:1],
        )
        for code, message in (
            ("source_closure", "All feature lineage references are caller-declared and complete."),
            ("unit_invariant", "All categorical features use the explicit caller_declared unit."),
            (
                "topology_invariant",
                "Relations connect existing distinct features without self-loops.",
            ),
            (
                "stoichiometric_invariant",
                "The locked configuration binds a stoichiometry reference.",
            ),
            (
                "negative_control",
                "The locked configuration contains unique negative-control references.",
            ),
            (
                "authority_ceiling",
                "No elevated parent, clinical, or treatment authority claim is emitted.",
            ),
        )
    )
    if typed_diagnostic is not None:
        diagnostics = (*diagnostics, typed_diagnostic)
    return feature_object, diagnostics


class M1403MechanisticFeatureEngine:
    """Construct compatibility metadata or typed research program states."""

    __slots__ = ()

    def construct(self, request: object) -> ProteinSubtypeMechanisticFeatureResult:
        validated = _as_request(request)
        return self._result(validated)

    def _result(
        self,
        request: ConstructProteinSubtypeMechanisticFeaturesRequest,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        request_hash = canonical_request_digest(request)
        evidence = _evidence(request)
        findings: tuple[MechanisticFindingCode, ...] = ()
        abstention_reason: str | None = None
        try:
            feature_object, diagnostics = _feature_object(request, evidence, request_hash)
        except ValueError as error:
            diagnostics = (
                MechanisticFeatureDiagnostic(
                    diagnostic_id=f"diagnostic.m1403.{request_hash.removeprefix('sha256:')[:12]}.abstain",
                    status=MechanisticDiagnosticStatus.NOT_EVALUABLE,
                    message=str(error),
                    evidence=evidence[:1],
                ),
            )
            feature_object = None
            status = MechanisticConstructionStatus.ABSTAINED
            findings = (MechanisticFindingCode.UPSTREAM_UNSUPPORTED,)
            abstention_reason = (
                "M14-03 cannot safely construct features for the requested configuration."
            )
            support_status = SupportStatus.REVIEW_REQUIRED
            support_reason = "m1403_feature_construction_review_required"
            human_review_required = True
        else:
            status = MechanisticConstructionStatus.CONSTRUCTED
            findings = ()
            abstention_reason = None
            support_status = SupportStatus.REVIEW_REQUIRED
            support_reason = "m1403_feature_construction_review_required"
            human_review_required = True
        payload: dict[str, object] = {
            "output_type": "protein_subtype_mechanistic_features",
            "result_id": f"result.m1403.{request_hash.removeprefix('sha256:')[:32]}",
            "result_version": M1403_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": "sha256:" + "0" * 64,
            "request": request,
            "status": status,
            "feature_object": feature_object,
            "diagnostics": diagnostics,
            "findings": findings,
            "abstention_reason": abstention_reason,
            "parent_target": M1403_PARENT,
            "emits_parent": False,
            "support_decision": SupportDecision(
                status=support_status,
                reason_code=support_reason,
                rationale=(
                    "All closed metadata invariants passed; output remains caller-declared."
                    if status is MechanisticConstructionStatus.CONSTRUCTED
                    else (
                        "Feature construction is withheld pending review of the unsupported "
                        "configuration."
                    )
                ),
            ),
            "uncertainty": _uncertainty(typed=bool(request.typed_observations)),
            "provenance": _provenance(request, request_hash),
            "evidence": evidence,
            "limitations": (
                _TYPED_LIMITATIONS if request.typed_observations else _LIMITATIONS
            ),
            "human_review_required": human_review_required,
        }
        constructed = ProteinSubtypeMechanisticFeatureResult.model_construct(
            **payload  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinSubtypeMechanisticFeatureResult:
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1403ReplayVerificationError from error
        if validated.result_digest != result_payload_digest(validated):
            raise M1403ReplayVerificationError
        if replay:
            expected = self.construct(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1403ReplayVerificationError
        return validated


def construct_protein_subtype_mechanistic_features(
    request: object,
) -> ProteinSubtypeMechanisticFeatureResult:
    """Public provisional M14-03 operation."""

    return M1403MechanisticFeatureEngine().construct(request)


__all__ = [
    "M1403AuthorizationError",
    "M1403MechanisticFeatureEngine",
    "M1403ReplayVerificationError",
    "construct_protein_subtype_mechanistic_features",
    "preflight_m1403_authorization",
]
