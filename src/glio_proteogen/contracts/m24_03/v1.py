"""Provisional M24-03 internal benchmark and ablation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m24_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 8404-8444.
M2403_MODULE_ID: Final = "GLIO-PROTEOGEN-M24-03"
M2403_OPERATION: Final = "run_biomarker_panel_internal_benchmark"
M2403_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2403_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-03+json"
M2403_M2402_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m24-02+json"
M2403_PARENT: Final = "biomarker panel"
M2403_OWNER: Final = "Computational biology"
M2403_SAFETY_CLASS: Final = "S3"
M2403_GATE: Final = "G2"
M2403_PROVISIONAL_ABI: Final = True
M2403_MAX_BASELINES: Final = 32
M2403_MAX_ABLATIONS: Final = 256
M2403_MAX_COMPARISONS: Final = 128
M2403_MAX_METRICS: Final = 256
M2403_MAX_EVIDENCE: Final = 64
M2403_MAX_FINDINGS: Final = 64
M2403_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2403_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2403_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2403_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:8404-8444"
M2403_EVIDENCE_CLAIM: Final = (
    "Caller-declared M24-03 locked split, baseline, ablation and compute-matched evidence; "
    "issuer authority is not authenticated."
)
_M2403_SCORE_TOLERANCE: Final = 1e-12
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class ValidationStatus(StrEnum):
    PASS = "pass"  # noqa: S105
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


class BaselineKind(StrEnum):
    SIMPLE = "simple"
    MATURE = "mature"


class BenchmarkStatus(StrEnum):
    COMPLETED = "completed"
    ABSTAINED = "abstained"


class BenchmarkFindingCode(StrEnum):
    SPLIT_LEAKAGE = "split_leakage"
    BASELINE_FAILURE = "baseline_failure"
    ABLATION_FAILURE = "ablation_failure"
    COMPUTE_MISMATCH = "compute_mismatch"
    UNSUPPORTED_INPUT = "unsupported_input"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class LockedSplit(FrozenModel):
    split_id: Identifier
    version: SemanticVersion
    train_examples: int = Field(ge=1)
    validation_examples: int = Field(ge=1)
    test_examples: int = Field(ge=1)
    random_seed: int = Field(ge=0)
    nested_validation: Literal[True] = True
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2403_MAX_EVIDENCE)


class BenchmarkMetric(FrozenModel):
    metric_id: Identifier
    metric_name: NonEmptyStr
    baseline_value: FiniteFloat
    candidate_value: FiniteFloat
    tolerance: FiniteFloat = Field(ge=0.0)
    lower_is_better: bool = False
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def status_matches_tolerance(self) -> BenchmarkMetric:
        if self.status is ValidationStatus.NOT_EVALUABLE:
            return self
        difference = self.candidate_value - self.baseline_value
        within_tolerance = (
            difference <= self.tolerance
            if not self.lower_is_better
            else difference >= -self.tolerance
        )
        if self.status is ValidationStatus.PASS and not within_tolerance:
            raise ValueError("passing metric must satisfy its declared tolerance")
        if self.status is ValidationStatus.FAIL and within_tolerance:
            raise ValueError("failing metric must exceed its declared tolerance")
        return self


class BaselineRun(FrozenModel):
    run_id: Identifier
    kind: BaselineKind
    model_name: NonEmptyStr
    compute_units: FiniteFloat = Field(ge=0.0)
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2403_MAX_METRICS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def metric_ids_are_unique(self) -> BaselineRun:
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("baseline metric ids must be unique")
        return self


class ComponentAblation(FrozenModel):
    ablation_id: Identifier
    component: NonEmptyStr
    with_component_score: FiniteFloat
    without_component_score: FiniteFloat
    score_delta: FiniteFloat
    compute_units: FiniteFloat = Field(ge=0.0)
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def score_delta_is_canonical(self) -> ComponentAblation:
        expected = self.with_component_score - self.without_component_score
        if abs(self.score_delta - expected) > _M2403_SCORE_TOLERANCE:
            raise ValueError("ablation score delta must equal with-minus-without score")
        return self


class ComputeMatchedComparison(FrozenModel):
    comparison_id: Identifier
    reference_run_id: Identifier
    candidate_run_id: Identifier
    reference_compute_units: FiniteFloat = Field(ge=0.0)
    candidate_compute_units: FiniteFloat = Field(ge=0.0)
    compute_tolerance: FiniteFloat = Field(ge=0.0)
    reference_score: FiniteFloat
    candidate_score: FiniteFloat
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def compute_is_matched(self) -> ComputeMatchedComparison:
        if (
            abs(self.reference_compute_units - self.candidate_compute_units)
            > self.compute_tolerance
        ):
            raise ValueError("compute-matched comparison exceeds declared tolerance")
        return self


class BenchmarkDossier(FrozenModel):
    dossier_id: Identifier
    version: SemanticVersion
    split: LockedSplit
    baselines: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2403_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2403_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2403_MAX_COMPARISONS
    )
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2403_MAX_METRICS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2403_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dossier_is_closed(self) -> BenchmarkDossier:
        baseline_ids = tuple(item.run_id for item in self.baselines)
        ablation_ids = tuple(item.ablation_id for item in self.ablations)
        comparison_ids = tuple(item.comparison_id for item in self.comparisons)
        metric_ids = tuple(item.metric_id for item in self.metrics)
        nested_metric_ids = tuple(
            metric.metric_id for baseline in self.baselines for metric in baseline.metrics
        )
        ids = baseline_ids + ablation_ids + comparison_ids + metric_ids
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark dossier ids must be unique")
        if len(nested_metric_ids) != len(set(nested_metric_ids)):
            raise ValueError("nested baseline metric ids must be unique")
        if set(metric_ids) & set(nested_metric_ids):
            raise ValueError(
                "dossier metric ids must be unique across baseline and dossier metrics"
            )
        if {item.kind for item in self.baselines} != {BaselineKind.SIMPLE, BaselineKind.MATURE}:
            raise ValueError("benchmark dossier must include simple and mature baselines")
        if any(
            item.reference_run_id not in baseline_ids or item.candidate_run_id not in baseline_ids
            for item in self.comparisons
        ):
            raise ValueError("compute comparisons must reference declared baseline runs")
        if any(item.reference_run_id == item.candidate_run_id for item in self.comparisons):
            raise ValueError("compute comparisons require distinct baseline runs")
        return self


class BenchmarkFinding(FrozenModel):
    finding_id: Identifier
    code: BenchmarkFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2403_MAX_EVIDENCE)


class RunBiomarkerPanelInternalBenchmarkRequest(FrozenModel):
    operation: Literal["run_biomarker_panel_internal_benchmark"] = M2403_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2403_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    split: LockedSplit
    baseline_runs: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2403_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2403_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2403_MAX_COMPARISONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2403_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> RunBiomarkerPanelInternalBenchmarkRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        if self.upstream_result.media_type != M2403_M2402_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M24-02 synthetic truth result")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        upstream_key = (
            self.upstream_result.artifact_id,
            self.upstream_result.version,
            self.upstream_result.digest,
            self.upstream_result.media_type,
        )
        if sum(item == upstream_key for item in source_keys) != 1:
            raise ValueError("source artifacts must include exactly one declared M24-02 result")
        return self


class BiomarkerPanelInternalBenchmarkResult(FrozenModel):
    output_type: Literal["biomarker_panel_internal_benchmark"] = (
        "biomarker_panel_internal_benchmark"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2403_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RunBiomarkerPanelInternalBenchmarkRequest
    status: BenchmarkStatus
    dossier: BenchmarkDossier | None = None
    findings: tuple[BenchmarkFinding, ...] = Field(default=(), max_length=M2403_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["biomarker panel"] = M2403_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2403_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> BiomarkerPanelInternalBenchmarkResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result identifier must be derived from request digest")
        if self.status is BenchmarkStatus.COMPLETED:
            if (
                self.dossier is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("completed result requires a supported benchmark dossier")
        elif (
            self.dossier is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no dossier and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2403_CONTRACT_VERSION",
    "M2403_DOSSIER_SHA256",
    "M2403_DOSSIER_SLICE",
    "M2403_EVIDENCE_CLAIM",
    "M2403_GATE",
    "M2403_M2402_INPUT_MEDIA_TYPE",
    "M2403_MAX_ABLATIONS",
    "M2403_MAX_BASELINES",
    "M2403_MAX_CANONICAL_REQUEST_BYTES",
    "M2403_MAX_CANONICAL_RESULT_BYTES",
    "M2403_MAX_COMPARISONS",
    "M2403_MAX_EVIDENCE",
    "M2403_MAX_FINDINGS",
    "M2403_MAX_METRICS",
    "M2403_MODULE_ID",
    "M2403_OPERATION",
    "M2403_OUTPUT_MEDIA_TYPE",
    "M2403_OWNER",
    "M2403_PARENT",
    "M2403_PROVISIONAL_ABI",
    "M2403_SAFETY_CLASS",
    "BaselineKind",
    "BaselineRun",
    "BenchmarkDossier",
    "BenchmarkFinding",
    "BenchmarkFindingCode",
    "BenchmarkMetric",
    "BenchmarkStatus",
    "BiomarkerPanelInternalBenchmarkResult",
    "ComponentAblation",
    "ComputeMatchedComparison",
    "FiniteFloat",
    "LockedSplit",
    "RunBiomarkerPanelInternalBenchmarkRequest",
    "ValidationStatus",
]
