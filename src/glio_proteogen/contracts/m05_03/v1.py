"""Strict M05-03 ptm_localization raw-input ingestion contracts."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Final, Literal, cast

from pydantic import (
    AwareDatetime,
    Field,
    StringConstraints,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from glio_proteogen.contracts.m05_01 import (
    PtmLocalizationAssayKind,
    PtmLocalizationInputRole,
    PtmLocalizationSupportDomain,
    PtmLocalizationUnit,
    opaque_ptm_localization_protocol_identifier,
)
from glio_proteogen.contracts.m05_02 import (
    PtmLocalizationIdentityLineageResolution,
    PtmLocalizationLineageArtifactRole,
    opaque_ptm_localization_lineage_identifier,
)
from glio_proteogen.contracts.m05_03.canonical import (
    artifact_mapping_digest,
    canonical_request_digest,
    configuration_digest,
    context_digest,
    document_digest,
    normalized_lineage_result,
    normalized_request,
    policy_digest,
    receipt_digest,
    result_payload_digest,
    validated_inputs_digest,
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

M0503_MODULE_ID: Final = "GLIO-PROTEOGEN-M05-03"
M0503_OPERATION: Final = "ingest_ptm_localization_raw_inputs"
M0503_PARENT: Final = "variant_peptide"
M0503_CONTRACT_VERSION: Final = "1.0.0"
M0503_ROLE_COUNT: Final = 4
M0503_MIN_APPROVED_PARSERS: Final = 4
M0503_MAX_APPROVED_PARSERS: Final = 32
M0503_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0503_MAX_DOCUMENT_BYTES: Final = 8 * 1024 * 1024
M0503_MAX_TOTAL_DOCUMENT_BYTES: Final = 32 * 1024 * 1024
M0503_MAX_DECLARED_RECORD_COUNT: Final = 9_223_372_036_854_775_807
M0503_DIAGNOSTIC_CODE_COUNT: Final = 17
M0503_MAX_DIAGNOSTICS: Final = 60
M0503_LIMITATION_COUNT: Final = 3
M0503_MIN_EVIDENCE: Final = 20
M0503_MAX_EVIDENCE: Final = 48
_M0503_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0503_EVIDENCE_CLAIM: Final = (
    "Caller-declared content-addressed M05-03 raw-manifest validation evidence."
)

_OPAQUE_IDENTIFIER = re.compile(
    r"^(?:request|actor|decision|policy|parser|input|evidence|reviewer)"
    r"\.[0-9a-f]{64}$"
)

type PtmLocalizationRawInputOpaqueNamespace = Literal[
    "request",
    "actor",
    "decision",
    "policy",
    "parser",
    "input",
    "evidence",
    "reviewer",
]


def opaque_ptm_localization_raw_input_identifier(
    namespace: PtmLocalizationRawInputOpaqueNamespace,
    value: Identifier,
) -> Identifier:
    """Validate one module-owned opaque identifier."""

    if _OPAQUE_IDENTIFIER.fullmatch(value) is None or not value.startswith(f"{namespace}."):
        raise ValueError("M05-03 identifiers must use their exact opaque local namespace")
    return value


class PtmLocalizationRawInputRole(StrEnum):
    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME = "genome"
    TRANSCRIPTOME = "transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"


class PtmLocalizationRawDocumentFormat(StrEnum):
    PROTEOME_MANIFEST_JSON = "proteome_manifest_json"
    GENOME_MANIFEST_JSON = "genome_manifest_json"
    TRANSCRIPTOME_MANIFEST_JSON = "transcriptome_manifest_json"
    PTM_ANNOTATION_MANIFEST_JSON = "ptm_annotation_manifest_json"


class PtmLocalizationRawReferenceRole(StrEnum):
    """The reviewed M05-01 reference role bound by one raw document."""

    MASS_SPECTROMETRY_PROTEOME = "mass_spectrometry_proteome"
    GENOME_TRANSCRIPTOME = "genome_transcriptome"
    PTM_ANNOTATIONS = "ptm_annotations"


class PtmLocalizationRawEvidenceState(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    INDETERMINATE = "indeterminate"
    UNSUPPORTED = "unsupported"
    REDACTED = "redacted"


class PtmLocalizationRawCompletenessState(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_EVALUABLE = "not_evaluable"


class PtmLocalizationRawAssaySupportState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    NOT_EVALUABLE = "not_evaluable"


class PtmLocalizationRawParentQualityState(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NOT_EVALUABLE = "not_evaluable"


class PtmLocalizationRawInputDisposition(StrEnum):
    VALIDATED = "validated"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"


class PtmLocalizationRawDiagnosticAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"


class PtmLocalizationRawDiagnosticCode(StrEnum):
    UPSTREAM_LINEAGE_QUARANTINED = "upstream_lineage_quarantined"
    UPSTREAM_LINEAGE_ABSTAINED = "upstream_lineage_abstained"
    ARTIFACT_NOT_EVALUABLE = "artifact_not_evaluable"
    MANIFEST_CLAIM_MISMATCH = "manifest_claim_mismatch"
    IDENTITY_BINDING_MISMATCH = "identity_binding_mismatch"
    PROTOCOL_BINDING_MISMATCH = "protocol_binding_mismatch"
    REFERENCE_BUNDLE_MISMATCH = "reference_bundle_mismatch"
    ASSAY_SPECIMEN_POLICY_MISMATCH = "assay_specimen_policy_mismatch"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    UNSUPPORTED_FORMAT_VERSION = "unsupported_format_version"
    UNIT_MISMATCH = "unit_mismatch"
    ASSAY_PROTOCOL_MISMATCH = "assay_protocol_mismatch"
    SPECIMEN_PROCESSING_MISMATCH = "specimen_processing_mismatch"
    INCOMPLETE_MANIFEST = "incomplete_manifest"
    ASSAY_UNSUPPORTED = "assay_unsupported"
    PARENT_QUALITY_UNACCEPTABLE = "parent_quality_unacceptable"
    DUPLICATE_CONTENT_RETAINED = "duplicate_content_retained"


_LOWERCASE_MEDIA_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")
_CONTROL_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.control+json"
_POLICY_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-03.policy+json"
_PARSER_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m05-03.parser+json"
_ROLE_CONTENT_MEDIA_TYPES: Final = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        "application/vnd.glio-proteogen.m05-03.proteome-input+json"
    ),
    PtmLocalizationRawInputRole.GENOME: "application/vnd.glio-proteogen.m05-03.genome-input+json",
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        "application/vnd.glio-proteogen.m05-03.transcriptome-input+json"
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        "application/vnd.glio-proteogen.m05-03.ptm-annotation-input+json"
    ),
}
_ROLE_MANIFEST_MEDIA_TYPES: Final = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        "application/vnd.glio-proteogen.m05-02.mass-spectrometry-proteome-manifest+json"
    ),
    PtmLocalizationRawInputRole.GENOME: (
        "application/vnd.glio-proteogen.m05-02.genome-manifest+json"
    ),
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        "application/vnd.glio-proteogen.m05-02.transcriptome-manifest+json"
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        "application/vnd.glio-proteogen.m05-02.ptm-annotation-manifest+json"
    ),
}
_ROLE_FORMATS: Final = {
    PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
        PtmLocalizationRawDocumentFormat.PROTEOME_MANIFEST_JSON
    ),
    PtmLocalizationRawInputRole.GENOME: PtmLocalizationRawDocumentFormat.GENOME_MANIFEST_JSON,
    PtmLocalizationRawInputRole.TRANSCRIPTOME: (
        PtmLocalizationRawDocumentFormat.TRANSCRIPTOME_MANIFEST_JSON
    ),
    PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
        PtmLocalizationRawDocumentFormat.PTM_ANNOTATION_MANIFEST_JSON
    ),
}

DocumentType = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,127}$"),
]


def _owned_identifier(
    namespace: PtmLocalizationRawInputOpaqueNamespace, value: Identifier
) -> Identifier:
    return opaque_ptm_localization_raw_input_identifier(namespace, value)


def _owned_artifact(
    value: ArtifactReference,
    *,
    media_type: str,
    namespace: Literal["evidence", "input"] = "evidence",
) -> ArtifactReference:
    _owned_identifier(namespace, value.artifact_id)
    if _LOWERCASE_MEDIA_TYPE.fullmatch(value.media_type) is None or value.media_type != media_type:
        raise ValueError("M05-03 artifact media type is outside its exact owned role")
    return value


class ApprovedPtmLocalizationRawParser(FrozenModel):
    """One reviewed role-specific parser declaration."""

    role: PtmLocalizationRawInputRole
    format: PtmLocalizationRawDocumentFormat
    format_version: SemanticVersion
    parser_version: SemanticVersion
    media_type: str
    max_document_bytes: int = Field(gt=0, le=M0503_MAX_DOCUMENT_BYTES)
    evidence: ArtifactReference

    @model_validator(mode="after")
    def parser_is_role_closed(self) -> ApprovedPtmLocalizationRawParser:
        if self.format is not _ROLE_FORMATS[self.role]:
            raise ValueError("approved parser format must match its exact raw-input role")
        if self.media_type != _ROLE_CONTENT_MEDIA_TYPES[self.role]:
            raise ValueError("approved parser media type must match its exact raw-input role")
        _owned_artifact(self.evidence, media_type=_PARSER_MEDIA_TYPE)
        return self


class PtmLocalizationRawInputPolicy(FrozenModel):
    """Reviewed deterministic manifest-ingestion bounds."""

    policy_id: Identifier
    version: SemanticVersion
    max_document_bytes: int = Field(
        default=M0503_MAX_DOCUMENT_BYTES, gt=0, le=M0503_MAX_DOCUMENT_BYTES
    )
    max_total_bytes: int = Field(
        default=M0503_MAX_TOTAL_DOCUMENT_BYTES,
        ge=M0503_ROLE_COUNT,
        le=M0503_MAX_TOTAL_DOCUMENT_BYTES,
    )
    require_canonical_json: Literal[True] = True
    require_exact_role_mapping: Literal[True] = True
    reject_duplicate_json_keys: Literal[True] = True
    quarantine_on_semantic_mismatch: Literal[True] = True
    abstain_on_not_evaluable: Literal[True] = True
    retain_duplicate_content: Literal[True] = True
    approved_parsers: tuple[ApprovedPtmLocalizationRawParser, ...] = Field(
        min_length=M0503_MIN_APPROVED_PARSERS,
        max_length=M0503_MAX_APPROVED_PARSERS,
    )
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @field_validator("approved_parsers")
    @classmethod
    def parsers_are_unique_and_canonical(
        cls,
        values: tuple[ApprovedPtmLocalizationRawParser, ...],
    ) -> tuple[ApprovedPtmLocalizationRawParser, ...]:
        identities = tuple(
            (item.role, item.format, item.format_version, item.parser_version) for item in values
        )
        if len(identities) != len(set(identities)):
            raise ValueError("approved parser identities must be unique")
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def policy_is_role_closed(self) -> PtmLocalizationRawInputPolicy:
        _owned_identifier("policy", self.policy_id)
        _owned_identifier("reviewer", self.reviewed_by)
        _owned_artifact(self.evidence, media_type=_POLICY_MEDIA_TYPE)
        if {item.role for item in self.approved_parsers} != set(PtmLocalizationRawInputRole):
            raise ValueError("approved parser profiles must cover all four raw-input roles")
        if self.max_total_bytes < self.max_document_bytes:
            raise ValueError("total byte cap cannot be below the per-document cap")
        if any(item.max_document_bytes > self.max_document_bytes for item in self.approved_parsers):
            raise ValueError("approved parser cap cannot exceed the active policy cap")
        artifacts = (self.evidence, *(item.evidence for item in self.approved_parsers))
        identities = tuple((item.artifact_id, item.version) for item in artifacts)
        if len(identities) != len(set(identities)) or len(
            {item.digest for item in artifacts}
        ) != len(artifacts):
            raise ValueError("policy evidence identities and digests must be unique")
        return self


class PtmLocalizationRawInputArtifact(FrozenModel):
    """One exact M05-02 manifest claim paired with a canonical document declaration."""

    role: PtmLocalizationRawInputRole
    lineage_claim_id: Identifier
    manifest_reference: ArtifactReference
    content_reference: ArtifactReference
    declared_size_bytes: int = Field(ge=0, le=M0503_MAX_DOCUMENT_BYTES)
    format: PtmLocalizationRawDocumentFormat
    format_version: SemanticVersion
    parser_version: SemanticVersion

    @model_validator(mode="after")
    def artifact_is_structurally_role_closed(self) -> PtmLocalizationRawInputArtifact:
        opaque_ptm_localization_lineage_identifier("claim", self.lineage_claim_id)
        opaque_ptm_localization_lineage_identifier("evidence", self.manifest_reference.artifact_id)
        if self.manifest_reference.media_type != _ROLE_MANIFEST_MEDIA_TYPES[self.role]:
            raise ValueError("manifest reference media type must match its exact M05-02 role")
        _owned_identifier("input", self.content_reference.artifact_id)
        if _LOWERCASE_MEDIA_TYPE.fullmatch(self.content_reference.media_type) is None:
            raise ValueError(
                "content reference media type must be lowercase and syntactically valid"
            )
        if self.format is not _ROLE_FORMATS[self.role]:
            raise ValueError("artifact format must match its exact raw-input role")
        return self


class _PtmLocalizationRawDocumentBase(FrozenModel):
    document_type: DocumentType
    document_version: Literal["1.0.0"] = M0503_CONTRACT_VERSION
    input_id: Identifier
    lineage_claim_id: Identifier
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    assay_specimen_policy_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    assay_protocol_version: SemanticVersion
    specimen_processing_version: SemanticVersion
    unit_system_version: SemanticVersion
    reference_bundle_version: SemanticVersion
    content_reference: ArtifactReference
    declared_record_count: int = Field(ge=0, le=M0503_MAX_DECLARED_RECORD_COUNT)
    evidence_state: PtmLocalizationRawEvidenceState
    completeness_state: PtmLocalizationRawCompletenessState
    assay_support_state: PtmLocalizationRawAssaySupportState
    parent_quality_state: PtmLocalizationRawParentQualityState

    @model_validator(mode="after")
    def common_identifiers_are_owned(self) -> _PtmLocalizationRawDocumentBase:
        _owned_identifier("input", self.input_id)
        opaque_ptm_localization_lineage_identifier("claim", self.lineage_claim_id)
        _owned_identifier("input", self.content_reference.artifact_id)
        if _LOWERCASE_MEDIA_TYPE.fullmatch(self.content_reference.media_type) is None:
            raise ValueError(
                "document content media type must be lowercase and syntactically valid"
            )
        return self


class MassSpectrometryProteomeInputDocument(_PtmLocalizationRawDocumentBase):
    document_type: Literal["mass_spectrometry_proteome_input"] = "mass_spectrometry_proteome_input"
    reference_role: Literal[PtmLocalizationRawReferenceRole.MASS_SPECTROMETRY_PROTEOME] = (
        PtmLocalizationRawReferenceRole.MASS_SPECTROMETRY_PROTEOME
    )
    reference_digest: Sha256Digest
    assay_kind: PtmLocalizationAssayKind
    support_domain: PtmLocalizationSupportDomain
    declared_units: tuple[PtmLocalizationUnit, ...] = Field(min_length=1, max_length=16)

    @field_validator("declared_units")
    @classmethod
    def units_are_unique_and_canonical(
        cls, values: tuple[PtmLocalizationUnit, ...]
    ) -> tuple[PtmLocalizationUnit, ...]:
        if len(values) != len(set(values)):
            raise ValueError("mass-spectrometry unit declarations must be unique")
        return tuple(sorted(values))


class GenomeInputDocument(_PtmLocalizationRawDocumentBase):
    document_type: Literal["genome_input"] = "genome_input"
    reference_role: Literal[PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME] = (
        PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME
    )
    reference_digest: Sha256Digest
    reference_build: Identifier


class TranscriptomeInputDocument(_PtmLocalizationRawDocumentBase):
    document_type: Literal["transcriptome_input"] = "transcriptome_input"
    reference_role: Literal[PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME] = (
        PtmLocalizationRawReferenceRole.GENOME_TRANSCRIPTOME
    )
    reference_digest: Sha256Digest
    annotation_build: Identifier


class PtmAnnotationInputDocument(_PtmLocalizationRawDocumentBase):
    document_type: Literal["ptm_annotation_input"] = "ptm_annotation_input"
    reference_role: Literal[PtmLocalizationRawReferenceRole.PTM_ANNOTATIONS] = (
        PtmLocalizationRawReferenceRole.PTM_ANNOTATIONS
    )
    reference_digest: Sha256Digest
    vocabulary_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    vocabulary_versions: tuple[SemanticVersion, ...] = Field(min_length=1, max_length=32)
    vocabularies_digest: Sha256Digest

    @field_validator("vocabulary_ids")
    @classmethod
    def vocabulary_identifiers_are_upstream_owned(
        cls, values: tuple[Identifier, ...]
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("PTM vocabulary identifiers must be unique")
        return tuple(
            sorted(
                opaque_ptm_localization_protocol_identifier("vocabulary", value) for value in values
            )
        )

    @field_validator("vocabulary_versions")
    @classmethod
    def vocabulary_versions_are_canonical(
        cls,
        values: tuple[SemanticVersion, ...],
    ) -> tuple[SemanticVersion, ...]:
        return tuple(sorted(values))

    @model_validator(mode="after")
    def vocabulary_projection_is_cardinality_closed(self) -> PtmAnnotationInputDocument:
        if len(self.vocabulary_ids) != len(self.vocabulary_versions):
            raise ValueError("PTM vocabulary identifiers and versions must have equal cardinality")
        return self


PtmLocalizationRawInputDocument = Annotated[
    MassSpectrometryProteomeInputDocument
    | GenomeInputDocument
    | TranscriptomeInputDocument
    | PtmAnnotationInputDocument,
    Field(discriminator="document_type"),
]


class IngestPtmLocalizationRawInputsRequest(FrozenModel):
    """One exact authorized M05-03 manifest-ingestion request."""

    operation: Literal["ingest_ptm_localization_raw_inputs"] = M0503_OPERATION
    contract_version: Literal["1.0.0"] = M0503_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    lineage_result: PtmLocalizationIdentityLineageResolution
    policy: PtmLocalizationRawInputPolicy
    artifacts: tuple[PtmLocalizationRawInputArtifact, ...] = Field(
        min_length=M0503_ROLE_COUNT,
        max_length=M0503_ROLE_COUNT,
    )
    supersedes_result_digest: Sha256Digest | None = None

    @field_validator("lineage_result", mode="wrap")
    @classmethod
    def lineage_result_is_fully_replayed(
        cls,
        value: object,
        handler: ValidatorFunctionWrapHandler,
    ) -> PtmLocalizationIdentityLineageResolution:
        result_digest: object
        receipt_digest_value: object
        if isinstance(value, PtmLocalizationIdentityLineageResolution):
            result_digest = value.result_digest
            receipt_digest_value = value.receipt.receipt_digest
        elif isinstance(value, dict):
            result_digest = dict.get(value, "result_digest")
            receipt = dict.get(value, "receipt")
            receipt_digest_value = (
                dict.get(receipt, "receipt_digest") if isinstance(receipt, dict) else None
            )
        else:
            return cast("PtmLocalizationIdentityLineageResolution", handler(value))
        if _M0503_ZERO_DIGEST in (result_digest, receipt_digest_value):
            raise ValueError("embedded M05-02 derived digests must be final, not sentinels")
        parsed = (
            value
            if isinstance(value, PtmLocalizationIdentityLineageResolution)
            else PtmLocalizationIdentityLineageResolution.model_validate_json(
                canonical_json_bytes(value), strict=True
            )
        )
        return PtmLocalizationIdentityLineageResolution.model_validate_json(
            canonical_json_bytes(normalized_lineage_result(parsed)), strict=True
        )

    @field_validator("artifacts")
    @classmethod
    def artifacts_are_canonical(
        cls,
        values: tuple[PtmLocalizationRawInputArtifact, ...],
    ) -> tuple[PtmLocalizationRawInputArtifact, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

    @model_validator(mode="after")
    def request_is_closed(self) -> IngestPtmLocalizationRawInputsRequest:
        _owned_identifier("request", self.request_id)
        _owned_identifier("request", self.context.request_id)
        _owned_identifier("actor", self.context.actor_id)
        if self.request_id != self.context.request_id:
            raise ValueError("request identifier must equal the authorized context identifier")
        if self.policy.reviewed_at > self.context.occurred_at:
            raise ValueError("raw-input policy cannot postdate ingestion")
        if self.lineage_result.completed_at > self.context.occurred_at:
            raise ValueError("M05-02 result cannot postdate raw-input ingestion")
        roles = tuple(item.role for item in self.artifacts)
        if len(roles) != len(set(roles)) or set(roles) != set(PtmLocalizationRawInputRole):
            raise ValueError("M05-03 requires every raw-input role exactly once")
        claim_ids = tuple(item.lineage_claim_id for item in self.artifacts)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("raw-input lineage claim identifiers must be unique")
        upstream_graph_by_claim = {
            artifact.claim_id: artifact for artifact in self.lineage_result.graph.artifacts
        }
        upstream_claim_by_id = {
            claim.claim_id: claim for claim in self.lineage_result.request.artifact_claims
        }
        projection = {
            PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
                PtmLocalizationLineageArtifactRole.MASS_SPECTROMETRY_PROTEOME_MANIFEST
            ),
            PtmLocalizationRawInputRole.GENOME: PtmLocalizationLineageArtifactRole.GENOME_MANIFEST,
            PtmLocalizationRawInputRole.TRANSCRIPTOME: (
                PtmLocalizationLineageArtifactRole.TRANSCRIPTOME_MANIFEST
            ),
            PtmLocalizationRawInputRole.PTM_ANNOTATIONS: (
                PtmLocalizationLineageArtifactRole.PTM_ANNOTATION_MANIFEST
            ),
        }
        projected_roles = set(projection.values())
        upstream_source_claims = tuple(
            claim
            for claim in self.lineage_result.request.artifact_claims
            if claim.role in projected_roles
        )
        if (
            len(upstream_source_claims) != M0503_ROLE_COUNT
            or {claim.role for claim in upstream_source_claims} != projected_roles
        ):
            raise ValueError("M05-03 requires exactly one upstream claim per projected role")
        for artifact in self.artifacts:
            upstream_graph = upstream_graph_by_claim.get(artifact.lineage_claim_id)
            upstream_claim = upstream_claim_by_id.get(artifact.lineage_claim_id)
            if (
                upstream_graph is None
                or upstream_claim is None
                or upstream_graph.role is not projection[artifact.role]
                or upstream_claim.role is not projection[artifact.role]
                or artifact.manifest_reference != upstream_claim.artifact
            ):
                raise ValueError("raw-input artifacts must project the exact four M05-02 claims")
        refs = self.context.references
        generic_controls = (
            refs.approved_configuration,
            refs.provenance,
            refs.quality,
            refs.support,
            refs.intended_use,
        )
        if (
            refs.consent.state is not ConsentState.GRANTED
            or refs.identity_lineage.state.value != "resolved"
            or any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic_controls)
        ):
            raise ValueError("ptm_localization raw-input ingestion is not authorized")
        if (
            refs.identity_lineage.binding_digest != self.lineage_result.identity_resolution_digest
            or refs.quality.evidence.digest != self.lineage_result.result_digest
            or refs.support.evidence.digest != self.lineage_result.receipt.receipt_digest
            or refs.intended_use.evidence.digest
            != self.lineage_result.receipt.intended_use_evidence_digest
            or refs.approved_configuration.evidence.digest != configuration_digest(self.policy)
        ):
            raise ValueError("M05-03 context does not bind the exact upstream result and policy")
        controls = (
            refs.approved_configuration,
            refs.identity_lineage,
            refs.provenance,
            refs.consent,
            refs.quality,
            refs.support,
            refs.intended_use,
        )
        for control in controls:
            _owned_identifier("decision", control.decision_id)
            _owned_artifact(control.evidence, media_type=_CONTROL_MEDIA_TYPE)
        if len(canonical_json_bytes(normalized_request(self))) > M0503_MAX_CANONICAL_REQUEST_BYTES:
            raise ValueError("canonical M05-03 request exceeds the 4 MiB ingress bound")
        return self


_DIAGNOSTIC_ACTION: Final[
    dict[PtmLocalizationRawDiagnosticCode, PtmLocalizationRawDiagnosticAction]
] = {
    PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED: (
        PtmLocalizationRawDiagnosticAction.QUARANTINE
    ),
    PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED: (
        PtmLocalizationRawDiagnosticAction.ABSTAIN
    ),
    PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE: (
        PtmLocalizationRawDiagnosticAction.ABSTAIN
    ),
    PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED: (
        PtmLocalizationRawDiagnosticAction.RECORD
    ),
    **{
        code: PtmLocalizationRawDiagnosticAction.QUARANTINE
        for code in PtmLocalizationRawDiagnosticCode
        if code
        not in {
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
            PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
            PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE,
            PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED,
        }
    },
}


def _disposition_for_codes(
    codes: tuple[PtmLocalizationRawDiagnosticCode, ...],
) -> PtmLocalizationRawInputDisposition:
    actions = {_DIAGNOSTIC_ACTION[code] for code in codes}
    if PtmLocalizationRawDiagnosticAction.QUARANTINE in actions:
        return PtmLocalizationRawInputDisposition.QUARANTINED
    if PtmLocalizationRawDiagnosticAction.ABSTAIN in actions:
        return PtmLocalizationRawInputDisposition.ABSTAINED
    return PtmLocalizationRawInputDisposition.VALIDATED


class PtmLocalizationRawParseDiagnostic(FrozenModel):
    role: PtmLocalizationRawInputRole | None = None
    code: PtmLocalizationRawDiagnosticCode
    action: PtmLocalizationRawDiagnosticAction
    evidence_basis_digest: Sha256Digest

    @model_validator(mode="after")
    def action_matches_code(self) -> PtmLocalizationRawParseDiagnostic:
        if self.action is not _DIAGNOSTIC_ACTION[self.code]:
            raise ValueError("M05-03 diagnostic action contradicts its closed code")
        return self


class ValidatedPtmLocalizationRawInput(FrozenModel):
    role: PtmLocalizationRawInputRole
    lineage_claim_id: Identifier
    manifest_reference: ArtifactReference
    content_reference: ArtifactReference
    document: PtmLocalizationRawInputDocument
    document_digest: Sha256Digest
    format: PtmLocalizationRawDocumentFormat
    format_version: SemanticVersion
    parser_version: SemanticVersion
    diagnostic_codes: tuple[PtmLocalizationRawDiagnosticCode, ...] = Field(
        default=(), max_length=M0503_DIAGNOSTIC_CODE_COUNT
    )

    @field_validator("diagnostic_codes")
    @classmethod
    def diagnostic_codes_are_unique_and_canonical(
        cls,
        values: tuple[PtmLocalizationRawDiagnosticCode, ...],
    ) -> tuple[PtmLocalizationRawDiagnosticCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("validated-input diagnostic codes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def document_projection_is_exact(self) -> ValidatedPtmLocalizationRawInput:
        opaque_ptm_localization_lineage_identifier("claim", self.lineage_claim_id)
        if self.document_digest != document_digest(self.document):
            raise ValueError("validated-input document digest does not match its content")
        return self


class PtmLocalizationRawInputReceipt(FrozenModel):
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    protocol_receipt_digest: Sha256Digest
    lineage_result_digest: Sha256Digest
    lineage_receipt_digest: Sha256Digest
    lineage_graph_digest: Sha256Digest
    reference_bundle_digest: Sha256Digest
    assay_specimen_policy_digest: Sha256Digest
    intended_use_evidence_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    context_digest: Sha256Digest
    artifact_mapping_digest: Sha256Digest
    validated_inputs_digest: Sha256Digest
    diagnostic_codes: tuple[PtmLocalizationRawDiagnosticCode, ...] = Field(
        default=(), max_length=M0503_DIAGNOSTIC_CODE_COUNT
    )
    parent_target: Literal["variant_peptide"] = M0503_PARENT
    emits_variant_peptide: Literal[False] = False
    disposition: PtmLocalizationRawInputDisposition
    receipt_digest: Sha256Digest

    @field_validator("diagnostic_codes")
    @classmethod
    def codes_are_unique_and_canonical(
        cls,
        values: tuple[PtmLocalizationRawDiagnosticCode, ...],
    ) -> tuple[PtmLocalizationRawDiagnosticCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("receipt diagnostic codes must be unique")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def receipt_is_closed(self) -> PtmLocalizationRawInputReceipt:
        if self.disposition is not _disposition_for_codes(self.diagnostic_codes):
            raise ValueError("receipt disposition contradicts its diagnostic codes")
        if self.receipt_digest != receipt_digest(self):
            raise ValueError("M05-03 receipt digest does not match its canonical content")
        return self


def expected_support(disposition: PtmLocalizationRawInputDisposition) -> SupportDecision:
    if disposition is PtmLocalizationRawInputDisposition.VALIDATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="ptm_localization_raw_inputs_validated",
            rationale="All four canonical raw-input manifests passed the installed validation.",
        )
    if disposition is PtmLocalizationRawInputDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="ptm_localization_raw_inputs_quarantined",
            rationale="A governed raw-manifest discrepancy requires quarantine and review.",
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="ptm_localization_raw_inputs_abstained",
        rationale="The upstream lineage or raw-manifest evidence is not evaluable.",
    )


def expected_uncertainty() -> UncertaintyProfile:
    rationales = (
        "M05-03 validates manifest metadata and estimates no measurement uncertainty.",
        "M05-03 performs no sampling model.",
        "The deterministic ingester fits no parameters.",
        "M05-03 executes no learned parser or biological model.",
        "No protein or PTM-localization identification is performed.",
        "Support is a deterministic manifest-validation decision.",
        "External content and authorities remain caller-declared.",
    )
    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in rationales
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=(
            "Missing, unsupported, indeterminate, or redacted evidence never becomes negative.",
            "External scientific content is never opened or interpreted.",
        ),
    )


def expected_limitations() -> tuple[Limitation, ...]:
    return tuple(
        sorted(
            (
                Limitation(
                    code="deterministic_raw_manifest_validation_only",
                    statement=(
                        "This result validates canonical caller-declared manifest metadata only."
                    ),
                ),
                Limitation(
                    code="external_content_and_authority_not_authenticated",
                    statement=(
                        "Referenced content and caller-declared authorities are not authenticated."
                    ),
                ),
                Limitation(
                    code="no_variant_peptide_or_clinical_inference",
                    statement=(
                        "No protein, PTM localization, variant peptide, treatment, or clinical "
                        "claim is produced."
                    ),
                ),
            ),
            key=canonical_json_bytes,
        )
    )


class PtmLocalizationRawInputValidationResult(FrozenModel):
    output_type: Literal["ptm_localization_raw_input_validation_result"] = (
        "ptm_localization_raw_input_validation_result"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0503_CONTRACT_VERSION
    request_digest: Sha256Digest
    lineage_result_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    context_digest: Sha256Digest
    result_digest: Sha256Digest
    request: IngestPtmLocalizationRawInputsRequest
    receipt: PtmLocalizationRawInputReceipt
    validated_inputs: tuple[ValidatedPtmLocalizationRawInput, ...] = Field(
        default=(), max_length=M0503_ROLE_COUNT
    )
    diagnostics: tuple[PtmLocalizationRawParseDiagnostic, ...] = Field(
        default=(), max_length=M0503_MAX_DIAGNOSTICS
    )
    disposition: PtmLocalizationRawInputDisposition
    parent_target: Literal["variant_peptide"] = M0503_PARENT
    emits_variant_peptide: Literal[False] = False
    emits_proteogenomic_state: Literal[False] = False
    emits_proteotype: Literal[False] = False
    emits_protein_level_subtype: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_consent: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_ptm_localization: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    performs_cn_to_protein_regression: Literal[False] = False
    performs_all_omics_fusion: Literal[False] = False
    recommends_treatment: Literal[False] = False
    mutates_upstream: Literal[False] = False
    executes_model: Literal[False] = False
    persists_events: Literal[False] = False
    support: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(
        min_length=M0503_MIN_EVIDENCE,
        max_length=M0503_MAX_EVIDENCE,
    )
    limitations: tuple[Limitation, ...] = Field(
        min_length=M0503_LIMITATION_COUNT,
        max_length=M0503_LIMITATION_COUNT,
    )
    human_review_required: bool
    completed_at: AwareDatetime

    @field_validator("validated_inputs", "diagnostics", "evidence", "limitations")
    @classmethod
    def semantic_collections_are_canonical(
        cls,
        values: tuple[object, ...],
    ) -> tuple[object, ...]:
        return tuple(sorted(values, key=canonical_json_bytes))

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

    @field_validator("uncertainty")
    @classmethod
    def uncertainty_notes_are_canonical(cls, value: UncertaintyProfile) -> UncertaintyProfile:
        return value.model_copy(
            update={"sensitivity_notes": tuple(sorted(value.sensitivity_notes))}
        )

    @model_validator(mode="after")
    def result_is_exact_replay(self) -> PtmLocalizationRawInputValidationResult:
        return _validate_result_replay(self)


_DOCUMENT_ROLE: Final = {
    "mass_spectrometry_proteome_input": PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME,
    "genome_input": PtmLocalizationRawInputRole.GENOME,
    "transcriptome_input": PtmLocalizationRawInputRole.TRANSCRIPTOME,
    "ptm_annotation_input": PtmLocalizationRawInputRole.PTM_ANNOTATIONS,
}


def _diagnostic(
    code: PtmLocalizationRawDiagnosticCode,
    *,
    role: PtmLocalizationRawInputRole | None,
    basis: object,
) -> PtmLocalizationRawParseDiagnostic:
    return PtmLocalizationRawParseDiagnostic(
        role=role,
        code=code,
        action=_DIAGNOSTIC_ACTION[code],
        evidence_basis_digest=sha256_digest({"code": code, "role": role, "basis": basis}),
    )


def expected_diagnostics(  # noqa: PLR0912,PLR0915 - explicit closed diagnostic matrix.
    request: IngestPtmLocalizationRawInputsRequest,
    documents: tuple[_PtmLocalizationRawDocumentBase, ...],
) -> tuple[PtmLocalizationRawParseDiagnostic, ...]:
    """Derive the exact typed diagnostics from one replayed request and parsed documents."""

    if request.lineage_result.disposition.value == "quarantined":
        return (
            _diagnostic(
                PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_QUARANTINED,
                role=None,
                basis=request.lineage_result.result_digest,
            ),
        )
    if request.lineage_result.disposition.value == "abstained":
        return (
            _diagnostic(
                PtmLocalizationRawDiagnosticCode.UPSTREAM_LINEAGE_ABSTAINED,
                role=None,
                basis=request.lineage_result.result_digest,
            ),
        )

    artifacts = {item.role: item for item in request.artifacts}
    protocol_result = request.lineage_result.request.protocol_result
    protocol = protocol_result.request.protocol_schema
    assay_policy = protocol.assay_specimen_policy
    reference_by_role = {
        item.role: item.reference.digest for item in protocol.reference_bundle.references
    }
    bases_by_finding: dict[
        tuple[PtmLocalizationRawDiagnosticCode, PtmLocalizationRawInputRole | None],
        set[Sha256Digest],
    ] = {}

    def add(
        code: PtmLocalizationRawDiagnosticCode, role: PtmLocalizationRawInputRole, basis: object
    ) -> None:
        item = _diagnostic(code, role=role, basis=basis)
        bases_by_finding.setdefault((item.code, item.role), set()).add(item.evidence_basis_digest)

    for document in documents:
        role = _DOCUMENT_ROLE[document.document_type]
        artifact = artifacts[role]
        if (
            document.lineage_claim_id != artifact.lineage_claim_id
            or document.content_reference != artifact.content_reference
            or document.input_id != artifact.content_reference.artifact_id
        ):
            add(
                PtmLocalizationRawDiagnosticCode.MANIFEST_CLAIM_MISMATCH,
                role,
                (document.lineage_claim_id, document.content_reference, artifact),
            )
        if document.identity_resolution_digest != request.lineage_result.identity_resolution_digest:
            add(
                PtmLocalizationRawDiagnosticCode.IDENTITY_BINDING_MISMATCH,
                role,
                document.identity_resolution_digest,
            )
        if document.protocol_result_digest != request.lineage_result.protocol_result_digest:
            add(
                PtmLocalizationRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
                role,
                document.protocol_result_digest,
            )
        if (
            document.reference_bundle_digest
            != request.lineage_result.receipt.reference_bundle_digest
        ):
            add(
                PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
                role,
                document.reference_bundle_digest,
            )
        if (
            document.assay_specimen_policy_digest
            != request.lineage_result.receipt.assay_specimen_policy_digest
        ):
            add(
                PtmLocalizationRawDiagnosticCode.ASSAY_SPECIMEN_POLICY_MISMATCH,
                role,
                document.assay_specimen_policy_digest,
            )
        if (
            document.intended_use_evidence_digest
            != request.lineage_result.receipt.intended_use_evidence_digest
        ):
            add(
                PtmLocalizationRawDiagnosticCode.PROTOCOL_BINDING_MISMATCH,
                role,
                document.intended_use_evidence_digest,
            )
        approved = tuple(
            item
            for item in request.policy.approved_parsers
            if item.role is role
            and item.format is artifact.format
            and item.format_version == artifact.format_version
            and item.parser_version == artifact.parser_version
        )
        if not approved:
            add(
                PtmLocalizationRawDiagnosticCode.UNSUPPORTED_FORMAT_VERSION,
                role,
                (artifact.format_version, artifact.parser_version),
            )
        elif artifact.content_reference.media_type != approved[0].media_type:
            add(
                PtmLocalizationRawDiagnosticCode.UNSUPPORTED_MEDIA_TYPE,
                role,
                artifact.content_reference.media_type,
            )
        if document.assay_protocol_version != assay_policy.assay_protocol_version:
            add(
                PtmLocalizationRawDiagnosticCode.ASSAY_PROTOCOL_MISMATCH,
                role,
                document.assay_protocol_version,
            )
        if document.specimen_processing_version != assay_policy.specimen_processing_version:
            add(
                PtmLocalizationRawDiagnosticCode.SPECIMEN_PROCESSING_MISMATCH,
                role,
                document.specimen_processing_version,
            )
        if document.unit_system_version != protocol.unit_system_version:
            add(
                PtmLocalizationRawDiagnosticCode.UNIT_MISMATCH,
                role,
                document.unit_system_version,
            )
        if document.reference_bundle_version != protocol.reference_bundle.version:
            add(
                PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
                role,
                document.reference_bundle_version,
            )
        expected_reference_role = {
            PtmLocalizationRawInputRole.MASS_SPECTROMETRY_PROTEOME: (
                PtmLocalizationInputRole.MASS_SPECTROMETRY_PROTEOME
            ),
            PtmLocalizationRawInputRole.GENOME: PtmLocalizationInputRole.GENOME_TRANSCRIPTOME,
            PtmLocalizationRawInputRole.TRANSCRIPTOME: (
                PtmLocalizationInputRole.GENOME_TRANSCRIPTOME
            ),
            PtmLocalizationRawInputRole.PTM_ANNOTATIONS: PtmLocalizationInputRole.PTM_ANNOTATIONS,
        }[role]
        if not isinstance(
            document,
            (
                MassSpectrometryProteomeInputDocument,
                GenomeInputDocument,
                TranscriptomeInputDocument,
                PtmAnnotationInputDocument,
            ),
        ):
            raise TypeError("M05-03 parsed an unknown raw-document type")
        if document.reference_digest != reference_by_role[expected_reference_role]:
            add(
                PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
                role,
                document.reference_digest,
            )
        if isinstance(document, MassSpectrometryProteomeInputDocument):
            if (
                document.assay_kind is not assay_policy.assay_kind
                or document.support_domain is not assay_policy.support_domain
            ):
                add(
                    PtmLocalizationRawDiagnosticCode.ASSAY_SPECIMEN_POLICY_MISMATCH,
                    role,
                    document,
                )
            if set(document.declared_units) != {item.unit for item in protocol.unit_policies}:
                add(PtmLocalizationRawDiagnosticCode.UNIT_MISMATCH, role, document.declared_units)
        if isinstance(document, (GenomeInputDocument, TranscriptomeInputDocument)):
            build = (
                document.reference_build
                if isinstance(document, GenomeInputDocument)
                else document.annotation_build
            )
            if build != protocol.reference_bundle.bundle_id:
                add(
                    PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
                    role,
                    build,
                )
        if isinstance(document, PtmAnnotationInputDocument):
            vocabularies = tuple(protocol.controlled_vocabularies)
            if (
                document.vocabulary_ids
                != tuple(sorted(item.vocabulary_id for item in vocabularies))
                or document.vocabulary_versions
                != tuple(sorted(item.version for item in vocabularies))
                or document.vocabularies_digest != sha256_digest(vocabularies)
            ):
                add(
                    PtmLocalizationRawDiagnosticCode.REFERENCE_BUNDLE_MISMATCH,
                    role,
                    document.vocabularies_digest,
                )
        if document.completeness_state is PtmLocalizationRawCompletenessState.INCOMPLETE:
            add(
                PtmLocalizationRawDiagnosticCode.INCOMPLETE_MANIFEST,
                role,
                document.completeness_state,
            )
        if document.assay_support_state is PtmLocalizationRawAssaySupportState.UNSUPPORTED:
            add(
                PtmLocalizationRawDiagnosticCode.ASSAY_UNSUPPORTED,
                role,
                document.assay_support_state,
            )
        if document.parent_quality_state is PtmLocalizationRawParentQualityState.REJECTED:
            add(
                PtmLocalizationRawDiagnosticCode.PARENT_QUALITY_UNACCEPTABLE,
                role,
                document.parent_quality_state,
            )
        if (
            document.evidence_state is not PtmLocalizationRawEvidenceState.AVAILABLE
            or document.completeness_state is PtmLocalizationRawCompletenessState.NOT_EVALUABLE
            or document.assay_support_state is PtmLocalizationRawAssaySupportState.NOT_EVALUABLE
            or document.parent_quality_state is PtmLocalizationRawParentQualityState.NOT_EVALUABLE
        ):
            add(PtmLocalizationRawDiagnosticCode.ARTIFACT_NOT_EVALUABLE, role, document)

    digest_roles: dict[Sha256Digest, list[PtmLocalizationRawInputRole]] = {}
    for artifact in request.artifacts:
        digest_roles.setdefault(artifact.content_reference.digest, []).append(artifact.role)
    for digest, roles in digest_roles.items():
        if len(roles) > 1:
            for role in roles:
                add(PtmLocalizationRawDiagnosticCode.DUPLICATE_CONTENT_RETAINED, role, digest)
    return tuple(
        sorted(
            (
                PtmLocalizationRawParseDiagnostic(
                    code=code,
                    role=role,
                    action=_DIAGNOSTIC_ACTION[code],
                    evidence_basis_digest=sha256_digest(
                        {
                            "code": code,
                            "role": role,
                            "bases": tuple(sorted(bases)),
                        }
                    ),
                )
                for (code, role), bases in bases_by_finding.items()
            ),
            key=canonical_json_bytes,
        )
    )


def expected_validated_inputs(
    request: IngestPtmLocalizationRawInputsRequest,
    documents: tuple[_PtmLocalizationRawDocumentBase, ...],
    diagnostics: tuple[PtmLocalizationRawParseDiagnostic, ...],
) -> tuple[ValidatedPtmLocalizationRawInput, ...]:
    """Project parsed documents without mutating or deleting quarantined metadata."""

    if not documents:
        return ()
    artifacts = {item.role: item for item in request.artifacts}
    codes_by_role = {
        role: tuple(sorted({item.code for item in diagnostics if item.role is role}))
        for role in PtmLocalizationRawInputRole
    }
    values: list[ValidatedPtmLocalizationRawInput] = []
    for document in documents:
        role = _DOCUMENT_ROLE[document.document_type]
        artifact = artifacts[role]
        values.append(
            ValidatedPtmLocalizationRawInput(
                role=role,
                lineage_claim_id=artifact.lineage_claim_id,
                manifest_reference=artifact.manifest_reference,
                content_reference=artifact.content_reference,
                document=cast("PtmLocalizationRawInputDocument", document),
                document_digest=document_digest(document),
                format=artifact.format,
                format_version=artifact.format_version,
                parser_version=artifact.parser_version,
                diagnostic_codes=codes_by_role[role],
            )
        )
    return tuple(sorted(values, key=canonical_json_bytes))


def raw_input_evidence_index(
    request: IngestPtmLocalizationRawInputsRequest,
) -> tuple[EvidenceReference, ...]:
    refs = request.context.references
    artifacts: tuple[ArtifactReference, ...] = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        *(item.evidence for item in request.policy.approved_parsers),
        *(item.manifest_reference for item in request.artifacts),
        *(item.content_reference for item in request.artifacts),
    )
    if not M0503_MIN_EVIDENCE <= len(artifacts) <= M0503_MAX_EVIDENCE:
        raise ValueError("M05-03 evidence index exceeds its exact installed shape")
    by_identity: dict[tuple[Identifier, SemanticVersion], tuple[Sha256Digest, str]] = {}
    for artifact in artifacts:
        identity = (artifact.artifact_id, artifact.version)
        content = (artifact.digest, artifact.media_type)
        previous = by_identity.setdefault(identity, content)
        if previous != content:
            raise ValueError("one M05-03 evidence identity cannot declare conflicting content")
    return tuple(
        sorted(
            (
                EvidenceReference(
                    reference=item,
                    role="evidence",
                    claim=M0503_EVIDENCE_CLAIM,
                )
                for item in artifacts
            ),
            key=canonical_json_bytes,
        )
    )


def expected_control_decisions(
    context: ExecutionContext,
) -> tuple[ControlDecisionRecord, ...]:
    refs = context.references
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


def expected_receipt(
    request: IngestPtmLocalizationRawInputsRequest,
    validated_inputs: tuple[ValidatedPtmLocalizationRawInput, ...],
    diagnostics: tuple[PtmLocalizationRawParseDiagnostic, ...],
    disposition: PtmLocalizationRawInputDisposition,
) -> PtmLocalizationRawInputReceipt:
    codes = tuple(sorted({item.code for item in diagnostics}))
    if disposition is not _disposition_for_codes(codes):
        raise ValueError("receipt disposition contradicts supplied diagnostics")
    lineage = request.lineage_result
    payload: dict[str, object] = {
        "identity_resolution_digest": lineage.identity_resolution_digest,
        "protocol_result_digest": lineage.protocol_result_digest,
        "protocol_receipt_digest": lineage.receipt.protocol_receipt_digest,
        "lineage_result_digest": lineage.result_digest,
        "lineage_receipt_digest": lineage.receipt.receipt_digest,
        "lineage_graph_digest": lineage.graph_digest,
        "reference_bundle_digest": lineage.receipt.reference_bundle_digest,
        "assay_specimen_policy_digest": lineage.receipt.assay_specimen_policy_digest,
        "intended_use_evidence_digest": lineage.receipt.intended_use_evidence_digest,
        "policy_digest": policy_digest(request.policy),
        "configuration_digest": configuration_digest(request.policy),
        "context_digest": context_digest(request),
        "artifact_mapping_digest": artifact_mapping_digest(request.artifacts),
        "validated_inputs_digest": validated_inputs_digest(validated_inputs),
        "diagnostic_codes": codes,
        "parent_target": M0503_PARENT,
        "emits_variant_peptide": False,
        "disposition": disposition,
        "receipt_digest": _M0503_ZERO_DIGEST,
    }
    payload["receipt_digest"] = receipt_digest(payload)
    return PtmLocalizationRawInputReceipt.model_validate(payload, strict=True)


def expected_provenance(
    request: IngestPtmLocalizationRawInputsRequest,
    request_hash: Sha256Digest,
    validated_inputs: tuple[ValidatedPtmLocalizationRawInput, ...] = (),
) -> ProvenanceRecord:
    mapping_hash = artifact_mapping_digest(request.artifacts)
    inputs_hash = validated_inputs_digest(validated_inputs)
    controls = expected_control_decisions(request.context)
    evidence = raw_input_evidence_index(request)
    active_policy_hash = policy_digest(request.policy)
    config_hash = configuration_digest(request.policy)
    input_digests = tuple(
        sorted(
            {
                request_hash,
                request.lineage_result.result_digest,
                request.lineage_result.receipt.receipt_digest,
                request.lineage_result.graph_digest,
                active_policy_hash,
                config_hash,
                mapping_hash,
                inputs_hash,
                *(
                    (request.supersedes_result_digest,)
                    if request.supersedes_result_digest is not None
                    else ()
                ),
                *(item.reference.digest for item in evidence),
                *(item.evidence_digest for item in controls),
            }
        )
    )
    refs = request.context.references
    return ProvenanceRecord(
        activity_id=f"activity.m0503.{request_hash.removeprefix('sha256:')}",
        actor_id=request.context.actor_id,
        module_id=M0503_MODULE_ID,
        module_version=M0503_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=config_hash,
        consent_decision_id=refs.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


def _normalized_provenance(value: ProvenanceRecord) -> dict[str, object]:
    payload = value.model_dump(mode="python", exclude_none=False)
    payload["input_digests"] = tuple(sorted(value.input_digests))
    payload["control_decisions"] = tuple(
        sorted(payload["control_decisions"], key=canonical_json_bytes)
    )
    return payload


def _normalized_uncertainty(value: UncertaintyProfile) -> dict[str, object]:
    payload = value.model_dump(mode="python", exclude_none=False)
    payload["sensitivity_notes"] = tuple(sorted(value.sensitivity_notes))
    return payload


def _validate_result_replay(
    self: PtmLocalizationRawInputValidationResult,
) -> PtmLocalizationRawInputValidationResult:
    request_hash = canonical_request_digest(self.request)
    active_policy_hash = policy_digest(self.request.policy)
    config_hash = configuration_digest(self.request.policy)
    if self.request.lineage_result.disposition.value != "reconciled":
        replay_diagnostics = expected_diagnostics(self.request, ())
        replay_inputs: tuple[ValidatedPtmLocalizationRawInput, ...] = ()
    else:
        if len(self.validated_inputs) != M0503_ROLE_COUNT or {
            item.role for item in self.validated_inputs
        } != set(PtmLocalizationRawInputRole):
            raise ValueError("a reconciled M05-03 result requires every validated-input role")
        replay_documents = tuple(item.document for item in self.validated_inputs)
        replay_diagnostics = expected_diagnostics(self.request, replay_documents)
        replay_inputs = expected_validated_inputs(
            self.request,
            replay_documents,
            replay_diagnostics,
        )
    expected_codes = tuple(sorted({item.code for item in replay_diagnostics}))
    expected_disposition = _disposition_for_codes(expected_codes)
    replay_receipt = expected_receipt(
        self.request,
        replay_inputs,
        replay_diagnostics,
        expected_disposition,
    )
    suffix = request_hash.removeprefix("sha256:")
    if (
        self.result_id != f"result.m0503.{suffix}"
        or self.request_digest != request_hash
        or self.lineage_result_digest != self.request.lineage_result.result_digest
        or self.policy_digest != active_policy_hash
        or self.configuration_digest != config_hash
        or self.context_digest != context_digest(self.request)
        or self.receipt != replay_receipt
        or tuple(sorted(self.validated_inputs, key=canonical_json_bytes))
        != tuple(sorted(replay_inputs, key=canonical_json_bytes))
        or tuple(sorted(self.diagnostics, key=canonical_json_bytes))
        != tuple(sorted(replay_diagnostics, key=canonical_json_bytes))
        or self.disposition is not expected_disposition
        or self.support != expected_support(expected_disposition)
        or _normalized_uncertainty(self.uncertainty)
        != _normalized_uncertainty(expected_uncertainty())
        or _normalized_provenance(self.provenance)
        != _normalized_provenance(expected_provenance(self.request, request_hash, replay_inputs))
        or tuple(sorted(self.evidence, key=canonical_json_bytes))
        != tuple(sorted(raw_input_evidence_index(self.request), key=canonical_json_bytes))
        or tuple(sorted(self.limitations, key=canonical_json_bytes))
        != tuple(sorted(expected_limitations(), key=canonical_json_bytes))
        or self.human_review_required
        != (expected_disposition is not PtmLocalizationRawInputDisposition.VALIDATED)
        or self.completed_at != self.request.context.occurred_at
    ):
        raise ValueError("M05-03 result contradicts its embedded ingestion request")
    if self.result_digest != result_payload_digest(self):
        raise ValueError("M05-03 result digest does not match its canonical content")
    return self


__all__ = [
    "M0503_CONTRACT_VERSION",
    "M0503_DIAGNOSTIC_CODE_COUNT",
    "M0503_LIMITATION_COUNT",
    "M0503_MAX_APPROVED_PARSERS",
    "M0503_MAX_CANONICAL_REQUEST_BYTES",
    "M0503_MAX_DECLARED_RECORD_COUNT",
    "M0503_MAX_DIAGNOSTICS",
    "M0503_MAX_DOCUMENT_BYTES",
    "M0503_MAX_EVIDENCE",
    "M0503_MAX_TOTAL_DOCUMENT_BYTES",
    "M0503_MIN_APPROVED_PARSERS",
    "M0503_MIN_EVIDENCE",
    "M0503_MODULE_ID",
    "M0503_OPERATION",
    "M0503_PARENT",
    "M0503_ROLE_COUNT",
    "ApprovedPtmLocalizationRawParser",
    "GenomeInputDocument",
    "IngestPtmLocalizationRawInputsRequest",
    "MassSpectrometryProteomeInputDocument",
    "PtmAnnotationInputDocument",
    "PtmLocalizationRawAssaySupportState",
    "PtmLocalizationRawCompletenessState",
    "PtmLocalizationRawDiagnosticAction",
    "PtmLocalizationRawDiagnosticCode",
    "PtmLocalizationRawDocumentFormat",
    "PtmLocalizationRawEvidenceState",
    "PtmLocalizationRawInputArtifact",
    "PtmLocalizationRawInputDisposition",
    "PtmLocalizationRawInputOpaqueNamespace",
    "PtmLocalizationRawInputPolicy",
    "PtmLocalizationRawInputReceipt",
    "PtmLocalizationRawInputRole",
    "PtmLocalizationRawInputValidationResult",
    "PtmLocalizationRawParentQualityState",
    "PtmLocalizationRawParseDiagnostic",
    "PtmLocalizationRawReferenceRole",
    "TranscriptomeInputDocument",
    "ValidatedPtmLocalizationRawInput",
    "expected_control_decisions",
    "expected_diagnostics",
    "expected_limitations",
    "expected_provenance",
    "expected_receipt",
    "expected_support",
    "expected_uncertainty",
    "expected_validated_inputs",
    "opaque_ptm_localization_raw_input_identifier",
    "raw_input_evidence_index",
]
