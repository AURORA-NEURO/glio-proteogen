"""Provisional M24-04 external transport evaluator contracts.

M24-04 independently evaluates site, lab, platform, treatment-era,
population, disease-class and specimen transport beneath Batch/missing-protein
sensitivity. It emits a transportability report and support-domain update; the
ABI is provisional pending Bioinformatics owner confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m24_04.canonical import (
    canonical_request_digest,
    result_identifier,
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

# PROVISIONAL ABI: inferred solely from dossier lines 8448-8488.
M2404_MODULE_ID: Final = "GLIO-PROTEOGEN-M24-04"
M2404_OPERATION: Final = "evaluate_biomarker_panel_external_transport"
M2404_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2404_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-04+json"
M2404_PARENT: Final = "biomarker panel"
M2404_OWNER: Final = "Bioinformatics"
M2404_SAFETY_CLASS: Final = "S3"
M2404_GATE: Final = "G3"
M2404_PROVISIONAL_ABI: Final = True
M2404_MAX_EVALUATIONS: Final = 128
M2404_MAX_VALIDATIONS: Final = 128
M2404_MAX_DIMENSIONS: Final = 16
M2404_MAX_EVIDENCE: Final = 64
M2404_MAX_FINDINGS: Final = 64
M2404_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2404_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2404_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2404_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:8448-8488"
M2404_EVIDENCE_CLAIM: Final = (
    "Caller-declared M24-04 transport, calibration, support-domain and "
    "validation material; issuer authority is not authenticated."
)

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2404_MAX_EVIDENCE)


class TransportEvaluation(FrozenModel):
    """Metric and support decision for one transport dimension."""

    evaluation_id: Identifier
    dimension: TransportDimension
    status: TransportStatus
    metric_name: NonEmptyStr
    metric_value: FiniteFloat = Field(ge=0.0, le=1.0)
    calibration_floor: FiniteFloat = Field(ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2404_MAX_EVIDENCE)

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
        min_length=1, max_length=M2404_MAX_DIMENSIONS
    )
    narrowed_dimensions: tuple[TransportDimension, ...] = Field(
        default=(), max_length=M2404_MAX_DIMENSIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2404_MAX_EVIDENCE)

    @model_validator(mode="after")
    def domains_are_disjoint(self) -> SupportDomainUpdate:
        if set(self.retained_dimensions) & set(self.narrowed_dimensions):
            raise ValueError("retained and narrowed dimensions must be disjoint")
        if self.status is TransportStatus.DOMAIN_NARROWED and not self.narrowed_dimensions:
            raise ValueError("narrowed support status requires narrowed dimensions")
        if self.status is TransportStatus.SUPPORTED and self.narrowed_dimensions:
            raise ValueError("supported domain cannot carry narrowed dimensions")
        return self


class TransportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[TransportDimension, ...] = Field(
        min_length=1, max_length=M2404_MAX_DIMENSIONS
    )
    minimum_calibration_floor: float = Field(ge=0.0, le=1.0)
    independent_validation_required: Literal[True] = True
    ptm_aware_state_model_required: Literal[True] = True
    leakage_audit_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2404_MAX_EVIDENCE)

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
        min_length=1, max_length=M2404_MAX_VALIDATIONS
    )
    evaluations: tuple[TransportEvaluation, ...] = Field(
        min_length=1, max_length=M2404_MAX_EVALUATIONS
    )
    support_domain: SupportDomainUpdate
    configuration: TransportConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2404_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> TransportabilityReport:
        validation_dims = {item.dimension for item in self.validations}
        evaluation_dims = {item.dimension for item in self.evaluations}
        required_dimensions = set(self.configuration.required_dimensions)
        if len(validation_dims) != len(self.validations):
            raise ValueError("transport validation dimensions must be unique")
        if not required_dimensions <= validation_dims:
            raise ValueError("report must validate every configured transport dimension")
        if not required_dimensions <= evaluation_dims:
            raise ValueError("report must evaluate every configured transport dimension")
        if len(evaluation_dims) != len(self.evaluations):
            raise ValueError("transport evaluation dimensions must be unique")
        return self


class TransportFinding(FrozenModel):
    finding_id: Identifier
    code: TransportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2404_MAX_EVIDENCE)


class EvaluateBiomarkerPanelExternalTransportRequest(FrozenModel):
    """Provisional request for external transport evaluation."""

    operation: Literal["evaluate_biomarker_panel_external_transport"] = M2404_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2404_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    mass_spectrometry_proteome: ArtifactReference
    genome_transcriptome: ArtifactReference
    ptm_annotations: ArtifactReference
    benchmark_package: ArtifactReference
    validations: tuple[TransportValidation, ...] = Field(
        min_length=1, max_length=M2404_MAX_VALIDATIONS
    )
    evaluations: tuple[TransportEvaluation, ...] = Field(
        min_length=1, max_length=M2404_MAX_EVALUATIONS
    )
    configuration: TransportConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2404_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> EvaluateBiomarkerPanelExternalTransportRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        validation_dims = {item.dimension for item in self.validations}
        evaluation_dims = {item.dimension for item in self.evaluations}
        required = set(self.configuration.required_dimensions)
        if len(validation_dims) != len(self.validations):
            raise ValueError("request validation dimensions must be unique")
        if not required <= validation_dims or not required <= evaluation_dims:
            raise ValueError("request must cover every configured transport dimension")
        if len(evaluation_dims) != len(self.evaluations):
            raise ValueError("request evaluation dimensions must be unique")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        required_keys = {
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in (
                self.mass_spectrometry_proteome,
                self.genome_transcriptome,
                self.ptm_annotations,
                self.benchmark_package,
            )
        }
        if set(source_keys) != required_keys:
            raise ValueError("source artifacts must retain exactly all declared transport inputs")
        return self


class BiomarkerPanelExternalTransportResult(FrozenModel):
    """Transportability result with support-domain narrowing and abstention."""

    output_type: Literal["biomarker_panel_external_transport"] = (
        "biomarker_panel_external_transport"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2404_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateBiomarkerPanelExternalTransportRequest
    status: EvaluationStatus
    report: TransportabilityReport | None = None
    findings: tuple[TransportFinding, ...] = Field(default=(), max_length=M2404_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M2404_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2404_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelExternalTransportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result identifier must be derived from request digest")
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported transport report")
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


__all__ = [
    "M2404_CONTRACT_VERSION",
    "M2404_DOSSIER_SHA256",
    "M2404_DOSSIER_SLICE",
    "M2404_EVIDENCE_CLAIM",
    "M2404_GATE",
    "M2404_MAX_CANONICAL_REQUEST_BYTES",
    "M2404_MAX_CANONICAL_RESULT_BYTES",
    "M2404_MAX_DIMENSIONS",
    "M2404_MAX_EVALUATIONS",
    "M2404_MAX_EVIDENCE",
    "M2404_MAX_FINDINGS",
    "M2404_MAX_VALIDATIONS",
    "M2404_MODULE_ID",
    "M2404_OPERATION",
    "M2404_OUTPUT_MEDIA_TYPE",
    "M2404_OWNER",
    "M2404_PARENT",
    "M2404_PROVISIONAL_ABI",
    "M2404_SAFETY_CLASS",
    "BiomarkerPanelExternalTransportResult",
    "EvaluateBiomarkerPanelExternalTransportRequest",
    "EvaluationStatus",
    "FiniteFloat",
    "SupportDomainUpdate",
    "TransportConfiguration",
    "TransportDimension",
    "TransportEvaluation",
    "TransportFinding",
    "TransportFindingCode",
    "TransportStatus",
    "TransportValidation",
    "TransportabilityReport",
]
