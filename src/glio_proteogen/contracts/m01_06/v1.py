"""Strict public contracts for deterministic M01-06 harmonization."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from glio_proteogen.contracts.m01_06.canonical import (
    configuration_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlRole,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    IdentityLineageState,
    Limitation,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0106_MODULE_ID: Final = "GLIO-PROTEOGEN-M01-06"
M0106_CONTRACT_VERSION: Final = "1.0.0"
M0106_MAX_STAGES: Final = 8
M0106_MAX_OBSERVATIONS: Final = 10_000
M0106_MAX_INVARIANTS: Final = 256
M0106_MAX_EVIDENCE_PER_ITEM: Final = 64
M0106_HARMONIZATION_LIMITATION_CODE: Final = "technical_harmonization_only"
M0106_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_MINIMUM_STAGE_LEVELS: Final = 2

ValueUnit = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9%][A-Za-z0-9%._/*^-]*$"),
]


class TechnicalFactor(StrEnum):
    PLATFORM = "platform"
    BATCH = "batch"
    LABORATORY = "laboratory"
    BUILD = "build"
    DEPTH = "depth"
    PURITY = "purity"
    COMPOSITION = "composition"
    PREANALYTIC = "preanalytic"


class ObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    BELOW_DETECTION_LIMIT = "below_detection_limit"
    NOT_APPLICABLE = "not_applicable"


class InvariantKind(StrEnum):
    DIRECTION = "direction"
    RANK = "rank"


class DiagnosticStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class ShiftState(StrEnum):
    ESTIMATED = "estimated"
    CAPPED = "capped"
    NOT_EVALUABLE = "not_evaluable"


class HarmonizationDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"


class FactorLevel(FrozenModel):
    factor: TechnicalFactor
    level_id: Identifier


class HarmonizationObservation(FrozenModel):
    sample_id: Identifier
    feature_id: Identifier
    group_id: Identifier
    state: ObservationState
    value: float | None = None
    unit: ValueUnit
    detection_limit: float | None = None
    factor_levels: tuple[FactorLevel, ...] = Field(min_length=1, max_length=M0106_MAX_STAGES)
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0106_MAX_EVIDENCE_PER_ITEM,
    )

    @model_validator(mode="after")
    def observation_is_closed(self) -> HarmonizationObservation:
        if len({level.factor for level in self.factor_levels}) != len(self.factor_levels):
            raise ValueError("observation factor levels must be unique by factor")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("observation evidence references must be unique")
        if self.state is ObservationState.OBSERVED and self.value is None:
            raise ValueError("observed harmonization input requires a value")
        if self.state is not ObservationState.OBSERVED and self.value is not None:
            raise ValueError("non-observed harmonization input cannot carry a value")
        if self.state is ObservationState.BELOW_DETECTION_LIMIT:
            if self.detection_limit is None:
                raise ValueError("censored harmonization input requires a detection limit")
        elif self.detection_limit is not None:
            raise ValueError("only censored harmonization input may carry a detection limit")
        return self


class HarmonizationStage(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0106_MAX_STAGES)
    factor: TechnicalFactor
    reference_level_id: Identifier
    control_sample_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1_000)
    control_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def controls_are_unique(self) -> HarmonizationStage:
        if len(self.control_sample_ids) != len(set(self.control_sample_ids)):
            raise ValueError("stage control sample identifiers must be unique")
        if len(self.control_feature_ids) != len(set(self.control_feature_ids)):
            raise ValueError("stage control feature identifiers must be unique")
        return self


class BiologicalInvariant(FrozenModel):
    invariant_id: Identifier
    kind: InvariantKind
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    group_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def members_are_unique(self) -> BiologicalInvariant:
        if len(self.feature_ids) != len(set(self.feature_ids)):
            raise ValueError("biological invariant feature identifiers must be unique")
        if len(self.group_ids) != len(set(self.group_ids)):
            raise ValueError("biological invariant group identifiers must be unique")
        expected_shape = {
            InvariantKind.DIRECTION: (1, 2),
            InvariantKind.RANK: (2, 1),
        }[self.kind]
        if (len(self.feature_ids), len(self.group_ids)) != expected_shape:
            raise ValueError("biological invariant members do not match its kind")
        return self


class HarmonizationProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    stages: tuple[HarmonizationStage, ...] = Field(min_length=1, max_length=M0106_MAX_STAGES)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def stages_are_ordered_and_unique(self) -> HarmonizationProfile:
        if tuple(stage.ordinal for stage in self.stages) != tuple(range(1, len(self.stages) + 1)):
            raise ValueError("harmonization stages must have contiguous ordered ordinals")
        if len({stage.stage_id for stage in self.stages}) != len(self.stages):
            raise ValueError("harmonization stage identifiers must be unique")
        if len({stage.factor for stage in self.stages}) != len(self.stages):
            raise ValueError("harmonization stages must be unique by factor")
        return self


class HarmonizationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_absolute_shift: float = Field(gt=0.0)
    min_controls_per_level: int = Field(default=2, ge=1, le=1_000)
    technical_effect_tolerance: float = Field(ge=0.0)
    biological_invariant_tolerance: float = Field(ge=0.0)
    max_observations: int = Field(default=M0106_MAX_OBSERVATIONS, gt=0, le=M0106_MAX_OBSERVATIONS)
    max_invariants: int = Field(default=M0106_MAX_INVARIANTS, ge=0, le=M0106_MAX_INVARIANTS)


class HarmonizeObservationsRequest(FrozenModel):
    operation: Literal["harmonize_observations"] = "harmonize_observations"
    contract_version: Literal["1.0.0"] = M0106_CONTRACT_VERSION
    context: ExecutionContext
    profile: HarmonizationProfile
    policy: HarmonizationPolicy
    observations: tuple[HarmonizationObservation, ...] = Field(
        min_length=1,
        max_length=M0106_MAX_OBSERVATIONS,
    )
    biological_invariants: tuple[BiologicalInvariant, ...] = Field(
        default=(),
        max_length=M0106_MAX_INVARIANTS,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_closed_and_configuration_bound(
        self,
    ) -> HarmonizeObservationsRequest:
        _require_authorized_context(self.context)
        if len(self.observations) > self.policy.max_observations or len(
            self.biological_invariants
        ) > self.policy.max_invariants:
            raise ValueError("harmonization request exceeds the active policy")
        keys = [(item.sample_id, item.feature_id) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("harmonization observations must be unique by sample and feature")
        invariant_ids = [item.invariant_id for item in self.biological_invariants]
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("biological invariant identifiers must be unique")
        _validate_request_closure(self)
        expected = configuration_digest(self.profile, self.policy, self.biological_invariants)
        if self.context.references.approved_configuration.evidence.digest != expected:
            raise ValueError("approved configuration does not bind the harmonization request")
        return self


def _validate_request_closure(request: HarmonizeObservationsRequest) -> None:
    observations = request.observations
    samples = {item.sample_id for item in observations}
    features = {item.feature_id for item in observations}
    factors = {stage.factor for stage in request.profile.stages}
    if any({level.factor for level in item.factor_levels} != factors for item in observations):
        raise ValueError("every observation must declare every configured technical factor")
    _validate_sample_levels(observations)
    for stage in request.profile.stages:
        _validate_stage_closure(stage, observations, samples, features)
    groups = {item.group_id for item in observations}
    if any(
        not set(item.feature_ids).issubset(features) or not set(item.group_ids).issubset(groups)
        for item in request.biological_invariants
    ):
        raise ValueError("biological invariant references unknown request members")
    if len({observation.unit for observation in observations}) != 1:
        raise ValueError("harmonization request requires one common unit")


def _validate_sample_levels(observations: tuple[HarmonizationObservation, ...]) -> None:
    levels_by_sample_factor: dict[tuple[Identifier, TechnicalFactor], set[Identifier]] = {}
    for observation in observations:
        for level in observation.factor_levels:
            levels_by_sample_factor.setdefault(
                (observation.sample_id, level.factor),
                set(),
            ).add(level.level_id)
    if any(len(levels) != 1 for levels in levels_by_sample_factor.values()):
        raise ValueError("technical factor levels must be consistent within each sample")


def _validate_stage_closure(
    stage: HarmonizationStage,
    observations: tuple[HarmonizationObservation, ...],
    samples: set[Identifier],
    features: set[Identifier],
) -> None:
    if not set(stage.control_sample_ids).issubset(samples):
        raise ValueError("harmonization stage references an unknown control sample")
    if not set(stage.control_feature_ids).issubset(features):
        raise ValueError("harmonization stage references an unknown control feature")
    declared_levels = {
        level.level_id
        for observation in observations
        for level in observation.factor_levels
        if level.factor is stage.factor
    }
    if len(declared_levels) < _MINIMUM_STAGE_LEVELS:
        raise ValueError("harmonization stage requires reference and non-reference levels")
    reference_is_declared = any(
        observation.sample_id in stage.control_sample_ids
        and any(
            level.factor is stage.factor and level.level_id == stage.reference_level_id
            for level in observation.factor_levels
        )
        for observation in observations
    )
    if not reference_is_declared:
        raise ValueError("stage reference level requires a declared control observation")


class HarmonizedValue(FrozenModel):
    sample_id: Identifier
    feature_id: Identifier
    group_id: Identifier
    state: ObservationState
    value: float | None = None
    unit: ValueUnit
    detection_limit: float | None = None
    source_observation_digest: Sha256Digest
    applied_stage_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0106_MAX_STAGES)

    @model_validator(mode="after")
    def value_preserves_state(self) -> HarmonizedValue:
        if self.state is ObservationState.OBSERVED and self.value is None:
            raise ValueError("observed harmonized value requires a value")
        if self.state is not ObservationState.OBSERVED and self.value is not None:
            raise ValueError("non-observed harmonized value cannot carry a value")
        if self.state is ObservationState.BELOW_DETECTION_LIMIT:
            if self.detection_limit is None:
                raise ValueError("censored harmonized value requires a detection limit")
        elif self.detection_limit is not None:
            raise ValueError("only censored harmonized value may carry a detection limit")
        if len(self.applied_stage_ids) != len(set(self.applied_stage_ids)):
            raise ValueError("applied harmonization stage identifiers must be unique")
        return self


class LevelShift(FrozenModel):
    level_id: Identifier
    state: ShiftState
    estimated_shift: float | None = None
    applied_shift: float | None = None
    unit: ValueUnit
    control_count: int = Field(ge=0)

    @model_validator(mode="after")
    def shift_matches_state(self) -> LevelShift:
        evaluable = self.estimated_shift is not None and self.applied_shift is not None
        if self.state is ShiftState.NOT_EVALUABLE and evaluable:
            raise ValueError("non-evaluable level shift cannot carry values")
        if self.state is not ShiftState.NOT_EVALUABLE and not evaluable:
            raise ValueError("evaluable level shift requires estimated and applied values")
        if (self.estimated_shift is None) != (self.applied_shift is None):
            raise ValueError("level shift estimates and applications must be paired")
        if (
            self.state is ShiftState.ESTIMATED
            and self.estimated_shift != self.applied_shift
        ):
            raise ValueError("uncapped level shift must apply its exact estimate")
        return self


class StageTransformation(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0106_MAX_STAGES)
    factor: TechnicalFactor
    method: Literal["control_median_additive_shift"] = "control_median_additive_shift"
    reference_level_id: Identifier
    maximum_absolute_shift: float = Field(gt=0.0)
    level_shifts: tuple[LevelShift, ...] = Field(min_length=1, max_length=10_000)
    input_digest: Sha256Digest
    output_digest: Sha256Digest

    @model_validator(mode="after")
    def levels_are_unique(self) -> StageTransformation:
        if len({item.level_id for item in self.level_shifts}) != len(self.level_shifts):
            raise ValueError("transformation level identifiers must be unique")
        references = [
            item for item in self.level_shifts if item.level_id == self.reference_level_id
        ]
        if len(references) != 1:
            raise ValueError("transformation requires exactly one reference-level shift")
        reference = references[0]
        valid_reference = (
            reference.state is ShiftState.ESTIMATED
            and reference.estimated_shift == 0.0
            and reference.applied_shift == 0.0
        ) or (
            reference.state is ShiftState.NOT_EVALUABLE
            and reference.estimated_shift is None
            and reference.applied_shift is None
        )
        if not valid_reference:
            raise ValueError("reference shift must be exact zero or not evaluable")
        for shift in self.level_shifts:
            _validate_shift_against_cap(shift, self.maximum_absolute_shift)
        return self


def _validate_shift_against_cap(shift: LevelShift, maximum: float) -> None:
    if shift.state is ShiftState.NOT_EVALUABLE:
        return
    estimated = shift.estimated_shift
    applied = shift.applied_shift
    if estimated is None or applied is None:  # pragma: no cover - LevelShift closes this shape.
        raise ValueError("evaluable level shift requires estimated and applied values")
    if shift.state is ShiftState.ESTIMATED:
        if abs(estimated) >= maximum or applied != estimated:
            raise ValueError("estimated shift must be exact and strictly within the cap")
        return
    expected = max(-maximum, min(maximum, estimated))
    if abs(estimated) < maximum or applied != expected:
        raise ValueError("capped shift must apply the declared cap exactly")


class TransformationManifest(FrozenModel):
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    stages: tuple[StageTransformation, ...] = Field(min_length=1, max_length=M0106_MAX_STAGES)

    @model_validator(mode="after")
    def stages_are_ordered(self) -> TransformationManifest:
        if tuple(stage.ordinal for stage in self.stages) != tuple(range(1, len(self.stages) + 1)):
            raise ValueError("transformation stages must have contiguous ordered ordinals")
        if len({stage.stage_id for stage in self.stages}) != len(self.stages):
            raise ValueError("transformation stage identifiers must be unique")
        if len({stage.factor for stage in self.stages}) != len(self.stages):
            raise ValueError("transformation stages must be unique by factor")
        if len({stage.maximum_absolute_shift for stage in self.stages}) != 1:
            raise ValueError("transformation stages must share one maximum absolute shift")
        return self


class TechnicalEffectDiagnostic(FrozenModel):
    stage_id: Identifier
    factor: TechnicalFactor
    before_spread: float | None = Field(default=None, ge=0.0)
    after_spread: float | None = Field(default=None, ge=0.0)
    tolerance: float = Field(ge=0.0)
    capped: bool = False
    status: DiagnosticStatus

    @model_validator(mode="after")
    def scores_match_status(self) -> TechnicalEffectDiagnostic:
        if self.before_spread is None or self.after_spread is None:
            expected = DiagnosticStatus.NOT_EVALUABLE
        elif (
            not self.capped
            and self.after_spread <= self.before_spread
            and self.after_spread <= self.tolerance
        ):
            expected = DiagnosticStatus.PASSED
        else:
            expected = DiagnosticStatus.FAILED
        if self.status is not expected:
            raise ValueError("technical diagnostic scores contradict its status")
        return self


class BiologicalInvariantDiagnostic(FrozenModel):
    invariant_id: Identifier
    kind: InvariantKind
    before_score: float | None = None
    after_score: float | None = None
    tolerance: float = Field(ge=0.0)
    status: DiagnosticStatus

    @model_validator(mode="after")
    def scores_match_status(self) -> BiologicalInvariantDiagnostic:
        if self.before_score is None or self.after_score is None:
            expected = DiagnosticStatus.NOT_EVALUABLE
        elif (
            _score_sign(self.before_score) == _score_sign(self.after_score)
            and _score_sign(self.before_score) != 0
            and abs(self.after_score - self.before_score) <= self.tolerance
        ):
            expected = DiagnosticStatus.PASSED
        else:
            expected = DiagnosticStatus.FAILED
        if self.status is not expected:
            raise ValueError("biological diagnostic scores contradict its status")
        return self


class HarmonizationResult(FrozenModel):
    output_type: Literal["harmonization_result"] = "harmonization_result"
    harmonization_id: Identifier
    result_version: Literal["1.0.0"] = M0106_CONTRACT_VERSION
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: HarmonizationDisposition
    values: tuple[HarmonizedValue, ...] = Field(min_length=1, max_length=M0106_MAX_OBSERVATIONS)
    transformation_manifest: TransformationManifest
    technical_effect_diagnostics: tuple[TechnicalEffectDiagnostic, ...] = Field(
        min_length=1,
        max_length=M0106_MAX_STAGES,
    )
    biological_invariant_diagnostics: tuple[BiologicalInvariantDiagnostic, ...] = Field(
        default=(),
        max_length=M0106_MAX_INVARIANTS,
    )
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def envelope_is_coherent_and_digest_bound(self) -> HarmonizationResult:
        _validate_result_collections(self)
        _validate_result_envelope(self)
        expected = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected)
        elif self.result_digest != expected:
            raise ValueError("harmonization result digest does not match its content")
        return self


def _validate_result_collections(result: HarmonizationResult) -> None:
    value_keys = [(item.sample_id, item.feature_id) for item in result.values]
    if len(value_keys) != len(set(value_keys)):
        raise ValueError("harmonized values must be unique by sample and feature")
    stages = result.transformation_manifest.stages
    units = {item.unit for item in result.values} | {
        shift.unit for stage in stages for shift in stage.level_shifts
    }
    if len(units) != 1:
        raise ValueError("harmonized values and level shifts require one common unit")
    stage_ids = tuple(item.stage_id for item in stages)
    if any(
        tuple(item for item in stage_ids if item in value.applied_stage_ids)
        != value.applied_stage_ids
        for value in result.values
    ):
        raise ValueError("applied stage identifiers must follow the transformation manifest")
    if [(item.stage_id, item.factor) for item in stages] != [
        (item.stage_id, item.factor) for item in result.technical_effect_diagnostics
    ]:
        raise ValueError("technical diagnostics must align with transformation stages")
    if any(
        diagnostic.capped
        != any(shift.state is ShiftState.CAPPED for shift in stage.level_shifts)
        for stage, diagnostic in zip(
            stages,
            result.technical_effect_diagnostics,
            strict=True,
        )
    ):
        raise ValueError("technical diagnostics must report capped transformations")
    invariant_ids = [item.invariant_id for item in result.biological_invariant_diagnostics]
    if len(invariant_ids) != len(set(invariant_ids)):
        raise ValueError("biological diagnostic identifiers must be unique")
    diagnostic_statuses = (
        *(item.status for item in result.technical_effect_diagnostics),
        *(item.status for item in result.biological_invariant_diagnostics),
    )
    problematic = any(status is not DiagnosticStatus.PASSED for status in diagnostic_statuses)
    expected = (
        HarmonizationDisposition.QUARANTINED
        if problematic
        else HarmonizationDisposition.ACCEPTED
    )
    if result.disposition is not expected:
        raise ValueError("harmonization disposition contradicts its diagnostics")


def _validate_result_envelope(result: HarmonizationResult) -> None:
    manifest = result.transformation_manifest
    if (
        manifest.profile_digest != result.profile_digest
        or manifest.policy_digest != result.policy_digest
        or manifest.configuration_digest != result.configuration_digest
    ):
        raise ValueError("transformation manifest contradicts the result configuration")
    expected_support = {
        HarmonizationDisposition.ACCEPTED: (SupportStatus.LIMITED, "harmonization_accepted"),
        HarmonizationDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "harmonization_quarantined",
        ),
    }[result.disposition]
    if (result.support.status, result.support.reason_code) != expected_support:
        raise ValueError("harmonization support contradicts its disposition")
    if result.human_review_required is (result.disposition is HarmonizationDisposition.ACCEPTED):
        raise ValueError("harmonization review flag contradicts its disposition")
    suffix = result.request_digest.removeprefix("sha256:")
    provenance = result.provenance
    if result.harmonization_id != f"harmonization.m0106.{suffix}":
        raise ValueError("harmonization identifier does not bind its request digest")
    if provenance.activity_id != f"activity.m0106.{suffix}":
        raise ValueError("harmonization activity does not bind its request digest")
    if (
        provenance.module_id != M0106_MODULE_ID
        or provenance.module_version != result.result_version
    ):
        raise ValueError("harmonization provenance belongs to the wrong module version")
    if provenance.generated_at != result.completed_at:
        raise ValueError("harmonization provenance timestamp contradicts the result")
    if provenance.configuration_digest != result.configuration_digest:
        raise ValueError("harmonization provenance contradicts its configuration")
    required = {
        result.request_digest,
        result.profile_digest,
        result.policy_digest,
        result.configuration_digest,
    }
    if not required.issubset(provenance.input_digests):
        raise ValueError("harmonization provenance input digests are incomplete")
    if len(result.evidence) != len(set(result.evidence)):
        raise ValueError("harmonization evidence references must be unique")
    if {item.code for item in result.limitations} != {
        M0106_HARMONIZATION_LIMITATION_CODE,
        M0106_AUTHORITY_LIMITATION_CODE,
    }:
        raise ValueError("harmonization result requires both module limitations")
    _validate_authorized_provenance(provenance, result.configuration_digest)


def _validate_authorized_provenance(
    provenance: ProvenanceRecord,
    configuration_hash: Sha256Digest,
) -> None:
    states = {item.role: item.state for item in provenance.control_decisions}
    expected_states = {
        ControlRole.APPROVED_CONFIGURATION: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.IDENTITY_LINEAGE: IdentityLineageState.RESOLVED.value,
        ControlRole.PROVENANCE: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.CONSENT: ConsentState.GRANTED.value,
        ControlRole.QUALITY: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.SUPPORT: UpstreamDecisionState.ACCEPTED.value,
        ControlRole.INTENDED_USE: UpstreamDecisionState.ACCEPTED.value,
    }
    if states != expected_states or provenance.consent_state is not ConsentState.GRANTED:
        raise ValueError("harmonization provenance requires accepted authorization states")
    approved_configuration = next(
        item
        for item in provenance.control_decisions
        if item.role is ControlRole.APPROVED_CONFIGURATION
    )
    if approved_configuration.evidence_digest != configuration_hash:
        raise ValueError("approved configuration provenance must bind the result configuration")
    consent = next(
        item for item in provenance.control_decisions if item.role is ControlRole.CONSENT
    )
    if (
        consent.decision_id != provenance.consent_decision_id
        or consent.policy_version != provenance.consent_policy_version
        or consent.evidence_digest != provenance.consent_evidence_digest
    ):
        raise ValueError("harmonization consent provenance is internally inconsistent")


def _score_sign(value: float | None) -> int:
    if value is None or value == 0:
        return 0
    return 1 if value > 0 else -1


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize harmonization")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before harmonization")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(reference.state is not UpstreamDecisionState.ACCEPTED for reference in generic):
        raise ValueError("every upstream control must accept harmonization")


__all__ = [
    "M0106_CONTRACT_VERSION",
    "M0106_MODULE_ID",
    "BiologicalInvariant",
    "BiologicalInvariantDiagnostic",
    "DiagnosticStatus",
    "FactorLevel",
    "HarmonizationDisposition",
    "HarmonizationObservation",
    "HarmonizationPolicy",
    "HarmonizationProfile",
    "HarmonizationResult",
    "HarmonizationStage",
    "HarmonizeObservationsRequest",
    "HarmonizedValue",
    "InvariantKind",
    "LevelShift",
    "ObservationState",
    "ShiftState",
    "StageTransformation",
    "TechnicalEffectDiagnostic",
    "TechnicalFactor",
    "TransformationManifest",
]
