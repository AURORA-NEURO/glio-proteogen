"""Strict M04-06 proteoform harmonization and normalization contracts.

M04-06 consumes the complete replay-closed M04-05 result and a caller-declared,
content-addressed fixed-point analysis ledger. It emits only a harmonized
analysis object and its transformation manifest. It never mutates upstream
evidence, manufactures missing support, or infers proteoforms, kinase state,
protein-RNA discordance, treatment, identity, or consent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m04_01 import (  # noqa: TC001 - Pydantic resolves at runtime
    ProteoformApplicability,
)
from glio_proteogen.contracts.m04_05 import (
    ProteoformArtifactDetectionResult,
    ProteoformArtifactDetectorClass,
    ProteoformArtifactDisposition,
    ProteoformArtifactObservationState,
    ProteoformArtifactPosterior,
    ProteoformArtifactPosteriorState,
    ProteoformEvidenceUnitKind,
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
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0406_MODULE_ID: Final = "GLIO-PROTEOGEN-M04-06"
M0406_OPERATION: Final = "harmonize_proteoform_analysis"
M0406_CONTRACT_VERSION: Final = "1.0.0"
M0406_PARENT: Final = "protein_rna_discordance"
M0406_OWNER: Final = "Scientific engineering"
M0406_SAFETY_CLASS: Final = "S2"
M0406_GATE: Final = "G1"
M0406_RATE_SCALE: Final = 1_000_000
M0406_MAX_RESIDUAL_PPM: Final = 2 * M0406_RATE_SCALE
M0406_FACTOR_COUNT: Final = 8
M0406_UPSTREAM_DETECTOR_COUNT: Final = 7
M0406_MAX_STAGES: Final = 8
M0406_MAX_TARGETS: Final = 512
M0406_MAX_OBSERVATIONS: Final = 512
M0406_MAX_LEVELS_PER_FACTOR: Final = 64
M0406_MAX_LEVEL_SHIFTS: Final = M0406_MAX_STAGES * M0406_MAX_LEVELS_PER_FACTOR
M0406_MAX_STAGE_ESTIMATION_ANCHORS: Final = 128
M0406_MAX_STAGE_VALIDATION_ANCHORS: Final = 128
M0406_MAX_INVARIANTS: Final = 256
M0406_MAX_INVARIANT_TARGET_REFS: Final = 64
M0406_MAX_EVIDENCE_PER_OBSERVATION: Final = 8
M0406_MAX_APPLIED_ADJUSTMENTS: Final = M0406_MAX_OBSERVATIONS * M0406_MAX_STAGES
M0406_MAX_PROFILES: Final = 16
M0406_MAX_APPROVED_VERSIONS: Final = 32
M0406_MAX_EVIDENCE: Final = 16
M0406_MAX_FINDINGS: Final = 14
M0406_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
_M0406_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIN_FACTOR_LEVELS: Final = 2
_M0405_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m04-05+json"
ProteoformHarmonizationIdentifierNamespace = Literal[
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
]
_OPAQUE_IDENTIFIER_PATTERN: Final = re.compile(
    r"^(request|policy|profile|ledger|target|anchor|group|level|invariant|stage|evidence|reviewer)"
    r"\.[0-9a-f]{64}$"
)
_LOWERCASE_MEDIA_TYPE_PATTERN: Final = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$"
)
_UPSTREAM_FLAG_ID_PATTERN: Final = re.compile(r"^flag\.[0-9a-f]{64}$")
M0406_HARMONIZATION_LIMITATION_CODE: Final = "proteoform_harmonization_only"
M0406_SCALE_LIMITATION_CODE: Final = "analysis_coordinate_not_abundance_or_probability"
M0406_AUTHORITY_LIMITATION_CODE: Final = "upstream_result_replay_not_issuer_authentication"
M0406_EVIDENCE_CLAIM: Final = "Caller-declared content-addressed proteoform harmonization evidence."
M0406_SENSITIVITY_NOTES: Final = (
    "Missing, censored, unsupported, and not-applicable support remains explicitly typed.",
    "Artifact-review and artifact-excluded targets never train or receive a correction.",
    "Fixed-point support coordinates are not abundance values or calibrated probabilities.",
)
M0406_UNCERTAINTY_RATIONALES: Final = (
    "Measurement uncertainty is not estimated from caller-declared support coordinates.",
    "Sampling uncertainty is not estimated by deterministic paired normalization.",
    "The lower-median fixed-point evaluator fits no probabilistic parameters.",
    "No masked foundation model, autoencoder, or cross-attention model is executed.",
    (
        "Protein/proteoform identity, protein-RNA discordance, and kinase state remain outside "
        "this module."
    ),
    "Support is limited to reviewed technical factors and declared protected invariants.",
    "Transportability requires external assay, cohort, and control-panel validation.",
)


def opaque_harmonization_identifier(
    namespace: ProteoformHarmonizationIdentifierNamespace,
    value: object,
) -> Identifier:
    """Return one namespaced opaque identifier derived from canonical content."""

    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def _opaque_identifier(
    value: Identifier,
    namespace: ProteoformHarmonizationIdentifierNamespace,
    label: str,
) -> Identifier:
    prefix = f"{namespace}."
    if not value.startswith(prefix) or _OPAQUE_IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a content-derived opaque {prefix} identifier")
    return value


def _validate_owned_evidence_reference(
    value: ArtifactReference,
    label: str,
) -> ArtifactReference:
    _opaque_identifier(value.artifact_id, "evidence", f"{label} artifact identifier")
    if _LOWERCASE_MEDIA_TYPE_PATTERN.fullmatch(value.media_type) is None:
        raise ValueError(f"{label} media type must use strict lowercase type/subtype syntax")
    return value


class ProteoformNormalizationFactor(StrEnum):
    PLATFORM = "platform"
    BATCH = "batch"
    LABORATORY = "laboratory"
    BUILD = "build"
    DEPTH = "depth"
    PURITY = "purity"
    COMPOSITION = "composition"
    PREANALYTIC = "preanalytic"


class ProteoformSupportObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    CENSORED = "censored"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ProteoformArtifactTargetState(StrEnum):
    """Aggregate M04-05 target state; absence of a flag never implies ``clear``."""

    CLEAR = "clear"
    REVIEW = "review"
    INDETERMINATE = "indeterminate"
    EXCLUDED = "excluded"


class ProteoformArtifactAction(StrEnum):
    RETAIN = "retain"
    REVIEW = "review"
    EXCLUDE = "exclude"


class ProteoformArtifactEvaluationState(StrEnum):
    COMPLETE = "complete"
    NOT_EVALUABLE = "not_evaluable"


class ProteoformSupportShiftState(StrEnum):
    ESTIMATED = "estimated"
    CAPPED = "capped"
    NOT_EVALUABLE = "not_evaluable"


class ProteoformHarmonizationDiagnosticStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class ProteoformSupportInvariantKind(StrEnum):
    SUPPORT_DIRECTION = "support_direction"
    SUPPORT_RANK = "support_rank"
    COMPOSITION_FRACTION = "composition_fraction"


class ProteoformHarmonizationDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class ProteoformHarmonizationFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class ProteoformHarmonizationFindingCode(StrEnum):
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
    ProteoformHarmonizationFindingCode.UPSTREAM_QUARANTINED: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
    ProteoformHarmonizationFindingCode.UPSTREAM_ABSTAINED: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
    ProteoformHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
    ProteoformHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.SHIFT_CAPPED: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
    ProteoformHarmonizationFindingCode.VALUE_CLIPPED: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
    ProteoformHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
    ProteoformHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE: (
        ProteoformHarmonizationFindingAction.ABSTAIN
    ),
    ProteoformHarmonizationFindingCode.INVARIANT_VIOLATED: (
        ProteoformHarmonizationFindingAction.QUARANTINE
    ),
}

_FINDING_MESSAGE: Final = {
    ProteoformHarmonizationFindingCode.UPSTREAM_QUARANTINED: (
        "M04-05 quarantined the proteoform artifact evaluation."
    ),
    ProteoformHarmonizationFindingCode.UPSTREAM_ABSTAINED: (
        "M04-05 abstained from a proteoform artifact evaluation."
    ),
    ProteoformHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        "The projected M04-05 target graph exceeds the reviewed harmonization envelope."
    ),
    ProteoformHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH: (
        "The support ledger does not bind the exact compact M04-05 target projection."
    ),
    ProteoformHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED: (
        "No reviewed proteoform harmonization profile applies."
    ),
    ProteoformHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT: (
        "At least one M04-05 target remains excluded from harmonization."
    ),
    ProteoformHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED: (
        "At least one M04-05 target remains held for review."
    ),
    ProteoformHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE: (
        "At least one retained support coordinate is not evaluable."
    ),
    ProteoformHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT: (
        "At least one technical level lacks reviewed estimation or validation pairs."
    ),
    ProteoformHarmonizationFindingCode.SHIFT_CAPPED: (
        "At least one estimated technical shift reached its reviewed cap."
    ),
    ProteoformHarmonizationFindingCode.VALUE_CLIPPED: (
        "At least one adjusted support coordinate reached the fixed-point boundary."
    ),
    ProteoformHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED: (
        "At least one held-out technical residual did not meet its reduction criterion."
    ),
    ProteoformHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE: (
        "At least one protected support invariant is not evaluable."
    ),
    ProteoformHarmonizationFindingCode.INVARIANT_VIOLATED: (
        "At least one protected support invariant was violated."
    ),
}


class ProteoformNormalizationFactorLevel(FrozenModel):
    factor: ProteoformNormalizationFactor
    level_id: Identifier

    @field_validator("level_id")
    @classmethod
    def level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "factor-level identifier")


class ProteoformArtifactTargetReceipt(FrozenModel):
    target_id: Identifier
    unit_kind: ProteoformEvidenceUnitKind
    target_state: ProteoformArtifactTargetState
    action: ProteoformArtifactAction
    posterior_digests: tuple[Sha256Digest, ...] = Field(
        min_length=M0406_UPSTREAM_DETECTOR_COUNT,
        max_length=M0406_UPSTREAM_DETECTOR_COUNT,
    )
    posterior_binding_digest: Sha256Digest
    contamination_flag_ids: tuple[Identifier, ...] = Field(
        default=(),
        max_length=M0406_UPSTREAM_DETECTOR_COUNT,
    )
    excluded: bool

    @field_validator("target_id")
    @classmethod
    def target_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "target", "artifact-target identifier")

    @field_validator("posterior_digests")
    @classmethod
    def posterior_digests_are_canonical(
        cls,
        values: tuple[Sha256Digest, ...],
    ) -> tuple[Sha256Digest, ...]:
        if len(values) != len(set(values)):
            raise ValueError("artifact-target posterior digests must be unique")
        return tuple(sorted(values))

    @field_validator("contamination_flag_ids")
    @classmethod
    def flag_identifiers_are_upstream_opaque(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)) or any(
            _UPSTREAM_FLAG_ID_PATTERN.fullmatch(value) is None for value in values
        ):
            raise ValueError("contamination flags must preserve exact opaque M04-05 identifiers")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def action_matches_target_state(self) -> ProteoformArtifactTargetReceipt:
        expected = {
            ProteoformArtifactTargetState.CLEAR: ProteoformArtifactAction.RETAIN,
            ProteoformArtifactTargetState.REVIEW: ProteoformArtifactAction.REVIEW,
            ProteoformArtifactTargetState.INDETERMINATE: ProteoformArtifactAction.REVIEW,
            ProteoformArtifactTargetState.EXCLUDED: ProteoformArtifactAction.EXCLUDE,
        }[self.target_state]
        if (
            self.action is not expected
            or self.excluded != (self.action is ProteoformArtifactAction.EXCLUDE)
            or (
                self.target_state
                in {
                    ProteoformArtifactTargetState.CLEAR,
                    ProteoformArtifactTargetState.INDETERMINATE,
                }
                and self.contamination_flag_ids
            )
            or self.posterior_binding_digest != sha256_digest(self.posterior_digests)
        ):
            raise ValueError("artifact target receipt contradicts its exact M04-05 projection")
        return self


class ProteoformArtifactHarmonizationReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = M0406_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    artifact_result_digest: Sha256Digest
    artifact_request_digest: Sha256Digest
    artifact_policy_digest: Sha256Digest
    artifact_configuration_digest: Sha256Digest
    artifact_disposition: ProteoformArtifactDisposition
    artifact_support_status: SupportStatus
    artifact_human_review_required: bool
    artifact_completed_at: AwareDatetime
    quality_receipt_digest: Sha256Digest
    evidence_ledger_digest: Sha256Digest | None = None
    selected_profile_digest: Sha256Digest | None = None
    quality_result_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    coordinate_policy_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    applicability: ProteoformApplicability | None = None
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    evaluation_state: ProteoformArtifactEvaluationState
    target_count: int = Field(ge=0, le=M0406_MAX_TARGETS)
    targets: tuple[ProteoformArtifactTargetReceipt, ...] = Field(
        default=(), max_length=M0406_MAX_TARGETS
    )
    target_binding_digest: Sha256Digest
    receipt_digest: Sha256Digest

    @field_validator("targets")
    @classmethod
    def units_are_canonical(
        cls,
        values: tuple[ProteoformArtifactTargetReceipt, ...],
    ) -> tuple[ProteoformArtifactTargetReceipt, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_closed(self) -> ProteoformArtifactHarmonizationReceipt:
        from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
            artifact_receipt_digest,
            target_binding_digest,
        )

        target_ids = tuple(item.target_id for item in self.targets)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("artifact harmonization receipt target identifiers must be unique")
        complete = self.evaluation_state is ProteoformArtifactEvaluationState.COMPLETE
        if complete:
            if (
                not self.targets
                or len(self.targets) != self.target_count
                or self.evidence_ledger_digest is None
                or self.selected_profile_digest is None
                or self.applicability is None
            ):
                raise ValueError(
                    "complete artifact receipt requires its exact screened target graph"
                )
            expected_disposition = (
                ProteoformArtifactDisposition.QUARANTINED
                if any(
                    item.target_state
                    in {
                        ProteoformArtifactTargetState.REVIEW,
                        ProteoformArtifactTargetState.EXCLUDED,
                    }
                    for item in self.targets
                )
                else ProteoformArtifactDisposition.ABSTAINED
                if any(
                    item.target_state is ProteoformArtifactTargetState.INDETERMINATE
                    for item in self.targets
                )
                else ProteoformArtifactDisposition.CLEARED
            )
            if self.artifact_disposition is not expected_disposition:
                raise ValueError("artifact receipt disposition contradicts its target posteriors")
        elif self.targets or self.target_count != 0:
            raise ValueError("non-evaluable artifact receipt cannot project successful targets")
        if self.artifact_disposition is ProteoformArtifactDisposition.CLEARED and not complete:
            raise ValueError("cleared artifact receipt must carry a complete screen")
        expected_support = {
            ProteoformArtifactDisposition.CLEARED: SupportStatus.SUPPORTED,
            ProteoformArtifactDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
            ProteoformArtifactDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
        }[self.artifact_disposition]
        if self.artifact_support_status is not expected_support:
            raise ValueError("artifact receipt disposition and support status contradict")
        if self.artifact_human_review_required != (
            self.artifact_disposition is not ProteoformArtifactDisposition.CLEARED
        ):
            raise ValueError("artifact receipt disposition and review requirement contradict")
        expected_artifact_id = (
            f"result.m0405.{self.artifact_request_digest.removeprefix('sha256:')}"
        )
        if (
            self.artifact_reference.artifact_id != expected_artifact_id
            or self.artifact_reference.version != "1.0.0"
            or self.artifact_reference.media_type != _M0405_RESULT_MEDIA_TYPE
        ):
            raise ValueError("artifact reference does not identify the exact M04-05 result ABI")
        if (
            self.artifact_reference.digest != self.artifact_result_digest
            or self.target_binding_digest != target_binding_digest(self.targets)
            or self.receipt_digest != artifact_receipt_digest(self)
        ):
            raise ValueError("artifact harmonization receipt digest closure failed")
        return self


class ProteoformSupportObservation(FrozenModel):
    target_id: Identifier
    unit_kind: ProteoformEvidenceUnitKind
    artifact_target_state: ProteoformArtifactTargetState
    artifact_action: ProteoformArtifactAction
    artifact_posterior_digests: tuple[Sha256Digest, ...] = Field(
        min_length=M0406_UPSTREAM_DETECTOR_COUNT,
        max_length=M0406_UPSTREAM_DETECTOR_COUNT,
    )
    artifact_posterior_binding_digest: Sha256Digest
    artifact_contamination_flag_ids: tuple[Identifier, ...] = Field(
        default=(),
        max_length=M0406_UPSTREAM_DETECTOR_COUNT,
    )
    artifact_excluded: bool
    anchor_id: Identifier
    biological_group_id: Identifier
    state: ProteoformSupportObservationState
    support_coordinate_ppm: int | None = Field(default=None, ge=0, le=M0406_RATE_SCALE)
    censoring_upper_bound_ppm: int | None = Field(default=None, ge=0, le=M0406_RATE_SCALE)
    is_calibrated_probability: Literal[False] = False
    factor_levels: tuple[ProteoformNormalizationFactorLevel, ...] = Field(
        min_length=M0406_FACTOR_COUNT,
        max_length=M0406_FACTOR_COUNT,
    )
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_EVIDENCE_PER_OBSERVATION,
    )

    @field_validator("target_id")
    @classmethod
    def target_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "target", "support-observation unit identifier")

    @field_validator("anchor_id")
    @classmethod
    def anchor_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "anchor", "support-observation anchor identifier")

    @field_validator("biological_group_id")
    @classmethod
    def group_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "group", "support-observation group identifier")

    @field_validator(
        "artifact_posterior_digests",
        "artifact_contamination_flag_ids",
        "factor_levels",
        "evidence",
    )
    @classmethod
    def collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("evidence")
    @classmethod
    def evidence_references_are_opaque(
        cls,
        values: tuple[ArtifactReference, ...],
    ) -> tuple[ArtifactReference, ...]:
        for value in values:
            _validate_owned_evidence_reference(value, "support-observation evidence")
        return values

    @model_validator(mode="after")
    def observation_is_typed_and_closed(self) -> ProteoformSupportObservation:
        factors = tuple(item.factor for item in self.factor_levels)
        if len(factors) != len(set(factors)) or set(factors) != set(ProteoformNormalizationFactor):
            raise ValueError("support observation requires every technical factor exactly once")
        if len({item.digest for item in self.evidence}) != len(self.evidence):
            raise ValueError("support observation evidence digests must be unique")
        expected_action = {
            ProteoformArtifactTargetState.CLEAR: ProteoformArtifactAction.RETAIN,
            ProteoformArtifactTargetState.REVIEW: ProteoformArtifactAction.REVIEW,
            ProteoformArtifactTargetState.INDETERMINATE: ProteoformArtifactAction.REVIEW,
            ProteoformArtifactTargetState.EXCLUDED: ProteoformArtifactAction.EXCLUDE,
        }[self.artifact_target_state]
        if (
            self.artifact_action is not expected_action
            or self.artifact_excluded != (self.artifact_action is ProteoformArtifactAction.EXCLUDE)
            or self.artifact_posterior_binding_digest
            != sha256_digest(self.artifact_posterior_digests)
            or (
                self.artifact_target_state
                in {
                    ProteoformArtifactTargetState.CLEAR,
                    ProteoformArtifactTargetState.INDETERMINATE,
                }
                and self.artifact_contamination_flag_ids
            )
            or any(
                _UPSTREAM_FLAG_ID_PATTERN.fullmatch(value) is None
                for value in self.artifact_contamination_flag_ids
            )
        ):
            raise ValueError("support observation contradicts its artifact-target receipt")
        if self.state is ProteoformSupportObservationState.OBSERVED:
            if self.support_coordinate_ppm is None or self.censoring_upper_bound_ppm is not None:
                raise ValueError("observed support requires only its fixed-point coordinate")
        elif self.state is ProteoformSupportObservationState.CENSORED:
            if self.support_coordinate_ppm is not None or self.censoring_upper_bound_ppm is None:
                raise ValueError("censored support requires only its upper bound")
        elif self.support_coordinate_ppm is not None or self.censoring_upper_bound_ppm is not None:
            raise ValueError("non-observed support cannot carry a numeric coordinate")
        return self


class ProteoformSupportInvariant(FrozenModel):
    invariant_id: Identifier
    kind: ProteoformSupportInvariantKind
    left_target_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_INVARIANT_TARGET_REFS,
    )
    right_target_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_INVARIANT_TARGET_REFS,
    )

    @field_validator("invariant_id")
    @classmethod
    def invariant_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "invariant", "support-invariant identifier")

    @field_validator("left_target_ids", "right_target_ids")
    @classmethod
    def members_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def member_shape_is_closed(self) -> ProteoformSupportInvariant:
        if self.kind is ProteoformSupportInvariantKind.SUPPORT_RANK and (
            len(self.left_target_ids) != 1 or len(self.right_target_ids) != 1
        ):
            raise ValueError("support-rank invariant requires exactly one unit per side")
        if (
            len(self.left_target_ids) != len(set(self.left_target_ids))
            or len(self.right_target_ids) != len(set(self.right_target_ids))
            or set(self.left_target_ids) & set(self.right_target_ids)
        ):
            raise ValueError("support invariant sides must be unique and disjoint")
        return self


def _target_receipt_from_observation(
    observation: ProteoformSupportObservation,
) -> ProteoformArtifactTargetReceipt:
    return ProteoformArtifactTargetReceipt(
        target_id=observation.target_id,
        unit_kind=observation.unit_kind,
        target_state=observation.artifact_target_state,
        action=observation.artifact_action,
        posterior_digests=observation.artifact_posterior_digests,
        posterior_binding_digest=observation.artifact_posterior_binding_digest,
        contamination_flag_ids=observation.artifact_contamination_flag_ids,
        excluded=observation.artifact_excluded,
    )


class ProteoformSupportLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    artifact_result_digest: Sha256Digest
    artifact_receipt_digest: Sha256Digest
    artifact_target_binding_digest: Sha256Digest
    observations: tuple[ProteoformSupportObservation, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_OBSERVATIONS,
    )
    invariants: tuple[ProteoformSupportInvariant, ...] = Field(
        min_length=3,
        max_length=M0406_MAX_INVARIANTS,
    )
    evidence: ArtifactReference
    recorded_at: AwareDatetime
    ledger_digest: Sha256Digest

    @field_validator("ledger_id")
    @classmethod
    def ledger_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "ledger", "support-ledger identifier")

    @field_validator("evidence")
    @classmethod
    def evidence_reference_is_opaque(cls, value: ArtifactReference) -> ArtifactReference:
        return _validate_owned_evidence_reference(value, "support-ledger evidence")

    @field_validator("observations", "invariants")
    @classmethod
    def ledger_collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def ledger_is_content_addressed_and_relationally_closed(
        self,
    ) -> ProteoformSupportLedger:
        from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
            support_ledger_digest,
            target_binding_digest,
        )

        target_ids = tuple(item.target_id for item in self.observations)
        invariant_ids = tuple(item.invariant_id for item in self.invariants)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("support observation target identifiers must be unique")
        if {item.kind for item in self.invariants} != set(ProteoformSupportInvariantKind):
            raise ValueError("support ledger requires every protected invariant kind")
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("support invariant identifiers must be unique")
        projected = tuple(_target_receipt_from_observation(item) for item in self.observations)
        if self.artifact_target_binding_digest != target_binding_digest(projected):
            raise ValueError("support ledger unit binding does not match its observations")
        _validate_invariant_members(self.observations, self.invariants)
        if self.ledger_digest != support_ledger_digest(self):
            raise ValueError("support ledger digest does not match its content")
        return self


def _validate_invariant_members(
    observations: tuple[ProteoformSupportObservation, ...],
    invariants: tuple[ProteoformSupportInvariant, ...],
) -> None:
    by_id = {item.target_id: item for item in observations}
    for invariant in invariants:
        members = set(invariant.left_target_ids) | set(invariant.right_target_ids)
        if not members.issubset(by_id):
            raise ValueError("support invariant references an unknown target")
        left = tuple(by_id[item] for item in invariant.left_target_ids)
        right = tuple(by_id[item] for item in invariant.right_target_ids)
        if invariant.kind is ProteoformSupportInvariantKind.SUPPORT_DIRECTION:
            left_groups = {item.biological_group_id for item in left}
            right_groups = {item.biological_group_id for item in right}
            left_keys = {(item.anchor_id, item.unit_kind) for item in left}
            right_keys = {(item.anchor_id, item.unit_kind) for item in right}
            if (
                len(left_groups) != 1
                or len(right_groups) != 1
                or left_groups == right_groups
                or len(left_keys) != len(left)
                or len(right_keys) != len(right)
                or left_keys != right_keys
            ):
                raise ValueError(
                    "support-direction invariant requires matched anchors across groups"
                )
        elif invariant.kind is ProteoformSupportInvariantKind.SUPPORT_RANK:
            if (
                left[0].biological_group_id != right[0].biological_group_id
                or left[0].unit_kind is not right[0].unit_kind
                or left[0].anchor_id == right[0].anchor_id
            ):
                raise ValueError("support-rank invariant requires distinct anchors in one context")
        else:
            groups = {item.biological_group_id for item in (*left, *right)}
            if (
                len(groups) != 1
                or {item.unit_kind for item in left}
                != {ProteoformEvidenceUnitKind.PROTEOFORM_CANDIDATE}
                or {item.unit_kind for item in right}
                != {ProteoformEvidenceUnitKind.SPECTRAL_FEATURE}
                or {item.anchor_id for item in left} != {item.anchor_id for item in right}
                or len({item.anchor_id for item in left}) != len(left)
                or len({item.anchor_id for item in right}) != len(right)
            ):
                raise ValueError(
                    "composition invariant requires matched candidate and spectral anchors"
                )


class ProteoformNormalizationStage(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0406_MAX_STAGES)
    factor: ProteoformNormalizationFactor
    reference_level_id: Identifier
    estimation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    validation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_STAGE_VALIDATION_ANCHORS,
    )

    @field_validator("stage_id")
    @classmethod
    def stage_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "stage", "normalization-stage identifier")

    @field_validator("reference_level_id")
    @classmethod
    def reference_level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "reference-level identifier")

    @field_validator("estimation_anchor_ids", "validation_anchor_ids")
    @classmethod
    def anchors_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "anchor", "normalization-stage anchor identifier")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def anchor_sets_are_disjoint(self) -> ProteoformNormalizationStage:
        if (
            len(self.estimation_anchor_ids) != len(set(self.estimation_anchor_ids))
            or len(self.validation_anchor_ids) != len(set(self.validation_anchor_ids))
            or set(self.estimation_anchor_ids) & set(self.validation_anchor_ids)
        ):
            raise ValueError("estimation and validation anchors must be unique and disjoint")
        return self


class ProteoformHarmonizationProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    applicability: ProteoformApplicability
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_APPROVED_VERSIONS,
    )
    approved_specimen_processing_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_APPROVED_VERSIONS,
    )
    approved_controlled_vocabulary_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_APPROVED_VERSIONS,
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_APPROVED_VERSIONS,
    )
    stages: tuple[ProteoformNormalizationStage, ...] = Field(
        min_length=M0406_MAX_STAGES,
        max_length=M0406_MAX_STAGES,
    )
    evidence: ArtifactReference

    @field_validator("profile_id")
    @classmethod
    def profile_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "profile", "harmonization-profile identifier")

    @field_validator("evidence")
    @classmethod
    def evidence_reference_is_opaque(cls, value: ArtifactReference) -> ArtifactReference:
        return _validate_owned_evidence_reference(value, "harmonization-profile evidence")

    @field_validator(
        "approved_assay_protocol_versions",
        "approved_specimen_processing_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    )
    @classmethod
    def version_domains_are_canonical(
        cls,
        values: tuple[SemanticVersion, ...],
    ) -> tuple[SemanticVersion, ...]:
        return tuple(sorted(values))

    @field_validator("stages")
    @classmethod
    def stages_are_ordered(
        cls,
        values: tuple[ProteoformNormalizationStage, ...],
    ) -> tuple[ProteoformNormalizationStage, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def profile_is_closed(self) -> ProteoformHarmonizationProfile:
        domains = (
            self.approved_assay_protocol_versions,
            self.approved_specimen_processing_versions,
            self.approved_controlled_vocabulary_versions,
            self.approved_unit_system_versions,
        )
        if any(len(values) != len(set(values)) for values in domains):
            raise ValueError("harmonization profile versions must be unique")
        if {item.factor for item in self.stages} != set(ProteoformNormalizationFactor):
            raise ValueError("harmonization profile requires every technical factor exactly once")
        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0406_MAX_STAGES + 1)):
            raise ValueError("harmonization stages require exact ordered ordinals")
        if len({item.stage_id for item in self.stages}) != len(self.stages):
            raise ValueError("harmonization stage identifiers must be unique")
        return self


class ProteoformHarmonizationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_targets: int = Field(gt=0, le=M0406_MAX_TARGETS)
    max_invariants: int = Field(ge=3, le=M0406_MAX_INVARIANTS)
    max_absolute_shift_ppm: int = Field(gt=0, le=M0406_RATE_SCALE)
    technical_effect_tolerance_ppm: int = Field(ge=0, le=M0406_RATE_SCALE)
    biological_invariant_tolerance_ppm: int = Field(ge=0, le=M0406_RATE_SCALE)
    min_estimation_pairs_per_level: int = Field(
        gt=0,
        le=M0406_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    min_validation_pairs_per_level: int = Field(
        gt=0,
        le=M0406_MAX_STAGE_VALIDATION_ANCHORS,
    )
    profiles: tuple[ProteoformHarmonizationProfile, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_PROFILES,
    )
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("policy_id")
    @classmethod
    def policy_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "policy", "harmonization-policy identifier")

    @field_validator("reviewed_by")
    @classmethod
    def reviewer_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "reviewer", "harmonization-policy reviewer identifier")

    @field_validator("evidence")
    @classmethod
    def evidence_reference_is_opaque(cls, value: ArtifactReference) -> ArtifactReference:
        return _validate_owned_evidence_reference(value, "harmonization-policy evidence")

    @field_validator("profiles")
    @classmethod
    def profiles_are_canonical(
        cls,
        values: tuple[ProteoformHarmonizationProfile, ...],
    ) -> tuple[ProteoformHarmonizationProfile, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def profile_domains_are_pairwise_disjoint(self) -> ProteoformHarmonizationPolicy:
        identities = tuple((item.profile_id, item.version) for item in self.profiles)
        if len(identities) != len(set(identities)):
            raise ValueError("harmonization profile identities must be unique")
        for index, left in enumerate(self.profiles):
            for right in self.profiles[index + 1 :]:
                overlaps = (
                    left.applicability is right.applicability
                    and bool(
                        set(left.approved_assay_protocol_versions)
                        & set(right.approved_assay_protocol_versions)
                    )
                    and bool(
                        set(left.approved_specimen_processing_versions)
                        & set(right.approved_specimen_processing_versions)
                    )
                    and bool(
                        set(left.approved_controlled_vocabulary_versions)
                        & set(right.approved_controlled_vocabulary_versions)
                    )
                    and bool(
                        set(left.approved_unit_system_versions)
                        & set(right.approved_unit_system_versions)
                    )
                )
                if overlaps:
                    raise ValueError("harmonization profile match domains must be disjoint")
        return self


def matching_harmonization_profile(
    request: HarmonizeProteoformAnalysisRequest,
) -> ProteoformHarmonizationProfile | None:
    receipt = request.artifact_receipt
    if receipt.applicability is None:
        return None
    matches = tuple(
        item
        for item in request.policy.profiles
        if item.applicability is receipt.applicability
        and receipt.assay_protocol_version in item.approved_assay_protocol_versions
        and receipt.specimen_processing_version in item.approved_specimen_processing_versions
        and receipt.controlled_vocabulary_version in item.approved_controlled_vocabulary_versions
        and receipt.unit_system_version in item.approved_unit_system_versions
    )
    return matches[0] if len(matches) == 1 else None


class HarmonizeProteoformAnalysisRequest(FrozenModel):
    operation: Literal["harmonize_proteoform_analysis"] = M0406_OPERATION
    contract_version: Literal["1.0.0"] = M0406_CONTRACT_VERSION
    context: ExecutionContext
    artifact_result: ProteoformArtifactDetectionResult
    artifact_receipt: ProteoformArtifactHarmonizationReceipt
    support_ledger: ProteoformSupportLedger | None = None
    policy: ProteoformHarmonizationPolicy
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_closed(self) -> HarmonizeProteoformAnalysisRequest:
        from glio_proteogen.contracts.m04_06.canonical import configuration_digest  # noqa: PLC0415

        _require_authorized_context(self.context)
        _opaque_identifier(
            self.context.request_id,
            "request",
            "harmonization request identifier",
        )
        receipt = self.artifact_receipt
        if receipt != artifact_harmonization_receipt(self.artifact_result):
            raise ValueError("artifact receipt must replay the exact embedded M04-05 result")
        refs = self.context.references
        upstream_refs = self.artifact_result.request.context.references
        if (
            refs.approved_configuration.state is not upstream_refs.approved_configuration.state
            or refs.identity_lineage != upstream_refs.identity_lineage
            or refs.provenance != upstream_refs.provenance
            or refs.consent != upstream_refs.consent
            or refs.quality != upstream_refs.quality
            or refs.support != upstream_refs.support
            or refs.intended_use != upstream_refs.intended_use
        ):
            raise ValueError(
                "M04-06 must preserve every M04-05 authority state and non-configuration region"
            )
        if max(receipt.artifact_completed_at, self.policy.reviewed_at) > self.context.occurred_at:
            raise ValueError("M04-06 inputs cannot postdate harmonization")
        if refs.identity_lineage.binding_digest != receipt.identity_resolution_digest:
            raise ValueError("identity control does not bind the compact M04-05 receipt")
        if refs.quality.evidence.digest != receipt.quality_result_digest:
            raise ValueError("quality control does not bind the exact M04-04 result")
        if refs.approved_configuration.evidence.digest != configuration_digest(self.policy):
            raise ValueError("approved configuration does not bind the harmonization policy")
        _validate_artifact_reference_consistency(self)
        supported_shape = (
            receipt.evaluation_state is ProteoformArtifactEvaluationState.COMPLETE
            and receipt.artifact_disposition is ProteoformArtifactDisposition.CLEARED
            and receipt.target_count <= self.policy.max_targets
        )
        if supported_shape != (self.support_ledger is not None):
            raise ValueError("support-ledger presence contradicts the traversal envelope")
        ledger = self.support_ledger
        if ledger is not None:
            if not receipt.artifact_completed_at <= ledger.recorded_at <= self.context.occurred_at:
                raise ValueError(
                    "support facts must follow artifact evaluation and precede execution"
                )
            if len(ledger.invariants) > self.policy.max_invariants:
                raise ValueError("support ledger exceeds the reviewed invariant ceiling")
            active = matching_harmonization_profile(self)
            if active is not None:
                _validate_active_profile_members(active, ledger)
        if len(canonical_json_bytes(self.model_dump(mode="python"))) > (
            M0406_MAX_CANONICAL_REQUEST_BYTES
        ):
            raise ValueError("canonical M04-06 request exceeds its ingress ceiling")
        return self


def _validate_active_profile_members(
    profile: ProteoformHarmonizationProfile,
    ledger: ProteoformSupportLedger,
) -> None:
    anchors = {item.anchor_id for item in ledger.observations}
    for stage in profile.stages:
        if not (set(stage.estimation_anchor_ids) | set(stage.validation_anchor_ids)).issubset(
            anchors
        ):
            raise ValueError("active harmonization stage references an unknown anchor")
        levels = {
            level.level_id
            for item in ledger.observations
            for level in item.factor_levels
            if level.factor is stage.factor
        }
        if (
            stage.reference_level_id not in levels
            or len(levels) < _MIN_FACTOR_LEVELS
            or len(levels) > M0406_MAX_LEVELS_PER_FACTOR
        ):
            raise ValueError("active harmonization stage has an invalid factor-level domain")


def _artifact_references(
    request: HarmonizeProteoformAnalysisRequest,
) -> tuple[ArtifactReference, ...]:
    refs = request.context.references
    values = [
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.artifact_receipt.artifact_reference,
        request.policy.evidence,
    ]
    values.extend(item.evidence for item in request.policy.profiles)
    if request.support_ledger is not None:
        values.append(request.support_ledger.evidence)
        values.extend(
            evidence
            for observation in request.support_ledger.observations
            for evidence in observation.evidence
        )
    return tuple(values)


def _validate_artifact_reference_consistency(
    request: HarmonizeProteoformAnalysisRequest,
) -> None:
    index: dict[tuple[Identifier, SemanticVersion], tuple[Sha256Digest, NonEmptyStr]] = {}
    for item in _artifact_references(request):
        key = (item.artifact_id, item.version)
        content = (item.digest, item.media_type)
        if key in index and index[key] != content:
            raise ValueError("same artifact identity/version cannot bind conflicting content")
        index[key] = content


def artifact_harmonization_receipt(
    value: object,
) -> ProteoformArtifactHarmonizationReceipt:
    """Project a fully validated genuine M04-05 result into the M04-06 boundary."""

    result = ProteoformArtifactDetectionResult.model_validate_json(
        canonical_json_bytes(value),
        strict=True,
    )
    quality = result.request.quality_result
    raw_input_result = quality.request.raw_input_result
    lineage_result = raw_input_result.request.lineage_result
    protocol_result = lineage_result.request.protocol_result
    protocol = protocol_result.request.protocol_schema
    posterior_groups: dict[Identifier, list[ProteoformArtifactPosterior]] = {}
    for posterior in result.artifact_posteriors:
        posterior_groups.setdefault(posterior.target_id, []).append(posterior)
    flag_groups: dict[Identifier, list[Identifier]] = {}
    for flag in result.contamination_flags:
        flag_groups.setdefault(flag.target_id, []).append(flag.flag_id)
    exclusion_by_target = {item.target_id: item for item in result.exclusion_mask}
    if not set(flag_groups).issubset(posterior_groups) or not set(exclusion_by_target).issubset(
        posterior_groups
    ):
        raise ValueError("M04-05 flags and exclusion entries require emitted target posteriors")
    targets: list[ProteoformArtifactTargetReceipt] = []
    for target_id, group in posterior_groups.items():
        posteriors = tuple(sorted(group, key=canonical_json_bytes))
        if (
            len(posteriors) != M0406_UPSTREAM_DETECTOR_COUNT
            or {item.detector_class for item in posteriors} != set(ProteoformArtifactDetectorClass)
            or len({item.unit_kind for item in posteriors}) != 1
        ):
            raise ValueError("M04-05 target projection requires all seven detector posteriors")
        states = {item.state for item in posteriors}
        observed = all(
            item.observation_state is ProteoformArtifactObservationState.OBSERVED
            for item in posteriors
        )
        excluded = target_id in exclusion_by_target
        flag_ids = tuple(sorted(flag_groups.get(target_id, ())))
        if excluded:
            target_state = ProteoformArtifactTargetState.EXCLUDED
            action = ProteoformArtifactAction.EXCLUDE
        elif ProteoformArtifactPosteriorState.DETECTED in states:
            raise ValueError("a detected M04-05 target requires an exclusion-mask entry")
        elif ProteoformArtifactPosteriorState.SUSPECTED in states:
            target_state = ProteoformArtifactTargetState.REVIEW
            action = ProteoformArtifactAction.REVIEW
        elif not observed or ProteoformArtifactPosteriorState.INDETERMINATE in states:
            target_state = ProteoformArtifactTargetState.INDETERMINATE
            action = ProteoformArtifactAction.REVIEW
        elif states == {ProteoformArtifactPosteriorState.CLEAR}:
            target_state = ProteoformArtifactTargetState.CLEAR
            action = ProteoformArtifactAction.RETAIN
        else:  # pragma: no cover - upstream enum closure makes this defensive only.
            raise ValueError("M04-05 target posterior states do not form a closed projection")
        posterior_digests = tuple(sorted(item.posterior_digest for item in posteriors))
        targets.append(
            ProteoformArtifactTargetReceipt(
                target_id=target_id,
                unit_kind=posteriors[0].unit_kind,
                target_state=target_state,
                action=action,
                posterior_digests=posterior_digests,
                posterior_binding_digest=sha256_digest(posterior_digests),
                contamination_flag_ids=flag_ids,
                excluded=excluded,
            )
        )
    canonical_targets = tuple(sorted(targets, key=canonical_json_bytes))
    from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
        artifact_receipt_digest,
        target_binding_digest,
    )

    payload: dict[str, object] = {
        "receipt_version": M0406_CONTRACT_VERSION,
        "artifact_reference": ArtifactReference(
            artifact_id=result.result_id,
            version=result.result_version,
            digest=result.result_digest,
            media_type=_M0405_RESULT_MEDIA_TYPE,
        ),
        "artifact_result_digest": result.result_digest,
        "artifact_request_digest": result.request_digest,
        "artifact_policy_digest": result.policy_digest,
        "artifact_configuration_digest": result.configuration_digest,
        "artifact_disposition": result.disposition,
        "artifact_support_status": result.support.status,
        "artifact_human_review_required": result.human_review_required,
        "artifact_completed_at": result.completed_at,
        "quality_receipt_digest": result.receipt.quality_receipt_digest,
        "evidence_ledger_digest": result.receipt.evidence_ledger_digest,
        "selected_profile_digest": result.receipt.selected_profile_digest,
        "quality_result_digest": result.receipt.quality_result_digest,
        "identity_resolution_digest": result.receipt.identity_resolution_digest,
        "protocol_result_digest": result.receipt.protocol_result_digest,
        "reference_bundle_digest": result.receipt.reference_bundle_digest,
        "coordinate_policy_digest": result.receipt.coordinate_policy_digest,
        "intended_use_evidence_digest": result.receipt.intended_use_evidence_digest,
        "applicability": protocol.applicability,
        "assay_protocol_version": protocol.assay_protocol_version,
        "specimen_processing_version": protocol.specimen_processing_version,
        "controlled_vocabulary_id": protocol.controlled_vocabulary_id,
        "controlled_vocabulary_version": protocol.controlled_vocabulary_version,
        "unit_system_version": protocol.unit_system_version,
        "evaluation_state": (
            ProteoformArtifactEvaluationState.COMPLETE
            if canonical_targets
            else ProteoformArtifactEvaluationState.NOT_EVALUABLE
        ),
        "target_count": len(canonical_targets),
        "targets": canonical_targets,
        "target_binding_digest": target_binding_digest(canonical_targets),
        "receipt_digest": _M0406_ZERO_DIGEST,
    }
    payload["receipt_digest"] = artifact_receipt_digest(payload)
    return ProteoformArtifactHarmonizationReceipt.model_validate(payload, strict=True)


def harmonization_ledger_bindings_close(
    request: HarmonizeProteoformAnalysisRequest,
) -> bool:
    ledger = request.support_ledger
    receipt = request.artifact_receipt
    return ledger is not None and (
        ledger.artifact_result_digest == receipt.artifact_result_digest
        and ledger.artifact_receipt_digest == receipt.receipt_digest
        and ledger.artifact_target_binding_digest == receipt.target_binding_digest
        and len(ledger.observations) == receipt.target_count
    )


def _require_authorized_context(context: ExecutionContext) -> None:
    references = context.references
    checks = (
        references.approved_configuration.state is UpstreamDecisionState.ACCEPTED,
        references.identity_lineage.state is IdentityLineageState.RESOLVED,
        references.provenance.state is UpstreamDecisionState.ACCEPTED,
        references.consent.state is ConsentState.GRANTED,
        references.quality.state is UpstreamDecisionState.ACCEPTED,
        references.support.state is UpstreamDecisionState.ACCEPTED,
        references.intended_use.state is UpstreamDecisionState.ACCEPTED,
    )
    if not all(checks):
        raise ValueError("proteoform harmonization is not authorized")


def preflight_authorized(candidate: object) -> bool:
    """Return whether seven controls authorize traversal without reading the ledger."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = (
            ("approved_configuration", "accepted"),
            ("identity_lineage", "resolved"),
            ("provenance", "accepted"),
            ("consent", "granted"),
            ("quality", "accepted"),
            ("support", "accepted"),
            ("intended_use", "accepted"),
        )
        return all(
            _state(_member(_member(references, role), "state")) == state for role, state in expected
        )
    except Exception:  # noqa: BLE001 - hostile accessors collapse to safe denial.
        return False


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, dict):
        return dict.get(candidate, field)
    if isinstance(candidate, Mapping):
        return candidate.get(field)
    return getattr(candidate, field, None)


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


class ProteoformSupportLevelShift(FrozenModel):
    level_id: Identifier
    state: ProteoformSupportShiftState
    estimated_shift_ppm: int | None = Field(
        default=None,
        ge=-M0406_RATE_SCALE,
        le=M0406_RATE_SCALE,
    )
    applied_shift_ppm: int | None = Field(
        default=None,
        ge=-M0406_RATE_SCALE,
        le=M0406_RATE_SCALE,
    )
    estimation_pair_count: int = Field(ge=0, le=M0406_MAX_OBSERVATIONS)
    validation_pair_count: int = Field(ge=0, le=M0406_MAX_OBSERVATIONS)
    pre_validation_residual_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0406_RATE_SCALE,
    )
    post_validation_residual_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0406_MAX_RESIDUAL_PPM,
    )
    unit: Literal["support_coordinate_ppm"] = "support_coordinate_ppm"

    @field_validator("level_id")
    @classmethod
    def level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "support-level-shift identifier")

    @model_validator(mode="after")
    def shift_shape_matches_state(self) -> ProteoformSupportLevelShift:
        numeric = (
            self.estimated_shift_ppm,
            self.applied_shift_ppm,
            self.pre_validation_residual_ppm,
            self.post_validation_residual_ppm,
        )
        if self.state is ProteoformSupportShiftState.NOT_EVALUABLE:
            if any(item is not None for item in numeric):
                raise ValueError("not-evaluable support shift cannot carry numeric estimates")
        elif any(item is None for item in numeric):
            raise ValueError("evaluable support shift requires estimates and validation residuals")
        elif (
            self.state is ProteoformSupportShiftState.ESTIMATED
            and self.applied_shift_ppm != self.estimated_shift_ppm
        ):
            raise ValueError("estimated fixed-point shift must be exact and below its cap")
        return self


class ProteoformAppliedSupportAdjustment(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0406_MAX_STAGES)
    factor: ProteoformNormalizationFactor
    level_id: Identifier
    shift_ppm: int = Field(ge=-M0406_RATE_SCALE, le=M0406_RATE_SCALE)
    unit: Literal["support_coordinate_ppm"] = "support_coordinate_ppm"

    @field_validator("stage_id")
    @classmethod
    def stage_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "stage", "applied-adjustment stage identifier")

    @field_validator("level_id")
    @classmethod
    def level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "applied-adjustment level identifier")


class ProteoformStageTransformation(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0406_MAX_STAGES)
    factor: ProteoformNormalizationFactor
    method: Literal["paired_lower_median_fixed_point_shift"] = (
        "paired_lower_median_fixed_point_shift"
    )
    reference_level_id: Identifier
    estimation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    validation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_STAGE_VALIDATION_ANCHORS,
    )
    maximum_absolute_shift_ppm: int = Field(gt=0, le=M0406_RATE_SCALE)
    minimum_estimation_pairs: int = Field(
        gt=0,
        le=M0406_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    minimum_validation_pairs: int = Field(
        gt=0,
        le=M0406_MAX_STAGE_VALIDATION_ANCHORS,
    )
    level_shifts: tuple[ProteoformSupportLevelShift, ...] = Field(
        min_length=2,
        max_length=M0406_MAX_LEVELS_PER_FACTOR,
    )
    clipped_target_ids: tuple[Identifier, ...] = Field(
        default=(),
        max_length=M0406_MAX_TARGETS,
    )
    input_digest: Sha256Digest
    output_digest: Sha256Digest

    @field_validator("stage_id")
    @classmethod
    def stage_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "stage", "transformation-stage identifier")

    @field_validator("reference_level_id")
    @classmethod
    def reference_level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "transformation reference-level identifier")

    @field_validator("estimation_anchor_ids", "validation_anchor_ids")
    @classmethod
    def anchor_collections_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "anchor", "transformation anchor identifier")
        return tuple(sorted(values))

    @field_validator("clipped_target_ids")
    @classmethod
    def clipped_target_identifiers_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "target", "clipped-target identifier")
        return tuple(sorted(values))

    @field_validator("level_shifts")
    @classmethod
    def level_shifts_are_canonical(
        cls,
        values: tuple[ProteoformSupportLevelShift, ...],
    ) -> tuple[ProteoformSupportLevelShift, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def transformation_is_closed(  # noqa: PLR0912 - ordered transformation audit
        self,
    ) -> ProteoformStageTransformation:
        if (
            len(self.estimation_anchor_ids) != len(set(self.estimation_anchor_ids))
            or len(self.validation_anchor_ids) != len(set(self.validation_anchor_ids))
            or set(self.estimation_anchor_ids) & set(self.validation_anchor_ids)
            or len(self.clipped_target_ids) != len(set(self.clipped_target_ids))
        ):
            raise ValueError("transformation identifier collections are not closed")
        levels = tuple(item.level_id for item in self.level_shifts)
        if len(levels) != len(set(levels)):
            raise ValueError("transformation level identifiers must be unique")
        reference = tuple(
            item for item in self.level_shifts if item.level_id == self.reference_level_id
        )
        if len(reference) != 1:
            raise ValueError("transformation requires exactly one reference-level shift")
        for shift in self.level_shifts:
            if shift.state is ProteoformSupportShiftState.NOT_EVALUABLE:
                if (
                    shift.estimation_pair_count >= self.minimum_estimation_pairs
                    and shift.validation_pair_count >= self.minimum_validation_pairs
                ):
                    raise ValueError(
                        "not-evaluable shift must fall below an exact control-pair minimum"
                    )
                continue
            if (
                shift.estimation_pair_count < self.minimum_estimation_pairs
                or shift.validation_pair_count < self.minimum_validation_pairs
            ):
                raise ValueError("evaluable shift must meet both control-pair minima")
            estimated = shift.estimated_shift_ppm
            applied = shift.applied_shift_ppm
            if estimated is None or applied is None:
                raise ValueError("evaluable transformation shift is incomplete")
            if shift.state is ProteoformSupportShiftState.ESTIMATED:
                if abs(estimated) >= self.maximum_absolute_shift_ppm or applied != estimated:
                    raise ValueError("estimated fixed-point shift must be exact and below its cap")
            else:
                expected = max(
                    -self.maximum_absolute_shift_ppm,
                    min(self.maximum_absolute_shift_ppm, estimated),
                )
                if abs(estimated) < self.maximum_absolute_shift_ppm or applied != expected:
                    raise ValueError("capped fixed-point shift must apply the exact signed cap")
        reference_shift = reference[0]
        if reference_shift.state is not ProteoformSupportShiftState.NOT_EVALUABLE and (
            reference_shift.estimated_shift_ppm != 0
            or reference_shift.applied_shift_ppm != 0
            or reference_shift.pre_validation_residual_ppm != 0
            or reference_shift.post_validation_residual_ppm != 0
        ):
            raise ValueError("evaluable reference-level shift must be exact zero")
        return self


class ProteoformTransformationManifest(FrozenModel):
    artifact_receipt_digest: Sha256Digest
    support_ledger_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    stages: tuple[ProteoformStageTransformation, ...] = Field(
        min_length=M0406_MAX_STAGES,
        max_length=M0406_MAX_STAGES,
    )
    manifest_digest: Sha256Digest

    @field_validator("stages")
    @classmethod
    def stages_are_ordered(
        cls,
        values: tuple[ProteoformStageTransformation, ...],
    ) -> tuple[ProteoformStageTransformation, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def manifest_is_content_addressed(self) -> ProteoformTransformationManifest:
        from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
            transformation_manifest_digest,
        )

        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0406_MAX_STAGES + 1)):
            raise ValueError("transformation manifest stage ordinals are not exact")
        if len({item.stage_id for item in self.stages}) != M0406_MAX_STAGES:
            raise ValueError("transformation manifest stage identifiers must be unique")
        if {item.factor for item in self.stages} != set(ProteoformNormalizationFactor):
            raise ValueError("transformation manifest must cover all eight factors")
        if self.manifest_digest != transformation_manifest_digest(self):
            raise ValueError("transformation manifest digest does not match its content")
        return self


class ProteoformTechnicalEffectDiagnostic(FrozenModel):
    stage_id: Identifier
    factor: ProteoformNormalizationFactor
    before_residual_ppm: int | None = Field(default=None, ge=0, le=M0406_RATE_SCALE)
    after_residual_ppm: int | None = Field(default=None, ge=0, le=M0406_MAX_RESIDUAL_PPM)
    tolerance_ppm: int = Field(ge=0, le=M0406_RATE_SCALE)
    capped: bool
    clipped: bool
    status: ProteoformHarmonizationDiagnosticStatus

    @field_validator("stage_id")
    @classmethod
    def stage_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "stage", "technical-diagnostic stage identifier")

    @model_validator(mode="after")
    def diagnostic_status_is_exact(self) -> ProteoformTechnicalEffectDiagnostic:
        if (self.before_residual_ppm is None) != (self.after_residual_ppm is None):
            raise ValueError("technical residuals must be jointly present or absent")
        if self.before_residual_ppm is None or self.after_residual_ppm is None:
            expected = ProteoformHarmonizationDiagnosticStatus.NOT_EVALUABLE
        elif (
            not self.capped
            and not self.clipped
            and self.after_residual_ppm <= self.tolerance_ppm
            and (
                self.after_residual_ppm < self.before_residual_ppm
                or self.after_residual_ppm == self.before_residual_ppm == 0
            )
        ):
            expected = ProteoformHarmonizationDiagnosticStatus.PASSED
        else:
            expected = ProteoformHarmonizationDiagnosticStatus.FAILED
        if self.status is not expected:
            raise ValueError("technical residuals contradict their deterministic status")
        return self


class ProteoformInvariantDiagnostic(FrozenModel):
    invariant_id: Identifier
    kind: ProteoformSupportInvariantKind
    before_score_ppm: int | None = Field(
        default=None,
        ge=-M0406_RATE_SCALE,
        le=M0406_RATE_SCALE,
    )
    after_score_ppm: int | None = Field(
        default=None,
        ge=-M0406_RATE_SCALE,
        le=M0406_RATE_SCALE,
    )
    tolerance_ppm: int = Field(ge=0, le=M0406_RATE_SCALE)
    status: ProteoformHarmonizationDiagnosticStatus

    @field_validator("invariant_id")
    @classmethod
    def invariant_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "invariant", "invariant-diagnostic identifier")

    @model_validator(mode="after")
    def diagnostic_status_is_exact(self) -> ProteoformInvariantDiagnostic:
        before = self.before_score_ppm
        after = self.after_score_ppm
        if (before is None) != (after is None):
            raise ValueError("protected support scores must be jointly present or absent")
        if before is None or after is None:
            expected = ProteoformHarmonizationDiagnosticStatus.NOT_EVALUABLE
        elif self.kind is ProteoformSupportInvariantKind.COMPOSITION_FRACTION:
            expected = (
                ProteoformHarmonizationDiagnosticStatus.PASSED
                if abs(after - before) <= self.tolerance_ppm
                else ProteoformHarmonizationDiagnosticStatus.FAILED
            )
        else:
            expected = (
                ProteoformHarmonizationDiagnosticStatus.PASSED
                if _sign(before) != 0
                and _sign(before) == _sign(after)
                and abs(after - before) <= self.tolerance_ppm
                else ProteoformHarmonizationDiagnosticStatus.FAILED
            )
        if self.status is not expected:
            raise ValueError("protected support scores contradict their deterministic status")
        return self


class ProteoformHarmonizedSupportValue(FrozenModel):
    target_id: Identifier
    unit_kind: ProteoformEvidenceUnitKind
    artifact_action: ProteoformArtifactAction
    input_state: ProteoformSupportObservationState
    output_state: ProteoformSupportObservationState
    input_support_coordinate_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0406_RATE_SCALE,
    )
    harmonized_support_coordinate_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0406_RATE_SCALE,
    )
    censoring_upper_bound_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0406_RATE_SCALE,
    )
    is_calibrated_probability: Literal[False] = False
    source_observation_digest: Sha256Digest
    adjustments: tuple[ProteoformAppliedSupportAdjustment, ...] = Field(
        default=(),
        max_length=M0406_MAX_STAGES,
    )
    was_clipped: bool

    @field_validator("target_id")
    @classmethod
    def target_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "target", "harmonized-value target identifier")

    @field_validator("adjustments")
    @classmethod
    def adjustments_are_ordered(
        cls,
        values: tuple[ProteoformAppliedSupportAdjustment, ...],
    ) -> tuple[ProteoformAppliedSupportAdjustment, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> ProteoformHarmonizedSupportValue:
        ordinals = tuple(item.ordinal for item in self.adjustments)
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("harmonized support adjustments must be unique by ordinal")
        if self.output_state is not self.input_state:
            raise ValueError("harmonization cannot relabel a support observation state")
        traversable = (
            self.artifact_action is ProteoformArtifactAction.RETAIN
            and self.input_state is ProteoformSupportObservationState.OBSERVED
        )
        if traversable:
            if (
                self.input_support_coordinate_ppm is None
                or self.harmonized_support_coordinate_ppm is None
                or self.censoring_upper_bound_ppm is not None
            ):
                raise ValueError("retained observed support requires its exact input and output")
            expected = self.input_support_coordinate_ppm
            clipped = False
            for adjustment in self.adjustments:
                shifted = expected + adjustment.shift_ppm
                clipped = clipped or (
                    adjustment.shift_ppm != 0 and (shifted <= 0 or shifted >= M0406_RATE_SCALE)
                )
                expected = max(0, min(M0406_RATE_SCALE, shifted))
            if self.harmonized_support_coordinate_ppm != expected or self.was_clipped != clipped:
                raise ValueError("harmonized support contradicts its exact applied adjustments")
            return self
        if (
            self.harmonized_support_coordinate_ppm is not None
            or self.adjustments
            or self.was_clipped
        ):
            raise ValueError("held or non-observed support cannot carry a harmonized value")
        if self.input_state is ProteoformSupportObservationState.OBSERVED:
            if (
                self.input_support_coordinate_ppm is None
                or self.censoring_upper_bound_ppm is not None
            ):
                raise ValueError("held observed support requires only its input coordinate")
        elif self.input_state is ProteoformSupportObservationState.CENSORED:
            if (
                self.input_support_coordinate_ppm is not None
                or self.censoring_upper_bound_ppm is None
            ):
                raise ValueError("censored support output must preserve its exact bound")
        elif (
            self.input_support_coordinate_ppm is not None
            or self.censoring_upper_bound_ppm is not None
        ):
            raise ValueError("non-observed support output cannot manufacture a coordinate")
        return self


class ProteoformHarmonizedAnalysis(FrozenModel):
    analysis_id: Identifier
    artifact_result_digest: Sha256Digest
    support_ledger_digest: Sha256Digest
    artifact_target_binding_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    retain_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0406_MAX_TARGETS)
    review_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0406_MAX_TARGETS)
    exclude_target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0406_MAX_TARGETS)
    platform_level_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_LEVELS_PER_FACTOR,
    )
    target_count: int = Field(ge=1, le=M0406_MAX_TARGETS)
    retain_target_count: int = Field(ge=0, le=M0406_MAX_TARGETS)
    review_target_count: int = Field(ge=0, le=M0406_MAX_TARGETS)
    exclude_target_count: int = Field(ge=0, le=M0406_MAX_TARGETS)
    evaluable_target_count: int = Field(ge=0, le=M0406_MAX_TARGETS)
    values: tuple[ProteoformHarmonizedSupportValue, ...] = Field(
        min_length=1,
        max_length=M0406_MAX_OBSERVATIONS,
    )
    analysis_digest: Sha256Digest
    parent_target: Literal["protein_rna_discordance"] = M0406_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    executes_model: Literal[False] = False

    @field_validator("retain_target_ids", "review_target_ids", "exclude_target_ids")
    @classmethod
    def partitions_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "target", "analysis partition unit identifier")
        return tuple(sorted(values))

    @field_validator("platform_level_ids")
    @classmethod
    def platform_levels_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("platform level identifiers must be unique")
        for value in values:
            _opaque_identifier(value, "level", "platform-level identifier")
        return tuple(sorted(values))

    @field_validator("values")
    @classmethod
    def values_are_canonical(
        cls,
        values: tuple[ProteoformHarmonizedSupportValue, ...],
    ) -> tuple[ProteoformHarmonizedSupportValue, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def analysis_is_content_addressed(self) -> ProteoformHarmonizedAnalysis:
        from glio_proteogen.contracts.m04_06.canonical import analysis_digest  # noqa: PLC0415

        partitions = (
            self.retain_target_ids,
            self.review_target_ids,
            self.exclude_target_ids,
        )
        if any(len(values) != len(set(values)) for values in partitions):
            raise ValueError("harmonized analysis partitions require unique targets")
        if any(
            set(left) & set(right)
            for index, left in enumerate(partitions)
            for right in partitions[index + 1 :]
        ):
            raise ValueError("harmonized analysis partitions must be disjoint")
        value_ids = tuple(item.target_id for item in self.values)
        if len(value_ids) != len(set(value_ids)) or set(value_ids) != set().union(
            *(set(values) for values in partitions)
        ):
            raise ValueError("harmonized analysis values must exactly cover its target partitions")
        expected_action = {
            **dict.fromkeys(self.retain_target_ids, ProteoformArtifactAction.RETAIN),
            **dict.fromkeys(self.review_target_ids, ProteoformArtifactAction.REVIEW),
            **dict.fromkeys(self.exclude_target_ids, ProteoformArtifactAction.EXCLUDE),
        }
        if any(item.artifact_action is not expected_action[item.target_id] for item in self.values):
            raise ValueError("harmonized analysis partition contradicts a target action")
        expected_counts = (
            len(self.values),
            len(self.retain_target_ids),
            len(self.review_target_ids),
            len(self.exclude_target_ids),
            sum(item.harmonized_support_coordinate_ppm is not None for item in self.values),
        )
        if expected_counts != (
            self.target_count,
            self.retain_target_count,
            self.review_target_count,
            self.exclude_target_count,
            self.evaluable_target_count,
        ):
            raise ValueError("harmonized analysis counts must replay its exact target partitions")
        if self.analysis_digest != analysis_digest(self):
            raise ValueError("harmonized analysis digest does not match its content")
        return self


class ProteoformHarmonizationFinding(FrozenModel):
    finding_id: Identifier
    code: ProteoformHarmonizationFindingCode
    action: ProteoformHarmonizationFindingAction
    stage_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0406_MAX_STAGES)
    target_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0406_MAX_TARGETS)
    invariant_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0406_MAX_INVARIANTS)
    message: NonEmptyStr

    @field_validator("stage_ids", "target_ids", "invariant_ids")
    @classmethod
    def references_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def finding_references_are_opaque(self) -> ProteoformHarmonizationFinding:
        for value in self.stage_ids:
            _opaque_identifier(value, "stage", "finding stage identifier")
        for value in self.target_ids:
            _opaque_identifier(value, "target", "finding target identifier")
        for value in self.invariant_ids:
            _opaque_identifier(value, "invariant", "finding invariant identifier")
        return self

    @model_validator(mode="after")
    def finding_is_closed(self) -> ProteoformHarmonizationFinding:
        if (
            len(self.stage_ids) != len(set(self.stage_ids))
            or len(self.target_ids) != len(set(self.target_ids))
            or len(self.invariant_ids) != len(set(self.invariant_ids))
        ):
            raise ValueError("harmonization finding references must be unique")
        expected = finding_for(
            self.code,
            stage_ids=self.stage_ids,
            target_ids=self.target_ids,
            invariant_ids=self.invariant_ids,
        )
        if self != expected:
            raise ValueError("M04-06 finding contradicts its closed vocabulary")
        return self


class ProteoformHarmonizationComputationReceipt(FrozenModel):
    artifact_result_digest: Sha256Digest
    artifact_receipt_digest: Sha256Digest
    quality_result_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    applicability: ProteoformApplicability | None = None
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    support_ledger_digest: Sha256Digest | None = None
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    profile_digest: Sha256Digest | None = None
    analysis_digest: Sha256Digest | None = None
    analysis_platform_level_ids: tuple[Identifier, ...] = Field(
        default=(),
        max_length=M0406_MAX_LEVELS_PER_FACTOR,
    )
    analysis_target_count: int | None = Field(default=None, ge=1, le=M0406_MAX_TARGETS)
    analysis_retain_target_count: int | None = Field(default=None, ge=0, le=M0406_MAX_TARGETS)
    analysis_review_target_count: int | None = Field(default=None, ge=0, le=M0406_MAX_TARGETS)
    analysis_exclude_target_count: int | None = Field(default=None, ge=0, le=M0406_MAX_TARGETS)
    analysis_evaluable_target_count: int | None = Field(
        default=None,
        ge=0,
        le=M0406_MAX_TARGETS,
    )
    transformation_manifest_digest: Sha256Digest | None = None
    supersedes_result_digest: Sha256Digest | None = None
    parent_target: Literal["protein_rna_discordance"] = M0406_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    executes_model: Literal[False] = False
    disposition: ProteoformHarmonizationDisposition

    @field_validator("analysis_platform_level_ids")
    @classmethod
    def analysis_platform_levels_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("receipt platform-level identifiers must be unique")
        for value in values:
            _opaque_identifier(value, "level", "receipt platform-level identifier")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def analysis_projection_is_closed(self) -> ProteoformHarmonizationComputationReceipt:
        counts = (
            self.analysis_target_count,
            self.analysis_retain_target_count,
            self.analysis_review_target_count,
            self.analysis_exclude_target_count,
            self.analysis_evaluable_target_count,
        )
        analysis_present = self.analysis_digest is not None
        if analysis_present != all(value is not None for value in counts):
            raise ValueError("receipt analysis digest and counts must be present together")
        if analysis_present != bool(self.analysis_platform_level_ids):
            raise ValueError("receipt analysis requires its exact platform-level projection")
        if analysis_present:
            target_count, retain_count, review_count, exclude_count, evaluable_count = counts
            if (
                target_count is None
                or retain_count is None
                or review_count is None
                or exclude_count is None
                or evaluable_count is None
            ):
                raise ValueError("receipt analysis requires every partition count")
            if (
                target_count != retain_count + review_count + exclude_count
                or evaluable_count > retain_count
            ):
                raise ValueError("receipt analysis counts contradict its target partitions")
        return self


class ProteoformHarmonizationResult(FrozenModel):
    output_type: Literal["proteoform_harmonized_analysis"] = "proteoform_harmonized_analysis"
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0406_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: HarmonizeProteoformAnalysisRequest
    receipt: ProteoformHarmonizationComputationReceipt
    analysis: ProteoformHarmonizedAnalysis | None = None
    transformation_manifest: ProteoformTransformationManifest | None = None
    technical_effect_diagnostics: tuple[ProteoformTechnicalEffectDiagnostic, ...] = Field(
        default=(),
        max_length=M0406_MAX_STAGES,
    )
    invariant_diagnostics: tuple[ProteoformInvariantDiagnostic, ...] = Field(
        default=(),
        max_length=M0406_MAX_INVARIANTS,
    )
    findings: tuple[ProteoformHarmonizationFinding, ...] = Field(
        default=(),
        max_length=M0406_MAX_FINDINGS,
    )
    disposition: ProteoformHarmonizationDisposition
    parent_target: Literal["protein_rna_discordance"] = M0406_PARENT
    emits_protein_rna_discordance: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    localizes_modification: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    executes_model: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0406_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator(
        "technical_effect_diagnostics",
        "invariant_diagnostics",
        "findings",
        "evidence",
        "limitations",
    )
    @classmethod
    def collections_are_canonical(cls, values: tuple[object, ...]) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_notes_are_canonical(cls, value: UncertaintyProfile) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @field_validator("provenance")
    @classmethod
    def provenance_collections_are_canonical(cls, value: ProvenanceRecord) -> ProvenanceRecord:
        return value.model_copy(
            update={
                "input_digests": tuple(sorted(value.input_digests)),
                "control_decisions": tuple(
                    sorted(value.control_decisions, key=canonical_json_bytes)
                ),
            }
        )

    @model_validator(mode="after")
    def result_is_relationally_closed(  # noqa: PLR0912 - ordered closure audit
        self,
    ) -> ProteoformHarmonizationResult:
        from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
            canonical_request_digest,
            configuration_digest,
            normalized_request,
            policy_digest,
            result_payload_digest,
        )

        canonical_request = HarmonizeProteoformAnalysisRequest.model_validate_json(
            canonical_json_bytes(normalized_request(self.request)),
            strict=True,
        )
        if self.request != canonical_request:
            raise ValueError("M04-06 embedded request is not in canonical semantic order")
        analysis, manifest, technical, invariants = derive_harmonization(self.request)
        findings = expected_harmonization_findings(
            self.request,
            manifest,
            technical,
            invariants,
        )
        disposition = expected_disposition(self.request, findings)
        request_hash = canonical_request_digest(self.request)
        policy_hash = policy_digest(self.request.policy)
        config_hash = configuration_digest(self.request.policy)
        if self.analysis != analysis or self.transformation_manifest != manifest:
            raise ValueError("M04-06 analysis or transformation manifest does not replay")
        if not _semantic_tuple_equal(self.technical_effect_diagnostics, technical):
            raise ValueError("M04-06 technical diagnostics do not replay")
        if not _semantic_tuple_equal(self.invariant_diagnostics, invariants):
            raise ValueError("M04-06 protected invariant diagnostics do not replay")
        if not _semantic_tuple_equal(self.findings, findings):
            raise ValueError("M04-06 findings do not replay")
        if (
            self.result_id != f"result.m0406.{request_hash.removeprefix('sha256:')}"
            or self.request_digest != request_hash
            or self.policy_digest != policy_hash
            or self.configuration_digest != config_hash
            or self.receipt
            != expected_computation_receipt(
                self.request,
                disposition,
                analysis,
                manifest,
            )
            or self.disposition is not disposition
        ):
            raise ValueError("M04-06 output envelope contradicts its replayed request")
        if self.support != expected_support(disposition):
            raise ValueError("M04-06 support is not deterministic")
        if not _uncertainty_equal(self.uncertainty, expected_uncertainty(disposition)):
            raise ValueError("M04-06 uncertainty is not deterministic")
        if not _provenance_equal(self.provenance, expected_provenance(self.request)):
            raise ValueError("M04-06 provenance does not close")
        if not _semantic_tuple_equal(self.evidence, harmonization_evidence_index(self.request)):
            raise ValueError("M04-06 evidence index does not close")
        if not _semantic_tuple_equal(self.limitations, expected_limitations()):
            raise ValueError("M04-06 limitations do not close")
        if self.human_review_required != (
            disposition is not ProteoformHarmonizationDisposition.ACCEPTED
        ):
            raise ValueError("M04-06 human-review flag contradicts disposition")
        if self.completed_at != self.request.context.occurred_at:
            raise ValueError("M04-06 completion time must equal execution time")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M04-06 result digest does not match its canonical payload")
        return self


def lower_median(values: tuple[int, ...]) -> int:
    """Return the deterministic lower middle integer without interpolation."""

    if not values:
        raise ValueError("lower median requires at least one integer")
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _factor_level(
    observation: ProteoformSupportObservation,
    factor: ProteoformNormalizationFactor,
) -> Identifier:
    return next(item.level_id for item in observation.factor_levels if item.factor is factor)


def _retained_observed(observation: ProteoformSupportObservation) -> bool:
    return (
        observation.artifact_action is ProteoformArtifactAction.RETAIN
        and observation.state is ProteoformSupportObservationState.OBSERVED
        and observation.support_coordinate_ppm is not None
    )


def _working_digest(
    observations: tuple[ProteoformSupportObservation, ...],
    working: dict[Identifier, int],
) -> Sha256Digest:
    return sha256_digest(
        tuple(
            sorted(
                (
                    {
                        "target_id": item.target_id,
                        "state": item.state.value,
                        "artifact_action": item.artifact_action.value,
                        "support_coordinate_ppm": working.get(item.target_id),
                    }
                    for item in observations
                ),
                key=canonical_json_bytes,
            )
        )
    )


def _pair_differences(  # noqa: PLR0913 - explicit fixed-point pairing inputs
    observations: tuple[ProteoformSupportObservation, ...],
    working: dict[Identifier, int],
    *,
    factor: ProteoformNormalizationFactor,
    reference_level_id: Identifier,
    comparison_level_id: Identifier,
    anchor_ids: tuple[Identifier, ...],
) -> tuple[int, ...]:
    accepted_anchors = set(anchor_ids)
    grouped: dict[
        tuple[Identifier, Identifier, ProteoformEvidenceUnitKind],
        dict[Identifier, list[int]],
    ] = {}
    for observation in observations:
        if not _retained_observed(observation) or observation.anchor_id not in accepted_anchors:
            continue
        level_id = _factor_level(observation, factor)
        if level_id not in {reference_level_id, comparison_level_id}:
            continue
        key = (
            observation.anchor_id,
            observation.biological_group_id,
            observation.unit_kind,
        )
        grouped.setdefault(key, {}).setdefault(level_id, []).append(working[observation.target_id])
    differences: list[int] = []
    for values_by_level in grouped.values():
        reference = values_by_level.get(reference_level_id)
        comparison = values_by_level.get(comparison_level_id)
        if reference and comparison:
            differences.append(lower_median(tuple(reference)) - lower_median(tuple(comparison)))
    return tuple(differences)


def _stage_execution(
    request: HarmonizeProteoformAnalysisRequest,
    stage: ProteoformNormalizationStage,
    observations: tuple[ProteoformSupportObservation, ...],
    working: dict[Identifier, int],
    adjustments: dict[Identifier, list[ProteoformAppliedSupportAdjustment]],
) -> tuple[
    ProteoformStageTransformation,
    ProteoformTechnicalEffectDiagnostic,
]:
    policy = request.policy
    input_digest = _working_digest(observations, working)
    levels = tuple(sorted({_factor_level(item, stage.factor) for item in observations}))
    non_reference: list[ProteoformSupportLevelShift] = []
    for level_id in levels:
        if level_id == stage.reference_level_id:
            continue
        estimation_differences = _pair_differences(
            observations,
            working,
            factor=stage.factor,
            reference_level_id=stage.reference_level_id,
            comparison_level_id=level_id,
            anchor_ids=stage.estimation_anchor_ids,
        )
        validation_differences = _pair_differences(
            observations,
            working,
            factor=stage.factor,
            reference_level_id=stage.reference_level_id,
            comparison_level_id=level_id,
            anchor_ids=stage.validation_anchor_ids,
        )
        if (
            len(estimation_differences) < policy.min_estimation_pairs_per_level
            or len(validation_differences) < policy.min_validation_pairs_per_level
        ):
            non_reference.append(
                ProteoformSupportLevelShift(
                    level_id=level_id,
                    state=ProteoformSupportShiftState.NOT_EVALUABLE,
                    estimation_pair_count=len(estimation_differences),
                    validation_pair_count=len(validation_differences),
                )
            )
            continue
        estimate = lower_median(estimation_differences)
        applied = max(
            -policy.max_absolute_shift_ppm,
            min(policy.max_absolute_shift_ppm, estimate),
        )
        state = (
            ProteoformSupportShiftState.CAPPED
            if abs(estimate) >= policy.max_absolute_shift_ppm
            else ProteoformSupportShiftState.ESTIMATED
        )
        non_reference.append(
            ProteoformSupportLevelShift(
                level_id=level_id,
                state=state,
                estimated_shift_ppm=estimate,
                applied_shift_ppm=applied,
                estimation_pair_count=len(estimation_differences),
                validation_pair_count=len(validation_differences),
                pre_validation_residual_ppm=abs(lower_median(validation_differences)),
                post_validation_residual_ppm=abs(
                    lower_median(tuple(item - applied for item in validation_differences))
                ),
            )
        )
    all_non_reference_evaluable = bool(non_reference) and all(
        item.state is not ProteoformSupportShiftState.NOT_EVALUABLE for item in non_reference
    )
    reference = ProteoformSupportLevelShift(
        level_id=stage.reference_level_id,
        state=(
            ProteoformSupportShiftState.ESTIMATED
            if all_non_reference_evaluable
            else ProteoformSupportShiftState.NOT_EVALUABLE
        ),
        estimated_shift_ppm=0 if all_non_reference_evaluable else None,
        applied_shift_ppm=0 if all_non_reference_evaluable else None,
        estimation_pair_count=(
            min(item.estimation_pair_count for item in non_reference) if non_reference else 0
        ),
        validation_pair_count=(
            min(item.validation_pair_count for item in non_reference) if non_reference else 0
        ),
        pre_validation_residual_ppm=0 if all_non_reference_evaluable else None,
        post_validation_residual_ppm=0 if all_non_reference_evaluable else None,
    )
    shifts = tuple(sorted((reference, *non_reference), key=canonical_json_bytes))
    applied_by_level = {
        item.level_id: item.applied_shift_ppm
        for item in shifts
        if item.applied_shift_ppm is not None
    }
    clipped: set[Identifier] = set()
    for observation in observations:
        if not _retained_observed(observation):
            continue
        level_id = _factor_level(observation, stage.factor)
        shift = applied_by_level.get(level_id)
        if shift is None:
            continue
        shifted = working[observation.target_id] + shift
        if shift != 0 and (shifted <= 0 or shifted >= M0406_RATE_SCALE):
            clipped.add(observation.target_id)
        working[observation.target_id] = max(0, min(M0406_RATE_SCALE, shifted))
        adjustments[observation.target_id].append(
            ProteoformAppliedSupportAdjustment(
                stage_id=stage.stage_id,
                ordinal=stage.ordinal,
                factor=stage.factor,
                level_id=level_id,
                shift_ppm=shift,
            )
        )
    output_digest = _working_digest(observations, working)
    capped = any(item.state is ProteoformSupportShiftState.CAPPED for item in shifts)
    evaluable = all(item.state is not ProteoformSupportShiftState.NOT_EVALUABLE for item in shifts)
    before = max(item.pre_validation_residual_ppm or 0 for item in shifts) if evaluable else None
    after = max(item.post_validation_residual_ppm or 0 for item in shifts) if evaluable else None
    status = (
        ProteoformHarmonizationDiagnosticStatus.NOT_EVALUABLE
        if before is None or after is None
        else ProteoformHarmonizationDiagnosticStatus.PASSED
        if not capped
        and not clipped
        and after <= policy.technical_effect_tolerance_ppm
        and (after < before or after == before == 0)
        else ProteoformHarmonizationDiagnosticStatus.FAILED
    )
    transformation = ProteoformStageTransformation(
        stage_id=stage.stage_id,
        ordinal=stage.ordinal,
        factor=stage.factor,
        reference_level_id=stage.reference_level_id,
        estimation_anchor_ids=stage.estimation_anchor_ids,
        validation_anchor_ids=stage.validation_anchor_ids,
        maximum_absolute_shift_ppm=policy.max_absolute_shift_ppm,
        minimum_estimation_pairs=policy.min_estimation_pairs_per_level,
        minimum_validation_pairs=policy.min_validation_pairs_per_level,
        level_shifts=shifts,
        clipped_target_ids=tuple(sorted(clipped)),
        input_digest=input_digest,
        output_digest=output_digest,
    )
    diagnostic = ProteoformTechnicalEffectDiagnostic(
        stage_id=stage.stage_id,
        factor=stage.factor,
        before_residual_ppm=before,
        after_residual_ppm=after,
        tolerance_ppm=policy.technical_effect_tolerance_ppm,
        capped=capped,
        clipped=bool(clipped),
        status=status,
    )
    return transformation, diagnostic


def _invariant_score(
    invariant: ProteoformSupportInvariant,
    observations: dict[Identifier, ProteoformSupportObservation],
    values: dict[Identifier, int],
) -> int | None:
    members = (*invariant.left_target_ids, *invariant.right_target_ids)
    if any(
        not _retained_observed(observations[target_id]) or target_id not in values
        for target_id in members
    ):
        return None
    left = tuple(values[item] for item in invariant.left_target_ids)
    right = tuple(values[item] for item in invariant.right_target_ids)
    if invariant.kind is ProteoformSupportInvariantKind.COMPOSITION_FRACTION:
        numerator = sum(left)
        denominator = numerator + sum(right)
        return (
            None
            if denominator == 0
            else (numerator * M0406_RATE_SCALE + denominator // 2) // denominator
        )
    return lower_median(left) - lower_median(right)


def _invariant_diagnostics(
    request: HarmonizeProteoformAnalysisRequest,
    initial: dict[Identifier, int],
    working: dict[Identifier, int],
) -> tuple[ProteoformInvariantDiagnostic, ...]:
    ledger = request.support_ledger
    if ledger is None:
        return ()
    observations = {item.target_id: item for item in ledger.observations}
    diagnostics: list[ProteoformInvariantDiagnostic] = []
    for invariant in ledger.invariants:
        before = _invariant_score(invariant, observations, initial)
        after = _invariant_score(invariant, observations, working)
        if before is None or after is None:
            status = ProteoformHarmonizationDiagnosticStatus.NOT_EVALUABLE
        elif invariant.kind is ProteoformSupportInvariantKind.COMPOSITION_FRACTION:
            status = (
                ProteoformHarmonizationDiagnosticStatus.PASSED
                if abs(after - before) <= request.policy.biological_invariant_tolerance_ppm
                else ProteoformHarmonizationDiagnosticStatus.FAILED
            )
        else:
            status = (
                ProteoformHarmonizationDiagnosticStatus.PASSED
                if _sign(before) != 0
                and _sign(before) == _sign(after)
                and abs(after - before) <= request.policy.biological_invariant_tolerance_ppm
                else ProteoformHarmonizationDiagnosticStatus.FAILED
            )
        diagnostics.append(
            ProteoformInvariantDiagnostic(
                invariant_id=invariant.invariant_id,
                kind=invariant.kind,
                before_score_ppm=before,
                after_score_ppm=after,
                tolerance_ppm=request.policy.biological_invariant_tolerance_ppm,
                status=status,
            )
        )
    return tuple(sorted(diagnostics, key=canonical_json_bytes))


def derive_harmonization(
    request: HarmonizeProteoformAnalysisRequest,
) -> tuple[
    ProteoformHarmonizedAnalysis | None,
    ProteoformTransformationManifest | None,
    tuple[ProteoformTechnicalEffectDiagnostic, ...],
    tuple[ProteoformInvariantDiagnostic, ...],
]:
    """Replay the exact fixed-point harmonization inside its supported envelope."""

    active = matching_harmonization_profile(request)
    ledger = request.support_ledger
    if (
        request.artifact_receipt.evaluation_state is not ProteoformArtifactEvaluationState.COMPLETE
        or request.artifact_receipt.target_count > request.policy.max_targets
        or ledger is None
        or active is None
        or not harmonization_ledger_bindings_close(request)
    ):
        return None, None, (), ()
    observations = tuple(sorted(ledger.observations, key=canonical_json_bytes))
    initial = {
        item.target_id: item.support_coordinate_ppm
        for item in observations
        if _retained_observed(item) and item.support_coordinate_ppm is not None
    }
    working = dict(initial)
    adjustments: dict[Identifier, list[ProteoformAppliedSupportAdjustment]] = {
        item.target_id: [] for item in observations
    }
    transformations: list[ProteoformStageTransformation] = []
    technical: list[ProteoformTechnicalEffectDiagnostic] = []
    for stage in active.stages:
        transformation, diagnostic = _stage_execution(
            request,
            stage,
            observations,
            working,
            adjustments,
        )
        transformations.append(transformation)
        technical.append(diagnostic)
    invariant_diagnostics = _invariant_diagnostics(request, initial, working)
    from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
        analysis_digest,
        canonical_request_digest,
        configuration_digest,
        observation_digest,
        policy_digest,
        profile_digest,
        transformation_manifest_digest,
    )

    request_hash = canonical_request_digest(request)
    active_profile_digest = profile_digest(active)
    active_policy_digest = policy_digest(request.policy)
    manifest_payload: dict[str, object] = {
        "artifact_receipt_digest": request.artifact_receipt.receipt_digest,
        "support_ledger_digest": ledger.ledger_digest,
        "profile_digest": active_profile_digest,
        "policy_digest": active_policy_digest,
        "configuration_digest": configuration_digest(request.policy),
        "stages": tuple(transformations),
        "manifest_digest": _M0406_ZERO_DIGEST,
    }
    manifest_payload["manifest_digest"] = transformation_manifest_digest(manifest_payload)
    manifest = ProteoformTransformationManifest.model_validate(manifest_payload, strict=True)
    clipped_targets = {
        target_id for stage in transformations for target_id in stage.clipped_target_ids
    }
    values = tuple(
        ProteoformHarmonizedSupportValue(
            target_id=item.target_id,
            unit_kind=item.unit_kind,
            artifact_action=item.artifact_action,
            input_state=item.state,
            output_state=item.state,
            input_support_coordinate_ppm=item.support_coordinate_ppm,
            harmonized_support_coordinate_ppm=(
                working[item.target_id] if _retained_observed(item) else None
            ),
            censoring_upper_bound_ppm=item.censoring_upper_bound_ppm,
            source_observation_digest=observation_digest(item),
            adjustments=tuple(adjustments[item.target_id]) if _retained_observed(item) else (),
            was_clipped=item.target_id in clipped_targets,
        )
        for item in observations
    )
    analysis_payload: dict[str, object] = {
        "analysis_id": f"analysis.m0406.{request_hash.removeprefix('sha256:')}",
        "artifact_result_digest": request.artifact_receipt.artifact_result_digest,
        "support_ledger_digest": ledger.ledger_digest,
        "artifact_target_binding_digest": request.artifact_receipt.target_binding_digest,
        "profile_digest": active_profile_digest,
        "policy_digest": active_policy_digest,
        "retain_target_ids": tuple(
            sorted(
                item.target_id
                for item in observations
                if item.artifact_action is ProteoformArtifactAction.RETAIN
            )
        ),
        "review_target_ids": tuple(
            sorted(
                item.target_id
                for item in observations
                if item.artifact_action is ProteoformArtifactAction.REVIEW
            )
        ),
        "exclude_target_ids": tuple(
            sorted(
                item.target_id
                for item in observations
                if item.artifact_action is ProteoformArtifactAction.EXCLUDE
            )
        ),
        "platform_level_ids": tuple(
            sorted(
                {
                    level.level_id
                    for item in observations
                    for level in item.factor_levels
                    if level.factor is ProteoformNormalizationFactor.PLATFORM
                }
            )
        ),
        "target_count": len(values),
        "retain_target_count": sum(
            item.artifact_action is ProteoformArtifactAction.RETAIN for item in values
        ),
        "review_target_count": sum(
            item.artifact_action is ProteoformArtifactAction.REVIEW for item in values
        ),
        "exclude_target_count": sum(
            item.artifact_action is ProteoformArtifactAction.EXCLUDE for item in values
        ),
        "evaluable_target_count": sum(
            item.harmonized_support_coordinate_ppm is not None for item in values
        ),
        "values": values,
        "analysis_digest": _M0406_ZERO_DIGEST,
        "parent_target": M0406_PARENT,
        "emits_protein_rna_discordance": False,
        "infers_identity": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_kinase_activity": False,
    }
    analysis_payload["analysis_digest"] = analysis_digest(
        ProteoformHarmonizedAnalysis.model_construct(**analysis_payload)  # type: ignore[arg-type]
    )
    analysis = ProteoformHarmonizedAnalysis.model_validate(analysis_payload, strict=True)
    return (
        analysis,
        manifest,
        tuple(sorted(technical, key=canonical_json_bytes)),
        invariant_diagnostics,
    )


def finding_for(
    code: ProteoformHarmonizationFindingCode,
    *,
    stage_ids: tuple[Identifier, ...] = (),
    target_ids: tuple[Identifier, ...] = (),
    invariant_ids: tuple[Identifier, ...] = (),
) -> ProteoformHarmonizationFinding:
    canonical_stages = tuple(sorted(set(stage_ids)))
    canonical_targets = tuple(sorted(set(target_ids)))
    canonical_invariants = tuple(sorted(set(invariant_ids)))
    suffix = sha256_digest(
        {
            "code": code.value,
            "stage_ids": canonical_stages,
            "target_ids": canonical_targets,
            "invariant_ids": canonical_invariants,
        }
    ).removeprefix("sha256:")
    return ProteoformHarmonizationFinding.model_construct(
        finding_id=f"finding.m0406.{suffix}",
        code=code,
        action=_FINDING_ACTION[code],
        stage_ids=canonical_stages,
        target_ids=canonical_targets,
        invariant_ids=canonical_invariants,
        message=_FINDING_MESSAGE[code],
    )


def _safe_failure_finding(
    request: HarmonizeProteoformAnalysisRequest,
) -> ProteoformHarmonizationFinding | None:
    receipt = request.artifact_receipt
    upstream = {
        ProteoformArtifactDisposition.QUARANTINED: (
            ProteoformHarmonizationFindingCode.UPSTREAM_QUARANTINED
        ),
        ProteoformArtifactDisposition.ABSTAINED: (
            ProteoformHarmonizationFindingCode.UPSTREAM_ABSTAINED
        ),
    }.get(receipt.artifact_disposition)
    if upstream is not None:
        return finding_for(upstream)
    if receipt.evaluation_state is ProteoformArtifactEvaluationState.NOT_EVALUABLE:
        return finding_for(ProteoformHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    if receipt.target_count > request.policy.max_targets or request.support_ledger is None:
        return finding_for(ProteoformHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    if not harmonization_ledger_bindings_close(request):
        return finding_for(ProteoformHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH)
    if matching_harmonization_profile(request) is None:
        return finding_for(ProteoformHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED)
    return None


def expected_harmonization_findings(
    request: HarmonizeProteoformAnalysisRequest,
    manifest: ProteoformTransformationManifest | None = None,
    technical: tuple[ProteoformTechnicalEffectDiagnostic, ...] = (),
    invariants: tuple[ProteoformInvariantDiagnostic, ...] = (),
) -> tuple[ProteoformHarmonizationFinding, ...]:
    safe_failure = _safe_failure_finding(request)
    if safe_failure is not None:
        return (safe_failure,)
    ledger = request.support_ledger
    if ledger is None or manifest is None:
        return (finding_for(ProteoformHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED),)
    findings: list[ProteoformHarmonizationFinding] = []
    excluded = tuple(
        item.target_id
        for item in ledger.observations
        if item.artifact_action is ProteoformArtifactAction.EXCLUDE
    )
    review = tuple(
        item.target_id
        for item in ledger.observations
        if item.artifact_action is ProteoformArtifactAction.REVIEW
    )
    non_evaluable = tuple(
        item.target_id
        for item in ledger.observations
        if item.artifact_action is ProteoformArtifactAction.RETAIN
        and item.state is not ProteoformSupportObservationState.OBSERVED
    )
    if excluded:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT,
                target_ids=excluded,
            )
        )
    if review:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED,
                target_ids=review,
            )
        )
    if non_evaluable:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE,
                target_ids=non_evaluable,
            )
        )
    not_evaluable_stages = tuple(
        item.stage_id
        for item in technical
        if item.status is ProteoformHarmonizationDiagnosticStatus.NOT_EVALUABLE
    )
    failed_stages = tuple(
        item.stage_id
        for item in technical
        if item.status is ProteoformHarmonizationDiagnosticStatus.FAILED
    )
    capped_stages = tuple(
        item.stage_id
        for item in manifest.stages
        if any(shift.state is ProteoformSupportShiftState.CAPPED for shift in item.level_shifts)
    )
    clipped_targets = tuple(
        target_id for item in manifest.stages for target_id in item.clipped_target_ids
    )
    if not_evaluable_stages:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT,
                stage_ids=not_evaluable_stages,
            )
        )
    if capped_stages:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.SHIFT_CAPPED,
                stage_ids=capped_stages,
            )
        )
    if clipped_targets:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.VALUE_CLIPPED,
                target_ids=clipped_targets,
            )
        )
    if failed_stages:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED,
                stage_ids=failed_stages,
            )
        )
    not_evaluable_invariants = tuple(
        item.invariant_id
        for item in invariants
        if item.status is ProteoformHarmonizationDiagnosticStatus.NOT_EVALUABLE
    )
    failed_invariants = tuple(
        item.invariant_id
        for item in invariants
        if item.status is ProteoformHarmonizationDiagnosticStatus.FAILED
    )
    if not_evaluable_invariants:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE,
                invariant_ids=not_evaluable_invariants,
            )
        )
    if failed_invariants:
        findings.append(
            finding_for(
                ProteoformHarmonizationFindingCode.INVARIANT_VIOLATED,
                invariant_ids=failed_invariants,
            )
        )
    return tuple(sorted(findings, key=canonical_json_bytes))


def expected_disposition(
    request: HarmonizeProteoformAnalysisRequest,
    findings: tuple[ProteoformHarmonizationFinding, ...] = (),
) -> ProteoformHarmonizationDisposition:
    upstream = request.artifact_receipt.artifact_disposition
    if upstream is ProteoformArtifactDisposition.QUARANTINED or any(
        item.action is ProteoformHarmonizationFindingAction.QUARANTINE for item in findings
    ):
        return ProteoformHarmonizationDisposition.QUARANTINED
    if upstream is ProteoformArtifactDisposition.ABSTAINED or any(
        item.action is ProteoformHarmonizationFindingAction.ABSTAIN for item in findings
    ):
        return ProteoformHarmonizationDisposition.ABSTAINED
    return ProteoformHarmonizationDisposition.ACCEPTED


def expected_computation_receipt(
    request: HarmonizeProteoformAnalysisRequest,
    disposition: ProteoformHarmonizationDisposition,
    analysis: ProteoformHarmonizedAnalysis | None = None,
    manifest: ProteoformTransformationManifest | None = None,
) -> ProteoformHarmonizationComputationReceipt:
    from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    active = matching_harmonization_profile(request)
    artifact_receipt = request.artifact_receipt
    return ProteoformHarmonizationComputationReceipt(
        artifact_result_digest=artifact_receipt.artifact_result_digest,
        artifact_receipt_digest=artifact_receipt.receipt_digest,
        quality_result_digest=artifact_receipt.quality_result_digest,
        identity_resolution_digest=artifact_receipt.identity_resolution_digest,
        applicability=artifact_receipt.applicability,
        assay_protocol_version=artifact_receipt.assay_protocol_version,
        specimen_processing_version=artifact_receipt.specimen_processing_version,
        controlled_vocabulary_id=artifact_receipt.controlled_vocabulary_id,
        controlled_vocabulary_version=artifact_receipt.controlled_vocabulary_version,
        unit_system_version=artifact_receipt.unit_system_version,
        support_ledger_digest=(
            request.support_ledger.ledger_digest if request.support_ledger is not None else None
        ),
        policy_digest=policy_digest(request.policy),
        configuration_digest=configuration_digest(request.policy),
        profile_digest=profile_digest(active) if active is not None else None,
        analysis_digest=analysis.analysis_digest if analysis is not None else None,
        analysis_platform_level_ids=(analysis.platform_level_ids if analysis is not None else ()),
        analysis_target_count=analysis.target_count if analysis is not None else None,
        analysis_retain_target_count=(
            analysis.retain_target_count if analysis is not None else None
        ),
        analysis_review_target_count=(
            analysis.review_target_count if analysis is not None else None
        ),
        analysis_exclude_target_count=(
            analysis.exclude_target_count if analysis is not None else None
        ),
        analysis_evaluable_target_count=(
            analysis.evaluable_target_count if analysis is not None else None
        ),
        transformation_manifest_digest=(manifest.manifest_digest if manifest is not None else None),
        supersedes_result_digest=request.supersedes_result_digest,
        disposition=disposition,
    )


def expected_support(disposition: ProteoformHarmonizationDisposition) -> SupportDecision:
    if disposition is ProteoformHarmonizationDisposition.ACCEPTED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="proteoform_support_harmonization_accepted",
            rationale="All reviewed technical and protected-invariant diagnostics passed.",
        )
    if disposition is ProteoformHarmonizationDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="proteoform_support_harmonization_quarantined",
            rationale="An artifact firewall, technical effect, or invariant requires review.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="proteoform_support_harmonization_abstained",
        rationale="The upstream screen, support graph, controls, or profile is unsupported.",
    )


def expected_uncertainty(
    disposition: ProteoformHarmonizationDisposition,
) -> UncertaintyProfile:
    del disposition
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0406_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0406_SENSITIVITY_NOTES,
    )


def expected_control_decisions(
    request: HarmonizeProteoformAnalysisRequest,
) -> tuple[ControlDecisionRecord, ...]:
    refs = request.context.references
    records = (
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
    return tuple(sorted(records, key=lambda item: item.role.value))


def harmonization_evidence_index(
    request: HarmonizeProteoformAnalysisRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    active = matching_harmonization_profile(request)
    artifacts = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.artifact_receipt.artifact_reference,
        request.policy.evidence,
        *((active.evidence,) if active is not None else ()),
        *((request.support_ledger.evidence,) if request.support_ledger is not None else ()),
    )
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item for item in artifacts
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0406_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def expected_provenance(request: HarmonizeProteoformAnalysisRequest) -> ProvenanceRecord:
    from glio_proteogen.contracts.m04_06.canonical import (  # noqa: PLC0415
        canonical_request_digest,
        configuration_digest,
    )

    request_hash = canonical_request_digest(request)
    digests = [request.artifact_receipt.receipt_digest, request_hash]
    if request.support_ledger is not None:
        digests.append(request.support_ledger.ledger_digest)
    if request.supersedes_result_digest is not None:
        digests.append(request.supersedes_result_digest)
    return ProvenanceRecord(
        activity_id=f"activity.m0406.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0406_MODULE_ID,
        module_version=M0406_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(digests)),
        configuration_digest=configuration_digest(request.policy),
        consent_decision_id=request.context.references.consent.decision_id,
        consent_state=request.context.references.consent.state,
        consent_policy_version=request.context.references.consent.policy_version,
        consent_evidence_digest=request.context.references.consent.evidence.digest,
        control_decisions=expected_control_decisions(request),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code=M0406_HARMONIZATION_LIMITATION_CODE,
                    statement=(
                        "This output owns only deterministic technical harmonization of "
                        "proteoform support coordinates; it does not infer protein, "
                        "proteoform, complex, subtype, or kinase activity."
                    ),
                ),
                Limitation(
                    code=M0406_SCALE_LIMITATION_CODE,
                    statement=(
                        "support_coordinate_ppm is a bounded fixed-point support coordinate, "
                        "not abundance, effect size, risk, or calibrated probability."
                    ),
                ),
                Limitation(
                    code=M0406_AUTHORITY_LIMITATION_CODE,
                    statement=(
                        "The derived M04-05 receipt proves caller-declared content "
                        "self-consistency, not issuer authenticity or external control authority."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _sign(value: int) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _semantic_tuple_equal(left: tuple[object, ...], right: tuple[object, ...]) -> bool:
    return tuple(sorted(left, key=canonical_json_bytes)) == tuple(
        sorted(right, key=canonical_json_bytes)
    )


def _uncertainty_equal(left: UncertaintyProfile, right: UncertaintyProfile) -> bool:
    left_value = left.model_dump(mode="python", exclude_none=False)
    right_value = right.model_dump(mode="python", exclude_none=False)
    left_value["sensitivity_notes"] = tuple(sorted(left.sensitivity_notes))
    right_value["sensitivity_notes"] = tuple(sorted(right.sensitivity_notes))
    return canonical_json_bytes(left_value) == canonical_json_bytes(right_value)


def _provenance_equal(left: ProvenanceRecord, right: ProvenanceRecord) -> bool:
    left_value = left.model_dump(mode="python", exclude_none=False)
    right_value = right.model_dump(mode="python", exclude_none=False)
    for value in (left_value, right_value):
        value["input_digests"] = tuple(sorted(value["input_digests"]))
        value["control_decisions"] = tuple(
            sorted(value["control_decisions"], key=canonical_json_bytes)
        )
    return canonical_json_bytes(left_value) == canonical_json_bytes(right_value)


expected_findings = expected_harmonization_findings
