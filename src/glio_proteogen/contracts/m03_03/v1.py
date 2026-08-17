"""Strict public contracts for M03-03 protein-inference raw-source admission."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from glio_proteogen.contracts.m03_01 import (
    DeclaredUnresolvedState,
    ProtocolConformanceDisposition,
    SearchSpaceReceipt,
)
from glio_proteogen.contracts.m03_02 import (
    ArtifactClaimRole,
    ProteinInferenceIdentityLineageResolution,
    ReconciliationDisposition,
    ReconciliationFindingCode,
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
    NonInferenceResultModel,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyEstimate,
    UncertaintyProfile,
    UpstreamDecisionState,
)

M0303_MODULE_ID: Final = "GLIO-PROTEOGEN-M03-03"
M0303_OPERATION: Final = "ingest_protein_inference_raw_inputs"
M0303_CONTRACT_VERSION: Final = "1.0.0"
M0303_PARENT: Final = "complex_activity"
M0303_MAX_SOURCES: Final = 64
M0303_MAX_LINEAGE_ARTIFACTS: Final = 48
M0303_MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
M0303_MAX_DECODED_BYTES: Final = 32 * 1024 * 1024
M0303_MAX_TOTAL_SOURCE_BYTES: Final = 64 * 1024 * 1024
M0303_MAX_TOTAL_DECODED_BYTES: Final = 128 * 1024 * 1024
M0303_MAX_DIAGNOSTICS: Final = 512
# Seven control references, one policy reference, seven protocol/search references,
# and the larger of the 256-artifact safe-failure shape or 48 artifacts + 64 sources.
M0303_MAX_EVIDENCE: Final = 7 + 1 + 7 + max(256, 48 + 64)
# Compact digest-bound upstream receipts keep the public metadata request within the
# dossier-wide strict JSON ingress boundary; raw payloads remain out-of-band.
M0303_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M0303_ZERO_DIGEST: Final = "sha256:" + ("0" * 64)
M0303_EVIDENCE_CLAIM: Final = "Caller-declared content-addressed M03-03 raw-admission evidence."
M0303_SENSITIVITY_NOTES: Final = (
    "Raw admission validates bounded transport and declared structural coherence only.",
    "No probability is estimated from caller-declared metadata or parser diagnostics.",
)
M0303_UNCERTAINTY_RATIONALES: Final = (
    "Measurement uncertainty is not estimable from metadata-only raw admission.",
    "Sampling uncertainty is not estimable from parser inputs.",
    "Parameter uncertainty is not estimated by this deterministic parser.",
    "Model-form uncertainty is not applicable to format admission.",
    "Identification uncertainty remains owned by downstream protein inference.",
    "Support is a deterministic domain decision, not a calibrated probability.",
    "Transportability requires external assay and reference validation.",
)


class ProteinInferenceRawRole(StrEnum):
    SPECTRA = "spectra"
    PEPTIDE_EVIDENCE = "peptide_evidence"
    PROTEIN_GROUP_MANIFEST = "protein_group_manifest"
    AMBIGUITY_MANIFEST = "ambiguity_manifest"
    COMPLEX_ACTIVITY_INPUT_BUNDLE = "complex_activity_input_bundle"
    CANONICAL_SEQUENCES = "canonical_sequences"
    DECOY_SEQUENCES = "decoy_sequences"
    ISOFORM_SEQUENCES = "isoform_sequences"
    VARIANT_SEQUENCES = "variant_sequences"
    CONTAMINANT_SEQUENCES = "contaminant_sequences"
    PTM_VOCABULARY = "ptm_vocabulary"
    GENOMIC_CONTEXT = "genomic_context"
    TRANSCRIPT_CONTEXT = "transcript_context"


class ProteinInferenceRawFormat(StrEnum):
    MZML = "mzML"
    MZIDENTML = "mzIdentML"
    PROTEIN_GROUP_JSON = "protein_group_json"
    AMBIGUITY_JSON = "ambiguity_json"
    COMPLEX_BUNDLE_JSON = "complex_bundle_json"
    FASTA = "FASTA"
    PSI_MOD_OBO = "PSI_MOD_OBO"
    VCF = "VCF"
    GFF3 = "GFF3"


class ProteinInferenceCompression(StrEnum):
    NONE = "none"
    GZIP = "gzip"


class ProteinInferenceAdmissionDisposition(StrEnum):
    VALIDATED = "validated"
    QUARANTINED = "quarantined"
    ABSTAINED = "abstained"
    REJECTED = "rejected"


class ProteinInferenceBuildState(StrEnum):
    EXACT = "exact"
    MISMATCHED = "mismatched"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    NOT_APPLICABLE = "not_applicable"


class ProteinInferenceDiagnosticAction(StrEnum):
    RECORD = "record"
    QUARANTINE = "quarantine"
    ABSTAIN = "abstain"
    REJECT = "reject"


class ProteinInferenceDiagnosticCode(StrEnum):
    CHECKSUM_MISMATCH = "checksum_mismatch"
    DECLARED_SIZE_MISMATCH = "declared_size_mismatch"
    RAW_SIZE_LIMIT_EXCEEDED = "raw_size_limit_exceeded"
    DECODED_SIZE_LIMIT_EXCEEDED = "decoded_size_limit_exceeded"
    INVALID_GZIP = "invalid_gzip"
    UNSUPPORTED_FORMAT = "unsupported_format"
    UNSUPPORTED_VERSION = "unsupported_version"
    MALFORMED_CONTENT = "malformed_content"
    FORBIDDEN_XML_CONSTRUCT = "forbidden_xml_construct"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    DANGLING_REFERENCE = "dangling_reference"
    ROLE_FORMAT_MISMATCH = "role_format_mismatch"
    BUILD_MISMATCH = "build_mismatch"
    BUILD_MISSING = "build_missing"
    BUILD_UNSUPPORTED = "build_unsupported"
    CONTROLLED_VOCABULARY_MISMATCH = "controlled_vocabulary_mismatch"
    UNIT_PROFILE_MISMATCH = "unit_profile_mismatch"
    ASSEMBLY_MISMATCH = "assembly_mismatch"
    CROSS_SOURCE_DISAGREEMENT = "cross_source_disagreement"
    UPSTREAM_QUARANTINED = "upstream_quarantined"
    UPSTREAM_ABSTAINED = "upstream_abstained"
    UPSTREAM_SHAPE_UNSUPPORTED = "upstream_shape_unsupported"


_ACTION_BY_CODE: Final = {
    ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH: ProteinInferenceDiagnosticAction.REJECT,
    ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH: (
        ProteinInferenceDiagnosticAction.REJECT
    ),
    ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED: (
        ProteinInferenceDiagnosticAction.REJECT
    ),
    ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED: (
        ProteinInferenceDiagnosticAction.REJECT
    ),
    ProteinInferenceDiagnosticCode.INVALID_GZIP: ProteinInferenceDiagnosticAction.REJECT,
    ProteinInferenceDiagnosticCode.UNSUPPORTED_FORMAT: ProteinInferenceDiagnosticAction.ABSTAIN,
    ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION: ProteinInferenceDiagnosticAction.ABSTAIN,
    ProteinInferenceDiagnosticCode.MALFORMED_CONTENT: (ProteinInferenceDiagnosticAction.QUARANTINE),
    ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.DANGLING_REFERENCE: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.BUILD_MISMATCH: (ProteinInferenceDiagnosticAction.QUARANTINE),
    ProteinInferenceDiagnosticCode.BUILD_MISSING: ProteinInferenceDiagnosticAction.ABSTAIN,
    ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED: ProteinInferenceDiagnosticAction.ABSTAIN,
    ProteinInferenceDiagnosticCode.CONTROLLED_VOCABULARY_MISMATCH: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.UNIT_PROFILE_MISMATCH: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH: (ProteinInferenceDiagnosticAction.QUARANTINE),
    ProteinInferenceDiagnosticCode.CROSS_SOURCE_DISAGREEMENT: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED: (
        ProteinInferenceDiagnosticAction.QUARANTINE
    ),
    ProteinInferenceDiagnosticCode.UPSTREAM_ABSTAINED: ProteinInferenceDiagnosticAction.ABSTAIN,
    ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED: (
        ProteinInferenceDiagnosticAction.ABSTAIN
    ),
}

_MESSAGE_BY_CODE: Final = dict(  # noqa: C406 - tuple layout keeps long messages readable.
    (
        (
            ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
            "Source checksum does not match its declaration.",
        ),
        (
            ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH,
            "Source size does not match its declaration.",
        ),
        (
            ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED,
            "Transported source exceeds its byte ceiling.",
        ),
        (
            ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED,
            "Decoded source exceeds its byte ceiling.",
        ),
        (
            ProteinInferenceDiagnosticCode.INVALID_GZIP,
            "Gzip transport is invalid or exceeds its bounded profile.",
        ),
        (
            ProteinInferenceDiagnosticCode.UNSUPPORTED_FORMAT,
            "Source format is outside the reviewed M03-03 profile.",
        ),
        (
            ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION,
            "Source version is outside the reviewed M03-03 profile.",
        ),
        (
            ProteinInferenceDiagnosticCode.MALFORMED_CONTENT,
            "Source content is malformed for its declared role.",
        ),
        (
            ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT,
            "XML contains a forbidden external or document-type construct.",
        ),
        (
            ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY,
            "JSON contains a duplicate object member.",
        ),
        (
            ProteinInferenceDiagnosticCode.DANGLING_REFERENCE,
            "A required internal or cross-source reference is unresolved.",
        ),
        (
            ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH,
            "Detected content contradicts its governed source role.",
        ),
        (
            ProteinInferenceDiagnosticCode.BUILD_MISMATCH,
            "Detected build contradicts its exact expected build.",
        ),
        (
            ProteinInferenceDiagnosticCode.BUILD_MISSING,
            "A governed build declaration is unavailable.",
        ),
        (
            ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED,
            "The declared build is outside the reviewed profile.",
        ),
        (
            ProteinInferenceDiagnosticCode.CONTROLLED_VOCABULARY_MISMATCH,
            "Controlled-vocabulary identity or version disagrees.",
        ),
        (
            ProteinInferenceDiagnosticCode.UNIT_PROFILE_MISMATCH,
            "Unit-system version disagrees with the reviewed protocol.",
        ),
        (
            ProteinInferenceDiagnosticCode.ASSEMBLY_MISMATCH,
            "Genome and transcript assembly declarations disagree.",
        ),
        (
            ProteinInferenceDiagnosticCode.CROSS_SOURCE_DISAGREEMENT,
            "Cross-source metadata disagreement remains unresolved.",
        ),
        (
            ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED,
            "The valid upstream lineage result is quarantined.",
        ),
        (
            ProteinInferenceDiagnosticCode.UPSTREAM_ABSTAINED,
            "The valid upstream lineage result abstained.",
        ),
        (
            ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED,
            "The valid upstream lineage shape exceeds this reviewed parser profile.",
        ),
    )
)


class ApprovedBuild(FrozenModel):
    build_id: Identifier
    version: SemanticVersion


class ProteinInferenceRawPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    max_sources: int = Field(gt=0, le=M0303_MAX_SOURCES)
    max_lineage_artifacts: int = Field(gt=0, le=M0303_MAX_LINEAGE_ARTIFACTS)
    max_spectra_sources: int = Field(gt=0, le=32)
    max_source_bytes: int = Field(gt=0, le=M0303_MAX_SOURCE_BYTES)
    max_decoded_bytes: int = Field(gt=0, le=M0303_MAX_DECODED_BYTES)
    max_total_source_bytes: int = Field(gt=0, le=M0303_MAX_TOTAL_SOURCE_BYTES)
    max_total_decoded_bytes: int = Field(gt=0, le=M0303_MAX_TOTAL_DECODED_BYTES)
    approved_genome_builds: tuple[ApprovedBuild, ...] = Field(min_length=1, max_length=32)
    approved_transcript_builds: tuple[ApprovedBuild, ...] = Field(min_length=1, max_length=32)
    evidence: ArtifactReference
    reviewed_by: Identifier
    reviewed_at: AwareDatetime

    @model_validator(mode="after")
    def policy_is_closed(self) -> ProteinInferenceRawPolicy:
        if self.max_decoded_bytes < self.max_source_bytes:
            raise ValueError("decoded byte ceiling cannot be below the source byte ceiling")
        if self.max_total_source_bytes < self.max_source_bytes:
            raise ValueError("total source ceiling cannot be below the per-source ceiling")
        if self.max_total_decoded_bytes < self.max_decoded_bytes:
            raise ValueError("total decoded ceiling cannot be below the per-source ceiling")
        for values, label in (
            (self.approved_genome_builds, "genome"),
            (self.approved_transcript_builds, "transcript"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"approved {label} builds must be unique")
        return self


class ProteinInferenceProtocolIngestionReceipt(FrozenModel):
    protocol_result_digest: Sha256Digest
    protocol_digest: Sha256Digest
    search_space_digest: Sha256Digest
    identity_subject_digest: Sha256Digest
    disposition: ProtocolConformanceDisposition
    completed_at: AwareDatetime
    search_space: SearchSpaceReceipt
    modification_vocabulary_reference: ArtifactReference
    controlled_vocabulary_id: Identifier
    controlled_vocabulary_version: SemanticVersion
    unit_system_version: SemanticVersion
    assay_protocol_version: SemanticVersion
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def receipt_is_content_addressed(self) -> ProteinInferenceProtocolIngestionReceipt:
        from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
            protocol_receipt_digest,
        )

        if self.receipt_digest != protocol_receipt_digest(self):
            raise ValueError("M03-01 ingestion receipt digest does not match its content")
        if self.search_space_digest != sha256_digest(self.search_space):
            raise ValueError("M03-01 search-space receipt digest does not match its content")
        return self


class ProteinInferenceLineageArtifactReceipt(FrozenModel):
    claim_id: Identifier
    claim_role: ArtifactClaimRole
    artifact: ArtifactReference
    identity_entity_id: Identifier
    lineage_path_digest: Sha256Digest
    evidence_state: Literal["observed"] | DeclaredUnresolvedState
    finding_codes: tuple[ReconciliationFindingCode, ...] = Field(default=(), max_length=16)

    @field_validator("finding_codes")
    @classmethod
    def finding_codes_are_unique(
        cls,
        values: tuple[ReconciliationFindingCode, ...],
    ) -> tuple[ReconciliationFindingCode, ...]:
        if len(values) != len(set(values)):
            raise ValueError("lineage artifact finding codes must be unique")
        return values


class ProteinInferenceLineageIngestionReceipt(FrozenModel):
    lineage_result_digest: Sha256Digest
    lineage_request_digest: Sha256Digest
    identity_resolution_digest: Sha256Digest
    protocol_result_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    graph_digest: Sha256Digest
    disposition: ReconciliationDisposition
    completed_at: AwareDatetime
    artifacts: tuple[ProteinInferenceLineageArtifactReceipt, ...] = Field(
        min_length=4, max_length=256
    )
    receipt_digest: Sha256Digest

    @model_validator(mode="after")
    def artifacts_are_exactly_indexable(self) -> ProteinInferenceLineageIngestionReceipt:
        claim_ids = tuple(item.claim_id for item in self.artifacts)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("lineage artifact receipts require unique claim identifiers")
        roles = tuple(item.claim_role for item in self.artifacts)
        if (
            roles.count(ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST) < 1
            or roles.count(ArtifactClaimRole.PROTEIN_GROUP_MANIFEST) != 1
            or roles.count(ArtifactClaimRole.AMBIGUITY_MANIFEST) != 1
            or roles.count(ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE) != 1
        ):
            raise ValueError("lineage receipt must preserve the exact four-role artifact shape")
        from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
            lineage_receipt_digest,
        )

        if self.receipt_digest != lineage_receipt_digest(self):
            raise ValueError("M03-02 ingestion receipt digest does not match its content")
        return self


_FORMAT_BY_ROLE: Final = {
    ProteinInferenceRawRole.SPECTRA: ProteinInferenceRawFormat.MZML,
    ProteinInferenceRawRole.PEPTIDE_EVIDENCE: ProteinInferenceRawFormat.MZIDENTML,
    ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST: ProteinInferenceRawFormat.PROTEIN_GROUP_JSON,
    ProteinInferenceRawRole.AMBIGUITY_MANIFEST: ProteinInferenceRawFormat.AMBIGUITY_JSON,
    ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: (
        ProteinInferenceRawFormat.COMPLEX_BUNDLE_JSON
    ),
    ProteinInferenceRawRole.CANONICAL_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.DECOY_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.ISOFORM_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.VARIANT_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.CONTAMINANT_SEQUENCES: ProteinInferenceRawFormat.FASTA,
    ProteinInferenceRawRole.PTM_VOCABULARY: ProteinInferenceRawFormat.PSI_MOD_OBO,
    ProteinInferenceRawRole.GENOMIC_CONTEXT: ProteinInferenceRawFormat.VCF,
    ProteinInferenceRawRole.TRANSCRIPT_CONTEXT: ProteinInferenceRawFormat.GFF3,
}


class ProteinInferenceRawSource(FrozenModel):
    source_id: Identifier
    role: ProteinInferenceRawRole
    artifact: ArtifactReference
    byte_length: int = Field(ge=0, le=M0303_MAX_SOURCE_BYTES)
    declared_format: ProteinInferenceRawFormat
    declared_compression: ProteinInferenceCompression
    bound_claim_id: Identifier | None = None
    expected_build_id: Identifier | None = None
    expected_build_version: SemanticVersion | None = None

    @model_validator(mode="after")
    def declaration_is_role_closed(self) -> ProteinInferenceRawSource:
        if self.declared_format is not _FORMAT_BY_ROLE[self.role]:
            raise ValueError("raw source format contradicts its protein-inference role")
        if (self.expected_build_id is None) != (self.expected_build_version is None):
            raise ValueError("build identity and version must be declared together")
        return self


def protocol_ingestion_receipt(
    value: object,
) -> ProteinInferenceProtocolIngestionReceipt:
    """Project a strict M03-01 result into the exact M03-03 upstream receipt."""

    from glio_proteogen.contracts.m03_01 import (  # noqa: PLC0415
        ProteinInferenceProtocolConformanceResult,
    )

    result = ProteinInferenceProtocolConformanceResult.model_validate(value, strict=True)
    protocol = result.protocol_schema
    payload = {
        "protocol_result_digest": result.result_digest,
        "protocol_digest": result.protocol_digest,
        "search_space_digest": result.receipt.search_space_digest,
        "identity_subject_digest": result.receipt.identity_subject_digest,
        "disposition": result.disposition,
        "completed_at": result.completed_at,
        "search_space": protocol.search_space,
        "modification_vocabulary_reference": (
            protocol.peptide_eligibility.modification_vocabulary_reference
        ),
        "controlled_vocabulary_id": protocol.controlled_vocabulary_id,
        "controlled_vocabulary_version": protocol.controlled_vocabulary_version,
        "unit_system_version": protocol.unit_system_version,
        "assay_protocol_version": protocol.assay_protocol_version,
    }
    from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
        protocol_receipt_digest,
    )

    return ProteinInferenceProtocolIngestionReceipt(
        protocol_result_digest=result.result_digest,
        protocol_digest=result.protocol_digest,
        search_space_digest=result.receipt.search_space_digest,
        identity_subject_digest=result.receipt.identity_subject_digest,
        disposition=result.disposition,
        completed_at=result.completed_at,
        search_space=protocol.search_space,
        modification_vocabulary_reference=(
            protocol.peptide_eligibility.modification_vocabulary_reference
        ),
        controlled_vocabulary_id=protocol.controlled_vocabulary_id,
        controlled_vocabulary_version=protocol.controlled_vocabulary_version,
        unit_system_version=protocol.unit_system_version,
        assay_protocol_version=protocol.assay_protocol_version,
        receipt_digest=protocol_receipt_digest(payload),
    )


def lineage_ingestion_receipt(
    value: object,
) -> ProteinInferenceLineageIngestionReceipt:
    """Project a strict M03-02 result into the exact M03-03 lineage receipt."""

    result = ProteinInferenceIdentityLineageResolution.model_validate(value, strict=True)
    artifacts = tuple(
        ProteinInferenceLineageArtifactReceipt(
            claim_id=item.claim_id,
            claim_role=item.role,
            artifact=next(
                claim.artifact
                for claim in result.request.artifact_claims
                if claim.claim_id == item.claim_id
            ),
            identity_entity_id=item.identity_entity_id,
            lineage_path_digest=item.lineage_path_digest,
            evidence_state=item.evidence_state,
            finding_codes=item.finding_codes,
        )
        for item in result.graph.artifacts
    )
    payload = {
        "lineage_result_digest": result.result_digest,
        "lineage_request_digest": result.request_digest,
        "identity_resolution_digest": result.identity_resolution_digest,
        "protocol_result_digest": result.protocol_result_digest,
        "policy_digest": result.policy_digest,
        "configuration_digest": result.configuration_digest,
        "graph_digest": result.graph_digest,
        "disposition": result.disposition,
        "completed_at": result.completed_at,
        "artifacts": artifacts,
    }
    from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
        lineage_receipt_digest,
    )

    return ProteinInferenceLineageIngestionReceipt(
        lineage_result_digest=result.result_digest,
        lineage_request_digest=result.request_digest,
        identity_resolution_digest=result.identity_resolution_digest,
        protocol_result_digest=result.protocol_result_digest,
        policy_digest=result.policy_digest,
        configuration_digest=result.configuration_digest,
        graph_digest=result.graph_digest,
        disposition=result.disposition,
        completed_at=result.completed_at,
        artifacts=artifacts,
        receipt_digest=lineage_receipt_digest(payload),
    )


def source_manifest_digest(
    sources: tuple[ProteinInferenceRawSource, ...],
) -> Sha256Digest:
    """Digest all declarations except the bundle that carries this digest."""

    from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
        canonical_source_manifest_digest,
    )

    return canonical_source_manifest_digest(sources)


class IngestProteinInferenceRawInputsRequest(FrozenModel):
    operation: Literal["ingest_protein_inference_raw_inputs"] = M0303_OPERATION
    contract_version: Literal["1.0.0"] = M0303_CONTRACT_VERSION
    context: ExecutionContext
    protocol_receipt: ProteinInferenceProtocolIngestionReceipt
    lineage_receipt: ProteinInferenceLineageIngestionReceipt
    policy: ProteinInferenceRawPolicy
    source_manifest_digest: Sha256Digest
    sources: tuple[ProteinInferenceRawSource, ...] = Field(default=(), max_length=M0303_MAX_SOURCES)
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_authorized_and_closed(self) -> IngestProteinInferenceRawInputsRequest:
        _require_authorized_context(self.context)
        if (
            max(
                self.protocol_receipt.completed_at,
                self.lineage_receipt.completed_at,
                self.policy.reviewed_at,
            )
            > self.context.occurred_at
        ):
            raise ValueError("M03-03 inputs cannot postdate ingestion")
        if (
            self.context.references.identity_lineage.binding_digest
            != self.lineage_receipt.identity_resolution_digest
            or self.protocol_receipt.identity_subject_digest
            != self.lineage_receipt.identity_resolution_digest
            or self.protocol_receipt.protocol_result_digest
            != self.lineage_receipt.protocol_result_digest
        ):
            raise ValueError("M03-03 upstream identity and protocol receipts do not close")
        if (
            self.protocol_receipt.disposition is not ProtocolConformanceDisposition.CONFORMANT
            and self.sources
        ):
            raise ValueError("nonconformant protocol receipts cannot traverse raw sources")
        from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
            configuration_digest,
        )

        if self.context.references.approved_configuration.evidence.digest != configuration_digest(
            self.policy
        ):
            raise ValueError("approved configuration does not bind the M03-03 policy")
        if self.source_manifest_digest != source_manifest_digest(self.sources):
            raise ValueError("declared source manifest digest does not match its sources")
        _validate_source_closure(self)
        if (
            len(canonical_json_bytes(self.model_dump(mode="python")))
            > M0303_MAX_CANONICAL_REQUEST_BYTES
        ):
            raise ValueError("canonical M03-03 request exceeds its ingress ceiling")
        return self


def _validate_source_closure(request: IngestProteinInferenceRawInputsRequest) -> None:
    sources = request.sources
    if len(sources) > request.policy.max_sources:
        raise ValueError("source count exceeds the active M03-03 policy")
    if any(item.byte_length > request.policy.max_source_bytes for item in sources):
        raise ValueError("source bytes exceed the active per-source M03-03 policy")
    source_ids = tuple(item.source_id for item in sources)
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("M03-03 source identifiers must be unique")
    if sum(item.byte_length for item in sources) > request.policy.max_total_source_bytes:
        raise ValueError("declared source bytes exceed the active M03-03 policy")
    lineage = request.lineage_receipt
    safe_failure = (
        lineage.disposition is not ReconciliationDisposition.RECONCILED
        or request.protocol_receipt.disposition is not ProtocolConformanceDisposition.CONFORMANT
    )
    unsupported_shape = len(lineage.artifacts) > request.policy.max_lineage_artifacts
    if safe_failure or unsupported_shape:
        if sources:
            raise ValueError("safe-failure ingestion requests cannot traverse raw sources")
        return
    by_claim = {item.claim_id: item for item in lineage.artifacts}
    bound = tuple(item.bound_claim_id for item in sources if item.bound_claim_id is not None)
    if set(bound) != set(by_claim) or len(bound) != len(set(bound)):
        raise ValueError("every lineage artifact must bind exactly one raw source")
    expected_role = {
        ArtifactClaimRole.PEPTIDE_EVIDENCE_MANIFEST: ProteinInferenceRawRole.PEPTIDE_EVIDENCE,
        ArtifactClaimRole.PROTEIN_GROUP_MANIFEST: ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
        ArtifactClaimRole.AMBIGUITY_MANIFEST: ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
        ArtifactClaimRole.COMPLEX_ACTIVITY_INPUT_BUNDLE: (
            ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE
        ),
    }
    for source in sources:
        if source.bound_claim_id is None:
            continue
        receipt = by_claim[source.bound_claim_id]
        if (
            source.role is not expected_role[receipt.claim_role]
            or source.artifact != receipt.artifact
        ):
            raise ValueError("raw source contradicts its bound M03-02 artifact claim")
    _validate_required_roles(request)


def _validate_required_roles(  # noqa: PLR0912 - explicit closed role matrix.
    request: IngestProteinInferenceRawInputsRequest,
) -> None:
    roles = [item.role for item in request.sources]
    counts = {role: roles.count(role) for role in ProteinInferenceRawRole}
    if not 1 <= counts[ProteinInferenceRawRole.SPECTRA] <= request.policy.max_spectra_sources:
        raise ValueError("M03-03 requires a bounded nonempty spectra source set")
    exact_one = {
        ProteinInferenceRawRole.PROTEIN_GROUP_MANIFEST,
        ProteinInferenceRawRole.AMBIGUITY_MANIFEST,
        ProteinInferenceRawRole.COMPLEX_ACTIVITY_INPUT_BUNDLE,
        ProteinInferenceRawRole.CANONICAL_SEQUENCES,
        ProteinInferenceRawRole.DECOY_SEQUENCES,
        ProteinInferenceRawRole.PTM_VOCABULARY,
    }
    if any(counts[role] != 1 for role in exact_one):
        raise ValueError("M03-03 required source roles must occur exactly once")
    if counts[ProteinInferenceRawRole.PEPTIDE_EVIDENCE] < 1:
        raise ValueError("M03-03 requires at least one peptide-evidence source")
    for role in (
        ProteinInferenceRawRole.GENOMIC_CONTEXT,
        ProteinInferenceRawRole.TRANSCRIPT_CONTEXT,
    ):
        if counts[role] > 1:
            raise ValueError("M03-03 context source roles may occur at most once")
    for source in request.sources:
        if (
            source.role
            in {
                ProteinInferenceRawRole.GENOMIC_CONTEXT,
                ProteinInferenceRawRole.TRANSCRIPT_CONTEXT,
            }
            and source.expected_build_id is None
        ):
            raise ValueError("context sources require an exact expected build")
    search = request.protocol_receipt.search_space
    search_build = (search.build_id, search.release)
    peptide_sources = (
        item for item in request.sources if item.role is ProteinInferenceRawRole.PEPTIDE_EVIDENCE
    )
    if any(
        (item.expected_build_id, item.expected_build_version) != search_build
        for item in peptide_sources
    ):
        raise ValueError("peptide evidence must bind the exact M03-01 search build")
    optional = (
        (ProteinInferenceRawRole.ISOFORM_SEQUENCES, search.isoform_reference),
        (ProteinInferenceRawRole.VARIANT_SEQUENCES, search.variant_reference),
        (ProteinInferenceRawRole.CONTAMINANT_SEQUENCES, search.contaminant_reference),
    )
    if any(counts[role] != int(reference is not None) for role, reference in optional):
        raise ValueError("conditional search-space sources contradict M03-01")
    expected_refs = {
        ProteinInferenceRawRole.CANONICAL_SEQUENCES: search.canonical_sequence_reference,
        ProteinInferenceRawRole.DECOY_SEQUENCES: search.decoy_reference,
        ProteinInferenceRawRole.PTM_VOCABULARY: (
            request.protocol_receipt.modification_vocabulary_reference
        ),
        **{role: reference for role, reference in optional if reference is not None},
    }
    for role, reference in expected_refs.items():
        source = next(item for item in request.sources if item.role is role)
        if source.artifact != reference:
            raise ValueError("search-space or PTM source does not match M03-01")
    ptm_source = next(
        item for item in request.sources if item.role is ProteinInferenceRawRole.PTM_VOCABULARY
    )
    if (ptm_source.expected_build_id, ptm_source.expected_build_version) != (
        request.protocol_receipt.controlled_vocabulary_id,
        request.protocol_receipt.controlled_vocabulary_version,
    ):
        raise ValueError("PTM source must bind the exact M03-01 vocabulary version")
    approved_pairs = {
        ProteinInferenceRawRole.GENOMIC_CONTEXT: {
            (item.build_id, item.version) for item in request.policy.approved_genome_builds
        },
        ProteinInferenceRawRole.TRANSCRIPT_CONTEXT: {
            (item.build_id, item.version) for item in request.policy.approved_transcript_builds
        },
    }
    for source in request.sources:
        approved = approved_pairs.get(source.role)
        if (
            approved is not None
            and (
                source.expected_build_id,
                source.expected_build_version,
            )
            not in approved
        ):
            raise ValueError("context source build is outside the reviewed M03-03 policy")


def _require_authorized_context(context: ExecutionContext) -> None:
    refs = context.references
    if refs.consent.state is not ConsentState.GRANTED:
        raise ValueError("consent does not authorize M03-03 ingestion")
    generic = (
        refs.approved_configuration,
        refs.provenance,
        refs.quality,
        refs.support,
        refs.intended_use,
    )
    if any(item.state is not UpstreamDecisionState.ACCEPTED for item in generic):
        raise ValueError("every generic control must accept M03-03 ingestion")
    if refs.identity_lineage.state is not IdentityLineageState.RESOLVED:
        raise ValueError("identity lineage must be resolved before M03-03 ingestion")


def diagnostic_for(
    code: ProteinInferenceDiagnosticCode,
    source_ids: tuple[Identifier, ...] = (),
) -> ProteinInferenceParseDiagnostic:
    """Construct one deterministic diagnostic from the closed M03-03 vocabulary."""

    ordered_ids = tuple(sorted(source_ids))
    digest = sha256_digest({"code": code, "source_ids": ordered_ids})
    suffix = digest.removeprefix("sha256:")[:16]
    return ProteinInferenceParseDiagnostic(
        diagnostic_id=f"diagnostic.m0303.{code.value}.{suffix}",
        code=code,
        action=_ACTION_BY_CODE[code],
        source_ids=ordered_ids,
        message=_MESSAGE_BY_CODE[code],
    )


def expected_upstream_diagnostics(
    request: IngestProteinInferenceRawInputsRequest,
) -> tuple[ProteinInferenceParseDiagnostic, ...]:
    """Derive a safe-failure diagnostic before any source traversal."""

    if (
        request.protocol_receipt.disposition is ProtocolConformanceDisposition.QUARANTINED
        or request.lineage_receipt.disposition is ReconciliationDisposition.QUARANTINED
    ):
        return (diagnostic_for(ProteinInferenceDiagnosticCode.UPSTREAM_QUARANTINED),)
    if request.lineage_receipt.disposition is ReconciliationDisposition.ABSTAINED:
        return (diagnostic_for(ProteinInferenceDiagnosticCode.UPSTREAM_ABSTAINED),)
    if len(request.lineage_receipt.artifacts) > request.policy.max_lineage_artifacts:
        return (diagnostic_for(ProteinInferenceDiagnosticCode.UPSTREAM_SHAPE_UNSUPPORTED),)
    roles = {item.role for item in request.sources}
    search = request.protocol_receipt.search_space
    missing_genome_context = (
        search.variant_reference is not None
        and ProteinInferenceRawRole.GENOMIC_CONTEXT not in roles
    )
    missing_transcript_context = (
        search.isoform_reference is not None
        and ProteinInferenceRawRole.TRANSCRIPT_CONTEXT not in roles
    )
    if missing_genome_context or missing_transcript_context:
        return (diagnostic_for(ProteinInferenceDiagnosticCode.BUILD_MISSING),)
    return ()


def expected_disposition(
    diagnostics: tuple[ProteinInferenceParseDiagnostic, ...],
) -> ProteinInferenceAdmissionDisposition:
    """Apply the closed reject > quarantine > abstain > validate precedence."""

    actions = {item.action for item in diagnostics}
    if ProteinInferenceDiagnosticAction.REJECT in actions:
        return ProteinInferenceAdmissionDisposition.REJECTED
    if ProteinInferenceDiagnosticAction.QUARANTINE in actions:
        return ProteinInferenceAdmissionDisposition.QUARANTINED
    if ProteinInferenceDiagnosticAction.ABSTAIN in actions:
        return ProteinInferenceAdmissionDisposition.ABSTAINED
    return ProteinInferenceAdmissionDisposition.VALIDATED


def expected_support(
    disposition: ProteinInferenceAdmissionDisposition,
) -> SupportDecision:
    """Return the exact support envelope for one admission disposition."""

    if disposition is ProteinInferenceAdmissionDisposition.VALIDATED:
        return SupportDecision(
            status=SupportStatus.SUPPORTED,
            reason_code="protein_inference_raw_inputs_validated",
            rationale=(
                "The declared protein-inference sources passed bounded transport, format, "
                "and cross-source admission checks."
            ),
        )
    if disposition is ProteinInferenceAdmissionDisposition.QUARANTINED:
        return SupportDecision(
            status=SupportStatus.REVIEW_REQUIRED,
            reason_code="protein_inference_raw_inputs_quarantined",
            rationale=(
                "A critical format, build, vocabulary, or cross-source disagreement requires "
                "review before downstream use."
            ),
        )
    if disposition is ProteinInferenceAdmissionDisposition.ABSTAINED:
        return SupportDecision(
            status=SupportStatus.UNSUPPORTED,
            reason_code="protein_inference_raw_inputs_abstained",
            rationale=(
                "The upstream state or declared source profile is outside the reviewed M03-03 "
                "admission domain."
            ),
        )
    return SupportDecision(
        status=SupportStatus.UNSUPPORTED,
        reason_code="protein_inference_raw_inputs_rejected",
        rationale=(
            "Transport integrity or an exact byte-capacity boundary rejected this source set."
        ),
    )


def expected_uncertainty() -> UncertaintyProfile:
    """Return the fixed non-probabilistic seven-dimension uncertainty envelope."""

    estimates = tuple(
        UncertaintyEstimate(
            state=EstimateState.NOT_ESTIMABLE,
            probability=None,
            rationale=rationale,
        )
        for rationale in M0303_UNCERTAINTY_RATIONALES
    )
    return UncertaintyProfile(
        measurement=estimates[0],
        sampling=estimates[1],
        parameter=estimates[2],
        model_form=estimates[3],
        identification=estimates[4],
        support=estimates[5],
        transport=estimates[6],
        sensitivity_notes=M0303_SENSITIVITY_NOTES,
    )


def expected_limitations() -> tuple[Limitation, ...]:
    """Return the exact interpretation ceiling for raw-source admission."""

    return (
        Limitation(
            code="raw_admission_only",
            statement=(
                "This result validates bounded transport, declared format structure, and "
                "content-addressed source bindings only; it does not infer a protein, "
                "proteoform, complex, pathway, subtype, biological state, or absence."
            ),
        ),
        Limitation(
            code="caller_declared_controls_not_authenticated",
            statement=(
                "Digests prove deterministic self-consistency of caller-declared controls and "
                "source-byte bindings, not issuer authenticity, parser-execution attestation, "
                "external reference truth, kinase activity, treatment suitability, or clinical "
                "readiness."
            ),
        ),
    )


def expected_control_decisions(
    context: ExecutionContext,
) -> tuple[ControlDecisionRecord, ...]:
    """Project the exact seven caller-declared controls into provenance."""

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


def admission_evidence_index(
    request: IngestProteinInferenceRawInputsRequest,
) -> tuple[EvidenceReference, ...]:
    """Return the exact de-duplicated content-reference index for admission."""

    refs = request.context.references
    search = request.protocol_receipt.search_space
    artifacts = (
        refs.approved_configuration.evidence,
        refs.identity_lineage.evidence,
        refs.provenance.evidence,
        refs.consent.evidence,
        refs.quality.evidence,
        refs.support.evidence,
        refs.intended_use.evidence,
        request.policy.evidence,
        search.canonical_sequence_reference,
        search.decoy_reference,
        search.evidence,
        request.protocol_receipt.modification_vocabulary_reference,
        *(item.artifact for item in request.lineage_receipt.artifacts),
        *(item.artifact for item in request.sources),
        *((search.isoform_reference,) if search.isoform_reference is not None else ()),
        *((search.variant_reference,) if search.variant_reference is not None else ()),
        *((search.contaminant_reference,) if search.contaminant_reference is not None else ()),
    )
    unique = {
        (item.artifact_id, item.version, item.digest, item.media_type): item for item in artifacts
    }
    return tuple(
        EvidenceReference(
            reference=unique[key],
            role="evidence",
            claim=M0303_EVIDENCE_CLAIM,
        )
        for key in sorted(unique, key=canonical_json_bytes)
    )


def expected_provenance(
    request: IngestProteinInferenceRawInputsRequest,
    request_hash: Sha256Digest,
) -> ProvenanceRecord:
    """Derive the exact metadata-only provenance envelope."""

    from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
        configuration_digest,
        lineage_receipt_digest,
        policy_digest,
        protocol_receipt_digest,
    )

    policy_hash = policy_digest(request.policy)
    config_hash = configuration_digest(request.policy)
    evidence = admission_evidence_index(request)
    controls = expected_control_decisions(request.context)
    input_digests = tuple(
        sorted(
            {
                request_hash,
                policy_hash,
                config_hash,
                request.source_manifest_digest,
                protocol_receipt_digest(request.protocol_receipt),
                lineage_receipt_digest(request.lineage_receipt),
                request.protocol_receipt.protocol_result_digest,
                request.protocol_receipt.protocol_digest,
                request.protocol_receipt.search_space_digest,
                request.lineage_receipt.lineage_result_digest,
                request.lineage_receipt.lineage_request_digest,
                request.lineage_receipt.identity_resolution_digest,
                request.lineage_receipt.graph_digest,
                *(item.reference.digest for item in evidence),
                *(item.evidence_digest for item in controls),
            }
        )
    )
    refs = request.context.references
    suffix = request_hash.removeprefix("sha256:")
    return ProvenanceRecord(
        activity_id=f"activity.m0303.{suffix}",
        actor_id=request.context.actor_id,
        module_id=M0303_MODULE_ID,
        module_version=M0303_CONTRACT_VERSION,
        generated_at=request.context.occurred_at,
        input_digests=input_digests,
        configuration_digest=config_hash,
        consent_decision_id=refs.consent.decision_id,
        consent_state=ConsentState.GRANTED,
        consent_policy_version=refs.consent.policy_version,
        consent_evidence_digest=refs.consent.evidence.digest,
        control_decisions=controls,
    )


# Output models are deliberately defined in the same versioned contract so every public schema
# can be independently validated and the top-level result can replay the complete request.
class ProteinInferenceBuildBindingReceipt(FrozenModel):
    state: ProteinInferenceBuildState
    declared_build_id: Identifier | None = None
    declared_build_version: SemanticVersion | None = None
    expected_build_id: Identifier | None = None
    expected_build_version: SemanticVersion | None = None

    @model_validator(mode="after")
    def build_fields_are_paired(self) -> ProteinInferenceBuildBindingReceipt:
        pairs = (
            (self.declared_build_id, self.declared_build_version),
            (self.expected_build_id, self.expected_build_version),
        )
        if any((left is None) != (right is None) for left, right in pairs):
            raise ValueError("build identifiers and versions must be paired")
        declared = (self.declared_build_id, self.declared_build_version)
        expected = (self.expected_build_id, self.expected_build_version)
        if self.state is ProteinInferenceBuildState.EXACT and (
            self.declared_build_id is None or declared != expected
        ):
            raise ValueError("exact build state requires matching declared and expected builds")
        if self.state is ProteinInferenceBuildState.MISMATCHED and (
            self.declared_build_id is None or self.expected_build_id is None or declared == expected
        ):
            raise ValueError("mismatched build state requires two different builds")
        if self.state is ProteinInferenceBuildState.MISSING and (
            self.declared_build_id is not None or self.expected_build_id is None
        ):
            raise ValueError("missing build state requires only an expected build")
        if self.state is ProteinInferenceBuildState.UNSUPPORTED and (
            self.expected_build_id is None
        ):
            raise ValueError("unsupported build state requires an expected build")
        if self.state is ProteinInferenceBuildState.NOT_APPLICABLE and any(
            item is not None for item in declared
        ):
            raise ValueError("not-applicable build state cannot carry a detected build")
        return self


class ProteinInferenceParseDiagnostic(FrozenModel):
    diagnostic_id: Identifier
    code: ProteinInferenceDiagnosticCode
    action: ProteinInferenceDiagnosticAction
    source_ids: tuple[Identifier, ...] = Field(default=(), max_length=M0303_MAX_SOURCES)
    message: NonEmptyStr

    @field_validator("source_ids")
    @classmethod
    def source_ids_are_unique(cls, values: tuple[Identifier, ...]) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("diagnostic source identifiers must be unique")
        return values

    @model_validator(mode="after")
    def diagnostic_uses_closed_vocabulary(self) -> ProteinInferenceParseDiagnostic:
        expected = sha256_digest({"code": self.code, "source_ids": tuple(sorted(self.source_ids))})
        suffix = expected.removeprefix("sha256:")[:16]
        if (
            self.diagnostic_id != f"diagnostic.m0303.{self.code.value}.{suffix}"
            or self.action is not _ACTION_BY_CODE[self.code]
            or self.message != _MESSAGE_BY_CODE[self.code]
        ):
            raise ValueError("M03-03 diagnostic contradicts its closed code vocabulary")
        return self


class ValidatedProteinInferenceRawInput(FrozenModel):
    source_id: Identifier
    role: ProteinInferenceRawRole
    source_digest: Sha256Digest
    source_size_bytes: int = Field(ge=0, le=M0303_MAX_SOURCE_BYTES + 1)
    decoded_digest: Sha256Digest | None = None
    decoded_size_bytes: int = Field(ge=0, le=M0303_MAX_DECODED_BYTES + 1)
    detected_format: ProteinInferenceRawFormat | None = None
    detected_version: SemanticVersion | None = None
    compression: ProteinInferenceCompression | None = None
    record_count: int = Field(ge=0, le=10_000_000)
    reference_count: int = Field(ge=0, le=10_000_000)
    build: ProteinInferenceBuildBindingReceipt
    diagnostics: tuple[ProteinInferenceParseDiagnostic, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def parsed_summary_is_relationally_closed(self) -> ValidatedProteinInferenceRawInput:
        decoded_cap = any(
            item.code is ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED
            for item in self.diagnostics
        )
        if self.decoded_digest is None and self.decoded_size_bytes != 0 and not decoded_cap:
            raise ValueError("decoded byte count requires a decoded content digest")
        if decoded_cap and self.decoded_digest is not None:
            raise ValueError("bounded partial decode cannot claim a complete content digest")
        if self.detected_format is None and self.detected_version is not None:
            raise ValueError("detected version requires a detected format")
        if any(self.source_id not in item.source_ids for item in self.diagnostics):
            raise ValueError("source diagnostics must name their parsed source")
        if len(self.diagnostics) != len(set(self.diagnostics)):
            raise ValueError("source diagnostics must be unique")
        return self


class ProteinInferenceRawAdmissionReceipt(FrozenModel):
    protocol_receipt_digest: Sha256Digest
    lineage_receipt_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    source_manifest_digest: Sha256Digest
    parent_target: Literal["complex_activity"] = M0303_PARENT
    emits_complex_activity: Literal[False] = False
    infers_identity: Literal[False] = False
    infers_protein: Literal[False] = False
    infers_proteoform: Literal[False] = False
    infers_isoform: Literal[False] = False
    infers_glioma_specific_biology: Literal[False] = False
    infers_kinase_activity: Literal[False] = False
    disposition: ProteinInferenceAdmissionDisposition


def expected_admission_receipt(
    request: IngestProteinInferenceRawInputsRequest,
    disposition: ProteinInferenceAdmissionDisposition,
) -> ProteinInferenceRawAdmissionReceipt:
    """Derive the exact compact downstream handoff receipt."""

    from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
        configuration_digest,
        lineage_receipt_digest,
        policy_digest,
        protocol_receipt_digest,
    )

    return ProteinInferenceRawAdmissionReceipt(
        protocol_receipt_digest=protocol_receipt_digest(request.protocol_receipt),
        lineage_receipt_digest=lineage_receipt_digest(request.lineage_receipt),
        policy_digest=policy_digest(request.policy),
        configuration_digest=configuration_digest(request.policy),
        source_manifest_digest=request.source_manifest_digest,
        disposition=disposition,
    )


class ProteinInferenceRawAdmissionResult(NonInferenceResultModel):
    output_type: Literal["protein_inference_raw_admission_result"] = (
        "protein_inference_raw_admission_result"
    )
    result_id: Identifier
    result_version: Literal["1.0.0"] = M0303_CONTRACT_VERSION
    request_digest: Sha256Digest
    policy_digest: Sha256Digest
    configuration_digest: Sha256Digest
    result_digest: Sha256Digest
    request: IngestProteinInferenceRawInputsRequest
    receipt: ProteinInferenceRawAdmissionReceipt
    raw_inputs: tuple[ValidatedProteinInferenceRawInput, ...] = Field(
        default=(), max_length=M0303_MAX_SOURCES
    )
    diagnostics: tuple[ProteinInferenceParseDiagnostic, ...] = Field(
        default=(), max_length=M0303_MAX_DIAGNOSTICS
    )
    disposition: ProteinInferenceAdmissionDisposition
    parent_target: Literal["complex_activity"] = M0303_PARENT
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M0303_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=2, max_length=2)
    human_review_required: bool
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def result_is_relationally_closed(self) -> ProteinInferenceRawAdmissionResult:
        from glio_proteogen.contracts.m03_03.canonical import (  # noqa: PLC0415
            canonical_request_digest,
            configuration_digest,
            policy_digest,
            result_payload_digest,
        )

        request_hash = canonical_request_digest(self.request)
        active_policy_hash = policy_digest(self.request.policy)
        config_hash = configuration_digest(self.request.policy)
        source_ids = {item.source_id for item in self.request.sources}
        diagnostic_ids = tuple(item.diagnostic_id for item in self.diagnostics)
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("M03-03 result diagnostics must be unique")
        if any(not set(item.source_ids).issubset(source_ids) for item in self.diagnostics):
            raise ValueError("M03-03 diagnostics name an undeclared source")
        upstream_diagnostics = expected_upstream_diagnostics(self.request)
        if upstream_diagnostics:
            if self.raw_inputs or not _semantic_tuple_equal(self.diagnostics, upstream_diagnostics):
                raise ValueError("M03-03 safe failure contradicts its upstream disposition")
        else:
            _validate_raw_input_closure(self.request, self.raw_inputs, self.diagnostics)
        disposition = expected_disposition(self.diagnostics)
        expected_receipt = expected_admission_receipt(self.request, disposition)
        suffix = request_hash.removeprefix("sha256:")
        if (
            self.result_id != f"result.m0303.{suffix}"
            or self.request_digest != request_hash
            or self.policy_digest != active_policy_hash
            or self.configuration_digest != config_hash
            or self.receipt != expected_receipt
            or self.disposition is not disposition
            or self.support != expected_support(disposition)
            or not _uncertainty_equal(self.uncertainty, expected_uncertainty())
            or not _provenance_equal(
                self.provenance, expected_provenance(self.request, request_hash)
            )
            or not _semantic_tuple_equal(self.evidence, admission_evidence_index(self.request))
            or not _semantic_tuple_equal(self.limitations, expected_limitations())
            or self.human_review_required
            != (disposition is not ProteinInferenceAdmissionDisposition.VALIDATED)
            or self.completed_at != self.request.context.occurred_at
        ):
            raise ValueError("M03-03 result contradicts its embedded admission request")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("M03-03 result digest does not match its canonical content")
        return self


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


def _validate_raw_input_closure(
    request: IngestProteinInferenceRawInputsRequest,
    raw_inputs: tuple[ValidatedProteinInferenceRawInput, ...],
    diagnostics: tuple[ProteinInferenceParseDiagnostic, ...],
) -> None:
    by_source = {item.source_id: item for item in request.sources}
    input_ids = tuple(item.source_id for item in raw_inputs)
    if len(input_ids) != len(set(input_ids)) or set(input_ids) != set(by_source):
        raise ValueError("M03-03 result requires exactly one summary per declared source")
    flattened = tuple(item for value in raw_inputs for item in value.diagnostics)
    if not set(flattened).issubset(set(diagnostics)):
        raise ValueError("M03-03 source diagnostics must occur in the result index")
    transport_codes = {
        ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
        ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH,
        ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED,
        ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED,
        ProteinInferenceDiagnosticCode.INVALID_GZIP,
        ProteinInferenceDiagnosticCode.UNSUPPORTED_FORMAT,
        ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION,
        ProteinInferenceDiagnosticCode.MALFORMED_CONTENT,
        ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT,
        ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY,
        ProteinInferenceDiagnosticCode.DANGLING_REFERENCE,
        ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH,
        ProteinInferenceDiagnosticCode.BUILD_MISMATCH,
        ProteinInferenceDiagnosticCode.BUILD_MISSING,
        ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED,
    }
    source_scoped = {
        item for item in diagnostics if item.code in transport_codes and len(item.source_ids) == 1
    }
    if not source_scoped.issubset(set(flattened)):
        raise ValueError("source-scoped result diagnostics require their raw-input record")
    if sum(item.source_size_bytes for item in raw_inputs) > (
        request.policy.max_total_source_bytes + 1
    ):
        raise ValueError("M03-03 result exceeds the bounded aggregate source summary")
    if sum(item.decoded_size_bytes for item in raw_inputs) > (
        request.policy.max_total_decoded_bytes + 1
    ):
        raise ValueError("M03-03 result exceeds the bounded aggregate decoded summary")
    for value in raw_inputs:
        source = by_source[value.source_id]
        codes = {item.code for item in value.diagnostics}
        if value.role is not source.role:
            raise ValueError("parsed source role contradicts its declaration")
        _require_transport_code(source, value, codes, request.policy.max_source_bytes)
        _forbid_code_without_condition(
            value.decoded_size_bytes <= request.policy.max_decoded_bytes,
            ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED,
            codes,
        )
        _require_detected_format_closure(source, value, codes)
        if (
            value.detected_format is not None
            and value.compression is not source.declared_compression
        ):
            raise ValueError("detected compression contradicts its source declaration")
        expected_build = (source.expected_build_id, source.expected_build_version)
        actual_expected = (
            value.build.expected_build_id,
            value.build.expected_build_version,
        )
        if expected_build != actual_expected:
            raise ValueError("build receipt contradicts the source's expected build")
        expected_build_code = {
            ProteinInferenceBuildState.MISMATCHED: (ProteinInferenceDiagnosticCode.BUILD_MISMATCH),
            ProteinInferenceBuildState.MISSING: ProteinInferenceDiagnosticCode.BUILD_MISSING,
            ProteinInferenceBuildState.UNSUPPORTED: (
                ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED
            ),
        }.get(value.build.state)
        actual_build_codes = codes & {
            ProteinInferenceDiagnosticCode.BUILD_MISMATCH,
            ProteinInferenceDiagnosticCode.BUILD_MISSING,
            ProteinInferenceDiagnosticCode.BUILD_UNSUPPORTED,
        }
        if actual_build_codes != (
            {expected_build_code} if expected_build_code is not None else set()
        ):
            raise ValueError("build diagnostic contradicts the parsed build state")


def _forbid_code_without_condition(
    condition: bool,  # noqa: FBT001 - relational predicate, not a mode flag.
    code: ProteinInferenceDiagnosticCode,
    codes: set[ProteinInferenceDiagnosticCode],
) -> None:
    if condition and code in codes:
        raise ValueError("M03-03 diagnostic set contradicts its parsed source summary")


def _require_transport_code(
    source: ProteinInferenceRawSource,
    value: ValidatedProteinInferenceRawInput,
    codes: set[ProteinInferenceDiagnosticCode],
    max_source_bytes: int,
) -> None:
    """Replay the parser's raw-cap, declared-size, then checksum precedence."""

    ordered = (
        (
            value.source_size_bytes > max_source_bytes,
            ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED,
        ),
        (
            value.source_size_bytes != source.byte_length,
            ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH,
        ),
        (
            value.source_digest != source.artifact.digest,
            ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
        ),
    )
    expected = next((code for condition, code in ordered if condition), None)
    transport_codes = {code for _, code in ordered}
    actual = codes & transport_codes
    if actual != ({expected} if expected is not None else set()):
        raise ValueError("M03-03 transport diagnostic contradicts its parsed source summary")


def _require_detected_format_closure(
    source: ProteinInferenceRawSource,
    value: ValidatedProteinInferenceRawInput,
    codes: set[ProteinInferenceDiagnosticCode],
) -> None:
    failure_codes = {
        ProteinInferenceDiagnosticCode.CHECKSUM_MISMATCH,
        ProteinInferenceDiagnosticCode.DECLARED_SIZE_MISMATCH,
        ProteinInferenceDiagnosticCode.RAW_SIZE_LIMIT_EXCEEDED,
        ProteinInferenceDiagnosticCode.DECODED_SIZE_LIMIT_EXCEEDED,
        ProteinInferenceDiagnosticCode.INVALID_GZIP,
        ProteinInferenceDiagnosticCode.UNSUPPORTED_FORMAT,
        ProteinInferenceDiagnosticCode.UNSUPPORTED_VERSION,
        ProteinInferenceDiagnosticCode.MALFORMED_CONTENT,
        ProteinInferenceDiagnosticCode.FORBIDDEN_XML_CONSTRUCT,
        ProteinInferenceDiagnosticCode.DUPLICATE_JSON_KEY,
        ProteinInferenceDiagnosticCode.DANGLING_REFERENCE,
        ProteinInferenceDiagnosticCode.ROLE_FORMAT_MISMATCH,
    }
    if codes & failure_codes:
        if value.detected_format is not None:
            raise ValueError("failed source cannot claim a fully detected format")
    elif value.detected_format is not source.declared_format:
        raise ValueError("successful parsed format contradicts its declaration")


__all__ = [name for name in globals() if not name.startswith("_")]
