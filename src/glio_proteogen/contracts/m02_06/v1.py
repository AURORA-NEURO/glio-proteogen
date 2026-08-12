"""Strict M02-06 contracts for identification-specific harmonization.

M02-06 owns the C02 identification-QC normalization decision and its replayable
transformation manifest.  It deliberately does not own raw parsing, artifact
detection, biological interpretation, subtype inference, or treatment logic.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m02_01 import ConformanceEvaluation  # noqa: TC001
from glio_proteogen.contracts.m02_02 import IdentityBindingEvaluation  # noqa: TC001
from glio_proteogen.contracts.m02_03 import (  # noqa: TC001
    IdentificationRawIngestionResult,
)
from glio_proteogen.contracts.m02_04 import IdentificationQualityProfile  # noqa: TC001
from glio_proteogen.contracts.m02_05 import (  # noqa: TC001
    IdentificationArtifactDetectionResult,
)
from glio_proteogen.contracts.m02_06.canonical import (
    configuration_digest,
    invariant_digest,
    observation_summary_digest,
    policy_digest,
    profile_digest,
    request_manifest_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    EstimateState,
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

M0206_MODULE_ID: Final = "GLIO-PROTEOGEN-M02-06"
M0206_CONTRACT_VERSION: Final = "1.0.0"
M0206_MAX_STAGES: Final = 8
M0206_MAX_OBSERVATIONS: Final = 2_048
M0206_MAX_INVARIANTS: Final = 256
M0206_MAX_EVIDENCE_PER_OBSERVATION: Final = 64
M0206_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0206_MAX_ABSOLUTE_LOG2_ABUNDANCE: Final = 1_024.0
M0206_HARMONIZATION_LIMITATION_CODE: Final = "identification_harmonization_only"
M0206_AUTHORITY_LIMITATION_CODE: Final = "external_controls_unverified"
M0206_HARMONIZATION_LIMITATION_STATEMENT: Final = (
    "This result applies identification-specific additive harmonization only; it does "
    "not infer subtype, proteotype, biology, kinase activity, or treatment response."
)
M0206_AUTHORITY_LIMITATION_STATEMENT: Final = (
    "Upstream controls, prerequisite results, and the harmonization profile are "
    "caller-declared artifacts whose issuers M02-06 does not authenticate."
)
M0206_PROFILE_EVIDENCE_CLAIM: Final = (
    "Caller-declared identification harmonization profile; issuer is not authenticated."
)
M0206_SENSITIVITY_NOTES: Final = (
    "Shifts are bounded by the reviewed policy cap.",
    "Missing, censored, unsupported, and excluded values are never imputed.",
)
M0206_UNCERTAINTY_RATIONALES: Final[dict[str, str]] = {
    "measurement": "Input measurement error is not calibrated by M02-06.",
    "sampling": "The request supplies no sampling distribution.",
    "parameter": "Control-median shifts have no probabilistic parameter model.",
    "model_form": "The fixed additive stage model has no calibrated uncertainty.",
    "identification": "Residual identification attribution error is not scored.",
    "support": "Support is a deterministic diagnostic policy state.",
    "transport": "Transport beyond the pinned profile is not evaluated.",
}
_DERIVED_DIGEST_SENTINEL: Final = "sha256:" + ("0" * 64)
_MINIMUM_STAGE_LEVELS: Final = 2
_PREREQUISITE_COUNT: Final = 5
_RESULT_EVIDENCE_COUNT: Final = 8

ValueUnit = Literal["log2_abundance"]


class IdentificationTechnicalFactor(StrEnum):
    PLATFORM = "platform"
    BATCH = "batch"
    LABORATORY = "laboratory"
    BUILD = "build"
    DEPTH = "depth"
    PURITY = "purity"
    COMPOSITION = "composition"
    PREANALYTIC = "preanalytic"


class HarmonizationValueState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    CENSORED = "censored"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    EXCLUDED = "excluded"


class BiologicalInvariantKind(StrEnum):
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
    ABSTAINED = "abstained"


IdentificationHarmonizationDisposition = HarmonizationDisposition


class IdentificationFactorLevel(FrozenModel):
    factor: IdentificationTechnicalFactor
    level_id: Identifier


class IdentificationAbundanceObservation(FrozenModel):
    target_id: Identifier
    feature_id: Identifier
    biological_group_id: Identifier
    state: HarmonizationValueState
    value: float | None = None
    censoring_limit: float | None = None
    unit: ValueUnit
    factor_levels: tuple[IdentificationFactorLevel, ...] = Field(
        min_length=M0206_MAX_STAGES,
        max_length=M0206_MAX_STAGES,
    )
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0206_MAX_EVIDENCE_PER_OBSERVATION,
    )

    @model_validator(mode="after")
    def observation_is_typed_and_closed(self) -> IdentificationAbundanceObservation:
        factors = [item.factor for item in self.factor_levels]
        if len(set(factors)) != len(factors) or set(factors) != set(IdentificationTechnicalFactor):
            raise ValueError("observation must declare every technical factor exactly once")
        if len({item.digest for item in self.evidence}) != len(self.evidence):
            raise ValueError("observation evidence digests must be unique")
        if self.state is HarmonizationValueState.EXCLUDED:
            raise ValueError("input exclusion is derived only from the M02-05 result")
        if self.state is HarmonizationValueState.OBSERVED:
            if self.value is None:
                raise ValueError("observed identification abundance requires a value")
            if abs(self.value) > M0206_MAX_ABSOLUTE_LOG2_ABUNDANCE:
                raise ValueError("observed log2 abundance exceeds the supported numeric envelope")
            if self.censoring_limit is not None:
                raise ValueError("observed identification abundance cannot carry a censoring limit")
        elif self.state is HarmonizationValueState.CENSORED:
            if self.value is not None or self.censoring_limit is None:
                raise ValueError("censored identification abundance requires only its limit")
            if abs(self.censoring_limit) > M0206_MAX_ABSOLUTE_LOG2_ABUNDANCE:
                raise ValueError(
                    "censored log2 abundance limit exceeds the supported numeric envelope"
                )
        elif self.value is not None or self.censoring_limit is not None:
            raise ValueError("non-observed identification abundance cannot carry a number")
        return self


class IdentificationNormalizationStage(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0206_MAX_STAGES)
    factor: IdentificationTechnicalFactor
    reference_level_id: Identifier
    control_target_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1_000)
    control_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def controls_are_unique(self) -> IdentificationNormalizationStage:
        if len(set(self.control_target_ids)) != len(self.control_target_ids):
            raise ValueError("stage control target identifiers must be unique")
        if len(set(self.control_feature_ids)) != len(self.control_feature_ids):
            raise ValueError("stage control feature identifiers must be unique")
        return self


class IdentificationHarmonizationProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    stages: tuple[IdentificationNormalizationStage, ...] = Field(
        min_length=M0206_MAX_STAGES,
        max_length=M0206_MAX_STAGES,
    )
    evidence: ArtifactReference

    @model_validator(mode="after")
    def stages_are_the_exact_ordered_factor_set(self) -> IdentificationHarmonizationProfile:
        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0206_MAX_STAGES + 1)):
            raise ValueError("identification harmonization stages must have ordered ordinals")
        if len({item.stage_id for item in self.stages}) != len(self.stages):
            raise ValueError("identification harmonization stage identifiers must be unique")
        if {item.factor for item in self.stages} != set(IdentificationTechnicalFactor):
            raise ValueError("profile must configure all eight technical factors exactly once")
        return self


class IdentificationHarmonizationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_absolute_shift: float = Field(gt=0.0)
    min_controls_per_level: int = Field(default=2, ge=1, le=1_000)
    technical_effect_tolerance: float = Field(ge=0.0)
    biological_invariant_tolerance: float = Field(ge=0.0)
    max_observations: int = Field(
        default=M0206_MAX_OBSERVATIONS,
        gt=0,
        le=M0206_MAX_OBSERVATIONS,
    )
    max_invariants: int = Field(
        default=M0206_MAX_INVARIANTS,
        ge=0,
        le=M0206_MAX_INVARIANTS,
    )


class BiologicalControlInvariant(FrozenModel):
    invariant_id: Identifier
    kind: BiologicalInvariantKind
    feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=2)
    biological_group_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def members_match_the_ordered_invariant_kind(self) -> BiologicalControlInvariant:
        if len(set(self.feature_ids)) != len(self.feature_ids):
            raise ValueError("biological control features must be unique")
        if len(set(self.biological_group_ids)) != len(self.biological_group_ids):
            raise ValueError("biological control groups must be unique")
        expected = {
            BiologicalInvariantKind.DIRECTION: (1, 2),
            BiologicalInvariantKind.RANK: (2, 1),
        }[self.kind]
        if (len(self.feature_ids), len(self.biological_group_ids)) != expected:
            raise ValueError("biological control members do not match its kind")
        return self


class IdentificationHarmonizationPrerequisites(FrozenModel):
    conformance: ConformanceEvaluation
    identity: IdentityBindingEvaluation
    ingestion: IdentificationRawIngestionResult
    quality: IdentificationQualityProfile
    artifact_detection: IdentificationArtifactDetectionResult


class HarmonizeIdentificationEvidenceRequest(FrozenModel):
    operation: Literal["harmonize_identification_evidence"] = "harmonize_identification_evidence"
    contract_version: Literal["1.0.0"] = M0206_CONTRACT_VERSION
    context: ExecutionContext
    prerequisites: IdentificationHarmonizationPrerequisites
    profile: IdentificationHarmonizationProfile
    policy: IdentificationHarmonizationPolicy
    observations: tuple[IdentificationAbundanceObservation, ...] = Field(
        min_length=1,
        max_length=M0206_MAX_OBSERVATIONS,
    )
    biological_controls: tuple[BiologicalControlInvariant, ...] = Field(
        default=(),
        max_length=M0206_MAX_INVARIANTS,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_bound_and_closed(self) -> HarmonizeIdentificationEvidenceRequest:
        _require_authorized_context(self.context)
        if (
            len(self.observations) > self.policy.max_observations
            or len(self.biological_controls) > self.policy.max_invariants
        ):
            raise ValueError("identification harmonization request exceeds its policy")
        keys = [(item.target_id, item.feature_id) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("observations must be unique by target and feature")
        invariant_ids = [item.invariant_id for item in self.biological_controls]
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("biological control identifiers must be unique")
        if len({item.unit for item in self.observations}) != 1:
            raise ValueError("identification harmonization requires one common additive unit")
        _validate_observation_and_stage_closure(self)
        expected_configuration = configuration_digest(
            self.profile,
            self.policy,
            self.biological_controls,
        )
        if self.context.references.approved_configuration.evidence.digest != expected_configuration:
            raise ValueError("approved configuration does not bind M02-06")
        if len(canonical_json_bytes(self)) > M0206_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("M02-06 canonical request exceeds the public ingress byte limit")
        result_evidence_digests = {
            self.profile.evidence.digest,
            self.context.references.approved_configuration.evidence.digest,
            self.context.references.identity_lineage.evidence.digest,
            self.context.references.provenance.evidence.digest,
            self.context.references.consent.evidence.digest,
            self.context.references.quality.evidence.digest,
            self.context.references.support.evidence.digest,
            self.context.references.intended_use.evidence.digest,
        }
        if len(result_evidence_digests) != _RESULT_EVIDENCE_COUNT:
            raise ValueError("M02-06 profile and control evidence digests must be distinct")
        if (
            self.context.references.identity_lineage.binding_digest
            != self.prerequisites.identity.result_digest
        ):
            raise ValueError("identity control does not bind the M02-02 result")
        return self


def _validate_observation_and_stage_closure(
    request: HarmonizeIdentificationEvidenceRequest,
) -> None:
    observations = request.observations
    targets = {item.target_id for item in observations}
    features = {item.feature_id for item in observations}
    excluded = set(request.prerequisites.artifact_detection.exclusion_mask.excluded_target_ids)
    review = set(request.prerequisites.artifact_detection.exclusion_mask.review_target_ids)
    if not (excluded | review).issubset(
        request.prerequisites.artifact_detection.evaluated_target_ids
    ):
        raise ValueError("M02-05 mask references an unevaluated target")
    if not targets.issubset(request.prerequisites.artifact_detection.evaluated_target_ids):
        raise ValueError("every harmonization target must be evaluated by M02-05")
    levels_by_target_factor: dict[
        tuple[Identifier, IdentificationTechnicalFactor], set[Identifier]
    ] = {}
    for item in observations:
        for level in item.factor_levels:
            levels_by_target_factor.setdefault(
                (item.target_id, level.factor),
                set(),
            ).add(level.level_id)
    if any(len(values) != 1 for values in levels_by_target_factor.values()):
        raise ValueError("technical levels must be consistent within each target")
    for stage in request.profile.stages:
        if not set(stage.control_target_ids).issubset(targets):
            raise ValueError("stage references an unknown control target")
        if not set(stage.control_feature_ids).issubset(features):
            raise ValueError("stage references an unknown control feature")
        declared_levels = {
            level.level_id
            for item in observations
            for level in item.factor_levels
            if level.factor is stage.factor
        }
        if (
            stage.reference_level_id not in declared_levels
            or len(declared_levels) < _MINIMUM_STAGE_LEVELS
        ):
            raise ValueError("stage requires a declared reference and comparison level")
    groups = {item.biological_group_id for item in observations}
    if any(
        not set(item.feature_ids).issubset(features)
        or not set(item.biological_group_ids).issubset(groups)
        for item in request.biological_controls
    ):
        raise ValueError("biological control references an unknown observation member")


class UpstreamHarmonizationReceipt(FrozenModel):
    module_id: Literal[
        "GLIO-PROTEOGEN-M02-01",
        "GLIO-PROTEOGEN-M02-02",
        "GLIO-PROTEOGEN-M02-03",
        "GLIO-PROTEOGEN-M02-04",
        "GLIO-PROTEOGEN-M02-05",
    ]
    result_digest: Sha256Digest
    disposition: Identifier
    evaluated_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=10_000)
    excluded_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=10_000)
    review_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=10_000)

    @model_validator(mode="after")
    def mask_is_unique_and_only_owned_by_m0205(self) -> UpstreamHarmonizationReceipt:
        allowed_dispositions = {
            "GLIO-PROTEOGEN-M02-01": {"conformant", "quarantined"},
            "GLIO-PROTEOGEN-M02-02": {"conformant", "quarantined", "abstained"},
            "GLIO-PROTEOGEN-M02-03": {"accepted", "quarantined", "rejected"},
            "GLIO-PROTEOGEN-M02-04": {"accepted", "quarantined"},
            "GLIO-PROTEOGEN-M02-05": {"accepted", "quarantined"},
        }
        if self.disposition not in allowed_dispositions[self.module_id]:
            raise ValueError("upstream receipt disposition contradicts its module")
        if len(set(self.excluded_target_ids)) != len(self.excluded_target_ids) or len(
            set(self.review_target_ids)
        ) != len(self.review_target_ids):
            raise ValueError("upstream receipt target identifiers must be unique")
        if len(set(self.evaluated_target_ids)) != len(self.evaluated_target_ids):
            raise ValueError("upstream evaluated target identifiers must be unique")
        if set(self.excluded_target_ids) & set(self.review_target_ids):
            raise ValueError("upstream excluded and review targets must be disjoint")
        if self.module_id != "GLIO-PROTEOGEN-M02-05" and (
            self.evaluated_target_ids or self.excluded_target_ids or self.review_target_ids
        ):
            raise ValueError("only M02-05 may issue an exclusion mask")
        if self.module_id == "GLIO-PROTEOGEN-M02-05" and not (
            set(self.excluded_target_ids) | set(self.review_target_ids)
        ).issubset(self.evaluated_target_ids):
            raise ValueError("M02-05 receipt mask targets must have been evaluated")
        if self.module_id == "GLIO-PROTEOGEN-M02-05" and (
            (self.disposition == "accepted")
            != (not self.excluded_target_ids and not self.review_target_ids)
        ):
            raise ValueError("M02-05 receipt disposition contradicts its exclusion mask")
        return self


class SourceObservationSummary(FrozenModel):
    target_id: Identifier
    feature_id: Identifier
    biological_group_id: Identifier
    state: HarmonizationValueState
    value: float | None = None
    censoring_limit: float | None = None
    unit: ValueUnit
    factor_levels: tuple[IdentificationFactorLevel, ...] = Field(
        min_length=M0206_MAX_STAGES,
        max_length=M0206_MAX_STAGES,
    )
    evidence_digests: tuple[Sha256Digest, ...] = Field(
        min_length=1,
        max_length=M0206_MAX_EVIDENCE_PER_OBSERVATION,
    )

    @model_validator(mode="after")
    def summary_matches_an_input_observation(self) -> SourceObservationSummary:
        if self.state is HarmonizationValueState.EXCLUDED:
            raise ValueError("source observations cannot claim a derived exclusion")
        if len({item.factor for item in self.factor_levels}) != M0206_MAX_STAGES:
            raise ValueError("source summary must carry all factor levels")
        if len(set(self.evidence_digests)) != len(self.evidence_digests):
            raise ValueError("source evidence digests must be unique")
        if self.state is HarmonizationValueState.OBSERVED:
            if self.value is None or self.censoring_limit is not None:
                raise ValueError("observed source summary has invalid numeric state")
            if abs(self.value) > M0206_MAX_ABSOLUTE_LOG2_ABUNDANCE:
                raise ValueError("source log2 abundance exceeds the supported numeric envelope")
        elif self.state is HarmonizationValueState.CENSORED:
            if self.value is not None or self.censoring_limit is None:
                raise ValueError("censored source summary has invalid numeric state")
            if abs(self.censoring_limit) > M0206_MAX_ABSOLUTE_LOG2_ABUNDANCE:
                raise ValueError("source censoring limit exceeds the supported numeric envelope")
        elif self.value is not None or self.censoring_limit is not None:
            raise ValueError("absent source summary cannot carry a number")
        return self


class AppliedStageAdjustment(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0206_MAX_STAGES)
    factor: IdentificationTechnicalFactor
    level_id: Identifier
    shift: float
    unit: ValueUnit


class HarmonizedIdentificationValue(FrozenModel):
    sample_id: Identifier
    feature_id: Identifier
    biological_group_id: Identifier
    input_state: HarmonizationValueState
    output_state: HarmonizationValueState
    input_value: float | None = None
    harmonized_value: float | None = None
    input_censoring_limit: float | None = None
    censoring_limit: float | None = None
    unit: ValueUnit
    source_observation_digest: Sha256Digest
    source_observation: SourceObservationSummary
    applied_adjustments: tuple[AppliedStageAdjustment, ...] = Field(
        default=(),
        max_length=M0206_MAX_STAGES,
    )

    @model_validator(mode="after")
    def value_is_derived_from_its_exact_source(  # noqa: PLR0912
        self,
    ) -> HarmonizedIdentificationValue:
        source = self.source_observation
        if (
            self.sample_id,
            self.feature_id,
            self.biological_group_id,
            self.input_state,
            self.input_value,
            self.input_censoring_limit,
            self.unit,
        ) != (
            source.target_id,
            source.feature_id,
            source.biological_group_id,
            source.state,
            source.value,
            source.censoring_limit,
            source.unit,
        ):
            raise ValueError("harmonized value contradicts its source summary")
        expected_source_digest = observation_summary_digest(
            target_id=source.target_id,
            feature_id=source.feature_id,
            biological_group_id=source.biological_group_id,
            state=source.state.value,
            value=source.value,
            censoring_limit=source.censoring_limit,
            unit=source.unit,
            factor_levels=tuple(
                (item.factor.value, item.level_id) for item in source.factor_levels
            ),
            evidence_digests=source.evidence_digests,
        )
        if self.source_observation_digest != expected_source_digest:
            raise ValueError("source observation digest contradicts its summary")
        ordinals = tuple(item.ordinal for item in self.applied_adjustments)
        if ordinals != tuple(sorted(ordinals)) or len(set(ordinals)) != len(ordinals):
            raise ValueError("applied adjustments must be unique and stage ordered")
        if any(item.unit != self.unit for item in self.applied_adjustments):
            raise ValueError("applied adjustment unit must match the observation")
        if self.output_state is HarmonizationValueState.EXCLUDED:
            if self.harmonized_value is not None or self.applied_adjustments:
                raise ValueError("excluded output cannot carry a repaired value")
            if self.censoring_limit is not None:
                raise ValueError("excluded output cannot carry a censoring limit")
            return self
        if self.output_state is not self.input_state:
            raise ValueError("harmonization cannot relabel a non-excluded state")
        if self.input_state is HarmonizationValueState.OBSERVED:
            if self.harmonized_value is None or self.input_value is None:
                raise ValueError("observed harmonized output requires both values")
            expected = self.input_value + sum(item.shift for item in self.applied_adjustments)
            if not math.isclose(self.harmonized_value, expected, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("harmonized value contradicts its applied adjustments")
            if self.censoring_limit is not None:
                raise ValueError("observed output cannot carry a censoring limit")
        else:
            if self.harmonized_value is not None or self.applied_adjustments:
                raise ValueError("non-observed output cannot be imputed or adjusted")
            if self.censoring_limit != self.input_censoring_limit:
                raise ValueError("harmonization must preserve the censoring limit")
        return self


class IdentificationLevelShift(FrozenModel):
    level_id: Identifier
    state: ShiftState
    estimated_shift: float | None = None
    applied_shift: float | None = None
    unit: ValueUnit
    control_count: int = Field(ge=0)

    @model_validator(mode="after")
    def shift_values_match_state(self) -> IdentificationLevelShift:
        paired = self.estimated_shift is not None and self.applied_shift is not None
        if self.state is ShiftState.NOT_EVALUABLE:
            if self.estimated_shift is not None or self.applied_shift is not None:
                raise ValueError("not-evaluable shift cannot carry numeric values")
        elif not paired:
            raise ValueError("evaluable shift requires estimate and applied value")
        elif self.state is ShiftState.ESTIMATED and (self.estimated_shift != self.applied_shift):
            raise ValueError("uncapped shift must apply its exact estimate")
        return self


class IdentificationStageTransformation(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0206_MAX_STAGES)
    factor: IdentificationTechnicalFactor
    method: Literal["control_median_additive_shift"] = "control_median_additive_shift"
    reference_level_id: Identifier
    control_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=1_000)
    control_feature_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=1_000)
    maximum_absolute_shift: float = Field(gt=0.0)
    level_shifts: tuple[IdentificationLevelShift, ...] = Field(
        min_length=2,
        max_length=10_000,
    )
    input_digest: Sha256Digest
    output_digest: Sha256Digest

    @model_validator(mode="after")
    def transformation_is_closed(self) -> IdentificationStageTransformation:
        if len(set(self.control_target_ids)) != len(self.control_target_ids):
            raise ValueError("eligible transformation controls must be unique")
        if len(set(self.control_feature_ids)) != len(self.control_feature_ids):
            raise ValueError("transformation control features must be unique")
        if len({item.level_id for item in self.level_shifts}) != len(self.level_shifts):
            raise ValueError("transformation levels must be unique")
        reference = [item for item in self.level_shifts if item.level_id == self.reference_level_id]
        if len(reference) != 1:
            raise ValueError("transformation requires exactly one reference-level shift")
        reference_shift = reference[0]
        valid_reference = (
            reference_shift.state is ShiftState.ESTIMATED
            and reference_shift.estimated_shift == 0.0
            and reference_shift.applied_shift == 0.0
        ) or (
            reference_shift.state is ShiftState.NOT_EVALUABLE
            and reference_shift.estimated_shift is None
            and reference_shift.applied_shift is None
        )
        if not valid_reference:
            raise ValueError("reference-level shift must be exact zero or not evaluable")
        for shift in self.level_shifts:
            _validate_shift_cap(shift, self.maximum_absolute_shift)
        return self


def _validate_shift_cap(shift: IdentificationLevelShift, maximum: float) -> None:
    if shift.state is ShiftState.NOT_EVALUABLE:
        return
    estimated = shift.estimated_shift
    applied = shift.applied_shift
    if estimated is None or applied is None:
        raise ValueError("evaluable shift is incomplete")
    if shift.state is ShiftState.ESTIMATED:
        if abs(estimated) >= maximum or applied != estimated:
            raise ValueError("estimated shift must be exact and strictly within the cap")
    else:
        expected = max(-maximum, min(maximum, estimated))
        if abs(estimated) < maximum or applied != expected:
            raise ValueError("capped shift must apply the declared bound exactly")


class IdentificationTransformationManifest(FrozenModel):
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    stages: tuple[IdentificationStageTransformation, ...] = Field(
        min_length=M0206_MAX_STAGES,
        max_length=M0206_MAX_STAGES,
    )

    @model_validator(mode="after")
    def stages_are_exactly_ordered(self) -> IdentificationTransformationManifest:
        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0206_MAX_STAGES + 1)):
            raise ValueError("transformation manifest stages must remain ordered")
        if len({item.stage_id for item in self.stages}) != len(self.stages):
            raise ValueError("transformation manifest stage identifiers must be unique")
        if {item.factor for item in self.stages} != set(IdentificationTechnicalFactor):
            raise ValueError("manifest must cover all eight technical factors")
        return self


class TechnicalEffectDiagnostic(FrozenModel):
    stage_id: Identifier
    factor: IdentificationTechnicalFactor
    before_spread: float | None = Field(default=None, ge=0.0)
    after_spread: float | None = Field(default=None, ge=0.0)
    tolerance: float = Field(ge=0.0)
    capped: bool = False
    status: DiagnosticStatus

    @model_validator(mode="after")
    def scores_derive_status(self) -> TechnicalEffectDiagnostic:
        if self.before_spread is None or self.after_spread is None:
            expected = DiagnosticStatus.NOT_EVALUABLE
        elif (
            not self.capped
            and self.after_spread < self.before_spread
            and self.after_spread <= self.tolerance
        ):
            expected = DiagnosticStatus.PASSED
        else:
            expected = DiagnosticStatus.FAILED
        if self.status is not expected:
            raise ValueError("technical effect scores contradict their status")
        return self


class BiologicalInvariantDiagnostic(FrozenModel):
    invariant_id: Identifier
    kind: BiologicalInvariantKind
    before_score: float | None = None
    after_score: float | None = None
    tolerance: float = Field(ge=0.0)
    status: DiagnosticStatus

    @model_validator(mode="after")
    def scores_derive_status(self) -> BiologicalInvariantDiagnostic:
        if self.before_score is None or self.after_score is None:
            expected = DiagnosticStatus.NOT_EVALUABLE
        elif (
            _sign(self.before_score) == _sign(self.after_score)
            and _sign(self.before_score) != 0
            and abs(self.after_score - self.before_score) <= self.tolerance
        ):
            expected = DiagnosticStatus.PASSED
        else:
            expected = DiagnosticStatus.FAILED
        if self.status is not expected:
            raise ValueError("biological invariant scores contradict their status")
        return self


class IdentificationHarmonizationResult(FrozenModel):
    output_type: Literal["identification_harmonization_result"] = (
        "identification_harmonization_result"
    )
    harmonization_id: Identifier
    result_version: Literal["1.0.0"] = M0206_CONTRACT_VERSION
    request_digest: Sha256Digest
    context_digest: Sha256Digest
    prerequisites_digest: Sha256Digest
    upstream_receipts: tuple[UpstreamHarmonizationReceipt, ...] = Field(
        min_length=5,
        max_length=5,
    )
    profile: IdentificationHarmonizationProfile
    profile_digest: Sha256Digest
    policy: IdentificationHarmonizationPolicy
    policy_digest: Sha256Digest
    biological_controls: tuple[BiologicalControlInvariant, ...] = Field(
        default=(),
        max_length=M0206_MAX_INVARIANTS,
    )
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest = _DERIVED_DIGEST_SENTINEL
    disposition: HarmonizationDisposition
    values: tuple[HarmonizedIdentificationValue, ...] = Field(
        min_length=1,
        max_length=M0206_MAX_OBSERVATIONS,
    )
    transformation_manifest: IdentificationTransformationManifest
    technical_effect_diagnostics: tuple[TechnicalEffectDiagnostic, ...] = Field(
        min_length=M0206_MAX_STAGES,
        max_length=M0206_MAX_STAGES,
    )
    biological_invariant_diagnostics: tuple[BiologicalInvariantDiagnostic, ...] = Field(
        default=(),
        max_length=M0206_MAX_INVARIANTS,
    )
    parent_target: Literal["protein_subtype"] = "protein_subtype"
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=8, max_length=512)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> IdentificationHarmonizationResult:
        _validate_result_manifests(self)
        _validate_result_values(self)
        _validate_result_diagnostics_and_disposition(self)
        _validate_result_envelope(self)
        expected = result_payload_digest(self)
        if self.result_digest == _DERIVED_DIGEST_SENTINEL:
            object.__setattr__(self, "result_digest", expected)
        elif self.result_digest != expected:
            raise ValueError("M02-06 result digest does not match its content")
        return self


def _validate_result_manifests(result: IdentificationHarmonizationResult) -> None:
    if (
        len(result.values) > result.policy.max_observations
        or len(result.biological_controls) > result.policy.max_invariants
    ):
        raise ValueError("harmonization result exceeds its embedded policy capacity")
    if result.profile_digest != profile_digest(result.profile):
        raise ValueError("result profile digest is inconsistent")
    if result.policy_digest != policy_digest(result.policy):
        raise ValueError("result policy digest is inconsistent")
    expected_config = configuration_digest(
        result.profile,
        result.policy,
        result.biological_controls,
    )
    if result.configuration_digest != expected_config:
        raise ValueError("result configuration digest is inconsistent")
    manifest = result.transformation_manifest
    if (
        manifest.profile_digest,
        manifest.policy_digest,
        manifest.configuration_digest,
    ) != (result.profile_digest, result.policy_digest, result.configuration_digest):
        raise ValueError("transformation manifest uses a different configuration")
    modules = [item.module_id for item in result.upstream_receipts]
    expected_modules = {
        "GLIO-PROTEOGEN-M02-01",
        "GLIO-PROTEOGEN-M02-02",
        "GLIO-PROTEOGEN-M02-03",
        "GLIO-PROTEOGEN-M02-04",
        "GLIO-PROTEOGEN-M02-05",
    }
    if len(set(modules)) != _PREREQUISITE_COUNT or set(modules) != expected_modules:
        raise ValueError("result requires one receipt for each M02-01 through M02-05")
    receipt_payload = [
        {
            "module_id": item.module_id,
            "result_digest": item.result_digest,
            "disposition": item.disposition,
            **(
                {
                    "evaluated_target_ids": sorted(item.evaluated_target_ids),
                    "excluded_target_ids": sorted(item.excluded_target_ids),
                    "review_target_ids": sorted(item.review_target_ids),
                }
                if item.module_id == "GLIO-PROTEOGEN-M02-05"
                else {}
            ),
        }
        for item in sorted(result.upstream_receipts, key=lambda value: value.module_id)
    ]
    if result.prerequisites_digest != sha256_digest(receipt_payload):
        raise ValueError("result prerequisite receipt digest is inconsistent")
    expected_request = request_manifest_digest(
        active_context_digest=result.context_digest,
        active_prerequisites_digest=result.prerequisites_digest,
        active_profile_digest=result.profile_digest,
        active_policy_digest=result.policy_digest,
        observation_digests=tuple(item.source_observation_digest for item in result.values),
        invariant_digests=tuple(invariant_digest(item) for item in result.biological_controls),
        supersedes_result_digest=result.supersedes_result_digest,
    )
    if result.request_digest != expected_request:
        raise ValueError("result request digest is inconsistent")
    profile_stages = {item.stage_id: item for item in result.profile.stages}
    for transformation in manifest.stages:
        configured = profile_stages.get(transformation.stage_id)
        if configured is None or (
            transformation.ordinal,
            transformation.factor,
            transformation.reference_level_id,
            set(transformation.control_feature_ids),
            transformation.maximum_absolute_shift,
        ) != (
            configured.ordinal,
            configured.factor,
            configured.reference_level_id,
            set(configured.control_feature_ids),
            result.policy.max_absolute_shift,
        ):
            raise ValueError("transformation contradicts its configured stage")


def _m0205_receipt(result: IdentificationHarmonizationResult) -> UpstreamHarmonizationReceipt:
    return next(
        item for item in result.upstream_receipts if item.module_id == "GLIO-PROTEOGEN-M02-05"
    )


@dataclass(frozen=True, slots=True)
class _ExpectedStage:
    input_digest: Sha256Digest
    output_digest: Sha256Digest
    level_shifts: tuple[tuple[Identifier, ShiftState, float | None, float | None, int], ...]
    before_spread: float | None
    after_spread: float | None


def _kernel_payload(values: dict[tuple[str, str], float]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "target_id": target_id,
            "feature_id": feature_id,
            "state": "observed",
            "value": value,
        }
        for (target_id, feature_id), value in sorted(values.items())
    )


def _spread(values: dict[str, float]) -> float | None:
    return max(values.values()) - min(values.values()) if values else None


def _globally_abstained(result: IdentificationHarmonizationResult) -> bool:
    receipts: dict[str, UpstreamHarmonizationReceipt] = {
        item.module_id: item for item in result.upstream_receipts
    }
    accepted = {
        "GLIO-PROTEOGEN-M02-01": "conformant",
        "GLIO-PROTEOGEN-M02-02": "conformant",
        "GLIO-PROTEOGEN-M02-03": "accepted",
        "GLIO-PROTEOGEN-M02-04": "accepted",
    }
    if any(receipts[module].disposition != disposition for module, disposition in accepted.items()):
        return True
    artifact = receipts["GLIO-PROTEOGEN-M02-05"]
    artifact_usable = artifact.disposition == "accepted" or (
        artifact.disposition == "quarantined"
        and bool(artifact.excluded_target_ids)
        and not artifact.review_target_ids
    )
    return (
        not artifact_usable
        or bool(artifact.review_target_ids)
        or any(item.input_state is HarmonizationValueState.UNSUPPORTED for item in result.values)
    )


def _replay_expected_stages(
    result: IdentificationHarmonizationResult,
) -> tuple[dict[str, _ExpectedStage], dict[tuple[str, str], float]]:
    excluded = set(_m0205_receipt(result).excluded_target_ids)
    source_by_key = {
        (item.sample_id, item.feature_id): item.source_observation for item in result.values
    }
    working = {
        key: source.value
        for key, source in source_by_key.items()
        if source.target_id not in excluded
        and source.state is HarmonizationValueState.OBSERVED
        and source.value is not None
    }
    globally_abstained = _globally_abstained(result)
    expected: dict[str, _ExpectedStage] = {}
    for configured in result.profile.stages:
        input_digest = sha256_digest(_kernel_payload(working))
        active_level_by_target = {
            source.target_id: next(
                item.level_id for item in source.factor_levels if item.factor is configured.factor
            )
            for source in source_by_key.values()
            if source.target_id not in excluded
        }
        active_levels = set(active_level_by_target.values())
        insufficient_active_levels = (
            configured.reference_level_id not in active_levels
            or len(active_levels) < _MINIMUM_STAGE_LEVELS
        )
        level_by_target = (
            {
                source.target_id: next(
                    item.level_id
                    for item in source.factor_levels
                    if item.factor is configured.factor
                )
                for source in source_by_key.values()
            }
            if insufficient_active_levels
            else active_level_by_target
        )
        levels = sorted(set(level_by_target.values()))
        if configured.reference_level_id not in levels:
            levels.append(configured.reference_level_id)
            levels.sort()
        controls: dict[str, dict[str, list[float]]] = {
            level: {feature_id: [] for feature_id in configured.control_feature_ids}
            for level in levels
        }
        eligible_targets = set(configured.control_target_ids) - excluded
        for (target_id, feature_id), value in working.items():
            level = level_by_target.get(target_id)
            if (
                level in controls
                and target_id in eligible_targets
                and feature_id in controls[level]
            ):
                controls[level][feature_id].append(value)
        counts = {
            level: sum(len(items) for items in by_feature.values())
            for level, by_feature in controls.items()
        }
        force_not_evaluable = globally_abstained or insufficient_active_levels
        minimum = (
            len(result.values) + 1 if force_not_evaluable else result.policy.min_controls_per_level
        )
        feature_medians = {
            level: {
                feature_id: statistics.median(items)
                for feature_id, items in by_feature.items()
                if items
            }
            for level, by_feature in controls.items()
            if counts[level] >= minimum
        }
        reference = feature_medians.get(configured.reference_level_id)
        estimates: dict[str, float] = {}
        if reference is not None:
            for level, medians in feature_medians.items():
                differences = [
                    reference[feature_id] - medians[feature_id]
                    for feature_id in reference
                    if feature_id in medians
                ]
                if differences:
                    estimates[level] = statistics.median(differences)
        shifts: list[tuple[Identifier, ShiftState, float | None, float | None, int]] = []
        applied_by_level: dict[str, float] = {}
        for level in levels:
            estimate = estimates.get(level)
            if estimate is None:
                shifts.append((level, ShiftState.NOT_EVALUABLE, None, None, counts[level]))
                continue
            applied = max(
                -result.policy.max_absolute_shift,
                min(result.policy.max_absolute_shift, estimate),
            )
            state = (
                ShiftState.CAPPED
                if abs(estimate) >= result.policy.max_absolute_shift
                else ShiftState.ESTIMATED
            )
            shifts.append((level, state, estimate, applied, counts[level]))
            applied_by_level[level] = applied
        working = {
            key: value + applied_by_level.get(level_by_target[key[0]], 0.0)
            for key, value in working.items()
        }
        offsets = {level: -estimate for level, estimate in estimates.items()}
        post_offsets = {
            level: offset + applied_by_level[level]
            for level, offset in offsets.items()
            if level in applied_by_level
        }
        incomplete = any(item[1] is ShiftState.NOT_EVALUABLE for item in shifts)
        expected[configured.stage_id] = _ExpectedStage(
            input_digest=input_digest,
            output_digest=sha256_digest(_kernel_payload(working)),
            level_shifts=tuple(shifts),
            before_spread=None if incomplete else _spread(offsets),
            after_spread=None if incomplete else _spread(post_offsets),
        )
    return expected, working


def _validate_result_values(  # noqa: PLR0912,PLR0915 - exact value/manifest closure.
    result: IdentificationHarmonizationResult,
) -> None:
    keys = [(item.sample_id, item.feature_id) for item in result.values]
    if len(keys) != len(set(keys)):
        raise ValueError("harmonized values must be unique by target and feature")
    targets = {item.sample_id for item in result.values}
    features = {item.feature_id for item in result.values}
    groups = {item.biological_group_id for item in result.values}
    for configured_stage in result.profile.stages:
        if not set(configured_stage.control_target_ids).issubset(targets):
            raise ValueError("result profile references an unknown control target")
        if not set(configured_stage.control_feature_ids).issubset(features):
            raise ValueError("result profile references an unknown control feature")
    if any(
        not set(control.feature_ids).issubset(features)
        or not set(control.biological_group_ids).issubset(groups)
        for control in result.biological_controls
    ):
        raise ValueError("result biological control references an unknown source member")
    levels_by_target_factor: dict[
        tuple[Identifier, IdentificationTechnicalFactor], set[Identifier]
    ] = {}
    for value in result.values:
        for level in value.source_observation.factor_levels:
            levels_by_target_factor.setdefault(
                (value.sample_id, level.factor),
                set(),
            ).add(level.level_id)
    if any(len(levels) != 1 for levels in levels_by_target_factor.values()):
        raise ValueError("source factor levels must be consistent within each target")
    for configured_stage in result.profile.stages:
        declared_levels = {
            level.level_id
            for value in result.values
            for level in value.source_observation.factor_levels
            if level.factor is configured_stage.factor
        }
        if (
            configured_stage.reference_level_id not in declared_levels
            or len(declared_levels) < _MINIMUM_STAGE_LEVELS
        ):
            raise ValueError(
                "result stage requires a source-declared reference and comparison level"
            )
    if len({item.unit for item in result.values}) != 1:
        raise ValueError("harmonized values must preserve one common additive unit")
    artifact_receipt = _m0205_receipt(result)
    if not {item.sample_id for item in result.values}.issubset(
        artifact_receipt.evaluated_target_ids
    ):
        raise ValueError("every harmonized target must have an M02-05 evaluation receipt")
    excluded = set(artifact_receipt.excluded_target_ids)
    profile_stages = {item.stage_id: item for item in result.profile.stages}
    manifest_stages = {item.stage_id: item for item in result.transformation_manifest.stages}
    expected_stages, expected_final_values = _replay_expected_stages(result)
    for stage in manifest_stages.values():
        expected_controls = set(profile_stages[stage.stage_id].control_target_ids) - excluded
        if set(stage.control_target_ids) != expected_controls:
            raise ValueError("transformation controls contradict the exclusion firewall")
        expected_stage = expected_stages[stage.stage_id]
        actual_shifts = {
            item.level_id: (
                item.state,
                item.estimated_shift,
                item.applied_shift,
                item.control_count,
            )
            for item in stage.level_shifts
        }
        expected_shifts = {
            level_id: (state, estimate, applied, count)
            for level_id, state, estimate, applied, count in expected_stage.level_shifts
        }
        if (
            actual_shifts != expected_shifts
            or stage.input_digest != expected_stage.input_digest
            or stage.output_digest != expected_stage.output_digest
        ):
            raise ValueError("transformation manifest contradicts deterministic replay")
    for value in result.values:
        should_be_excluded = value.sample_id in excluded
        if (value.output_state is HarmonizationValueState.EXCLUDED) != should_be_excluded:
            raise ValueError("harmonized output contradicts the M02-05 exclusion receipt")
        value_key = (value.sample_id, value.feature_id)
        if value.output_state is HarmonizationValueState.OBSERVED and not math.isclose(
            value.harmonized_value or 0.0,
            expected_final_values[value_key],
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("harmonized output contradicts deterministic stage replay")
        levels = {item.factor: item.level_id for item in value.source_observation.factor_levels}
        expected_adjustments: list[tuple[object, ...]] = []
        if value.input_state is HarmonizationValueState.OBSERVED and not should_be_excluded:
            for configured in result.profile.stages:
                transformed = manifest_stages[configured.stage_id]
                level_id = levels[configured.factor]
                shift = next(item for item in transformed.level_shifts if item.level_id == level_id)
                if shift.applied_shift is None:
                    continue
                expected_adjustments.append(
                    (
                        configured.stage_id,
                        configured.ordinal,
                        configured.factor,
                        level_id,
                        shift.applied_shift,
                        value.unit,
                    )
                )
        actual_adjustments = [
            (
                item.stage_id,
                item.ordinal,
                item.factor,
                item.level_id,
                item.shift,
                item.unit,
            )
            for item in value.applied_adjustments
        ]
        if actual_adjustments != expected_adjustments:
            raise ValueError("value adjustments do not cover the exact applicable stages")
        for adjustment in value.applied_adjustments:
            configured_lookup = profile_stages.get(adjustment.stage_id)
            transformed_lookup = manifest_stages.get(adjustment.stage_id)
            if (
                configured_lookup is None
                or transformed_lookup is None
                or (
                    adjustment.ordinal,
                    adjustment.factor,
                    adjustment.level_id,
                )
                != (
                    configured_lookup.ordinal,
                    configured_lookup.factor,
                    levels[configured_lookup.factor],
                )
            ):
                raise ValueError("value adjustment contradicts the configured stage")
            shift_lookup = next(
                (
                    item
                    for item in transformed_lookup.level_shifts
                    if item.level_id == adjustment.level_id
                ),
                None,
            )
            if shift_lookup is None or shift_lookup.applied_shift != adjustment.shift:
                raise ValueError("value adjustment contradicts the transformation manifest")


def _invariant_member_median(
    result: IdentificationHarmonizationResult,
    *,
    feature_id: str,
    group_id: str,
    before: bool,
    expected_values: dict[tuple[str, str], float] | None,
) -> float | None:
    excluded = set(_m0205_receipt(result).excluded_target_ids)
    members = [
        item
        for item in result.values
        if item.sample_id not in excluded
        and item.feature_id == feature_id
        and item.biological_group_id == group_id
    ]
    if not members or any(
        item.input_state is not HarmonizationValueState.OBSERVED for item in members
    ):
        return None
    if before:
        return statistics.median(
            item.input_value for item in members if item.input_value is not None
        )
    if expected_values is None:
        raise TypeError("after-harmonization score requires replayed values")
    return statistics.median(expected_values[(item.sample_id, item.feature_id)] for item in members)


def _invariant_score_from_result(
    invariant: BiologicalControlInvariant,
    result: IdentificationHarmonizationResult,
    *,
    before: bool,
    expected_values: dict[tuple[str, str], float] | None = None,
) -> float | None:
    if _globally_abstained(result):
        return None
    if invariant.kind is BiologicalInvariantKind.DIRECTION:
        first = _invariant_member_median(
            result,
            feature_id=invariant.feature_ids[0],
            group_id=invariant.biological_group_ids[0],
            before=before,
            expected_values=expected_values,
        )
        second = _invariant_member_median(
            result,
            feature_id=invariant.feature_ids[0],
            group_id=invariant.biological_group_ids[1],
            before=before,
            expected_values=expected_values,
        )
    else:
        first = _invariant_member_median(
            result,
            feature_id=invariant.feature_ids[0],
            group_id=invariant.biological_group_ids[0],
            before=before,
            expected_values=expected_values,
        )
        second = _invariant_member_median(
            result,
            feature_id=invariant.feature_ids[1],
            group_id=invariant.biological_group_ids[0],
            before=before,
            expected_values=expected_values,
        )
    return None if first is None or second is None else second - first


def _validate_result_diagnostics_and_disposition(
    result: IdentificationHarmonizationResult,
) -> None:
    expected_stages, expected_values = _replay_expected_stages(result)
    technical_keys = [item.stage_id for item in result.technical_effect_diagnostics]
    if len(set(technical_keys)) != len(technical_keys) or set(technical_keys) != {
        item.stage_id for item in result.profile.stages
    }:
        raise ValueError("technical diagnostics must cover each configured stage")
    for diagnostic in result.technical_effect_diagnostics:
        stage = next(item for item in result.profile.stages if item.stage_id == diagnostic.stage_id)
        transformation = next(
            item
            for item in result.transformation_manifest.stages
            if item.stage_id == diagnostic.stage_id
        )
        if (
            diagnostic.factor is not stage.factor
            or diagnostic.tolerance != result.policy.technical_effect_tolerance
            or diagnostic.capped
            != any(item.state is ShiftState.CAPPED for item in transformation.level_shifts)
            or diagnostic.before_spread != expected_stages[diagnostic.stage_id].before_spread
            or diagnostic.after_spread != expected_stages[diagnostic.stage_id].after_spread
        ):
            raise ValueError("technical diagnostic contradicts its stage or policy")
    invariant_map = {item.invariant_id: item for item in result.biological_controls}
    if len(invariant_map) != len(result.biological_controls) or {
        item.invariant_id for item in result.biological_invariant_diagnostics
    } != set(invariant_map):
        raise ValueError("biological diagnostics must cover each declared control")
    for invariant_diagnostic in result.biological_invariant_diagnostics:
        invariant = invariant_map[invariant_diagnostic.invariant_id]
        expected_before = _invariant_score_from_result(invariant, result, before=True)
        expected_after = _invariant_score_from_result(
            invariant,
            result,
            before=False,
            expected_values=expected_values,
        )
        if (
            invariant_diagnostic.kind is not invariant.kind
            or invariant_diagnostic.tolerance != result.policy.biological_invariant_tolerance
            or invariant_diagnostic.before_score != expected_before
            or invariant_diagnostic.after_score != expected_after
        ):
            raise ValueError("biological diagnostic contradicts its control or policy")
    statuses = [
        *(item.status for item in result.technical_effect_diagnostics),
        *(item.status for item in result.biological_invariant_diagnostics),
    ]
    expected = (
        HarmonizationDisposition.QUARANTINED
        if DiagnosticStatus.FAILED in statuses
        else HarmonizationDisposition.ABSTAINED
        if DiagnosticStatus.NOT_EVALUABLE in statuses
        else HarmonizationDisposition.ACCEPTED
    )
    if result.disposition is not expected:
        raise ValueError("harmonization disposition contradicts its diagnostics")


def _validate_result_envelope(  # noqa: PLR0912 - exact closed output envelope.
    result: IdentificationHarmonizationResult,
) -> None:
    expected_support = {
        HarmonizationDisposition.ACCEPTED: (
            SupportStatus.LIMITED,
            "identification_harmonization_accepted",
            "All configured technical and biological diagnostics passed.",
            False,
        ),
        HarmonizationDisposition.QUARANTINED: (
            SupportStatus.REVIEW_REQUIRED,
            "identification_harmonization_quarantined",
            "At least one harmonization diagnostic failed and requires review.",
            True,
        ),
        HarmonizationDisposition.ABSTAINED: (
            SupportStatus.UNSUPPORTED,
            "identification_harmonization_abstained",
            "At least one harmonization diagnostic was not evaluable.",
            True,
        ),
    }[result.disposition]
    if (
        result.support.status,
        result.support.reason_code,
        result.support.rationale,
        result.human_review_required,
    ) != expected_support:
        raise ValueError("harmonization support contradicts disposition")
    suffix = result.request_digest.removeprefix("sha256:")
    provenance = result.provenance
    if (
        result.harmonization_id != f"harmonization.m0206.{suffix}"
        or provenance.activity_id != f"activity.m0206.{suffix}"
        or provenance.module_id != M0206_MODULE_ID
        or provenance.module_version != result.result_version
        or provenance.generated_at != result.completed_at
        or provenance.configuration_digest != result.configuration_digest
    ):
        raise ValueError("M02-06 provenance is inconsistent")
    required = {
        result.request_digest,
        result.context_digest,
        result.prerequisites_digest,
        result.profile_digest,
        result.policy_digest,
        result.configuration_digest,
        *(item.result_digest for item in result.upstream_receipts),
        *(item.evidence_digest for item in provenance.control_decisions),
    }
    if set(provenance.input_digests) != required or len(provenance.input_digests) != len(required):
        raise ValueError("M02-06 provenance must contain the exact unique input digest set")
    expected_states = {
        "approved_configuration": "accepted",
        "identity_lineage": "resolved",
        "provenance": "accepted",
        "consent": "granted",
        "quality": "accepted",
        "support": "accepted",
        "intended_use": "accepted",
    }
    controls = {item.role.value: item for item in provenance.control_decisions}
    if {key: item.state for key, item in controls.items()} != expected_states:
        raise ValueError("M02-06 control decisions are inconsistent")
    if controls["approved_configuration"].evidence_digest != result.configuration_digest:
        raise ValueError("approved configuration does not bind the result")
    identity_receipt = next(
        item for item in result.upstream_receipts if item.module_id == "GLIO-PROTEOGEN-M02-02"
    )
    if controls["identity_lineage"].subject_digest != identity_receipt.result_digest:
        raise ValueError("identity control does not bind the M02-02 receipt")
    consent = controls["consent"]
    if (
        provenance.consent_decision_id,
        provenance.consent_state.value,
        provenance.consent_policy_version,
        provenance.consent_evidence_digest,
    ) != (
        consent.decision_id,
        consent.state,
        consent.policy_version,
        consent.evidence_digest,
    ):
        raise ValueError("M02-06 consent provenance is inconsistent")
    common_unit = result.values[0].unit
    if any(
        shift.unit != common_unit
        for stage in result.transformation_manifest.stages
        for shift in stage.level_shifts
    ):
        raise ValueError("transformation shifts must use the common output unit")
    expected_limitations = {
        M0206_HARMONIZATION_LIMITATION_CODE: M0206_HARMONIZATION_LIMITATION_STATEMENT,
        M0206_AUTHORITY_LIMITATION_CODE: M0206_AUTHORITY_LIMITATION_STATEMENT,
    }
    if {item.code: item.statement for item in result.limitations} != expected_limitations:
        raise ValueError("M02-06 result requires both fixed limitations")
    if len(result.evidence) != len(set(result.evidence)) or len(
        {item.reference.digest for item in result.evidence}
    ) != len(result.evidence):
        raise ValueError("M02-06 evidence and evidence digests must be unique")
    expected_evidence = {
        result.profile.evidence.digest,
        *(item.evidence_digest for item in provenance.control_decisions),
    }
    if {item.reference.digest for item in result.evidence} != expected_evidence:
        raise ValueError("M02-06 evidence index is inconsistent")
    expected_claims = {
        item.evidence_digest: (
            "evidence",
            f"Caller-declared {item.role.value} control; issuer is not authenticated.",
        )
        for item in provenance.control_decisions
    }
    expected_claims[result.profile.evidence.digest] = (
        "evidence",
        M0206_PROFILE_EVIDENCE_CLAIM,
    )
    if {
        item.reference.digest: (item.role, item.claim) for item in result.evidence
    } != expected_claims:
        raise ValueError("M02-06 evidence claims exceed the module authority boundary")
    for dimension, rationale in M0206_UNCERTAINTY_RATIONALES.items():
        estimate = getattr(result.uncertainty, dimension)
        if (
            estimate.state is not EstimateState.NOT_ESTIMABLE
            or estimate.probability is not None
            or estimate.rationale != rationale
        ):
            raise ValueError("M02-06 uncertainty must remain deterministic and not estimable")
    if result.uncertainty.sensitivity_notes != M0206_SENSITIVITY_NOTES:
        raise ValueError("M02-06 uncertainty sensitivity notes are inconsistent")


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    if references.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize identification harmonization")
    if references.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before harmonization")
    generic = (
        references.approved_configuration,
        references.provenance,
        references.quality,
        references.support,
        references.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every upstream control must authorize identification harmonization")


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


__all__ = [
    "M0206_AUTHORITY_LIMITATION_CODE",
    "M0206_CONTRACT_VERSION",
    "M0206_HARMONIZATION_LIMITATION_CODE",
    "M0206_MAX_INVARIANTS",
    "M0206_MAX_OBSERVATIONS",
    "M0206_MAX_STAGES",
    "M0206_MODULE_ID",
    "AppliedStageAdjustment",
    "BiologicalControlInvariant",
    "BiologicalInvariantDiagnostic",
    "BiologicalInvariantKind",
    "DiagnosticStatus",
    "HarmonizationDisposition",
    "HarmonizationValueState",
    "HarmonizeIdentificationEvidenceRequest",
    "HarmonizedIdentificationValue",
    "IdentificationAbundanceObservation",
    "IdentificationFactorLevel",
    "IdentificationHarmonizationDisposition",
    "IdentificationHarmonizationPolicy",
    "IdentificationHarmonizationPrerequisites",
    "IdentificationHarmonizationProfile",
    "IdentificationHarmonizationResult",
    "IdentificationLevelShift",
    "IdentificationNormalizationStage",
    "IdentificationStageTransformation",
    "IdentificationTechnicalFactor",
    "IdentificationTransformationManifest",
    "ShiftState",
    "SourceObservationSummary",
    "TechnicalEffectDiagnostic",
    "UpstreamHarmonizationReceipt",
]
