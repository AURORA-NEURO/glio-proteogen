"""Provisional M05-06 PTM-localization harmonization contracts.

This ABI is intentionally marked provisional.  M05-06 is not present in the
published dossier ABI, so the names and limits below are a convention proposal
copied from the M04-06 harmonization boundary and specialized to the complete
M05-05 result.  The boundary is nevertheless strict: it replays the complete
M05-05 result, preserves the seven control authorities, and never turns an
artifact review or an unavailable support coordinate into a negative claim.
"""

# Provisional ABI keeps explicit closure checks readable while this contract is
# pending owner confirmation; line-length and local-import diagnostics are tracked
# separately from the strict type/schema gate.
# ruff: noqa: E501, PLC0415

from __future__ import annotations

import re
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m05_05.v1 import (
    M0505_CONTRACT_VERSION,
    PtmLocalizationArtifactDetectionResult,
    PtmLocalizationArtifactDisposition,
    PtmLocalizationEvidenceUnitKind,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentState,
    ControlDecisionRecord,
    ControlRole,
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
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0506_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-06"
M0506_OPERATION: Final = "harmonize_ptm_localization_analysis"
M0506_CONTRACT_VERSION: Final = "1.0.0-provisional"
M0506_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-06+json"
M0506_PARENT: Final = "variant_peptide"
M0506_OWNER: Final = "Platform engineering"
M0506_SAFETY_CLASS: Final = "S2"
M0506_GATE: Final = "G1"
M0506_RATE_SCALE: Final = 1_000_000
M0506_FACTOR_COUNT: Final = 8
M0506_UPSTREAM_DETECTOR_COUNT: Final = 7
M0506_MAX_TARGETS: Final = 64
M0506_MAX_OBSERVATIONS: Final = 64
M0506_MAX_STAGES: Final = 8
M0506_MAX_LEVELS_PER_FACTOR: Final = 64
M0506_MAX_INVARIANTS: Final = 256
M0506_MAX_PROFILES: Final = 16
M0506_MAX_EVIDENCE: Final = 24
M0506_MAX_FINDINGS: Final = 16
M0506_MAX_EVIDENCE_PER_OBSERVATION: Final = 8
M0506_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0506_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M0506_BENCHMARK_ITERATIONS: Final = 25
M0506_BENCHMARK_WARMUPS: Final = 1
M0506_MEAN_BUDGET_NS: Final = 4_000_000_000
M0506_P95_BUDGET_NS: Final = 5_000_000_000
M0506_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0506_PROVISIONAL_ABI: Final = True
M0506_EVIDENCE_CLAIM: Final = (
    "Caller-declared PTM-localization harmonization evidence; issuer is not authenticated."
)
M0506_HARMONIZATION_LIMITATION_CODE: Final = "ptm_localization_harmonization_only"
M0506_UNCERTAINTY_RATIONALES: Final = (
    "Measurement uncertainty is not estimated from caller-declared support coordinates.",
    "Sampling uncertainty is not estimated by deterministic normalization.",
    "The provisional fixed-point boundary fits no probabilistic parameters.",
    "No learned model, sequence model, or external content is executed.",
    "PTM identity, modification localization, kinase state, and treatment remain outside this module.",
    "Support is limited to the reviewed M05-05 result and caller-declared controls.",
    "Transportability requires external assay, cohort, and control-panel validation.",
)

_OPAQUE_IDENTIFIER = re.compile(
    r"^(request|policy|profile|ledger|target|anchor|group|level|invariant|stage|evidence|reviewer)\.[0-9a-f]{64}$"
)
_LOWERCASE_MEDIA_TYPE = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$"
)
_M0505_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-05+json"


def opaque_harmonization_identifier(namespace: str, value: object) -> Identifier:
    """Derive one opaque, content-addressed identifier for this boundary."""

    if namespace not in {
        "request",
        "policy",
        "profile",
        "ledger",
        "target",
        "anchor",
        "group",
        "level",
        "invariant",
        "stage",
        "evidence",
        "reviewer",
    }:
        raise ValueError("unknown M05-06 identifier namespace")
    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def _opaque(value: Identifier, namespace: str, label: str) -> Identifier:
    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be an opaque {namespace} identifier")
    return value


class PtmLocalizationNormalizationFactor(StrEnum):
    PLATFORM = "platform"
    BATCH = "batch"
    LABORATORY = "laboratory"
    BUILD = "build"
    DEPTH = "depth"
    PURITY = "purity"
    COMPOSITION = "composition"
    PREANALYTIC = "preanalytic"


class PtmLocalizationSupportObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    CENSORED = "censored"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class PtmLocalizationArtifactTargetState(StrEnum):
    CLEAR = "clear"
    REVIEW = "review"
    INDETERMINATE = "indeterminate"
    EXCLUDED = "excluded"


class PtmLocalizationArtifactAction(StrEnum):
    RETAIN = "retain"
    REVIEW = "review"
    EXCLUDE = "exclude"


class PtmLocalizationArtifactEvaluationState(StrEnum):
    COMPLETE = "complete"
    NOT_EVALUABLE = "not_evaluable"


class PtmLocalizationSupportShiftState(StrEnum):
    ESTIMATED = "estimated"
    CAPPED = "capped"
    NOT_EVALUABLE = "not_evaluable"


class PtmLocalizationHarmonizationDiagnosticStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class PtmLocalizationSupportInvariantKind(StrEnum):
    SUPPORT_DIRECTION = "support_direction"
    SUPPORT_RANK = "support_rank"
    SITE_FRACTION = "site_fraction"


class PtmLocalizationHarmonizationDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class PtmLocalizationHarmonizationFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class PtmLocalizationHarmonizationFindingCode(StrEnum):
    UPSTREAM_QUARANTINED = "upstream_quarantined"
    UPSTREAM_ABSTAINED = "upstream_abstained"
    UPSTREAM_SHAPE_UNSUPPORTED = "upstream_shape_unsupported"
    SUPPORT_LEDGER_BINDING_MISMATCH = "support_ledger_binding_mismatch"
    HARMONIZATION_PROFILE_UNSUPPORTED = "harmonization_profile_unsupported"
    ARTIFACT_EXCLUSION_PRESENT = "artifact_exclusion_present"
    ARTIFACT_REVIEW_REQUIRED = "artifact_review_required"
    RETAINED_SUPPORT_NOT_EVALUABLE = "retained_support_not_evaluable"
    CONTROL_PAIR_INSUFFICIENT = "control_pair_insufficient"
    SHIFT_CAPPED = "shift_capped"
    VALUE_CLIPPED = "value_clipped"
    TECHNICAL_EFFECT_NOT_REDUCED = "technical_effect_not_reduced"
    INVARIANT_NOT_EVALUABLE = "invariant_not_evaluable"
    INVARIANT_VIOLATED = "invariant_violated"


_FINDING_ACTION: Final = {
    PtmLocalizationHarmonizationFindingCode.UPSTREAM_QUARANTINED: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
    PtmLocalizationHarmonizationFindingCode.UPSTREAM_ABSTAINED: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
    PtmLocalizationHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
    PtmLocalizationHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.SHIFT_CAPPED: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
    PtmLocalizationHarmonizationFindingCode.VALUE_CLIPPED: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
    PtmLocalizationHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
    PtmLocalizationHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE: PtmLocalizationHarmonizationFindingAction.ABSTAIN,
    PtmLocalizationHarmonizationFindingCode.INVARIANT_VIOLATED: PtmLocalizationHarmonizationFindingAction.QUARANTINE,
}


def _canonical_unique[T](values: tuple[T, ...], label: str) -> tuple[T, ...]:
    if len(values) != len({canonical_json_bytes(value) for value in values}):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(values, key=canonical_json_bytes))


class PtmLocalizationNormalizationFactorLevel(FrozenModel):
    factor: PtmLocalizationNormalizationFactor
    level_id: Identifier

    @field_validator("level_id")
    @classmethod
    def level_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque(value, "level", "factor level")


class PtmLocalizationArtifactTargetReceipt(FrozenModel):
    """Exact seven-detector projection of one full M05-05 target."""

    target_id: Identifier
    unit_kind: PtmLocalizationEvidenceUnitKind
    target_state: PtmLocalizationArtifactTargetState
    action: PtmLocalizationArtifactAction
    posterior_digests: tuple[Sha256Digest, ...] = Field(
        min_length=M0506_UPSTREAM_DETECTOR_COUNT,
        max_length=M0506_UPSTREAM_DETECTOR_COUNT,
    )
    posterior_binding_digest: Sha256Digest
    contamination_flag_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M0506_UPSTREAM_DETECTOR_COUNT
    )
    excluded: bool

    @field_validator("target_id")
    @classmethod
    def target_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque(value, "target", "target")

    @field_validator("posterior_digests")
    @classmethod
    def posterior_digests_are_canonical(
        cls, values: tuple[Sha256Digest, ...]
    ) -> tuple[Sha256Digest, ...]:
        return _canonical_unique(values, "posterior digests")

    @field_validator("contamination_flag_ids")
    @classmethod
    def flags_are_opaque(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)) or any(
            not value.startswith("flag.") or re.fullmatch(r"flag\.[0-9a-f]{64}", value) is None
            for value in values
        ):
            raise ValueError("contamination flags must preserve M05-05 opaque identifiers")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def projection_is_closed(self) -> PtmLocalizationArtifactTargetReceipt:
        expected = {
            PtmLocalizationArtifactTargetState.CLEAR: PtmLocalizationArtifactAction.RETAIN,
            PtmLocalizationArtifactTargetState.REVIEW: PtmLocalizationArtifactAction.REVIEW,
            PtmLocalizationArtifactTargetState.INDETERMINATE: PtmLocalizationArtifactAction.REVIEW,
            PtmLocalizationArtifactTargetState.EXCLUDED: PtmLocalizationArtifactAction.EXCLUDE,
        }[self.target_state]
        if self.action is not expected or self.excluded != (
            self.action is PtmLocalizationArtifactAction.EXCLUDE
        ):
            raise ValueError("M05-05 target projection contradicts its state")
        if self.posterior_binding_digest != sha256_digest(self.posterior_digests):
            raise ValueError("posterior binding digest is stale")
        if (
            self.target_state
            in {
                PtmLocalizationArtifactTargetState.CLEAR,
                PtmLocalizationArtifactTargetState.INDETERMINATE,
            }
            and self.contamination_flag_ids
        ):
            raise ValueError("clear or indeterminate targets cannot carry contamination flags")
        return self


class PtmLocalizationArtifactHarmonizationReceipt(FrozenModel):
    """Replay receipt binding the complete upstream M05-05 result."""

    receipt_version: Literal["1.0.0-provisional"] = M0506_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    artifact_result_digest: Sha256Digest
    artifact_request_digest: Sha256Digest
    artifact_disposition: PtmLocalizationArtifactDisposition
    artifact_support_status: SupportStatus
    artifact_human_review_required: bool
    artifact_completed_at: AwareDatetime
    quality_result_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    raw_input_receipt_digest: Sha256Digest
    evaluation_state: PtmLocalizationArtifactEvaluationState
    target_count: int = Field(ge=0, le=M0506_MAX_TARGETS)
    targets: tuple[PtmLocalizationArtifactTargetReceipt, ...] = Field(
        default=(), max_length=M0506_MAX_TARGETS
    )
    target_binding_digest: Sha256Digest
    receipt_digest: Sha256Digest

    @field_validator("targets")
    @classmethod
    def targets_are_canonical(
        cls, values: tuple[PtmLocalizationArtifactTargetReceipt, ...]
    ) -> tuple[PtmLocalizationArtifactTargetReceipt, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_closed(self) -> PtmLocalizationArtifactHarmonizationReceipt:
        from glio_proteogen.contracts.m05_06.canonical import (
            artifact_receipt_digest,
            target_binding_digest,
        )

        if self.target_count != len(self.targets) or len(
            {item.target_id for item in self.targets}
        ) != len(self.targets):
            raise ValueError("target count and projection are inconsistent")
        complete = self.evaluation_state is PtmLocalizationArtifactEvaluationState.COMPLETE
        if complete != (self.artifact_disposition is PtmLocalizationArtifactDisposition.CLEARED):
            raise ValueError("M05-05 disposition and evaluation state contradict")
        if self.target_binding_digest != target_binding_digest(self.targets):
            raise ValueError("target binding digest is stale")
        if (
            self.artifact_reference.version != M0505_CONTRACT_VERSION
            or self.artifact_reference.media_type != _M0505_MEDIA_TYPE
        ):
            raise ValueError("artifact reference does not identify the M05-05 result ABI")
        if self.artifact_reference.digest != self.artifact_result_digest:
            raise ValueError("artifact reference digest does not bind M05-05 result")
        if self.receipt_digest != artifact_receipt_digest(self):
            raise ValueError("M05-06 artifact receipt digest is stale")
        return self


class PtmLocalizationSupportObservation(FrozenModel):
    target_id: Identifier
    unit_kind: PtmLocalizationEvidenceUnitKind
    artifact_target_state: PtmLocalizationArtifactTargetState
    artifact_action: PtmLocalizationArtifactAction
    posterior_digests: tuple[Sha256Digest, ...] = Field(
        min_length=M0506_UPSTREAM_DETECTOR_COUNT,
        max_length=M0506_UPSTREAM_DETECTOR_COUNT,
    )
    posterior_binding_digest: Sha256Digest
    state: PtmLocalizationSupportObservationState
    support_coordinate_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    censoring_upper_bound_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    factor_levels: tuple[PtmLocalizationNormalizationFactorLevel, ...] = Field(
        min_length=M0506_FACTOR_COUNT, max_length=M0506_FACTOR_COUNT
    )
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M0506_MAX_EVIDENCE_PER_OBSERVATION
    )
    artifact_excluded: bool

    @model_validator(mode="after")
    def observation_is_closed(self) -> PtmLocalizationSupportObservation:
        if len(set(self.posterior_digests)) != len(
            self.posterior_digests
        ) or self.posterior_binding_digest != sha256_digest(self.posterior_digests):
            raise ValueError("observation posterior binding is not canonical")
        if {item.factor for item in self.factor_levels} != set(PtmLocalizationNormalizationFactor):
            raise ValueError("observation must declare all eight technical factors")
        expected = {
            PtmLocalizationArtifactTargetState.CLEAR: PtmLocalizationArtifactAction.RETAIN,
            PtmLocalizationArtifactTargetState.REVIEW: PtmLocalizationArtifactAction.REVIEW,
            PtmLocalizationArtifactTargetState.INDETERMINATE: PtmLocalizationArtifactAction.REVIEW,
            PtmLocalizationArtifactTargetState.EXCLUDED: PtmLocalizationArtifactAction.EXCLUDE,
        }[self.artifact_target_state]
        if self.artifact_action is not expected or self.artifact_excluded != (
            self.artifact_action is PtmLocalizationArtifactAction.EXCLUDE
        ):
            raise ValueError("observation artifact state/action mismatch")
        numeric = self.state is PtmLocalizationSupportObservationState.OBSERVED
        if numeric != (
            self.support_coordinate_ppm is not None and self.censoring_upper_bound_ppm is None
        ):
            raise ValueError("observed support requires exactly one coordinate")
        if self.state is PtmLocalizationSupportObservationState.CENSORED and (
            self.censoring_upper_bound_ppm is None or self.support_coordinate_ppm is not None
        ):
            raise ValueError("censored support requires only an upper bound")
        if (
            self.state is not PtmLocalizationSupportObservationState.OBSERVED
            and self.state is not PtmLocalizationSupportObservationState.CENSORED
            and (
                self.support_coordinate_ppm is not None
                or self.censoring_upper_bound_ppm is not None
            )
        ):
            raise ValueError("non-evaluable support cannot carry numeric coordinates")
        return self


class PtmLocalizationSupportInvariant(FrozenModel):
    invariant_id: Identifier
    kind: PtmLocalizationSupportInvariantKind
    target_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M0506_MAX_TARGETS)
    evidence: tuple[ArtifactReference, ...] = Field(min_length=1, max_length=8)

    @field_validator("invariant_id")
    @classmethod
    def invariant_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque(value, "invariant", "invariant")


class PtmLocalizationSupportLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    artifact_result_digest: Sha256Digest
    observations: tuple[PtmLocalizationSupportObservation, ...] = Field(
        min_length=1, max_length=M0506_MAX_OBSERVATIONS
    )
    invariants: tuple[PtmLocalizationSupportInvariant, ...] = Field(
        default=(), max_length=M0506_MAX_INVARIANTS
    )
    evidence: ArtifactReference
    ledger_digest: Sha256Digest

    @field_validator("observations")
    @classmethod
    def observations_are_canonical(
        cls, values: tuple[PtmLocalizationSupportObservation, ...]
    ) -> tuple[PtmLocalizationSupportObservation, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def ledger_is_closed(self) -> PtmLocalizationSupportLedger:
        from glio_proteogen.contracts.m05_06.canonical import support_ledger_digest

        if len({item.target_id for item in self.observations}) != len(self.observations):
            raise ValueError("support observations must have unique target identifiers")
        _opaque(self.ledger_id, "ledger", "ledger")
        if self.ledger_digest != support_ledger_digest(self):
            raise ValueError("support ledger digest is stale")
        return self


class PtmLocalizationNormalizationStage(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0506_MAX_STAGES)
    factor: PtmLocalizationNormalizationFactor
    reference_level_id: Identifier
    estimation_anchor_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M0506_MAX_OBSERVATIONS
    )
    validation_anchor_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M0506_MAX_OBSERVATIONS
    )

    @model_validator(mode="after")
    def stage_is_closed(self) -> PtmLocalizationNormalizationStage:
        _opaque(self.stage_id, "stage", "stage")
        _opaque(self.reference_level_id, "level", "reference level")
        if set(self.estimation_anchor_ids) & set(self.validation_anchor_ids):
            raise ValueError("estimation and validation anchors must be disjoint")
        return self


class PtmLocalizationHarmonizationProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    approved_artifact_contract_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=32
    )
    stages: tuple[PtmLocalizationNormalizationStage, ...] = Field(
        min_length=M0506_MAX_STAGES, max_length=M0506_MAX_STAGES
    )
    evidence: ArtifactReference

    @field_validator("stages")
    @classmethod
    def stages_are_ordered(
        cls, values: tuple[PtmLocalizationNormalizationStage, ...]
    ) -> tuple[PtmLocalizationNormalizationStage, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def profile_is_closed(self) -> PtmLocalizationHarmonizationProfile:
        _opaque(self.profile_id, "profile", "profile")
        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0506_MAX_STAGES + 1)):
            raise ValueError("profile stages must have ordinals one through eight")
        if {item.factor for item in self.stages} != set(PtmLocalizationNormalizationFactor):
            raise ValueError("profile must configure every technical factor exactly once")
        return self


class PtmLocalizationHarmonizationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_targets: int = Field(gt=0, le=M0506_MAX_TARGETS)
    max_observations: int = Field(gt=0, le=M0506_MAX_OBSERVATIONS)
    max_absolute_shift_ppm: int = Field(gt=0, le=M0506_RATE_SCALE)
    technical_effect_tolerance_ppm: int = Field(ge=0, le=M0506_RATE_SCALE)
    profiles: tuple[PtmLocalizationHarmonizationProfile, ...] = Field(
        min_length=1, max_length=M0506_MAX_PROFILES
    )
    evidence: ArtifactReference

    @field_validator("policy_id")
    @classmethod
    def policy_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque(value, "policy", "policy")

    @field_validator("profiles")
    @classmethod
    def profiles_are_canonical(
        cls, values: tuple[PtmLocalizationHarmonizationProfile, ...]
    ) -> tuple[PtmLocalizationHarmonizationProfile, ...]:
        return _canonical_unique(values, "harmonization profiles")


class HarmonizePtmLocalizationAnalysisRequest(FrozenModel):
    operation: Literal["harmonize_ptm_localization_analysis"] = M0506_OPERATION
    contract_version: Literal["1.0.0-provisional"] = M0506_CONTRACT_VERSION
    context: ExecutionContext
    artifact_result: PtmLocalizationArtifactDetectionResult
    artifact_receipt: PtmLocalizationArtifactHarmonizationReceipt
    support_ledger: PtmLocalizationSupportLedger | None = None
    policy: PtmLocalizationHarmonizationPolicy
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("artifact_result", mode="before")
    @classmethod
    def artifact_result_is_strictly_replayed(
        cls, value: object
    ) -> PtmLocalizationArtifactDetectionResult:
        return PtmLocalizationArtifactDetectionResult.model_validate_json(
            canonical_json_bytes(value), strict=True
        )

    @model_validator(mode="after")
    def request_is_authorized_and_bound(
        self,
    ) -> HarmonizePtmLocalizationAnalysisRequest:
        refs = self.context.references
        upstream_refs = self.artifact_result.request.context.references
        if self.context.request_id != self.artifact_result.request.request_id:
            raise ValueError("M05-06 context must preserve the M05-05 request identifier")
        if any(
            current != upstream
            for current, upstream in (
                (refs.identity_lineage, upstream_refs.identity_lineage),
                (refs.provenance, upstream_refs.provenance),
                (refs.consent, upstream_refs.consent),
                (refs.support, upstream_refs.support),
                (refs.intended_use, upstream_refs.intended_use),
            )
        ):
            raise ValueError("M05-06 must preserve M05-05 identity/provenance/support authority")
        if (
            refs.approved_configuration.state is not UpstreamDecisionState.ACCEPTED
            or refs.quality.state is not UpstreamDecisionState.ACCEPTED
            or refs.provenance.state is not UpstreamDecisionState.ACCEPTED
            or refs.support.state is not UpstreamDecisionState.ACCEPTED
            or refs.intended_use.state is not UpstreamDecisionState.ACCEPTED
            or refs.identity_lineage.state is not IdentityLineageState.RESOLVED
            or refs.consent.state is not ConsentState.GRANTED
        ):
            raise ValueError("M05-06 requires all seven authorized upstream controls")
        from glio_proteogen.contracts.m05_06.canonical import configuration_digest

        if refs.approved_configuration.evidence.digest != configuration_digest(self.policy):
            raise ValueError("approved configuration must bind the M05-06 policy")
        from glio_proteogen.contracts.m05_06.canonical import artifact_receipt_digest

        if (
            self.artifact_receipt.artifact_result_digest != self.artifact_result.result_digest
            or self.artifact_receipt.receipt_digest
            != artifact_receipt_digest(self.artifact_receipt)
        ):
            raise ValueError("artifact receipt must bind the complete M05-05 result")
        if self.artifact_result.disposition is not PtmLocalizationArtifactDisposition.CLEARED:
            if self.support_ledger is not None:
                raise ValueError("quarantined or abstained M05-05 results cannot traverse support")
        else:
            if (
                self.support_ledger is None
                or self.support_ledger.artifact_result_digest != self.artifact_result.result_digest
            ):
                raise ValueError("cleared M05-05 result requires an exactly bound support ledger")
            target_ids = {item.target_id for item in self.artifact_receipt.targets}
            if {item.target_id for item in self.support_ledger.observations} - target_ids:
                raise ValueError("support ledger references an unknown M05-05 target")
        if len(canonical_json_bytes(self)) > M0506_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M05-06 request exceeds the ingress ceiling")
        return self


class PtmLocalizationSupportLevelShift(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0506_MAX_STAGES)
    factor: PtmLocalizationNormalizationFactor
    level_id: Identifier
    state: PtmLocalizationSupportShiftState
    estimated_shift_ppm: int | None = Field(default=None, ge=-M0506_RATE_SCALE, le=M0506_RATE_SCALE)
    applied_shift_ppm: int | None = Field(default=None, ge=-M0506_RATE_SCALE, le=M0506_RATE_SCALE)
    estimation_pair_count: int = Field(ge=0, le=M0506_MAX_OBSERVATIONS)
    validation_pair_count: int = Field(ge=0, le=M0506_MAX_OBSERVATIONS)

    @model_validator(mode="after")
    def shift_shape_is_closed(self) -> PtmLocalizationSupportLevelShift:
        _opaque(self.stage_id, "stage", "stage")
        _opaque(self.level_id, "level", "level")
        if self.state is PtmLocalizationSupportShiftState.NOT_EVALUABLE and (
            self.estimated_shift_ppm is not None or self.applied_shift_ppm is not None
        ):
            raise ValueError("not-evaluable shifts cannot carry numbers")
        if (
            self.state is not PtmLocalizationSupportShiftState.NOT_EVALUABLE
            and self.estimated_shift_ppm is None
        ):
            raise ValueError("evaluated shifts require an estimate")
        return self


class PtmLocalizationAppliedSupportAdjustment(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0506_MAX_STAGES)
    factor: PtmLocalizationNormalizationFactor
    level_id: Identifier
    shift_ppm: int = Field(ge=-M0506_RATE_SCALE, le=M0506_RATE_SCALE)


class PtmLocalizationHarmonizedValue(FrozenModel):
    target_id: Identifier
    unit_kind: PtmLocalizationEvidenceUnitKind
    input_state: PtmLocalizationSupportObservationState
    output_state: PtmLocalizationSupportObservationState
    input_coordinate_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    harmonized_coordinate_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    censoring_upper_bound_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    source_observation_digest: Sha256Digest
    applied_adjustments: tuple[PtmLocalizationAppliedSupportAdjustment, ...] = Field(
        default=(), max_length=M0506_MAX_STAGES
    )


class PtmLocalizationHarmonizedAnalysis(FrozenModel):
    analysis_id: Identifier
    values: tuple[PtmLocalizationHarmonizedValue, ...] = Field(
        min_length=1, max_length=M0506_MAX_OBSERVATIONS
    )
    source_ledger_digest: Sha256Digest
    analysis_digest: Sha256Digest


class PtmLocalizationStageTransformation(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0506_MAX_STAGES)
    factor: PtmLocalizationNormalizationFactor
    reference_level_id: Identifier
    level_shifts: tuple[PtmLocalizationSupportLevelShift, ...] = Field(
        default=(), max_length=M0506_MAX_LEVELS_PER_FACTOR
    )


class PtmLocalizationTransformationManifest(FrozenModel):
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    stages: tuple[PtmLocalizationStageTransformation, ...] = Field(
        min_length=M0506_MAX_STAGES, max_length=M0506_MAX_STAGES
    )
    manifest_digest: Sha256Digest


class PtmLocalizationTechnicalEffectDiagnostic(FrozenModel):
    stage_id: Identifier
    factor: PtmLocalizationNormalizationFactor
    status: PtmLocalizationHarmonizationDiagnosticStatus
    before_spread_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    after_spread_ppm: int | None = Field(default=None, ge=0, le=M0506_RATE_SCALE)
    tolerance_ppm: int = Field(ge=0, le=M0506_RATE_SCALE)


class PtmLocalizationInvariantDiagnostic(FrozenModel):
    invariant_id: Identifier
    kind: PtmLocalizationSupportInvariantKind
    status: PtmLocalizationHarmonizationDiagnosticStatus


class PtmLocalizationHarmonizationFinding(FrozenModel):
    finding_id: Identifier
    code: PtmLocalizationHarmonizationFindingCode
    action: PtmLocalizationHarmonizationFindingAction
    message: str
    target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0506_MAX_TARGETS)

    @model_validator(mode="after")
    def finding_is_closed(self) -> PtmLocalizationHarmonizationFinding:
        _opaque(self.finding_id, "evidence", "finding")
        if self.action is not _FINDING_ACTION[self.code]:
            raise ValueError("finding action contradicts its code")
        return self


class PtmLocalizationHarmonizationComputationReceipt(FrozenModel):
    artifact_result_digest: Sha256Digest
    artifact_receipt_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    profile_digest: Sha256Digest | None
    analysis_digest: Sha256Digest | None
    transformation_manifest_digest: Sha256Digest | None
    finding_codes: tuple[PtmLocalizationHarmonizationFindingCode, ...] = Field(
        default=(), max_length=M0506_MAX_FINDINGS
    )
    disposition: PtmLocalizationHarmonizationDisposition
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_digest_is_current(self) -> PtmLocalizationHarmonizationComputationReceipt:
        from glio_proteogen.contracts.m05_06.canonical import computation_receipt_digest

        if self.receipt_digest != computation_receipt_digest(self):
            raise ValueError("computation receipt digest is stale")
        return self


class PtmLocalizationHarmonizationResult(FrozenModel):
    output_type: Literal["ptm_localization_harmonized_analysis"] = (
        "ptm_localization_harmonized_analysis"
    )
    result_id: Identifier
    result_version: Literal["1.0.0-provisional"] = M0506_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: HarmonizePtmLocalizationAnalysisRequest
    receipt: PtmLocalizationHarmonizationComputationReceipt
    analysis: PtmLocalizationHarmonizedAnalysis | None
    transformation_manifest: PtmLocalizationTransformationManifest | None
    technical_effect_diagnostics: tuple[PtmLocalizationTechnicalEffectDiagnostic, ...] = Field(
        default=(), max_length=M0506_MAX_STAGES
    )
    invariant_diagnostics: tuple[PtmLocalizationInvariantDiagnostic, ...] = Field(
        default=(), max_length=M0506_MAX_INVARIANTS
    )
    findings: tuple[PtmLocalizationHarmonizationFinding, ...] = Field(
        default=(), max_length=M0506_MAX_FINDINGS
    )
    disposition: PtmLocalizationHarmonizationDisposition
    parent_target: Literal["variant_peptide"] = M0506_PARENT
    emits_variant_peptide: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=7, max_length=M0506_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("result_id")
    @classmethod
    def result_id_is_opaque(cls, value: Identifier) -> Identifier:
        if not value.startswith("result."):
            raise ValueError("result identifier must be opaque")
        return value

    @model_validator(mode="after")
    def result_is_closed(self) -> PtmLocalizationHarmonizationResult:
        from glio_proteogen.contracts.m05_06.canonical import (
            canonical_request_digest,
            configuration_digest,
            policy_digest,
            result_payload_digest,
        )

        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest is stale")
        if self.policy_digest != policy_digest(
            self.request.policy
        ) or self.configuration_digest != configuration_digest(self.request.policy):
            raise ValueError("result policy/configuration digest is stale")
        if self.receipt.artifact_result_digest != self.request.artifact_result.result_digest:
            raise ValueError("result receipt does not bind the complete M05-05 result")
        matching_profiles = tuple(
            profile
            for profile in self.request.policy.profiles
            if M0505_CONTRACT_VERSION in profile.approved_artifact_contract_versions
        )
        expected_profile_digest = sha256_digest(matching_profiles[0]) if matching_profiles else None
        expected_receipt_bindings = (
            (self.receipt.artifact_receipt_digest, self.request.artifact_receipt.receipt_digest),
            (self.receipt.policy_digest, self.policy_digest),
            (self.receipt.configuration_digest, self.configuration_digest),
            (self.receipt.disposition, self.disposition),
            (self.receipt.finding_codes, tuple(item.code for item in self.findings)),
            (
                self.receipt.analysis_digest,
                self.analysis.analysis_digest if self.analysis is not None else None,
            ),
            (
                self.receipt.transformation_manifest_digest,
                self.transformation_manifest.manifest_digest
                if self.transformation_manifest is not None
                else None,
            ),
            (
                self.receipt.profile_digest,
                expected_profile_digest,
            ),
        )
        if any(actual != expected for actual, expected in expected_receipt_bindings):
            raise ValueError("result receipt does not bind the complete harmonization output")
        if self.disposition is PtmLocalizationHarmonizationDisposition.ACCEPTED and (
            self.analysis is None or self.transformation_manifest is None
        ):
            raise ValueError("accepted result requires analysis and transformation manifest")
        if self.disposition is not PtmLocalizationHarmonizationDisposition.ACCEPTED and (
            self.analysis is not None or self.transformation_manifest is not None
        ):
            raise ValueError("quarantined or abstained result cannot emit harmonized output")
        if self.human_review_required != (
            self.disposition is not PtmLocalizationHarmonizationDisposition.ACCEPTED
        ):
            raise ValueError("human-review state contradicts disposition")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not bind the canonical result payload")
        if len(canonical_json_bytes(self)) > M0506_MAX_CANONICAL_RESULT_BYTES:
            raise ValueError("canonical M05-06 result exceeds the output ceiling")
        return self


def expected_control_decisions(context: ExecutionContext) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
    entries = (
        (ControlRole.APPROVED_CONFIGURATION, refs.approved_configuration, None),
        (ControlRole.IDENTITY_LINEAGE, refs.identity_lineage, refs.identity_lineage.binding_digest),
        (ControlRole.PROVENANCE, refs.provenance, None),
        (ControlRole.CONSENT, refs.consent, None),
        (ControlRole.QUALITY, refs.quality, None),
        (ControlRole.SUPPORT, refs.support, None),
        (ControlRole.INTENDED_USE, refs.intended_use, None),
    )
    return tuple(
        ControlDecisionRecord(
            role=role,
            decision_id=reference.decision_id,
            state=reference.state.value,
            policy_version=reference.policy_version,
            evidence_digest=reference.evidence.digest,
            subject_digest=subject,
        )
        for role, reference, subject in entries
    )


def expected_provenance(
    request: HarmonizePtmLocalizationAnalysisRequest,
    request_digest: Sha256Digest,
    configuration_digest: Sha256Digest,
    input_digests: tuple[Sha256Digest, ...],
) -> ProvenanceRecord:
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m0506.{request_digest.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0506_MODULE_ID,
        module_version=M0506_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(set(input_digests))),
        configuration_digest=configuration_digest,
        consent_decision_id=refs.consent.decision_id,
        consent_state=refs.consent.state,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=expected_control_decisions(request.context),
    )


def expected_uncertainty() -> UncertaintyProfile:
    def unavailable(rationale: str) -> UncertaintyEstimate:
        return UncertaintyEstimate(state=EstimateState.NOT_ESTIMABLE, rationale=rationale)

    return UncertaintyProfile(
        measurement=unavailable(M0506_UNCERTAINTY_RATIONALES[0]),
        sampling=unavailable(M0506_UNCERTAINTY_RATIONALES[1]),
        parameter=unavailable(M0506_UNCERTAINTY_RATIONALES[2]),
        model_form=unavailable(M0506_UNCERTAINTY_RATIONALES[3]),
        identification=unavailable(M0506_UNCERTAINTY_RATIONALES[4]),
        support=unavailable(M0506_UNCERTAINTY_RATIONALES[5]),
        transport=unavailable(M0506_UNCERTAINTY_RATIONALES[6]),
        sensitivity_notes=(
            "Missing, censored, unsupported, and artifact-held support remains explicitly typed.",
            "No correction is applied to a target that M05-05 did not clear.",
            "Support coordinates are not abundance values or calibrated probabilities.",
        ),
    )


__all__ = [name for name in globals() if name.startswith("M0506_")] + [
    "HarmonizePtmLocalizationAnalysisRequest",
    "PtmLocalizationHarmonizationResult",
    "PtmLocalizationAppliedSupportAdjustment",
    "PtmLocalizationArtifactAction",
    "PtmLocalizationArtifactEvaluationState",
    "PtmLocalizationArtifactHarmonizationReceipt",
    "PtmLocalizationArtifactTargetReceipt",
    "PtmLocalizationArtifactTargetState",
    "PtmLocalizationHarmonizationComputationReceipt",
    "PtmLocalizationHarmonizationDisposition",
    "PtmLocalizationHarmonizationFinding",
    "PtmLocalizationHarmonizationFindingAction",
    "PtmLocalizationHarmonizationFindingCode",
    "PtmLocalizationHarmonizationProfile",
    "PtmLocalizationHarmonizationPolicy",
    "PtmLocalizationHarmonizedAnalysis",
    "PtmLocalizationHarmonizedValue",
    "PtmLocalizationHarmonizationDiagnosticStatus",
    "PtmLocalizationInvariantDiagnostic",
    "PtmLocalizationNormalizationFactor",
    "PtmLocalizationNormalizationFactorLevel",
    "PtmLocalizationNormalizationStage",
    "PtmLocalizationStageTransformation",
    "PtmLocalizationSupportInvariant",
    "PtmLocalizationSupportInvariantKind",
    "PtmLocalizationSupportLedger",
    "PtmLocalizationSupportLevelShift",
    "PtmLocalizationSupportObservation",
    "PtmLocalizationSupportObservationState",
    "PtmLocalizationSupportShiftState",
    "PtmLocalizationTechnicalEffectDiagnostic",
    "PtmLocalizationTransformationManifest",
    "expected_control_decisions",
    "expected_provenance",
    "expected_uncertainty",
    "opaque_harmonization_identifier",
]
