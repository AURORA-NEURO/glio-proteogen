"""Provisional M23-04 external transport evaluator contracts.

M23-04 independently evaluates site, lab, platform, treatment-era,
population, disease-class and specimen transport beneath Cross-instrument
transport. It emits a transportability report and support-domain update; the
ABI is provisional pending Computational biology owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m23_04.canonical import (
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.models import (
    ArtifactReference,
    EvidenceReference,
    ExecutionContext,
    FrozenModel,
    Identifier,
    Limitation,
    NonEmptyStr,
    ProvenanceRecord,
    SemanticVersion,
    Sha256Digest,
    SupportDecision,
    SupportStatus,
    UncertaintyProfile,
)

# PROVISIONAL ABI: inferred solely from dossier lines 8088-8128.
M2304_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2304_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:8088-8128"
M2304_MODULE_ID: Final = "GLIO-PROTEOGEN-M23-04"
M2304_OPERATION: Final = "evaluate_variant_peptide_external_transport"
M2304_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2304_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m23-04+json"
M2304_PARENT: Final = "variant peptide"
M2304_OWNER: Final = "Computational biology"
M2304_SAFETY_CLASS: Final = "S3"
M2304_GATE: Final = "G3"
M2304_PROVISIONAL_ABI: Final = True
M2304_MAX_EVALUATIONS: Final = 128
M2304_MAX_VALIDATIONS: Final = 128
M2304_MAX_DIMENSIONS: Final = 16
M2304_MAX_EVIDENCE: Final = 64
M2304_MAX_FINDINGS: Final = 64
M2304_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2304_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2304_EVIDENCE_CLAIM: Final = (
    "Caller-declared M23-04 transport, calibration, support-domain and "
    "validation material; issuer authority is not authenticated."
)
M2304_RESULT_ID_PREFIX: Final = "transport.m2304."


class TransportDimension(StrEnum):
    SITE = "site"
    LAB = "lab"
    PLATFORM = "platform"
    TREATMENT_ERA = "treatment_era"
    POPULATION = "population"
    DISEASE_CLASS = "disease_class"
    SPECIMEN = "specimen"


class TransportStatus(StrEnum):
    SUPPORTED = "supported"
    DOMAIN_NARROWED = "domain_narrowed"
    NOT_EVALUABLE = "not_evaluable"


class EvaluationStatus(StrEnum):
    EVALUATED = "evaluated"
    ABSTAINED = "abstained"


class TransportFindingCode(StrEnum):
    DIMENSION_UNVALIDATED = "dimension_unvalidated"
    CALIBRATION_FLOOR_FAILED = "calibration_floor_failed"
    SUPPORT_DOMAIN_NARROWED = "support_domain_narrowed"
    SPECIMEN_MISMATCH = "specimen_mismatch"
    PROVENANCE_MISSING = "provenance_missing"
    EVALUATION_INCOMPLETE = "evaluation_incomplete"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class TransportValidation(FrozenModel):
    """Independent validation record for one external transport dimension."""

    validation_id: Identifier
    dimension: TransportDimension
    source_domain: NonEmptyStr
    target_domain: NonEmptyStr
    assay_or_platform: NonEmptyStr
    specimen_description: NonEmptyStr
    sample_count: int = Field(gt=0)
    identity_verified: Literal[True] = True
    provenance_artifact: ArtifactReference
    uncertainty: UncertaintyProfile
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def source_and_target_are_distinct(self) -> TransportValidation:
        if self.source_domain == self.target_domain:
            raise ValueError("transport validation source and target domains must differ")
        return self


class TransportEvaluation(FrozenModel):
    """Metric and support decision for one transport dimension."""

    evaluation_id: Identifier
    dimension: TransportDimension
    status: TransportStatus
    metric_name: NonEmptyStr
    metric_value: float = Field(ge=0.0, le=1.0)
    calibration_floor: float = Field(ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def metric_matches_status(self) -> TransportEvaluation:
        if self.status is TransportStatus.SUPPORTED and self.metric_value < self.calibration_floor:
            raise ValueError("supported evaluation must meet its calibration floor")
        if (
            self.status is TransportStatus.DOMAIN_NARROWED
            and self.metric_value >= self.calibration_floor
        ):
            raise ValueError("narrowed evaluation must document a failed calibration floor")
        return self


class SupportDomainUpdate(FrozenModel):
    update_id: Identifier
    version: SemanticVersion
    status: TransportStatus
    retained_dimensions: tuple[TransportDimension, ...] = Field(
        min_length=1, max_length=M2304_MAX_DIMENSIONS
    )
    narrowed_dimensions: tuple[TransportDimension, ...] = Field(
        default=(), max_length=M2304_MAX_DIMENSIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def domains_are_disjoint(self) -> SupportDomainUpdate:
        if set(self.retained_dimensions) & set(self.narrowed_dimensions):
            raise ValueError("retained and narrowed dimensions must be disjoint")
        return self


class TransportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[TransportDimension, ...] = Field(
        min_length=1, max_length=M2304_MAX_DIMENSIONS
    )
    minimum_calibration_floor: float = Field(ge=0.0, le=1.0)
    independent_validation_required: Literal[True] = True
    isoform_aware_quantification_required: Literal[True] = True
    leakage_audit_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def required_dimensions_are_unique(self) -> TransportConfiguration:
        if len(self.required_dimensions) != len(set(self.required_dimensions)):
            raise ValueError("required transport dimensions must be unique")
        return self


class TransportabilityReport(FrozenModel):
    """External transport report and support-domain update."""

    report_id: Identifier
    version: SemanticVersion
    validations: tuple[TransportValidation, ...] = Field(
        min_length=1, max_length=M2304_MAX_VALIDATIONS
    )
    evaluations: tuple[TransportEvaluation, ...] = Field(
        min_length=1, max_length=M2304_MAX_EVALUATIONS
    )
    support_domain: SupportDomainUpdate
    configuration: TransportConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2304_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> TransportabilityReport:
        validation_dims = {item.dimension for item in self.validations}
        evaluation_dims = {item.dimension for item in self.evaluations}
        required_dimensions = set(self.configuration.required_dimensions)
        if not required_dimensions <= validation_dims:
            raise ValueError("report must validate every configured transport dimension")
        if not required_dimensions <= evaluation_dims:
            raise ValueError("report must evaluate every configured transport dimension")
        if len(evaluation_dims) != len(self.evaluations):
            raise ValueError("transport evaluation dimensions must be unique")
        if len(validation_dims) != len(self.validations):
            raise ValueError("transport validation dimensions must be unique")
        if self.support_domain.status is TransportStatus.SUPPORTED and (
            self.support_domain.narrowed_dimensions
        ):
            raise ValueError("supported report cannot narrow transport dimensions")
        return self


class TransportFinding(FrozenModel):
    finding_id: Identifier
    code: TransportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2304_MAX_EVIDENCE)


class EvaluateVariantPeptideExternalTransportRequest(FrozenModel):
    """Provisional request for external transport evaluation."""

    operation: Literal["evaluate_variant_peptide_external_transport"] = M2304_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2304_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    benchmark_package: ArtifactReference
    validations: tuple[TransportValidation, ...] = Field(
        min_length=1, max_length=M2304_MAX_VALIDATIONS
    )
    evaluations: tuple[TransportEvaluation, ...] = Field(
        min_length=1, max_length=M2304_MAX_EVALUATIONS
    )
    configuration: TransportConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2304_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> EvaluateVariantPeptideExternalTransportRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request ID must match the request")
        validation_dims = {item.dimension for item in self.validations}
        evaluation_dims = {item.dimension for item in self.evaluations}
        required = set(self.configuration.required_dimensions)
        if not required <= validation_dims or not required <= evaluation_dims:
            raise ValueError("request must cover every configured transport dimension")
        if len(evaluation_dims) != len(self.evaluations):
            raise ValueError("request evaluation dimensions must be unique")
        if len(validation_dims) != len(self.validations):
            raise ValueError("request validation dimensions must be unique")
        required_artifacts = (
            self.mass_spectrometry_proteome,
            self.genome_transcriptome,
            self.ptm_annotations,
            self.benchmark_package,
        )
        artifact_ids = tuple(item.artifact_id for item in required_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("transport input artifact IDs must be unique")
        required_keys = {
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in required_artifacts
        }
        source_keys = {
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        }
        if len(source_keys) != len(self.source_artifacts) or source_keys != required_keys:
            raise ValueError("source artifacts must bind every transport input exactly once")
        return self


class VariantPeptideExternalTransportResult(FrozenModel):
    """Transportability result with support-domain narrowing and abstention."""

    output_type: Literal["variant_peptide_external_transport"] = (
        "variant_peptide_external_transport"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2304_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateVariantPeptideExternalTransportRequest
    status: EvaluationStatus
    report: TransportabilityReport | None = None
    findings: tuple[TransportFinding, ...] = Field(default=(), max_length=M2304_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["variant peptide"] = M2304_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2304_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> VariantPeptideExternalTransportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request_digest):
            raise ValueError("result identifier does not bind the request digest")
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported transport report")
            if (
                self.report.configuration != self.request.configuration
                or self.report.validations != self.request.validations
                or self.report.evaluations != self.request.evaluations
            ):
                raise ValueError("evaluated report must bind the exact request declarations")
            narrowed = tuple(
                item.dimension
                for item in self.request.evaluations
                if item.status is TransportStatus.DOMAIN_NARROWED
            )
            retained = tuple(
                item.dimension
                for item in self.request.evaluations
                if item.status is not TransportStatus.DOMAIN_NARROWED
            )
            expected_retained = retained or (narrowed[0],)
            expected_status = (
                TransportStatus.DOMAIN_NARROWED if narrowed else TransportStatus.SUPPORTED
            )
            support_domain = self.report.support_domain
            if (
                support_domain.version != self.request.configuration.version
                or support_domain.status is not expected_status
                or support_domain.retained_dimensions != expected_retained
                or support_domain.narrowed_dimensions != narrowed
            ):
                raise ValueError("evaluated support domain must bind request evaluations")
        elif (
            self.report is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no report and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


def result_identifier(request_digest: Sha256Digest) -> str:
    """Return the deterministic M23-04 result identifier for a request digest."""

    return M2304_RESULT_ID_PREFIX + request_digest.removeprefix("sha256:")


__all__ = [
    "M2304_CONTRACT_VERSION",
    "M2304_DOSSIER_SHA256",
    "M2304_DOSSIER_SLICE",
    "M2304_EVIDENCE_CLAIM",
    "M2304_GATE",
    "M2304_MAX_CANONICAL_REQUEST_BYTES",
    "M2304_MAX_CANONICAL_RESULT_BYTES",
    "M2304_MAX_DIMENSIONS",
    "M2304_MAX_EVALUATIONS",
    "M2304_MAX_EVIDENCE",
    "M2304_MAX_FINDINGS",
    "M2304_MAX_VALIDATIONS",
    "M2304_MODULE_ID",
    "M2304_OPERATION",
    "M2304_OUTPUT_MEDIA_TYPE",
    "M2304_OWNER",
    "M2304_PARENT",
    "M2304_PROVISIONAL_ABI",
    "M2304_RESULT_ID_PREFIX",
    "M2304_SAFETY_CLASS",
    "EvaluateVariantPeptideExternalTransportRequest",
    "EvaluationStatus",
    "SupportDomainUpdate",
    "TransportConfiguration",
    "TransportDimension",
    "TransportEvaluation",
    "TransportFinding",
    "TransportFindingCode",
    "TransportStatus",
    "TransportValidation",
    "TransportabilityReport",
    "VariantPeptideExternalTransportResult",
    "result_identifier",
]
