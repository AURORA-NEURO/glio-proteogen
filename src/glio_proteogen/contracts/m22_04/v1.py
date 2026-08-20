"""Provisional M22-04 external transport evaluator contracts.

M22-04 independently evaluates site, lab, platform, treatment-era,
population, disease-class and specimen transport beneath Orthogonal
immunoassay validation. It emits a transportability report and support-domain
update; the ABI is provisional pending Scientific engineering owner
confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, FiniteFloat, model_validator

from glio_proteogen.contracts.m22_04.canonical import (
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

# PROVISIONAL ABI: inferred solely from the permitted M22-04 dossier slice.
M2204_MODULE_ID: Final = "GLIO-PROTEOGEN-M22-04"
M2204_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2204_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7728-7768"
M2204_OPERATION: Final = "evaluate_protein_rna_discordance_external_transport"
M2204_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2204_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-04+json"
M2204_M2202_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-02+json"
M2204_M2203_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-03+json"
M2204_PARENT: Final = "protein-RNA discordance"
M2204_OWNER: Final = "Scientific engineering"
M2204_SAFETY_CLASS: Final = "S3"
M2204_GATE: Final = "G3"
M2204_PROVISIONAL_ABI: Final = True
M2204_MAX_EVALUATIONS: Final = 128
M2204_MAX_VALIDATIONS: Final = 128
M2204_MAX_DIMENSIONS: Final = 16
M2204_MAX_EVIDENCE: Final = 64
M2204_MAX_FINDINGS: Final = 64
M2204_MAX_CANONICAL_REQUEST_BYTES: Final = 8 * 1024 * 1024
M2204_MAX_CANONICAL_RESULT_BYTES: Final = 16 * 1024 * 1024
M2204_EVIDENCE_CLAIM: Final = (
    "Caller-declared M22-04 transport, calibration, support-domain and "
    "validation material; issuer authority is not authenticated."
)


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2204_MAX_EVIDENCE)


class TransportEvaluation(FrozenModel):
    """Metric and support decision for one transport dimension."""

    evaluation_id: Identifier
    dimension: TransportDimension
    status: TransportStatus
    metric_name: NonEmptyStr
    metric_value: FiniteFloat = Field(ge=0.0, le=1.0)
    calibration_floor: FiniteFloat = Field(ge=0.0, le=1.0)
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2204_MAX_EVIDENCE)

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
        min_length=1, max_length=M2204_MAX_DIMENSIONS
    )
    narrowed_dimensions: tuple[TransportDimension, ...] = Field(
        default=(), max_length=M2204_MAX_DIMENSIONS
    )
    rationale: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2204_MAX_EVIDENCE)

    @model_validator(mode="after")
    def domains_are_disjoint(self) -> SupportDomainUpdate:
        if set(self.retained_dimensions) & set(self.narrowed_dimensions):
            raise ValueError("retained and narrowed dimensions must be disjoint")
        if not set(self.retained_dimensions) | set(self.narrowed_dimensions):
            raise ValueError("support-domain update must retain or narrow a dimension")
        return self


class TransportConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    required_dimensions: tuple[TransportDimension, ...] = Field(
        min_length=1, max_length=M2204_MAX_DIMENSIONS
    )
    minimum_calibration_floor: float = Field(ge=0.0, le=1.0)
    independent_validation_required: Literal[True] = True
    leakage_audit_required: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2204_MAX_EVIDENCE)

    @model_validator(mode="after")
    def required_dimensions_are_unique(self) -> TransportConfiguration:
        if len(self.required_dimensions) != len(set(self.required_dimensions)):
            raise ValueError("required transport dimensions must be unique")
        if set(self.required_dimensions) != set(TransportDimension):
            raise ValueError("configuration must require all seven transport dimensions")
        return self


class TransportabilityReport(FrozenModel):
    """External transport report and support-domain update."""

    report_id: Identifier
    version: SemanticVersion
    validations: tuple[TransportValidation, ...] = Field(
        min_length=1, max_length=M2204_MAX_VALIDATIONS
    )
    evaluations: tuple[TransportEvaluation, ...] = Field(
        min_length=1, max_length=M2204_MAX_EVALUATIONS
    )
    support_domain: SupportDomainUpdate
    configuration: TransportConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2204_MAX_EVIDENCE)

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
        support_dims = set(self.support_domain.retained_dimensions) | set(
            self.support_domain.narrowed_dimensions
        )
        if support_dims != required_dimensions:
            raise ValueError("support-domain update must close every configured dimension")
        return self


class TransportFinding(FrozenModel):
    finding_id: Identifier
    code: TransportFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2204_MAX_EVIDENCE)


class EvaluateProteinRnaDiscordanceExternalTransportRequest(FrozenModel):
    """Provisional request for external transport evaluation."""

    operation: Literal["evaluate_protein_rna_discordance_external_transport"] = M2204_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2204_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    benchmark_package: ArtifactReference
    upstream_truth: ArtifactReference
    validations: tuple[TransportValidation, ...] = Field(
        min_length=1, max_length=M2204_MAX_VALIDATIONS
    )
    evaluations: tuple[TransportEvaluation, ...] = Field(
        min_length=1, max_length=M2204_MAX_EVALUATIONS
    )
    configuration: TransportConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2204_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> EvaluateProteinRnaDiscordanceExternalTransportRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must equal request id")
        if self.benchmark_package.media_type != M2204_M2203_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M22-03 benchmark result")
        if self.upstream_truth.media_type != M2204_M2202_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M22-02 upstream result")
        validation_dims = {item.dimension for item in self.validations}
        evaluation_dims = {item.dimension for item in self.evaluations}
        required = set(self.configuration.required_dimensions)
        if not required <= validation_dims or not required <= evaluation_dims:
            raise ValueError("request must cover every configured transport dimension")
        if len(evaluation_dims) != len(self.evaluations):
            raise ValueError("request evaluation dimensions must be unique")
        validation_ids = tuple(item.validation_id for item in self.validations)
        evaluation_ids = tuple(item.evaluation_id for item in self.evaluations)
        if len(validation_ids) != len(set(validation_ids)):
            raise ValueError("request validation ids must be unique")
        if len(evaluation_ids) != len(set(evaluation_ids)):
            raise ValueError("request evaluation ids must be unique")
        artifact_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(artifact_keys) != len(set(artifact_keys)):
            raise ValueError("request source artifacts must be unique")
        source_keys = set(artifact_keys)
        for required_artifact in (self.benchmark_package, self.upstream_truth):
            key = (
                required_artifact.artifact_id,
                required_artifact.version,
                required_artifact.digest,
                required_artifact.media_type,
            )
            if key not in source_keys:
                raise ValueError("source artifacts must include every upstream result")
        return self


def _provenance_binding_error(
    result: ProteinRnaDiscordanceExternalTransportResult,
) -> str | None:
    request = result.request
    expected_inputs = tuple(
        dict.fromkeys(
            (
                canonical_request_digest(request),
                request.benchmark_package.digest,
                request.upstream_truth.digest,
                *(artifact.digest for artifact in request.source_artifacts),
            )
        )
    )
    provenance_checks = (
        (
            result.provenance.module_id == M2204_MODULE_ID,
            "provenance module id must identify M22-04",
        ),
        (
            result.provenance.module_version == M2204_CONTRACT_VERSION,
            "provenance module version must identify M22-04",
        ),
        (
            result.provenance.configuration_digest
            == request.context.references.approved_configuration.evidence.digest,
            "provenance configuration must bind approved transport policy",
        ),
        (
            result.provenance.input_digests == expected_inputs,
            "provenance inputs must bind the request and source artifacts",
        ),
    )
    for bound, message in provenance_checks:
        if not bound:
            return message
    return None


class ProteinRnaDiscordanceExternalTransportResult(FrozenModel):
    """Transportability result with support-domain narrowing and abstention."""

    output_type: Literal["protein_rna_discordance_external_transport"] = (
        "protein_rna_discordance_external_transport"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2204_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateProteinRnaDiscordanceExternalTransportRequest
    status: EvaluationStatus
    report: TransportabilityReport | None = None
    findings: tuple[TransportFinding, ...] = Field(default=(), max_length=M2204_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein-RNA discordance"] = M2204_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2204_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = True

    @model_validator(mode="after")
    def result_is_closed(  # noqa: PLR0912 - closure validates independent safety invariants.
        self,
    ) -> ProteinRnaDiscordanceExternalTransportResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id must be deterministically bound to the request")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("result evidence must be unique")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        if self.provenance.module_id != M2204_MODULE_ID:
            raise ValueError("provenance module id must identify M22-04")
        required_digests = {
            self.request.benchmark_package.digest,
            self.request.upstream_truth.digest,
        }
        if not required_digests <= set(self.provenance.input_digests):
            raise ValueError("provenance must include every upstream result digest")
        provenance_error = _provenance_binding_error(self)
        if provenance_error is not None:
            raise ValueError(provenance_error)
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported transport report")
            if self.report.configuration != self.request.configuration:
                raise ValueError("evaluated report configuration must equal the request")
            if self.report.validations != self.request.validations:
                raise ValueError("evaluated report validations must equal the request")
            if self.report.evaluations != self.request.evaluations:
                raise ValueError("evaluated report evaluations must equal the request")
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
    "M2204_CONTRACT_VERSION",
    "M2204_DOSSIER_SHA256",
    "M2204_DOSSIER_SLICE",
    "M2204_EVIDENCE_CLAIM",
    "M2204_GATE",
    "M2204_M2202_INPUT_MEDIA_TYPE",
    "M2204_M2203_INPUT_MEDIA_TYPE",
    "M2204_MAX_CANONICAL_REQUEST_BYTES",
    "M2204_MAX_CANONICAL_RESULT_BYTES",
    "M2204_MAX_DIMENSIONS",
    "M2204_MAX_EVALUATIONS",
    "M2204_MAX_EVIDENCE",
    "M2204_MAX_FINDINGS",
    "M2204_MAX_VALIDATIONS",
    "M2204_MODULE_ID",
    "M2204_OPERATION",
    "M2204_OUTPUT_MEDIA_TYPE",
    "M2204_OWNER",
    "M2204_PARENT",
    "M2204_PROVISIONAL_ABI",
    "M2204_SAFETY_CLASS",
    "EvaluateProteinRnaDiscordanceExternalTransportRequest",
    "EvaluationStatus",
    "ProteinRnaDiscordanceExternalTransportResult",
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
