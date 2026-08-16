"""Provisional M24-05 subgroup, equity, and rare-context contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m24_05.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 8492-8532.
M2405_MODULE_ID: Final = "GLIO-PROTEOGEN-M24-05"
M2405_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2405_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:8492-8532"
M2405_OPERATION: Final = "evaluate_biomarker_panel_subgroup_equity"
M2405_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2405_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-05+json"
M2405_M2404_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-04+json"
M2405_PARENT: Final = "biomarker panel"
M2405_OWNER: Final = "ML engineering"
M2405_SAFETY_CLASS: Final = "S3"
M2405_GATE: Final = "G3"
M2405_PROVISIONAL_ABI: Final = True
M2405_MAX_METRICS: Final = 256
M2405_MAX_EVIDENCE: Final = 64
M2405_MAX_FINDINGS: Final = 64
M2405_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2405_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_M2405_FRACTION_TOLERANCE: Final = 1e-12
M2405_EVIDENCE_CLAIM: Final = (
    "Caller-declared M24-05 subgroup performance, calibration, coverage and "
    "equity material; issuer authority is not authenticated."
)


class SubgroupDimension(StrEnum):
    AGE = "age"
    SEX = "sex"
    ANCESTRY = "ancestry"
    SUBTYPE = "subtype"
    SITE = "site"
    LOW_RESOURCE = "low_resource"
    PEDIATRIC_AYA = "pediatric_aya"
    RARE_BIOLOGICAL_STATE = "rare_biological_state"


class CoverageStatus(StrEnum):
    ADEQUATE = "adequate"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"
    NOT_EVALUABLE = "not_evaluable"


class EquityStatus(StrEnum):
    WITHIN_FLOOR = "within_floor"
    BELOW_FLOOR = "below_floor"
    RESTRICTED = "restricted"
    NOT_EVALUABLE = "not_evaluable"


class EvaluationStatus(StrEnum):
    EVALUATED = "evaluated"
    ABSTAINED = "abstained"


class SubgroupFindingCode(StrEnum):
    SAFETY_FLOOR_BREACH = "safety_floor_breach"
    COVERAGE_LIMITED = "coverage_limited"
    RARE_CONTEXT_UNSUPPORTED = "rare_context_unsupported"
    CALIBRATION_FAILURE = "calibration_failure"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class SubgroupPerformance(FrozenModel):
    metric_id: Identifier
    dimension: SubgroupDimension
    subgroup: NonEmptyStr
    sample_size: int = Field(ge=1)
    metric_name: NonEmptyStr
    value: float
    lower_bound: float
    upper_bound: float
    safety_floor: float
    coverage_status: CoverageStatus
    equity_status: EquityStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2405_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bounds_are_closed(self) -> SubgroupPerformance:
        if self.lower_bound > self.upper_bound:
            raise ValueError("subgroup bounds are not ordered")
        if not self.lower_bound <= self.value <= self.upper_bound:
            raise ValueError("subgroup value must lie within bounds")
        if self.equity_status is EquityStatus.BELOW_FLOOR and self.value >= self.safety_floor:
            raise ValueError("below-floor status requires value below safety floor")
        return self


class CalibrationSummary(FrozenModel):
    calibration_id: Identifier
    dimension: SubgroupDimension
    subgroup: NonEmptyStr
    expected_calibration_error: float = Field(ge=0.0)
    nominal_coverage: float = Field(ge=0.0, le=1.0)
    coverage_target: float = Field(ge=0.0, le=1.0)
    status: EvaluationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2405_MAX_EVIDENCE)


class CoverageSummary(FrozenModel):
    coverage_id: Identifier
    dimension: SubgroupDimension
    subgroup: NonEmptyStr
    supported_examples: int = Field(ge=0)
    total_examples: int = Field(ge=1)
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    status: CoverageStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2405_MAX_EVIDENCE)

    @model_validator(mode="after")
    def fraction_is_canonical(self) -> CoverageSummary:
        if self.supported_examples > self.total_examples:
            raise ValueError("supported examples cannot exceed total examples")
        expected = self.supported_examples / self.total_examples
        if abs(self.coverage_fraction - expected) > _M2405_FRACTION_TOLERANCE:
            raise ValueError("coverage fraction must equal supported divided by total examples")
        return self


class EvaluationConfiguration(FrozenModel):
    configuration_id: Identifier
    version: SemanticVersion
    nominal_coverage_target: float = Field(ge=0.0, le=1.0)
    safety_floor: float
    required_dimensions: tuple[SubgroupDimension, ...] = Field(min_length=8, max_length=8)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2405_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_dimensions_are_required(self) -> EvaluationConfiguration:
        if set(self.required_dimensions) != set(SubgroupDimension):
            raise ValueError("configuration must require all subgroup dimensions")
        return self


class SubgroupEvaluationReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    performance: tuple[SubgroupPerformance, ...] = Field(min_length=1, max_length=M2405_MAX_METRICS)
    calibration: tuple[CalibrationSummary, ...] = Field(min_length=1, max_length=M2405_MAX_METRICS)
    coverage: tuple[CoverageSummary, ...] = Field(min_length=1, max_length=M2405_MAX_METRICS)
    configuration: EvaluationConfiguration
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2405_MAX_EVIDENCE)

    @model_validator(mode="after")
    def report_is_closed(self) -> SubgroupEvaluationReport:
        ids = (
            tuple(item.metric_id for item in self.performance)
            + tuple(item.calibration_id for item in self.calibration)
            + tuple(item.coverage_id for item in self.coverage)
        )
        if len(ids) != len(set(ids)):
            raise ValueError("subgroup report ids must be unique")
        return self


class SubgroupFinding(FrozenModel):
    finding_id: Identifier
    code: SubgroupFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2405_MAX_EVIDENCE)


class EvaluateBiomarkerPanelSubgroupEquityRequest(FrozenModel):
    operation: Literal["evaluate_biomarker_panel_subgroup_equity"] = M2405_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2405_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    performance: tuple[SubgroupPerformance, ...] = Field(min_length=1, max_length=M2405_MAX_METRICS)
    calibration: tuple[CalibrationSummary, ...] = Field(min_length=1, max_length=M2405_MAX_METRICS)
    coverage: tuple[CoverageSummary, ...] = Field(min_length=1, max_length=M2405_MAX_METRICS)
    configuration: EvaluationConfiguration
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2405_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> EvaluateBiomarkerPanelSubgroupEquityRequest:
        if self.upstream_result.media_type != M2405_M2404_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M24-04 evaluator result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must match request id")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifact ids must be unique")
        if self.upstream_result.artifact_id not in set(source_ids):
            raise ValueError("source artifacts must include the upstream result")
        required = set(self.configuration.required_dimensions)
        if {item.dimension for item in self.performance} != required:
            raise ValueError("performance must cover every configured subgroup dimension")
        if {item.dimension for item in self.calibration} != required:
            raise ValueError("calibration must cover every configured subgroup dimension")
        if {item.dimension for item in self.coverage} != required:
            raise ValueError("coverage must cover every configured subgroup dimension")
        return self


class BiomarkerPanelSubgroupEvaluationResult(FrozenModel):
    output_type: Literal["biomarker_panel_subgroup_evaluation"] = (
        "biomarker_panel_subgroup_evaluation"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2405_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: EvaluateBiomarkerPanelSubgroupEquityRequest
    status: EvaluationStatus
    report: SubgroupEvaluationReport | None = None
    findings: tuple[SubgroupFinding, ...] = Field(default=(), max_length=M2405_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M2405_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2405_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelSubgroupEvaluationResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id does not match deterministic request identity")
        if self.provenance.module_id != M2405_MODULE_ID:
            raise ValueError("provenance module id must identify M24-05")
        if self.request.upstream_result.digest not in self.provenance.input_digests:
            raise ValueError("provenance must include the upstream result digest")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("subgroup finding ids must be unique")
        if self.status is EvaluationStatus.EVALUATED:
            if (
                self.report is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("evaluated result requires a supported subgroup report")
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
    "M2405_CONTRACT_VERSION",
    "M2405_DOSSIER_SHA256",
    "M2405_DOSSIER_SLICE",
    "M2405_EVIDENCE_CLAIM",
    "M2405_GATE",
    "M2405_M2404_INPUT_MEDIA_TYPE",
    "M2405_MAX_CANONICAL_REQUEST_BYTES",
    "M2405_MAX_CANONICAL_RESULT_BYTES",
    "M2405_MAX_EVIDENCE",
    "M2405_MAX_FINDINGS",
    "M2405_MAX_METRICS",
    "M2405_MODULE_ID",
    "M2405_OPERATION",
    "M2405_OUTPUT_MEDIA_TYPE",
    "M2405_OWNER",
    "M2405_PARENT",
    "M2405_PROVISIONAL_ABI",
    "M2405_SAFETY_CLASS",
    "BiomarkerPanelSubgroupEvaluationResult",
    "CalibrationSummary",
    "CoverageStatus",
    "CoverageSummary",
    "EquityStatus",
    "EvaluateBiomarkerPanelSubgroupEquityRequest",
    "EvaluationConfiguration",
    "EvaluationStatus",
    "SubgroupDimension",
    "SubgroupEvaluationReport",
    "SubgroupFinding",
    "SubgroupFindingCode",
    "SubgroupPerformance",
]
