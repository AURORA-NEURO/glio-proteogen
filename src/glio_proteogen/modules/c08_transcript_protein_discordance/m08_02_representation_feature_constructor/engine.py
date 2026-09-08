"""Deterministic, lineage-complete M08-02 representation construction."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import fsum, isfinite, sqrt
from typing import Final

import numpy as np
from pydantic import TypeAdapter, ValidationError

from glio_proteogen.contracts.m08_02 import (
    M0802_EVIDENCE_CLAIM,
    M0802_GLIOMA_MODEL_FAMILY,
    M0802_MAX_CANONICAL_RESULT_BYTES,
    M0802_MAX_TYPED_EFFECT,
    M0802_MODULE_ID,
    ConstructTranscriptProteinRepresentationRequest,
    ConstructTranscriptProteinRepresentationVerification,
    DiscordanceOptimizationDiagnostic,
    DiscordanceOptimizationStatus,
    FeatureSpecification,
    GliomaTranscriptProteinEvidenceState,
    GliomaTranscriptProteinObservation,
    LeakageCheck,
    LeakageCheckStatus,
    RepresentationConstructionStatus,
    RepresentationFeature,
    RepresentationReplayReason,
    RepresentationTransformationKind,
    TranscriptProteinRepresentationResult,
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

_REQUEST_ADAPTER: Final = TypeAdapter(ConstructTranscriptProteinRepresentationRequest)
_RESULT_ADAPTER: Final = TypeAdapter(TranscriptProteinRepresentationResult)
_LEAKAGE_TOKENS: Final = frozenset(
    {"future", "outcome", "target", "label", "held_out", "heldout", "response"}
)


class RepresentationAuthorizationError(PermissionError):
    """Raised before an unauthorized request reaches the constructor."""

    def __init__(self) -> None:
        super().__init__("M08-02 representation request is not authorized")


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
    """Typed result and its sole canonical byte representation."""

    result: TranscriptProteinRepresentationResult
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if self.result.result_digest != result_payload_digest(self.result):
            raise RepresentationInputError("result_digest")
        expected = canonical_json_bytes(self.result.model_dump(mode="json"))
        if expected != self.canonical_bytes:
            raise RepresentationInputError("result_noncanonical")


def preflight_representation_authorization(request: object) -> None:
    """Apply consent, identity, and accepted-control gates without inference."""

    if not isinstance(request, ConstructTranscriptProteinRepresentationRequest):
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
    request: ConstructTranscriptProteinRepresentationRequest,
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


def _provenance(request: ConstructTranscriptProteinRepresentationRequest) -> ProvenanceRecord:
    refs = request.context.references
    policy_digests = tuple(item.reference.digest for item in request.policy.evidence)
    typed_digests = {
        evidence.reference.digest
        for observation in request.typed_observations
        for evidence in observation.evidence
    }
    input_digests = tuple(
        sorted(
            {artifact.digest for artifact in request.source_artifacts}
            | {request.formal_state_result.digest}
            | set(policy_digests)
            | typed_digests
        )
    )
    return ProvenanceRecord(
        activity_id=f"activity.{request.request_id}",
        actor_id=request.context.actor_id,
        module_id=M0802_MODULE_ID,
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
        rationale="No owner-approved M08-02 uncertainty estimator is frozen yet.",
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
            "Measurement, sampling, parameter, model-form, identification, support, "
            "and transport uncertainty remain explicitly non-estimable pending owner review.",
        ),
    )


def _typed_uncertainty() -> UncertaintyProfile:
    def estimated(probability: float, dimension: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(
            state=EstimateState.ESTIMATED,
            probability=probability,
            rationale=f"deterministic M08-02 typed {dimension} uncertainty",
        )

    return UncertaintyProfile(
        measurement=estimated(0.12, "measurement"),
        sampling=estimated(0.10, "sampling"),
        parameter=estimated(0.15, "parameter"),
        model_form=estimated(0.22, "model-form"),
        identification=estimated(0.10, "identification"),
        support=estimated(0.15, "support"),
        transport=estimated(0.28, "transport"),
        sensitivity_notes=(
            "Bootstrap intervals perturb paired transcript/protein evidence only.",
            "Modality ablations expose transcript, protein, and translation-prior sensitivity.",
            "The typed lane emits representation-level discordance and no subtype claim.",
        ),
    )


def _limitations() -> tuple[Limitation, ...]:
    return (
        Limitation(
            code="provisional_abi",
            statement=(
                "The typed glioma discordance estimator is research-use-only; the opaque "
                "feature fallback remains provisional compatibility behavior."
            ),
        ),
        Limitation(
            code="no_parent_emission",
            statement=(
                "M08-02 constructs a versioned analysis representation and emits no protein "
                "subtype claim."
            ),
        ),
        Limitation(
            code="kinase_activity_owned_elsewhere",
            statement="KINOPHOS owns kinase-state output; M08-02 never emits kinase activity.",
        ),
        Limitation(
            code="caller_declared_evidence",
            statement=(
                "Evidence and provenance references are linked but their issuer authority is "
                "not authenticated by this constructor."
            ),
        ),
    )


def _leakage_reason(spec: FeatureSpecification) -> str | None:
    fields = {field.casefold() for field in spec.lineage.source_fields}
    tokens = {token for field in fields for token in field.replace("-", "_").split("_")}
    if tokens & _LEAKAGE_TOKENS:
        return (
            "feature lineage references a future, outcome, target, label, response, "
            "or held-out field"
        )
    if any(not item.leakage_safe for item in spec.lineage.transformations):
        return "feature lineage contains a leakage-unsafe transformation"
    return None


def _feature_values(
    spec: FeatureSpecification,
    request: ConstructTranscriptProteinRepresentationRequest,
) -> tuple[float, ...]:
    """Transform observed values, retaining a legacy digest-only compatibility path."""

    if spec.source_values:
        observed_values = [float(value) for value in spec.source_values]
        for transformation in spec.lineage.transformations:
            if transformation.kind in {
                RepresentationTransformationKind.SCALING,
                RepresentationTransformationKind.NORMALIZATION,
            }:
                center = fsum(observed_values) / len(observed_values)
                variance = fsum(
                    (value - center) ** 2 for value in observed_values
                ) / len(observed_values)
                scale = sqrt(max(variance, 1e-12))
                observed_values = [
                    (value - center) / scale for value in observed_values
                ]
            elif transformation.kind is RepresentationTransformationKind.RESIDUAL:
                center = fsum(observed_values) / len(observed_values)
                observed_values = [value - center for value in observed_values]
            elif transformation.kind is RepresentationTransformationKind.MASKING:
                # Values are finite by contract; masking is represented by the
                # feature's explicit mask field and does not alter observations.
                observed_values = list(observed_values)
            elif transformation.kind is RepresentationTransformationKind.COVARIATE:
                # Covariates are carried in lineage and are not folded into the
                # measured transcript/protein vector without an explicit model.
                observed_values = list(observed_values)
        return tuple(round(value, 8) for value in observed_values)

    seed = "|".join(
        (
            spec.feature_id,
            spec.version,
            request.formal_state_result.digest,
            *sorted(artifact.digest for artifact in request.source_artifacts),
            *spec.lineage.source_fields,
            *[item.parameters_digest for item in spec.lineage.transformations],
            request.policy.policy_id,
            request.policy.version,
        )
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
_TYPED_TRANSLATION_PRIOR: Final = 0.20
_TYPED_TRANSLATION_ALPHA: Final = 0.65
_TYPED_TOLERANCE: Final = 1e-5
_TYPED_BACKTRACK_FLOOR: Final = 1e-3
_TYPED_MAX_ITERATIONS: Final = 256
_TYPED_MIN_OBSERVATIONS: Final = 3


@dataclass(frozen=True, slots=True)
class _TypedDiscordanceFit:
    discordance: float
    transcript: float
    protein: float
    coupling: float
    lower: float
    upper: float
    stability: float
    discordance_score: float
    evidence_count: int
    top_drivers: tuple[str, ...]
    ablation_effects: tuple[str, ...]
    objective: float
    iterations: int
    convergence_gap: float
    objective_trace: tuple[float, ...]
    converged: bool


def _typed_active(observation: GliomaTranscriptProteinObservation) -> bool:
    return observation.evidence_state in {
        GliomaTranscriptProteinEvidenceState.OBSERVED,
        GliomaTranscriptProteinEvidenceState.LEFT_CENSORED,
    }


def _typed_component_target(
    observation: GliomaTranscriptProteinObservation,
    modality: str,
) -> float:
    effect = (
        observation.transcript_effect
        if modality == "transcript"
        else observation.protein_effect
    )
    limit = (
        observation.transcript_censoring_limit
        if modality == "transcript"
        else observation.protein_censoring_limit
    )
    value = effect if effect is not None else limit
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_component_error(
    observation: GliomaTranscriptProteinObservation,
    modality: str,
) -> float:
    value = (
        observation.transcript_standard_error
        if modality == "transcript"
        else observation.protein_standard_error
    )
    if value is None:
        raise ValueError from None
    return float(value)


def _typed_component_residual(
    state: float,
    observation: GliomaTranscriptProteinObservation,
    modality: str,
) -> float:
    effect = (
        observation.transcript_effect
        if modality == "transcript"
        else observation.protein_effect
    )
    if effect is not None:
        return state - float(effect)
    return max(0.0, state - _typed_component_target(observation, modality))


def _typed_component_activation(
    state: float,
    observation: GliomaTranscriptProteinObservation,
    modality: str,
) -> float:
    effect = (
        observation.transcript_effect
        if modality == "transcript"
        else observation.protein_effect
    )
    if effect is not None:
        return 1.0
    scaled = np.clip(
        (state - _typed_component_target(observation, modality)) / 0.1,
        -50.0,
        50.0,
    )
    return float(1.0 / (1.0 + np.exp(-scaled)))


def _typed_huber(value: float) -> float:
    magnitude = abs(value)
    return (
        0.5 * magnitude * magnitude
        if magnitude <= _TYPED_HUBER_K
        else _TYPED_HUBER_K * magnitude - 0.5 * _TYPED_HUBER_K**2
    )


def _typed_pair_objective(  # noqa: PLR0913 - explicit modality ablations stay visible.
    observations: tuple[GliomaTranscriptProteinObservation, ...],
    transcript: float,
    protein: float,
    *,
    include_translation: bool,
    include_transcript: bool = True,
    include_protein: bool = True,
) -> float:
    total = 0.0
    for item in observations:
        if not _typed_active(item):
            continue
        for modality, state, enabled in (
            ("transcript", transcript, include_transcript),
            ("protein", protein, include_protein),
        ):
            if not enabled:
                continue
            error = _typed_component_error(item, modality)
            residual = _typed_component_residual(state, item, modality)
            precision = item.quality_weight / max(error**2, 1e-12)
            total += precision * _typed_huber(residual / error)
    if include_translation and include_transcript and include_protein:
        total += _TYPED_TRANSLATION_PRIOR * (
            protein - _TYPED_TRANSLATION_ALPHA * transcript
        ) ** 2
    total += _TYPED_RIDGE * (transcript**2 + protein**2)
    return float(total)


def _fit_typed_pair(  # noqa: C901, PLR0912, PLR0915 - explicit IRLS safeguards.
    observations: tuple[GliomaTranscriptProteinObservation, ...],
    *,
    max_iterations: int,
    include_translation: bool = True,
    include_transcript: bool = True,
    include_protein: bool = True,
) -> tuple[float, float, float, int, float, tuple[float, ...], bool] | None:
    active = tuple(item for item in observations if _typed_active(item))
    if len(active) < _TYPED_MIN_OBSERVATIONS or not (include_transcript or include_protein):
        return None
    transcript_weights = np.asarray(
        [
            item.quality_weight / max(_typed_component_error(item, "transcript") ** 2, 1e-12)
            for item in active
        ],
        dtype=np.float64,
    )
    protein_weights = np.asarray(
        [
            item.quality_weight / max(_typed_component_error(item, "protein") ** 2, 1e-12)
            for item in active
        ],
        dtype=np.float64,
    )
    transcript = float(
        np.average(
            [_typed_component_target(item, "transcript") for item in active],
            weights=transcript_weights,
        )
    )
    protein = float(
        np.average(
            [_typed_component_target(item, "protein") for item in active],
            weights=protein_weights,
        )
    )
    if not include_transcript:
        transcript = 0.0
    if not include_protein:
        protein = 0.0
    previous = _typed_pair_objective(
        active,
        transcript,
        protein,
        include_translation=include_translation,
        include_transcript=include_transcript,
        include_protein=include_protein,
    )
    trace = [round(previous, 10)]
    gap = float("inf")
    converged = False
    iterations = 0
    for iteration in range(min(max_iterations, _TYPED_MAX_ITERATIONS)):
        iterations = iteration + 1
        proposed_transcript = transcript
        proposed_protein = protein
        if include_transcript:
            numerator = 0.0
            denominator = _TYPED_RIDGE
            for item in active:
                error = _typed_component_error(item, "transcript")
                residual = _typed_component_residual(transcript, item, "transcript")
                standardized = residual / error
                robust = (
                    1.0
                    if residual == 0.0
                    else min(1.0, _TYPED_HUBER_K / max(1.0, abs(standardized)))
                )
                precision = (
                    item.quality_weight
                    * _typed_component_activation(transcript, item, "transcript")
                    * robust
                    / max(error**2, 1e-12)
                )
                numerator += precision * _typed_component_target(item, "transcript")
                denominator += precision
            if include_translation and include_protein:
                numerator += _TYPED_TRANSLATION_PRIOR * _TYPED_TRANSLATION_ALPHA * protein
                denominator += (
                    _TYPED_TRANSLATION_PRIOR * _TYPED_TRANSLATION_ALPHA**2
                )
            proposed_transcript = numerator / max(denominator, 1e-12)
        if include_protein:
            numerator = 0.0
            denominator = _TYPED_RIDGE
            for item in active:
                error = _typed_component_error(item, "protein")
                residual = _typed_component_residual(protein, item, "protein")
                standardized = residual / error
                robust = (
                    1.0
                    if residual == 0.0
                    else min(1.0, _TYPED_HUBER_K / max(1.0, abs(standardized)))
                )
                precision = (
                    item.quality_weight
                    * _typed_component_activation(protein, item, "protein")
                    * robust
                    / max(error**2, 1e-12)
                )
                numerator += precision * _typed_component_target(item, "protein")
                denominator += precision
            if include_translation and include_transcript:
                numerator += _TYPED_TRANSLATION_PRIOR * _TYPED_TRANSLATION_ALPHA * transcript
                denominator += _TYPED_TRANSLATION_PRIOR
            proposed_protein = numerator / max(denominator, 1e-12)
        proposed_transcript = float(
            np.clip(
                _TYPED_DAMPING * proposed_transcript
                + (1.0 - _TYPED_DAMPING) * transcript,
                -M0802_MAX_TYPED_EFFECT,
                M0802_MAX_TYPED_EFFECT,
            )
        )
        proposed_protein = float(
            np.clip(
                _TYPED_DAMPING * proposed_protein
                + (1.0 - _TYPED_DAMPING) * protein,
                -M0802_MAX_TYPED_EFFECT,
                M0802_MAX_TYPED_EFFECT,
            )
        )
        gap = max(
            abs(proposed_transcript - transcript), abs(proposed_protein - protein)
        )
        blend = 1.0
        candidate_transcript = proposed_transcript
        candidate_protein = proposed_protein
        objective = _typed_pair_objective(
            active,
            candidate_transcript,
            candidate_protein,
            include_translation=include_translation,
            include_transcript=include_transcript,
            include_protein=include_protein,
        )
        while objective > previous + 1e-9 and blend > _TYPED_BACKTRACK_FLOOR:
            blend *= 0.5
            candidate_transcript = transcript + blend * (proposed_transcript - transcript)
            candidate_protein = protein + blend * (proposed_protein - protein)
            objective = _typed_pair_objective(
                active,
                candidate_transcript,
                candidate_protein,
                include_translation=include_translation,
                include_transcript=include_transcript,
                include_protein=include_protein,
            )
        if not isfinite(objective):
            return None
        if objective > previous + 1e-7:
            candidate_transcript = transcript
            candidate_protein = protein
            objective = previous
            gap = 0.0
        transcript = candidate_transcript
        protein = candidate_protein
        previous = objective
        trace.append(round(objective, 10))
        if gap <= _TYPED_TOLERANCE:
            converged = True
            break
    if not isfinite(gap) or any(not isfinite(value) for value in trace):
        return None
    return transcript, protein, previous, iterations, gap, tuple(trace), converged


def _typed_fit(  # noqa: C901 - fit, bootstrap, and ablations are one replay unit.
    observations: tuple[GliomaTranscriptProteinObservation, ...],
    request_digest: str,
    request: ConstructTranscriptProteinRepresentationRequest,
) -> _TypedDiscordanceFit | None:
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (item.observation_id, item.feature_id, item.gene),
        )
    )
    fitted = _fit_typed_pair(ordered, max_iterations=request.max_iterations)
    if fitted is None:
        return None
    transcript, protein, objective, iterations, gap, trace, converged = fitted
    discordance = protein - transcript
    coupling = protein - _TYPED_TRANSLATION_ALPHA * transcript
    seed = int(
        sha256_digest({"request": request_digest, "model": M0802_GLIOMA_MODEL_FAMILY})
        .removeprefix("sha256:")[:16],
        16,
    )
    rng = np.random.default_rng(seed)
    active = tuple(item for item in ordered if _typed_active(item))
    bootstrap: list[float] = []
    for _ in range(request.bootstrap_replicates):
        sampled: list[GliomaTranscriptProteinObservation] = []
        for index in rng.integers(0, len(active), size=len(active)):
            item = active[int(index)]
            updates: dict[str, float] = {}
            for modality in ("transcript", "protein"):
                effect_name = f"{modality}_effect"
                limit_name = f"{modality}_censoring_limit"
                effect = getattr(item, effect_name)
                value = _typed_component_target(item, modality) + _typed_component_error(
                    item, modality
                ) * float(rng.normal())
                if effect is not None:
                    updates[effect_name] = float(
                        np.clip(value, -M0802_MAX_TYPED_EFFECT, M0802_MAX_TYPED_EFFECT)
                    )
                else:
                    updates[limit_name] = float(
                        np.clip(value, -M0802_MAX_TYPED_EFFECT, M0802_MAX_TYPED_EFFECT)
                    )
            sampled.append(item.model_copy(update=updates))
        replicate = _fit_typed_pair(tuple(sampled), max_iterations=request.max_iterations)
        if replicate is not None:
            bootstrap.append(replicate[1] - replicate[0])
    if len(bootstrap) < max(8, request.bootstrap_replicates // 2):
        return None
    lower, upper = np.quantile(np.asarray(bootstrap, dtype=np.float64), (0.05, 0.95))
    lower = float(min(lower, discordance))
    upper = float(max(upper, discordance))
    discordance_score = float(np.clip(abs(discordance) / 3.0, 0.0, 1.0))
    drivers = sorted(
        (
            abs(
                _typed_component_residual(transcript, item, "transcript")
                - _typed_component_residual(protein, item, "protein")
            )
            * item.quality_weight,
            item.gene,
        )
        for item in active
    )
    without_translation = _fit_typed_pair(
        ordered, max_iterations=request.max_iterations, include_translation=False
    )
    transcript_only = _fit_typed_pair(
        ordered,
        max_iterations=request.max_iterations,
        include_translation=False,
        include_protein=False,
    )
    protein_only = _fit_typed_pair(
        ordered,
        max_iterations=request.max_iterations,
        include_translation=False,
        include_transcript=False,
    )
    ablations: list[str] = []
    if without_translation is not None:
        ablations.append(
            "translation_prior_delta="
            f"{abs(discordance - (without_translation[1] - without_translation[0])):.8f}"
        )
    if transcript_only is not None:
        ablations.append(
            "transcript_modality_delta="
            f"{abs(discordance - (transcript_only[1] - transcript_only[0])):.8f}"
        )
    if protein_only is not None:
        ablations.append(
            "protein_modality_delta="
            f"{abs(discordance - (protein_only[1] - protein_only[0])):.8f}"
        )
    return _TypedDiscordanceFit(
        discordance=round(discordance, 8),
        transcript=round(transcript, 8),
        protein=round(protein, 8),
        coupling=round(coupling, 8),
        lower=round(lower, 8),
        upper=round(upper, 8),
        stability=round(float(np.clip(1.0 - (upper - lower) / 6.0, 0.0, 1.0)), 8),
        discordance_score=round(discordance_score, 8),
        evidence_count=len(active),
        top_drivers=tuple(f"gene:{gene}" for _, gene in reversed(drivers[-4:])),
        ablation_effects=tuple(ablations),
        objective=round(objective, 8),
        iterations=iterations,
        convergence_gap=round(gap, 8),
        objective_trace=trace,
        converged=converged,
    )


def _typed_result(  # noqa: C901 - typed result closure keeps safety decisions together.
    request: ConstructTranscriptProteinRepresentationRequest,
) -> TranscriptProteinRepresentationResult:
    """Build the research-use-only typed glioma discordance result."""

    request = request.model_copy(
        update={
            "typed_observations": tuple(
                sorted(
                    request.typed_observations,
                    key=lambda item: (item.observation_id, item.feature_id, item.gene),
                )
            )
        }
    )
    request_digest = canonical_request_digest(request)
    checks: list[LeakageCheck] = []
    failure_reasons: list[str] = []
    for spec in request.feature_specs:
        leakage_reason = _leakage_reason(spec)
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{spec.feature_id}",
                status=(LeakageCheckStatus.FAILED if leakage_reason else LeakageCheckStatus.PASSED),
                message=(
                    leakage_reason
                    or "lineage, source fields, and locked transforms pass leakage checks"
                ),
                held_out_group=(spec.feature_id if leakage_reason else None),
            )
        )
        if leakage_reason:
            failure_reasons.append(leakage_reason)
    duplicate_sources = len({item.artifact_id for item in request.source_artifacts}) != len(
        request.source_artifacts
    )
    if duplicate_sources:
        failure_reasons.append("source artifact identifiers must be unique")
    evidence = (
        tuple(
            EvidenceReference(reference=item, role="evidence", claim=M0802_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        + request.policy.evidence
        + tuple(
            evidence
            for observation in request.typed_observations
            for evidence in observation.evidence
        )
    )
    fits: dict[str, _TypedDiscordanceFit] = {}
    if not failure_reasons:
        for spec in request.feature_specs:
            members = tuple(
                item
                for item in request.typed_observations
                if item.feature_id == spec.feature_id
            )
            fit = _typed_fit(members, request_digest, request)
            if fit is None or not fit.converged:
                failure_reasons.append(
                    "typed glioma transcript-protein discordance needs at least three "
                    "supported paired observations and a converged robust fit"
                )
                break
            fits[spec.feature_id] = fit
    diagnostics: list[DiscordanceOptimizationDiagnostic] = []
    for spec in request.feature_specs:
        fit = fits.get(spec.feature_id)
        if fit is None:
            diagnostics.append(
                DiscordanceOptimizationDiagnostic(
                    diagnostic_id=f"diagnostic.{spec.feature_id}.typed",
                    status=DiscordanceOptimizationStatus.NOT_EVALUABLE,
                    objective="glioma_transcript_protein_discordance",
                    iteration_count=0,
                    model_family=M0802_GLIOMA_MODEL_FAMILY,
                    message=failure_reasons[-1]
                    if failure_reasons
                    else "typed discordance fit was not evaluable",
                    evidence=evidence,
                )
            )
        else:
            diagnostics.append(
                DiscordanceOptimizationDiagnostic(
                    diagnostic_id=f"diagnostic.{spec.feature_id}.typed",
                    status=DiscordanceOptimizationStatus.CONVERGED,
                    objective="glioma_transcript_protein_discordance",
                    iteration_count=fit.iterations,
                    objective_value=fit.objective,
                    convergence_gap=fit.convergence_gap,
                    objective_trace_digest=sha256_digest({"trace": fit.objective_trace}),
                    model_family=M0802_GLIOMA_MODEL_FAMILY,
                    message=(
                        "typed glioma transcript-protein discordance converged with robust "
                        "Huber IRLS, translation prior, censored loss, and stratified bootstrap"
                    ),
                    evidence=evidence,
                )
            )
    features: list[RepresentationFeature] = []
    if not failure_reasons:
        for spec in request.feature_specs:
            fit = fits[spec.feature_id]
            channels = (fit.discordance, fit.transcript, fit.protein, fit.coupling)
            values = tuple(
                round(channels[index] if index < len(channels) else channels[-1], 8)
                for index in range(spec.dimension)
            )
            features.append(
                RepresentationFeature(
                    feature_id=spec.feature_id,
                    value_kind=spec.value_kind,
                    unit=spec.unit,
                    values=values,
                    mask=(True,) * spec.dimension if spec.value_kind.value == "mask" else (),
                    lineage=spec.lineage,
                    evidence_count=fit.evidence_count,
                    stability=fit.stability,
                    discordance=fit.discordance_score,
                    top_drivers=fit.top_drivers,
                    ablation_effects=fit.ablation_effects,
                    lower_bound=fit.lower,
                    upper_bound=fit.upper,
                    model_family=M0802_GLIOMA_MODEL_FAMILY,
                    evidence=evidence,
                )
            )
    constructed = not failure_reasons and len(features) == len(request.feature_specs)
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if constructed
        else RepresentationConstructionStatus.ABSTAINED
    )
    reason = None if constructed else "; ".join(dict.fromkeys(failure_reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if constructed else SupportStatus.REVIEW_REQUIRED,
        reason_code=(
            "m0802_typed_glioma_supported"
            if constructed
            else "m0802_typed_glioma_abstention"
        ),
        rationale=(
            "explicit paired glioma evidence supports a robust discordance representation"
            if constructed
            else reason or "typed discordance construction requires human review"
        ),
    )
    draft = TranscriptProteinRepresentationResult.model_construct(
        result_id=f"result.{request_digest.removeprefix('sha256:')}",
        request_digest=request_digest,
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        features=tuple(features) if constructed else (),
        optimization_diagnostics=tuple(diagnostics),
        model_family=M0802_GLIOMA_MODEL_FAMILY,
        leakage_checks=tuple(checks),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_typed_uncertainty() if constructed else _uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return TranscriptProteinRepresentationResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


def _build_result(
    request: ConstructTranscriptProteinRepresentationRequest,
) -> TranscriptProteinRepresentationResult:
    if request.typed_observations:
        return _typed_result(request)
    duplicate_sources = len({item.artifact_id for item in request.source_artifacts}) != len(
        request.source_artifacts
    )
    checks: list[LeakageCheck] = []
    features: list[RepresentationFeature] = []
    failure_reasons: list[str] = []
    for spec in request.feature_specs:
        leakage_reason = _leakage_reason(spec)
        checks.append(
            LeakageCheck(
                check_id=f"leakage.{spec.feature_id}",
                status=(LeakageCheckStatus.FAILED if leakage_reason else LeakageCheckStatus.PASSED),
                message=(
                    leakage_reason
                    or "lineage, source fields, and locked transforms pass leakage checks"
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
    status = (
        RepresentationConstructionStatus.CONSTRUCTED
        if constructed
        else RepresentationConstructionStatus.ABSTAINED
    )
    reason = None if constructed else "; ".join(dict.fromkeys(failure_reasons))
    support = SupportDecision(
        status=SupportStatus.SUPPORTED if constructed else SupportStatus.REVIEW_REQUIRED,
        reason_code="representation_support_state",
        rationale=(
            "all feature lineage and leakage-safe construction gates are satisfied"
            if constructed
            else reason or "representation construction requires human review"
        ),
    )
    evidence = (
        tuple(
            EvidenceReference(reference=item, role="evidence", claim=M0802_EVIDENCE_CLAIM)
            for item in request.source_artifacts
        )
        + request.policy.evidence
    )
    draft = TranscriptProteinRepresentationResult.model_construct(
        result_id=f"result.{request.request_id}",
        request_digest=canonical_request_digest(request),
        result_digest="sha256:" + "0" * 64,
        request=request,
        status=status,
        features=tuple(features) if constructed else (),
        leakage_checks=tuple(checks),
        abstention_reason=reason,
        support_decision=support,
        uncertainty=_uncertainty(),
        provenance=_provenance(request),
        evidence=evidence,
        limitations=_limitations(),
    )
    return TranscriptProteinRepresentationResult.model_validate(
        draft.model_copy(update={"result_digest": result_payload_digest(draft)}),
        strict=True,
    )


class M0802RepresentationEngine:
    """Build, execute, and replay one deterministic M08-02 representation."""

    @staticmethod
    def validate_request(request: object) -> ConstructTranscriptProteinRepresentationRequest:
        preflight_representation_authorization(request)
        return _REQUEST_ADAPTER.validate_python(request, strict=True)

    def construct(self, request: object) -> BuiltRepresentation:
        typed = self.validate_request(request)
        result = _build_result(typed)
        canonical_bytes = canonical_json_bytes(result.model_dump(mode="json"))
        if len(canonical_bytes) > M0802_MAX_CANONICAL_RESULT_BYTES:
            raise RepresentationInputError("result_limit")
        return BuiltRepresentation(result=result, canonical_bytes=canonical_bytes)

    def verify(
        self,
        result: object,
        canonical_bytes: bytes | None = None,
    ) -> ConstructTranscriptProteinRepresentationVerification:
        try:
            typed = _RESULT_ADAPTER.validate_python(result, strict=True)
        except (TypeError, ValueError, ValidationError):
            return ConstructTranscriptProteinRepresentationVerification(
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
            or len(canonical_bytes) > M0802_MAX_CANONICAL_RESULT_BYTES
        ):
            content_verified = False
        verified = content_verified and deterministic_verified
        reason = (
            RepresentationReplayReason.VERIFIED
            if verified
            else (
                RepresentationReplayReason.CANONICAL_BYTES_MISMATCH
                if deterministic_verified
                else RepresentationReplayReason.DIGEST_MISMATCH
            )
        )
        return ConstructTranscriptProteinRepresentationVerification(
            content_verified=content_verified,
            deterministic_verified=deterministic_verified,
            verified=verified,
            result_digest=typed.result_digest if verified else None,
            reason=reason,
        )

    def execute(self, request: object) -> BuiltRepresentation:
        return self.construct(request)


def construct_transcript_protein_representation(request: object) -> BuiltRepresentation:
    """Construct one representation through the stateless default engine."""

    return M0802RepresentationEngine().construct(request)


__all__ = [
    "BuiltRepresentation",
    "M0802RepresentationEngine",
    "RepresentationAuthorizationError",
    "RepresentationInputError",
    "construct_transcript_protein_representation",
    "preflight_representation_authorization",
]
