"""Strict contracts for deterministic M03-07 joint support-envelope routing.

M03-07 consumes compact, self-validating M03-04 and M03-06 receipts.  It
confirms support only when one reviewed envelope admits the complete protein-
inference context; missing or unknown declarations remain indeterminate.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

from glio_proteogen.contracts.m03_01 import ProteinInferenceApplicability  # noqa: TC001
from glio_proteogen.contracts.m03_04 import (
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityResult,
)
from glio_proteogen.contracts.m03_06 import (
    ProteinInferenceHarmonizationDisposition,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceNormalizationFactor,
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

M0307_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-07"
M0307_OPERATION: Final = "route_protein_inference_support"
M0307_CONTRACT_VERSION: Final = "1.0.0"
M0307_PARENT: Final = "complex_activity"
M0307_OWNER: Final = "Scientific engineering"
M0307_SAFETY_CLASS: Final = "S2"
M0307_GATE: Final = "G1"
M0307_RATE_SCALE: Final = 1_000_000
M0307_DIMENSION_COUNT: Final = 8
M0307_DECLARED_FACT_COUNT: Final = 4
M0307_CONTEXT_RECEIPT_COUNT: Final = 3
M0307_MAX_ENVELOPES: Final = 64
M0307_MAX_FACT_VALUES: Final = 64
M0307_MAX_PLATFORM_LEVEL_IDS: Final = 512
M0307_MAX_APPROVED_VERSIONS: Final = 32
M0307_MAX_EVIDENCE_PER_FACT: Final = 8
# At maximum envelope capacity every dimension can be blocked, and both
# prerequisite modules can add one aggregate blocker.  The joint-envelope
# blocker is mutually exclusive with that shape because it requires the union
# of supported dimensions to cover the domain.
M0307_MAX_ABSTENTIONS: Final = (M0307_MAX_ENVELOPES * M0307_DIMENSION_COUNT) + 2
M0307_MAX_EVIDENCE: Final = 46
M0307_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0307_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0307_EVIDENCE_CLAIM: Final = (
    "Caller-declared evidence for deterministic protein-inference support routing; "
    "issuer authority is not authenticated."
)
M0307_ROUTING_LIMITATION_CODE: Final = "protein_inference_support_routing_only"
M0307_AUTHORITY_LIMITATION_CODE: Final = "external_receipt_issuers_unverified"
M0307_DOMAIN_LIMITATION_CODE: Final = "reviewed_support_domain_not_validated"
M0307_UNCERTAINTY_RATIONALES: Final = (
    "Support routing does not estimate measurement uncertainty.",
    "Support routing does not estimate sampling uncertainty.",
    "Support routing does not estimate parameter uncertainty.",
    "Support routing does not estimate model-form uncertainty.",
    "Support routing does not re-estimate upstream identification uncertainty.",
    "Support is categorical within one reviewed joint envelope.",
    "Transport beyond the reviewed support envelope is not estimable.",
)
M0307_SENSITIVITY_NOTES: Final = (
    "Missing and unknown declarations remain indeterminate.",
    "No union of partial envelopes can establish support.",
)

_M0304_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m03-04+json"
_M0306_RESULT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m03-06+json"

_OPAQUE_IDENTIFIER = re.compile(
    r"^(request|profile|policy|envelope|specimen|disease|reference|use|reason|"
    r"remediation|evidence|reviewer|route)\.[0-9a-f]{64}$"
)
_OWNED_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


class ProteinInferenceSupportDimension(StrEnum):
    ASSAY = "assay"
    SPECIMEN = "specimen"
    DISEASE_CLASS = "disease_class"
    QUALITY = "quality"
    COMPLETENESS = "completeness"
    PLATFORM = "platform"
    REFERENCE = "reference"
    INTENDED_USE = "intended_use"


class ProteinInferenceDeclaredSupportState(StrEnum):
    OBSERVED = "observed"
    MISSING = "missing"
    UNKNOWN = "unknown"


class ProteinInferenceDimensionSupportDecision(StrEnum):
    SUPPORTED = "supported"
    OUTSIDE_DOMAIN = "outside_domain"
    INDETERMINATE = "indeterminate"


class ProteinInferenceEnvelopeSupportDecision(StrEnum):
    CONFIRMED = "confirmed"
    ELIMINATED = "eliminated"
    PROVISIONAL = "provisional"


class ProteinInferenceSupportDisposition(StrEnum):
    SUPPORTED = "supported"
    ABSTAINED = "abstained"


class ProteinInferenceContextRole(StrEnum):
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"
    TREATMENT_HISTORY = "treatment_history"


class ProteinInferenceAbstentionCode(StrEnum):
    DIMENSION_OUTSIDE_DOMAIN = "dimension_outside_domain"
    DIMENSION_INDETERMINATE = "dimension_indeterminate"
    PREREQUISITE_UNRELEASABLE = "prerequisite_unreleasable"
    JOINT_COMBINATION_OUTSIDE_DOMAIN = "joint_combination_outside_domain"


class ProteinInferenceRemediationPath(StrEnum):
    CORRECT_SUPPORT_DECLARATION = "correct_support_declaration"
    SUPPLY_REQUIRED_SUPPORT_EVIDENCE = "supply_required_support_evidence"
    RESOLVE_UPSTREAM_PREREQUISITE = "resolve_upstream_prerequisite"
    SELECT_ONE_REVIEWED_JOINT_ENVELOPE = "select_one_reviewed_joint_envelope"
    REQUEST_GOVERNED_SUPPORT_REVIEW = "request_governed_support_review"


def opaque_support_identifier(namespace: str, value: str) -> Identifier:
    """Validate one content-derived M03-07 identifier and its namespace."""

    if not value.startswith(f"{namespace}.") or _OPAQUE_IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"identifier must be an opaque {namespace} digest alias")
    return value


def _owned_evidence(value: ArtifactReference) -> ArtifactReference:
    opaque_support_identifier("evidence", value.artifact_id)
    if _OWNED_MEDIA_TYPE.fullmatch(value.media_type) is None:
        raise ValueError("M03-07 evidence media type must use lowercase type/subtype syntax")
    return value


class ProteinInferenceQualityMetricSupportReceipt(FrozenModel):
    metric_code: ProteinInferenceQualityMetricCode
    observation_state: ProteinInferenceQualityObservationState
    status: ProteinInferenceQualityMetricStatus
    value_ppm: int | None = Field(default=None, ge=0, le=M0307_RATE_SCALE)

    @model_validator(mode="after")
    def value_matches_observation(self) -> ProteinInferenceQualityMetricSupportReceipt:
        if self.observation_state in {
            ProteinInferenceQualityObservationState.OBSERVED,
            ProteinInferenceQualityObservationState.CENSORED,
        }:
            if self.value_ppm is None or self.status in {
                ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
                ProteinInferenceQualityMetricStatus.NOT_APPLICABLE,
            }:
                raise ValueError("evaluable quality support metric requires its integer value")
        elif self.value_ppm is not None or self.status is not (
            ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
            if self.observation_state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
            else ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
        ):
            raise ValueError("non-evaluable quality support metric cannot carry a value")
        return self


class ProteinInferenceQualitySupportReceipt(FrozenModel):
    module_id: Literal["GLIO-PROTEOGEN-M03-04"] = "GLIO-PROTEOGEN-M03-04"
    receipt_version: Literal["1.0.0"] = M0307_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    result_digest: Sha256Digest
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    disposition: ProteinInferenceQualityDisposition
    support_status: SupportStatus
    human_review_required: bool
    completed_at: AwareDatetime
    identity_resolution_digest: Sha256Digest
    applicability: ProteinInferenceApplicability | None = None
    assay_protocol_version: SemanticVersion
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    metrics: tuple[ProteinInferenceQualityMetricSupportReceipt, ...] = Field(
        default=(), max_length=M0307_DIMENSION_COUNT
    )
    receipt_digest: Sha256Digest

    @field_validator("metrics")
    @classmethod
    def metrics_are_canonical(
        cls, values: tuple[ProteinInferenceQualityMetricSupportReceipt, ...]
    ) -> tuple[ProteinInferenceQualityMetricSupportReceipt, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def receipt_shape_is_closed(self) -> ProteinInferenceQualitySupportReceipt:
        from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
            quality_support_receipt_digest,
        )

        codes = tuple(item.metric_code for item in self.metrics)
        if len(codes) != len(set(codes)):
            raise ValueError("quality support receipt metrics must be unique")
        expected_artifact_id = f"result.m0304.{self.request_digest.removeprefix('sha256:')}"
        if (
            self.artifact_reference.artifact_id != expected_artifact_id
            or self.artifact_reference.version != M0307_CONTRACT_VERSION
            or self.artifact_reference.media_type != _M0304_RESULT_MEDIA_TYPE
            or self.artifact_reference.digest != self.result_digest
        ):
            raise ValueError("quality receipt artifact does not bind the exact M03-04 result")
        if self.disposition is ProteinInferenceQualityDisposition.QUALIFIED and (
            len(self.metrics) != M0307_DIMENSION_COUNT
            or set(codes) != set(ProteinInferenceQualityMetricCode)
            or self.applicability is None
            or self.support_status not in {SupportStatus.SUPPORTED, SupportStatus.LIMITED}
            or self.human_review_required
            or any(
                item.status
                in {
                    ProteinInferenceQualityMetricStatus.FAIL,
                    ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
                }
                for item in self.metrics
            )
        ):
            raise ValueError("qualified quality receipt requires its exact metric domain")
        expected_statuses, expected_review = {
            ProteinInferenceQualityDisposition.QUALIFIED: (
                {SupportStatus.SUPPORTED, SupportStatus.LIMITED},
                False,
            ),
            ProteinInferenceQualityDisposition.QUARANTINED: (
                {SupportStatus.REVIEW_REQUIRED},
                True,
            ),
            ProteinInferenceQualityDisposition.ABSTAINED: (
                {SupportStatus.UNSUPPORTED},
                True,
            ),
            ProteinInferenceQualityDisposition.REJECTED: (
                {SupportStatus.UNSUPPORTED},
                True,
            ),
        }[self.disposition]
        if self.support_status not in expected_statuses or self.human_review_required is not (
            expected_review
        ):
            raise ValueError("quality receipt disposition and support envelope contradict")
        if self.receipt_digest != quality_support_receipt_digest(self):
            raise ValueError("quality support receipt digest does not match its content")
        return self


class ProteinInferenceHarmonizationSupportReceipt(FrozenModel):
    module_id: Literal["GLIO-PROTEOGEN-M03-06"] = "GLIO-PROTEOGEN-M03-06"
    receipt_version: Literal["1.0.0"] = M0307_CONTRACT_VERSION
    artifact_reference: ArtifactReference
    result_digest: Sha256Digest
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    disposition: ProteinInferenceHarmonizationDisposition
    support_status: SupportStatus
    human_review_required: bool
    completed_at: AwareDatetime
    quality_result_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    applicability: ProteinInferenceApplicability | None = None
    assay_protocol_version: SemanticVersion
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    platform_level_ids: tuple[Identifier, ...] = Field(
        default=(), max_length=M0307_MAX_PLATFORM_LEVEL_IDS
    )
    total_unit_count: int = Field(ge=0, le=M0307_MAX_PLATFORM_LEVEL_IDS)
    retained_unit_count: int = Field(ge=0, le=M0307_MAX_PLATFORM_LEVEL_IDS)
    review_unit_count: int = Field(ge=0, le=M0307_MAX_PLATFORM_LEVEL_IDS)
    excluded_unit_count: int = Field(ge=0, le=M0307_MAX_PLATFORM_LEVEL_IDS)
    evaluable_unit_count: int = Field(ge=0, le=M0307_MAX_PLATFORM_LEVEL_IDS)
    analysis_digest: Sha256Digest | None = None
    receipt_digest: Sha256Digest

    @field_validator("platform_level_ids")
    @classmethod
    def platform_ids_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if any(not value.startswith("level.") for value in values):
            raise ValueError("platform level identifiers must preserve M03-06 opaque aliases")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def receipt_shape_is_closed(self) -> ProteinInferenceHarmonizationSupportReceipt:
        from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
            harmonization_support_receipt_digest,
        )

        if len(self.platform_level_ids) != len(set(self.platform_level_ids)):
            raise ValueError("harmonization platform identifiers must be unique")
        expected_artifact_id = f"result.m0306.{self.request_digest.removeprefix('sha256:')}"
        if (
            self.artifact_reference.artifact_id != expected_artifact_id
            or self.artifact_reference.version != M0307_CONTRACT_VERSION
            or self.artifact_reference.media_type != _M0306_RESULT_MEDIA_TYPE
            or self.artifact_reference.digest != self.result_digest
        ):
            raise ValueError("harmonization receipt artifact does not bind the exact M03-06 result")
        partition = self.retained_unit_count + self.review_unit_count + self.excluded_unit_count
        if partition != self.total_unit_count or self.evaluable_unit_count > self.total_unit_count:
            raise ValueError("harmonization support unit counts do not form a closed partition")
        if self.disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED:
            if (
                self.total_unit_count == 0
                or self.applicability is None
                or self.analysis_digest is None
                or not self.platform_level_ids
            ):
                raise ValueError(
                    "accepted harmonization receipt requires its successful projection"
                )
            if self.support_status is not SupportStatus.LIMITED or self.human_review_required:
                raise ValueError("accepted harmonization receipt has an invalid support envelope")
        elif (
            any(
                (
                    self.total_unit_count,
                    self.retained_unit_count,
                    self.review_unit_count,
                    self.excluded_unit_count,
                    self.evaluable_unit_count,
                    len(self.platform_level_ids),
                )
            )
            or self.analysis_digest is not None
            or self.applicability is not None
        ):
            raise ValueError("non-accepted harmonization receipt cannot project analysis values")
        expected_status = {
            ProteinInferenceHarmonizationDisposition.ACCEPTED: SupportStatus.LIMITED,
            ProteinInferenceHarmonizationDisposition.QUARANTINED: SupportStatus.REVIEW_REQUIRED,
            ProteinInferenceHarmonizationDisposition.ABSTAINED: SupportStatus.UNSUPPORTED,
            ProteinInferenceHarmonizationDisposition.REJECTED: SupportStatus.UNSUPPORTED,
        }[self.disposition]
        if self.support_status is not expected_status or self.human_review_required is not (
            self.disposition is not ProteinInferenceHarmonizationDisposition.ACCEPTED
        ):
            raise ValueError("harmonization receipt disposition and support envelope contradict")
        if self.receipt_digest != harmonization_support_receipt_digest(self):
            raise ValueError("harmonization support receipt digest does not match its content")
        return self


class ProteinInferenceSupportPrerequisites(FrozenModel):
    quality_result: ProteinInferenceQualityResult
    harmonization_result: ProteinInferenceHarmonizationResult
    quality: ProteinInferenceQualitySupportReceipt
    harmonization: ProteinInferenceHarmonizationSupportReceipt

    @model_validator(mode="after")
    def chain_is_closed(self) -> ProteinInferenceSupportPrerequisites:
        if self.quality != quality_support_receipt(self.quality_result):
            raise ValueError(
                "quality receipt is not the exact projection of its full M03-04 result"
            )
        if self.harmonization != harmonization_support_receipt(self.harmonization_result):
            raise ValueError(
                "harmonization receipt is not the exact projection of its full M03-06 result"
            )
        if self.quality.result_digest != self.harmonization.quality_result_digest:
            raise ValueError("harmonization receipt does not bind the exact quality result")
        if self.quality.identity_resolution_digest != self.harmonization.identity_resolution_digest:
            raise ValueError("support prerequisites disagree on identity lineage")
        if self.quality.completed_at > self.harmonization.completed_at:
            raise ValueError("support prerequisite chronology is impossible")
        if (
            self.quality.disposition is ProteinInferenceQualityDisposition.QUALIFIED
            and self.harmonization.disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED
        ) and (
            self.quality.applicability != self.harmonization.applicability
            or self.quality.assay_protocol_version != self.harmonization.assay_protocol_version
            or self.quality.controlled_vocabulary_version
            != self.harmonization.controlled_vocabulary_version
            or self.quality.unit_system_version != self.harmonization.unit_system_version
        ):
            raise ValueError("support prerequisites disagree on applicability or protocol versions")
        return self


class ProteinInferenceDeclaredSupportFact(FrozenModel):
    dimension: Literal[
        ProteinInferenceSupportDimension.SPECIMEN,
        ProteinInferenceSupportDimension.DISEASE_CLASS,
        ProteinInferenceSupportDimension.REFERENCE,
        ProteinInferenceSupportDimension.INTENDED_USE,
    ]
    state: ProteinInferenceDeclaredSupportState
    values: tuple[Identifier, ...] = Field(default=(), max_length=M0307_MAX_FACT_VALUES)
    evidence: tuple[ArtifactReference, ...] = Field(
        default=(), max_length=M0307_MAX_EVIDENCE_PER_FACT
    )

    @field_validator("values")
    @classmethod
    def values_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        return tuple(sorted(values))

    @field_validator("evidence")
    @classmethod
    def evidence_is_canonical(
        cls, values: tuple[ArtifactReference, ...]
    ) -> tuple[ArtifactReference, ...]:
        for value in values:
            _owned_evidence(value)
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def declaration_is_closed(self) -> ProteinInferenceDeclaredSupportFact:
        if len(self.values) != len(set(self.values)) or len(self.evidence) != len(
            set(self.evidence)
        ):
            raise ValueError("declared support fact collections must be unique")
        namespace = {
            ProteinInferenceSupportDimension.SPECIMEN: "specimen",
            ProteinInferenceSupportDimension.DISEASE_CLASS: "disease",
            ProteinInferenceSupportDimension.REFERENCE: "reference",
            ProteinInferenceSupportDimension.INTENDED_USE: "use",
        }[self.dimension]
        for value in self.values:
            opaque_support_identifier(namespace, value)
        if self.state is ProteinInferenceDeclaredSupportState.OBSERVED:
            if not self.values:
                raise ValueError("observed support fact requires at least one value")
        elif self.values:
            raise ValueError("missing or unknown support fact cannot carry values")
        return self


class ProteinInferenceContextReceipt(FrozenModel):
    role: ProteinInferenceContextRole
    state: ProteinInferenceDeclaredSupportState
    reference: ArtifactReference | None = None

    @model_validator(mode="after")
    def context_shape_is_closed(self) -> ProteinInferenceContextReceipt:
        if self.state is ProteinInferenceDeclaredSupportState.OBSERVED:
            if self.reference is None:
                raise ValueError("observed context receipt requires evidence")
            _owned_evidence(self.reference)
        elif self.reference is not None:
            raise ValueError("missing or unknown context receipt cannot carry evidence")
        return self


class ProteinInferenceDimensionRemediation(FrozenModel):
    dimension: ProteinInferenceSupportDimension
    outside_reason_code: Identifier
    indeterminate_reason_code: Identifier
    remediation_code: Identifier
    remediation_path: ProteinInferenceRemediationPath

    @field_validator("outside_reason_code", "indeterminate_reason_code")
    @classmethod
    def reason_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("reason", value)

    @field_validator("remediation_code")
    @classmethod
    def remediation_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("remediation", value)


class ProteinInferenceSupportEnvelope(FrozenModel):
    envelope_id: Identifier
    applicabilities: tuple[ProteinInferenceApplicability, ...] = Field(min_length=1, max_length=3)
    approved_assay_protocol_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0307_MAX_APPROVED_VERSIONS
    )
    approved_controlled_vocabulary_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0307_MAX_APPROVED_VERSIONS
    )
    approved_unit_system_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M0307_MAX_APPROVED_VERSIONS
    )
    specimen_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=M0307_MAX_FACT_VALUES)
    disease_class_terms: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0307_MAX_FACT_VALUES
    )
    quality_statuses: tuple[ProteinInferenceQualityMetricStatus, ...] = Field(
        min_length=1, max_length=5
    )
    minimum_completeness_ppm: int = Field(ge=0, le=M0307_RATE_SCALE)
    platform_level_ids: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0307_MAX_PLATFORM_LEVEL_IDS
    )
    reference_terms: tuple[Identifier, ...] = Field(min_length=1, max_length=M0307_MAX_FACT_VALUES)
    intended_use_terms: tuple[Identifier, ...] = Field(
        min_length=1, max_length=M0307_MAX_FACT_VALUES
    )
    required_context_roles: tuple[ProteinInferenceContextRole, ...] = Field(
        min_length=1, max_length=M0307_CONTEXT_RECEIPT_COUNT
    )
    remediations: tuple[ProteinInferenceDimensionRemediation, ...] = Field(
        min_length=M0307_DIMENSION_COUNT, max_length=M0307_DIMENSION_COUNT
    )

    @field_validator("envelope_id")
    @classmethod
    def envelope_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("envelope", value)

    @field_validator(
        "applicabilities",
        "approved_assay_protocol_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
        "specimen_terms",
        "disease_class_terms",
        "quality_statuses",
        "platform_level_ids",
        "reference_terms",
        "intended_use_terms",
        "required_context_roles",
    )
    @classmethod
    def semantic_sets_are_canonical(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        if len(values) != len(set(values)):
            raise ValueError("support envelope collections must be unique")
        return tuple(sorted(values))

    @field_validator("remediations")
    @classmethod
    def remediations_are_canonical(
        cls, values: tuple[ProteinInferenceDimensionRemediation, ...]
    ) -> tuple[ProteinInferenceDimensionRemediation, ...]:
        return tuple(sorted(values, key=lambda item: item.dimension.value))

    @model_validator(mode="after")
    def envelope_is_relationally_closed(self) -> ProteinInferenceSupportEnvelope:
        if {item.dimension for item in self.remediations} != set(ProteinInferenceSupportDimension):
            raise ValueError("support envelope requires one remediation per dimension")
        namespaces = (
            (self.specimen_terms, "specimen"),
            (self.disease_class_terms, "disease"),
            (self.platform_level_ids, "level"),
            (self.reference_terms, "reference"),
            (self.intended_use_terms, "use"),
        )
        for values, namespace in namespaces:
            for value in values:
                if namespace == "level":
                    if re.fullmatch(r"level\.[0-9a-f]{64}", value) is None:
                        raise ValueError("platform values must preserve M03-06 level aliases")
                else:
                    opaque_support_identifier(namespace, value)
        return self


class ProteinInferenceSupportProfile(FrozenModel):
    profile_id: Identifier
    version: SemanticVersion
    envelopes: tuple[ProteinInferenceSupportEnvelope, ...] = Field(
        min_length=1, max_length=M0307_MAX_ENVELOPES
    )
    evidence: ArtifactReference

    @field_validator("profile_id")
    @classmethod
    def profile_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("profile", value)

    @field_validator("envelopes")
    @classmethod
    def envelopes_are_canonical(
        cls, values: tuple[ProteinInferenceSupportEnvelope, ...]
    ) -> tuple[ProteinInferenceSupportEnvelope, ...]:
        if len({item.envelope_id for item in values}) != len(values):
            raise ValueError("support profile envelope identifiers must be unique")
        return tuple(sorted(values, key=lambda item: item.envelope_id))

    @field_validator("evidence")
    @classmethod
    def profile_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class ProteinInferenceSupportPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_envelopes: int = Field(gt=0, le=M0307_MAX_ENVELOPES)
    require_releasable_prerequisites: Literal[True] = True
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("policy_id")
    @classmethod
    def policy_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("policy", value)

    @field_validator("reviewed_by")
    @classmethod
    def reviewer_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("reviewer", value)

    @field_validator("evidence")
    @classmethod
    def policy_evidence_is_owned(cls, value: ArtifactReference) -> ArtifactReference:
        return _owned_evidence(value)


class RouteProteinInferenceSupportRequest(FrozenModel):
    operation: Literal["route_protein_inference_support"] = M0307_OPERATION
    contract_version: Literal["1.0.0"] = M0307_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    prerequisites: ProteinInferenceSupportPrerequisites
    profile: ProteinInferenceSupportProfile
    policy: ProteinInferenceSupportPolicy
    declared_facts: tuple[ProteinInferenceDeclaredSupportFact, ...] = Field(
        min_length=M0307_DECLARED_FACT_COUNT, max_length=M0307_DECLARED_FACT_COUNT
    )
    context_receipts: tuple[ProteinInferenceContextReceipt, ...] = Field(
        min_length=M0307_CONTEXT_RECEIPT_COUNT, max_length=M0307_CONTEXT_RECEIPT_COUNT
    )
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("request_id")
    @classmethod
    def request_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("request", value)

    @field_validator("declared_facts")
    @classmethod
    def facts_are_canonical(
        cls, values: tuple[ProteinInferenceDeclaredSupportFact, ...]
    ) -> tuple[ProteinInferenceDeclaredSupportFact, ...]:
        return tuple(sorted(values, key=lambda item: item.dimension.value))

    @field_validator("context_receipts")
    @classmethod
    def contexts_are_canonical(
        cls, values: tuple[ProteinInferenceContextReceipt, ...]
    ) -> tuple[ProteinInferenceContextReceipt, ...]:
        return tuple(sorted(values, key=lambda item: item.role.value))

    @model_validator(mode="after")
    def request_is_authorized_bound_and_closed(self) -> RouteProteinInferenceSupportRequest:
        _validate_route_boundary(self)
        if len(canonical_json_bytes(self)) > M0307_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("M03-07 canonical request exceeds the public ingress byte limit")
        return self


class ProteinInferenceDimensionAssessment(FrozenModel):
    dimension: ProteinInferenceSupportDimension
    decision: ProteinInferenceDimensionSupportDecision
    values: tuple[Identifier, ...] = Field(default=(), max_length=M0307_MAX_PLATFORM_LEVEL_IDS)
    numeric_value_ppm: int | None = Field(default=None, ge=0, le=M0307_RATE_SCALE)
    reason_code: Identifier | None = None
    remediation_code: Identifier | None = None
    remediation_path: ProteinInferenceRemediationPath | None = None

    @field_validator("values")
    @classmethod
    def values_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("dimension assessment values must be unique")
        return tuple(sorted(values))

    @field_validator("reason_code")
    @classmethod
    def reason_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else opaque_support_identifier("reason", value)

    @field_validator("remediation_code")
    @classmethod
    def remediation_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else opaque_support_identifier("remediation", value)

    @model_validator(mode="after")
    def codes_match_decision(self) -> ProteinInferenceDimensionAssessment:
        remediation = (self.reason_code, self.remediation_code, self.remediation_path)
        has_any = any(value is not None for value in remediation)
        has_all = all(value is not None for value in remediation)
        if self.decision is ProteinInferenceDimensionSupportDecision.SUPPORTED:
            if has_any:
                raise ValueError("supported dimension assessments cannot carry remediation")
        elif not has_all:
            raise ValueError("only blocking dimension assessments require remediation")
        return self


class ProteinInferenceEnvelopeAssessment(FrozenModel):
    envelope_id: Identifier
    decision: ProteinInferenceEnvelopeSupportDecision
    dimensions: tuple[ProteinInferenceDimensionAssessment, ...] = Field(
        min_length=M0307_DIMENSION_COUNT, max_length=M0307_DIMENSION_COUNT
    )

    @field_validator("envelope_id")
    @classmethod
    def envelope_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("envelope", value)

    @field_validator("dimensions")
    @classmethod
    def dimensions_are_canonical(
        cls, values: tuple[ProteinInferenceDimensionAssessment, ...]
    ) -> tuple[ProteinInferenceDimensionAssessment, ...]:
        return tuple(sorted(values, key=lambda item: item.dimension.value))

    @model_validator(mode="after")
    def decision_matches_dimensions(self) -> ProteinInferenceEnvelopeAssessment:
        if {item.dimension for item in self.dimensions} != set(ProteinInferenceSupportDimension):
            raise ValueError("envelope assessment must cover all eight dimensions")
        decisions = {item.decision for item in self.dimensions}
        expected = (
            ProteinInferenceEnvelopeSupportDecision.ELIMINATED
            if ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN in decisions
            else ProteinInferenceEnvelopeSupportDecision.PROVISIONAL
            if ProteinInferenceDimensionSupportDecision.INDETERMINATE in decisions
            else ProteinInferenceEnvelopeSupportDecision.CONFIRMED
        )
        if self.decision is not expected:
            raise ValueError("envelope decision contradicts dimension assessments")
        return self


class ProteinInferenceAbstention(FrozenModel):
    code: ProteinInferenceAbstentionCode
    envelope_id: Identifier | None = None
    dimension: ProteinInferenceSupportDimension | None = None
    upstream_module_id: Literal["GLIO-PROTEOGEN-M03-04", "GLIO-PROTEOGEN-M03-06"] | None = None
    reason_code: Identifier
    remediation_code: Identifier
    remediation_path: ProteinInferenceRemediationPath

    @field_validator("envelope_id")
    @classmethod
    def envelope_is_opaque(cls, value: Identifier | None) -> Identifier | None:
        return None if value is None else opaque_support_identifier("envelope", value)

    @field_validator("reason_code")
    @classmethod
    def reason_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("reason", value)

    @field_validator("remediation_code")
    @classmethod
    def remediation_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("remediation", value)

    @model_validator(mode="after")
    def shape_matches_code(self) -> ProteinInferenceAbstention:
        if self.code in {
            ProteinInferenceAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
            ProteinInferenceAbstentionCode.DIMENSION_INDETERMINATE,
        }:
            if self.envelope_id is None or self.dimension is None or self.upstream_module_id:
                raise ValueError("dimension abstention requires only envelope and dimension")
        elif self.code is ProteinInferenceAbstentionCode.PREREQUISITE_UNRELEASABLE:
            if self.upstream_module_id is None or self.envelope_id or self.dimension:
                raise ValueError("prerequisite abstention requires only its upstream module")
        elif self.envelope_id or self.dimension or self.upstream_module_id:
            raise ValueError("joint-combination abstention cannot name one dimension")
        return self


class ProteinInferenceSupportRouteResult(FrozenModel):
    output_type: Literal["protein_inference_support_route_result"] = (
        "protein_inference_support_route_result"
    )
    route_id: Identifier
    result_version: Literal["1.0.0"] = M0307_CONTRACT_VERSION
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RouteProteinInferenceSupportRequest
    disposition: ProteinInferenceSupportDisposition
    matched_envelope_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0307_MAX_ENVELOPES)
    envelope_assessments: tuple[ProteinInferenceEnvelopeAssessment, ...] = Field(
        min_length=1, max_length=M0307_MAX_ENVELOPES
    )
    abstention_reasons: tuple[ProteinInferenceAbstention, ...] = Field(
        default=(), max_length=M0307_MAX_ABSTENTIONS
    )
    parent_target: Literal["complex_activity"] = M0307_PARENT
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0307_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=3, max_length=3)
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("route_id")
    @classmethod
    def route_is_opaque(cls, value: Identifier) -> Identifier:
        return opaque_support_identifier("route", value)

    @field_validator("matched_envelope_ids")
    @classmethod
    def matches_are_canonical(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("matched support envelopes must be unique")
        return tuple(sorted(values))

    @field_validator("envelope_assessments", "abstention_reasons", "evidence", "limitations")
    @classmethod
    def result_collections_are_canonical(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_is_canonical(cls, value: UncertaintyProfile) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @field_validator("provenance")
    @classmethod
    def provenance_is_canonical(cls, value: ProvenanceRecord) -> ProvenanceRecord:
        return value.model_copy(
            update={
                "input_digests": tuple(sorted(value.input_digests)),
                "control_decisions": tuple(
                    sorted(value.control_decisions, key=canonical_json_bytes)
                ),
            }
        )

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> ProteinInferenceSupportRouteResult:
        _validate_result(self)
        from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
            result_payload_digest,
        )

        expected = result_payload_digest(self)
        if self.result_digest != expected:
            raise ValueError("M03-07 result digest does not match its content")
        return self


def _opaque(namespace: str, value: object) -> Identifier:
    return f"{namespace}.{sha256_digest(value).removeprefix('sha256:')}"


def quality_support_receipt(value: object) -> ProteinInferenceQualitySupportReceipt:
    """Project a strict full M03-04 result to its privacy-minimized support receipt."""

    result = ProteinInferenceQualityResult.model_validate(value, strict=True)
    raw = result.request.raw_quality_receipt
    qualified = result.disposition is ProteinInferenceQualityDisposition.QUALIFIED
    ledger = result.request.fact_ledger
    metrics = (
        tuple(
            ProteinInferenceQualityMetricSupportReceipt(
                metric_code=item.metric_code,
                observation_state=item.observation_state,
                status=item.status,
                value_ppm=item.value_ppm,
            )
            for item in result.metrics
        )
        if qualified
        else ()
    )
    payload: dict[str, object] = {
        "module_id": "GLIO-PROTEOGEN-M03-04",
        "receipt_version": M0307_CONTRACT_VERSION,
        "artifact_reference": ArtifactReference(
            artifact_id=f"result.m0304.{result.request_digest.removeprefix('sha256:')}",
            version=M0307_CONTRACT_VERSION,
            digest=result.result_digest,
            media_type=_M0304_RESULT_MEDIA_TYPE,
        ),
        "result_digest": result.result_digest,
        "request_digest": result.request_digest,
        "policy_digest": result.policy_digest,
        "configuration_digest": result.configuration_digest,
        "disposition": result.disposition,
        "support_status": result.support.status,
        "human_review_required": result.human_review_required,
        "completed_at": result.completed_at,
        "identity_resolution_digest": raw.identity_resolution_digest,
        "applicability": ledger.applicability if qualified and ledger is not None else None,
        "assay_protocol_version": raw.assay_protocol_version,
        "controlled_vocabulary_version": raw.controlled_vocabulary_version,
        "unit_system_version": raw.unit_system_version,
        "metrics": metrics,
    }
    from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
        quality_support_receipt_digest,
    )

    payload["receipt_digest"] = quality_support_receipt_digest(payload)
    return ProteinInferenceQualitySupportReceipt.model_validate(payload, strict=True)


def harmonization_support_receipt(
    value: object,
) -> ProteinInferenceHarmonizationSupportReceipt:
    """Project a strict full M03-06 result to its privacy-minimized support receipt."""

    result = ProteinInferenceHarmonizationResult.model_validate(value, strict=True)
    upstream = result.request.artifact_receipt
    accepted = result.disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED
    analysis = result.analysis if accepted else None
    manifest = result.transformation_manifest if accepted else None
    platform_ids = (
        tuple(
            sorted(
                {
                    shift.level_id
                    for stage in manifest.stages
                    if stage.factor is ProteinInferenceNormalizationFactor.PLATFORM
                    for shift in stage.level_shifts
                }
            )
        )
        if manifest is not None
        else ()
    )
    evaluable_count = (
        sum(item.harmonized_support_coordinate_ppm is not None for item in analysis.values)
        if analysis is not None
        else 0
    )
    payload: dict[str, object] = {
        "module_id": "GLIO-PROTEOGEN-M03-06",
        "receipt_version": M0307_CONTRACT_VERSION,
        "artifact_reference": ArtifactReference(
            artifact_id=f"result.m0306.{result.request_digest.removeprefix('sha256:')}",
            version=M0307_CONTRACT_VERSION,
            digest=result.result_digest,
            media_type=_M0306_RESULT_MEDIA_TYPE,
        ),
        "result_digest": result.result_digest,
        "request_digest": result.request_digest,
        "policy_digest": result.policy_digest,
        "configuration_digest": result.configuration_digest,
        "disposition": result.disposition,
        "support_status": result.support.status,
        "human_review_required": result.human_review_required,
        "completed_at": result.completed_at,
        "quality_result_digest": upstream.quality_result_digest,
        "identity_resolution_digest": upstream.identity_resolution_digest,
        "applicability": upstream.applicability if accepted else None,
        "assay_protocol_version": upstream.assay_protocol_version,
        "controlled_vocabulary_version": upstream.controlled_vocabulary_version,
        "unit_system_version": upstream.unit_system_version,
        "platform_level_ids": platform_ids,
        "total_unit_count": len(analysis.values) if analysis is not None else 0,
        "retained_unit_count": len(analysis.retain_unit_ids) if analysis is not None else 0,
        "review_unit_count": len(analysis.review_unit_ids) if analysis is not None else 0,
        "excluded_unit_count": len(analysis.exclude_unit_ids) if analysis is not None else 0,
        "evaluable_unit_count": evaluable_count,
        "analysis_digest": analysis.analysis_digest if analysis is not None else None,
    }
    from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
        harmonization_support_receipt_digest,
    )

    payload["receipt_digest"] = harmonization_support_receipt_digest(payload)
    return ProteinInferenceHarmonizationSupportReceipt.model_validate(payload, strict=True)


def _member(candidate: object, field: str) -> object:
    if isinstance(candidate, dict):
        return dict.get(candidate, field)
    if isinstance(candidate, BaseModel):
        return getattr(candidate, field, None)
    return None


def _state(candidate: object) -> object:
    return getattr(candidate, "value", candidate)


def preflight_authorized(candidate: object) -> bool:
    """Inspect only seven shallow controls before any governed payload traversal."""

    try:
        context = _member(candidate, "context")
        references = _member(context, "references")
        expected = (
            ("approved_configuration", UpstreamDecisionState.ACCEPTED.value),
            ("identity_lineage", IdentityLineageState.RESOLVED.value),
            ("provenance", UpstreamDecisionState.ACCEPTED.value),
            ("consent", ConsentState.GRANTED.value),
            ("quality", UpstreamDecisionState.ACCEPTED.value),
            ("support", UpstreamDecisionState.ACCEPTED.value),
            ("intended_use", UpstreamDecisionState.ACCEPTED.value),
        )
        return all(
            _state(_member(_member(references, role), "state")) == state for role, state in expected
        )
    except Exception:  # noqa: BLE001 - hostile shallow access collapses to denial.
        return False


def _validate_route_boundary(request: RouteProteinInferenceSupportRequest) -> None:
    if not preflight_authorized(request):
        raise ValueError("protein-inference support routing is not authorized")
    if request.request_id != request.context.request_id:
        raise ValueError("M03-07 request and execution context identifiers disagree")
    fact_dimensions = tuple(item.dimension for item in request.declared_facts)
    expected_facts = {
        ProteinInferenceSupportDimension.SPECIMEN,
        ProteinInferenceSupportDimension.DISEASE_CLASS,
        ProteinInferenceSupportDimension.REFERENCE,
        ProteinInferenceSupportDimension.INTENDED_USE,
    }
    if (
        len(set(fact_dimensions)) != M0307_DECLARED_FACT_COUNT
        or set(fact_dimensions) != expected_facts
    ):
        raise ValueError("route requires exactly four caller-declared support dimensions")
    roles = tuple(item.role for item in request.context_receipts)
    if len(set(roles)) != M0307_CONTEXT_RECEIPT_COUNT or set(roles) != set(
        ProteinInferenceContextRole
    ):
        raise ValueError("route requires all three context receipt roles")
    if len(request.profile.envelopes) > request.policy.max_envelopes:
        raise ValueError("support profile exceeds its reviewed policy capacity")
    from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
        configuration_digest,
    )

    references = request.context.references
    prerequisites = request.prerequisites
    if references.approved_configuration.evidence.digest != configuration_digest(
        request.profile, request.policy
    ):
        raise ValueError("approved configuration does not bind M03-07")
    if (
        references.identity_lineage.binding_digest
        != prerequisites.quality.identity_resolution_digest
        or references.quality.evidence.digest != prerequisites.quality.result_digest
        or references.support.evidence.digest != prerequisites.harmonization.result_digest
    ):
        raise ValueError("M03-07 controls do not bind the exact prerequisite chain")
    if (
        request.policy.reviewed_at > request.context.occurred_at
        or prerequisites.harmonization.completed_at > request.context.occurred_at
    ):
        raise ValueError("M03-07 policy or prerequisite chronology is impossible")
    support_route_evidence_index(request)


def support_route_evidence_index(
    request: RouteProteinInferenceSupportRequest,
) -> tuple[EvidenceReference, ...]:
    """Return the exact de-duplicated evidence index, rejecting identity conflicts."""

    refs = request.context.references
    artifacts = [
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.profile.evidence,
        request.policy.evidence,
        request.prerequisites.quality.artifact_reference,
        request.prerequisites.harmonization.artifact_reference,
    ]
    artifacts.extend(reference for fact in request.declared_facts for reference in fact.evidence)
    artifacts.extend(
        receipt.reference for receipt in request.context_receipts if receipt.reference is not None
    )
    by_identity: dict[tuple[str, str], ArtifactReference] = {}
    for reference in artifacts:
        identity = (reference.artifact_id, reference.version)
        existing = by_identity.get(identity)
        if existing is not None and existing != reference:
            raise ValueError("one artifact identity cannot carry conflicting evidence metadata")
        by_identity[identity] = reference
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item
        for item in by_identity.values()
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0307_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def _remediation(
    envelope: ProteinInferenceSupportEnvelope,
    dimension: ProteinInferenceSupportDimension,
) -> ProteinInferenceDimensionRemediation:
    return next(item for item in envelope.remediations if item.dimension is dimension)


def _assessment(  # noqa: PLR0913 - one exact dimension projection.
    envelope: ProteinInferenceSupportEnvelope,
    dimension: ProteinInferenceSupportDimension,
    state: ProteinInferenceDeclaredSupportState,
    values: tuple[Identifier, ...],
    allowed: set[str],
    *,
    numeric_value_ppm: int | None = None,
    minimum_ppm: int | None = None,
    context_supported: bool = True,
    explicit_supported: bool | None = None,
) -> ProteinInferenceDimensionAssessment:
    remediation = _remediation(envelope, dimension)
    if state is not ProteinInferenceDeclaredSupportState.OBSERVED or not context_supported:
        decision = ProteinInferenceDimensionSupportDecision.INDETERMINATE
        reason = remediation.indeterminate_reason_code
    elif explicit_supported is not None:
        decision = (
            ProteinInferenceDimensionSupportDecision.SUPPORTED
            if explicit_supported
            else ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    elif minimum_ppm is not None:
        decision = (
            ProteinInferenceDimensionSupportDecision.SUPPORTED
            if numeric_value_ppm is not None and numeric_value_ppm >= minimum_ppm
            else ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    else:
        decision = (
            ProteinInferenceDimensionSupportDecision.SUPPORTED
            if set(values).issubset(allowed)
            else ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN
        )
        reason = remediation.outside_reason_code
    supported = decision is ProteinInferenceDimensionSupportDecision.SUPPORTED
    return ProteinInferenceDimensionAssessment(
        dimension=dimension,
        decision=decision,
        values=tuple(sorted(values)),
        numeric_value_ppm=numeric_value_ppm,
        reason_code=None if supported else reason,
        remediation_code=None if supported else remediation.remediation_code,
        remediation_path=None if supported else remediation.remediation_path,
    )


def _prerequisites_releasable(prerequisites: ProteinInferenceSupportPrerequisites) -> bool:
    return (
        prerequisites.quality.disposition is ProteinInferenceQualityDisposition.QUALIFIED
        and prerequisites.quality.support_status in {SupportStatus.SUPPORTED, SupportStatus.LIMITED}
        and not prerequisites.quality.human_review_required
        and prerequisites.harmonization.disposition
        is ProteinInferenceHarmonizationDisposition.ACCEPTED
        and prerequisites.harmonization.support_status is SupportStatus.LIMITED
        and not prerequisites.harmonization.human_review_required
    )


def _envelope_assessment(
    envelope: ProteinInferenceSupportEnvelope,
    prerequisites: ProteinInferenceSupportPrerequisites,
    facts: tuple[ProteinInferenceDeclaredSupportFact, ...],
    contexts: tuple[ProteinInferenceContextReceipt, ...],
) -> ProteinInferenceEnvelopeAssessment:
    fact_map = {item.dimension: item for item in facts}
    context_map = {item.role: item for item in contexts}
    quality = prerequisites.quality
    harmonization = prerequisites.harmonization
    releasable = _prerequisites_releasable(prerequisites)
    assay_supported = releasable and (
        quality.applicability in envelope.applicabilities
        and quality.assay_protocol_version in envelope.approved_assay_protocol_versions
        and quality.controlled_vocabulary_version
        in envelope.approved_controlled_vocabulary_versions
        and quality.unit_system_version in envelope.approved_unit_system_versions
    )
    quality_values = tuple(sorted({item.status.value for item in quality.metrics}))
    completeness_metric = next(
        (
            item
            for item in quality.metrics
            if item.metric_code is ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS
        ),
        None,
    )
    harmonized_ppm = (
        (
            harmonization.evaluable_unit_count * M0307_RATE_SCALE
            + harmonization.total_unit_count // 2
        )
        // harmonization.total_unit_count
        if releasable and harmonization.total_unit_count > 0
        else None
    )
    completeness = (
        min(completeness_metric.value_ppm, harmonized_ppm)
        if completeness_metric is not None
        and completeness_metric.value_ppm is not None
        and harmonized_ppm is not None
        else None
    )
    reference_roles = {
        ProteinInferenceContextRole.GENOME_TRANSCRIPTOME,
        ProteinInferenceContextRole.PTM_ANNOTATIONS,
    }
    required_reference = set(envelope.required_context_roles) & reference_roles
    required_intended = set(envelope.required_context_roles) & {
        ProteinInferenceContextRole.TREATMENT_HISTORY
    }
    reference_context = all(
        context_map[role].state is ProteinInferenceDeclaredSupportState.OBSERVED
        for role in required_reference
    )
    intended_context = all(
        context_map[role].state is ProteinInferenceDeclaredSupportState.OBSERVED
        for role in required_intended
    )
    specimen = fact_map[ProteinInferenceSupportDimension.SPECIMEN]
    disease = fact_map[ProteinInferenceSupportDimension.DISEASE_CLASS]
    reference = fact_map[ProteinInferenceSupportDimension.REFERENCE]
    intended = fact_map[ProteinInferenceSupportDimension.INTENDED_USE]
    dimensions = (
        _assessment(
            envelope,
            ProteinInferenceSupportDimension.ASSAY,
            ProteinInferenceDeclaredSupportState.OBSERVED
            if releasable
            else ProteinInferenceDeclaredSupportState.UNKNOWN,
            ((quality.applicability.value,) if quality.applicability is not None else ()),
            set(),
            explicit_supported=assay_supported,
        ),
        _assessment(
            envelope,
            specimen.dimension,
            specimen.state,
            specimen.values,
            set(envelope.specimen_terms),
        ),
        _assessment(
            envelope,
            disease.dimension,
            disease.state,
            disease.values,
            set(envelope.disease_class_terms),
        ),
        _assessment(
            envelope,
            ProteinInferenceSupportDimension.QUALITY,
            ProteinInferenceDeclaredSupportState.OBSERVED
            if releasable
            else ProteinInferenceDeclaredSupportState.UNKNOWN,
            quality_values,
            {item.value for item in envelope.quality_statuses},
        ),
        _assessment(
            envelope,
            ProteinInferenceSupportDimension.COMPLETENESS,
            ProteinInferenceDeclaredSupportState.OBSERVED
            if completeness is not None
            else ProteinInferenceDeclaredSupportState.UNKNOWN,
            (),
            set(),
            numeric_value_ppm=completeness,
            minimum_ppm=envelope.minimum_completeness_ppm,
        ),
        _assessment(
            envelope,
            ProteinInferenceSupportDimension.PLATFORM,
            ProteinInferenceDeclaredSupportState.OBSERVED
            if releasable
            else ProteinInferenceDeclaredSupportState.UNKNOWN,
            harmonization.platform_level_ids,
            set(envelope.platform_level_ids),
        ),
        _assessment(
            envelope,
            reference.dimension,
            reference.state,
            reference.values,
            set(envelope.reference_terms),
            context_supported=reference_context,
        ),
        _assessment(
            envelope,
            intended.dimension,
            intended.state,
            intended.values,
            set(envelope.intended_use_terms),
            context_supported=intended_context,
        ),
    )
    decisions = {item.decision for item in dimensions}
    decision = (
        ProteinInferenceEnvelopeSupportDecision.ELIMINATED
        if ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN in decisions
        else ProteinInferenceEnvelopeSupportDecision.PROVISIONAL
        if ProteinInferenceDimensionSupportDecision.INDETERMINATE in decisions
        else ProteinInferenceEnvelopeSupportDecision.CONFIRMED
    )
    return ProteinInferenceEnvelopeAssessment(
        envelope_id=envelope.envelope_id,
        decision=decision,
        dimensions=dimensions,
    )


def _union_covers(assessments: tuple[ProteinInferenceEnvelopeAssessment, ...]) -> bool:
    return all(
        any(
            next(item for item in envelope.dimensions if item.dimension is dimension).decision
            is ProteinInferenceDimensionSupportDecision.SUPPORTED
            for envelope in assessments
        )
        for dimension in ProteinInferenceSupportDimension
    )


def derive_support_route(
    prerequisites: ProteinInferenceSupportPrerequisites,
    profile: ProteinInferenceSupportProfile,
    facts: tuple[ProteinInferenceDeclaredSupportFact, ...],
    contexts: tuple[ProteinInferenceContextReceipt, ...],
) -> tuple[
    tuple[ProteinInferenceEnvelopeAssessment, ...],
    tuple[Identifier, ...],
    tuple[ProteinInferenceAbstention, ...],
]:
    """Derive the complete single-envelope route and every typed blocker."""

    assessments = tuple(
        sorted(
            (
                _envelope_assessment(envelope, prerequisites, facts, contexts)
                for envelope in profile.envelopes
            ),
            key=lambda item: item.envelope_id,
        )
    )
    matches = tuple(
        item.envelope_id
        for item in assessments
        if item.decision is ProteinInferenceEnvelopeSupportDecision.CONFIRMED
    )
    if matches and _prerequisites_releasable(prerequisites):
        return assessments, matches, ()
    abstentions: list[ProteinInferenceAbstention] = []
    upstream: tuple[
        tuple[
            Literal["GLIO-PROTEOGEN-M03-04", "GLIO-PROTEOGEN-M03-06"],
            bool,
        ],
        ...,
    ] = (
        (
            "GLIO-PROTEOGEN-M03-04",
            prerequisites.quality.disposition is ProteinInferenceQualityDisposition.QUALIFIED,
        ),
        (
            "GLIO-PROTEOGEN-M03-06",
            prerequisites.harmonization.disposition
            is ProteinInferenceHarmonizationDisposition.ACCEPTED,
        ),
    )
    for module_id, releasable in upstream:
        if not releasable:
            abstentions.append(
                ProteinInferenceAbstention(
                    code=ProteinInferenceAbstentionCode.PREREQUISITE_UNRELEASABLE,
                    upstream_module_id=module_id,
                    reason_code=_opaque("reason", {"module": module_id, "state": "unreleasable"}),
                    remediation_code=_opaque(
                        "remediation", {"module": module_id, "action": "resolve"}
                    ),
                    remediation_path=ProteinInferenceRemediationPath.RESOLVE_UPSTREAM_PREREQUISITE,
                )
            )
    for envelope in assessments:
        for dimension in envelope.dimensions:
            if dimension.decision is ProteinInferenceDimensionSupportDecision.SUPPORTED:
                continue
            abstentions.append(
                ProteinInferenceAbstention(
                    code=(
                        ProteinInferenceAbstentionCode.DIMENSION_OUTSIDE_DOMAIN
                        if dimension.decision
                        is ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN
                        else ProteinInferenceAbstentionCode.DIMENSION_INDETERMINATE
                    ),
                    envelope_id=envelope.envelope_id,
                    dimension=dimension.dimension,
                    reason_code=dimension.reason_code or _opaque("reason", dimension.dimension),
                    remediation_code=dimension.remediation_code
                    or _opaque("remediation", dimension.dimension),
                    remediation_path=dimension.remediation_path
                    or ProteinInferenceRemediationPath.REQUEST_GOVERNED_SUPPORT_REVIEW,
                )
            )
    if _union_covers(assessments):
        abstentions.append(
            ProteinInferenceAbstention(
                code=ProteinInferenceAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN,
                reason_code=_opaque("reason", "joint_combination_outside_domain"),
                remediation_code=_opaque("remediation", "select_one_joint_envelope"),
                remediation_path=ProteinInferenceRemediationPath.SELECT_ONE_REVIEWED_JOINT_ENVELOPE,
            )
        )
    unique = {canonical_json_bytes(item): item for item in abstentions}
    return assessments, (), tuple(unique[key] for key in sorted(unique))


def expected_support(disposition: ProteinInferenceSupportDisposition) -> SupportDecision:
    if disposition is ProteinInferenceSupportDisposition.SUPPORTED:
        return SupportDecision(
            status=SupportStatus.LIMITED,
            reason_code="protein_inference_support_confirmed",
            rationale="One complete reviewed protein-inference support envelope was confirmed.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="protein_inference_support_abstained",
        rationale="No complete reviewed protein-inference support envelope was confirmed.",
    )


def expected_uncertainty(
    disposition: ProteinInferenceSupportDisposition,
) -> UncertaintyProfile:
    del disposition
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0307_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0307_SENSITIVITY_NOTES,
    )


def expected_control_decisions(
    request: RouteProteinInferenceSupportRequest,
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


def expected_provenance(request: RouteProteinInferenceSupportRequest) -> ProvenanceRecord:
    from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
        canonical_request_digest,
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    request_hash = canonical_request_digest(request)
    evidence_digests = {item.reference.digest for item in support_route_evidence_index(request)}
    input_digests = {
        request_hash,
        request.prerequisites.quality.receipt_digest,
        request.prerequisites.harmonization.receipt_digest,
        profile_digest(request.profile),
        policy_digest(request.policy),
        configuration_digest(request.profile, request.policy),
        *evidence_digests,
    }
    if request.supersedes_result_digest is not None:
        input_digests.add(request.supersedes_result_digest)
    return ProvenanceRecord(
        activity_id=f"activity.m0307.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0307_MODULE_ID,
        module_version=M0307_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=tuple(sorted(input_digests)),
        configuration_digest=configuration_digest(request.profile, request.policy),
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
                    code=M0307_ROUTING_LIMITATION_CODE,
                    statement=(
                        "This output routes support only; it does not infer protein, "
                        "proteoform, complex activity, kinase activity, subtype, or treatment."
                    ),
                ),
                Limitation(
                    code=M0307_AUTHORITY_LIMITATION_CODE,
                    statement=(
                        "Upstream receipts and caller evidence are self-consistent but their "
                        "external issuer authority is not authenticated."
                    ),
                ),
                Limitation(
                    code=M0307_DOMAIN_LIMITATION_CODE,
                    statement=(
                        "A reviewed support envelope is a governed engineering boundary, not "
                        "assay validation, biological truth, or clinical fitness."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


def _validate_result(result: ProteinInferenceSupportRouteResult) -> None:
    from glio_proteogen.contracts.m03_07.canonical import (  # noqa: PLC0415
        canonical_request_digest,
        configuration_digest,
        policy_digest,
        profile_digest,
    )

    _validate_route_boundary(result.request)
    expected_assessments, expected_matches, expected_abstentions = derive_support_route(
        result.request.prerequisites,
        result.request.profile,
        result.request.declared_facts,
        result.request.context_receipts,
    )
    disposition = (
        ProteinInferenceSupportDisposition.SUPPORTED
        if expected_matches
        else ProteinInferenceSupportDisposition.ABSTAINED
    )
    request_hash = canonical_request_digest(result.request)
    if (
        result.request_digest != request_hash
        or result.profile_digest != profile_digest(result.request.profile)
        or result.policy_digest != policy_digest(result.request.policy)
        or result.configuration_digest
        != configuration_digest(result.request.profile, result.request.policy)
    ):
        raise ValueError("M03-07 result digest bindings are inconsistent")
    if (
        result.envelope_assessments != expected_assessments
        or result.matched_envelope_ids != expected_matches
        or result.abstention_reasons != expected_abstentions
        or result.disposition is not disposition
    ):
        raise ValueError("M03-07 result contradicts deterministic joint-envelope routing")
    if (
        result.route_id != f"route.{request_hash.removeprefix('sha256:')}"
        or result.support != expected_support(disposition)
        or result.uncertainty != expected_uncertainty(disposition)
        or result.provenance != expected_provenance(result.request)
        or result.evidence != support_route_evidence_index(result.request)
        or result.limitations != expected_limitations()
        or result.human_review_required
        != (disposition is ProteinInferenceSupportDisposition.ABSTAINED)
        or result.completed_at != result.request.context.occurred_at
    ):
        raise ValueError("M03-07 result envelope does not replay exactly")


__all__ = [
    "M0307_AUTHORITY_LIMITATION_CODE",
    "M0307_CONTEXT_RECEIPT_COUNT",
    "M0307_CONTRACT_VERSION",
    "M0307_DECLARED_FACT_COUNT",
    "M0307_DIMENSION_COUNT",
    "M0307_DOMAIN_LIMITATION_CODE",
    "M0307_EVIDENCE_CLAIM",
    "M0307_GATE",
    "M0307_MAX_ABSTENTIONS",
    "M0307_MAX_APPROVED_VERSIONS",
    "M0307_MAX_CANONICAL_REQUEST_BYTES",
    "M0307_MAX_ENVELOPES",
    "M0307_MAX_EVIDENCE",
    "M0307_MAX_EVIDENCE_PER_FACT",
    "M0307_MAX_FACT_VALUES",
    "M0307_MAX_PLATFORM_LEVEL_IDS",
    "M0307_MODULE_ID",
    "M0307_OPERATION",
    "M0307_OWNER",
    "M0307_PARENT",
    "M0307_RATE_SCALE",
    "M0307_ROUTING_LIMITATION_CODE",
    "M0307_SAFETY_CLASS",
    "M0307_SENSITIVITY_NOTES",
    "M0307_UNCERTAINTY_RATIONALES",
    "M0307_ZERO_DIGEST",
    "ProteinInferenceAbstention",
    "ProteinInferenceAbstentionCode",
    "ProteinInferenceContextReceipt",
    "ProteinInferenceContextRole",
    "ProteinInferenceDeclaredSupportFact",
    "ProteinInferenceDeclaredSupportState",
    "ProteinInferenceDimensionAssessment",
    "ProteinInferenceDimensionRemediation",
    "ProteinInferenceDimensionSupportDecision",
    "ProteinInferenceEnvelopeAssessment",
    "ProteinInferenceEnvelopeSupportDecision",
    "ProteinInferenceHarmonizationSupportReceipt",
    "ProteinInferenceQualityMetricSupportReceipt",
    "ProteinInferenceQualitySupportReceipt",
    "ProteinInferenceRemediationPath",
    "ProteinInferenceSupportDimension",
    "ProteinInferenceSupportDisposition",
    "ProteinInferenceSupportEnvelope",
    "ProteinInferenceSupportPolicy",
    "ProteinInferenceSupportPrerequisites",
    "ProteinInferenceSupportProfile",
    "ProteinInferenceSupportRouteResult",
    "RouteProteinInferenceSupportRequest",
    "derive_support_route",
    "expected_control_decisions",
    "expected_limitations",
    "expected_provenance",
    "expected_support",
    "expected_uncertainty",
    "harmonization_support_receipt",
    "opaque_support_identifier",
    "preflight_authorized",
    "quality_support_receipt",
    "support_route_evidence_index",
]
