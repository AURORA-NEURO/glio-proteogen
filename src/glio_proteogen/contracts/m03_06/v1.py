"""Strict M03-06 fixed-point protein-inference harmonization contracts.

M03-06 consumes an exact compact projection of M03-05 and caller-declared,
content-addressed fixed-point support coordinates.  It does not consume raw
spectra, peptide strings, protein accessions, abundance measurements, or a
learned model output.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m03_01 import (  # noqa: TC001 - Pydantic resolves at runtime
    ProteinInferenceApplicability,
)
from glio_proteogen.contracts.m03_05 import (
    M0305_CONTRACT_VERSION,
    ProteinInferenceArtifactDetectionResult,
    ProteinInferenceArtifactDisposition,
    ProteinInferenceArtifactPosteriorState,
    ProteinInferenceEvidenceUnitKind,
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

M0306_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-06"
M0306_OPERATION: Final = "harmonize_protein_inference_support"
M0306_CONTRACT_VERSION: Final = "1.0.0"
M0306_PARENT: Final = "complex_activity"
M0306_OWNER: Final = "Platform engineering"
M0306_SAFETY_CLASS: Final = "S2"
M0306_GATE: Final = "G1"
M0306_RATE_SCALE: Final = 1_000_000
M0306_MAX_RESIDUAL_PPM: Final = 2 * M0306_RATE_SCALE
M0306_FACTOR_COUNT: Final = 8
M0306_MAX_STAGES: Final = 8
M0306_MAX_UNITS: Final = 512
M0306_MAX_OBSERVATIONS: Final = 512
M0306_MAX_LEVELS_PER_FACTOR: Final = 64
M0306_MAX_LEVEL_SHIFTS: Final = M0306_MAX_STAGES * M0306_MAX_LEVELS_PER_FACTOR
M0306_MAX_STAGE_ESTIMATION_ANCHORS: Final = 128
M0306_MAX_STAGE_VALIDATION_ANCHORS: Final = 128
M0306_MAX_INVARIANTS: Final = 256
M0306_MAX_INVARIANT_UNIT_REFS: Final = 64
M0306_MAX_EVIDENCE_PER_OBSERVATION: Final = 8
M0306_MAX_APPLIED_ADJUSTMENTS: Final = M0306_MAX_OBSERVATIONS * M0306_MAX_STAGES
M0306_MAX_PROFILES: Final = 16
M0306_MAX_APPROVED_VERSIONS: Final = 32
M0306_MAX_EVIDENCE: Final = 16
M0306_MAX_FINDINGS: Final = 15
M0306_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0306_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
_MIN_FACTOR_LEVELS: Final = 2
_M0305_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m03-05+json"
ProteinInferenceHarmonizationIdentifierNamespace = Literal[
    "request",
    "policy",
    "profile",
    "ledger",
    "unit",
    "anchor",
    "group",
    "level",
    "invariant",
    "stage",
    "evidence",
    "reviewer",
]
_OPAQUE_IDENTIFIER_PATTERN: Final = re.compile(
    r"^(request|policy|profile|ledger|unit|anchor|group|level|invariant|stage|evidence|reviewer)"
    r"\.[0-9a-f]{64}$"
)
_LOWERCASE_MEDIA_TYPE_PATTERN: Final = re.compile(
    r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,63}$"
)
M0306_HARMONIZATION_LIMITATION_CODE: Final = "protein_inference_support_harmonization_only"
M0306_SCALE_LIMITATION_CODE: Final = "support_coordinate_not_abundance_or_probability"
M0306_AUTHORITY_LIMITATION_CODE: Final = "artifact_receipt_content_not_authenticated"
M0306_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed protein-inference support harmonization evidence."
)
M0306_SENSITIVITY_NOTES: Final = (
    "Missing, censored, unsupported, and not-applicable support remains explicitly typed.",
    "Artifact-review and artifact-excluded units never train or receive a correction.",
    "Fixed-point support coordinates are not abundance values or calibrated probabilities.",
)
M0306_UNCERTAINTY_RATIONALES: Final = (
    "Measurement uncertainty is not estimated from caller-declared support coordinates.",
    "Sampling uncertainty is not estimated by deterministic paired normalization.",
    "The lower-median fixed-point evaluator fits no probabilistic parameters.",
    "No masked foundation model, autoencoder, or cross-attention model is executed.",
    "Protein, proteoform, complex-activity, and kinase identity remain outside this module.",
    "Support is limited to reviewed technical factors and declared protected invariants.",
    "Transportability requires external assay, cohort, and control-panel validation.",
)


def opaque_harmonization_identifier(
    namespace: ProteinInferenceHarmonizationIdentifierNamespace,
    value: object,
) -> Identifier:
    """Return one namespaced opaque identifier derived from canonical content."""

    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def _opaque_identifier(
    value: Identifier,
    namespace: ProteinInferenceHarmonizationIdentifierNamespace,
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


class ProteinInferenceNormalizationFactor(StrEnum):
    PLATFORM = "platform"
    BATCH = "batch"
    LABORATORY = "laboratory"
    BUILD = "build"
    DEPTH = "depth"
    PURITY = "purity"
    COMPOSITION = "composition"
    PREANALYTIC = "preanalytic"


class ProteinInferenceSupportObservationState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    CENSORED = "censored"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"


class ProteinInferenceArtifactAction(StrEnum):
    RETAIN = "retain"
    REVIEW = "review"
    EXCLUDE = "exclude"


class ProteinInferenceArtifactEvaluationState(StrEnum):
    COMPLETE = "complete"
    NOT_EVALUABLE = "not_evaluable"


class ProteinInferenceSupportShiftState(StrEnum):
    ESTIMATED = "estimated"
    CAPPED = "capped"
    NOT_EVALUABLE = "not_evaluable"


class ProteinInferenceHarmonizationDiagnosticStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class ProteinInferenceSupportInvariantKind(StrEnum):
    SUPPORT_DIRECTION = "support_direction"
    SUPPORT_RANK = "support_rank"
    AMBIGUITY_FRACTION = "ambiguity_fraction"


class ProteinInferenceHarmonizationDisposition(StrEnum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"
    REJECTED = "rejected"


class ProteinInferenceHarmonizationFindingAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"
    REJECT = "reject"


class ProteinInferenceHarmonizationFindingCode(StrEnum):
    UPSTREAM_REJECTED = "upstream_rejected"
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
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_REJECTED: (
        ProteinInferenceHarmonizationFindingAction.REJECT
    ),
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_ABSTAINED: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
    ProteinInferenceHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
    ProteinInferenceHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.SHIFT_CAPPED: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
    ProteinInferenceHarmonizationFindingCode.VALUE_CLIPPED: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
    ProteinInferenceHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
    ProteinInferenceHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE: (
        ProteinInferenceHarmonizationFindingAction.ABSTAIN
    ),
    ProteinInferenceHarmonizationFindingCode.INVARIANT_VIOLATED: (
        ProteinInferenceHarmonizationFindingAction.QUARANTINE
    ),
}

_FINDING_MESSAGE: Final = {
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_REJECTED: (
        "M03-05 rejected the protein-inference artifact evaluation."
    ),
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED: (
        "M03-05 quarantined the protein-inference artifact evaluation."
    ),
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_ABSTAINED: (
        "M03-05 abstained from a protein-inference artifact evaluation."
    ),
    ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        "The projected M03-05 unit graph exceeds the reviewed harmonization envelope."
    ),
    ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH: (
        "The support ledger does not bind the exact compact M03-05 unit projection."
    ),
    ProteinInferenceHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED: (
        "No reviewed protein-inference harmonization profile applies."
    ),
    ProteinInferenceHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT: (
        "At least one M03-05 unit remains excluded from harmonization."
    ),
    ProteinInferenceHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED: (
        "At least one M03-05 unit remains held for review."
    ),
    ProteinInferenceHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE: (
        "At least one retained support coordinate is not evaluable."
    ),
    ProteinInferenceHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT: (
        "At least one technical level lacks reviewed estimation or validation pairs."
    ),
    ProteinInferenceHarmonizationFindingCode.SHIFT_CAPPED: (
        "At least one estimated technical shift reached its reviewed cap."
    ),
    ProteinInferenceHarmonizationFindingCode.VALUE_CLIPPED: (
        "At least one adjusted support coordinate reached the fixed-point boundary."
    ),
    ProteinInferenceHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED: (
        "At least one held-out technical residual did not meet its reduction criterion."
    ),
    ProteinInferenceHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE: (
        "At least one protected support invariant is not evaluable."
    ),
    ProteinInferenceHarmonizationFindingCode.INVARIANT_VIOLATED: (
        "At least one protected support invariant was violated."
    ),
}


class ProteinInferenceNormalizationFactorLevel(FrozenModel):
    factor: ProteinInferenceNormalizationFactor
    level_id: Identifier

    @field_validator("level_id")
    @classmethod
    def level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "factor-level identifier")


class ProteinInferenceArtifactUnitReceipt(FrozenModel):
    unit_id: Identifier
    unit_kind: ProteinInferenceEvidenceUnitKind
    posterior_state: ProteinInferenceArtifactPosteriorState
    action: ProteinInferenceArtifactAction
    signal_score_digest: Sha256Digest
    posterior_digest: Sha256Digest

    @field_validator("unit_id")
    @classmethod
    def unit_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "unit", "artifact-unit identifier")

    @model_validator(mode="after")
    def action_matches_posterior(self) -> ProteinInferenceArtifactUnitReceipt:
        expected = {
            ProteinInferenceArtifactPosteriorState.CLEAR: ProteinInferenceArtifactAction.RETAIN,
            ProteinInferenceArtifactPosteriorState.SUSPECTED: ProteinInferenceArtifactAction.REVIEW,
            ProteinInferenceArtifactPosteriorState.INDETERMINATE: (
                ProteinInferenceArtifactAction.REVIEW
            ),
            ProteinInferenceArtifactPosteriorState.DETECTED: ProteinInferenceArtifactAction.EXCLUDE,
        }[self.posterior_state]
        if self.action is not expected:
            raise ValueError("artifact unit action contradicts its M03-05 posterior")
        return self


class ProteinInferenceArtifactHarmonizationReceipt(FrozenModel):
    receipt_version: Literal["1.0.0"] = M0306_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    artifact_result_digest: Sha256Digest
    artifact_request_digest: Sha256Digest
    artifact_policy_digest: Sha256Digest
    artifact_configuration_digest: Sha256Digest
    artifact_disposition: ProteinInferenceArtifactDisposition
    artifact_support_status: SupportStatus
    artifact_human_review_required: bool
    artifact_completed_at: AwareDatetime
    artifact_quality_receipt_digest: Sha256Digest
    artifact_evidence_ledger_digest: Sha256Digest | None = None
    artifact_profile_digest: Sha256Digest | None = None
    quality_result_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    source_binding_digest: Sha256Digest
    claim_binding_digest: Sha256Digest
    quality_metric_binding_digest: Sha256Digest
    applicability: ProteinInferenceApplicability | None = None
    assay_protocol_version: SemanticVersion
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    evaluation_state: ProteinInferenceArtifactEvaluationState
    unit_count: int = Field(ge=0, le=M0306_MAX_UNITS)
    units: tuple[ProteinInferenceArtifactUnitReceipt, ...] = Field(
        default=(), max_length=M0306_MAX_UNITS
    )
    unit_binding_digest: Sha256Digest
    receipt_digest: Sha256Digest

    @field_validator("units")
    @classmethod
    def units_are_canonical(
        cls,
        values: tuple[ProteinInferenceArtifactUnitReceipt, ...],
    ) -> tuple[ProteinInferenceArtifactUnitReceipt, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_is_closed(self) -> ProteinInferenceArtifactHarmonizationReceipt:
        from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
            artifact_receipt_digest,
            unit_binding_digest,
        )

        unit_ids = tuple(item.unit_id for item in self.units)
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("artifact harmonization receipt unit identifiers must be unique")
        complete = self.evaluation_state is ProteinInferenceArtifactEvaluationState.COMPLETE
        if complete:
            if (
                not self.units
                or len(self.units) != self.unit_count
                or self.artifact_evidence_ledger_digest is None
                or self.artifact_profile_digest is None
                or self.applicability is None
            ):
                raise ValueError("complete artifact receipt requires its exact screened unit graph")
            expected_disposition = (
                ProteinInferenceArtifactDisposition.QUARANTINED
                if any(
                    item.posterior_state
                    in {
                        ProteinInferenceArtifactPosteriorState.SUSPECTED,
                        ProteinInferenceArtifactPosteriorState.DETECTED,
                    }
                    for item in self.units
                )
                else ProteinInferenceArtifactDisposition.ABSTAINED
                if any(
                    item.posterior_state is ProteinInferenceArtifactPosteriorState.INDETERMINATE
                    for item in self.units
                )
                else ProteinInferenceArtifactDisposition.CLEARED
            )
            if self.artifact_disposition is not expected_disposition:
                raise ValueError("artifact receipt disposition contradicts its unit posteriors")
        elif self.units or self.unit_count != 0:
            raise ValueError("non-evaluable artifact receipt cannot project successful units")
        if (
            self.artifact_disposition is ProteinInferenceArtifactDisposition.CLEARED
            and not complete
        ):
            raise ValueError("cleared artifact receipt must carry a complete screen")
        expected_support = {
            ProteinInferenceArtifactDisposition.CLEARED: SupportStatus.SUPPORTED,
            ProteinInferenceArtifactDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
            ProteinInferenceArtifactDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
            ProteinInferenceArtifactDisposition.REJECTED: SupportStatus.UNSUPPORTED,
        }[self.artifact_disposition]
        if self.artifact_support_status is not expected_support:
            raise ValueError("artifact receipt disposition and support status contradict")
        if self.artifact_human_review_required != (
            self.artifact_disposition is not ProteinInferenceArtifactDisposition.CLEARED
        ):
            raise ValueError("artifact receipt disposition and review requirement contradict")
        expected_artifact_id = (
            f"result.m0305.{self.artifact_request_digest.removeprefix('sha256:')}"
        )
        if (
            self.artifact_reference.artifact_id != expected_artifact_id
            or self.artifact_reference.version != M0305_CONTRACT_VERSION
            or self.artifact_reference.media_type != _M0305_RESULT_MEDIA_TYPE
        ):
            raise ValueError("artifact reference does not identify the exact M03-05 result ABI")
        if (
            self.artifact_reference.digest != self.artifact_result_digest
            or self.unit_binding_digest != unit_binding_digest(self.units)
            or self.receipt_digest != artifact_receipt_digest(self)
        ):
            raise ValueError("artifact harmonization receipt digest closure failed")
        return self


class ProteinInferenceSupportObservation(FrozenModel):
    unit_id: Identifier
    unit_kind: ProteinInferenceEvidenceUnitKind
    artifact_posterior_state: ProteinInferenceArtifactPosteriorState
    artifact_action: ProteinInferenceArtifactAction
    artifact_signal_score_digest: Sha256Digest
    artifact_posterior_digest: Sha256Digest
    anchor_id: Identifier
    biological_group_id: Identifier
    state: ProteinInferenceSupportObservationState
    support_coordinate_ppm: int | None = Field(default=None, ge=0, le=M0306_RATE_SCALE)
    censoring_upper_bound_ppm: int | None = Field(default=None, ge=0, le=M0306_RATE_SCALE)
    is_calibrated_probability: Literal[False] = False
    factor_levels: tuple[ProteinInferenceNormalizationFactorLevel, ...] = Field(
        min_length=M0306_FACTOR_COUNT,
        max_length=M0306_FACTOR_COUNT,
    )
    evidence: tuple[ArtifactReference, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_EVIDENCE_PER_OBSERVATION,
    )

    @field_validator("unit_id")
    @classmethod
    def unit_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "unit", "support-observation unit identifier")

    @field_validator("anchor_id")
    @classmethod
    def anchor_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "anchor", "support-observation anchor identifier")

    @field_validator("biological_group_id")
    @classmethod
    def group_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "group", "support-observation group identifier")

    @field_validator("factor_levels", "evidence")
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
    def observation_is_typed_and_closed(self) -> ProteinInferenceSupportObservation:
        factors = tuple(item.factor for item in self.factor_levels)
        if len(factors) != len(set(factors)) or set(factors) != set(
            ProteinInferenceNormalizationFactor
        ):
            raise ValueError("support observation requires every technical factor exactly once")
        if len({item.digest for item in self.evidence}) != len(self.evidence):
            raise ValueError("support observation evidence digests must be unique")
        expected_action = {
            ProteinInferenceArtifactPosteriorState.CLEAR: ProteinInferenceArtifactAction.RETAIN,
            ProteinInferenceArtifactPosteriorState.SUSPECTED: ProteinInferenceArtifactAction.REVIEW,
            ProteinInferenceArtifactPosteriorState.INDETERMINATE: (
                ProteinInferenceArtifactAction.REVIEW
            ),
            ProteinInferenceArtifactPosteriorState.DETECTED: ProteinInferenceArtifactAction.EXCLUDE,
        }[self.artifact_posterior_state]
        if self.artifact_action is not expected_action:
            raise ValueError("support observation action contradicts its artifact posterior")
        if self.state is ProteinInferenceSupportObservationState.OBSERVED:
            if self.support_coordinate_ppm is None or self.censoring_upper_bound_ppm is not None:
                raise ValueError("observed support requires only its fixed-point coordinate")
        elif self.state is ProteinInferenceSupportObservationState.CENSORED:
            if self.support_coordinate_ppm is not None or self.censoring_upper_bound_ppm is None:
                raise ValueError("censored support requires only its upper bound")
        elif self.support_coordinate_ppm is not None or self.censoring_upper_bound_ppm is not None:
            raise ValueError("non-observed support cannot carry a numeric coordinate")
        return self


class ProteinInferenceSupportInvariant(FrozenModel):
    invariant_id: Identifier
    kind: ProteinInferenceSupportInvariantKind
    left_unit_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_INVARIANT_UNIT_REFS,
    )
    right_unit_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_INVARIANT_UNIT_REFS,
    )

    @field_validator("invariant_id")
    @classmethod
    def invariant_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "invariant", "support-invariant identifier")

    @field_validator("left_unit_ids", "right_unit_ids")
    @classmethod
    def members_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def member_shape_is_closed(self) -> ProteinInferenceSupportInvariant:
        if self.kind is ProteinInferenceSupportInvariantKind.SUPPORT_RANK and (
            len(self.left_unit_ids) != 1 or len(self.right_unit_ids) != 1
        ):
            raise ValueError("support-rank invariant requires exactly one unit per side")
        if (
            len(self.left_unit_ids) != len(set(self.left_unit_ids))
            or len(self.right_unit_ids) != len(set(self.right_unit_ids))
            or set(self.left_unit_ids) & set(self.right_unit_ids)
        ):
            raise ValueError("support invariant sides must be unique and disjoint")
        return self


def _unit_receipt_from_observation(
    observation: ProteinInferenceSupportObservation,
) -> ProteinInferenceArtifactUnitReceipt:
    return ProteinInferenceArtifactUnitReceipt(
        unit_id=observation.unit_id,
        unit_kind=observation.unit_kind,
        posterior_state=observation.artifact_posterior_state,
        action=observation.artifact_action,
        signal_score_digest=observation.artifact_signal_score_digest,
        posterior_digest=observation.artifact_posterior_digest,
    )


class ProteinInferenceSupportLedger(FrozenModel):
    ledger_id: Identifier
    version: SemanticVersion
    artifact_result_digest: Sha256Digest
    artifact_receipt_digest: Sha256Digest
    artifact_unit_binding_digest: Sha256Digest
    observations: tuple[ProteinInferenceSupportObservation, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_OBSERVATIONS,
    )
    invariants: tuple[ProteinInferenceSupportInvariant, ...] = Field(
        min_length=3,
        max_length=M0306_MAX_INVARIANTS,
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
    ) -> ProteinInferenceSupportLedger:
        from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
            support_ledger_digest,
            unit_binding_digest,
        )

        unit_ids = tuple(item.unit_id for item in self.observations)
        invariant_ids = tuple(item.invariant_id for item in self.invariants)
        if len(unit_ids) != len(set(unit_ids)):
            raise ValueError("support observation unit identifiers must be unique")
        if {item.kind for item in self.invariants} != set(ProteinInferenceSupportInvariantKind):
            raise ValueError("support ledger requires every protected invariant kind")
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("support invariant identifiers must be unique")
        projected = tuple(_unit_receipt_from_observation(item) for item in self.observations)
        if self.artifact_unit_binding_digest != unit_binding_digest(projected):
            raise ValueError("support ledger unit binding does not match its observations")
        _validate_invariant_members(self.observations, self.invariants)
        if self.ledger_digest != support_ledger_digest(self):
            raise ValueError("support ledger digest does not match its content")
        return self


def _validate_invariant_members(
    observations: tuple[ProteinInferenceSupportObservation, ...],
    invariants: tuple[ProteinInferenceSupportInvariant, ...],
) -> None:
    by_id = {item.unit_id: item for item in observations}
    for invariant in invariants:
        members = set(invariant.left_unit_ids) | set(invariant.right_unit_ids)
        if not members.issubset(by_id):
            raise ValueError("support invariant references an unknown unit")
        left = tuple(by_id[item] for item in invariant.left_unit_ids)
        right = tuple(by_id[item] for item in invariant.right_unit_ids)
        if invariant.kind is ProteinInferenceSupportInvariantKind.SUPPORT_DIRECTION:
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
        elif invariant.kind is ProteinInferenceSupportInvariantKind.SUPPORT_RANK:
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
                != {ProteinInferenceEvidenceUnitKind.AMBIGUITY_CLASS}
                or {item.unit_kind for item in right}
                != {ProteinInferenceEvidenceUnitKind.PROTEIN_GROUP}
                or {item.anchor_id for item in left} != {item.anchor_id for item in right}
                or len({item.anchor_id for item in left}) != len(left)
                or len({item.anchor_id for item in right}) != len(right)
            ):
                raise ValueError("ambiguity invariant requires matched ambiguity and group anchors")


class ProteinInferenceNormalizationStage(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0306_MAX_STAGES)
    factor: ProteinInferenceNormalizationFactor
    reference_level_id: Identifier
    estimation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    validation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_STAGE_VALIDATION_ANCHORS,
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
    def anchor_sets_are_disjoint(self) -> ProteinInferenceNormalizationStage:
        if (
            len(self.estimation_anchor_ids) != len(set(self.estimation_anchor_ids))
            or len(self.validation_anchor_ids) != len(set(self.validation_anchor_ids))
            or set(self.estimation_anchor_ids) & set(self.validation_anchor_ids)
        ):
            raise ValueError("estimation and validation anchors must be unique and disjoint")
        return self


class ProteinInferenceHarmonizationProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    applicability: ProteinInferenceApplicability
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_APPROVED_VERSIONS,
    )
    approved_controlled_vocabulary_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_APPROVED_VERSIONS,
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_APPROVED_VERSIONS,
    )
    stages: tuple[ProteinInferenceNormalizationStage, ...] = Field(
        min_length=M0306_MAX_STAGES,
        max_length=M0306_MAX_STAGES,
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
        values: tuple[ProteinInferenceNormalizationStage, ...],
    ) -> tuple[ProteinInferenceNormalizationStage, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def profile_is_closed(self) -> ProteinInferenceHarmonizationProfile:
        domains = (
            self.approved_assay_protocol_versions,
            self.approved_controlled_vocabulary_versions,
            self.approved_unit_system_versions,
        )
        if any(len(values) != len(set(values)) for values in domains):
            raise ValueError("harmonization profile versions must be unique")
        if {item.factor for item in self.stages} != set(ProteinInferenceNormalizationFactor):
            raise ValueError("harmonization profile requires every technical factor exactly once")
        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0306_MAX_STAGES + 1)):
            raise ValueError("harmonization stages require exact ordered ordinals")
        if len({item.stage_id for item in self.stages}) != len(self.stages):
            raise ValueError("harmonization stage identifiers must be unique")
        return self


class ProteinInferenceHarmonizationPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_units: int = Field(gt=0, le=M0306_MAX_UNITS)
    max_invariants: int = Field(ge=3, le=M0306_MAX_INVARIANTS)
    max_absolute_shift_ppm: int = Field(gt=0, le=M0306_RATE_SCALE)
    technical_effect_tolerance_ppm: int = Field(ge=0, le=M0306_RATE_SCALE)
    biological_invariant_tolerance_ppm: int = Field(ge=0, le=M0306_RATE_SCALE)
    min_estimation_pairs_per_level: int = Field(
        gt=0,
        le=M0306_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    min_validation_pairs_per_level: int = Field(
        gt=0,
        le=M0306_MAX_STAGE_VALIDATION_ANCHORS,
    )
    profiles: tuple[ProteinInferenceHarmonizationProfile, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_PROFILES,
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
        values: tuple[ProteinInferenceHarmonizationProfile, ...],
    ) -> tuple[ProteinInferenceHarmonizationProfile, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def profile_domains_are_pairwise_disjoint(self) -> ProteinInferenceHarmonizationPolicy:
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
    request: HarmonizeProteinInferenceSupportRequest,
) -> ProteinInferenceHarmonizationProfile | None:
    receipt = request.artifact_receipt
    if receipt.applicability is None:
        return None
    matches = tuple(
        item
        for item in request.policy.profiles
        if item.applicability is receipt.applicability
        and receipt.assay_protocol_version in item.approved_assay_protocol_versions
        and receipt.controlled_vocabulary_version in item.approved_controlled_vocabulary_versions
        and receipt.unit_system_version in item.approved_unit_system_versions
    )
    return matches[0] if len(matches) == 1 else None


class HarmonizeProteinInferenceSupportRequest(FrozenModel):
    operation: Literal["harmonize_protein_inference_support"] = M0306_OPERATION
    contract_version: Literal["1.0.0"] = M0306_CONTRACT_VERSION
    context: ExecutionContext
    artifact_receipt: ProteinInferenceArtifactHarmonizationReceipt
    support_ledger: ProteinInferenceSupportLedger | None = None
    policy: ProteinInferenceHarmonizationPolicy
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_closed(self) -> HarmonizeProteinInferenceSupportRequest:
        from glio_proteogen.contracts.m03_06.canonical import configuration_digest  # noqa: PLC0415

        _require_authorized_context(self.context)
        _opaque_identifier(
            self.context.request_id,
            "request",
            "harmonization request identifier",
        )
        receipt = self.artifact_receipt
        if max(receipt.artifact_completed_at, self.policy.reviewed_at) > self.context.occurred_at:
            raise ValueError("M03-06 inputs cannot postdate harmonization")
        refs = self.context.references
        if refs.identity_lineage.binding_digest != receipt.identity_resolution_digest:
            raise ValueError("identity control does not bind the compact M03-05 receipt")
        if refs.quality.evidence.digest != receipt.quality_result_digest:
            raise ValueError("quality control does not bind the compact M03-04 result")
        if refs.approved_configuration.evidence.digest != configuration_digest(self.policy):
            raise ValueError("approved configuration does not bind the harmonization policy")
        _validate_artifact_reference_consistency(self)
        supported_shape = (
            receipt.evaluation_state is ProteinInferenceArtifactEvaluationState.COMPLETE
            and receipt.artifact_disposition is ProteinInferenceArtifactDisposition.CLEARED
            and receipt.unit_count <= self.policy.max_units
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
            M0306_MAX_CANONICAL_REQUEST_BYTES
        ):
            raise ValueError("canonical M03-06 request exceeds its ingress ceiling")
        return self


def _validate_active_profile_members(
    profile: ProteinInferenceHarmonizationProfile,
    ledger: ProteinInferenceSupportLedger,
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
            or len(levels) > M0306_MAX_LEVELS_PER_FACTOR
        ):
            raise ValueError("active harmonization stage has an invalid factor-level domain")


def _artifact_references(
    request: HarmonizeProteinInferenceSupportRequest,
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
    request: HarmonizeProteinInferenceSupportRequest,
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
) -> ProteinInferenceArtifactHarmonizationReceipt:
    """Project a fully validated genuine M03-05 result into the M03-06 boundary."""

    result = ProteinInferenceArtifactDetectionResult.model_validate_json(
        canonical_json_bytes(value),
        strict=True,
    )
    quality = result.request.quality_receipt
    score_groups = {
        posterior.unit_id: tuple(
            sorted(
                (item for item in result.signal_scores if item.unit_id == posterior.unit_id),
                key=canonical_json_bytes,
            )
        )
        for posterior in result.artifact_posteriors
    }
    retained = set(result.exclusion_mask.retain_unit_ids)
    review = set(result.exclusion_mask.review_unit_ids)
    excluded = set(result.exclusion_mask.exclude_unit_ids)
    units: list[ProteinInferenceArtifactUnitReceipt] = []
    for posterior in result.artifact_posteriors:
        scores = score_groups[posterior.unit_id]
        if not scores:
            raise ValueError("M03-05 posterior lacks its exact signal-score projection")
        kinds = {item.unit_kind for item in scores}
        if len(kinds) != 1:
            raise ValueError("M03-05 unit signal scores contradict their unit kind")
        action = (
            ProteinInferenceArtifactAction.RETAIN
            if posterior.unit_id in retained
            else ProteinInferenceArtifactAction.REVIEW
            if posterior.unit_id in review
            else ProteinInferenceArtifactAction.EXCLUDE
            if posterior.unit_id in excluded
            else None
        )
        if action is None:
            raise ValueError("M03-05 posterior is absent from the exclusion-mask partition")
        units.append(
            ProteinInferenceArtifactUnitReceipt(
                unit_id=posterior.unit_id,
                unit_kind=next(iter(kinds)),
                posterior_state=posterior.state,
                action=action,
                signal_score_digest=sha256_digest(scores),
                posterior_digest=sha256_digest(posterior),
            )
        )
    canonical_units = tuple(sorted(units, key=canonical_json_bytes))
    from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
        artifact_receipt_digest,
        unit_binding_digest,
    )

    payload: dict[str, object] = {
        "receipt_version": M0306_CONTRACT_VERSION,
        "artifact_reference": ArtifactReference(
            artifact_id=result.result_id,
            version=result.result_version,
            digest=result.result_digest,
            media_type=_M0305_RESULT_MEDIA_TYPE,
        ),
        "artifact_result_digest": result.result_digest,
        "artifact_request_digest": result.request_digest,
        "artifact_policy_digest": result.policy_digest,
        "artifact_configuration_digest": result.configuration_digest,
        "artifact_disposition": result.disposition,
        "artifact_support_status": result.support.status,
        "artifact_human_review_required": result.human_review_required,
        "artifact_completed_at": result.completed_at,
        "artifact_quality_receipt_digest": result.receipt.artifact_quality_receipt_digest,
        "artifact_evidence_ledger_digest": result.receipt.evidence_ledger_digest,
        "artifact_profile_digest": result.receipt.profile_digest,
        "quality_result_digest": quality.quality_result_digest,
        "identity_resolution_digest": quality.identity_resolution_digest,
        "source_binding_digest": quality.source_binding_digest,
        "claim_binding_digest": quality.claim_binding_digest,
        "quality_metric_binding_digest": quality.quality_metric_binding_digest,
        "applicability": quality.applicability,
        "assay_protocol_version": quality.assay_protocol_version,
        "controlled_vocabulary_id": quality.controlled_vocabulary_id,
        "controlled_vocabulary_version": quality.controlled_vocabulary_version,
        "unit_system_version": quality.unit_system_version,
        "evaluation_state": (
            ProteinInferenceArtifactEvaluationState.COMPLETE
            if canonical_units
            else ProteinInferenceArtifactEvaluationState.NOT_EVALUABLE
        ),
        "unit_count": len(canonical_units),
        "units": canonical_units,
        "unit_binding_digest": unit_binding_digest(canonical_units),
        "receipt_digest": M0306_ZERO_DIGEST,
    }
    payload["receipt_digest"] = artifact_receipt_digest(payload)
    return ProteinInferenceArtifactHarmonizationReceipt.model_validate(payload, strict=True)


def harmonization_ledger_bindings_close(
    request: HarmonizeProteinInferenceSupportRequest,
) -> bool:
    ledger = request.support_ledger
    receipt = request.artifact_receipt
    return ledger is not None and (
        ledger.artifact_result_digest == receipt.artifact_result_digest
        and ledger.artifact_receipt_digest == receipt.receipt_digest
        and ledger.artifact_unit_binding_digest == receipt.unit_binding_digest
        and len(ledger.observations) == receipt.unit_count
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
        raise ValueError("protein-inference harmonization is not authorized")


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


class ProteinInferenceSupportLevelShift(FrozenModel):
    level_id: Identifier
    state: ProteinInferenceSupportShiftState
    estimated_shift_ppm: int | None = Field(
        default=None,
        ge=-M0306_RATE_SCALE,
        le=M0306_RATE_SCALE,
    )
    applied_shift_ppm: int | None = Field(
        default=None,
        ge=-M0306_RATE_SCALE,
        le=M0306_RATE_SCALE,
    )
    estimation_pair_count: int = Field(ge=0, le=M0306_MAX_OBSERVATIONS)
    validation_pair_count: int = Field(ge=0, le=M0306_MAX_OBSERVATIONS)
    pre_validation_residual_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0306_RATE_SCALE,
    )
    post_validation_residual_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0306_MAX_RESIDUAL_PPM,
    )
    unit: Literal["support_coordinate_ppm"] = "support_coordinate_ppm"

    @field_validator("level_id")
    @classmethod
    def level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "support-level-shift identifier")

    @model_validator(mode="after")
    def shift_shape_matches_state(self) -> ProteinInferenceSupportLevelShift:
        numeric = (
            self.estimated_shift_ppm,
            self.applied_shift_ppm,
            self.pre_validation_residual_ppm,
            self.post_validation_residual_ppm,
        )
        if self.state is ProteinInferenceSupportShiftState.NOT_EVALUABLE:
            if any(item is not None for item in numeric):
                raise ValueError("not-evaluable support shift cannot carry numeric estimates")
        elif any(item is None for item in numeric):
            raise ValueError("evaluable support shift requires estimates and validation residuals")
        elif (
            self.state is ProteinInferenceSupportShiftState.ESTIMATED
            and self.applied_shift_ppm != self.estimated_shift_ppm
        ):
            raise ValueError("estimated fixed-point shift must be exact and below its cap")
        return self


class ProteinInferenceAppliedSupportAdjustment(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0306_MAX_STAGES)
    factor: ProteinInferenceNormalizationFactor
    level_id: Identifier
    shift_ppm: int = Field(ge=-M0306_RATE_SCALE, le=M0306_RATE_SCALE)
    unit: Literal["support_coordinate_ppm"] = "support_coordinate_ppm"

    @field_validator("stage_id")
    @classmethod
    def stage_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "stage", "applied-adjustment stage identifier")

    @field_validator("level_id")
    @classmethod
    def level_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "level", "applied-adjustment level identifier")


class ProteinInferenceStageTransformation(FrozenModel):
    stage_id: Identifier
    ordinal: int = Field(ge=1, le=M0306_MAX_STAGES)
    factor: ProteinInferenceNormalizationFactor
    method: Literal["paired_lower_median_fixed_point_shift"] = (
        "paired_lower_median_fixed_point_shift"
    )
    reference_level_id: Identifier
    estimation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    validation_anchor_ids: tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_STAGE_VALIDATION_ANCHORS,
    )
    maximum_absolute_shift_ppm: int = Field(gt=0, le=M0306_RATE_SCALE)
    minimum_estimation_pairs: int = Field(
        gt=0,
        le=M0306_MAX_STAGE_ESTIMATION_ANCHORS,
    )
    minimum_validation_pairs: int = Field(
        gt=0,
        le=M0306_MAX_STAGE_VALIDATION_ANCHORS,
    )
    level_shifts: tuple[ProteinInferenceSupportLevelShift, ...] = Field(
        min_length=2,
        max_length=M0306_MAX_LEVELS_PER_FACTOR,
    )
    clipped_unit_ids: tuple[Identifier, ...] = Field(
        default=(),
        max_length=M0306_MAX_UNITS,
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

    @field_validator("clipped_unit_ids")
    @classmethod
    def clipped_unit_identifiers_are_canonical(
        cls,
        values: tuple[Identifier, ...],
    ) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "unit", "clipped-unit identifier")
        return tuple(sorted(values))

    @field_validator("level_shifts")
    @classmethod
    def level_shifts_are_canonical(
        cls,
        values: tuple[ProteinInferenceSupportLevelShift, ...],
    ) -> tuple[ProteinInferenceSupportLevelShift, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def transformation_is_closed(  # noqa: PLR0912 - ordered transformation audit
        self,
    ) -> ProteinInferenceStageTransformation:
        if (
            len(self.estimation_anchor_ids) != len(set(self.estimation_anchor_ids))
            or len(self.validation_anchor_ids) != len(set(self.validation_anchor_ids))
            or set(self.estimation_anchor_ids) & set(self.validation_anchor_ids)
            or len(self.clipped_unit_ids) != len(set(self.clipped_unit_ids))
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
            if shift.state is ProteinInferenceSupportShiftState.NOT_EVALUABLE:
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
            if shift.state is ProteinInferenceSupportShiftState.ESTIMATED:
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
        if reference_shift.state is not ProteinInferenceSupportShiftState.NOT_EVALUABLE and (
            reference_shift.estimated_shift_ppm != 0
            or reference_shift.applied_shift_ppm != 0
            or reference_shift.pre_validation_residual_ppm != 0
            or reference_shift.post_validation_residual_ppm != 0
        ):
            raise ValueError("evaluable reference-level shift must be exact zero")
        return self


class ProteinInferenceTransformationManifest(FrozenModel):
    artifact_receipt_digest: Sha256Digest
    support_ledger_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    stages: tuple[ProteinInferenceStageTransformation, ...] = Field(
        min_length=M0306_MAX_STAGES,
        max_length=M0306_MAX_STAGES,
    )
    manifest_digest: Sha256Digest

    @field_validator("stages")
    @classmethod
    def stages_are_ordered(
        cls,
        values: tuple[ProteinInferenceStageTransformation, ...],
    ) -> tuple[ProteinInferenceStageTransformation, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def manifest_is_content_addressed(self) -> ProteinInferenceTransformationManifest:
        from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
            transformation_manifest_digest,
        )

        if tuple(item.ordinal for item in self.stages) != tuple(range(1, M0306_MAX_STAGES + 1)):
            raise ValueError("transformation manifest stage ordinals are not exact")
        if len({item.stage_id for item in self.stages}) != M0306_MAX_STAGES:
            raise ValueError("transformation manifest stage identifiers must be unique")
        if {item.factor for item in self.stages} != set(ProteinInferenceNormalizationFactor):
            raise ValueError("transformation manifest must cover all eight factors")
        if self.manifest_digest != transformation_manifest_digest(self):
            raise ValueError("transformation manifest digest does not match its content")
        return self


class ProteinInferenceTechnicalEffectDiagnostic(FrozenModel):
    stage_id: Identifier
    factor: ProteinInferenceNormalizationFactor
    before_residual_ppm: int | None = Field(default=None, ge=0, le=M0306_RATE_SCALE)
    after_residual_ppm: int | None = Field(default=None, ge=0, le=M0306_MAX_RESIDUAL_PPM)
    tolerance_ppm: int = Field(ge=0, le=M0306_RATE_SCALE)
    capped: bool
    clipped: bool
    status: ProteinInferenceHarmonizationDiagnosticStatus

    @field_validator("stage_id")
    @classmethod
    def stage_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "stage", "technical-diagnostic stage identifier")

    @model_validator(mode="after")
    def diagnostic_status_is_exact(self) -> ProteinInferenceTechnicalEffectDiagnostic:
        if (self.before_residual_ppm is None) != (self.after_residual_ppm is None):
            raise ValueError("technical residuals must be jointly present or absent")
        if self.before_residual_ppm is None or self.after_residual_ppm is None:
            expected = ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
        elif (
            not self.capped
            and not self.clipped
            and self.after_residual_ppm <= self.tolerance_ppm
            and (
                self.after_residual_ppm < self.before_residual_ppm
                or self.after_residual_ppm == self.before_residual_ppm == 0
            )
        ):
            expected = ProteinInferenceHarmonizationDiagnosticStatus.PASSED
        else:
            expected = ProteinInferenceHarmonizationDiagnosticStatus.FAILED
        if self.status is not expected:
            raise ValueError("technical residuals contradict their deterministic status")
        return self


class ProteinInferenceInvariantDiagnostic(FrozenModel):
    invariant_id: Identifier
    kind: ProteinInferenceSupportInvariantKind
    before_score_ppm: int | None = Field(
        default=None,
        ge=-M0306_RATE_SCALE,
        le=M0306_RATE_SCALE,
    )
    after_score_ppm: int | None = Field(
        default=None,
        ge=-M0306_RATE_SCALE,
        le=M0306_RATE_SCALE,
    )
    tolerance_ppm: int = Field(ge=0, le=M0306_RATE_SCALE)
    status: ProteinInferenceHarmonizationDiagnosticStatus

    @field_validator("invariant_id")
    @classmethod
    def invariant_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "invariant", "invariant-diagnostic identifier")

    @model_validator(mode="after")
    def diagnostic_status_is_exact(self) -> ProteinInferenceInvariantDiagnostic:
        before = self.before_score_ppm
        after = self.after_score_ppm
        if (before is None) != (after is None):
            raise ValueError("protected support scores must be jointly present or absent")
        if before is None or after is None:
            expected = ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
        elif self.kind is ProteinInferenceSupportInvariantKind.AMBIGUITY_FRACTION:
            expected = (
                ProteinInferenceHarmonizationDiagnosticStatus.PASSED
                if abs(after - before) <= self.tolerance_ppm
                else ProteinInferenceHarmonizationDiagnosticStatus.FAILED
            )
        else:
            expected = (
                ProteinInferenceHarmonizationDiagnosticStatus.PASSED
                if _sign(before) != 0
                and _sign(before) == _sign(after)
                and abs(after - before) <= self.tolerance_ppm
                else ProteinInferenceHarmonizationDiagnosticStatus.FAILED
            )
        if self.status is not expected:
            raise ValueError("protected support scores contradict their deterministic status")
        return self


class ProteinInferenceHarmonizedSupportValue(FrozenModel):
    unit_id: Identifier
    unit_kind: ProteinInferenceEvidenceUnitKind
    artifact_action: ProteinInferenceArtifactAction
    input_state: ProteinInferenceSupportObservationState
    output_state: ProteinInferenceSupportObservationState
    input_support_coordinate_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0306_RATE_SCALE,
    )
    harmonized_support_coordinate_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0306_RATE_SCALE,
    )
    censoring_upper_bound_ppm: int | None = Field(
        default=None,
        ge=0,
        le=M0306_RATE_SCALE,
    )
    is_calibrated_probability: Literal[False] = False
    source_observation_digest: Sha256Digest
    adjustments: tuple[ProteinInferenceAppliedSupportAdjustment, ...] = Field(
        default=(),
        max_length=M0306_MAX_STAGES,
    )
    was_clipped: bool

    @field_validator("unit_id")
    @classmethod
    def unit_identifier_is_opaque(cls, value: Identifier) -> Identifier:
        return _opaque_identifier(value, "unit", "harmonized-value unit identifier")

    @field_validator("adjustments")
    @classmethod
    def adjustments_are_ordered(
        cls,
        values: tuple[ProteinInferenceAppliedSupportAdjustment, ...],
    ) -> tuple[ProteinInferenceAppliedSupportAdjustment, ...]:
        return tuple(sorted(values, key=lambda item: item.ordinal))

    @model_validator(mode="after")
    def value_shape_is_closed(self) -> ProteinInferenceHarmonizedSupportValue:
        ordinals = tuple(item.ordinal for item in self.adjustments)
        if len(ordinals) != len(set(ordinals)):
            raise ValueError("harmonized support adjustments must be unique by ordinal")
        if self.output_state is not self.input_state:
            raise ValueError("harmonization cannot relabel a support observation state")
        traversable = (
            self.artifact_action is ProteinInferenceArtifactAction.RETAIN
            and self.input_state is ProteinInferenceSupportObservationState.OBSERVED
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
                    adjustment.shift_ppm != 0 and (shifted <= 0 or shifted >= M0306_RATE_SCALE)
                )
                expected = max(0, min(M0306_RATE_SCALE, shifted))
            if self.harmonized_support_coordinate_ppm != expected or self.was_clipped != clipped:
                raise ValueError("harmonized support contradicts its exact applied adjustments")
            return self
        if (
            self.harmonized_support_coordinate_ppm is not None
            or self.adjustments
            or self.was_clipped
        ):
            raise ValueError("held or non-observed support cannot carry a harmonized value")
        if self.input_state is ProteinInferenceSupportObservationState.OBSERVED:
            if (
                self.input_support_coordinate_ppm is None
                or self.censoring_upper_bound_ppm is not None
            ):
                raise ValueError("held observed support requires only its input coordinate")
        elif self.input_state is ProteinInferenceSupportObservationState.CENSORED:
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


class ProteinInferenceHarmonizedAnalysis(FrozenModel):
    analysis_id: Identifier
    artifact_result_digest: Sha256Digest
    support_ledger_digest: Sha256Digest
    artifact_unit_binding_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    retain_unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0306_MAX_UNITS)
    review_unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0306_MAX_UNITS)
    exclude_unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0306_MAX_UNITS)
    values: tuple[ProteinInferenceHarmonizedSupportValue, ...] = Field(
        min_length=1,
        max_length=M0306_MAX_OBSERVATIONS,
    )
    analysis_digest: Sha256Digest
    parent_target: Literal["complex_activity"] = M0306_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False

    @field_validator("retain_unit_ids", "review_unit_ids", "exclude_unit_ids")
    @classmethod
    def partitions_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        for value in values:
            _opaque_identifier(value, "unit", "analysis partition unit identifier")
        return tuple(sorted(values))

    @field_validator("values")
    @classmethod
    def values_are_canonical(
        cls,
        values: tuple[ProteinInferenceHarmonizedSupportValue, ...],
    ) -> tuple[ProteinInferenceHarmonizedSupportValue, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def analysis_is_content_addressed(self) -> ProteinInferenceHarmonizedAnalysis:
        from glio_proteogen.contracts.m03_06.canonical import analysis_digest  # noqa: PLC0415

        partitions = (
            self.retain_unit_ids,
            self.review_unit_ids,
            self.exclude_unit_ids,
        )
        if any(len(values) != len(set(values)) for values in partitions):
            raise ValueError("harmonized analysis partitions require unique units")
        if any(
            set(left) & set(right)
            for index, left in enumerate(partitions)
            for right in partitions[index + 1 :]
        ):
            raise ValueError("harmonized analysis partitions must be disjoint")
        value_ids = tuple(item.unit_id for item in self.values)
        if len(value_ids) != len(set(value_ids)) or set(value_ids) != set().union(
            *(set(values) for values in partitions)
        ):
            raise ValueError("harmonized analysis values must exactly cover its unit partitions")
        expected_action = {
            **dict.fromkeys(self.retain_unit_ids, ProteinInferenceArtifactAction.RETAIN),
            **dict.fromkeys(self.review_unit_ids, ProteinInferenceArtifactAction.REVIEW),
            **dict.fromkeys(self.exclude_unit_ids, ProteinInferenceArtifactAction.EXCLUDE),
        }
        if any(item.artifact_action is not expected_action[item.unit_id] for item in self.values):
            raise ValueError("harmonized analysis partition contradicts a unit action")
        if self.analysis_digest != analysis_digest(self):
            raise ValueError("harmonized analysis digest does not match its content")
        return self


class ProteinInferenceHarmonizationFinding(FrozenModel):
    finding_id: Identifier
    code: ProteinInferenceHarmonizationFindingCode
    action: ProteinInferenceHarmonizationFindingAction
    stage_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0306_MAX_STAGES)
    unit_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0306_MAX_UNITS)
    invariant_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0306_MAX_INVARIANTS)
    message: NonEmptyStr

    @field_validator("stage_ids", "unit_ids", "invariant_ids")
    @classmethod
    def references_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def finding_references_are_opaque(self) -> ProteinInferenceHarmonizationFinding:
        for value in self.stage_ids:
            _opaque_identifier(value, "stage", "finding stage identifier")
        for value in self.unit_ids:
            _opaque_identifier(value, "unit", "finding unit identifier")
        for value in self.invariant_ids:
            _opaque_identifier(value, "invariant", "finding invariant identifier")
        return self

    @model_validator(mode="after")
    def finding_is_closed(self) -> ProteinInferenceHarmonizationFinding:
        if (
            len(self.stage_ids) != len(set(self.stage_ids))
            or len(self.unit_ids) != len(set(self.unit_ids))
            or len(self.invariant_ids) != len(set(self.invariant_ids))
        ):
            raise ValueError("harmonization finding references must be unique")
        expected = finding_for(
            self.code,
            stage_ids=self.stage_ids,
            unit_ids=self.unit_ids,
            invariant_ids=self.invariant_ids,
        )
        if self != expected:
            raise ValueError("M03-06 finding contradicts its closed vocabulary")
        return self


class ProteinInferenceHarmonizationComputationReceipt(FrozenModel):
    artifact_receipt_digest: Sha256Digest
    support_ledger_digest: Sha256Digest | None = None
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    profile_digest: Sha256Digest | None = None
    analysis_digest: Sha256Digest | None = None
    transformation_manifest_digest: Sha256Digest | None = None
    supersedes_result_digest: Sha256Digest | None = None
    parent_target: Literal["complex_activity"] = M0306_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    disposition: ProteinInferenceHarmonizationDisposition


class ProteinInferenceHarmonizationResult(FrozenModel):
    output_type: Literal["protein_inference_harmonized_analysis"] = (
        "protein_inference_harmonized_analysis"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0306_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: HarmonizeProteinInferenceSupportRequest
    receipt: ProteinInferenceHarmonizationComputationReceipt
    analysis: ProteinInferenceHarmonizedAnalysis | None = None
    transformation_manifest: ProteinInferenceTransformationManifest | None = None
    technical_effect_diagnostics: tuple[ProteinInferenceTechnicalEffectDiagnostic, ...] = Field(
        default=(),
        max_length=M0306_MAX_STAGES,
    )
    invariant_diagnostics: tuple[ProteinInferenceInvariantDiagnostic, ...] = Field(
        default=(),
        max_length=M0306_MAX_INVARIANTS,
    )
    findings: tuple[ProteinInferenceHarmonizationFinding, ...] = Field(
        default=(),
        max_length=M0306_MAX_FINDINGS,
    )
    disposition: ProteinInferenceHarmonizationDisposition
    parent_target: Literal["complex_activity"] = M0306_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0306_MAX_EVIDENCE)
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
    ) -> ProteinInferenceHarmonizationResult:
        from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
            canonical_request_digest,
            configuration_digest,
            normalized_request,
            policy_digest,
            result_payload_digest,
        )

        canonical_request = HarmonizeProteinInferenceSupportRequest.model_validate_json(
            canonical_json_bytes(normalized_request(self.request)),
            strict=True,
        )
        if self.request != canonical_request:
            raise ValueError("M03-06 embedded request is not in canonical semantic order")
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
            raise ValueError("M03-06 analysis or transformation manifest does not replay")
        if not _semantic_tuple_equal(self.technical_effect_diagnostics, technical):
            raise ValueError("M03-06 technical diagnostics do not replay")
        if not _semantic_tuple_equal(self.invariant_diagnostics, invariants):
            raise ValueError("M03-06 protected invariant diagnostics do not replay")
        if not _semantic_tuple_equal(self.findings, findings):
            raise ValueError("M03-06 findings do not replay")
        if (
            self.result_id != f"result.m0306.{request_hash.removeprefix('sha256:')}"
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
            raise ValueError("M03-06 output envelope contradicts its replayed request")
        if self.support != expected_support(disposition):
            raise ValueError("M03-06 support is not deterministic")
        if not _uncertainty_equal(self.uncertainty, expected_uncertainty(disposition)):
            raise ValueError("M03-06 uncertainty is not deterministic")
        if not _provenance_equal(self.provenance, expected_provenance(self.request)):
            raise ValueError("M03-06 provenance does not close")
        if not _semantic_tuple_equal(self.evidence, harmonization_evidence_index(self.request)):
            raise ValueError("M03-06 evidence index does not close")
        if not _semantic_tuple_equal(self.limitations, expected_limitations()):
            raise ValueError("M03-06 limitations do not close")
        if self.human_review_required != (
            disposition is not ProteinInferenceHarmonizationDisposition.ACCEPTED
        ):
            raise ValueError("M03-06 human-review flag contradicts disposition")
        if self.completed_at != self.request.context.occurred_at:
            raise ValueError("M03-06 completion time must equal execution time")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M03-06 result digest does not match its canonical payload")
        return self


def lower_median(values: tuple[int, ...]) -> int:
    """Return the deterministic lower middle integer without interpolation."""

    if not values:
        raise ValueError("lower median requires at least one integer")
    ordered = sorted(values)
    return ordered[(len(ordered) - 1) // 2]


def _factor_level(
    observation: ProteinInferenceSupportObservation,
    factor: ProteinInferenceNormalizationFactor,
) -> Identifier:
    return next(item.level_id for item in observation.factor_levels if item.factor is factor)


def _retained_observed(observation: ProteinInferenceSupportObservation) -> bool:
    return (
        observation.artifact_action is ProteinInferenceArtifactAction.RETAIN
        and observation.state is ProteinInferenceSupportObservationState.OBSERVED
        and observation.support_coordinate_ppm is not None
    )


def _working_digest(
    observations: tuple[ProteinInferenceSupportObservation, ...],
    working: dict[Identifier, int],
) -> Sha256Digest:
    return sha256_digest(
        tuple(
            sorted(
                (
                    {
                        "unit_id": item.unit_id,
                        "state": item.state.value,
                        "artifact_action": item.artifact_action.value,
                        "support_coordinate_ppm": working.get(item.unit_id),
                    }
                    for item in observations
                ),
                key=canonical_json_bytes,
            )
        )
    )


def _pair_differences(  # noqa: PLR0913 - explicit fixed-point pairing inputs
    observations: tuple[ProteinInferenceSupportObservation, ...],
    working: dict[Identifier, int],
    *,
    factor: ProteinInferenceNormalizationFactor,
    reference_level_id: Identifier,
    comparison_level_id: Identifier,
    anchor_ids: tuple[Identifier, ...],
) -> tuple[int, ...]:
    accepted_anchors = set(anchor_ids)
    grouped: dict[
        tuple[Identifier, Identifier, ProteinInferenceEvidenceUnitKind],
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
        grouped.setdefault(key, {}).setdefault(level_id, []).append(working[observation.unit_id])
    differences: list[int] = []
    for values_by_level in grouped.values():
        reference = values_by_level.get(reference_level_id)
        comparison = values_by_level.get(comparison_level_id)
        if reference and comparison:
            differences.append(lower_median(tuple(reference)) - lower_median(tuple(comparison)))
    return tuple(differences)


def _stage_execution(
    request: HarmonizeProteinInferenceSupportRequest,
    stage: ProteinInferenceNormalizationStage,
    observations: tuple[ProteinInferenceSupportObservation, ...],
    working: dict[Identifier, int],
    adjustments: dict[Identifier, list[ProteinInferenceAppliedSupportAdjustment]],
) -> tuple[
    ProteinInferenceStageTransformation,
    ProteinInferenceTechnicalEffectDiagnostic,
]:
    policy = request.policy
    input_digest = _working_digest(observations, working)
    levels = tuple(sorted({_factor_level(item, stage.factor) for item in observations}))
    non_reference: list[ProteinInferenceSupportLevelShift] = []
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
                ProteinInferenceSupportLevelShift(
                    level_id=level_id,
                    state=ProteinInferenceSupportShiftState.NOT_EVALUABLE,
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
            ProteinInferenceSupportShiftState.CAPPED
            if abs(estimate) >= policy.max_absolute_shift_ppm
            else ProteinInferenceSupportShiftState.ESTIMATED
        )
        non_reference.append(
            ProteinInferenceSupportLevelShift(
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
        item.state is not ProteinInferenceSupportShiftState.NOT_EVALUABLE for item in non_reference
    )
    reference = ProteinInferenceSupportLevelShift(
        level_id=stage.reference_level_id,
        state=(
            ProteinInferenceSupportShiftState.ESTIMATED
            if all_non_reference_evaluable
            else ProteinInferenceSupportShiftState.NOT_EVALUABLE
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
        shifted = working[observation.unit_id] + shift
        if shift != 0 and (shifted <= 0 or shifted >= M0306_RATE_SCALE):
            clipped.add(observation.unit_id)
        working[observation.unit_id] = max(0, min(M0306_RATE_SCALE, shifted))
        adjustments[observation.unit_id].append(
            ProteinInferenceAppliedSupportAdjustment(
                stage_id=stage.stage_id,
                ordinal=stage.ordinal,
                factor=stage.factor,
                level_id=level_id,
                shift_ppm=shift,
            )
        )
    output_digest = _working_digest(observations, working)
    capped = any(item.state is ProteinInferenceSupportShiftState.CAPPED for item in shifts)
    evaluable = all(
        item.state is not ProteinInferenceSupportShiftState.NOT_EVALUABLE for item in shifts
    )
    before = max(item.pre_validation_residual_ppm or 0 for item in shifts) if evaluable else None
    after = max(item.post_validation_residual_ppm or 0 for item in shifts) if evaluable else None
    status = (
        ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
        if before is None or after is None
        else ProteinInferenceHarmonizationDiagnosticStatus.PASSED
        if not capped
        and not clipped
        and after <= policy.technical_effect_tolerance_ppm
        and (after < before or after == before == 0)
        else ProteinInferenceHarmonizationDiagnosticStatus.FAILED
    )
    transformation = ProteinInferenceStageTransformation(
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
        clipped_unit_ids=tuple(sorted(clipped)),
        input_digest=input_digest,
        output_digest=output_digest,
    )
    diagnostic = ProteinInferenceTechnicalEffectDiagnostic(
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
    invariant: ProteinInferenceSupportInvariant,
    observations: dict[Identifier, ProteinInferenceSupportObservation],
    values: dict[Identifier, int],
) -> int | None:
    members = (*invariant.left_unit_ids, *invariant.right_unit_ids)
    if any(
        not _retained_observed(observations[unit_id]) or unit_id not in values
        for unit_id in members
    ):
        return None
    left = tuple(values[item] for item in invariant.left_unit_ids)
    right = tuple(values[item] for item in invariant.right_unit_ids)
    if invariant.kind is ProteinInferenceSupportInvariantKind.AMBIGUITY_FRACTION:
        numerator = sum(left)
        denominator = numerator + sum(right)
        return (
            None
            if denominator == 0
            else (numerator * M0306_RATE_SCALE + denominator // 2) // denominator
        )
    return lower_median(left) - lower_median(right)


def _invariant_diagnostics(
    request: HarmonizeProteinInferenceSupportRequest,
    initial: dict[Identifier, int],
    working: dict[Identifier, int],
) -> tuple[ProteinInferenceInvariantDiagnostic, ...]:
    ledger = request.support_ledger
    if ledger is None:
        return ()
    observations = {item.unit_id: item for item in ledger.observations}
    diagnostics: list[ProteinInferenceInvariantDiagnostic] = []
    for invariant in ledger.invariants:
        before = _invariant_score(invariant, observations, initial)
        after = _invariant_score(invariant, observations, working)
        if before is None or after is None:
            status = ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
        elif invariant.kind is ProteinInferenceSupportInvariantKind.AMBIGUITY_FRACTION:
            status = (
                ProteinInferenceHarmonizationDiagnosticStatus.PASSED
                if abs(after - before) <= request.policy.biological_invariant_tolerance_ppm
                else ProteinInferenceHarmonizationDiagnosticStatus.FAILED
            )
        else:
            status = (
                ProteinInferenceHarmonizationDiagnosticStatus.PASSED
                if _sign(before) != 0
                and _sign(before) == _sign(after)
                and abs(after - before) <= request.policy.biological_invariant_tolerance_ppm
                else ProteinInferenceHarmonizationDiagnosticStatus.FAILED
            )
        diagnostics.append(
            ProteinInferenceInvariantDiagnostic(
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
    request: HarmonizeProteinInferenceSupportRequest,
) -> tuple[
    ProteinInferenceHarmonizedAnalysis | None,
    ProteinInferenceTransformationManifest | None,
    tuple[ProteinInferenceTechnicalEffectDiagnostic, ...],
    tuple[ProteinInferenceInvariantDiagnostic, ...],
]:
    """Replay the exact fixed-point harmonization inside its supported envelope."""

    active = matching_harmonization_profile(request)
    ledger = request.support_ledger
    if (
        request.artifact_receipt.evaluation_state
        is not ProteinInferenceArtifactEvaluationState.COMPLETE
        or request.artifact_receipt.unit_count > request.policy.max_units
        or ledger is None
        or active is None
        or not harmonization_ledger_bindings_close(request)
    ):
        return None, None, (), ()
    observations = tuple(sorted(ledger.observations, key=canonical_json_bytes))
    initial = {
        item.unit_id: item.support_coordinate_ppm
        for item in observations
        if _retained_observed(item) and item.support_coordinate_ppm is not None
    }
    working = dict(initial)
    adjustments: dict[Identifier, list[ProteinInferenceAppliedSupportAdjustment]] = {
        item.unit_id: [] for item in observations
    }
    transformations: list[ProteinInferenceStageTransformation] = []
    technical: list[ProteinInferenceTechnicalEffectDiagnostic] = []
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
    from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
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
        "manifest_digest": M0306_ZERO_DIGEST,
    }
    manifest_payload["manifest_digest"] = transformation_manifest_digest(manifest_payload)
    manifest = ProteinInferenceTransformationManifest.model_validate(manifest_payload, strict=True)
    clipped_units = {unit_id for stage in transformations for unit_id in stage.clipped_unit_ids}
    values = tuple(
        ProteinInferenceHarmonizedSupportValue(
            unit_id=item.unit_id,
            unit_kind=item.unit_kind,
            artifact_action=item.artifact_action,
            input_state=item.state,
            output_state=item.state,
            input_support_coordinate_ppm=item.support_coordinate_ppm,
            harmonized_support_coordinate_ppm=(
                working[item.unit_id] if _retained_observed(item) else None
            ),
            censoring_upper_bound_ppm=item.censoring_upper_bound_ppm,
            source_observation_digest=observation_digest(item),
            adjustments=tuple(adjustments[item.unit_id]) if _retained_observed(item) else (),
            was_clipped=item.unit_id in clipped_units,
        )
        for item in observations
    )
    analysis_payload: dict[str, object] = {
        "analysis_id": f"analysis.m0306.{request_hash.removeprefix('sha256:')}",
        "artifact_result_digest": request.artifact_receipt.artifact_result_digest,
        "support_ledger_digest": ledger.ledger_digest,
        "artifact_unit_binding_digest": request.artifact_receipt.unit_binding_digest,
        "profile_digest": active_profile_digest,
        "policy_digest": active_policy_digest,
        "retain_unit_ids": tuple(
            sorted(
                item.unit_id
                for item in observations
                if item.artifact_action is ProteinInferenceArtifactAction.RETAIN
            )
        ),
        "review_unit_ids": tuple(
            sorted(
                item.unit_id
                for item in observations
                if item.artifact_action is ProteinInferenceArtifactAction.REVIEW
            )
        ),
        "exclude_unit_ids": tuple(
            sorted(
                item.unit_id
                for item in observations
                if item.artifact_action is ProteinInferenceArtifactAction.EXCLUDE
            )
        ),
        "values": values,
        "analysis_digest": M0306_ZERO_DIGEST,
        "parent_target": M0306_PARENT,
        "emits_complex_activity": False,
        "infers_identity": False,
        "infers_protein": False,
        "infers_proteoform": False,
        "infers_isoform": False,
        "infers_glioma_specific_biology": False,
        "infers_kinase_activity": False,
    }
    analysis_payload["analysis_digest"] = analysis_digest(analysis_payload)
    analysis = ProteinInferenceHarmonizedAnalysis.model_validate(analysis_payload, strict=True)
    return (
        analysis,
        manifest,
        tuple(sorted(technical, key=canonical_json_bytes)),
        invariant_diagnostics,
    )


def finding_for(
    code: ProteinInferenceHarmonizationFindingCode,
    *,
    stage_ids: tuple[Identifier, ...] = (),
    unit_ids: tuple[Identifier, ...] = (),
    invariant_ids: tuple[Identifier, ...] = (),
) -> ProteinInferenceHarmonizationFinding:
    canonical_stages = tuple(sorted(set(stage_ids)))
    canonical_units = tuple(sorted(set(unit_ids)))
    canonical_invariants = tuple(sorted(set(invariant_ids)))
    suffix = sha256_digest(
        {
            "code": code.value,
            "stage_ids": canonical_stages,
            "unit_ids": canonical_units,
            "invariant_ids": canonical_invariants,
        }
    ).removeprefix("sha256:")
    return ProteinInferenceHarmonizationFinding.model_construct(
        finding_id=f"finding.m0306.{suffix}",
        code=code,
        action=_FINDING_ACTION[code],
        stage_ids=canonical_stages,
        unit_ids=canonical_units,
        invariant_ids=canonical_invariants,
        message=_FINDING_MESSAGE[code],
    )


def _safe_failure_finding(
    request: HarmonizeProteinInferenceSupportRequest,
) -> ProteinInferenceHarmonizationFinding | None:
    receipt = request.artifact_receipt
    upstream = {
        ProteinInferenceArtifactDisposition.REJECTED: (
            ProteinInferenceHarmonizationFindingCode.UPSTREAM_REJECTED
        ),
        ProteinInferenceArtifactDisposition.QUARANTINED: (
            ProteinInferenceHarmonizationFindingCode.UPSTREAM_QUARANTINED
        ),
        ProteinInferenceArtifactDisposition.ABSTAINED: (
            ProteinInferenceHarmonizationFindingCode.UPSTREAM_ABSTAINED
        ),
    }.get(receipt.artifact_disposition)
    if upstream is not None:
        return finding_for(upstream)
    if receipt.evaluation_state is ProteinInferenceArtifactEvaluationState.NOT_EVALUABLE:
        return finding_for(ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    if receipt.unit_count > request.policy.max_units or request.support_ledger is None:
        return finding_for(ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    if not harmonization_ledger_bindings_close(request):
        return finding_for(ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH)
    if matching_harmonization_profile(request) is None:
        return finding_for(
            ProteinInferenceHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED
        )
    return None


def expected_harmonization_findings(
    request: HarmonizeProteinInferenceSupportRequest,
    manifest: ProteinInferenceTransformationManifest | None = None,
    technical: tuple[ProteinInferenceTechnicalEffectDiagnostic, ...] = (),
    invariants: tuple[ProteinInferenceInvariantDiagnostic, ...] = (),
) -> tuple[ProteinInferenceHarmonizationFinding, ...]:
    safe_failure = _safe_failure_finding(request)
    if safe_failure is not None:
        return (safe_failure,)
    ledger = request.support_ledger
    if ledger is None or manifest is None:
        return (finding_for(ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED),)
    findings: list[ProteinInferenceHarmonizationFinding] = []
    excluded = tuple(
        item.unit_id
        for item in ledger.observations
        if item.artifact_action is ProteinInferenceArtifactAction.EXCLUDE
    )
    review = tuple(
        item.unit_id
        for item in ledger.observations
        if item.artifact_action is ProteinInferenceArtifactAction.REVIEW
    )
    non_evaluable = tuple(
        item.unit_id
        for item in ledger.observations
        if item.artifact_action is ProteinInferenceArtifactAction.RETAIN
        and item.state is not ProteinInferenceSupportObservationState.OBSERVED
    )
    if excluded:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.ARTIFACT_EXCLUSION_PRESENT,
                unit_ids=excluded,
            )
        )
    if review:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED,
                unit_ids=review,
            )
        )
    if non_evaluable:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.RETAINED_SUPPORT_NOT_EVALUABLE,
                unit_ids=non_evaluable,
            )
        )
    not_evaluable_stages = tuple(
        item.stage_id
        for item in technical
        if item.status is ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
    )
    failed_stages = tuple(
        item.stage_id
        for item in technical
        if item.status is ProteinInferenceHarmonizationDiagnosticStatus.FAILED
    )
    capped_stages = tuple(
        item.stage_id
        for item in manifest.stages
        if any(
            shift.state is ProteinInferenceSupportShiftState.CAPPED for shift in item.level_shifts
        )
    )
    clipped_units = tuple(unit_id for item in manifest.stages for unit_id in item.clipped_unit_ids)
    if not_evaluable_stages:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.CONTROL_PAIR_INSUFFICIENT,
                stage_ids=not_evaluable_stages,
            )
        )
    if capped_stages:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.SHIFT_CAPPED,
                stage_ids=capped_stages,
            )
        )
    if clipped_units:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.VALUE_CLIPPED,
                unit_ids=clipped_units,
            )
        )
    if failed_stages:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.TECHNICAL_EFFECT_NOT_REDUCED,
                stage_ids=failed_stages,
            )
        )
    not_evaluable_invariants = tuple(
        item.invariant_id
        for item in invariants
        if item.status is ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
    )
    failed_invariants = tuple(
        item.invariant_id
        for item in invariants
        if item.status is ProteinInferenceHarmonizationDiagnosticStatus.FAILED
    )
    if not_evaluable_invariants:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.INVARIANT_NOT_EVALUABLE,
                invariant_ids=not_evaluable_invariants,
            )
        )
    if failed_invariants:
        findings.append(
            finding_for(
                ProteinInferenceHarmonizationFindingCode.INVARIANT_VIOLATED,
                invariant_ids=failed_invariants,
            )
        )
    return tuple(sorted(findings, key=canonical_json_bytes))


def expected_disposition(
    request: HarmonizeProteinInferenceSupportRequest,
    findings: tuple[ProteinInferenceHarmonizationFinding, ...] = (),
) -> ProteinInferenceHarmonizationDisposition:
    upstream = request.artifact_receipt.artifact_disposition
    if upstream is ProteinInferenceArtifactDisposition.REJECTED or any(
        item.action is ProteinInferenceHarmonizationFindingAction.REJECT for item in findings
    ):
        return ProteinInferenceHarmonizationDisposition.REJECTED
    if upstream is ProteinInferenceArtifactDisposition.QUARANTINED or any(
        item.action is ProteinInferenceHarmonizationFindingAction.QUARANTINE for item in findings
    ):
        return ProteinInferenceHarmonizationDisposition.QUARANTINED
    if upstream is ProteinInferenceArtifactDisposition.ABSTAINED or any(
        item.action is ProteinInferenceHarmonizationFindingAction.ABSTAIN for item in findings
    ):
        return ProteinInferenceHarmonizationDisposition.ABSTAINED
    return ProteinInferenceHarmonizationDisposition.ACCEPTED


def expected_computation_receipt(
    request: HarmonizeProteinInferenceSupportRequest,
    disposition: ProteinInferenceHarmonizationDisposition,
    analysis: ProteinInferenceHarmonizedAnalysis | None = None,
    manifest: ProteinInferenceTransformationManifest | None = None,
) -> ProteinInferenceHarmonizationComputationReceipt:
    from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    active = matching_harmonization_profile(request)
    return ProteinInferenceHarmonizationComputationReceipt(
        artifact_receipt_digest=request.artifact_receipt.receipt_digest,
        support_ledger_digest=(
            request.support_ledger.ledger_digest if request.support_ledger is not None else None
        ),
        policy_digest=policy_digest(request.policy),
        configuration_digest=configuration_digest(request.policy),
        profile_digest=profile_digest(active) if active is not None else None,
        analysis_digest=analysis.analysis_digest if analysis is not None else None,
        transformation_manifest_digest=(manifest.manifest_digest if manifest is not None else None),
        supersedes_result_digest=request.supersedes_result_digest,
        disposition=disposition,
    )


def expected_support(disposition: ProteinInferenceHarmonizationDisposition) -> SupportDecision:
    if disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="protein_inference_support_harmonization_accepted",
            rationale="All reviewed technical and protected-invariant diagnostics passed.",
        )
    if disposition is ProteinInferenceHarmonizationDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="protein_inference_support_harmonization_quarantined",
            rationale="An artifact firewall, technical effect, or invariant requires review.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code=(
            "protein_inference_support_harmonization_rejected"
            if disposition is ProteinInferenceHarmonizationDisposition.REJECTED
            else "protein_inference_support_harmonization_abstained"
        ),
        rationale="The upstream screen, support graph, controls, or profile is unsupported.",
    )


def expected_uncertainty(
    disposition: ProteinInferenceHarmonizationDisposition,
) -> UncertaintyProfile:
    del disposition
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0306_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0306_SENSITIVITY_NOTES,
    )


def expected_control_decisions(
    request: HarmonizeProteinInferenceSupportRequest,
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
    request: HarmonizeProteinInferenceSupportRequest,
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
            claim=M0306_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def expected_provenance(request: HarmonizeProteinInferenceSupportRequest) -> ProvenanceRecord:
    from glio_proteogen.contracts.m03_06.canonical import (  # noqa: PLC0415
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
        activity_id=f"activity.m0306.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0306_MODULE_ID,
        module_version=M0306_CONTRACT_VERSION,
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
                    code=M0306_HARMONIZATION_LIMITATION_CODE,
                    statement=(
                        "This output owns only deterministic technical harmonization of "
                        "protein-inference support coordinates; it does not infer protein, "
                        "proteoform, complex, subtype, or kinase activity."
                    ),
                ),
                Limitation(
                    code=M0306_SCALE_LIMITATION_CODE,
                    statement=(
                        "support_coordinate_ppm is a bounded fixed-point support coordinate, "
                        "not abundance, effect size, risk, or calibrated probability."
                    ),
                ),
                Limitation(
                    code=M0306_AUTHORITY_LIMITATION_CODE,
                    statement=(
                        "The compact M03-05 receipt proves caller-declared content "
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
