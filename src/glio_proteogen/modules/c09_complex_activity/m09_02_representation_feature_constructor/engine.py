"""Deterministic, leakage-safe M09-02 representation construction runtime.

The dossier describes a representation boundary but intentionally does not freeze
an estimator, feature catalogue, endpoint, or media contract.  This runtime keeps
those choices explicit and provisional: feature values are generated from locked
content-addressed inputs, transformations are never learned from the request, and
missing, unsupported, OOD, or unevaluable paths abstain without manufacturing a
negative finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite, sqrt
from typing import Final

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m09_02 import (
    M0902_CONTRACT_VERSION,
    M0902_EVIDENCE_CLAIM,
    M0902_GLIOMA_MODEL_FAMILY,
    M0902_MAX_CANONICAL_RESULT_BYTES,
    M0902_MAX_TYPED_EFFECT,
    M0902_MODULE_ID,
    ComplexActivityRepresentationResult,
    ComplexOptimizationDiagnostic,
    ComplexOptimizationStatus,
    ConstructComplexActivityRepresentationRequest,
    FeatureSpecification,
    GliomaComplexEvidenceState,
    GliomaComplexObservation,
    LeakageCheck,
    LeakageCheckStatus,
    RepresentationConstructionStatus,
    RepresentationFeature,
    RepresentationTransformationKind,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructComplexActivityRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ComplexActivityRepresentationResult)
_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)


class M0902AuthorizationError(PermissionError):
    """Raised when consent, identity, or an upstream control is not accepted."""

    def __init__(self) -> None:
        super().__init__(
            "M09-02 requires granted consent, resolved identity, and accepted controls"
        )


class M0902InputError(ValueError):
    """Raised when replay material exceeds bounds or is not canonical."""

    _MESSAGES: Final = {
        "result_limit": "M09-02 result exceeds the canonical byte limit",
        "result_digest": "M09-02 result digest does not match its content",
        "result_noncanonical": "M09-02 result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltM0902Result:
    """Typed result plus the only canonical byte representation."""

    result: ComplexActivityRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise M0902InputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise M0902InputError("result_noncanonical")


def preflight_m0902_authorization(request: object) -> None:
    """Check the seven caller-declared controls before construction."""

    if not isinstance(request, ConstructComplexActivityRepresentationRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise M0902AuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise M0902AuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise M0902AuthorizationError


def _control_decisions(
    request: ConstructComplexActivityRepresentationRequest,
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


def _provenance(request: ConstructComplexActivityRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    typed_digests = {
        evidence.reference.digest
        for observation in request.typed_observations
        for evidence in observation.evidence
    }
    input_digests = tuple(
        sorted(
            {item.digest for item in request.source_artifacts}
            | {request.formal_state_result.digest}
            | typed_digests
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M0902_MODULE_ID,
        module_version=M0902_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=refs.approved_configuration.evidence.digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=_control_decisions(request),
    )


def _uncertainty() -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale=(
            "M09-02 has no owner-locked probabilistic estimator in the provisional ABI; "
            "construction therefore exposes explicit non-estimability."
        ),
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=(
            "Sensitivity, support, and transport uncertainty require owner-locked validation "
            "data and are not inferred from caller-declared references.",
        ),
    )


def _typed_uncertainty() -> UncertaintyProfile:
    def estimated(probability: float, dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=f"deterministic M09-02 typed {dimension} uncertainty",
        )

    return UncertaintyProfile(
        measurement=estimated(0.10, "measurement"),
        sampling=estimated(0.10, "sampling"),
        parameter=estimated(0.15, "parameter"),
        model_form=estimated(0.20, "model-form"),
        identification=estimated(0.10, "identification"),
        support=estimated(0.15, "support"),
        transport=estimated(0.25, "transport"),
        sensitivity_notes=(
            "Bootstrap intervals reflect measurement and sampling perturbations only.",
            "Essential-subunit and stoichiometric ablations expose topology sensitivity.",
            "The typed lane emits complex activity only; no kinase or treatment claim is made.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "The typed glioma complex estimator is research-use-only; the opaque feature "
                "fallback remains provisional compatibility behavior."
            ),
        ),
        Limitation(
            code="caller_declared_inputs",
            statement=(
                "References are content-addressed and replay-bound, but issuer authority and "
                "external artifact content are not authenticated or traversed."
            ),
        ),
        Limitation(
            code="ownership_boundary",
            statement=(
                "The module emits no kinase activity, generic all-omics fusion, treatment "
                "recommendation, identity inference, or protein-level subtype claim."
            ),
        ),
    )


def _seed(feature_id: str, request: ConstructComplexActivityRepresentationRequest) -> bytes:
    digest = canonical_request_digest(request)
    source_digests = ",".join(sorted(item.digest for item in request.source_artifacts))
    return (
        f"{feature_id}|{digest}|{request.policy.policy_id}|{request.policy.version}|{source_digests}"
    ).encode()


def _values(
    specification: FeatureSpecification,
    request: ConstructComplexActivityRepresentationRequest,
) -> tuple[float, ...]:
    if specification.source_values:
        values = [float(value) for value in specification.source_values]
        for transformation in specification.lineage.transformations:
            if transformation.kind in {
                RepresentationTransformationKind.SCALING,
                RepresentationTransformationKind.NORMALIZATION,
            }:
                center = fsum(values) / len(values)
                variance = fsum((value - center) ** 2 for value in values) / len(values)
                scale = sqrt(max(variance, 1e-12))
                values = [(value - center) / scale for value in values]
            elif transformation.kind is RepresentationTransformationKind.RESIDUAL:
                center = fsum(values) / len(values)
                values = [value - center for value in values]
            elif transformation.kind in {
                RepresentationTransformationKind.MASKING,
                RepresentationTransformationKind.COVARIATE,
            }:
                values = list(values)
        return tuple(round(value, 8) for value in values)

    feature_id = specification.feature_id
    dimension = specification.dimension
    seed = _seed(feature_id, request)
    hash_values: list[float] = []
    for position in range(dimension):
        block = sha256(seed + f"|{position}".encode("ascii")).digest()
        raw = int.from_bytes(block[:8], "big") / float(2**64)
        hash_values.append(round(raw, 8))
    return tuple(hash_values)


_TYPED_HUBER_K: Final = 1.5
_TYPED_DAMPING: Final = 0.62
_TYPED_RIDGE: Final = 0.12
_TYPED_BOTTLENECK: Final = 0.35
_TYPED_COHERENCE: Final = 0.18
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_BACKTRACK_FLOOR: Final = 1e-3
_TYPED_MIN_OBSERVATIONS: Final = 3
_TYPED_MAX_ITERATIONS: Final = 256


@dataclass(frozen=True, slots=True)
class _TypedComplexFit:
    activity: float
    lower: float
    upper: float
    coherence: float
    bottleneck: float
    coverage: float
    objective: float
    iterations: int
    convergence_gap: float
    stability: float
    discordance: float
    evidence_count: int
    top_drivers: tuple[str, ...]
    ablation_effects: tuple[str, ...]
    objective_trace: tuple[float, ...]
    converged: bool


def _typed_active(observation: GliomaComplexObservation) -> bool:
    return observation.evidence_state in {
        GliomaComplexEvidenceState.OBSERVED,
        GliomaComplexEvidenceState.LEFT_CENSORED,
    }


def _typed_target(observation: GliomaComplexObservation) -> float:
    if observation.evidence_state is GliomaComplexEvidenceState.OBSERVED:
        value = observation.standardized_effect
        if value is None:
            raise ValueError from None
        return float(value)
    value = observation.censoring_limit
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_error(observation: GliomaComplexObservation) -> float:
    value = observation.standard_error
    if value is None:
        raise ValueError from None
    return float(value)


def _initial_typed_complex_state(
    members: tuple[GliomaComplexObservation, ...],
) -> float:
    """Initialize a complex from observed members and feasible censor bounds."""

    observed = tuple(
        item for item in members if item.evidence_state is GliomaComplexEvidenceState.OBSERVED
    )
    limits = tuple(
        float(item.censoring_limit)
        for item in members
        if item.evidence_state is GliomaComplexEvidenceState.LEFT_CENSORED
        and item.censoring_limit is not None
    )
    if observed:
        values = np.asarray([_typed_target(item) for item in observed], dtype=np.float64)
        weights = np.asarray(
            [
                item.quality_weight
                * item.stoichiometric_weight
                / max(_typed_error(item) ** 2, 1e-12)
                for item in observed
            ],
            dtype=np.float64,
        )
        state = float(np.average(values, weights=weights))
        if limits:
            state = min(state, *limits)
    elif limits:
        state = min(0.0, *limits)
    else:
        state = 0.0
    return float(np.clip(state, -M0902_MAX_TYPED_EFFECT, M0902_MAX_TYPED_EFFECT))


def _typed_residual(state: float, observation: GliomaComplexObservation) -> float:
    if observation.evidence_state is GliomaComplexEvidenceState.LEFT_CENSORED:
        return max(0.0, state - _typed_target(observation))
    return state - _typed_target(observation)


def _typed_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * magnitude * magnitude
        if magnitude <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * magnitude - 0.5 * _TYPED_HUBER_K**2
    )


def _typed_censor_activation(state: float, observation: GliomaComplexObservation) -> float:
    """Return the exact one-sided influence for a censored member.

    A left-censored value is an upper bound, not a noisy target.  Its
    contribution must therefore be absent throughout the feasible region and
    become active only when the latent complex exceeds the detection limit.
    The previous logistic ramp introduced a small but deterministic pull
    toward the limit even when the bound was already satisfied.
    """

    if observation.evidence_state is not GliomaComplexEvidenceState.LEFT_CENSORED:
        return 1.0
    return 1.0 if state > _typed_target(observation) else 0.0


def _typed_objective(
    observations: tuple[GliomaComplexObservation, ...],
    states: dict[str, float],
    *,
    include_bottleneck: bool,
    include_coherence: bool,
) -> float:
    total = 0.0
    grouped: dict[str, list[GliomaComplexObservation]] = {}
    for item in observations:
        if not _typed_active(item):
            continue
        grouped.setdefault(item.complex_id, []).append(item)
        state = states[item.complex_id]
        precision = item.quality_weight * item.stoichiometric_weight / max(
            _typed_error(item) ** 2, 1e-12
        )
        total += precision * _typed_huber(_typed_residual(state, item) / _typed_error(item))
        if include_bottleneck and item.essential:
            total += _TYPED_BOTTLENECK * max(0.0, state - _typed_target(item)) ** 2
    for complex_id, members in grouped.items():
        state = states[complex_id]
        if include_coherence:
            observed_members = tuple(
                item
                for item in members
                if item.evidence_state is GliomaComplexEvidenceState.OBSERVED
            )
            denominator = sum(
                item.quality_weight * item.stoichiometric_weight
                for item in observed_members
            )
            if denominator > 0.0:
                center = sum(
                    item.quality_weight * item.stoichiometric_weight * _typed_target(item)
                    for item in observed_members
                ) / denominator
                total += _TYPED_COHERENCE * (state - center) ** 2
        total += _TYPED_RIDGE * state * state
    return float(total)


def _fit_typed_complexes(  # noqa: C901, PLR0912, PLR0915 - explicit IRLS safeguards and backtracking.
    observations: tuple[GliomaComplexObservation, ...],
    *,
    max_iterations: int,
    include_bottleneck: bool = True,
    include_coherence: bool = True,
) -> tuple[dict[str, float], float, int, float, tuple[float, ...], bool] | None:
    active = tuple(item for item in observations if _typed_active(item))
    if len(active) < _TYPED_MIN_OBSERVATIONS:
        return None
    grouped: dict[str, tuple[GliomaComplexObservation, ...]] = {}
    for complex_id in sorted({item.complex_id for item in active}):
        grouped[complex_id] = tuple(item for item in active if item.complex_id == complex_id)
    states: dict[str, float] = {}
    for complex_id, members in grouped.items():
        states[complex_id] = _initial_typed_complex_state(members)
    previous = _typed_objective(
        active,
        states,
        include_bottleneck=include_bottleneck,
        include_coherence=include_coherence,
    )
    trace = [round(previous, 10)]
    gap = float("inf")
    converged = False
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        iterations = iteration + 1
        proposal = dict(states)
        for complex_id, members in grouped.items():
            state = states[complex_id]
            numerator = 0.0
            denominator = _TYPED_RIDGE
            centers: list[tuple[float, float]] = []
            for item in members:
                residual = _typed_residual(state, item)
                standardized = residual / _typed_error(item)
                robust = (
                    1.0
                    if residual == 0.0
                    else min(1.0, _TYPED_HUBER_K / max(1.0, abs(standardized)))
                )
                precision = (
                    item.quality_weight
                    * item.stoichiometric_weight
                    * _typed_censor_activation(state, item)
                    * robust
                    / max(_typed_error(item) ** 2, 1e-12)
                )
                numerator += precision * _typed_target(item)
                denominator += precision
                if item.evidence_state is GliomaComplexEvidenceState.OBSERVED:
                    centers.append((precision, _typed_target(item)))
                if include_bottleneck and item.essential and state > _typed_target(item):
                    numerator += _TYPED_BOTTLENECK * _typed_target(item)
                    denominator += _TYPED_BOTTLENECK
            if include_coherence and centers:
                center_weight = sum(weight for weight, _ in centers)
                center = sum(weight * target for weight, target in centers) / max(
                    center_weight, 1e-12
                )
                numerator += _TYPED_COHERENCE * center
                denominator += _TYPED_COHERENCE
            raw = numerator / max(denominator, 1e-12)
            proposal[complex_id] = float(
                np.clip(_TYPED_DAMPING * raw + (1.0 - _TYPED_DAMPING) * state,
                        -M0902_MAX_TYPED_EFFECT, M0902_MAX_TYPED_EFFECT)
            )
        gap = max(abs(proposal[key] - states[key]) for key in states)
        blend = 1.0
        candidate = proposal
        objective = _typed_objective(
            active,
            candidate,
            include_bottleneck=include_bottleneck,
            include_coherence=include_coherence,
        )
        while objective > previous + 1e-9 and blend > _TYPED_BACKTRACK_FLOOR:
            blend *= 0.5
            candidate = {
                key: states[key] + blend * (proposal[key] - states[key]) for key in states
            }
            objective = _typed_objective(
                active,
                candidate,
                include_bottleneck=include_bottleneck,
                include_coherence=include_coherence,
            )
        if not isfinite(objective):
            return None
        if objective > previous + 1e-7:
            # The current point is already lower than the robust surrogate
            # proposal; retaining it is the deterministic line-search stop.
            candidate = states
            objective = previous
            gap = 0.0
        states = candidate
        previous = objective
        trace.append(round(objective, 10))
        if gap <= _TYPED_TOLERANCE:
            converged = True
            break
    if not trace or not isfinite(gap) or any(not isfinite(value) for value in trace):
        return None
    return states, previous, iterations, gap, tuple(trace), converged


def _typed_fit(  # noqa: C901 - aggregate fit, bootstrap, and ablation are one replay unit.
    observations: tuple[GliomaComplexObservation, ...],
    request_digest: str,
    request: ConstructComplexActivityRepresentationRequest,
) -> _TypedComplexFit | None:
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.observation_id,
                item.feature_id,
                item.complex_id,
                item.member_id,
            ),
        )
    )
    fitted = _fit_typed_complexes(ordered, max_iterations=request.max_iterations)
    if fitted is None:
        return None
    states, objective, iterations, gap, trace, converged = fitted
    active = tuple(item for item in ordered if _typed_active(item))
    grouped = {
        complex_id: tuple(item for item in active if item.complex_id == complex_id)
        for complex_id in sorted({item.complex_id for item in active})
    }
    all_complexes = {item.complex_id for item in ordered}
    weights = {
        complex_id: sum(
            item.quality_weight * item.stoichiometric_weight for item in members
        )
        for complex_id, members in grouped.items()
    }
    total_weight = sum(weights.values())
    center = sum(weights[key] * states[key] for key in states) / max(total_weight, 1e-12)
    residuals = [_typed_residual(states[item.complex_id], item) for item in active]
    discordance = float(
        np.clip(np.median(np.abs(np.asarray(residuals))) / 3.0, 0.0, 1.0)
    )
    coherence_residual = sum(
        weights[key]
        * abs(
            states[key]
            - sum(
                item.quality_weight
                * item.stoichiometric_weight
                * _typed_target(item)
                for item in members
                if item.evidence_state is GliomaComplexEvidenceState.OBSERVED
            )
            / max(
                sum(
                    item.quality_weight * item.stoichiometric_weight
                    for item in members
                    if item.evidence_state is GliomaComplexEvidenceState.OBSERVED
                ),
                1e-12,
            )
        )
        for key, members in grouped.items()
        if any(item.evidence_state is GliomaComplexEvidenceState.OBSERVED for item in members)
    ) / max(total_weight, 1e-12)
    coherence = float(np.clip(np.exp(-coherence_residual), 0.0, 1.0))
    bottleneck_values = [
        max(0.0, states[key] - _typed_target(item))
        for key, members in grouped.items()
        for item in members
        if item.essential
    ]
    bottleneck = float(
        np.clip(np.mean(bottleneck_values) / 3.0 if bottleneck_values else 0.0, 0.0, 1.0)
    )
    seed = int(
        sha256_digest({"request": request_digest, "model": M0902_GLIOMA_MODEL_FAMILY})
        .removeprefix("sha256:")[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    bootstrap: list[float] = []
    for _ in range(request.bootstrap_replicates):
        sampled: list[GliomaComplexObservation] = []
        for members in grouped.values():
            for index in rng.integers(0, len(members), size=len(members)):
                item = members[int(index)]
                if item.evidence_state is GliomaComplexEvidenceState.OBSERVED:
                    value = _typed_target(item) + _typed_error(item) * float(rng.normal())
                    sampled.append(
                        item.model_copy(
                            update={
                                "standardized_effect": float(
                                    np.clip(value, -M0902_MAX_TYPED_EFFECT, M0902_MAX_TYPED_EFFECT)
                                )
                            }
                        )
                    )
                else:
                    limit = _typed_target(item) + _typed_error(item) * float(rng.normal())
                    sampled.append(
                        item.model_copy(
                            update={
                                "censoring_limit": float(
                                    np.clip(limit, -M0902_MAX_TYPED_EFFECT, M0902_MAX_TYPED_EFFECT)
                                )
                            }
                        )
                    )
        replicate = _fit_typed_complexes(tuple(sampled), max_iterations=request.max_iterations)
        if replicate is not None:
            rep_states = replicate[0]
            rep_weights = {
                key: sum(item.quality_weight * item.stoichiometric_weight for item in members)
                for key, members in grouped.items()
                if key in rep_states
            }
            denom = sum(rep_weights.values())
            if denom:
                bootstrap.append(
                    sum(rep_weights[key] * rep_states[key] for key in rep_states) / denom
                )
    if len(bootstrap) < max(8, request.bootstrap_replicates // 2):
        return None
    lower, upper = np.quantile(np.asarray(bootstrap, dtype=np.float64), (0.05, 0.95))
    lower = float(min(lower, center))
    upper = float(max(upper, center))
    without_bottleneck = _fit_typed_complexes(
        ordered, max_iterations=request.max_iterations, include_bottleneck=False
    )
    without_coherence = _fit_typed_complexes(
        ordered, max_iterations=request.max_iterations, include_coherence=False
    )
    ablations: list[str] = []
    if without_bottleneck is not None:
        ablated_center = sum(
            weights[key] * without_bottleneck[0][key] for key in states
        ) / max(total_weight, 1e-12)
        ablations.append(f"essential_bottleneck_delta={abs(center - ablated_center):.8f}")
    if without_coherence is not None:
        ablated_center = sum(
            weights[key] * without_coherence[0][key] for key in states
        ) / max(total_weight, 1e-12)
        ablations.append(f"stoichiometric_coherence_delta={abs(center - ablated_center):.8f}")
    contributions = sorted(
        (abs(residuals[index]) * active[index].quality_weight, active[index])
        for index in range(len(active))
    )
    return _TypedComplexFit(
        activity=round(center, 8),
        lower=round(lower, 8),
        upper=round(upper, 8),
        coherence=round(coherence, 8),
        bottleneck=round(bottleneck, 8),
        coverage=round(len(grouped) / max(len(all_complexes), 1), 8),
        objective=round(objective, 8),
        iterations=iterations,
        convergence_gap=round(gap, 8),
        stability=round(float(np.clip(1.0 - (upper - lower) / 6.0, 0.0, 1.0)), 8),
        discordance=round(discordance, 8),
        evidence_count=len(active),
        top_drivers=tuple(
            f"{item.complex_id}:{item.member_id}" for _, item in reversed(contributions[-4:])
        ),
        ablation_effects=tuple(ablations),
        objective_trace=trace,
        converged=converged,
    )


def _evidence(
    request: ConstructComplexActivityRepresentationRequest,
) -> tuple[EvidenceReference, ...]:
    references: dict[str, EvidenceReference] = {
        item.artifact_id: EvidenceReference(
            reference=item, role="evidence", claim=M0902_EVIDENCE_CLAIM
        )
        for item in request.source_artifacts
    }
    for observation in request.typed_observations:
        for evidence in observation.evidence:
            references.setdefault(evidence.reference.artifact_id, evidence)
    return tuple(references[key] for key in sorted(references))


def _quality_reason(request: ConstructComplexActivityRepresentationRequest) -> str | None:
    """Return a safe-failure reason for explicit unsupported/poor-quality markers."""

    haystack = " ".join(
        (
            request.policy.scaling_method,
            request.policy.mask_policy,
            *(item.artifact_id for item in request.source_artifacts),
            *(item.media_type for item in request.source_artifacts),
        )
    ).casefold()
    markers = (
        ("missing", "required representation input is missing"),
        ("unsupported", "representation input or transformation is unsupported"),
        ("ood", "representation input is outside the declared support domain"),
        ("not_evaluable", "representation quality cannot be evaluated safely"),
    )
    for marker, reason in markers:
        if marker in haystack:
            return reason
    return None


def _leakage_checks(
    request: ConstructComplexActivityRepresentationRequest,
) -> tuple[tuple[LeakageCheck, ...], str | None]:
    checks: list[LeakageCheck] = []
    failure: str | None = None
    policy_text = f"{request.policy.scaling_method} {request.policy.mask_policy}".casefold()
    for specification in request.feature_specs:
        marker = " ".join(specification.lineage.source_fields).casefold()
        if "leakage_failure" in policy_text or "leakage_failure" in marker:
            status = LeakageCheckStatus.FAILED
            message = "held-out group is not isolated from the transformation fit"
            failure = "leakage check failed for " + specification.feature_id
        elif "leakage_unknown" in policy_text or "leakage_unknown" in marker:
            status = LeakageCheckStatus.NOT_EVALUABLE
            message = "held-out group metadata is unavailable"
            failure = "leakage check is not evaluable for " + specification.feature_id
        else:
            status = LeakageCheckStatus.PASSED
            message = "locked transformation has no access to held-out target information"
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{specification.feature_id}",
                status=status,
                message=message,
                held_out_group=("held-out-group" if status is LeakageCheckStatus.FAILED else None),
                evidence=specification.lineage.evidence,
            )
        )
    return tuple(checks), failure


def _typed_result(
    request: ConstructComplexActivityRepresentationRequest,
) -> ComplexActivityRepresentationResult:
    """Build a typed glioma complex representation with replay-visible diagnostics."""

    request = request.model_copy(
        update={
            "typed_observations": tuple(
                sorted(
                    request.typed_observations,
                    key=lambda item: (
                        item.observation_id,
                        item.feature_id,
                        item.complex_id,
                        item.member_id,
                    ),
                )
            )
        }
    )
    request_digest = canonical_request_digest(request)
    checks, leakage_failure = _leakage_checks(request)
    quality_failure = _quality_reason(request)
    evidence = _evidence(request)
    reason = leakage_failure or quality_failure
    fits: dict[str, _TypedComplexFit] = {}
    if reason is None:
        for specification in request.feature_specs:
            members = tuple(
                item
                for item in request.typed_observations
                if item.feature_id == specification.feature_id
            )
            fit = _typed_fit(members, request_digest, request)
            if fit is None or not fit.converged:
                reason = (
                    "typed glioma complex activity needs at least three supported member "
                    "observations "
                    "and a converged robust stoichiometric fit for every requested feature"
                )
                break
            fits[specification.feature_id] = fit
    diagnostics: list[ComplexOptimizationDiagnostic] = []
    for specification in request.feature_specs:
        fit = fits.get(specification.feature_id)
        if fit is None:
            diagnostics.append(
                ComplexOptimizationDiagnostic(
                    diagnostic_id=f"diagnostic.{specification.feature_id}.typed",
                    status=ComplexOptimizationStatus.NOT_EVALUABLE,
                    objective="glioma_complex_activity",
                    iteration_count=0,
                    model_family=M0902_GLIOMA_MODEL_FAMILY,
                    message=reason or "typed complex fit was not evaluable",
                    evidence=evidence,
                )
            )
        else:
            diagnostics.append(
                ComplexOptimizationDiagnostic(
                    diagnostic_id=f"diagnostic.{specification.feature_id}.typed",
                    status=ComplexOptimizationStatus.CONVERGED,
                    objective="glioma_complex_activity",
                    iteration_count=fit.iterations,
                    objective_value=fit.objective,
                    convergence_gap=fit.convergence_gap,
                    objective_trace_digest=sha256_digest({"trace": fit.objective_trace}),
                    model_family=M0902_GLIOMA_MODEL_FAMILY,
                    message=(
                        "typed glioma complex activity converged with Huber IRLS, "
                        "essential-subunit "
                        "bottleneck penalties, stoichiometric coherence, and stratified bootstrap"
                    ),
                    evidence=evidence,
                )
            )
    features: list[RepresentationFeature] = []
    if reason is None:
        for specification in request.feature_specs:
            fit = fits[specification.feature_id]
            channels = (
                fit.activity,
                fit.coherence,
                fit.bottleneck,
                fit.coverage,
            )
            values = tuple(
                round(channels[index] if index < len(channels) else channels[-1], 8)
                for index in range(specification.dimension)
            )
            features.append(
                RepresentationFeature(
                    feature_id=specification.feature_id,
                    value_kind=specification.value_kind,
                    unit=specification.unit,
                    values=values,
                    mask=tuple(True for _ in values),
                    lineage=specification.lineage,
                    evidence_count=fit.evidence_count,
                    stability=fit.stability,
                    discordance=fit.discordance,
                    top_drivers=fit.top_drivers,
                    ablation_effects=fit.ablation_effects,
                    lower_bound=fit.lower,
                    upper_bound=fit.upper,
                    model_family=M0902_GLIOMA_MODEL_FAMILY,
                    evidence=evidence,
                )
            )
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if reason is None
        else RepresentationConstructionStatus.ABSTAINED
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if reason is None else SupportStatus.REVIEW_REQUIRED,
        reason_code=(
            "m0902_typed_glioma_supported"
            if reason is None
            else "m0902_typed_glioma_abstention"
        ),
        rationale=(
            "explicit glioma member evidence supports a robust constrained complex representation"
            if reason is None
            else reason
        ),
    )
    draft = ComplexActivityRepresentationResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        features=tuple(features),
        optimization_diagnostics=tuple(diagnostics),
        model_family=M0902_GLIOMA_MODEL_FAMILY,
        leakage_checks=checks,
        abstention_reason=reason,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=support,
        uncertainty=_typed_uncertainty() if reason is None else _uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


def _build_result(
    request: ConstructComplexActivityRepresentationRequest,
) -> ComplexActivityRepresentationResult:
    if request.typed_observations:
        return _typed_result(request)
    checks, leakage_failure = _leakage_checks(request)
    quality_failure = _quality_reason(request)
    reason = leakage_failure or quality_failure
    evidence = _evidence(request)
    features: list[RepresentationFeature] = []
    if reason is None:
        for specification in request.feature_specs:
            values = _values(specification, request)
            mask = tuple(True for _ in values)
            features.append(
                RepresentationFeature(
                    feature_id=specification.feature_id,
                    value_kind=specification.value_kind,
                    unit=specification.unit,
                    values=values,
                    mask=mask,
                    lineage=specification.lineage,
                    evidence=evidence,
                )
            )
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if reason is None
        else RepresentationConstructionStatus.ABSTAINED
    )
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if reason is None else SupportStatus.UNSUPPORTED,
        reason_code="m0902_representation_support",
        rationale=(
            "all requested features have complete leakage-safe lineage and supported inputs"
            if reason is None
            else reason
        ),
    )
    draft = ComplexActivityRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest=_ZERO_DIGEST,
        request=request,
        status=status,
        features=tuple(features),
        leakage_checks=checks,
        abstention_reason=reason,
        parent_target="complex_activity",
        emits_parent=False,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    payload = draft.model_dump(mode="python")
    payload["result_digest"] = result_payload_digest(draft)
    return _RESULT_ADAPTER.validate_python(payload, strict=True)


class M0902RepresentationConstructor:
    """Validate, construct, and replay one deterministic M09-02 result."""

    @staticmethod
    def validate_request(request: object) -> ConstructComplexActivityRepresentationRequest:
        preflight_m0902_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltM0902Result:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0902_MAX_CANONICAL_RESULT_BYTES:
            raise M0902InputError("result_limit")
        return BuiltM0902Result(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
        request: object | None = None,
    ) -> bool:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return False
        if typed.provenance != _provenance(typed.request):
            return False
        if canonical_bytes is not None:
            if (
                type(canonical_bytes) is not bytes
                or len(canonical_bytes) > M0902_MAX_CANONICAL_RESULT_BYTES
            ):
                return False
            if canonical_bytes != canonical_json_bytes(typed.model_dump(mode="json")):
                return False
        if typed.result_digest != result_payload_digest(typed):
            return False
        return request is None or typed == self.construct(request).result

    def execute(self, request: object) -> BuiltM0902Result:
        return self.construct(request)


def construct_complex_activity_representation(request: object) -> BuiltM0902Result:
    """Public provisional M09-02 operation."""

    return M0902RepresentationConstructor().construct(request)


__all__ = [
    "BuiltM0902Result",
    "M0902AuthorizationError",
    "M0902InputError",
    "M0902RepresentationConstructor",
    "construct_complex_activity_representation",
    "preflight_m0902_authorization",
]
