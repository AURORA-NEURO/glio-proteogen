"""Pure contract-facing deterministic harmonization engine for M01-06."""

from __future__ import annotations

import statistics
from collections.abc import Mapping
from itertools import chain
from typing import TYPE_CHECKING, Any, Final, cast

from pydantic import TypeAdapter

from glio_proteogen.contracts.m01_06 import (
    BiologicalInvariant,
    BiologicalInvariantDiagnostic,
    DiagnosticStatus,
    HarmonizationDisposition,
    HarmonizationObservation,
    HarmonizationResult,
    HarmonizationStage,
    HarmonizedValue,
    HarmonizeObservationsRequest,
    InvariantKind,
    LevelShift,
    ObservationState,
    ShiftState,
    StageTransformation,
    TechnicalEffectDiagnostic,
    TransformationManifest,
    canonical_request_digest,
    configuration_digest,
    observation_digest,
    policy_digest,
    profile_digest,
)
from glio_proteogen.contracts.m01_06.v1 import M0106_CONTRACT_VERSION, M0106_MODULE_ID
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ControlDecisionRecord,
    ControlRole,
    EstimateState,
    EvidenceReference,
    ExecutionContext,
    Limitation,
    ProvenanceRecord,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.kernel import (
    NormalizationResult,
    NormalizationStage,
    ScalarValue,
    StageResult,
    ValueState,
    normalize,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization.kernel import (
    ShiftState as KernelShiftState,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

_REQUEST_ADAPTER: Final[TypeAdapter[HarmonizeObservationsRequest]] = TypeAdapter(
    HarmonizeObservationsRequest
)
_AUTHORIZATION_ERROR: Final = "harmonization requires accepted upstream authorization states"
_LIMITATIONS: Final = (
    Limitation(
        code="technical_harmonization_only",
        statement=(
            "This result applies configured technical shifts only; it does not infer proteotype, "
            "kinase state, clinical meaning, or treatment."
        ),
    ),
    Limitation(
        code="external_controls_unverified",
        statement=(
            "Upstream controls, observations, and profile evidence are caller-declared "
            "references whose issuers M01-06 does not authenticate."
        ),
    ),
)


class HarmonizationAuthorizationError(ValueError):
    """Raw M01-06 request authorization failed before observation parsing."""

    def __init__(self) -> None:
        super().__init__(_AUTHORIZATION_ERROR)


class M0106HarmonizationEngine:
    """Normalize one authorized immutable request without I/O or learned inference."""

    __slots__ = ()

    def harmonize(self, request: HarmonizeObservationsRequest) -> HarmonizationResult:
        validated = _REQUEST_ADAPTER.validate_python(request, strict=True)
        preflight_harmonization_authorization(validated)
        request_hash = canonical_request_digest(validated)
        profile_hash = profile_digest(validated.profile)
        policy_hash = policy_digest(validated.policy)
        configuration_hash = configuration_digest(
            validated.profile,
            validated.policy,
            validated.biological_invariants,
        )
        kernel = normalize(
            _kernel_values(validated.observations),
            _kernel_stages(validated),
        )
        values = _values(validated.observations, kernel, validated.profile.stages)
        manifest = _manifest(validated, kernel, profile_hash, policy_hash, configuration_hash)
        technical = _technical_diagnostics(validated, kernel)
        biological = _biological_diagnostics(validated, values)
        disposition = (
            HarmonizationDisposition.ACCEPTED
            if all(item.status is DiagnosticStatus.PASSED for item in technical)
            and all(item.status is DiagnosticStatus.PASSED for item in biological)
            else HarmonizationDisposition.QUARANTINED
        )
        return HarmonizationResult(
            harmonization_id=f"harmonization.m0106.{request_hash.removeprefix('sha256:')}",
            request_digest=request_hash,
            profile_digest=profile_hash,
            policy_digest=policy_hash,
            configuration_digest=configuration_hash,
            disposition=disposition,
            values=values,
            transformation_manifest=manifest,
            technical_effect_diagnostics=technical,
            biological_invariant_diagnostics=biological,
            support=_support(disposition),
            uncertainty=_uncertainty(),
            provenance=_provenance(
                validated,
                request_hash,
                profile_hash,
                policy_hash,
                configuration_hash,
            ),
            evidence=_evidence(validated),
            limitations=_LIMITATIONS,
            human_review_required=disposition is HarmonizationDisposition.QUARANTINED,
            completed_at=validated.context.occurred_at,
            supersedes_result_digest=validated.supersedes_result_digest,
        )


def harmonize_observations(request: HarmonizeObservationsRequest) -> HarmonizationResult:
    """Convenience entry point for stateless callers and agent tools."""

    return M0106HarmonizationEngine().harmonize(request)


def preflight_harmonization_authorization(candidate: object) -> None:
    """Reject raw unauthorized payloads before observations are typed or hashed."""

    if isinstance(candidate, HarmonizeObservationsRequest):
        context: object = candidate.context
    elif isinstance(candidate, Mapping):
        context = candidate.get("context")
    else:
        raise HarmonizationAuthorizationError
    references = _mapping_value(context, "references")
    expected = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    if any(
        _mapping_value(_mapping_value(references, key), "state") != value
        for key, value in expected.items()
    ):
        raise HarmonizationAuthorizationError


def _mapping_value(candidate: object, key: str) -> object:
    if isinstance(candidate, Mapping):
        return candidate.get(key)
    return getattr(candidate, key, None)


def _kernel_values(observations: tuple[HarmonizationObservation, ...]) -> tuple[ScalarValue, ...]:
    return tuple(
        ScalarValue(
            target_id=item.sample_id,
            feature_id=item.feature_id,
            state=ValueState(item.state.value),
            value=item.value,
        )
        for item in observations
    )


def _kernel_stages(request: HarmonizeObservationsRequest) -> tuple[NormalizationStage, ...]:
    levels = {
        stage.factor: {
            observation.sample_id: next(
                item.level_id
                for item in observation.factor_levels
                if item.factor is stage.factor
            )
            for observation in request.observations
        }
        for stage in request.profile.stages
    }
    return tuple(
        NormalizationStage(
            stage_id=stage.stage_id,
            factor_id=stage.factor.value,
            reference_level_id=stage.reference_level_id,
            control_feature_ids=stage.control_feature_ids,
            levels_by_target=dict(levels[stage.factor]),
            maximum_absolute_shift=request.policy.max_absolute_shift,
            minimum_control_observations=request.policy.min_controls_per_level,
            control_target_ids=stage.control_sample_ids,
        )
        for stage in request.profile.stages
    )


def _values(
    observations: tuple[HarmonizationObservation, ...],
    kernel: NormalizationResult,
    stages: tuple[Any, ...],
) -> tuple[HarmonizedValue, ...]:
    output = {(item.target_id, item.feature_id): item for item in kernel.values}
    stage_levels = {
        configured.stage_id: (
            configured.factor,
            {
                item.level: item.applied_shift
                for item in manifest.level_shifts
                if item.applied_shift is not None
            },
        )
        for configured, manifest in zip(stages, kernel.stages, strict=True)
    }
    return tuple(
        HarmonizedValue(
            sample_id=item.sample_id,
            feature_id=item.feature_id,
            group_id=item.group_id,
            state=item.state,
            value=output[(item.sample_id, item.feature_id)].value,
            unit=item.unit,
            detection_limit=item.detection_limit,
            source_observation_digest=observation_digest(item),
            applied_stage_ids=(
                _applied_stage_ids(item, stages, stage_levels)
                if item.state is ObservationState.OBSERVED
                else ()
            ),
        )
        for item in sorted(observations, key=lambda value: (value.sample_id, value.feature_id))
    )


def _applied_stage_ids(
    observation: HarmonizationObservation,
    stages: tuple[Any, ...],
    stage_levels: dict[str, tuple[Any, dict[str, float]]],
) -> tuple[str, ...]:
    factor_levels = {item.factor: item.level_id for item in observation.factor_levels}
    return tuple(
        stage.stage_id
        for stage in stages
        if factor_levels[stage_levels[stage.stage_id][0]] in stage_levels[stage.stage_id][1]
    )


def _manifest(
    request: HarmonizeObservationsRequest,
    kernel: NormalizationResult,
    profile_hash: str,
    active_policy_hash: str,
    configuration_hash: str,
) -> TransformationManifest:
    unit = request.observations[0].unit
    working = _kernel_values(request.observations)
    transformations: list[StageTransformation] = []
    for configured, stage, kernel_stage in zip(
        request.profile.stages,
        _kernel_stages(request),
        kernel.stages,
        strict=True,
    ):
        input_hash = sha256_digest(_kernel_value_payload(working))
        stage_result = normalize(working, (stage,))
        working = stage_result.values
        transformations.append(
            StageTransformation(
                stage_id=configured.stage_id,
                ordinal=configured.ordinal,
                factor=configured.factor,
                reference_level_id=configured.reference_level_id,
                maximum_absolute_shift=request.policy.max_absolute_shift,
                level_shifts=tuple(
                    LevelShift(
                        level_id=item.level,
                        state=ShiftState(item.state.value),
                        estimated_shift=item.estimated_shift,
                        applied_shift=item.applied_shift,
                        unit=unit,
                        control_count=item.control_observation_count,
                    )
                    for item in kernel_stage.level_shifts
                ),
                input_digest=input_hash,
                output_digest=sha256_digest(_kernel_value_payload(working)),
            )
        )
    return TransformationManifest(
        profile_digest=profile_hash,
        policy_digest=active_policy_hash,
        configuration_digest=configuration_hash,
        stages=tuple(transformations),
    )


def _ordered_kernel_values(values: tuple[ScalarValue, ...]) -> tuple[ScalarValue, ...]:
    return tuple(sorted(values, key=lambda item: (item.target_id, item.feature_id)))


def _kernel_value_payload(values: tuple[ScalarValue, ...]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "target_id": item.target_id,
            "feature_id": item.feature_id,
            "state": item.state.value,
            "value": item.value,
        }
        for item in _ordered_kernel_values(values)
    )


def _technical_diagnostics(
    request: HarmonizeObservationsRequest,
    kernel: NormalizationResult,
) -> tuple[TechnicalEffectDiagnostic, ...]:
    return tuple(
        _technical_diagnostic(configured, stage, request.policy.technical_effect_tolerance)
        for configured, stage in zip(request.profile.stages, kernel.stages, strict=True)
    )


def _technical_diagnostic(
    configured: HarmonizationStage,
    stage: StageResult,
    tolerance: float,
) -> TechnicalEffectDiagnostic:
    incomplete = any(
        item.state is KernelShiftState.NOT_EVALUABLE for item in stage.level_shifts
    )
    before = None if incomplete else stage.pre_level_spread
    after = None if incomplete else stage.post_level_spread
    capped = any(item.state is KernelShiftState.CAPPED for item in stage.level_shifts)
    return TechnicalEffectDiagnostic(
        stage_id=configured.stage_id,
        factor=configured.factor,
        before_spread=before,
        after_spread=after,
        tolerance=tolerance,
        capped=capped,
        status=_technical_status(before, after, tolerance, capped=capped),
    )


def _technical_status(
    before: float | None,
    after: float | None,
    tolerance: float,
    *,
    capped: bool,
) -> DiagnosticStatus:
    if before is None or after is None:
        return DiagnosticStatus.NOT_EVALUABLE
    return (
        DiagnosticStatus.PASSED
        if not capped and after <= before and after <= tolerance
        else DiagnosticStatus.FAILED
    )


def _biological_diagnostics(
    request: HarmonizeObservationsRequest,
    values: tuple[HarmonizedValue, ...],
) -> tuple[BiologicalInvariantDiagnostic, ...]:
    return tuple(
        _invariant_diagnostic(
            invariant,
            request.observations,
            values,
            request.policy.biological_invariant_tolerance,
        )
        for invariant in sorted(request.biological_invariants, key=lambda item: item.invariant_id)
    )


def _invariant_diagnostic(
    invariant: BiologicalInvariant,
    before: tuple[HarmonizationObservation, ...],
    after: tuple[HarmonizedValue, ...],
    tolerance: float,
) -> BiologicalInvariantDiagnostic:
    before_score = _invariant_score(invariant, before)
    after_score = _invariant_score(invariant, after)
    if before_score is None or after_score is None:
        status = DiagnosticStatus.NOT_EVALUABLE
    else:
        preserved = _sign(before_score) == _sign(after_score) and _sign(before_score) != 0
        status = (
            DiagnosticStatus.PASSED
            if preserved and abs(after_score - before_score) <= tolerance
            else DiagnosticStatus.FAILED
        )
    return BiologicalInvariantDiagnostic(
        invariant_id=invariant.invariant_id,
        kind=invariant.kind,
        before_score=before_score,
        after_score=after_score,
        tolerance=tolerance,
        status=status,
    )


def _invariant_score(
    invariant: BiologicalInvariant,
    values: tuple[HarmonizationObservation, ...] | tuple[HarmonizedValue, ...],
) -> float | None:
    if invariant.kind is InvariantKind.DIRECTION:
        feature = invariant.feature_ids[0]
        first = _member_median(values, feature, invariant.group_ids[0])
        second = _member_median(values, feature, invariant.group_ids[1])
    else:
        group = invariant.group_ids[0]
        first = _member_median(values, invariant.feature_ids[0], group)
        second = _member_median(values, invariant.feature_ids[1], group)
    return None if first is None or second is None else second - first


def _member_median(
    values: tuple[HarmonizationObservation, ...] | tuple[HarmonizedValue, ...],
    feature_id: str,
    group_id: str,
) -> float | None:
    members = [
        item
        for item in values
        if item.feature_id == feature_id and item.group_id == group_id
    ]
    if not members or any(item.state is not ObservationState.OBSERVED for item in members):
        return None
    observed = [item.value for item in members]
    return statistics.median(cast("list[float]", observed))


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _support(disposition: HarmonizationDisposition) -> SupportDecision:
    if disposition is HarmonizationDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="harmonization_quarantined",
            rationale="A technical or protected biological diagnostic requires review.",
        )
    return SupportDecision(
        status=SupportStatus.LIMITED,
        reason_code="harmonization_accepted",
        rationale="Configured deterministic technical corrections met bounded invariants.",
    )


def _not_estimable(rationale: str) -> UncertaintyEstimate:
    return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)


def _uncertainty() -> UncertaintyProfile:
    return UncertaintyProfile(
        measurement=_not_estimable("No measurement-error distribution was supplied."),
        sampling=_not_estimable("No sampling distribution was supplied."),
        parameter=_not_estimable("Control-median shifts have no calibrated parameter uncertainty."),
        model_form=_not_estimable("No learned model is used."),
        identification=_not_estimable("Residual attribution error is not scored."),
        support=_not_estimable("Support is a deterministic policy state."),
        transport=_not_estimable("Transport beyond declared factors is not estimated."),
        sensitivity_notes=(
            "Shifts are relative to declared reference-level control medians and capped.",
            "Missing and censored inputs remain missing or censored and are never imputed as zero.",
        ),
    )


def _control_records(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    references = context.references
    values = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration, None),
        (
            ControlRole.IDENTITY_LINEAGE,
            references.identity_lineage,
            references.identity_lineage.binding_digest,
        ),
        (ControlRole.PROVENANCE, references.provenance, None),
        (ControlRole.CONSENT, references.consent, None),
        (ControlRole.QUALITY, references.quality, None),
        (ControlRole.SUPPORT, references.support, None),
        (ControlRole.INTENDED_USE, references.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject_digest,
        )
        for role, reference, subject_digest in values
    )


def _provenance(
    request: HarmonizeObservationsRequest,
    request_hash: str,
    profile_hash: str,
    active_policy_hash: str,
    configuration_hash: str,
) -> ProvenanceRecord:
    references = request.context.references
    controls = _control_records(request.context)
    return ProvenanceRecord(
        activity_id=f"activity.m0106.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0106_MODULE_ID,
        module_version=M0106_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(
            dict.fromkeys(
                (
                    request_hash,
                    profile_hash,
                    active_policy_hash,
                    configuration_hash,
                    *(item.evidence_digest for item in controls),
                )
            )
        ),
        configuration_digest=configuration_hash,
        consent_decision_id=references.consent.decision_id,
        consent_state=references.consent.state,
        consent_policy_version=references.consent.policy_version,
        consent_evidence_digest=references.consent.evidence.digest,
        control_decisions=controls,
    )


def _evidence(request: HarmonizeObservationsRequest) -> tuple[EvidenceReference, ...]:
    references = request.context.references
    controls = (
        (ControlRole.APPROVED_CONFIGURATION, references.approved_configuration.evidence),
        (ControlRole.IDENTITY_LINEAGE, references.identity_lineage.evidence),
        (ControlRole.PROVENANCE, references.provenance.evidence),
        (ControlRole.CONSENT, references.consent.evidence),
        (ControlRole.QUALITY, references.quality.evidence),
        (ControlRole.SUPPORT, references.support.evidence),
        (ControlRole.INTENDED_USE, references.intended_use.evidence),
    )
    control_evidence = tuple(
        EvidenceReference(
            reference=reference,
            role="evidence",
            claim=f"Caller-declared {role.value.replace('_', '-')} control reference.",
        )
        for role, reference in controls
    )
    artifacts = _bounded_references(
        chain(
            (request.profile.evidence,),
            (item for observation in request.observations for item in observation.evidence),
        ),
        limit=505,
    )
    observation_evidence = tuple(
        EvidenceReference(
            reference=item,
            role="evidence",
            claim="Caller-declared harmonization evidence; source payload is not retained.",
        )
        for item in artifacts
    )
    return (*control_evidence, *observation_evidence)


def _bounded_references(
    references: Iterable[ArtifactReference],
    *,
    limit: int,
) -> tuple[ArtifactReference, ...]:
    return tuple(sorted(set(references), key=canonical_json_bytes)[:limit])


__all__ = [
    "HarmonizationAuthorizationError",
    "M0106HarmonizationEngine",
    "harmonize_observations",
    "preflight_harmonization_authorization",
]
