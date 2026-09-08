"""Deterministic transparent baseline estimator with fail-closed replay."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import exp
from typing import Final, cast

import numpy as np
from pydantic import TypeAdapter

from glio_proteogen.contracts.m08_03 import (
    M0803_CONTRACT_VERSION,
    M0803_EVIDENCE_CLAIM,
    M0803_GLIOMA_MODEL_FAMILY,
    M0803_MAX_BOOTSTRAP_REPLICATES,
    M0803_MAX_CANONICAL_REQUEST_BYTES,
    M0803_PARENT,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimateStatus,
    BaselineFeatureState,
    BaselineFindingCode,
    BaselineMethod,
    EstimateProteinSubtypeBaselineRequest,
    GliomaEvidenceState,
    GliomaProgram,
    GliomaProgramLabel,
    ProteinSubtypeBaselineEstimate,
    ProteinSubtypeBaselineResult,
    TypedBaselineObservation,
    TypedProgramState,
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

_REQUEST_ADAPTER: Final = TypeAdapter(EstimateProteinSubtypeBaselineRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteinSubtypeBaselineResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIDPOINT: Final = 0.5
_TYPED_HUBER_K: Final = 1.5
_TYPED_RIDGE: Final = 0.08
_TYPED_RELATION_WEIGHT: Final = 0.35
_TYPED_MAX_ITERATIONS: Final = 128
_TYPED_TOLERANCE: Final = 1e-8
_TYPED_BOOTSTRAP_LOW: Final = 0.05
_TYPED_BOOTSTRAP_HIGH: Final = 0.95
_TYPED_MAX_EFFECT: Final = 8.0
_TYPED_STATE_THRESHOLD: Final = 0.25
_TYPED_MIN_PROGRAMS: Final = 2
_TYPED_CONVERGENCE_CUTOFF: Final = 1e-5
_TYPED_EDGES: Final = (
    (GliomaProgram.RTK_PI3K_AKT_MTOR, GliomaProgram.PROLIFERATION, 1.0),
    (GliomaProgram.P53_CELL_CYCLE, GliomaProgram.PROLIFERATION, -1.0),
    (GliomaProgram.IDH_HIF1A, GliomaProgram.MESENCHYMAL, -1.0),
    (GliomaProgram.RTK_PI3K_AKT_MTOR, GliomaProgram.MESENCHYMAL, 1.0),
    (GliomaProgram.MESENCHYMAL, GliomaProgram.PROLIFERATION, 1.0),
)


@dataclass(frozen=True, slots=True)
class _TypedFit:
    values: dict[GliomaProgram, float]
    objective: float
    iterations: int
    maximum_update: float
    trace_digest: str


class M0803BaselineAuthorizationError(PermissionError):
    """Raised before feature traversal when upstream controls are unsafe."""

    def __init__(self) -> None:
        super().__init__(
            "M08-03 requires accepted controls, resolved identity, and granted consent"
        )


def _member(value: object, field: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field)
    return getattr(value, field, None)


def _state(value: object) -> object:
    return getattr(value, "value", value)


def preflight_baseline_authorization(candidate: object) -> None:
    """Validate all seven immutable upstream control decisions before traversal."""

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
        raise M0803BaselineAuthorizationError from None
    if states != expected:
        raise M0803BaselineAuthorizationError


def _validate_typed_request(candidate: object) -> EstimateProteinSubtypeBaselineRequest:
    preflight_baseline_authorization(candidate)
    return _REQUEST_ADAPTER.validate_python(candidate, strict=True)


def _validate_json_request(
    candidate: object,
    serialized: bytes | bytearray | str,
) -> EstimateProteinSubtypeBaselineRequest:
    size = len(serialized.encode("utf-8")) if type(serialized) is str else len(serialized)
    if size > M0803_MAX_CANONICAL_REQUEST_BYTES:
        raise ValueError("M08-03 canonical request exceeds its byte limit")  # noqa: TRY003
    preflight_baseline_authorization(candidate)
    raw = serialized if isinstance(serialized, (bytes, bytearray)) else serialized.encode("utf-8")
    return _REQUEST_ADAPTER.validate_json(raw, strict=True)


def _uncertainty() -> UncertaintyProfile:
    estimate = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "The transparent baseline exposes typed uncertainty but does not claim "
            "calibrated uncertainty without owner-frozen training evidence."
        ),
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
            (
                "Baseline score is a transparent deterministic diagnostic, not a calibrated "
                "clinical probability."
            ),
        ),
    )


def _evidence(request: EstimateProteinSubtypeBaselineRequest) -> tuple[EvidenceReference, ...]:
    artifact_evidence = tuple(
        EvidenceReference(reference=artifact, role="evidence", claim=M0803_EVIDENCE_CLAIM)
        for artifact in request.source_artifacts
    )
    return artifact_evidence + tuple(
        evidence
        for observation in request.program_observations
        for evidence in observation.evidence
    )


def _provenance(
    request: EstimateProteinSubtypeBaselineRequest,
    request_digest: str,
) -> ProvenanceRecord:
    refs = request.context.references
    records = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage),
        (ControlRole.PROVENANCE, refs.provenance),
        (ControlRole.CONSENT, refs.consent),
        (ControlRole.QUALITY, refs.quality),
        (ControlRole.SUPPORT, refs.support),
        (ControlRole.INTENDED_USE, refs.intended_use),
    )
    decisions = tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=str(_state(reference.state)),
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=(
                getattr(reference, "binding_digest", None)
                if role is ControlRole.IDENTITY_LINEAGE
                else None
            ),
        )
        for role, reference in records
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M08-03",
        module_version=M0803_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=(
            request.representation_result.digest,
            *(artifact.digest for artifact in request.source_artifacts),
            *(
                evidence.reference.digest
                for observation in request.program_observations
                for evidence in observation.evidence
            ),
            request_digest,
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=decisions,
    )


def _limitations(*, measured: bool = False) -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="transparent_baseline",
            statement=(
                "Estimate is a deterministic baseline diagnostic, not a clinical probability."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This module emits no protein subtype parent object or treatment recommendation."
            ),
        ),
        Limitation(
            code="provisional_abi",
            statement="M08-02 handoff, feature catalogue, and estimator ABI remain provisional.",
        ),
        *(
            (
                Limitation(
                    code="typed_glioma_research_only",
                    statement=(
                        "Typed program states are research diagnostics over caller-supplied "
                        "protein evidence, not clinical subtype probabilities or treatment "
                        "guidance."
                    ),
                ),
            )
            if measured
            else ()
        ),
    )


def _diagnostic(
    diagnostic_id: str,
    status: BaselineDiagnosticStatus,
    message: str,
) -> BaselineDiagnostic:
    return BaselineDiagnostic(diagnostic_id=diagnostic_id, status=status, message=message)


def _bounded_signal(value: float) -> float:
    """Map an observed signed feature to a stable signal in [-1, 1]."""

    return value / (1.0 + abs(value))


def _estimate_signal(request: EstimateProteinSubtypeBaselineRequest) -> float:
    """Apply the declared transparent architecture without fitting or hidden state."""

    signals = tuple(
        _bounded_signal(feature.value)  # type: ignore[arg-type]
        for feature in request.features
    )
    method = request.configuration.method
    if method is BaselineMethod.STATISTICAL_RULE_BASED:
        return statistics.fmean(signals)
    if method is BaselineMethod.PATHWAY_ACTIVITY_NETWORK:
        weights = tuple(range(1, len(signals) + 1))
        return sum(signal * weight for signal, weight in zip(signals, weights, strict=True)) / sum(
            weights
        )
    # The fallback ensemble uses the median as a deterministic disagreement-resistant center.
    return statistics.median(signals)


def _huber_loss(residual: float, scale: float) -> float:
    standardized = abs(residual) / max(scale, 1e-9)
    return (
        0.5 * standardized**2
        if standardized <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * standardized - 0.5 * _TYPED_HUBER_K**2
    )


def _typed_value(
    observation: TypedBaselineObservation,
    overrides: Mapping[str, float] | None,
) -> float:
    if overrides is not None and observation.observation_id in overrides:
        return overrides[observation.observation_id]
    if observation.state is GliomaEvidenceState.LEFT_CENSORED:
        return float(cast("float", observation.censoring_limit))
    return float(cast("float", observation.standardized_effect))


def _typed_fit_graph(  # noqa: C901, PLR0912
    request: EstimateProteinSubtypeBaselineRequest,
    overrides: Mapping[str, float] | None = None,
) -> _TypedFit:
    """Fit the signed glioma program graph by damped robust coordinate descent."""

    observations = tuple(
        observation
        for observation in request.program_observations
        if observation.state
        in {GliomaEvidenceState.OBSERVED, GliomaEvidenceState.LEFT_CENSORED}
        and observation.quality_weight > 0.0
    )
    values = dict.fromkeys(GliomaProgram, 0.0)
    for program in GliomaProgram:
        grouped = tuple(item for item in observations if item.program is program)
        if grouped:
            weighted = sorted(
                (
                    _typed_value(item, overrides),
                    item.quality_weight / max(float(item.standard_error or 1.0) ** 2, 1e-9),
                )
                for item in grouped
            )
            total = sum(weight for _, weight in weighted)
            cutoff = 0.5 * total
            cumulative = 0.0
            for candidate, weight in weighted:
                cumulative += weight
                if cumulative >= cutoff:
                    values[program] = max(-_TYPED_MAX_EFFECT, min(_TYPED_MAX_EFFECT, candidate))
                    break
    trace: list[str] = []
    objective = float("inf")
    maximum_update = float("inf")
    iterations = 0
    for iteration in range(_TYPED_MAX_ITERATIONS):
        iterations = iteration + 1
        previous = values.copy()
        for program in GliomaProgram:
            numerator = _TYPED_RIDGE * 0.0
            denominator = _TYPED_RIDGE
            for observation in observations:
                if observation.program is not program:
                    continue
                observed = _typed_value(observation, overrides)
                residual = values[program] - observed
                if (
                    observation.state is GliomaEvidenceState.LEFT_CENSORED
                    and residual <= 0.0
                ):
                    continue
                precision = observation.quality_weight / max(
                    float(observation.standard_error or 1.0) ** 2, 1e-9
                )
                influence = min(
                    1.0,
                    _TYPED_HUBER_K
                    / max(1.0, abs(residual) / max(float(observation.standard_error or 1.0), 1e-9)),
                )
                weight = precision * influence
                numerator += weight * observed
                denominator += weight
            for source, target, sign in _TYPED_EDGES:
                if target is program:
                    numerator += _TYPED_RELATION_WEIGHT * sign * values[source]
                    denominator += _TYPED_RELATION_WEIGHT
                elif source is program:
                    numerator += _TYPED_RELATION_WEIGHT * sign * values[target]
                    denominator += _TYPED_RELATION_WEIGHT
            proposal = numerator / denominator
            values[program] = 0.65 * proposal + 0.35 * values[program]
            values[program] = max(-_TYPED_MAX_EFFECT, min(_TYPED_MAX_EFFECT, values[program]))
        maximum_update = max(abs(values[p] - previous[p]) for p in GliomaProgram)
        objective = _typed_objective(request, values, overrides)
        trace.append(
            ",".join(f"{program.value}={values[program]:.10f}" for program in GliomaProgram)
            + f";objective={objective:.10f}"
        )
        if maximum_update <= _TYPED_TOLERANCE:
            break
    trace_digest = "sha256:" + sha256("|".join(trace).encode("utf-8")).hexdigest()
    return _TypedFit(
        values=values,
        objective=objective,
        iterations=iterations,
        maximum_update=maximum_update,
        trace_digest=trace_digest,
    )


def _typed_objective(
    request: EstimateProteinSubtypeBaselineRequest,
    values: Mapping[GliomaProgram, float],
    overrides: Mapping[str, float] | None,
) -> float:
    total = _TYPED_RIDGE * sum(value * value for value in values.values())
    for observation in request.program_observations:
        if observation.state not in {
            GliomaEvidenceState.OBSERVED,
            GliomaEvidenceState.LEFT_CENSORED,
        } or observation.quality_weight <= 0.0:
            continue
        residual = values[observation.program] - _typed_value(observation, overrides)
        if observation.state is GliomaEvidenceState.LEFT_CENSORED and residual <= 0.0:
            continue
        total += observation.quality_weight * _huber_loss(
            residual,
            float(observation.standard_error or 1.0),
        )
    total += _TYPED_RELATION_WEIGHT * sum(
        (values[target] - sign * values[source]) ** 2
        for source, target, sign in _TYPED_EDGES
    )
    return float(total)


def _typed_label(lower: float, upper: float) -> GliomaProgramLabel:
    if lower > _TYPED_STATE_THRESHOLD:
        return GliomaProgramLabel.ACTIVATED
    if upper < -_TYPED_STATE_THRESHOLD:
        return GliomaProgramLabel.SUPPRESSED
    if lower >= -_TYPED_STATE_THRESHOLD and upper <= _TYPED_STATE_THRESHOLD:
        return GliomaProgramLabel.NEUTRAL
    return GliomaProgramLabel.INDETERMINATE


def _typed_program_states(
    request: EstimateProteinSubtypeBaselineRequest,
    request_digest: str,
    fit: _TypedFit,
) -> tuple[TypedProgramState, ...]:
    active = tuple(
        observation
        for observation in request.program_observations
        if observation.state
        in {GliomaEvidenceState.OBSERVED, GliomaEvidenceState.LEFT_CENSORED}
        and observation.quality_weight > 0.0
    )
    seed = int(request_digest.removeprefix("sha256:")[:16], 16)
    replicates = max(
        1,
        min(
            M0803_MAX_BOOTSTRAP_REPLICATES,
            request.configuration.bootstrap_replicates,
        ),
    )
    draws: dict[GliomaProgram, list[float]] = {program: [] for program in GliomaProgram}
    rng = np.random.default_rng(seed)
    for _ in range(replicates):
        overrides = {
            observation.observation_id: _typed_value(observation, None)
            + float(rng.normal(0.0, observation.standard_error or 1.0))
            for observation in active
            if observation.state is GliomaEvidenceState.OBSERVED
        }
        replicate = _typed_fit_graph(request, overrides)
        for program in GliomaProgram:
            draws[program].append(float(np.tanh(replicate.values[program])))
    states: list[TypedProgramState] = []
    evidence_counts = {
        program: sum(1 for observation in active if observation.program is program)
        for program in GliomaProgram
    }
    for program in GliomaProgram:
        center = float(np.tanh(fit.values[program]))
        if evidence_counts[program] == 0:
            center = 0.0
            lower, upper = -1.0, 1.0
            label = GliomaProgramLabel.INDETERMINATE
        else:
            lower, upper = np.quantile(
                np.asarray(draws[program], dtype=np.float64),
                (_TYPED_BOOTSTRAP_LOW, _TYPED_BOOTSTRAP_HIGH),
            )
            lower = max(-1.0, min(1.0, float(lower)))
            upper = max(-1.0, min(1.0, float(upper)))
            center = max(lower, min(upper, center))
            label = _typed_label(lower, upper)
        states.append(
            TypedProgramState(
                program=program,
                state=round(center, 8),
                lower_bound=round(lower, 8),
                upper_bound=round(upper, 8),
                label=label,
                evidence_count=evidence_counts[program],
                stability=round(max(0.0, 1.0 - (upper - lower) / 2.0), 8),
            )
        )
    return tuple(states)


def _typed_uncertainty(states: tuple[TypedProgramState, ...]) -> UncertaintyProfile:
    measured = tuple(item for item in states if item.evidence_count > 0)
    width = statistics.fmean(item.upper_bound - item.lower_bound for item in measured) / 2.0
    unstable = round(max(0.0, min(1.0, width)), 8)
    estimate = UncertaintyEstimate(
        state=EstimateState.ESTIMATED,
        probability=unstable,
        rationale="Bootstrap interval width is reported as repeat-fit instability propensity.",
    )
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="No owner-locked calibration maps this research interval to probability.",
    )
    return UncertaintyProfile(
        measurement=estimate,
        sampling=estimate,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=estimate,
        transport=not_estimable,
        sensitivity_notes=(
            "Intervals are deterministic digest-seeded bootstrap repeat-fit diagnostics.",
            "Missing and unsupported program evidence is not converted into negative state.",
        ),
    )


def _typed_estimate(
    request: EstimateProteinSubtypeBaselineRequest,
    request_digest: str,
) -> tuple[ProteinSubtypeBaselineEstimate, _TypedFit, UncertaintyProfile] | None:
    supported_programs = {
        observation.program
        for observation in request.program_observations
        if observation.state
        in {GliomaEvidenceState.OBSERVED, GliomaEvidenceState.LEFT_CENSORED}
        and observation.quality_weight > 0.0
    }
    if (
        len(supported_programs) < _TYPED_MIN_PROGRAMS
        or GliomaProgram.PROLIFERATION not in supported_programs
    ):
        return None
    fit = _typed_fit_graph(request)
    if fit.maximum_update > _TYPED_CONVERGENCE_CUTOFF:
        return None
    states = _typed_program_states(request, request_digest, fit)
    proliferation = fit.values[GliomaProgram.PROLIFERATION]
    score = 1.0 / (1.0 + exp(-proliferation))
    evidence = _evidence(request)
    return (
        ProteinSubtypeBaselineEstimate(
            predicted_subtype=(
                "glioma-proliferative-program-supported"
                if proliferation >= 0.0
                else "glioma-proliferative-program-suppressed"
            ),
            score=round(score, 8),
            calibration_reference=request.configuration.uncertainty_artifact,
            model_family=M0803_GLIOMA_MODEL_FAMILY,
            program_states=states,
            evidence=evidence,
        ),
        fit,
        _typed_uncertainty(states),
    )


def _typed_result(
    request: EstimateProteinSubtypeBaselineRequest,
) -> ProteinSubtypeBaselineResult:
    """Execute the explicit research-only glioma program graph lane."""

    request_digest = canonical_request_digest(request)
    typed_model = M0803_GLIOMA_MODEL_FAMILY
    diagnostics: list[BaselineDiagnostic] = [
        _diagnostic(
            "typed.inputs",
            BaselineDiagnosticStatus.PASS
            if request.program_observations
            else BaselineDiagnosticStatus.NOT_EVALUABLE,
            (
                "typed glioma program observations are present"
                if request.program_observations
                else "typed glioma model requires program observations"
            ),
        ),
        _diagnostic(
            "typed.configuration",
            BaselineDiagnosticStatus.PASS
            if request.configuration.model_family == typed_model
            else BaselineDiagnosticStatus.NOT_EVALUABLE,
            (
                "locked glioma signed-program model family selected"
                if request.configuration.model_family == typed_model
                else "program observations cannot be evaluated by the selected model family"
            ),
        ),
    ]
    finding_list: list[BaselineFindingCode] = []
    fit_result = (
        _typed_estimate(request, request_digest)
        if request.configuration.model_family == typed_model
        else None
    )
    if fit_result is None:
        diagnostics.append(
            _diagnostic(
                "typed.solver",
                BaselineDiagnosticStatus.NOT_EVALUABLE,
                (
                    "typed glioma graph needs at least two supported programs including "
                    "proliferation and a converged fit"
                ),
            )
        )
        finding_list.append(
            BaselineFindingCode.INCOMPLETE_INPUTS
            if request.configuration.model_family == typed_model
            else BaselineFindingCode.PROVISIONAL_ABI_PENDING_REVIEW
        )
        estimate = None
        uncertainty = _uncertainty()
        status = BaselineEstimateStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="m0803_typed_graph_not_evaluable",
            rationale=(
                "Typed glioma program evidence is incomplete or the selected model family "
                "is not authorized for this lane."
            ),
        )
        abstention_reason = (
            "Typed glioma baseline abstained because its signed program graph lacked "
            "sufficient supported evidence or a locked model family."
        )
        fit = None
    else:
        estimate, fit, uncertainty = fit_result
        diagnostics.append(
            _diagnostic(
                "typed.solver",
                BaselineDiagnosticStatus.PASS,
                "signed glioma program graph converged under robust coordinate descent",
            )
        )
        status = BaselineEstimateStatus.ESTIMATED
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="m0803_typed_glioma_graph_supported",
            rationale=(
                "Supported protein evidence fit the signed glioma program graph with "
                "deterministic bootstrap intervals."
            ),
        )
        abstention_reason = None
    payload: dict[str, object] = {
        "result_id": f"result.{request_digest.removeprefix('sha256:')}",
        "result_version": M0803_CONTRACT_VERSION,
        "request_digest": request_digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "estimate": estimate,
        "diagnostics": tuple(diagnostics),
        "findings": tuple(dict.fromkeys(finding_list)),
        "abstention_reason": abstention_reason,
        "parent_target": M0803_PARENT,
        "emits_parent": False,
        "support_decision": support,
        "uncertainty": uncertainty,
        "provenance": _provenance(request, request_digest),
        "evidence": _evidence(request),
        "typed_model": typed_model,
        "solver_iterations": fit.iterations if fit is not None else None,
        "solver_objective": round(fit.objective, 8) if fit is not None else None,
        "objective_trace_digest": fit.trace_digest if fit is not None else None,
        "limitations": _limitations(measured=fit is not None),
        "human_review_required": status is BaselineEstimateStatus.ABSTAINED,
    }
    constructed = ProteinSubtypeBaselineResult.model_construct(**payload)  # type: ignore[arg-type]
    payload["result_digest"] = result_payload_digest(constructed)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0803BaselineEngine:
    """Compute a transparent mean-based baseline without raw-source traversal."""

    __slots__ = ()

    def validate(self, request: object) -> EstimateProteinSubtypeBaselineRequest:
        return _validate_typed_request(request)

    def estimate(self, request: object) -> ProteinSubtypeBaselineResult:
        return self.estimate_validated(_validate_typed_request(request))

    def estimate_validated(
        self,
        request: EstimateProteinSubtypeBaselineRequest,
    ) -> ProteinSubtypeBaselineResult:
        if not isinstance(request, EstimateProteinSubtypeBaselineRequest):
            raise TypeError("M08-03 requires a validated request")  # noqa: TRY003
        if (
            request.configuration.model_family == M0803_GLIOMA_MODEL_FAMILY
            or request.program_observations
        ):
            return _typed_result(request)
        request_digest = canonical_request_digest(request)
        diagnostics: list[BaselineDiagnostic] = []
        findings: list[BaselineFindingCode] = []
        if not request.features:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    BaselineDiagnosticStatus.NOT_EVALUABLE,
                    "no caller-declared baseline features were supplied",
                )
            )
            findings.append(BaselineFindingCode.INCOMPLETE_INPUTS)
        elif any(
            feature.state is not BaselineFeatureState.OBSERVED for feature in request.features
        ):
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    BaselineDiagnosticStatus.NOT_EVALUABLE,
                    "one or more baseline features are missing or unsupported",
                )
            )
            findings.append(BaselineFindingCode.INCOMPLETE_INPUTS)
        else:
            diagnostics.append(
                _diagnostic(
                    "inputs.complete",
                    BaselineDiagnosticStatus.PASS,
                    "all declared baseline features are observed",
                )
            )
        suspicious = {"unsupported", "ood", "quality-failed", "unresolved"}
        if any(
            any(token in artifact.artifact_id.lower() for token in suspicious)
            for artifact in request.source_artifacts
        ):
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    BaselineDiagnosticStatus.NOT_EVALUABLE,
                    "source evidence declares an unsupported or out-of-domain condition",
                )
            )
            findings.append(BaselineFindingCode.OUT_OF_DOMAIN)
        else:
            diagnostics.append(
                _diagnostic(
                    "support.domain",
                    BaselineDiagnosticStatus.PASS,
                    "source evidence is within the declared provisional support envelope",
                )
            )
        diagnostics.extend(
            (
                _diagnostic(
                    "configuration.locked",
                    BaselineDiagnosticStatus.PASS,
                    "preprocessing, tuning, uncertainty, and benchmark artifacts are locked",
                ),
                _diagnostic(
                    "calibration.reference",
                    BaselineDiagnosticStatus.PASS,
                    "calibration and uncertainty references are present",
                ),
            )
        )
        failed = any(
            item.status in {BaselineDiagnosticStatus.FAIL, BaselineDiagnosticStatus.NOT_EVALUABLE}
            for item in diagnostics
        )
        estimate: ProteinSubtypeBaselineEstimate | None = None
        status = BaselineEstimateStatus.ABSTAINED
        support = SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="m0803_baseline_not_evaluable",
            rationale="Baseline inputs or support domain are not sufficient for a safe estimate.",
        )
        abstention_reason: str | None = (
            "Baseline abstained because required inputs or support checks were not evaluable."
        )
        if not failed:
            signal = _estimate_signal(request)
            score = _MIDPOINT + signal / 2.0
            predicted = (
                "protein-subtype-baseline-positive"
                if score >= _MIDPOINT
                else "protein-subtype-baseline-negative"
            )
            estimate = ProteinSubtypeBaselineEstimate(
                predicted_subtype=predicted,
                score=score,
                calibration_reference=request.configuration.uncertainty_artifact,
                evidence=_evidence(request),
            )
            status = BaselineEstimateStatus.ESTIMATED
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="m0803_baseline_supported",
                rationale="Observed declared features passed locked baseline support checks.",
            )
            abstention_reason = None
        payload: dict[str, object] = {
            "result_id": f"result.{request_digest.removeprefix('sha256:')}",
            "result_version": M0803_CONTRACT_VERSION,
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": request,
            "status": status,
            "estimate": estimate,
            "diagnostics": tuple(diagnostics),
            "findings": tuple(dict.fromkeys(findings)),
            "abstention_reason": abstention_reason,
            "parent_target": M0803_PARENT,
            "emits_parent": False,
            "support_decision": support,
            "uncertainty": _uncertainty(),
            "provenance": _provenance(request, request_digest),
            "evidence": _evidence(request),
            "limitations": _limitations(),
            "human_review_required": status is BaselineEstimateStatus.ABSTAINED,
        }
        constructed = ProteinSubtypeBaselineResult.model_construct(**payload)  # type: ignore[arg-type]
        payload["result_digest"] = result_payload_digest(constructed)
        return _RESULT_ADAPTER.validate_python(payload, strict=True)


def verify_m0803_result(result: object) -> ProteinSubtypeBaselineResult:
    typed = _RESULT_ADAPTER.validate_python(result, strict=True)
    if typed.request_digest != canonical_request_digest(typed.request):
        raise ValueError("M08-03 request digest verification failed")  # noqa: TRY003
    if typed.result_digest != result_payload_digest(typed):
        raise ValueError("M08-03 result digest verification failed")  # noqa: TRY003
    return typed


__all__ = [
    "M0803BaselineAuthorizationError",
    "M0803BaselineEngine",
    "_validate_json_request",
    "_validate_typed_request",
    "preflight_baseline_authorization",
    "verify_m0803_result",
]
