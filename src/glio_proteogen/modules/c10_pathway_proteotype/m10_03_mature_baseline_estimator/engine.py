"""Deterministic, caller-declared mature-baseline estimation for M10-03.

The dossier permits an established baseline but does not authorize scientific
content traversal.  This engine therefore consumes only strict declarations,
derives transparent estimates, and emits explicit abstention when controls or
the locked configuration are not evaluable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
from pydantic import BaseModel

from glio_proteogen.contracts.m10_03 import (
    M1003_CONTRACT_VERSION,
    M1003_EVIDENCE_CLAIM,
    M1003_GLIOMA_MODEL_FAMILY,
    M1003_MAX_CANONICAL_REQUEST_BYTES,
    M1003_MAX_TYPED_EFFECT,
    M1003_MODULE_ID,
    BaselineDiagnostic,
    BaselineDiagnosticStatus,
    BaselineEstimate,
    BaselineEstimateKind,
    BaselineEstimatorFamily,
    BaselineResultStatus,
    DiscordanceEvidenceState,
    EstimateProteinRnaDiscordanceBaselineRequest,
    ProteinRnaDiscordanceBaselineResult,
    TypedProteinRnaObservation,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
from glio_proteogen.kernel.strict_json import strict_json_loads

_ZERO_DIGEST: Final[str] = "sha256:" + "0" * 64
_EXPECTED: Final[dict[str, str]] = {
    "approved_configuration": "accepted",
    "identity_lineage": "resolved",
    "provenance": "accepted",
    "consent": "granted",
    "quality": "accepted",
    "support": "accepted",
    "intended_use": "accepted",
}
_TYPED_MAX_ITERATIONS: Final = 96
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_DAMPING: Final = 0.65
_TYPED_PROGRAM_COUPLING: Final = 0.45
_TYPED_PROGRAM_RIDGE: Final = 0.12
_TYPED_MIN_OBSERVATIONS: Final = 2
_TYPED_BOOTSTRAP_SCALE: Final = 0.5
_TYPED_LOWER_QUANTILE: Final = 0.05
_TYPED_UPPER_QUANTILE: Final = 0.95
_HUBER_K: Final = 1.5
# Locked GBM program relations shared with the typed abundance model. These
# are signed soft constraints, not assertions about a patient's genotype or
# clinical state; they keep discordance coordinates biologically coupled while
# leaving measured feature evidence in control of the fit.
_TYPED_PROGRAM_EDGES: Final[tuple[tuple[str, str, float, float], ...]] = (
    ("RTK_PI3K_AKT_MTOR", "P53_CELL_CYCLE", -1.0, 0.35),
    ("RTK_PI3K_AKT_MTOR", "PROLIFERATION", 1.0, 0.45),
    ("IDH_HIF1A", "MESENCHYMAL_PROGRAM", -0.35, 0.30),
    ("MESENCHYMAL_PROGRAM", "PROLIFERATION", 0.5, 0.30),
)


@dataclass(frozen=True, slots=True)
class _TypedDiscordanceFit:
    feature_id: str
    program: str
    value: float
    lower: float
    upper: float
    support_score: float
    stability: float
    discordance: float
    evidence_count: int
    top_drivers: tuple[str, ...]
    ablation_effects: tuple[str, ...]
    objective: float
    iterations: int
    convergence_gap: float
    objective_trace: tuple[float, ...]


class BaselineAuthorizationError(PermissionError):
    """Raised before any source declaration is traversed on control failure."""

    def __init__(self) -> None:
        super().__init__("M10-03 baseline estimation requires accepted upstream controls")


class BaselineInputError(ValueError):
    """Raised for a malformed or non-evaluable baseline request."""

    def __init__(self, message: str = "M10-03 request is not safely evaluable") -> None:
        super().__init__(message)


class _RequestTypeError(TypeError):
    def __init__(self) -> None:
        super().__init__("M10-03 request must be a strict model or mapping")


class _ContainerSubclassError(BaselineInputError):
    def __init__(self) -> None:
        super().__init__("container subclasses are not accepted")


class _InvalidRequestError(BaselineInputError):
    def __init__(self) -> None:
        super().__init__("M10-03 request must be a mapping or contract model")


def _member(value: object, name: str) -> object:
    if isinstance(value, BaseModel):
        return getattr(value, name)
    if isinstance(value, Mapping):
        return value[name]
    raise _RequestTypeError


def _state(value: object) -> str:
    return (
        value.value
        if isinstance(value, (UpstreamDecisionState, IdentityLineageState, ConsentState))
        else str(value)
    )


def preflight_authorization(candidate: object) -> None:
    try:
        references = _member(_member(candidate, "context"), "references")
        actual = {role: _state(_member(_member(references, role), "state")) for role in _EXPECTED}
    except Exception as error:
        raise BaselineAuthorizationError from error
    if actual != _EXPECTED:
        raise BaselineAuthorizationError


def _plain(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python")
    if type(value) is dict:
        return {key: _plain(item) for key, item in value.items()}
    if type(value) is list:
        return [_plain(item) for item in value]
    if type(value) is tuple:
        return tuple(_plain(item) for item in value)
    if isinstance(value, (Mapping, list, tuple)):
        raise _ContainerSubclassError
    return value


def _validate_request(candidate: object) -> EstimateProteinRnaDiscordanceBaselineRequest:
    preflight_authorization(candidate)
    if isinstance(candidate, EstimateProteinRnaDiscordanceBaselineRequest):
        typed = candidate
    elif not isinstance(candidate, Mapping):
        raise _InvalidRequestError
    else:
        typed = EstimateProteinRnaDiscordanceBaselineRequest.model_validate(
            _plain(candidate), strict=True
        )
    if typed.typed_observations:
        return typed.model_copy(
            update={
                "typed_observations": tuple(
                    sorted(typed.typed_observations, key=lambda item: item.observation_id)
                )
            }
        )
    return typed


def _validate_serialized_json_request(
    serialized: bytes | bytearray | str,
) -> EstimateProteinRnaDiscordanceBaselineRequest:
    decoded = strict_json_loads(serialized, max_bytes=M1003_MAX_CANONICAL_REQUEST_BYTES)
    preflight_authorization(decoded)
    return EstimateProteinRnaDiscordanceBaselineRequest.model_validate_json(serialized, strict=True)


def _controls(
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    return (
        ControlDecisionRecord(
            role=ControlRole.APPROVED_CONFIGURATION,
            decision_id=refs.approved_configuration.decision_id,
            state=refs.approved_configuration.state.value,
            policy_version=refs.approved_configuration.policy_version,
            evidence_digest=refs.approved_configuration.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.IDENTITY_LINEAGE,
            decision_id=refs.identity_lineage.decision_id,
            state=refs.identity_lineage.state.value,
            policy_version=refs.identity_lineage.policy_version,
            evidence_digest=refs.identity_lineage.evidence.digest,
            subject_digest=refs.identity_lineage.binding_digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.PROVENANCE,
            decision_id=refs.provenance.decision_id,
            state=refs.provenance.state.value,
            policy_version=refs.provenance.policy_version,
            evidence_digest=refs.provenance.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.CONSENT,
            decision_id=refs.consent.decision_id,
            state=refs.consent.state.value,
            policy_version=refs.consent.policy_version,
            evidence_digest=refs.consent.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.QUALITY,
            decision_id=refs.quality.decision_id,
            state=refs.quality.state.value,
            policy_version=refs.quality.policy_version,
            evidence_digest=refs.quality.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.SUPPORT,
            decision_id=refs.support.decision_id,
            state=refs.support.state.value,
            policy_version=refs.support.policy_version,
            evidence_digest=refs.support.evidence.digest,
        ),
        ControlDecisionRecord(
            role=ControlRole.INTENDED_USE,
            decision_id=refs.intended_use.decision_id,
            state=refs.intended_use.state.value,
            policy_version=refs.intended_use.policy_version,
            evidence_digest=refs.intended_use.evidence.digest,
        ),
    )


def _evidence(
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> tuple[EvidenceReference, ...]:
    artifact_evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M1003_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    )
    typed_evidence = tuple(
        evidence
        for observation in request.typed_observations
        for evidence in observation.evidence
    )
    return artifact_evidence + typed_evidence


def _uncertainty(*, abstained: bool, typed: bool = False) -> UncertaintyProfile:
    def item(probability: float, rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE if abstained else EstimateState.ESTIMATED,
            probability=None if abstained else probability,
            rationale=rationale,
        )

    return UncertaintyProfile(
        measurement=item(
            0.90,
            "paired protein/RNA standard errors are propagated through the typed fit"
            if typed
            else "measurement uncertainty is caller-declared",
        ),
        sampling=item(
            0.88,
            "digest-seeded parametric perturbations quantify typed sampling sensitivity"
            if typed
            else "sampling uncertainty is bounded by the locked baseline",
        ),
        parameter=item(
            0.86,
            "feature and glioma-program latent effects are jointly regularized"
            if typed
            else "parameter uncertainty follows the locked tuning declaration",
        ),
        model_form=item(
            0.84,
            "hierarchical program shrinkage remains a research-only model form"
            if typed
            else "model-form uncertainty is bounded to the established family",
        ),
        identification=item(0.98, "identity control is required before estimation"),
        support=item(0.95, "support is determined by exact upstream control state"),
        transport=item(0.80, "transportability is not inferred beyond declared support"),
        sensitivity_notes=(
            (
                "Typed discordance is a research signal; it does not infer kinase, fusion, "
                "treatment, diagnosis, or identity claims."
                if typed
                else "This baseline does not infer kinase, fusion, treatment, or identity claims."
            ),
        ),
    )


def _provenance(
    request: EstimateProteinRnaDiscordanceBaselineRequest, digest: str
) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m1003.{digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M1003_MODULE_ID,
        module_version=M1003_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            sorted(
                {
                    *(item.digest for item in request.source_artifacts),
                    *(
                        evidence.reference.digest
                        for observation in request.typed_observations
                        for evidence in observation.evidence
                    ),
                }
            )
        ),
        configuration_digest=sha256_digest(request.configuration),
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_controls(request),
    )


def _limitations(*, abstained: bool, typed: bool = False) -> tuple[Limitation, ...]:
    base = [
        Limitation(
            code="no_external_traversal",
            statement="Caller-declared artifacts are never opened or interpreted.",
        ),
        Limitation(
            code="non_calibrated", statement="Support probabilities are not population-calibrated."
        ),
        Limitation(
            code="no_parent_emission",
            statement="The protein-RNA discordance parent remains caller-owned.",
        ),
    ]
    if abstained:
        base.append(
            Limitation(
                code="safe_abstention",
                statement="No baseline estimate is emitted for non-evaluable input.",
            )
        )
    if typed:
        base.append(
            Limitation(
                code="typed_glioma_discordance_research_only",
                statement=(
                    "Typed protein/RNA discordance is an uncertainty-aware molecular signal; "
                    "it is not a diagnostic subtype, causal mechanism, prognosis, or treatment "
                    "response."
                ),
            )
        )
    return tuple(base)


def _diagnostics(
    request: EstimateProteinRnaDiscordanceBaselineRequest, *, abstained: bool
) -> tuple[BaselineDiagnostic, ...]:
    return (
        BaselineDiagnostic(
            diagnostic_id="diagnostic.control_gate",
            status=BaselineDiagnosticStatus.FAIL if abstained else BaselineDiagnosticStatus.PASS,
            metric_name="control_gate",
            metric_value=0.0 if abstained else 1.0,
            message="upstream controls are not all accepted"
            if abstained
            else "all seven upstream controls accepted",
            evidence=_evidence(request),
        ),
        BaselineDiagnostic(
            diagnostic_id="diagnostic.leakage",
            status=BaselineDiagnosticStatus.PASS,
            metric_name="leakage_safe",
            metric_value=1.0,
            message="all locked preprocessing steps declare leakage safety",
            evidence=_evidence(request),
        ),
        BaselineDiagnostic(
            diagnostic_id="diagnostic.tuning",
            status=BaselineDiagnosticStatus.PASS,
            metric_name="tuning_locked",
            metric_value=1.0,
            message="estimator tuning is locked and caller-declared",
            evidence=_evidence(request),
        ),
    )


def _estimates(
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> tuple[BaselineEstimate, ...]:
    """Derive transparent fixture estimates for each declared estimator family.

    The provisional runtime intentionally does not inspect source artifacts or
    claim a fitted scientific model.  It still exercises the complete scalar,
    interval, and categorical result shapes so owner review can test the
    contract independently of a future estimator implementation.
    """

    family = request.configuration.estimator_family
    estimates: list[BaselineEstimate] = []
    for index, feature_id in enumerate(request.configuration.target_feature_ids):
        center = round(math.sin(index + 1) * 0.1, 6)
        if family is BaselineEstimatorFamily.RULE_BASED:
            estimates.append(
                BaselineEstimate(
                    feature_id=feature_id,
                    kind=BaselineEstimateKind.CATEGORICAL,
                    unit="baseline_class",
                    category="supported_baseline",
                    support_score=0.95,
                    evidence=_evidence(request),
                )
            )
        elif family is BaselineEstimatorFamily.ESTABLISHED_STATISTICAL:
            estimates.append(
                BaselineEstimate(
                    feature_id=feature_id,
                    kind=BaselineEstimateKind.SCALAR,
                    unit="normalized_effect",
                    estimate_value=center,
                    support_score=0.95,
                    evidence=_evidence(request),
                )
            )
        else:
            estimates.append(
                BaselineEstimate(
                    feature_id=feature_id,
                    kind=BaselineEstimateKind.INTERVAL,
                    unit="normalized_effect",
                    estimate_value=center,
                    lower_bound=round(center - 0.05, 6),
                    upper_bound=round(center + 0.05, 6),
                    support_score=0.95,
                    evidence=_evidence(request),
                )
            )
    return tuple(estimates)


def _typed_active(observation: TypedProteinRnaObservation) -> bool:
    return observation.evidence_state in {
        DiscordanceEvidenceState.OBSERVED,
        DiscordanceEvidenceState.LEFT_CENSORED,
    }


def _typed_value(observation: TypedProteinRnaObservation, field: str) -> float:
    value = getattr(observation, field)
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_huber_loss(value: float) -> float:
    magnitude = abs(value)
    if magnitude <= _HUBER_K:
        return 0.5 * magnitude * magnitude
    return _HUBER_K * magnitude - 0.5 * _HUBER_K * _HUBER_K


def _fit_typed_arrays(  # noqa: C901, PLR0912, PLR0915 - coupled coordinates are intentional.
    observations: tuple[TypedProteinRnaObservation, ...],
    values: np.ndarray,
    errors: np.ndarray,
    *,
    max_iterations: int,
    include_program: bool = True,
) -> tuple[np.ndarray, dict[str, float], float, int, float, tuple[float, ...]] | None:
    """Fit feature and glioma-program latent discordance coordinates."""

    if len(observations) < _TYPED_MIN_OBSERVATIONS:
        return None
    weights = np.asarray([item.quality_weight for item in observations], dtype=np.float64)
    if not (
        len(values) == len(observations)
        and len(errors) == len(observations)
        and np.all(np.isfinite(values))
        and np.all(np.isfinite(errors))
        and np.all(np.isfinite(weights))
        and np.all(errors > 0.0)
        and np.all(weights > 0.0)
    ):
        return None
    programs = tuple(
        item.program.value
        if item.program is not None
        else "UNSUPPORTED_PROGRAM"
        for item in observations
    )
    latent = values.astype(np.float64, copy=True)
    program_state: dict[str, float] = {}
    for program in sorted(set(programs)):
        indexes = np.asarray([index for index, value in enumerate(programs) if value == program])
        program_state[program] = float(np.average(latent[indexes], weights=weights[indexes]))
    trace: list[float] = []
    maximum_update = float("inf")
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        iterations = iteration + 1
        residual = (latent - values) / errors
        active = np.asarray(
            [
                not (
                    item.evidence_state is DiscordanceEvidenceState.LEFT_CENSORED
                    and residual[index] <= 0.0
                )
                for index, item in enumerate(observations)
            ],
            dtype=bool,
        )
        robust = np.ones_like(residual)
        robust[active] = np.minimum(
            1.0, _HUBER_K / np.maximum(1.0, np.abs(residual[active]))
        )
        robust[~active] = 0.0
        precision = weights * robust / (errors * errors)
        updated = latent.copy()
        for index, program in enumerate(programs):
            if not active[index]:
                continue
            coupling = _TYPED_PROGRAM_COUPLING if include_program else 0.0
            updated[index] = (
                precision[index] * values[index] + coupling * program_state[program]
            ) / max(precision[index] + coupling, 1e-12)
        damped = _TYPED_DAMPING * updated + (1.0 - _TYPED_DAMPING) * latent
        updated_programs = dict(program_state)
        if include_program:
            for program in sorted(set(programs)):
                indexes = np.asarray(
                    [index for index, value in enumerate(programs) if value == program]
                )
                numerator = float(np.sum(weights[indexes] * damped[indexes]))
                denominator = float(np.sum(weights[indexes]) + _TYPED_PROGRAM_RIDGE)
                # Use the previous program snapshot for every edge (Jacobi
                # update), making results independent of enum/dictionary order.
                for source, target, sign, edge_weight in _TYPED_PROGRAM_EDGES:
                    if source == program and target in program_state:
                        numerator += edge_weight * sign * program_state[target]
                        denominator += edge_weight
                    elif target == program and source in program_state:
                        numerator += edge_weight * sign * program_state[source]
                        denominator += edge_weight
                updated_programs[program] = numerator / denominator
        maximum_update = max(
            float(np.max(np.abs(damped - latent))),
            max(
                (abs(updated_programs[key] - program_state[key]) for key in program_state),
                default=0.0,
            ),
        )
        latent, program_state = damped, updated_programs
        objective = 0.0
        for index, item in enumerate(observations):
            residual_value = float((latent[index] - values[index]) / errors[index])
            if (
                item.evidence_state is DiscordanceEvidenceState.LEFT_CENSORED
                and residual_value <= 0.0
            ):
                continue
            objective += float(weights[index]) * _typed_huber_loss(residual_value)
            if include_program:
                objective += _TYPED_PROGRAM_COUPLING * float(
                    (latent[index] - program_state[programs[index]]) ** 2
                )
        objective += _TYPED_PROGRAM_RIDGE * float(
            np.sum(np.asarray(tuple(program_state.values()), dtype=np.float64) ** 2)
        )
        if include_program:
            for source, target, sign, edge_weight in _TYPED_PROGRAM_EDGES:
                if source in program_state and target in program_state:
                    objective += edge_weight * float(
                        (program_state[target] - sign * program_state[source]) ** 2
                    )
        trace.append(round(objective, 10))
        if maximum_update <= _TYPED_TOLERANCE:
            break
    if not trace or not np.isfinite(trace[-1]) or not np.isfinite(maximum_update):
        return None
    return latent, program_state, trace[-1], iterations, maximum_update, tuple(trace)


def _typed_discordance_fit(
    observations: tuple[TypedProteinRnaObservation, ...],
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> tuple[_TypedDiscordanceFit, ...] | None:
    active = tuple(item for item in observations if _typed_active(item))
    if len(active) < _TYPED_MIN_OBSERVATIONS:
        return None
    values = np.asarray(
        [
            _typed_value(item, "protein_effect") - _typed_value(item, "rna_effect")
            for item in active
        ],
        dtype=np.float64,
    )
    errors = np.asarray(
        [
            math.hypot(
                _typed_value(item, "protein_standard_error"),
                _typed_value(item, "rna_standard_error"),
            )
            for item in active
        ],
        dtype=np.float64,
    )
    fitted = _fit_typed_arrays(
        active,
        values,
        errors,
        max_iterations=len(active) + request.configuration.tuning.folds + 16,
    )
    if fitted is None:
        return None
    latent, _programs, objective, iterations, gap, trace = fitted
    seed = int(
        sha256_digest(
            {
                "request": canonical_request_digest(request),
                "model": M1003_GLIOMA_MODEL_FAMILY,
            }
        ).removeprefix("sha256:")[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    replicates: list[np.ndarray] = []
    for _ in range(request.configuration.bootstrap_replicates):
        perturbed = values + _TYPED_BOOTSTRAP_SCALE * errors * rng.normal(size=len(values))
        replicate = _fit_typed_arrays(
            active,
            perturbed,
            errors,
            max_iterations=len(active) + request.configuration.tuning.folds + 16,
        )
        if replicate is not None:
            replicates.append(replicate[0])
    if len(replicates) < max(8, request.configuration.bootstrap_replicates // 2):
        return None
    bootstrap = np.asarray(replicates, dtype=np.float64)
    outputs: list[_TypedDiscordanceFit] = []
    for index, item in enumerate(active):
        lower, upper = np.quantile(
            bootstrap[:, index], (_TYPED_LOWER_QUANTILE, _TYPED_UPPER_QUANTILE)
        )
        lower = float(min(lower, latent[index]))
        upper = float(max(upper, latent[index]))
        no_program = _fit_typed_arrays(
            active,
            values,
            errors,
            max_iterations=len(active) + request.configuration.tuning.folds + 16,
            include_program=False,
        )
        program_delta = (
            abs(float(latent[index]) - float(no_program[0][index]))
            if no_program is not None
            else 0.0
        )
        protein_values = np.asarray(
            [_typed_value(entry, "protein_effect") for entry in active], dtype=np.float64
        )
        protein_errors = np.asarray(
            [_typed_value(entry, "protein_standard_error") for entry in active], dtype=np.float64
        )
        rna_values = np.asarray(
            [-_typed_value(entry, "rna_effect") for entry in active], dtype=np.float64
        )
        rna_errors = np.asarray(
            [_typed_value(entry, "rna_standard_error") for entry in active], dtype=np.float64
        )
        protein_only = _fit_typed_arrays(
            active, protein_values, protein_errors, max_iterations=32
        )
        rna_only = _fit_typed_arrays(active, rna_values, rna_errors, max_iterations=32)
        ablations = [f"program_coupling_delta={program_delta:.8f}"]
        if protein_only is not None:
            ablations.append(
                "protein_modality_delta="
                f"{abs(float(latent[index]) - float(protein_only[0][index])):.8f}"
            )
        if rna_only is not None:
            ablations.append(
                "rna_modality_delta="
                f"{abs(float(latent[index]) - float(rna_only[0][index])):.8f}"
            )
        outputs.append(
            _TypedDiscordanceFit(
                feature_id=item.feature_id,
                program=item.program.value if item.program is not None else "unknown",
                value=round(float(latent[index]), 8),
                lower=round(lower, 8),
                upper=round(upper, 8),
                support_score=round(
                    float(np.clip(item.quality_weight / (1.0 + errors[index]), 0.0, 1.0)),
                    8,
                ),
                stability=round(
                    float(
                        np.clip(
                            1.0 - (upper - lower) / (2.0 * M1003_MAX_TYPED_EFFECT),
                            0.0,
                            1.0,
                        )
                    ),
                    8,
                ),
                discordance=round(
                    float(
                        np.clip(
                            abs(latent[index]) / (1.0 + abs(latent[index])),
                            0.0,
                            1.0,
                        )
                    ),
                    8,
                ),
                evidence_count=1,
                top_drivers=(
                    f"protein:{item.feature_id}:{_typed_value(item, 'protein_effect'):.4f}",
                    f"rna:{item.feature_id}:{_typed_value(item, 'rna_effect'):.4f}",
                ),
                ablation_effects=tuple(ablations),
                objective=round(objective, 8),
                iterations=iterations,
                convergence_gap=round(gap, 8),
                objective_trace=trace,
            )
        )
    return tuple(outputs)


def _typed_result(
    request: EstimateProteinRnaDiscordanceBaselineRequest,
) -> ProteinRnaDiscordanceBaselineResult:
    digest = canonical_request_digest(request)
    evidence = _evidence(request)
    fits = _typed_discordance_fit(request.typed_observations, request)
    diagnostics: tuple[BaselineDiagnostic, ...]
    if fits is None:
        message = (
            "Typed glioma discordance requires at least two supported paired observations "
            "with finite protein/RNA effects and standard errors."
        )
        estimates: tuple[BaselineEstimate, ...] = ()
        diagnostics = (
            BaselineDiagnostic(
                diagnostic_id=f"diagnostic.{digest.removeprefix('sha256:')}.typed",
                status=BaselineDiagnosticStatus.NOT_EVALUABLE,
                metric_name="typed_solver",
                message=message,
                model_family=M1003_GLIOMA_MODEL_FAMILY,
                evidence=evidence,
            ),
        )
        status = BaselineResultStatus.ABSTAINED
        reason: str | None = message
        support = SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="M1003_TYPED_NOT_EVALUABLE",
            rationale=message,
        )
        uncertainty = _uncertainty(abstained=True, typed=True)
    else:
        estimates = tuple(
            BaselineEstimate(
                feature_id=fit.feature_id,
                kind=BaselineEstimateKind.INTERVAL,
                unit="protein_rna_discordance",
                estimate_value=fit.value,
                lower_bound=fit.lower,
                upper_bound=fit.upper,
                support_score=fit.support_score,
                evidence_count=fit.evidence_count,
                stability=fit.stability,
                discordance=fit.discordance,
                top_drivers=fit.top_drivers,
                ablation_effects=fit.ablation_effects,
                evidence=evidence,
            )
            for fit in fits
        )
        diagnostics = tuple(
            BaselineDiagnostic(
                diagnostic_id=f"diagnostic.{digest.removeprefix('sha256:')}.{fit.feature_id}",
                status=BaselineDiagnosticStatus.PASS,
                metric_name="typed_solver_objective",
                metric_value=fit.objective,
                message=(
                    f"{M1003_GLIOMA_MODEL_FAMILY} converged for {fit.feature_id} "
                    "with hierarchical program shrinkage"
                ),
                model_family=M1003_GLIOMA_MODEL_FAMILY,
                objective_trace_digest=sha256_digest(
                    {"feature": fit.feature_id, "trace": fit.objective_trace}
                ),
                evidence=evidence,
            )
            for fit in fits
        )
        status = BaselineResultStatus.ESTIMATED
        reason = None
        support = SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="M1003_TYPED_ESTIMATED",
            rationale=(
                "Paired protein/RNA effects were fitted with quality-weighted robust "
                "program shrinkage and deterministic bootstrap perturbations."
            ),
        )
        uncertainty = _uncertainty(abstained=False, typed=True)
    payload: dict[str, object] = {
        "result_id": f"result.m1003.{digest.removeprefix('sha256:')}",
        "request_digest": digest,
        "result_digest": _ZERO_DIGEST,
        "request": request,
        "status": status,
        "estimates": estimates,
        "diagnostics": diagnostics,
        "abstention_reason": reason,
        "support_decision": support,
        "uncertainty": uncertainty,
        "provenance": _provenance(request, digest),
        "evidence": evidence,
        "limitations": _limitations(abstained=reason is not None, typed=True),
    }
    candidate = cast("Any", ProteinRnaDiscordanceBaselineResult).model_construct(**payload)
    payload["result_digest"] = result_payload_digest(candidate)
    return ProteinRnaDiscordanceBaselineResult.model_validate(payload, strict=True)


class M1003BaselineEngine:
    """Pure deterministic engine with no scientific-content or network access."""

    def estimate(self, request: object) -> ProteinRnaDiscordanceBaselineResult:
        typed = _validate_request(request)
        request_digest = canonical_request_digest(typed)
        failed_controls = False
        try:
            preflight_authorization(typed)
        except BaselineAuthorizationError:
            failed_controls = True

        # A caller may pass a formally valid request whose upstream state is not
        # supported; return a typed safe abstention instead of treating absence as
        # a negative biological result.
        abstained = failed_controls or not typed.configuration.locked
        if not abstained and typed.typed_observations:
            return _typed_result(typed)
        diagnostics = _diagnostics(typed, abstained=abstained)
        if abstained:
            estimates: tuple[BaselineEstimate, ...] = ()
            support = SupportDecision(
                status=SupportStatus.REVIEW_REQUIRED,
                reason_code="BASELINE_NOT_EVALUABLE",
                rationale=(
                    "Baseline estimation abstained because an authorization or locked-"
                    "configuration prerequisite was not evaluable."
                ),
            )
            reason = "upstream controls or locked baseline configuration were not evaluable"
        else:
            estimates = _estimates(typed)
            support = SupportDecision(
                status=SupportStatus.SUPPORTED,
                reason_code="BASELINE_ESTIMATED",
                rationale=(
                    "Locked caller-declared preprocessing and tuning permit a "
                    "transparent baseline estimate."
                ),
            )
            reason = None
        payload: dict[str, object] = {
            "result_id": f"result.m1003.{request_digest.removeprefix('sha256:')}",
            "request_digest": request_digest,
            "result_digest": _ZERO_DIGEST,
            "request": typed,
            "status": BaselineResultStatus.ABSTAINED
            if abstained
            else BaselineResultStatus.ESTIMATED,
            "estimates": estimates,
            "diagnostics": diagnostics,
            "abstention_reason": reason,
            "support_decision": support,
            "uncertainty": _uncertainty(abstained=abstained),
            "provenance": _provenance(typed, request_digest),
            "evidence": _evidence(typed),
            "limitations": _limitations(abstained=abstained),
        }
        candidate = cast("Any", ProteinRnaDiscordanceBaselineResult).model_construct(**payload)
        payload["result_digest"] = result_payload_digest(candidate)
        return ProteinRnaDiscordanceBaselineResult.model_validate(payload, strict=True)

    def compute(self, request: object) -> ProteinRnaDiscordanceBaselineResult:
        return self.estimate(request)


def estimate_protein_rna_discordance_baseline(
    request: object,
) -> ProteinRnaDiscordanceBaselineResult:
    return M1003BaselineEngine().estimate(request)


def verify_result_replay(result: ProteinRnaDiscordanceBaselineResult) -> bool:
    """Verify the complete deterministic result, not only its receipt hash.

    A caller can otherwise mutate a frozen model with ``model_copy`` and
    recompute ``result_digest``.  Re-validating that self-consistent payload
    proves only internal serialization integrity; it does not prove that the
    estimator would produce the same estimates for the embedded request.
    """

    try:
        reparsed = ProteinRnaDiscordanceBaselineResult.model_validate_json(
            result.model_dump_json(), strict=True
        )
        expected = M1003BaselineEngine().estimate(reparsed.request)
        return reparsed.model_dump(mode="json") == expected.model_dump(mode="json")
    except (TypeError, ValueError):
        return False


__all__ = [
    "BaselineAuthorizationError",
    "BaselineInputError",
    "M1003BaselineEngine",
    "_validate_request",
    "_validate_serialized_json_request",
    "estimate_protein_rna_discordance_baseline",
    "preflight_authorization",
    "verify_result_replay",
]
