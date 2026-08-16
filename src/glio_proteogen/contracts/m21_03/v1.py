"""Provisional M21-03 internal benchmark and ablation contracts.

M21-03 owns nested validation, locked splits, baselines, component ablation,
and compute-matched comparisons beneath Reference material/spike-ins. The ABI
is provisional; unsupported or unresolved inputs abstain safely.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m21_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from the permitted dossier slice.
M2103_MODULE_ID: Final = "GLIO-PROTEOGEN-M21-03"
M2103_OPERATION: Final = "run_complex_activity_internal_benchmark"
M2103_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2103_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-03+json"
M2103_M2102_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m21-02+json"
M2103_PARENT: Final = "complex activity"
M2103_OWNER: Final = "Data engineering"
M2103_SAFETY_CLASS: Final = "S3"
M2103_GATE: Final = "G2"
M2103_PROVISIONAL_ABI: Final = True
M2103_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2103_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:7324-7364"
M2103_MAX_BASELINES: Final = 32
M2103_MAX_ABLATIONS: Final = 256
M2103_MAX_COMPARISONS: Final = 128
M2103_MAX_METRICS: Final = 256
M2103_MAX_EVIDENCE: Final = 64
M2103_MAX_FINDINGS: Final = 64
M2103_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2103_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_M2103_SCORE_TOLERANCE: Final = 1e-12
M2103_EVIDENCE_CLAIM: Final = (
    "Caller-declared M21-03 benchmark, split, baseline, ablation and comparison "
    "material; issuer authority is not authenticated."
)


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2103_MAX_EVIDENCE)


class BenchmarkMetric(FrozenModel):
    metric_id: Identifier
    metric_name: NonEmptyStr
    baseline_value: float
    candidate_value: float
    tolerance: float = Field(ge=0.0)
    lower_is_better: bool = False
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2103_MAX_EVIDENCE)


class BaselineRun(FrozenModel):
    run_id: Identifier
    kind: BaselineKind
    model_name: NonEmptyStr
    compute_units: float = Field(ge=0.0)
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2103_MAX_METRICS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2103_MAX_EVIDENCE)

    @model_validator(mode="after")
    def metrics_are_unique(self) -> BaselineRun:
        metric_ids = tuple(item.metric_id for item in self.metrics)
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("baseline metric ids must be unique")
        return self


class ComponentAblation(FrozenModel):
    ablation_id: Identifier
    component: NonEmptyStr
    with_component_score: float
    without_component_score: float
    score_delta: float
    compute_units: float = Field(ge=0.0)
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2103_MAX_EVIDENCE)

    @model_validator(mode="after")
    def score_delta_is_canonical(self) -> ComponentAblation:
        expected = self.with_component_score - self.without_component_score
        if abs(self.score_delta - expected) > _M2103_SCORE_TOLERANCE:
            raise ValueError("ablation score delta must equal with-minus-without score")
        return self


class ComputeMatchedComparison(FrozenModel):
    comparison_id: Identifier
    reference_run_id: Identifier
    candidate_run_id: Identifier
    reference_compute_units: float = Field(ge=0.0)
    candidate_compute_units: float = Field(ge=0.0)
    compute_tolerance: float = Field(ge=0.0)
    reference_score: float
    candidate_score: float
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2103_MAX_EVIDENCE)

    @model_validator(mode="after")
    def compute_is_matched(self) -> ComputeMatchedComparison:
        if (
            abs(self.reference_compute_units - self.candidate_compute_units)
            > self.compute_tolerance
        ):
            raise ValueError("compute-matched comparison exceeds declared tolerance")
        return self


class BenchmarkDossier(FrozenModel):
    """Locked benchmark, ablation, and compute-matched evidence dossier."""

    dossier_id: Identifier
    version: SemanticVersion
    split: LockedSplit
    baselines: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2103_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2103_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2103_MAX_COMPARISONS
    )
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2103_MAX_METRICS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2103_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dossier_is_closed(self) -> BenchmarkDossier:
        run_ids = tuple(item.run_id for item in self.baselines)
        ablation_ids = tuple(item.ablation_id for item in self.ablations)
        comparison_ids = tuple(item.comparison_id for item in self.comparisons)
        metric_ids = tuple(item.metric_id for item in self.metrics)
        for values, label in (
            (run_ids, "baseline run"),
            (ablation_ids, "ablation"),
            (comparison_ids, "comparison"),
            (metric_ids, "metric"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} ids must be unique")
        if not any(item.kind is BaselineKind.SIMPLE for item in self.baselines):
            raise ValueError("benchmark dossier requires a simple baseline")
        if not any(item.kind is BaselineKind.MATURE for item in self.baselines):
            raise ValueError("benchmark dossier requires a mature baseline")
        baseline_id_set = set(run_ids)
        if any(
            item.reference_run_id not in baseline_id_set
            or item.candidate_run_id not in baseline_id_set
            for item in self.comparisons
        ):
            raise ValueError("benchmark comparison must reference known baseline runs")
        return self


class BenchmarkFinding(FrozenModel):
    finding_id: Identifier
    code: BenchmarkFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2103_MAX_EVIDENCE)


class RunComplexActivityInternalBenchmarkRequest(FrozenModel):
    """Provisional request bound to the M21-02 synthetic truth corpus."""

    operation: Literal["run_complex_activity_internal_benchmark"] = M2103_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2103_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    split: LockedSplit
    baseline_runs: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2103_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2103_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2103_MAX_COMPARISONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2103_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> RunComplexActivityInternalBenchmarkRequest:
        if self.upstream_result.media_type != M2103_M2102_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M21-02 synthetic truth result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must equal request id")
        source_keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("request source artifacts must be unique")
        if (
            self.upstream_result.artifact_id,
            self.upstream_result.version,
            self.upstream_result.digest,
            self.upstream_result.media_type,
        ) not in set(source_keys):
            raise ValueError("request source artifacts must include the M21-02 result")
        baseline_ids = tuple(item.run_id for item in self.baseline_runs)
        if len(baseline_ids) != len(set(baseline_ids)):
            raise ValueError("request baseline run ids must be unique")
        if not any(item.kind is BaselineKind.SIMPLE for item in self.baseline_runs):
            raise ValueError("request requires a simple baseline")
        if not any(item.kind is BaselineKind.MATURE for item in self.baseline_runs):
            raise ValueError("request requires a mature baseline")
        ablation_ids = tuple(item.ablation_id for item in self.ablations)
        comparison_ids = tuple(item.comparison_id for item in self.comparisons)
        if len(ablation_ids) != len(set(ablation_ids)):
            raise ValueError("request ablation ids must be unique")
        if len(comparison_ids) != len(set(comparison_ids)):
            raise ValueError("request comparison ids must be unique")
        baseline_id_set = set(baseline_ids)
        if any(
            item.reference_run_id not in baseline_id_set
            or item.candidate_run_id not in baseline_id_set
            for item in self.comparisons
        ):
            raise ValueError("request comparison must reference known baseline runs")
        return self


class ComplexActivityInternalBenchmarkResult(FrozenModel):
    """Internal benchmark dossier with explicit support and safe abstention."""

    output_type: Literal["complex_activity_internal_benchmark"] = (
        "complex_activity_internal_benchmark"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2103_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RunComplexActivityInternalBenchmarkRequest
    status: BenchmarkStatus
    dossier: BenchmarkDossier | None = None
    findings: tuple[BenchmarkFinding, ...] = Field(default=(), max_length=M2103_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2103_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2103_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityInternalBenchmarkResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.result_id != result_identifier(self.request):
            raise ValueError("result id must be deterministically bound to the request")
        if self.status is BenchmarkStatus.COMPLETED:
            if (
                self.dossier is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("completed result requires a supported benchmark dossier")
            if self.dossier.split != self.request.split:
                raise ValueError("completed dossier split must equal the request split")
            if self.dossier.baselines != self.request.baseline_runs:
                raise ValueError("completed dossier baselines must equal the request baselines")
            if self.dossier.ablations != self.request.ablations:
                raise ValueError("completed dossier ablations must equal the request ablations")
            if self.dossier.comparisons != self.request.comparisons:
                raise ValueError("completed dossier comparisons must equal the request comparisons")
        elif (
            self.dossier is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no dossier and safe status")
        if len(self.findings) != len({finding.finding_id for finding in self.findings}):
            raise ValueError("result finding ids must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2103_CONTRACT_VERSION",
    "M2103_DOSSIER_SHA256",
    "M2103_DOSSIER_SLICE",
    "M2103_EVIDENCE_CLAIM",
    "M2103_GATE",
    "M2103_M2102_INPUT_MEDIA_TYPE",
    "M2103_MAX_ABLATIONS",
    "M2103_MAX_BASELINES",
    "M2103_MAX_CANONICAL_REQUEST_BYTES",
    "M2103_MAX_CANONICAL_RESULT_BYTES",
    "M2103_MAX_COMPARISONS",
    "M2103_MAX_EVIDENCE",
    "M2103_MAX_FINDINGS",
    "M2103_MAX_METRICS",
    "M2103_MODULE_ID",
    "M2103_OPERATION",
    "M2103_OUTPUT_MEDIA_TYPE",
    "M2103_OWNER",
    "M2103_PARENT",
    "M2103_PROVISIONAL_ABI",
    "M2103_SAFETY_CLASS",
    "BaselineKind",
    "BaselineRun",
    "BenchmarkDossier",
    "BenchmarkFinding",
    "BenchmarkFindingCode",
    "BenchmarkMetric",
    "BenchmarkStatus",
    "ComplexActivityInternalBenchmarkResult",
    "ComponentAblation",
    "ComputeMatchedComparison",
    "LockedSplit",
    "RunComplexActivityInternalBenchmarkRequest",
    "ValidationStatus",
]
