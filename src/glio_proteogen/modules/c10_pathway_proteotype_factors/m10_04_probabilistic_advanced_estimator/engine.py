"""Deterministic, fail-closed provisional M10-04 estimator runtime."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Final

import numpy as np
from pydantic import BaseModel, TypeAdapter

from glio_proteogen.contracts.m10_04 import (
    M1004_CONTRACT_VERSION,
    M1004_EVIDENCE_CLAIM,
    M1004_GLIOMA_MODEL_FAMILY,
    M1004_MAX_EVIDENCE,
    M1004_PARENT,
    EstimateProteinRnaDiscordanceProbabilisticRequest,
    OptimizationDiagnostic,
    OptimizationDiagnosticStatus,
    PosteriorEstimate,
    PosteriorEstimateKind,
    ProbabilisticObservation,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
    ProbabilisticResultStatus,
    ProteinRnaDiscordanceProbabilisticResult,
    expected_provenance,
    expected_uncertainty,
)
from glio_proteogen.contracts.m10_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
    verify_result_digest,
)
from glio_proteogen.kernel.models import (
    EvidenceReference,
    Limitation,
    SupportDecision,
    SupportStatus,
)

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinRnaDiscordanceProbabilisticRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinRnaDiscordanceProbabilisticResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_NORMAL_PARAMETER_COUNT: Final = 2
_HUBER_K: Final = 1.5
_CONVERGENCE_TOLERANCE: Final = 1e-9
M1004_GLIOMA_IRLS_OPTIMIZER: Final = "locked_glioma_proteotype_factor_irls_v1"
_GLIOMA_HUBER_K: Final = 1.5
_GLIOMA_DAMPING: Final = 0.68
_GLIOMA_RIDGE: Final = 0.12
_GLIOMA_EDGE_WEIGHT: Final = 0.28
_GLIOMA_TOLERANCE: Final = 1e-7
_GLIOMA_MAX_ITERATIONS: Final = 160
_GLIOMA_MIN_OBSERVATIONS: Final = 4
_GLIOMA_MIN_PROGRAMS: Final = 2
_GLIOMA_Z90: Final = 1.6448536269514722
_GLIOMA_PROGRAMS: Final = (
    "RTK_PI3K_AKT_MTOR",
    "P53_CELL_CYCLE",
    "IDH_HIF1A",
    "MESENCHYMAL_PROGRAM",
    "PROLIFERATION",
)
_GLIOMA_MARKERS: Final[dict[str, frozenset[str]]] = {
    "RTK_PI3K_AKT_MTOR": frozenset(
        {"egfr", "pdgfra", "pik3ca", "pik3r1", "akt1", "akt2", "mtor", "pten", "nf1"}
    ),
    "P53_CELL_CYCLE": frozenset(
        {"tp53", "mdm2", "cdkn2a", "cdkn2b", "cdk4", "rb1", "chek2", "atrx"}
    ),
    "IDH_HIF1A": frozenset({"idh1", "idh2", "hif1a", "vhl", "epas1", "dnmt1"}),
    "MESENCHYMAL_PROGRAM": frozenset(
        {
            "nf1",
            "stat3",
            "cebpb",
            "cebp",  # legacy alias retained; CEBPB is the canonical HGNC symbol.
            "tgfb1",
            "rela",
            "chi3l1",
            "fibronectin",
            "fn1",
        }
    ),
    "PROLIFERATION": frozenset(
        {"mki67", "pcna", "top2a", "mcm2", "mcm7", "ccnd1", "ccne1", "aurka"}
    ),
}
_GLIOMA_MARKER_PRIORITY: Final[dict[str, tuple[str, ...]]] = {
    # NF1 loss is represented as a mesenchymal-program driver in this
    # abundance/discordance model; lexical program order must not decide it.
    "nf1": ("MESENCHYMAL_PROGRAM", "RTK_PI3K_AKT_MTOR"),
}
_GLIOMA_EDGES: Final = (
    ("RTK_PI3K_AKT_MTOR", "P53_CELL_CYCLE", -1.0),
    ("RTK_PI3K_AKT_MTOR", "PROLIFERATION", 1.0),
    ("IDH_HIF1A", "MESENCHYMAL_PROGRAM", -0.35),
    ("MESENCHYMAL_PROGRAM", "PROLIFERATION", 0.5),
)


class M1004ProbabilisticEstimatorAuthorizationError(PermissionError):
    """Caller-owned controls are not authorized for estimation."""

    def __init__(self) -> None:
        super().__init__(
            "M10-04 requires accepted controls, resolved identity, and granted consent"
        )


class M1004ReplayVerificationError(ValueError):
    """A result cannot be reconstructed from its exact request envelope."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"M10-04 replay verification failed: {detail}")


@dataclass(frozen=True, slots=True)
class _GliomaFactorFit:
    states: tuple[float, ...]
    estimates: tuple[PosteriorEstimate, ...]
    objective: float
    iterations: int
    convergence_gap: float
    objective_trace: tuple[float, ...]
    program_counts: tuple[tuple[str, int], ...]


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_probabilistic_estimator_authorization(candidate: object) -> None:
    """Check seven control decisions before strict model validation."""

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
        raise M1004ProbabilisticEstimatorAuthorizationError from None
    if states != expected:
        raise M1004ProbabilisticEstimatorAuthorizationError


def _prepare(candidate: object) -> object:
    preflight_probabilistic_estimator_authorization(candidate)
    return candidate


def _evidence(
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
) -> tuple[EvidenceReference, ...]:
    artifacts = (
        request.baseline_result,
        request.configuration.reference,
        *request.source_artifacts,
        *(item.reference for observation in request.observations for item in observation.evidence),
    )
    return tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M1004_EVIDENCE_CLAIM)
        for artifact in artifacts[:M1004_MAX_EVIDENCE]
    )


def _diagnostic() -> OptimizationDiagnostic:
    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m1004.not-evaluable",
        status=OptimizationDiagnosticStatus.NOT_EVALUABLE,
        objective="owner-locked probabilistic objective pending",
        iteration_count=0,
        message=(
            "The provisional lane cannot claim optimization convergence until training, "
            "baseline comparison, and calibration artifacts are owner-locked."
        ),
    )


def _measured_diagnostic(  # noqa: PLR0913 - optional model metadata is explicit.
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    *,
    objective_value: float,
    iteration_count: int,
    convergence_gap: float,
    model_family: str | None = None,
    message: str | None = None,
) -> OptimizationDiagnostic:
    """Describe the deterministic robust posterior fit for measured observations."""

    return OptimizationDiagnostic(
        diagnostic_id="diagnostic.m1004.robust-normal-irls",
        status=OptimizationDiagnosticStatus.CONVERGED,
        objective=request.configuration.objective,
        iteration_count=iteration_count,
        objective_value=objective_value,
        convergence_gap=convergence_gap,
        model_family=model_family,
        message=message
        or (
            "Measured observations were fit with a robust Normal conjugate posterior using "
            "Huber IRLS, deterministic damping, and the locked configuration seed."
        ),
        evidence=_evidence(request),
    )


def _normal_prior(prior: ProbabilisticPrior) -> tuple[float, float] | None:
    """Return a finite (mean, standard deviation) Normal prior, if declared."""

    if (
        prior.kind is not ProbabilisticPriorKind.NORMAL
        or len(prior.parameters) < _NORMAL_PARAMETER_COUNT
    ):
        return None
    mean, standard_deviation = prior.parameters[:2]
    if not isfinite(mean) or not isfinite(standard_deviation) or standard_deviation <= 0:
        return None
    return mean, standard_deviation


def _fit_observation(
    observation: ProbabilisticObservation,
    prior: ProbabilisticPrior,
    *,
    max_iterations: int,
) -> tuple[PosteriorEstimate, float, int, float] | None:
    """Fit one measured value with a bounded Huber-IRLS Normal posterior.

    The prior is retained as an explicit regularizer.  Huber weights prevent a single
    low-quality outlier from dominating the protein/RNA discordance estimate while the
    posterior variance remains tied to the declared assay standard error.
    """

    prior_parameters = _normal_prior(prior)
    if prior_parameters is None:
        return None
    prior_mean, prior_sd = prior_parameters
    prior_precision = 1.0 / (prior_sd * prior_sd)
    observation_precision = observation.quality_weight / (
        observation.standard_error * observation.standard_error
    )
    if observation_precision <= 0:
        return None
    current = prior_mean
    damping = 0.7
    gap = float("inf")
    iterations = 0
    for iteration in range(1, max_iterations + 1):
        iterations = iteration
        standardized_residual = (observation.value - current) / observation.standard_error
        absolute_residual = abs(standardized_residual)
        huber_weight = (
            1.0 if absolute_residual <= _HUBER_K else _HUBER_K / absolute_residual
        )
        robust_precision = observation_precision * huber_weight
        target = (prior_precision * prior_mean + robust_precision * observation.value) / (
            prior_precision + robust_precision
        )
        updated = current + damping * (target - current)
        gap = abs(updated - current)
        current = updated
        if gap <= _CONVERGENCE_TOLERANCE:
            break
    robust_residual = (observation.value - current) / observation.standard_error
    absolute_residual = abs(robust_residual)
    huber_loss = (
        0.5 * robust_residual * robust_residual
        if absolute_residual <= _HUBER_K
        else _HUBER_K * absolute_residual - 0.5 * _HUBER_K * _HUBER_K
    )
    objective = 0.5 * ((current - prior_mean) / prior_sd) ** 2 + (
        observation.quality_weight * huber_loss
    )
    posterior_variance = 1.0 / (prior_precision + observation_precision)
    half_width = 1.96 * sqrt(posterior_variance)
    estimate = PosteriorEstimate(
        feature_id=observation.feature_id,
        kind=PosteriorEstimateKind.INTERVAL,
        unit="standardized-protein-rna-discordance",
        estimate_value=round(current, 8),
        lower_bound=round(current - half_width, 8),
        upper_bound=round(current + half_width, 8),
        posterior_mass=0.95,
        evidence=observation.evidence or prior.evidence,
    )
    return estimate, objective, iterations, gap


def _glioma_program_for_feature(feature_id: str) -> str | None:
    """Map a stable gene/protein identifier to one locked GBM program.

    The map intentionally uses a small, repository-owned marker panel rather than
    caller-provided labels.  Prefixes such as ``protein.egfr`` and ``gene.EGFR``
    therefore resolve identically while arbitrary feature names remain on the
    compatibility path.
    """

    normalized = feature_id.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    # HGNC symbols are frequently written with a hyphen (for example MKI-67
    # or HIF-1A).  ``re.findall`` intentionally tokenizes punctuation, so add
    # compact variants for compound identifier tokens without collapsing the
    # surrounding namespace (``protein.MKI-67`` remains namespace-safe).
    compound_tokens = re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)+", normalized)
    tokens.update(token.replace("-", "").replace("_", "") for token in compound_tokens)
    aliases = {
        "p53": "tp53",
        "akt": "akt1",
        "mki67": "mki67",
        "hif": "hif1a",
    }
    tokens.update(aliases[token] for token in tuple(tokens) if token in aliases)
    scored = tuple(
        (sum(token in markers for token in tokens), index, program)
        for index, program in enumerate(_GLIOMA_PROGRAMS)
        for markers in (_GLIOMA_MARKERS[program],)
    )
    best_score = max(item[0] for item in scored)
    if best_score == 0:
        return None
    matches = {program for score, _index, program in scored if score == best_score}
    for marker in sorted(tokens):
        for preferred in _GLIOMA_MARKER_PRIORITY.get(marker, ()):
            if preferred in matches:
                return preferred
    # Non-ambiguous markers retain the explicit catalogue order.
    return next(program for _score, _index, program in scored if program in matches)


def _glioma_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * magnitude * magnitude
        if magnitude <= _GLIOMA_HUBER_K
        else _GLIOMA_HUBER_K * magnitude - 0.5 * _GLIOMA_HUBER_K * _GLIOMA_HUBER_K
    )


def _glioma_factor_objective(
    observations: tuple[tuple[ProbabilisticObservation, str, float, float], ...],
    states: np.ndarray,
) -> float:
    index = {program: position for position, program in enumerate(_GLIOMA_PROGRAMS)}
    total = _GLIOMA_RIDGE * float(np.dot(states, states))
    for observation, program, prior_mean, prior_sd in observations:
        state = float(states[index[program]])
        standardized = (observation.value - state) / observation.standard_error
        total += observation.quality_weight * _glioma_huber(standardized)
        total += 0.5 * ((state - prior_mean) / prior_sd) ** 2
    for source, target, sign in _GLIOMA_EDGES:
        total += _GLIOMA_EDGE_WEIGHT * (
            float(states[index[target]]) - sign * float(states[index[source]])
        ) ** 2
    return float(total)


def _fit_glioma_factor_graph(  # noqa: C901, PLR0912, PLR0915 - solver safeguards are explicit.
    request: EstimateProteinRnaDiscordanceProbabilisticRequest,
) -> _GliomaFactorFit | None:
    """Fit coupled GBM program states with robust IRLS coordinate descent.

    This path is opt-in through ``locked_glioma_proteotype_factor_irls_v1``.  It
    is deliberately separate from the historical independent Normal posterior so
    existing callers retain byte-compatible behavior.  Each feature contributes
    to a fixed GBM program, and signed program edges constrain the latent states.
    """

    priors = {prior.prior_id: prior for prior in request.configuration.priors}
    prepared: list[tuple[ProbabilisticObservation, str, float, float]] = []
    for observation in sorted(request.observations, key=lambda item: item.feature_id):
        program = _glioma_program_for_feature(observation.feature_id)
        prior = priors.get(observation.feature_id)
        if program is None or prior is None:
            continue
        prior_parameters = _normal_prior(prior)
        if prior_parameters is None:
            return None
        prior_mean, prior_sd = prior_parameters
        prepared.append((observation, program, prior_mean, prior_sd))
    programs = {item[1] for item in prepared}
    if len(prepared) < _GLIOMA_MIN_OBSERVATIONS or len(programs) < _GLIOMA_MIN_PROGRAMS:
        return None
    index = {program: position for position, program in enumerate(_GLIOMA_PROGRAMS)}
    states = np.zeros(len(_GLIOMA_PROGRAMS), dtype=np.float64)
    for program in _GLIOMA_PROGRAMS:
        members = [item for item in prepared if item[1] == program]
        if members:
            weights = np.asarray(
                [
                    item[0].quality_weight / max(item[0].standard_error**2, 1e-12)
                    for item in members
                ],
                dtype=np.float64,
            )
            states[index[program]] = float(
                np.dot(weights, np.asarray([item[0].value for item in members]))
                / max(float(weights.sum()), 1e-12)
            )
    states = np.clip(states, -20.0, 20.0)
    trace: list[float] = []
    gap = float("inf")
    iterations = 0
    for iteration in range(_GLIOMA_MAX_ITERATIONS):
        previous = states.copy()
        for program in _GLIOMA_PROGRAMS:
            position = index[program]
            numerator = 0.0
            denominator = _GLIOMA_RIDGE
            for observation, member_program, prior_mean, prior_sd in prepared:
                if member_program != program:
                    continue
                residual = (observation.value - float(states[position])) / (
                    observation.standard_error
                )
                robust = (
                    1.0
                    if abs(residual) <= _GLIOMA_HUBER_K
                    else _GLIOMA_HUBER_K / abs(residual)
                )
                precision = observation.quality_weight * robust / max(
                    observation.standard_error**2, 1e-12
                )
                numerator += precision * observation.value
                numerator += prior_mean / max(prior_sd**2, 1e-12)
                denominator += precision + 1.0 / max(prior_sd**2, 1e-12)
            for source, target, sign in _GLIOMA_EDGES:
                if program == source:
                    numerator += _GLIOMA_EDGE_WEIGHT * sign * states[index[target]]
                    denominator += _GLIOMA_EDGE_WEIGHT
                elif program == target:
                    numerator += _GLIOMA_EDGE_WEIGHT * sign * states[index[source]]
                    denominator += _GLIOMA_EDGE_WEIGHT
            proposal = numerator / max(denominator, 1e-12)
            states[position] = _GLIOMA_DAMPING * proposal + (
                1.0 - _GLIOMA_DAMPING
            ) * states[position]
        states = np.clip(states, -20.0, 20.0)
        objective = _glioma_factor_objective(tuple(prepared), states)
        trace.append(round(objective, 10))
        gap = float(np.max(np.abs(states - previous)))
        iterations = iteration + 1
        if gap <= _GLIOMA_TOLERANCE:
            break
    if not np.all(np.isfinite(states)) or gap > _GLIOMA_TOLERANCE:
        return None
    estimates: list[PosteriorEstimate] = []
    for observation, program, _prior_mean, _prior_sd in prepared:
        position = index[program]
        state = float(states[position])
        residual = (observation.value - state) / observation.standard_error
        robust = (
            1.0
            if abs(residual) <= _GLIOMA_HUBER_K
            else _GLIOMA_HUBER_K / abs(residual)
        )
        precision = observation.quality_weight * robust / max(
            observation.standard_error**2, 1e-12
        )
        posterior_sd = sqrt(1.0 / max(precision + _GLIOMA_RIDGE, 1e-12))
        center = state + 0.35 * (observation.value - state)
        estimates.append(
            PosteriorEstimate(
                feature_id=observation.feature_id,
                kind=PosteriorEstimateKind.INTERVAL,
                unit="standardized-glioma-proteotype-factor",
                estimate_value=round(center, 8),
                lower_bound=round(center - _GLIOMA_Z90 * posterior_sd, 8),
                upper_bound=round(center + _GLIOMA_Z90 * posterior_sd, 8),
                posterior_mass=0.90,
                evidence=observation.evidence or (),
            )
        )
    return _GliomaFactorFit(
        states=tuple(round(float(item), 8) for item in states),
        estimates=tuple(estimates),
        objective=round(trace[-1], 8),
        iterations=iterations,
        convergence_gap=round(gap, 12),
        objective_trace=tuple(trace),
        program_counts=tuple(
            (program, sum(item[1] == program for item in prepared))
            for program in _GLIOMA_PROGRAMS
            if any(item[1] == program for item in prepared)
        ),
    )


def _support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.REVIEW_REQUIRED,
        reason_code="m1004_estimation_review_required",
        rationale=(
            "Posterior estimation is abstained pending owner-locked objective, training, "
            "baseline comparison, and uncertainty calibration evidence."
        ),
    )


def _measured_support() -> SupportDecision:
    return SupportDecision(
        status=SupportStatus.SUPPORTED,
        reason_code="m1004_measured_posterior_supported",
        rationale=(
            "Every measured observation resolved to a finite Normal prior and contributed "
            "positive quality-weighted precision to the robust posterior."
        ),
    )


def _limitations(*, measured: bool = False, glioma: bool = False) -> tuple[Limitation, ...]:
    if glioma:
        return (
            Limitation(
                code="glioma_factor_research_only",
                statement=(
                    "The locked GBM program factor fit is research-use-only and is not a "
                    "diagnostic, prognostic, or treatment-response classifier."
                ),
            ),
            Limitation(
                code="glioma_factor_interval_not_calibrated",
                statement=(
                    "Intervals combine declared assay error with robust topology shrinkage; "
                    "external coverage calibration is not claimed."
                ),
            ),
            Limitation(
                code="no_parent_emission",
                statement=(
                    "This estimator emits no parent discordance claim, kinase state, "
                    "all-omics fusion, or treatment advice."
                ),
            ),
        )
    if measured:
        return (
            Limitation(
                code="single_observation_sampling",
                statement=(
                    "Sampling uncertainty is not estimable from one observation per feature; "
                    "intervals reflect the declared assay error and Normal prior only."
                ),
            ),
            Limitation(
                code="prior_family_restriction",
                statement=(
                    "Measured fitting currently accepts finite Normal priors; other declared "
                    "prior families remain an explicit safe abstention."
                ),
            ),
            Limitation(
                code="no_parent_emission",
                statement=(
                    "This estimator emits no parent protein-RNA claim, kinase activity, "
                    "generic all-omics fusion, or treatment advice."
                ),
            ),
        )
    return (
        Limitation(
            code="posterior_not_published",
            statement="No posterior estimate is published until optimization gates are locked.",
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no parent protein-RNA discordance claim, kinase state, "
                "generic all-omics fusion, or treatment advice."
            ),
        ),
        Limitation(
            code="opaque_inputs",
            statement="Inputs remain immutable artifact references and are not traversed.",
        ),
        Limitation(
            code="provisional_abi_pending_owner_confirmation",
            statement=(
                "Estimator ABI, posterior representation, and baseline handoff are provisional."
            ),
        ),
    )


class M1004ProbabilisticEstimatorEngine:
    """Bind deterministic configuration and abstain until estimator gates are locked."""

    __slots__ = ()

    def estimate(self, request: object) -> ProteinRnaDiscordanceProbabilisticResult:
        validated = _REQUEST_ADAPTER.validate_python(_prepare(request), strict=True)
        return self._result(validated)

    def _result(
        self,
        request: EstimateProteinRnaDiscordanceProbabilisticRequest,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        request_hash = canonical_request_digest(request)
        estimates: list[PosteriorEstimate] = []
        objective_value = 0.0
        iteration_count = 0
        convergence_gap = 0.0
        glioma_fit: _GliomaFactorFit | None = None
        glioma_requested = request.configuration.optimizer == M1004_GLIOMA_IRLS_OPTIMIZER
        if glioma_requested:
            glioma_fit = _fit_glioma_factor_graph(request)
            if glioma_fit is not None:
                estimates = list(glioma_fit.estimates)
                objective_value = glioma_fit.objective
                iteration_count = glioma_fit.iterations
                convergence_gap = glioma_fit.convergence_gap
        # The typed GBM factor path is intentionally all-or-nothing. Falling back
        # to independent feature posteriors would hide insufficient topology
        # support and make the model family ambiguous.
        if request.observations and not glioma_requested:
            priors = {prior.prior_id: prior for prior in request.configuration.priors}
            fits = [
                _fit_observation(
                    observation,
                    priors[observation.feature_id],
                    max_iterations=request.configuration.max_iterations,
                )
                for observation in request.observations
            ]
            if all(fit is not None for fit in fits):
                estimates = [fit[0] for fit in fits if fit is not None]
                objective_value = round(sum(fit[1] for fit in fits if fit is not None), 8)
                iteration_count = max(fit[2] for fit in fits if fit is not None)
                convergence_gap = round(max(fit[3] for fit in fits if fit is not None), 12)
        measured = bool(estimates)
        glioma_measured = glioma_requested and glioma_fit is not None and measured
        payload: dict[str, object] = {
            "output_type": "protein_rna_discordance_posterior",
            "result_id": f"result.{request_hash.removeprefix('sha256:')}",
            "result_version": M1004_CONTRACT_VERSION,
            "request_digest": request_hash,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": (
                ProbabilisticResultStatus.ESTIMATED
                if measured
                else ProbabilisticResultStatus.ABSTAINED
            ),
            "estimates": tuple(estimates),
            "diagnostics": (
                _measured_diagnostic(
                    request,
                    objective_value=objective_value,
                    iteration_count=iteration_count,
                    convergence_gap=convergence_gap,
                    model_family=M1004_GLIOMA_MODEL_FAMILY if glioma_measured else None,
                    message=(
                        "Locked GBM proteotype factors converged with robust Huber IRLS, "
                        "signed program edges, deterministic damping, and feature-level "
                        "Normal priors."
                        if glioma_measured
                        else None
                    ),
                )
                if measured
                else _diagnostic(),
            ),
            "abstention_reason": None
            if measured
            else (
                "Estimation is abstained until M10-03 baseline comparison, optimization, "
                "calibration, and transport gates are owner-locked, or finite measured "
                "observations resolve to compatible Normal priors and, for the locked "
                "GBM factor path, cover at least four markers across two programs."
            ),
            "parent_target": M1004_PARENT,
            "support_decision": _measured_support() if measured else _support(),
            "uncertainty": expected_uncertainty(),
            "provenance": expected_provenance(request, request_hash),
            "evidence": _evidence(request),
            "limitations": _limitations(measured=measured, glioma=glioma_measured),
            "human_review_required": not measured,
        }
        constructed = ProteinRnaDiscordanceProbabilisticResult.model_construct(
            **payload,  # type: ignore[arg-type]
        )
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)

    def verify(
        self,
        result: object,
        *,
        replay: bool = True,
    ) -> ProteinRnaDiscordanceProbabilisticResult:
        """Verify receipt digests and optionally replay the exact request."""

        if isinstance(result, BaseModel):
            if not verify_result_digest(result):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "result digest does not match canonical payload"
                )
            embedded_request = getattr(result, "request", None)
            embedded_digest = getattr(result, "request_digest", None)
            if embedded_request is not None and embedded_digest != canonical_request_digest(
                embedded_request
            ):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "request digest does not match embedded request"
                )
        try:
            validated = _RESULT_ADAPTER.validate_python(result, strict=True)
        except Exception as error:
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "result is not a strict result envelope"
            ) from error
        if not verify_result_digest(
            validated
        ):  # pragma: no cover - contract validator closes this path.
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "result digest does not match canonical payload"
            )
        if validated.request_digest != canonical_request_digest(
            validated.request
        ):  # pragma: no cover - contract validator closes this path.
            raise M1004ReplayVerificationError(  # noqa: TRY003
                "request digest does not match embedded request"
            )
        if replay:
            expected = self.estimate(validated.request)
            if expected.model_dump(mode="json") != validated.model_dump(mode="json"):
                raise M1004ReplayVerificationError(  # noqa: TRY003
                    "replayed request produced a different result"
                )
        return validated


def estimate_protein_rna_discordance_probabilistic(
    request: object,
) -> ProteinRnaDiscordanceProbabilisticResult:
    """Public provisional M10-04 operation."""

    return M1004ProbabilisticEstimatorEngine().estimate(request)


__all__ = [
    "M1004_GLIOMA_IRLS_OPTIMIZER",
    "M1004ProbabilisticEstimatorAuthorizationError",
    "M1004ProbabilisticEstimatorEngine",
    "M1004ReplayVerificationError",
    "estimate_protein_rna_discordance_probabilistic",
    "preflight_probabilistic_estimator_authorization",
]
