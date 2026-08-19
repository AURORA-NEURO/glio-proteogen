"""Provisional M25-03 internal benchmark and ablation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m25_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 8764-8804.
M2503_MODULE_ID: Final = "GLIO-PROTEOGEN-M25-03"
M2503_OPERATION: Final = "run_proteotype_internal_benchmark"
M2503_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2503_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-03+json"
M2503_M2502_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m25-02+json"
M2503_PARENT: Final = "proteotype"
M2503_OWNER: Final = "Bioinformatics"
M2503_SAFETY_CLASS: Final = "S3"
M2503_GATE: Final = "G2"
M2503_PROVISIONAL_ABI: Final = True
M2503_MAX_BASELINES: Final = 32
M2503_MAX_ABLATIONS: Final = 256
M2503_MAX_COMPARISONS: Final = 128
M2503_MAX_METRICS: Final = 256
M2503_MAX_EVIDENCE: Final = 64
M2503_MAX_FINDINGS: Final = 64
M2503_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2503_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_M2503_SCORE_TOLERANCE: Final = 1e-12


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2503_MAX_EVIDENCE)


class BenchmarkMetric(FrozenModel):
    metric_id: Identifier
    metric_name: NonEmptyStr
    baseline_value: float
    candidate_value: float
    tolerance: float = Field(ge=0.0)
    lower_is_better: bool = False
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2503_MAX_EVIDENCE)

    @model_validator(mode="after")
    def status_matches_directional_tolerance(self) -> BenchmarkMetric:
        within_tolerance = (
            self.candidate_value <= self.baseline_value + self.tolerance
            if self.lower_is_better
            else self.candidate_value >= self.baseline_value - self.tolerance
        )
        if self.status is ValidationStatus.PASS and not within_tolerance:
            raise ValueError("passing benchmark metric must satisfy declared directional tolerance")
        return self


class BaselineRun(FrozenModel):
    run_id: Identifier
    kind: BaselineKind
    model_name: NonEmptyStr
    compute_units: float = Field(ge=0.0)
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2503_MAX_METRICS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2503_MAX_EVIDENCE)


class ComponentAblation(FrozenModel):
    ablation_id: Identifier
    component: NonEmptyStr
    with_component_score: float
    without_component_score: float
    score_delta: float
    compute_units: float = Field(ge=0.0)
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2503_MAX_EVIDENCE)

    @model_validator(mode="after")
    def score_delta_is_canonical(self) -> ComponentAblation:
        expected = self.with_component_score - self.without_component_score
        if abs(self.score_delta - expected) > _M2503_SCORE_TOLERANCE:
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2503_MAX_EVIDENCE)

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
    baselines: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2503_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2503_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2503_MAX_COMPARISONS
    )
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2503_MAX_METRICS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2503_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dossier_is_closed(self) -> BenchmarkDossier:
        ids = (
            tuple(item.run_id for item in self.baselines)
            + tuple(item.ablation_id for item in self.ablations)
            + tuple(item.comparison_id for item in self.comparisons)
            + tuple(item.metric_id for item in self.metrics)
        )
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark dossier ids must be unique")
        baseline_ids = {item.run_id for item in self.baselines}
        for comparison in self.comparisons:
            if comparison.reference_run_id not in baseline_ids:
                raise ValueError("comparison reference run must be a declared baseline")
            if comparison.candidate_run_id not in baseline_ids:
                raise ValueError("comparison candidate run must be a declared baseline")
        return self


class BenchmarkFinding(FrozenModel):
    finding_id: Identifier
    code: BenchmarkFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2503_MAX_EVIDENCE)


class RunProteotypeInternalBenchmarkRequest(FrozenModel):
    operation: Literal["run_proteotype_internal_benchmark"] = M2503_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2503_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    split: LockedSplit
    baseline_runs: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2503_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2503_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2503_MAX_COMPARISONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2503_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> RunProteotypeInternalBenchmarkRequest:
        if self.upstream_result.media_type != M2503_M2502_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M25-02 synthetic truth result")
        if self.context.request_id != self.request_id:
            raise ValueError("execution context request id must match request id")
        source_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source artifact identifiers must be unique")
        if self.upstream_result.artifact_id not in set(source_ids):
            raise ValueError("source artifacts must include the declared upstream result")
        baseline_ids = tuple(item.run_id for item in self.baseline_runs)
        if len(baseline_ids) != len(set(baseline_ids)):
            raise ValueError("baseline run identifiers must be unique")
        known_baselines = set(baseline_ids)
        for comparison in self.comparisons:
            if comparison.reference_run_id not in known_baselines:
                raise ValueError("comparison reference run must be a declared baseline")
            if comparison.candidate_run_id not in known_baselines:
                raise ValueError("comparison candidate run must be a declared baseline")
        ablation_ids = tuple(item.ablation_id for item in self.ablations)
        if len(ablation_ids) != len(set(ablation_ids)):
            raise ValueError("ablation identifiers must be unique")
        return self


class ProteotypeInternalBenchmarkResult(FrozenModel):
    output_type: Literal["proteotype_internal_benchmark"] = "proteotype_internal_benchmark"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2503_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RunProteotypeInternalBenchmarkRequest
    status: BenchmarkStatus
    dossier: BenchmarkDossier | None = None
    findings: tuple[BenchmarkFinding, ...] = Field(default=(), max_length=M2503_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["proteotype"] = M2503_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2503_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteotypeInternalBenchmarkResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.request.context.request_id != self.request.request_id:
            raise ValueError("result request context id must match request id")
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
        if self.result_id != result_identifier(self.request, self.status.value):
            raise ValueError("result identifier does not bind request and status")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("finding identifiers must be unique")
        return self


__all__ = [
    "M2503_CONTRACT_VERSION",
    "M2503_GATE",
    "M2503_M2502_INPUT_MEDIA_TYPE",
    "M2503_MAX_ABLATIONS",
    "M2503_MAX_BASELINES",
    "M2503_MAX_CANONICAL_REQUEST_BYTES",
    "M2503_MAX_CANONICAL_RESULT_BYTES",
    "M2503_MAX_COMPARISONS",
    "M2503_MAX_EVIDENCE",
    "M2503_MAX_FINDINGS",
    "M2503_MAX_METRICS",
    "M2503_MODULE_ID",
    "M2503_OPERATION",
    "M2503_OUTPUT_MEDIA_TYPE",
    "M2503_OWNER",
    "M2503_PARENT",
    "M2503_PROVISIONAL_ABI",
    "M2503_SAFETY_CLASS",
    "BaselineKind",
    "BaselineRun",
    "BenchmarkDossier",
    "BenchmarkFinding",
    "BenchmarkFindingCode",
    "BenchmarkMetric",
    "BenchmarkStatus",
    "ComponentAblation",
    "ComputeMatchedComparison",
    "LockedSplit",
    "ProteotypeInternalBenchmarkResult",
    "RunProteotypeInternalBenchmarkRequest",
    "ValidationStatus",
]
