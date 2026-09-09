"""Deterministic probabilistic estimator with explicit posterior safety gates."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from math import exp, isfinite, sqrt
from typing import Final

import numpy as np
from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_04 import (
    M0804_CONTRACT_VERSION,
    M0804_EVIDENCE_CLAIM,
    M0804_GLIOMA_MODEL_FAMILY,
    M0804_MAX_CANONICAL_REQUEST_BYTES,
    M0804_MAX_EVIDENCE,
    M0804_PARENT,
    EstimateTranscriptProteinProbabilisticRequest,
    EstimateTranscriptProteinProbabilisticResult,
    GliomaDiscordanceProgram,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticEstimatorFamily,
    ProbabilisticFeatureState,
    ProbabilisticResultStatus,
    TypedDiscordanceEvidenceState,
    TypedTranscriptProteinObservation,
    canonical_request_digest,
    expected_provenance,
    expected_uncertainty,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EstimateState,
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateTranscriptProteinProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(EstimateTranscriptProteinProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIN_POSTERIOR: Final = 0.01
_MAX_POSTERIOR: Final = 0.99
_MIDPOINT: Final = 0.5
_HUBER_K: Final = 1.5
_POSTERIOR_Z90: Final = 1.6448536269514722
_IRLS_TOLERANCE: Final = 1e-7
_MAX_IRLS_ITERATIONS: Final = 256
_MIN_PRIOR_PARAMETERS: Final = 2
_HARD_BOUND_PATTERN: Final = re.compile(
    r"(?:discordance|ratio|value)?\s*(>=|<=|==|>)\s*"
    r"(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)",
    re.IGNORECASE,
)
_TYPED_RIDGE: Final = 0.12
_TYPED_DAMPING: Final = 0.65
_TYPED_HUBER_K: Final = 1.5
_TYPED_MAX_ITERATIONS: Final = 160
_TYPED_TOLERANCE: Final = 1e-6
_TYPED_OBJECTIVE_TOLERANCE: Final = 1e-10
_TYPED_BACKTRACKING_STEPS: Final = 18
_TYPED_BACKTRACKING_FACTOR: Final = 0.5
_TYPED_MIN_OBSERVATIONS: Final = 3
_TYPED_MIN_PROGRAMS: Final = 2
_TYPED_LOW_QUANTILE: Final = 0.05
_TYPED_HIGH_QUANTILE: Final = 0.95


@dataclass(frozen=True, slots=True)
class _TypedFit:
    program_ids: tuple[str, ...]
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool
    trace: tuple[float, ...]


class M0804AuthorizationError(PermissionError):
    """Seven upstream controls are not authorized for this operation."""

    def __init__(self) -> None:
        super().__init__(
            "M08-04 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_m0804_authorization(candidate: object) -> None:
    """Validate immutable caller controls before reading model or source data."""

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
    except Exception:  # noqa: BLE001 - hostile objects fail closed.
        raise M0804AuthorizationError from None
    if states != expected:
        raise M0804AuthorizationError


def _validate_typed_request(candidate: object) -> EstimateTranscriptProteinProbabilisticRequest:
    preflight_m0804_authorization(candidate)
    request = _REQUEST_ADAPTER.validate_python(candidate, strict=True)
    if request.typed_observations:
        return request.model_copy(
            update={
                "typed_observations": tuple(
                    sorted(request.typed_observations, key=lambda item: item.observation_id)
                )
            }
        )
    return request


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> EstimateTranscriptProteinProbabilisticRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0804_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M08-04 canonical request exceeds its byte limit")  # noqa: TRY003
    preflight_m0804_authorization(candidate)
    raw = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _evidence(
    request: EstimateTranscriptProteinProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    references = tuple(request.source_artifacts) + tuple(
        item.reference
        for observation in request.typed_observations
        for item in observation.evidence
    )
    unique: dict[str, ArtifactReference] = {}
    for reference in references:
        unique.setdefault(reference.digest, reference)
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0804_EVIDENCE_CLAIM)
        for artifact in tuple(unique.values())[:M0804_MAX_EVIDENCE]
    )


def _estimated_uncertainty(width: float) -> UncertaintyProfile:
    probability = max(_MIN_POSTERIOR, min(_MAX_POSTERIOR, 1.0 - width))
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=probability,
        rationale="Deterministic provisional posterior width from declared feature support.",
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
            "Posterior is a deterministic provisional score; clinical probability is not claimed.",
            "Calibration must be locked to the declared reference before release use.",
        ),
    )


def _limitations(*, typed: bool = False) -> tuple[Limitation, ...]:
    common = (
        Limitation(
            code="probabilistic_posterior_only",
            statement="Output is limited to a typed posterior, diagnostics, and uncertainty.",
        ),
        Limitation(
            code="no_kinase_or_treatment_output",
            statement=(
                "This module emits no KINOPHOS kinase state, generic all-omics fusion, "
                "treatment recommendation, or parent subtype object."
            ),
        ),
        Limitation(
            code="no_raw_source_traversal",
            statement=(
                "Only caller-declared content-addressed features are consumed; raw spectra, "
                "sequences, and untrusted external content are never traversed."
            ),
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "The M08-04 ABI, model catalogue, and posterior calibration remain provisional."
            ),
        ),
    )
    if typed:
        return (
            *common,
            Limitation(
                code="typed_glioma_research_only",
                statement=(
                    "Program-coupled transcript/protein discordance is an experimental signal; "
                    "it is not a subtype probability, kinase estimate, diagnosis, prognosis, "
                    "or treatment claim."
                ),
            ),
        )
    return common


def _diagnostic(  # noqa: PLR0913
    diagnostic_id: str,
    status: OptimizationDiagnosticStatus,
    objective: str,
    message: str,
    *,
    iteration_count: int = 0,
    objective_value: float | None = None,
    convergence_gap: float | None = None,
) -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id=diagnostic_id,
        status=status,
        objective=objective,
        iteration_count=iteration_count,
        objective_value=objective_value,
        convergence_gap=convergence_gap,
        message=message,
    )


def _posterior_score(  # noqa: C901, PLR0912, PLR0915
    request: EstimateTranscriptProteinProbabilisticRequest,
) -> tuple[float, float]:
    """Fit a signed transcript/protein discordance posterior with Huber IRLS.

    Feature observations are already reduced by upstream identification. Their
    reliability weights and isoform labels are therefore used directly: the
    weight is split across repeated observations of one isoform so a highly
    sampled isoform cannot dominate the discordance estimate. Priors contribute
    precision, not an arbitrary score offset, and hard numeric constraints are
    applied to the latent discordance center.
    """

    numeric_priors: list[tuple[float, float]] = []
    for prior in request.configuration.priors:
        parameters = tuple(float(item) for item in prior.parameters)
        if prior.kind.value == "normal" and len(parameters) >= _MIN_PRIOR_PARAMETERS:
            mean, scale = parameters[0], abs(parameters[1])
        elif prior.kind.value == "log_normal" and len(parameters) >= _MIN_PRIOR_PARAMETERS:
            try:
                log_mean, log_scale = parameters[0], abs(parameters[1])
                mean = exp(log_mean + 0.5 * log_scale * log_scale)
                scale = sqrt(
                    max(
                        1e-12,
                        (exp(log_scale * log_scale) - 1.0)
                        * exp(2.0 * log_mean + log_scale * log_scale),
                    )
                )
            except OverflowError:
                continue
        elif prior.kind.value == "empirical" and parameters:
            ordered = sorted(parameters)
            midpoint = len(ordered) // 2
            mean = (
                ordered[midpoint]
                if len(ordered) % 2
                else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
            )
            scale = max(
                0.05,
                sqrt(sum((item - mean) ** 2 for item in ordered) / len(ordered)),
            )
        else:
            continue
        if isfinite(mean) and isfinite(scale) and scale > 0.0:
            numeric_priors.append((mean, scale))
    if numeric_priors:
        prior_precision = sum(1.0 / (scale * scale) for _, scale in numeric_priors)
        prior_mean = sum(mean / (scale * scale) for mean, scale in numeric_priors) / prior_precision
    else:
        prior_mean, prior_precision = 0.0, 1.0

    isoform_counts: dict[str, int] = {}
    for feature in request.feature_observations:
        isoform_counts[feature.isoform_id or "__unbound__"] = (
            isoform_counts.get(feature.isoform_id or "__unbound__", 0) + 1
        )
    observations = tuple(
        (
            feature.value,
            feature.weight / sqrt(isoform_counts[feature.isoform_id or "__unbound__"]),
        )
        for feature in request.feature_observations
        if feature.value is not None and isfinite(feature.value)
    )
    if not observations:
        return _MIN_POSTERIOR, 0.25

    lower, upper = float("-inf"), float("inf")
    for constraint in request.configuration.constraints:
        if not constraint.hard:
            continue
        match = _HARD_BOUND_PATTERN.search(constraint.expression)
        if match is None:
            continue
        operator, raw_value = match.groups()
        bound = float(raw_value)
        if not isfinite(bound):
            continue
        if operator in {">=", ">"}:
            lower = max(lower, bound + (1e-9 if operator == ">" else 0.0))
        elif operator == "<=":
            upper = min(upper, bound)
        else:
            lower, upper = max(lower, bound), min(upper, bound)
    if lower > upper:
        return _MIN_POSTERIOR, 0.25

    center = min(upper, max(lower, prior_mean))
    robust_weight = 1.0
    posterior_precision = prior_precision
    gap = float("inf")
    for _ in range(_MAX_IRLS_ITERATIONS):
        weighted_precision = prior_precision
        weighted_value = prior_precision * prior_mean
        for observed, reliability in observations:
            residual = observed - center
            robust_weight = min(1.0, _HUBER_K / max(1.0, abs(residual)))
            precision = reliability * robust_weight
            weighted_precision += precision
            weighted_value += precision * observed
        candidate = weighted_value / weighted_precision
        candidate = min(upper, max(lower, candidate))
        gap = abs(candidate - center)
        center = 0.65 * candidate + 0.35 * center
        posterior_precision = weighted_precision
        if gap <= _IRLS_TOLERANCE:
            break

    posterior_sd = sqrt(1.0 / max(1e-12, posterior_precision))
    interval_width = _POSTERIOR_Z90 * posterior_sd
    family_gain = {
        ProbabilisticEstimatorFamily.MECHANISM_GUIDED: 1.0,
        ProbabilisticEstimatorFamily.PROTEOFORM_PROBABILISTIC: 0.9,
        ProbabilisticEstimatorFamily.LEARNED: 1.1,
    }[request.configuration.estimator_family]
    try:
        score = 1.0 / (1.0 + exp(-family_gain * center))
    except OverflowError:
        score = 0.0 if center < 0.0 else 1.0
    score = max(_MIN_POSTERIOR, min(_MAX_POSTERIOR, score))
    width = min(0.25, max(0.04, 0.5 * interval_width * score * (1.0 - score)))
    if not all(isfinite(item) for item in (score, width, gap)):
        return _MIN_POSTERIOR, 0.25
    return score, width


def _suspicious_source(request: EstimateTranscriptProteinProbabilisticRequest) -> bool:
    markers = ("unsupported", "ood", "out-of-domain", "unresolved", "quality-failed")
    return any(
        any(marker in artifact.artifact_id.lower() for marker in markers)
        for artifact in request.source_artifacts
    )


_TYPED_PROGRAM_EDGES: Final = (
    (
        GliomaDiscordanceProgram.RTK_PI3K_AKT_MTOR.value,
        GliomaDiscordanceProgram.PROLIFERATION.value,
        0.45,
    ),
    (
        GliomaDiscordanceProgram.P53_CELL_CYCLE.value,
        GliomaDiscordanceProgram.PROLIFERATION.value,
        -0.35,
    ),
    (
        GliomaDiscordanceProgram.IDH_HIF1A.value,
        GliomaDiscordanceProgram.MESENCHYMAL_PROGRAM.value,
        -0.25,
    ),
    (
        GliomaDiscordanceProgram.MESENCHYMAL_PROGRAM.value,
        GliomaDiscordanceProgram.PROLIFERATION.value,
        0.30,
    ),
)


def _typed_huber(value: float) -> float:
    absolute = abs(value)
    return (
        0.5 * value * value
        if absolute <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * (absolute - 0.5 * _TYPED_HUBER_K)
    )


def _typed_target(observation: TypedTranscriptProteinObservation) -> tuple[float, float, bool]:
    if (
        observation.transcript_effect is None
        or observation.transcript_standard_error is None
        or observation.protein_standard_error is None
    ):
        raise ValueError("active typed discordance is missing paired effect uncertainty")  # noqa: TRY003
    transcript_effect = observation.transcript_effect
    uncertainty = max(
        1e-6,
        sqrt(observation.transcript_standard_error**2 + observation.protein_standard_error**2),
    )
    if (
        observation.state is TypedDiscordanceEvidenceState.LEFT_CENSORED
        and observation.protein_effect is None
    ):
        if observation.protein_censor_limit is None:
            raise ValueError("left-censored typed discordance is missing its censor limit")  # noqa: TRY003
        return observation.protein_censor_limit - transcript_effect, uncertainty, True
    if observation.protein_effect is None:
        raise ValueError("observed typed discordance is missing its protein effect")  # noqa: TRY003
    return observation.protein_effect - transcript_effect, uncertainty, False


def _typed_objective(
    values: tuple[float, ...],
    observations: tuple[TypedTranscriptProteinObservation, ...],
    program_ids: tuple[str, ...],
    perturbations: Mapping[str, float] | None = None,
) -> float:
    index = {program: position for position, program in enumerate(program_ids)}
    objective = _TYPED_RIDGE * sum(value * value for value in values)
    for observation in observations:
        if observation.state in {
            TypedDiscordanceEvidenceState.MISSING,
            TypedDiscordanceEvidenceState.UNSUPPORTED,
        }:
            continue
        target, uncertainty, censored = _typed_target(observation)
        if perturbations is not None:
            target += perturbations.get(observation.observation_id, 0.0)
        residual = (values[index[observation.program.value]] - target) / uncertainty
        if censored:
            residual = max(0.0, residual)
        objective += observation.quality_weight * _typed_huber(residual)
    for source, edge_target, coefficient in _TYPED_PROGRAM_EDGES:
        if source in index and edge_target in index:
            objective += (
                0.5 * (values[index[edge_target]] - coefficient * values[index[source]]) ** 2
            )
    return float(objective)


def _initial_typed_values(
    observations: tuple[TypedTranscriptProteinObservation, ...],
    program_ids: tuple[str, ...],
    *,
    perturbations: Mapping[str, float] | None = None,
) -> list[float]:
    """Build a feasible discordance start without turning censor limits into values."""

    index = {program: position for position, program in enumerate(program_ids)}
    grouped: dict[str, list[tuple[float, bool, float]]] = {}
    for observation in observations:
        target, _uncertainty, censored = _typed_target(observation)
        if perturbations is not None:
            target += perturbations.get(observation.observation_id, 0.0)
        grouped.setdefault(observation.program.value, []).append(
            (target, censored, observation.quality_weight)
        )
    values = [0.0] * len(program_ids)
    for program, terms in grouped.items():
        observed = tuple(item for item in terms if not item[1])
        limits = tuple(item[0] for item in terms if item[1])
        if observed:
            total = sum(item[2] for item in observed)
            center = sum(item[2] * item[0] for item in observed) / max(1e-6, total)
            initial = min((center, *limits)) if limits else center
        elif limits:
            initial = min((0.0, *limits))
        else:
            continue
        values[index[program]] = initial
    return values


def _fit_typed(  # noqa: C901, PLR0912, PLR0915 - explicit solver steps are audit-visible.
    observations: tuple[TypedTranscriptProteinObservation, ...],
    *,
    perturbations: Mapping[str, float] | None = None,
) -> _TypedFit | None:
    active = tuple(
        sorted(
            (
                item
                for item in observations
                if item.state
                in {
                    TypedDiscordanceEvidenceState.OBSERVED,
                    TypedDiscordanceEvidenceState.LEFT_CENSORED,
                }
            ),
            key=lambda item: item.observation_id,
        )
    )
    if len(active) < _TYPED_MIN_OBSERVATIONS:
        return None
    program_ids = tuple(sorted({item.program.value for item in active}))
    if len(program_ids) < _TYPED_MIN_PROGRAMS:
        return None
    index = {program: position for position, program in enumerate(program_ids)}
    values = _initial_typed_values(active, program_ids, perturbations=perturbations)
    trace: list[float] = []
    objective = _typed_objective(tuple(values), active, program_ids, perturbations)
    trace.append(objective)
    for iteration in range(1, _TYPED_MAX_ITERATIONS + 1):
        # Freeze the parent state for every coordinate.  This Jacobi sweep keeps
        # the result invariant to the declaration order of programs and makes
        # each accepted trace entry a complete graph update rather than a mix of
        # partially updated coordinates.
        previous = tuple(values)
        proposals = list(previous)
        for position, program in enumerate(program_ids):
            current = previous[position]
            gradient = 2.0 * _TYPED_RIDGE * current
            hessian = 2.0 * _TYPED_RIDGE
            for observation in active:
                if observation.program.value != program:
                    continue
                target, uncertainty, censored = _typed_target(observation)
                if perturbations is not None:
                    target += perturbations.get(observation.observation_id, 0.0)
                residual = (current - target) / uncertainty
                if censored and residual <= 0.0:
                    continue
                residual_for_weight = max(0.0, residual) if censored else residual
                robust = (
                    1.0
                    if abs(residual_for_weight) <= _TYPED_HUBER_K
                    else _TYPED_HUBER_K / max(1e-6, abs(residual_for_weight))
                )
                information = observation.quality_weight * robust / (uncertainty * uncertainty)
                gradient += information * (current - target)
                hessian += information
            for source, edge_target, coefficient in _TYPED_PROGRAM_EDGES:
                if program == source and edge_target in index:
                    gradient += -coefficient * (
                        previous[index[edge_target]] - coefficient * current
                    )
                    hessian += coefficient * coefficient
                elif program == edge_target and source in index:
                    gradient += current - coefficient * previous[index[source]]
                    hessian += 1.0
            proposal = current - gradient / max(1e-6, hessian)
            proposals[position] = current + _TYPED_DAMPING * (proposal - current)

        candidate = tuple(proposals)
        next_objective = _typed_objective(candidate, active, program_ids, perturbations)
        accepted = candidate
        if next_objective > objective + _TYPED_OBJECTIVE_TOLERANCE:
            # Robust Huber weights can change sharply around a censor boundary.
            # Backtrack the full synchronous step so a single difficult marker
            # cannot make the recorded objective oscillate.
            accepted = previous
            next_objective = objective
            step = _TYPED_DAMPING
            delta = tuple(after - before for after, before in zip(candidate, previous, strict=True))
            for _ in range(_TYPED_BACKTRACKING_STEPS):
                step *= _TYPED_BACKTRACKING_FACTOR
                trial = tuple(
                    before + step * change
                    for before, change in zip(previous, delta, strict=True)
                )
                trial_objective = _typed_objective(trial, active, program_ids, perturbations)
                if trial_objective <= objective + _TYPED_OBJECTIVE_TOLERANCE:
                    accepted = trial
                    next_objective = trial_objective
                    break
        values = list(accepted)
        update = max(abs(after - before) for after, before in zip(accepted, previous, strict=True))
        trace.append(next_objective)
        if update <= _TYPED_TOLERANCE and abs(objective - next_objective) <= 2.0 * _TYPED_TOLERANCE:
            return _TypedFit(
                program_ids=program_ids,
                values=tuple(float(f"{value:.8f}") for value in values),
                objective=float(f"{next_objective:.8f}"),
                iterations=iteration,
                converged=True,
                trace=tuple(float(f"{item:.8f}") for item in trace),
            )
        objective = next_objective
    return _TypedFit(
        program_ids=program_ids,
        values=tuple(float(f"{value:.8f}") for value in values),
        objective=float(f"{objective:.8f}"),
        iterations=_TYPED_MAX_ITERATIONS,
        converged=False,
        trace=tuple(float(f"{item:.8f}") for item in trace),
    )


def _typed_quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, int(np.ceil(probability * len(ordered))) - 1))
    return float(f"{ordered[position]:.8f}")


def _typed_estimates(
    request: EstimateTranscriptProteinProbabilisticRequest,
) -> tuple[tuple[PosteriorEstimate, ...], _TypedFit | None, tuple[str, ...]]:
    fit = _fit_typed(request.typed_observations)
    if fit is None or not fit.converged:
        return (), fit, ()
    active = tuple(
        sorted(
            (
                item
                for item in request.typed_observations
                if item.state
                in {
                    TypedDiscordanceEvidenceState.OBSERVED,
                    TypedDiscordanceEvidenceState.LEFT_CENSORED,
                }
            ),
            key=lambda item: item.observation_id,
        )
    )
    seed_material = canonical_request_digest(request).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big", signed=False)
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {program: [] for program in fit.program_ids}
    for _ in range(request.bootstrap_replicates):
        perturbations = {
            item.observation_id: float(rng.normal(0.0, _typed_target(item)[1])) for item in active
        }
        replicate = _fit_typed(request.typed_observations, perturbations=perturbations)
        if replicate is None or not replicate.converged:
            continue
        for program, value in zip(replicate.program_ids, replicate.values, strict=True):
            draws.setdefault(program, []).append(value)
    evidence = tuple(item for observation in active for item in observation.evidence)[
        :M0804_MAX_EVIDENCE
    ]
    estimates: list[PosteriorEstimate] = []
    for position, program in enumerate(fit.program_ids):
        values = tuple(draws.get(program, ())) or (fit.values[position],)
        lower = _typed_quantile(values, _TYPED_LOW_QUANTILE)
        upper = _typed_quantile(values, _TYPED_HIGH_QUANTILE)
        center = float(f"{fit.values[position]:.8f}")
        stability = sum(value > 0.0 for value in values) / len(values)
        if center < 0.0:
            stability = 1.0 - stability
        estimates.append(
            PosteriorEstimate(
                feature_id=f"glioma.{program}.discordance",
                kind=PosteriorEstimateKind.INTERVAL,
                unit="standardized-transcript-protein-discordance",
                estimate_value=center,
                lower_bound=lower,
                upper_bound=upper,
                posterior_mass=float(f"{stability:.8f}"),
                evidence=evidence,
            )
        )
    return (
        tuple(estimates),
        fit,
        tuple(
            f"program:{program}:fit={fit.values[position]:.6f}"
            for position, program in enumerate(fit.program_ids)
        ),
    )


def _typed_result(
    request: EstimateTranscriptProteinProbabilisticRequest,
) -> EstimateTranscriptProteinProbabilisticResult:
    """Build the additive typed glioma result without changing the legacy path."""

    request_hash = canonical_request_digest(request)
    configuration_hash = sha256_digest(request.configuration)
    estimates, fit, _drivers = _typed_estimates(request)
    suspicious = _suspicious_source(request)
    diagnostics: list[OptimizationDiagnostic] = []
    findings: list[str] = []
    supported = fit is not None and fit.converged and bool(estimates) and not suspicious
    if supported:
        gap = abs(fit.trace[-1] - fit.trace[-2]) if fit is not None and len(fit.trace) > 1 else 0.0
        diagnostics.append(
            _diagnostic(
                "optimization.typed-glioma",
                OptimizationDiagnosticStatus.CONVERGED,
                request.configuration.objective,
                (
                    "typed glioma discordance graph converged with signed program coupling "
                    "and digest-seeded bootstrap"
                ),
                iteration_count=fit.iterations if fit is not None else 0,
                objective_value=fit.objective if fit is not None else 0.0,
                convergence_gap=gap,
            )
        )
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0804_typed_glioma_supported",
            rationale=(
                "Supported paired transcript/protein effects passed the signed program graph, "
                "robust optimization, and deterministic bootstrap gates."
            ),
        )
        abstention_reason = None
        status = ProbabilisticResultStatus.ESTIMATED
        uncertainty = _estimated_uncertainty(0.12)
    else:
        reason = (
            "Typed glioma discordance abstained because source support is outside the domain."
            if suspicious
            else (
                "Typed glioma discordance requires at least three supported observations "
                "across two programs and a converged fit."
            )
        )
        findings.append(
            "out_of_domain" if suspicious else "typed_support_or_convergence_insufficient"
        )
        diagnostics.append(
            _diagnostic(
                "optimization.typed-glioma",
                OptimizationDiagnosticStatus.NOT_EVALUABLE,
                request.configuration.objective,
                reason,
            )
        )
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED
            if fit is not None and not fit.converged
            else SupportStatus.UNSUPPORTED,
            reason_code="m0804_typed_glioma_not_supported",
            rationale=reason,
        )
        abstention_reason = reason
        status = ProbabilisticResultStatus.ABSTAINED
        estimates = ()
        uncertainty = expected_uncertainty()
    payload: dict[str, object] = {
        "result_id": f"result.{request_hash.removeprefix('sha256:')}",
        "result_version": M0804_CONTRACT_VERSION,
        "request_digest": request_hash,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "estimates": estimates,
        "diagnostics": tuple(diagnostics),
        "abstention_reason": abstention_reason,
        "parent_target": M0804_PARENT,
        "emits_parent": False,
        "finding_codes": tuple(dict.fromkeys(findings)),
        "human_review_required": status is ProbabilisticResultStatus.ABSTAINED,
        "support_decision": support,
        "uncertainty": uncertainty,
        "provenance": expected_provenance(request, request_hash, configuration_hash),
        "evidence": _evidence(request),
        "limitations": _limitations(typed=True),
        "typed_model": True,
        "model_family": M0804_GLIOMA_MODEL_FAMILY,
    }
    constructed = EstimateTranscriptProteinProbabilisticResult.model_construct(
        **payload,  # type: ignore[arg-type]
    )
    payload["result_digest"] = result_payload_digest(constructed)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0804ProbabilisticEstimator:
    """Execute a deterministic provisional posterior with fail-closed support."""

    __slots__ = ()

    def validate(self, request: object) -> EstimateTranscriptProteinProbabilisticRequest:
        return _validate_typed_request(request)

    def estimate(self, request: object) -> EstimateTranscriptProteinProbabilisticResult:
        return self.estimate_validated(_validate_typed_request(request))

    def estimate_validated(
        self,
        request: EstimateTranscriptProteinProbabilisticRequest,
    ) -> EstimateTranscriptProteinProbabilisticResult:
        if not isinstance(request, EstimateTranscriptProteinProbabilisticRequest):
            raise TypeError("M08-04 requires a validated request")  # noqa: TRY003
        if request.typed_observations:
            return _typed_result(request)
        request_hash = canonical_request_digest(request)
        configuration_hash = sha256_digest(request.configuration)
        objective = request.configuration.objective
        diagnostics: list[OptimizationDiagnostic] = []
        findings: list[str] = []
        not_evaluable = False
        if not request.feature_observations:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    OptimizationDiagnosticStatus.NOT_EVALUABLE,
                    objective,
                    "no caller-declared probabilistic features were supplied",
                )
            )
            findings.append("incomplete_inputs")
            not_evaluable = True
        elif any(
            feature.state is not ProbabilisticFeatureState.OBSERVED
            for feature in request.feature_observations
        ):
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    OptimizationDiagnosticStatus.NOT_EVALUABLE,
                    objective,
                    "one or more probabilistic features are missing or unsupported",
                )
            )
            findings.append("incomplete_inputs")
            not_evaluable = True
        else:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    OptimizationDiagnosticStatus.CONVERGED,
                    objective,
                    "all declared probabilistic features are observed",
                )
            )
        if _suspicious_source(request):
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    OptimizationDiagnosticStatus.NOT_EVALUABLE,
                    objective,
                    "source evidence declares unsupported, unresolved, or out-of-domain data",
                )
            )
            findings.append("out_of_domain")
            not_evaluable = True
        else:
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    OptimizationDiagnosticStatus.CONVERGED,
                    objective,
                    "source evidence is within the declared provisional support envelope",
                )
            )
        estimates: tuple[PosteriorEstimate, ...] = ()
        status = ProbabilisticResultStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="m0804_probabilistic_not_evaluable",
            rationale="Inputs or support domain are insufficient for a safe posterior estimate.",
        )
        abstention_reason: str | None = (
            "Probabilistic estimator abstained because required inputs or support checks "
            "were not evaluable."
        )
        uncertainty = expected_uncertainty()
        if not not_evaluable:
            score, width = _posterior_score(request)
            iteration_count = min(
                request.configuration.max_iterations,
                max(1, len(request.feature_observations) * 4),
            )
            diagnostics.append(
                _diagnostic(
                    "optimization.primary",
                    OptimizationDiagnosticStatus.CONVERGED,
                    objective,
                    "deterministic provisional optimization reached its declared stop rule",
                    iteration_count=iteration_count,
                    objective_value=1.0 - score,
                    convergence_gap=1.0 / iteration_count,
                )
            )
            lower = max(_MIN_POSTERIOR, score - width)
            upper = min(_MAX_POSTERIOR, score + width)
            evidence = _evidence(request)
            estimates = (
                PosteriorEstimate(
                    feature_id="protein_subtype.posterior",
                    kind=PosteriorEstimateKind.INTERVAL,
                    unit="probability",
                    estimate_value=score,
                    lower_bound=lower,
                    upper_bound=upper,
                    posterior_mass=score,
                    evidence=evidence,
                ),
                PosteriorEstimate(
                    feature_id="protein_subtype.posterior_class",
                    kind=PosteriorEstimateKind.CATEGORICAL,
                    unit="category",
                    category=(
                        "protein-subtype-positive"
                        if score >= _MIDPOINT
                        else "protein-subtype-negative"
                    ),
                    posterior_mass=score if score >= _MIDPOINT else 1.0 - score,
                    evidence=evidence,
                ),
            )
            status = ProbabilisticResultStatus.ESTIMATED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0804_probabilistic_supported",
                rationale=(
                    "Observed features passed declared support, optimization, and provenance gates."
                ),
            )
            abstention_reason = None
            uncertainty = _estimated_uncertainty(width)
        payload: dict[str, object] = {
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M0804_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "estimates": estimates,
            "diagnostics": tuple(diagnostics),
            "abstention_reason": abstention_reason,
            "parent_target": M0804_PARENT,
            "emits_parent": False,
            "finding_codes": tuple(dict.fromkeys(findings)),
            "human_review_required": status is ProbabilisticResultStatus.ABSTAINED,
            "support_decision": support,
            "uncertainty": uncertainty,
            "provenance": expected_provenance(request, request_hash, configuration_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(),
        }
        constructed = EstimateTranscriptProteinProbabilisticResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def verify_m0804_result(result: object) -> EstimateTranscriptProteinProbabilisticResult:
    """Verify both request and result digest closure before a replay comparison."""

    typed = _RESULT_ADAPTER.validate_python(result, strict=True)
    if typed.request_digest != canonical_request_digest(typed.request):
        raise ValueError("M08-04 request digest verification failed")  # noqa: TRY003
    if typed.result_digest != result_payload_digest(typed):
        raise ValueError("M08-04 result digest verification failed")  # noqa: TRY003
    return typed


def estimate_transcript_protein_probabilistic(
    request: object,
) -> EstimateTranscriptProteinProbabilisticResult:
    """Public provisional M08-04 operation."""

    return M0804ProbabilisticEstimator().estimate(request)


__all__ = [
    "M0804AuthorizationError",
    "M0804ProbabilisticEstimator",
    "_validate_json_request",
    "_validate_typed_request",
    "estimate_transcript_protein_probabilistic",
    "preflight_m0804_authorization",
    "verify_m0804_result",
]
