"""Provisional M22-03 internal benchmark and ablation contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m22_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 7684-7724.
M2203_MODULE_ID: Final = "GLIO-PROTEOGEN-M22-03"
M2203_OPERATION: Final = "run_protein_rna_discordance_internal_benchmark"
M2203_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2203_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-03+json"
M2203_M2202_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m22-02+json"
M2203_PARENT: Final = "protein-RNA discordance"
M2203_OWNER: Final = "Platform engineering"
M2203_SAFETY_CLASS: Final = "S3"
M2203_GATE: Final = "G2"
M2203_PROVISIONAL_ABI: Final = True
M2203_MAX_BASELINES: Final = 32
M2203_MAX_ABLATIONS: Final = 256
M2203_MAX_COMPARISONS: Final = 128
M2203_MAX_METRICS: Final = 256
M2203_MAX_EVIDENCE: Final = 64
M2203_MAX_FINDINGS: Final = 64
M2203_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2203_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
_M2203_SCORE_TOLERANCE: Final = 1e-12


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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2203_MAX_EVIDENCE)


class BenchmarkMetric(FrozenModel):
    metric_id: Identifier
    metric_name: NonEmptyStr
    baseline_value: float
    candidate_value: float
    tolerance: float = Field(ge=0.0)
    lower_is_better: bool = False
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2203_MAX_EVIDENCE)


class BaselineRun(FrozenModel):
    run_id: Identifier
    kind: BaselineKind
    model_name: NonEmptyStr
    compute_units: float = Field(ge=0.0)
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2203_MAX_METRICS)
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2203_MAX_EVIDENCE)


class ComponentAblation(FrozenModel):
    ablation_id: Identifier
    component: NonEmptyStr
    with_component_score: float
    without_component_score: float
    score_delta: float
    compute_units: float = Field(ge=0.0)
    status: ValidationStatus
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2203_MAX_EVIDENCE)

    @model_validator(mode="after")
    def score_delta_is_canonical(self) -> ComponentAblation:
        expected = self.with_component_score - self.without_component_score
        if abs(self.score_delta - expected) > _M2203_SCORE_TOLERANCE:
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
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2203_MAX_EVIDENCE)

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
    baselines: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2203_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2203_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2203_MAX_COMPARISONS
    )
    metrics: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=M2203_MAX_METRICS)
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2203_MAX_EVIDENCE)

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
        return self


class BenchmarkFinding(FrozenModel):
    finding_id: Identifier
    code: BenchmarkFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2203_MAX_EVIDENCE)


class RunProteinRnaDiscordanceInternalBenchmarkRequest(FrozenModel):
    operation: Literal["run_protein_rna_discordance_internal_benchmark"] = M2203_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2203_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    split: LockedSplit
    baseline_runs: tuple[BaselineRun, ...] = Field(min_length=1, max_length=M2203_MAX_BASELINES)
    ablations: tuple[ComponentAblation, ...] = Field(min_length=1, max_length=M2203_MAX_ABLATIONS)
    comparisons: tuple[ComputeMatchedComparison, ...] = Field(
        min_length=1, max_length=M2203_MAX_COMPARISONS
    )
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2203_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> RunProteinRnaDiscordanceInternalBenchmarkRequest:
        if self.upstream_result.media_type != M2203_M2202_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M22-02 synthetic truth result")
        return self


class ProteinRnaDiscordanceInternalBenchmarkResult(FrozenModel):
    output_type: Literal["protein_rna_discordance_internal_benchmark"] = (
        "protein_rna_discordance_internal_benchmark"
    )
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2203_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: RunProteinRnaDiscordanceInternalBenchmarkRequest
    status: BenchmarkStatus
    dossier: BenchmarkDossier | None = None
    findings: tuple[BenchmarkFinding, ...] = Field(default=(), max_length=M2203_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein-RNA discordance"] = M2203_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2203_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinRnaDiscordanceInternalBenchmarkResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
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
    "M2203_CONTRACT_VERSION",
    "M2203_GATE",
    "M2203_M2202_INPUT_MEDIA_TYPE",
    "M2203_MAX_ABLATIONS",
    "M2203_MAX_BASELINES",
    "M2203_MAX_CANONICAL_REQUEST_BYTES",
    "M2203_MAX_CANONICAL_RESULT_BYTES",
    "M2203_MAX_COMPARISONS",
    "M2203_MAX_EVIDENCE",
    "M2203_MAX_FINDINGS",
    "M2203_MAX_METRICS",
    "M2203_MODULE_ID",
    "M2203_OPERATION",
    "M2203_OUTPUT_MEDIA_TYPE",
    "M2203_OWNER",
    "M2203_PARENT",
    "M2203_PROVISIONAL_ABI",
    "M2203_SAFETY_CLASS",
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
    "ProteinRnaDiscordanceInternalBenchmarkResult",
    "RunProteinRnaDiscordanceInternalBenchmarkRequest",
    "ValidationStatus",
]
