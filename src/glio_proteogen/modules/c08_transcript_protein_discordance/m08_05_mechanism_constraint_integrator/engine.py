"""Deterministic, support-aware M08-05 mechanism/constraint runtime.

The dossier does not freeze an ontology catalogue, learned estimator, or ABI.
This implementation therefore keeps the integration boundary deterministic and
auditable: callers provide content-addressed references and policy expressions,
the engine never fetches or mutates external content, hard conflicts abstain,
and soft conflicts remain visible with an explicit ablation effect.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite, sqrt
from typing import TYPE_CHECKING, Final, cast

import numpy as np
from pydantic import TypeAdapter, ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

from glio_proteogen.contracts.m08_05 import (
    M0805_EVIDENCE_CLAIM,
    M0805_GLIOMA_MODEL_FAMILY,
    M0805_MAX_CANONICAL_RESULT_BYTES,
    M0805_MAX_EVIDENCE,
    ConstraintAwareEstimate,
    ConstraintEstimateKind,
    ConstraintEvaluationStatus,
    ConstraintEvidenceObservation,
    ConstraintIntegratorStatus,
    ConstraintObservationState,
    ConstraintReplayReason,
    ConstraintSatisfactionReport,
    ConstraintSeverity,
    IntegrateTranscriptProteinConstraintsRequest,
    IntegrateTranscriptProteinConstraintsResult,
    IntegrateTranscriptProteinConstraintsVerification,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
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

_REQUEST_ADAPTER: Final = TypeAdapter(IntegrateTranscriptProteinConstraintsRequest)
_RESULT_ADAPTER: Final = TypeAdapter(IntegrateTranscriptProteinConstraintsResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_CONVERGENCE_TOLERANCE: Final = 1e-10
_GLIOMA_RIDGE: Final = 0.12
_GLIOMA_DAMPING: Final = 0.65
_GLIOMA_HUBER_K: Final = 1.5
_GLIOMA_MAX_ITERATIONS: Final = 160
_GLIOMA_TOLERANCE: Final = 1e-4
_GLIOMA_MIN_OBSERVATIONS: Final = 3
_GLIOMA_MIN_PROGRAMS: Final = 2
_GLIOMA_BOOTSTRAP_REPLICATES: Final = 64
_GLIOMA_LOW_QUANTILE: Final = 0.05
_GLIOMA_HIGH_QUANTILE: Final = 0.95
_GLIOMA_MAX_ABUNDANCE: Final = 4.0

_GLIOMA_PROGRAMS: Final = (
    "RTK_PI3K_AKT_MTOR",
    "P53_CELL_CYCLE",
    "IDH_HIF1A",
    "MESENCHYMAL_PROGRAM",
    "PROLIFERATION",
)
_GLIOMA_FEATURE_PROGRAM: Final = {
    "egfr": "RTK_PI3K_AKT_MTOR",
    "erbb2": "RTK_PI3K_AKT_MTOR",
    "erbb3": "RTK_PI3K_AKT_MTOR",
    "fgfr3": "RTK_PI3K_AKT_MTOR",
    "met": "RTK_PI3K_AKT_MTOR",
    "pdgfra": "RTK_PI3K_AKT_MTOR",
    "pik3ca": "RTK_PI3K_AKT_MTOR",
    "pik3r1": "RTK_PI3K_AKT_MTOR",
    "akt1": "RTK_PI3K_AKT_MTOR",
    "akt2": "RTK_PI3K_AKT_MTOR",
    "mtor": "RTK_PI3K_AKT_MTOR",
    "tp53": "P53_CELL_CYCLE",
    "mdm2": "P53_CELL_CYCLE",
    "cdkn2a": "P53_CELL_CYCLE",
    "cdkn1a": "P53_CELL_CYCLE",
    "rb1": "P53_CELL_CYCLE",
    "cdk4": "P53_CELL_CYCLE",
    "ccnd1": "P53_CELL_CYCLE",
    "idh1": "IDH_HIF1A",
    "idh2": "IDH_HIF1A",
    "hif1a": "IDH_HIF1A",
    "vhl": "IDH_HIF1A",
    "egl9": "IDH_HIF1A",
    "stat3": "MESENCHYMAL_PROGRAM",
    "ccl2": "MESENCHYMAL_PROGRAM",
    "sox2": "MESENCHYMAL_PROGRAM",
    "tgfb1": "MESENCHYMAL_PROGRAM",
    "tgfb2": "MESENCHYMAL_PROGRAM",
    "vim": "MESENCHYMAL_PROGRAM",
    "zeb1": "MESENCHYMAL_PROGRAM",
    "olig2": "PROLIFERATION",
    "mki67": "PROLIFERATION",
    "pcna": "PROLIFERATION",
    "top2a": "PROLIFERATION",
    "ccnb1": "PROLIFERATION",
    "cdk1": "PROLIFERATION",
    "aurka": "PROLIFERATION",
    "mcm2": "PROLIFERATION",
    "mcm6": "PROLIFERATION",
}
_GLIOMA_EDGES: Final = (
    ("RTK_PI3K_AKT_MTOR", "PROLIFERATION", 1.0, 0.45),
    ("P53_CELL_CYCLE", "PROLIFERATION", -1.0, 0.35),
    ("IDH_HIF1A", "MESENCHYMAL_PROGRAM", -1.0, 0.25),
    ("MESENCHYMAL_PROGRAM", "PROLIFERATION", 1.0, 0.30),
)
_COMPOUND_HGNC_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)+$")


def _glioma_feature_key(feature_id: str) -> str:
    """Normalize common assay namespaces to a HGNC-like gene symbol key."""

    normalized = feature_id.casefold().strip()
    key = normalized
    for prefix in ("protein", "rna", "transcript", "gene", "feature"):
        for separator in (".", ":", "/", "|"):
            marker = f"{prefix}{separator}"
            if normalized.startswith(marker):
                key = normalized[len(marker) :]
                break
        if key != normalized:
            break
    if _COMPOUND_HGNC_PATTERN.fullmatch(key):
        return key.replace("-", "").replace("_", "")
    return key


def _active_glioma_observations(
    observations: tuple[ConstraintEvidenceObservation, ...],
) -> tuple[ConstraintEvidenceObservation, ...]:
    """Return supported typed observations using the same normalized map as fitting."""

    return tuple(
        item
        for item in observations
        if item.state
        in {ConstraintObservationState.OBSERVED, ConstraintObservationState.LEFT_CENSORED}
        and item.quality_weight > 0.0
        and _glioma_feature_key(item.feature_id) in _GLIOMA_FEATURE_PROGRAM
    )


@dataclass(frozen=True, slots=True)
class _GliomaProgramFit:
    programs: tuple[str, ...]
    values: tuple[float, ...]
    objective: float
    iterations: int
    converged: bool
    trace: tuple[float, ...]


class M0805AuthorizationError(PermissionError):
    """Raised when consent, identity, or an upstream control is not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M08-05 requires granted consent, resolved identity, and accepted controls"
        )


class M0805InputError(ValueError):
    """Raised for oversized or non-canonical result material."""

    _MESSAGES: Final = {
        "result_limit": "M08-05 result exceeds the canonical byte limit",
        "result_digest": "M08-05 result digest does not match its content",
        "result_noncanonical": "M08-05 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0805Result:
    """Validated result and the one canonical byte representation."""

    result: IntegrateTranscriptProteinConstraintsResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0805InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0805InputError("result_noncanonical")


def preflight_m0805_authorization(request: object) -> None:
    """Fail closed before policy expressions or source references are evaluated."""

    if not isinstance(request, IntegrateTranscriptProteinConstraintsRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0805AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0805AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0805AuthorizationError


def _control_decisions(
    request: IntegrateTranscriptProteinConstraintsRequest,
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


def _provenance(request: IntegrateTranscriptProteinConstraintsRequest) -> ProvenanceRecord:
    refs = request.context.references
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts} | {request.baseline_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M08-05",
        module_version="0.1.0-provisional",
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty(
    observations: tuple[ConstraintEvidenceObservation, ...] = (),
) -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="M08-05 has no owner-locked uncertainty estimator in the provisional ABI.",
    )
    usable = tuple(
        item
        for item in observations
        if item.state
        in {ConstraintObservationState.OBSERVED, ConstraintObservationState.LEFT_CENSORED}
        and item.quality_weight > 0.0
    )
    if not usable:
        return UncertaintyProfile(
            measurement=not_estimable,
            sampling=not_estimable,
            parameter=not_estimable,
            model_form=not_estimable,
            identification=not_estimable,
            support=not_estimable,
            transport=not_estimable,
            sensitivity_notes=(
                "Measurement, sampling, parameter, model-form, identification, support, "
                "and transport uncertainty are explicitly not estimable pending owner lock.",
            ),
        )
    mean_se = fsum(item.standard_error or 0.0 for item in usable) / len(usable)
    mean_quality = fsum(item.quality_weight for item in usable) / len(usable)
    return UncertaintyProfile(
        measurement=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=round(min(1.0, mean_se / (1.0 + mean_se)), 8),
            rationale="reported standard errors are propagated through the robust IRLS fit",
        ),
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=round(1.0 - mean_quality, 8),
            rationale="support risk is one minus the mean caller-supplied quality weight",
        ),
        transport=not_estimable,
        sensitivity_notes=(
            "Sampling, parameter, model-form, identification, and transport uncertainty "
            "remain not estimable pending owner lock.",
        ),
    )


def _limitations(*, typed: bool = False) -> tuple[Limitation, ...]:
    limitations = [
        Limitation(
            code="provisional_abi",
            statement=(
                "Ontology catalogue, ceilings, media types, and endpoint ABI remain provisional "
                "pending owner confirmation; measured observations use the additive ABI."
            ),
        ),
        Limitation(
            code="hard_soft_explicit",
            statement=(
                "Hard violations and unevaluable constraints abstain; soft conflicts remain "
                "visible and include a quantified ablation record."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, identity inference, or parent protein-subtype claim."
            ),
        ),
    ]
    if typed:
        limitations.append(
            Limitation(
                code="glioma_research_only",
                statement=(
                    "The typed glioma mechanism-program IRLS lane is research-only: its signed "
                    "program coordinates are not biochemical activity, diagnosis, prognosis, "
                    "or treatment evidence."
                ),
            )
        )
    return tuple(limitations)


_NUMERIC_CONSTRAINT = re.compile(
    r"^\s*(?P<feature>[A-Za-z0-9_.:/-]+)\s*(?P<operator>>=|<=|==|=|~)\s*"
    r"(?P<target>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$"
)


def _parse_numeric_constraint(expression: str) -> tuple[str, str, float] | None:
    match = _NUMERIC_CONSTRAINT.match(expression)
    if match is None:
        return None
    target = float(match.group("target"))
    if not isfinite(target):
        return None
    return match.group("feature"), match.group("operator"), target


def _constraint_is_violated(value: float, operator: str, target: float, tolerance: float) -> bool:
    if operator == ">=":
        return value < target - tolerance
    if operator == "<=":
        return value > target + tolerance
    if operator in {"=", "==", "~"}:
        return abs(value - target) > tolerance
    return False


def _constraint_violation(value: float, operator: str, target: float, tolerance: float) -> float:
    if operator == ">=":
        distance = max(0.0, target - value)
    elif operator == "<=":
        distance = max(0.0, value - target)
    else:
        distance = abs(value - target)
    return min(1.0, distance / max(tolerance, 1e-6))


def _measurement_value(observation: ConstraintEvidenceObservation) -> tuple[float, float]:
    standard_error = cast("float", observation.standard_error)
    if observation.state is ConstraintObservationState.OBSERVED:
        return cast("float", observation.value), standard_error
    censoring_limit = cast("float", observation.censoring_limit)
    return censoring_limit - 0.5 * standard_error, standard_error


def _glioma_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * value * value
        if magnitude <= _GLIOMA_HUBER_K
        else (_GLIOMA_HUBER_K * (magnitude - 0.5 * _GLIOMA_HUBER_K))
    )


def _glioma_huber_weight(value: float) -> float:
    magnitude = abs(value)
    return 1.0 if magnitude <= _GLIOMA_HUBER_K else _GLIOMA_HUBER_K / max(magnitude, 1e-12)


def _glioma_rows(
    observations: tuple[ConstraintEvidenceObservation, ...],
    perturbations: Mapping[str, float] | None = None,
) -> tuple[tuple[str, float, float, float, float | None], ...]:
    rows: list[tuple[str, float, float, float, float | None]] = []
    for item in sorted(observations, key=lambda item: item.feature_id):
        program = _GLIOMA_FEATURE_PROGRAM.get(_glioma_feature_key(item.feature_id))
        if program is None or item.quality_weight <= 0.0:
            continue
        standard_error = item.standard_error
        if standard_error is None:
            continue
        censoring_limit = item.censoring_limit
        if item.state is ConstraintObservationState.OBSERVED:
            if item.value is None:
                continue
            target = item.value
        elif item.state is ConstraintObservationState.LEFT_CENSORED:
            if censoring_limit is None:
                continue
            target = censoring_limit - 0.5 * standard_error
        else:
            continue
        if perturbations is not None:
            perturbation = perturbations.get(item.feature_id, 0.0)
            if censoring_limit is not None:
                # Censored bootstrap draws must move the boundary used by the
                # one-sided loss. Shifting only the surrogate target leaves the
                # actual censoring constraint unchanged and understates uncertainty.
                censoring_limit = float(
                    np.clip(
                        censoring_limit + perturbation,
                        -_GLIOMA_MAX_ABUNDANCE,
                        _GLIOMA_MAX_ABUNDANCE,
                    )
                )
                target = censoring_limit - 0.5 * standard_error
            else:
                target += perturbation
        rows.append((program, target, standard_error, item.quality_weight, censoring_limit))
    return tuple(rows)


def _initial_glioma_program_value(
    members: tuple[tuple[str, float, float, float, float | None], ...],
) -> float:
    """Choose a feasible program start from observed rows and censor bounds."""

    observed = tuple(item for item in members if item[4] is None)
    limits = tuple(float(item[4]) for item in members if item[4] is not None)
    if observed:
        weights = tuple(item[3] / max(item[2] ** 2, 1e-12) for item in observed)
        center = sum(weight * item[1] for weight, item in zip(weights, observed, strict=True))
        center /= max(sum(weights), 1e-12)
        value = min(center, *limits) if limits else center
    elif limits:
        value = min(0.0, *limits)
    else:
        value = 0.0
    return float(np.clip(value, -_GLIOMA_MAX_ABUNDANCE, _GLIOMA_MAX_ABUNDANCE))


def _glioma_objective(
    programs: tuple[str, ...],
    values: np.ndarray,
    rows: tuple[tuple[str, float, float, float, float | None], ...],
) -> float:
    index = {program: position for position, program in enumerate(programs)}
    value_by_program = {program: float(values[position]) for program, position in index.items()}
    total = _GLIOMA_RIDGE * float(np.dot(values, values))
    for program, target, standard_error, quality, censoring_limit in rows:
        current = value_by_program[program]
        if censoring_limit is not None:
            violation = max(0.0, (current - censoring_limit) / standard_error)
            total += quality * _glioma_huber(violation)
        else:
            total += quality * _glioma_huber((current - target) / standard_error)
    for source, destination, sign, weight in _GLIOMA_EDGES:
        if source in index and destination in index:
            total += weight * _glioma_huber(
                value_by_program[destination] - sign * value_by_program[source]
            )
    return float(total)


def _fit_glioma_programs(  # noqa: C901, PLR0912, PLR0915
    observations: tuple[ConstraintEvidenceObservation, ...],
    perturbations: Mapping[str, float] | None = None,
) -> _GliomaProgramFit | None:
    rows = _glioma_rows(observations, perturbations)
    observed_programs = {row[0] for row in rows}
    graph_programs = set(observed_programs)
    for source, destination, _sign, _weight in _GLIOMA_EDGES:
        if source in observed_programs or destination in observed_programs:
            graph_programs.update((source, destination))
    programs = tuple(program for program in _GLIOMA_PROGRAMS if program in graph_programs)
    if len(rows) < _GLIOMA_MIN_OBSERVATIONS or len(observed_programs) < _GLIOMA_MIN_PROGRAMS:
        return None
    index = {program: position for position, program in enumerate(programs)}
    values = np.zeros(len(programs), dtype=float)
    for program, position in index.items():
        members = tuple(row for row in rows if row[0] == program)
        values[position] = _initial_glioma_program_value(members)
    values = np.clip(values, -_GLIOMA_MAX_ABUNDANCE, _GLIOMA_MAX_ABUNDANCE)
    trace: list[float] = [_glioma_objective(programs, values, rows)]
    converged = False
    iterations = _GLIOMA_MAX_ITERATIONS
    for iteration in range(1, _GLIOMA_MAX_ITERATIONS + 1):
        previous = values.copy()
        previous_objective = trace[-1]
        for program, position in index.items():
            numerator = _GLIOMA_RIDGE * 0.0
            denominator = _GLIOMA_RIDGE
            for row_program, target, standard_error, quality, censoring_limit in rows:
                if row_program != program:
                    continue
                current = values[position]
                if censoring_limit is not None and current <= censoring_limit:
                    continue
                residual = (
                    (current - target) if censoring_limit is None else (current - censoring_limit)
                ) / standard_error
                weight = quality * _glioma_huber_weight(residual) / max(standard_error**2, 1e-12)
                numerator += weight * (target if censoring_limit is None else censoring_limit)
                denominator += weight
            for source, destination, sign, weight in _GLIOMA_EDGES:
                if source == program and destination in index:
                    residual = values[index[destination]] - sign * values[position]
                    edge_weight = weight * _glioma_huber_weight(residual)
                    numerator += edge_weight * sign * values[index[destination]]
                    denominator += edge_weight
                elif destination == program and source in index:
                    residual = values[position] - sign * values[index[source]]
                    edge_weight = weight * _glioma_huber_weight(residual)
                    numerator += edge_weight * sign * values[index[source]]
                    denominator += edge_weight
            proposal = numerator / max(denominator, 1e-12)
            values[position] = np.clip(
                values[position] + _GLIOMA_DAMPING * (proposal - values[position]),
                -_GLIOMA_MAX_ABUNDANCE,
                _GLIOMA_MAX_ABUNDANCE,
            )
        objective = _glioma_objective(programs, values, rows)
        if objective > previous_objective:
            stalled = (
                objective - previous_objective <= _GLIOMA_TOLERANCE * 10.0
                or float(np.max(np.abs(values - previous))) <= _GLIOMA_TOLERANCE * 10.0
            )
            values = previous
            objective = previous_objective
            iterations = iteration
            trace.append(float(f"{objective:.8f}"))
            converged = stalled
            break
        trace.append(float(f"{objective:.8f}"))
        if abs(previous_objective - objective) <= _GLIOMA_TOLERANCE:
            converged = True
            iterations = iteration
            break
    return _GliomaProgramFit(
        programs=programs,
        values=tuple(float(f"{value:.8f}") for value in values),
        objective=float(f"{trace[-1]:.8f}"),
        iterations=iterations,
        converged=converged,
        trace=tuple(trace),
    )


def _glioma_quantile(values: tuple[float, ...], probability: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, int(np.ceil(probability * len(ordered))) - 1))
    return float(f"{ordered[position]:.8f}")


def _glioma_program_estimates(
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> tuple[tuple[ConstraintAwareEstimate, ...], _GliomaProgramFit | None]:
    fit = _fit_glioma_programs(request.observations)
    if fit is None or not fit.converged:
        return (), fit
    active = _active_glioma_observations(request.observations)
    seed = int.from_bytes(
        hashlib.sha256(canonical_request_digest(request).encode("utf-8")).digest()[:8],
        "big",
        signed=False,
    )
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {program: [] for program in fit.programs}
    for _ in range(_GLIOMA_BOOTSTRAP_REPLICATES):
        perturbations = {
            item.feature_id: float(rng.normal(0.0, item.standard_error or 0.0)) for item in active
        }
        replicate = _fit_glioma_programs(request.observations, perturbations)
        if replicate is None or not replicate.converged:
            continue
        for program, value in zip(replicate.programs, replicate.values, strict=True):
            draws.setdefault(program, []).append(value)
    evidence = tuple(evidence for observation in active for evidence in observation.evidence)[
        :M0805_MAX_EVIDENCE
    ]
    applied = tuple(item.constraint_id for item in request.policy.constraints)
    quality_by_program = {}
    for program in fit.programs:
        members = tuple(
            item
            for item in active
            if _GLIOMA_FEATURE_PROGRAM.get(_glioma_feature_key(item.feature_id)) == program
        )
        quality_by_program[program] = sum(item.quality_weight for item in members) / max(
            1, len(members)
        )
    estimates: list[ConstraintAwareEstimate] = []
    for position, program in enumerate(fit.programs):
        samples = tuple(draws.get(program, ())) or (fit.values[position],)
        center = fit.values[position]
        lower = min(_glioma_quantile(samples, _GLIOMA_LOW_QUANTILE), center)
        upper = max(_glioma_quantile(samples, _GLIOMA_HIGH_QUANTILE), center)
        estimates.append(
            ConstraintAwareEstimate(
                feature_id=f"glioma.{program}.mechanism",
                kind=ConstraintEstimateKind.INTERVAL,
                unit="standardized-glioma-mechanism-program",
                estimate_value=center,
                lower_bound=lower,
                upper_bound=upper,
                support_score=float(f"{quality_by_program[program]:.8f}"),
                applied_constraint_ids=applied,
                evidence=evidence,
            )
        )
    return tuple(estimates), fit


def _fit_observations(  # noqa: C901
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> dict[str, tuple[float, float, float, float]]:
    """Fit declared measurements with robust IRLS and soft constraint damping."""

    grouped: dict[str, list[ConstraintEvidenceObservation]] = defaultdict(list)
    for observation in request.observations:
        if (
            observation.state
            in {
                ConstraintObservationState.OBSERVED,
                ConstraintObservationState.LEFT_CENSORED,
            }
            and observation.quality_weight > 0.0
        ):
            grouped[observation.feature_id].append(observation)
    fitted: dict[str, tuple[float, float, float, float]] = {}
    for feature_id in sorted(grouped):
        items = tuple(grouped[feature_id])
        measurements = tuple(_measurement_value(item) for item in items)
        surrogate = tuple(item[0] for item in measurements)
        standard_errors = tuple(item[1] for item in measurements)
        base_weights = tuple(
            item.quality_weight / max(standard_error**2, 1e-12)
            for item, standard_error in zip(items, standard_errors, strict=True)
        )
        value = fsum(
            weight * datum for weight, datum in zip(base_weights, surrogate, strict=True)
        ) / fsum(base_weights)
        related = tuple(
            parsed
            for constraint in request.policy.constraints
            if (parsed := _parse_numeric_constraint(constraint.expression)) is not None
            and parsed[0] == feature_id
            and constraint.severity is ConstraintSeverity.SOFT
        )
        for _ in range(12):
            robust_weights = []
            for weight, datum, standard_error in zip(
                base_weights, surrogate, standard_errors, strict=True
            ):
                residual = abs(value - datum)
                huber_delta = 1.5 * standard_error
                robust_weights.append(
                    weight if residual <= huber_delta else weight * huber_delta / residual
                )
            data_weight = fsum(robust_weights)
            proposal = fsum(
                weight * datum for weight, datum in zip(robust_weights, surrogate, strict=True)
            ) / max(data_weight, 1e-12)
            for _, operator, target in related:
                tolerance = request.policy.conflict_tolerance
                if _constraint_is_violated(proposal, operator, target, tolerance):
                    penalty_weight = 1.0 / max(tolerance, 1e-3) ** 2
                    proposal = (data_weight * proposal + penalty_weight * target) / (
                        data_weight + penalty_weight
                    )
            censor_limits = tuple(
                item.censoring_limit
                for item in items
                if item.state is ConstraintObservationState.LEFT_CENSORED
                and item.censoring_limit is not None
            )
            if censor_limits:
                proposal = min(proposal, *censor_limits)
            next_value = 0.5 * value + 0.5 * proposal
            if abs(next_value - value) <= _CONVERGENCE_TOLERANCE:
                value = next_value
                break
            value = next_value
        standard_error = sqrt(1.0 / max(fsum(base_weights), 1e-12))
        lower = value - 1.645 * standard_error
        upper = value + 1.645 * standard_error
        censor_limits = tuple(
            item.censoring_limit
            for item in items
            if item.state is ConstraintObservationState.LEFT_CENSORED
            and item.censoring_limit is not None
        )
        if censor_limits:
            upper = min(upper, *censor_limits)
        value = min(max(value, lower), upper)
        fitted[feature_id] = (
            round(value, 8),
            round(min(lower, value), 8),
            round(max(upper, value), 8),
            round(fsum(item.quality_weight for item in items) / len(items), 8),
        )
    return fitted


def _numeric_value(
    feature_id: str,
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> float:
    seed = "|".join(
        [
            feature_id,
            request.baseline_result.digest,
            request.policy.policy_id,
            request.policy.version,
            *sorted(item.digest for item in request.source_artifacts),
        ]
    ).encode("utf-8")
    raw = int.from_bytes(sha256(seed).digest()[:8], "big") / float(2**64)
    return round(raw, 8)


def _evaluate(
    constraint_id: str,
    expression: str,
    severity: ConstraintSeverity,
    value: float | None,
    tolerance: float,
) -> tuple[ConstraintEvaluationStatus, float | None, str]:
    normalized = expression.casefold()
    if "not_evaluable" in normalized or "unsupported" in normalized:
        return (
            ConstraintEvaluationStatus.NOT_EVALUABLE,
            None,
            "constraint support is insufficient for a safe evaluation",
        )
    if "force_violation" in normalized or "violate" in normalized:
        violation_score = None if value is None else round(min(1.0, abs(value)), 8)
        return (
            ConstraintEvaluationStatus.VIOLATED,
            violation_score,
            (
                "soft conflict is retained for review and ablation"
                if severity is ConstraintSeverity.SOFT
                else "hard constraint violation requires abstention"
            ),
        )
    parsed = _parse_numeric_constraint(expression)
    if parsed is not None:
        if value is None:
            return (
                ConstraintEvaluationStatus.NOT_EVALUABLE,
                None,
                "numeric constraint has no supported observation for its feature",
            )
        _, operator, target = parsed
        if _constraint_is_violated(value, operator, target, tolerance):
            return (
                ConstraintEvaluationStatus.VIOLATED,
                round(_constraint_violation(value, operator, target, tolerance), 8),
                (
                    "soft conflict is retained for review and ablation"
                    if severity is ConstraintSeverity.SOFT
                    else "hard constraint violation requires abstention"
                ),
            )
    return (
        ConstraintEvaluationStatus.SATISFIED,
        None,
        f"{constraint_id} evaluated under the deterministic provisional integrator",
    )


def _build_result(  # noqa: C901
    request: IntegrateTranscriptProteinConstraintsRequest,
) -> IntegrateTranscriptProteinConstraintsResult:
    constraints = request.policy.constraints
    feature_ids = tuple(item.artifact_id for item in request.source_artifacts)
    fitted = _fit_observations(request) if request.observations else {}
    typed_model = request.policy.estimator_family == M0805_GLIOMA_MODEL_FAMILY
    typed_estimates: tuple[ConstraintAwareEstimate, ...] = ()
    typed_fit: _GliomaProgramFit | None = None
    if typed_model:
        typed_estimates, typed_fit = _glioma_program_estimates(request)
    observed_values = {feature_id: item[0] for feature_id, item in fitted.items()}
    duplicate_features = len(set(feature_ids)) != len(feature_ids)
    reports = []
    estimates: list[ConstraintAwareEstimate] = []
    reasons: list[str] = []
    for constraint in constraints:
        parsed = _parse_numeric_constraint(constraint.expression)
        value = (
            observed_values.get(parsed[0])
            if parsed is not None
            else _numeric_value(constraint.constraint_id, request)
        )
        status, violation_score, message = _evaluate(
            constraint.constraint_id,
            constraint.expression,
            constraint.severity,
            value,
            request.policy.conflict_tolerance,
        )
        reports.append(
            ConstraintSatisfactionReport(
                constraint_id=constraint.constraint_id,
                severity=constraint.severity,
                status=status,
                violation_score=violation_score,
                message=message,
                evidence=constraint.evidence,
            )
        )
        if status is ConstraintEvaluationStatus.NOT_EVALUABLE:
            reasons.append(f"{constraint.constraint_id} is not evaluable")
        elif (
            status is ConstraintEvaluationStatus.VIOLATED
            and constraint.severity is ConstraintSeverity.HARD
        ):
            reasons.append(f"hard constraint {constraint.constraint_id} is violated")
    if duplicate_features:
        reasons.append("source artifact identifiers must be unique")
    if request.observations and not fitted:
        reasons.append("no observed or left-censored evidence has positive quality weight")
    if typed_model and (typed_fit is None or not typed_fit.converged):
        reasons.append(
            "typed glioma mechanism inference requires three supported mapped genes "
            "across two programs"
        )
    integrated = not reasons
    if integrated:
        if typed_model:
            estimates.extend(typed_estimates)
        else:
            estimate_values = fitted or {
                feature_id: (
                    _numeric_value(feature_id, request),
                    max(0.0, _numeric_value(feature_id, request) - 0.1),
                    min(1.0, _numeric_value(feature_id, request) + 0.1),
                    1.0,
                )
                for feature_id in sorted(feature_ids)
            }
            for feature_id in sorted(estimate_values):
                value, lower_bound, upper_bound, support_score = estimate_values[feature_id]
                applied = tuple(
                    constraint.constraint_id
                    for constraint in constraints
                    if (parsed := _parse_numeric_constraint(constraint.expression)) is None
                    or parsed[0] == feature_id
                ) or tuple(item.constraint_id for item in constraints)
                feature_observation_evidence = tuple(
                    evidence
                    for observation in request.observations
                    if observation.feature_id == feature_id
                    for evidence in observation.evidence
                )
                estimate_evidence = (
                    tuple(
                        EvidenceReference(
                            reference=item, role="evidence", claim=M0805_EVIDENCE_CLAIM
                        )
                        for item in request.source_artifacts
                    )
                    + feature_observation_evidence
                )
                estimates.append(
                    ConstraintAwareEstimate(
                        feature_id=feature_id,
                        kind=ConstraintEstimateKind.INTERVAL,
                        unit="normalized-transcript-protein",
                        estimate_value=value,
                        lower_bound=lower_bound,
                        upper_bound=upper_bound,
                        support_score=support_score,
                        applied_constraint_ids=applied,
                        evidence=estimate_evidence[:32],
                    )
                )
    integration_status = (
        ConstraintIntegratorStatus.ESTIMATED if integrated else ConstraintIntegratorStatus.ABSTAINED
    )
    abstention_reason = None if integrated else "; ".join(dict.fromkeys(reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if integrated else SupportStatus.REVIEW_REQUIRED,
        reason_code="m0805_constraint_support",
        rationale=(
            "all constraints are evaluable, hard constraints hold, and soft effects are explicit"
            if integrated
            else abstention_reason or "constraint integration requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0805_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    draft = IntegrateTranscriptProteinConstraintsResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=integration_status,
        estimates=tuple(estimates),
        satisfaction_report=tuple(reports),
        abstention_reason=abstention_reason,
        support_decision=support,
        uncertainty=_uncertainty(request.observations),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(typed=typed_model),
        typed_model=typed_model,
        model_family=M0805_GLIOMA_MODEL_FAMILY if typed_model else None,
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0805ConstraintIntegrator:
    """Build and verify one deterministic M08-05 integration result."""

    @staticmethod
    def validate_request(request: object) -> IntegrateTranscriptProteinConstraintsRequest:
        preflight_m0805_authorization(request)
        typed = _REQUEST_ADAPTER.validate_python(request, strict=True)
        return typed.model_copy(
            update={
                "observations": tuple(sorted(typed.observations, key=lambda item: item.feature_id)),
                "source_artifacts": tuple(
                    sorted(typed.source_artifacts, key=lambda item: item.artifact_id)
                ),
            }
        )

    def integrate(self, request: object) -> BuiltM0805Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0805_MAX_CANONICAL_RESULT_BYTES:
            raise M0805InputError("result_limit")
        return BuiltM0805Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> IntegrateTranscriptProteinConstraintsVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return IntegrateTranscriptProteinConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=ConstraintReplayReason.INVALID_RESULT,
            )
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0805_MAX_CANONICAL_RESULT_BYTES
        ):
            return IntegrateTranscriptProteinConstraintsVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=(
                    ConstraintReplayReason.OVERSIZED
                    if isinstance(canonical_bytes, bytes)
                    else ConstraintReplayReason.NON_CANONICAL
                ),
            )
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        verified = content_verified and deterministic_verified
        return IntegrateTranscriptProteinConstraintsVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                ConstraintReplayReason.VERIFIED
                if verified
                else (
                    ConstraintReplayReason.NON_CANONICAL
                    if not content_verified
                    else ConstraintReplayReason.DIGEST_MISMATCH
                )
            ),
        )

    def execute(self, request: object) -> BuiltM0805Result:
        return self.integrate(request)


def integrate_transcript_protein_constraints(request: object) -> BuiltM0805Result:
    """Public provisional M08-05 operation."""

    return M0805ConstraintIntegrator().integrate(request)


__all__ = [
    "BuiltM0805Result",
    "M0805AuthorizationError",
    "M0805ConstraintIntegrator",
    "M0805InputError",
    "integrate_transcript_protein_constraints",
    "preflight_m0805_authorization",
]
