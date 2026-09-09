"""Deterministic leakage-safe representation construction runtime."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import log2
from typing import Final

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m07_02 import (
    M0702_EVIDENCE_CLAIM,
    M0702_GLIOMA_MODEL_FAMILY,
    M0702_MAX_CANONICAL_RESULT_BYTES,
    M0702_MAX_TYPED_EFFECT,
    ConstructProteotypeAnalysisRepresentationRequest,
    ConstructProteotypeAnalysisRepresentationVerification,
    FeatureSpecification,
    GliomaCopyNumberEvidenceState,
    GliomaCopyNumberObservation,
    GliomaRepresentationOptimizationDiagnostic,
    GliomaRepresentationOptimizationStatus,
    LeakageCheck,
    LeakageCheckStatus,
    ProteotypeAnalysisRepresentationResult,
    RepresentationConstructionStatus,
    RepresentationFeature,
    RepresentationReplayReason,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructProteotypeAnalysisRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(ProteotypeAnalysisRepresentationResult)
_LEAKAGE_TOKENS: Final = frozenset({"future", "outcome", "target", "label", "held_out"})


class RepresentationAuthorizationError(PermissionError):
    """Raised before an unauthorized request traverses source metadata."""

    def __init__(self) -> None:
        super().__init__("M07-02 representation request is not authorized")


class RepresentationInputError(ValueError):
    """Raised for malformed, oversized, or non-canonical representations."""

    _MESSAGES: Final = {
        "result_limit": "representation result exceeds byte limit",
        "result_digest": "representation result digest does not match",
        "result_noncanonical": "representation result bytes are not canonical",
    }

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self._MESSAGES.get(reason, reason))


@dataclass(frozen=True, slots=True)
class BuiltRepresentation:
    """Typed result and its only canonical byte representation."""

    result: ProteotypeAnalysisRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise RepresentationInputError("result_digest")
        if canonical_json_bytes(self.result.model_dump(mode="json")) != self.canonical_bytes:
            raise RepresentationInputError("result_noncanonical")


def preflight_representation_authorization(request: object) -> None:
    """Apply shared consent, identity, and accepted-control gates."""

    if not isinstance(request, ConstructProteotypeAnalysisRepresentationRequest):
        return
    refs = request.context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise RepresentationAuthorizationError
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise RepresentationAuthorizationError
    controls = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in controls):
        raise RepresentationAuthorizationError


def _control_decisions(
    request: ConstructProteotypeAnalysisRepresentationRequest,
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


def _provenance(request: ConstructProteotypeAnalysisRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    typed_digests = {
        reference.reference.digest
        for item in request.typed_observations
        for reference in item.evidence
    }
    input_digests = tuple(
        sorted(
            {artifact.digest for artifact in request.source_artifacts}
            | {request.formal_state_result.digest}
            | typed_digests
            | {request.policy.evidence[0].reference.digest}
            if request.policy.evidence
            else {artifact.digest for artifact in request.source_artifacts}
            | {request.formal_state_result.digest}
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id="GLIO-PROTEOGEN-M07-02",
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


def _uncertainty() -> UncertaintyProfile:
    not_estimable = UncertaintyEstimate(
        state=EstimateState.NOT_ESTIMABLE,
        rationale="Provisional constructor has no locked uncertainty estimator.",
    )
    return UncertaintyProfile(
        measurement=not_estimable,
        sampling=not_estimable,
        parameter=not_estimable,
        model_form=not_estimable,
        identification=not_estimable,
        support=not_estimable,
        transport=not_estimable,
        sensitivity_notes=("M07-02 uncertainty estimator remains provisional.",),
    )


def _typed_uncertainty() -> UncertaintyProfile:
    def _estimate(probability: float, dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=f"typed M07-02 glioma copy-number {dimension} uncertainty",
        )

    return UncertaintyProfile(
        measurement=_estimate(0.10, "measurement"),
        sampling=_estimate(0.10, "sampling"),
        parameter=_estimate(0.15, "parameter"),
        model_form=_estimate(0.20, "model-form"),
        identification=_estimate(0.10, "identification"),
        support=_estimate(0.15, "support"),
        transport=_estimate(0.25, "transport"),
        sensitivity_notes=(
            "Purity-adjusted copy-number intervals are replay-stable but not clinically "
            "calibrated.",
            "Typed copy-number output is a research signal only.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "Feature catalogue, transform vocabulary, limits, and endpoints remain provisional."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "This runtime constructs an analysis representation and emits no parent "
                "proteotype claim."
            ),
        ),
        Limitation(
            code="no_kinase_activity",
            statement="KINOPHOS owns kinase activity; M07-02 never emits it.",
        ),
        Limitation(
            code="synthetic_constructor",
            statement=(
                "Values are deterministic provisional constructor values until an owner-approved "
                "estimator is supplied."
            ),
        ),
        Limitation(
            code="typed_research_lane",
            statement=(
                "Typed glioma values use purity-adjusted segment evidence and robust uncertainty; "
                "they are research-use-only and do not emit a clinical copy-number call."
            ),
        ),
    )


def _leakage_reason(spec: FeatureSpecification) -> str | None:
    fields = {field.casefold() for field in spec.lineage.source_fields}
    tokens = {token for field in fields for token in field.replace("-", "_").split("_")}
    if tokens & _LEAKAGE_TOKENS:
        return "feature lineage references a future, outcome, target, label, or held-out field"
    if any(not transform.leakage_safe for transform in spec.lineage.transformations):
        return "feature lineage contains a leakage-unsafe transformation"
    return None


def _feature_values(
    spec: FeatureSpecification,
    request: ConstructProteotypeAnalysisRepresentationRequest,
) -> tuple[float, ...]:
    seed = "|".join(
        [
            spec.feature_id,
            request.formal_state_result.digest,
            *sorted(artifact.digest for artifact in request.source_artifacts),
            *spec.lineage.source_fields,
            *[transform.parameters_digest for transform in spec.lineage.transformations],
        ]
    ).encode("utf-8")
    values: list[float] = []
    for index in range(spec.dimension):
        digest = sha256(seed + index.to_bytes(4, "big")).digest()
        raw = int.from_bytes(digest[:8], "big") / float(2**64)
        values.append(round((raw * 2.0) - 1.0, 8))
    return tuple(values)


_TYPED_HUBER_K: Final = 1.5
_TYPED_DAMPING: Final = 0.62
_TYPED_RIDGE: Final = 0.12
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_BACKTRACKING_FLOOR: Final = 1e-3
_TYPED_MAX_ITERATIONS: Final = 256
_TYPED_MIN_OBSERVATIONS: Final = 1
_TYPED_DIRECTION_THRESHOLD: Final = 0.25
_TYPED_SEGMENT_SCALE: Final = 1_000_000.0
_TYPED_CHANNELS: Final = (
    "latent_dosage",
    "residual_scale",
    "amplified_fraction",
    "deleted_fraction",
    "allelic_imbalance",
    "mean_tumor_purity",
    "focal_segment_score",
)


@dataclass(frozen=True, slots=True)
class _TypedFeatureFit:
    value: float
    objective: float
    iterations: int
    convergence_gap: float
    trace: tuple[float, ...]
    residuals: tuple[float, ...]


def _typed_active(item: GliomaCopyNumberObservation) -> bool:
    return item.evidence_state in {
        GliomaCopyNumberEvidenceState.OBSERVED,
        GliomaCopyNumberEvidenceState.LEFT_CENSORED,
    }


def _typed_censored(item: GliomaCopyNumberObservation) -> bool:
    return item.evidence_state is GliomaCopyNumberEvidenceState.LEFT_CENSORED


def _typed_target(item: GliomaCopyNumberObservation) -> float:
    """Convert a log-ratio to a purity-adjusted diploid-relative effect."""

    raw = item.censoring_limit if _typed_censored(item) else item.log2_ratio
    if raw is None or item.tumor_purity is None:
        return 0.0
    bounded = max(-M0702_MAX_TYPED_EFFECT, min(M0702_MAX_TYPED_EFFECT, raw))
    tumor_ratio = 2.0**bounded
    normal_fraction = 1.0 - item.tumor_purity
    corrected_ratio = max((tumor_ratio - normal_fraction) / item.tumor_purity, 2.0**-20)
    return max(-M0702_MAX_TYPED_EFFECT, min(M0702_MAX_TYPED_EFFECT, log2(corrected_ratio)))


def _typed_weight(item: GliomaCopyNumberObservation) -> float:
    if item.standard_error is None or item.quality_weight <= 0.0:
        return 0.0
    return item.quality_weight / max(item.standard_error * item.standard_error, 1e-8)


def _typed_huber(value: float) -> float:
    magnitude = abs(value)
    return 0.5 * magnitude * magnitude if magnitude <= _TYPED_HUBER_K else (
        _TYPED_HUBER_K * (magnitude - 0.5 * _TYPED_HUBER_K)
    )


def _typed_objective(
    value: float,
    items: tuple[GliomaCopyNumberObservation, ...],
    targets: tuple[float, ...],
) -> float:
    objective = _TYPED_RIDGE * value * value
    for item, target in zip(items, targets, strict=True):
        scale = item.standard_error or 1.0
        residual = (value - target) / scale
        if _typed_censored(item):
            residual = max(0.0, residual)
        objective += _typed_weight(item) * _typed_huber(residual)
    return float(objective)


def _initial_typed_feature_value(
    items: tuple[GliomaCopyNumberObservation, ...],
    targets: tuple[float, ...],
) -> float:
    """Find a robust feasible start for the one-dimensional typed fit.

    Left-censored observations define upper bounds, not pseudo-measurements.
    The observed weighted center is therefore projected onto the tightest
    bound; when only censored evidence is available, the ridge-neutral point
    (zero) is retained whenever it is feasible.
    """

    observed = tuple(
        (target, _typed_weight(item))
        for item, target in zip(items, targets, strict=True)
        if not _typed_censored(item) and _typed_weight(item) > 0.0
    )
    weight_total = sum(weight for _, weight in observed)
    value = (
        sum(target * weight for target, weight in observed) / weight_total
        if weight_total > 0.0
        else 0.0
    )
    censor_bounds = tuple(
        target
        for item, target in zip(items, targets, strict=True)
        if _typed_censored(item)
    )
    if censor_bounds:
        value = min(value, *censor_bounds)
    return max(-M0702_MAX_TYPED_EFFECT, min(M0702_MAX_TYPED_EFFECT, value))


def _fit_typed_feature(
    items: tuple[GliomaCopyNumberObservation, ...],
    *,
    max_iterations: int,
    targets: tuple[float, ...] | None = None,
) -> _TypedFeatureFit:
    active = tuple(item for item in items if _typed_active(item))
    if not active:
        return _TypedFeatureFit(0.0, 0.0, 0, 0.0, (0.0,), ())
    effective_targets = targets or tuple(_typed_target(item) for item in active)
    value = _initial_typed_feature_value(active, effective_targets)
    trace = [_typed_objective(value, active, effective_targets)]
    gap = float("inf")
    damping = _TYPED_DAMPING
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        gradient = _TYPED_RIDGE * value
        curvature = _TYPED_RIDGE
        for item, target in zip(active, effective_targets, strict=True):
            scale = item.standard_error or 1.0
            residual = (value - target) / scale
            if _typed_censored(item) and residual <= 0.0:
                continue
            robust_weight = 1.0 if abs(residual) <= _TYPED_HUBER_K else _TYPED_HUBER_K / abs(
                residual
            )
            weight = _typed_weight(item) * robust_weight
            gradient += weight * (value - target)
            curvature += weight
        proposal = value - gradient / max(curvature, 1e-12)
        proposal = max(-M0702_MAX_TYPED_EFFECT, min(M0702_MAX_TYPED_EFFECT, proposal))
        current_objective = trace[-1]
        candidate = value + damping * (proposal - value)
        candidate_objective = _typed_objective(candidate, active, effective_targets)
        while (
            candidate_objective > current_objective + 1e-10
            and damping > _TYPED_BACKTRACKING_FLOOR
        ):
            damping *= 0.5
            candidate = value + damping * (proposal - value)
            candidate_objective = _typed_objective(candidate, active, effective_targets)
        gap = abs(candidate - value)
        value = candidate
        trace.append(candidate_objective)
        iterations = iteration + 1
        if gap <= _TYPED_TOLERANCE:
            break
    residuals = tuple(
        (value - target) / (item.standard_error or 1.0)
        for item, target in zip(active, effective_targets, strict=True)
    )
    return _TypedFeatureFit(
        value=value,
        objective=trace[-1],
        iterations=iterations,
        convergence_gap=gap if np.isfinite(gap) else 0.0,
        trace=tuple(round(point, 12) for point in trace),
        residuals=tuple(round(point, 12) for point in residuals),
    )


def _typed_seed(request: ConstructProteotypeAnalysisRepresentationRequest) -> int:
    digest = canonical_request_digest(request).removeprefix("sha256:")
    return int(digest[:16], 16) % (2**32)


def _typed_channels(
    items: tuple[GliomaCopyNumberObservation, ...],
    fit: _TypedFeatureFit,
    bootstrap_values: tuple[float, ...],
) -> tuple[tuple[float, ...], float, float, tuple[str, ...]]:
    active = tuple(item for item in items if _typed_active(item))
    weights = tuple(_typed_weight(item) for item in active)
    weight_total = sum(weights)
    if weight_total <= 0.0:
        weight_total = float(len(active)) or 1.0
        weights = (1.0,) * len(active)
    def weighted(values: tuple[float, ...]) -> float:
        return sum(
            value * weight for value, weight in zip(values, weights, strict=True)
        ) / weight_total

    targets = tuple(_typed_target(item) for item in active)
    amplified = weighted(tuple(float(value > _TYPED_DIRECTION_THRESHOLD) for value in targets))
    deleted = weighted(tuple(float(value < -_TYPED_DIRECTION_THRESHOLD) for value in targets))
    imbalance_values = tuple(
        abs((item.minor_copy_number or 1.0) - 1.0)
        for item in active
    )
    purities = tuple(item.tumor_purity or 0.0 for item in active)
    lengths = tuple(item.segment_end - item.segment_start + 1 for item in active)
    focality = weighted(
        tuple(
            1.0
            / (1.0 + max(0.0, log2(max(length, 1) / _TYPED_SEGMENT_SCALE)))
            for length in lengths
        )
    )
    residual_scale = float(
        np.sqrt(weighted(tuple(residual * residual for residual in fit.residuals)))
    )
    channels = (
        fit.value,
        residual_scale,
        amplified,
        deleted,
        weighted(imbalance_values),
        weighted(purities),
        focality,
    )
    if bootstrap_values:
        lower, upper = np.quantile(np.asarray(bootstrap_values), (0.05, 0.95)).tolist()
        stability = float(np.exp(-max(0.0, upper - lower)))
    else:
        stability = 0.0
    discordance = float(min(1.0, residual_scale / (_TYPED_HUBER_K + residual_scale)))
    drivers = tuple(
        f"{item.gene}@{item.chromosome}:{item.segment_start}-{item.segment_end}"
        for item, residual in sorted(
            zip(active, fit.residuals, strict=True),
            key=lambda pair: (-abs(pair[1]), pair[0].observation_id),
        )[:8]
    )
    return channels, stability, discordance, drivers


def _build_typed_result(  # noqa: PLR0915
    request: ConstructProteotypeAnalysisRepresentationRequest,
) -> ProteotypeAnalysisRepresentationResult:
    """Construct typed features from purity-aware segment evidence."""

    request = request.model_copy(
        update={
            "typed_observations": tuple(
                sorted(request.typed_observations, key=lambda item: item.observation_id)
            )
        }
    )
    checks: list[LeakageCheck] = []
    features: list[RepresentationFeature] = []
    failure_reasons: list[str] = []
    all_active = tuple(item for item in request.typed_observations if _typed_active(item))
    if len(all_active) < _TYPED_MIN_OBSERVATIONS:
        failure_reasons.append("insufficient supported typed copy-number evidence")
    grouped: dict[str, tuple[GliomaCopyNumberObservation, ...]] = {}
    for item in sorted(request.typed_observations, key=lambda value: value.observation_id):
        grouped[item.feature_id] = (*grouped.get(item.feature_id, ()), item)
    diagnostics_trace: list[float] = []
    total_objective = 0.0
    total_iterations = 0
    max_gap = 0.0
    all_converged = True
    seed = _typed_seed(request)
    rng = np.random.default_rng(seed)
    for spec in request.feature_specs:
        leakage_reason = _leakage_reason(spec)
        leakage_status = (
            LeakageCheckStatus.FAILED if leakage_reason else LeakageCheckStatus.PASSED
        )
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{spec.feature_id}",
                status=leakage_status,
                message=(
                    leakage_reason
                    or "typed copy-number lineage and transformations pass leakage checks"
                ),
                held_out_group=(spec.feature_id if leakage_reason else None),
            )
        )
        if leakage_reason:
            failure_reasons.append(leakage_reason)
            continue
        items = grouped.get(spec.feature_id, ())
        active = tuple(item for item in items if _typed_active(item))
        if not active:
            failure_reasons.append(f"feature {spec.feature_id} has no supported typed evidence")
            continue
        fit = _fit_typed_feature(active, max_iterations=request.max_iterations)
        bootstrap_values: list[float] = []
        targets = tuple(_typed_target(item) for item in active)
        for _ in range(request.bootstrap_replicates):
            indices = rng.integers(0, len(active), size=len(active))
            replicate_items = tuple(active[int(index)] for index in indices)
            perturbations = tuple(
                target + float(rng.normal(0.0, item.standard_error or 1.0) * 0.5)
                for item, target in zip(
                    replicate_items,
                    (targets[int(index)] for index in indices),
                    strict=True,
                )
            )
            bootstrap_values.append(
                _fit_typed_feature(
                    replicate_items,
                    max_iterations=min(request.max_iterations, 64),
                    targets=perturbations,
                ).value
            )
        channels, stability, discordance, drivers = _typed_channels(
            active,
            fit,
            tuple(bootstrap_values),
        )
        values = tuple(
            round(channels[index % len(channels)], 8) for index in range(spec.dimension)
        )
        evidence = tuple(
            reference
            for item in active
            for reference in item.evidence
        )
        features.append(
            RepresentationFeature(
                feature_id=spec.feature_id,
                value_kind=spec.value_kind,
                unit=spec.unit,
                values=values,
                mask=(True,) * spec.dimension if spec.value_kind.value == "mask" else (),
                evidence_count=len(active),
                stability=round(stability, 8),
                discordance=round(discordance, 8),
                top_drivers=drivers,
                model_family=M0702_GLIOMA_MODEL_FAMILY,
                lineage=spec.lineage,
                evidence=evidence,
            )
        )
        diagnostics_trace.extend(fit.trace)
        total_objective += fit.objective
        total_iterations += fit.iterations
        max_gap = max(max_gap, fit.convergence_gap)
        all_converged = all_converged and fit.convergence_gap <= _TYPED_TOLERANCE
    constructed = not failure_reasons and len(features) == len(request.feature_specs)
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if constructed
        else RepresentationConstructionStatus.ABSTAINED
    )
    reason = None if constructed else "; ".join(dict.fromkeys(failure_reasons))
    support_status = SupportStatus.SUPPORTED if constructed else SupportStatus.REVIEW_REQUIRED
    support = SupportDecision(
        status=support_status,
        reason_code="representation_support_state",
        rationale=(
            "typed glioma copy-number evidence and leakage gates are satisfied"
            if constructed
            else reason or "typed representation construction requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0702_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    ) + tuple(
        reference
        for item in request.typed_observations
        for reference in item.evidence
    ) + request.policy.evidence
    diagnostic_status = (
        GliomaRepresentationOptimizationStatus.CONVERGED
        if constructed and all_converged
        else GliomaRepresentationOptimizationStatus.NOT_EVALUABLE
        if not all_active
        else GliomaRepresentationOptimizationStatus.NOT_CONVERGED
    )
    trace_digest = sha256_digest(
        {
            "model_family": M0702_GLIOMA_MODEL_FAMILY,
            "trace": diagnostics_trace,
            "seed": seed,
        }
    )
    diagnostic = GliomaRepresentationOptimizationDiagnostic(
        diagnostic_id=f"diagnostic.{request.request_id}",
        status=diagnostic_status,
        objective="purity-adjusted Huber IRLS latent dosage with ridge regularization",
        iteration_count=total_iterations,
        objective_value=round(total_objective, 12) if all_active else None,
        convergence_gap=round(max_gap, 12) if all_active else None,
        objective_trace_digest=trace_digest if all_active else None,
        model_family=M0702_GLIOMA_MODEL_FAMILY,
        message=(
            "typed purity-aware dosage fit converged"
            if diagnostic_status is GliomaRepresentationOptimizationStatus.CONVERGED
            else "typed dosage fit abstained or did not meet convergence tolerance"
        ),
        evidence=evidence,
    )
    draft = ProteotypeAnalysisRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        features=tuple(features) if constructed else (),
        leakage_checks=tuple(checks),
        optimization_diagnostics=(diagnostic,),
        model_family=M0702_GLIOMA_MODEL_FAMILY,
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_typed_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return ProteotypeAnalysisRepresentationResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


def _build_result(
    request: ConstructProteotypeAnalysisRepresentationRequest,
) -> ProteotypeAnalysisRepresentationResult:
    if request.typed_observations:
        return _build_typed_result(request)
    duplicate_sources = len({item.artifact_id for item in request.source_artifacts}) != len(
        request.source_artifacts
    )
    checks: list[LeakageCheck] = []
    features: list[RepresentationFeature] = []
    failure_reasons: list[str] = []
    for spec in request.feature_specs:
        leakage_reason = _leakage_reason(spec)
        leakage_status = (
            LeakageCheckStatus.FAILED if leakage_reason else LeakageCheckStatus.PASSED
        )
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{spec.feature_id}",
                status=leakage_status,
                message=(
                    leakage_reason
                    or "lineage and transformations pass provisional leakage checks"
                ),
                held_out_group=(spec.feature_id if leakage_reason else None),
            )
        )
        if leakage_reason:
            failure_reasons.append(leakage_reason)
            continue
        features.append(
            RepresentationFeature(
                feature_id=spec.feature_id,
                value_kind=spec.value_kind,
                unit=spec.unit,
                values=_feature_values(spec, request),
                mask=(True,) * spec.dimension if spec.value_kind.value == "mask" else (),
                lineage=spec.lineage,
            )
        )
    if duplicate_sources:
        failure_reasons.append("source artifact identifiers must be unique")
    constructed = not failure_reasons and len(features) == len(request.feature_specs)
    construction_status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if constructed
        else RepresentationConstructionStatus.ABSTAINED
    )
    reason = None if constructed else "; ".join(dict.fromkeys(failure_reasons))
    support_status = SupportStatus.SUPPORTED if constructed else SupportStatus.REVIEW_REQUIRED
    support = SupportDecision(
        status=support_status,
        reason_code="representation_support_state",
        rationale=(
            "all feature lineage and leakage-safe construction gates are satisfied"
            if constructed
            else reason or "representation construction requires review"
        ),
    )
    evidence = tuple(
        EvidenceReference(reference=item, role="evidence", claim=M0702_EVIDENCE_CLAIM)
        for item in request.source_artifacts
    ) + request.policy.evidence
    draft = ProteotypeAnalysisRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=construction_status,
        features=tuple(features) if constructed else (),
        leakage_checks=tuple(checks),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return ProteotypeAnalysisRepresentationResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0702RepresentationEngine:
    """Build, replay, and verify one deterministic representation."""

    @staticmethod
    def validate_request(request: object) -> ConstructProteotypeAnalysisRepresentationRequest:
        preflight_representation_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltRepresentation:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0702_MAX_CANONICAL_RESULT_BYTES:
            raise RepresentationInputError("result_limit")
        return BuiltRepresentation(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ConstructProteotypeAnalysisRepresentationVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ConstructProteotypeAnalysisRepresentationVerification(
                content_verified=False,
                deterministic_verified=False,
                verified=False,
                reason=RepresentationReplayReason.INVALID_RESULT,
            )
        deterministic_verified = typed.result_digest == result_payload_digest(typed)
        expected_bytes = canonical_json_bytes(typed.model_dump(mode="json"))
        content_verified = canonical_bytes is None or canonical_bytes == expected_bytes
        if canonical_bytes is not None and (
            type(canonical_bytes) is not bytes
            or len(canonical_bytes) > M0702_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        return ConstructProteotypeAnalysisRepresentationVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=(
                RepresentationReplayReason.VERIFIED
                if verified
                else RepresentationReplayReason.DIGEST_MISMATCH
            ),
        )

    def execute(self, request: object) -> BuiltRepresentation:
        return self.construct(request)


def construct_proteotype_analysis_representation(request: object) -> BuiltRepresentation:
    """Construct one representation through the stateless default engine."""

    return M0702RepresentationEngine().construct(request)


__all__ = [
    "BuiltRepresentation",
    "M0702RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "construct_proteotype_analysis_representation",
    "preflight_representation_authorization",
]
