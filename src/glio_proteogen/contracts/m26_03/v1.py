"""Provisional M26-03 reproducible pipeline orchestrator contracts.

M26-03 owns workflow DAGs, deterministic execution, retries, checkpoints,
resource declarations, containers, and environment capture. The ABI is
inferred from dossier lines 9124-9164 and remains provisional pending ML
engineering confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import AwareDatetime, Field, model_validator

from glio_proteogen.contracts.m26_03.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 9124-9164.
M2603_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-03"
M2603_OPERATION: Final = "execute_protein_subtype_reproducible_workflow"
M2603_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2603_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-03+json"
M2603_PARENT: Final = "protein subtype"
M2603_OWNER: Final = "ML engineering"
M2603_SAFETY_CLASS: Final = "S3"
M2603_GATE: Final = "G1"
M2603_PROVISIONAL_ABI: Final = True
M2603_MAX_STEPS: Final = 256
M2603_MAX_ATTEMPTS: Final = 1024
M2603_MAX_ARTIFACTS: Final = 128
M2603_MAX_EVIDENCE: Final = 64
M2603_MAX_FINDINGS: Final = 64
M2603_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2603_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2603_EVIDENCE_CLAIM: Final = (
    "Caller-declared M26-03 workflow, deterministic execution, retry, checkpoint, "
    "environment and reproducibility material; issuer authority is not authenticated."
)


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABSTAINED = "abstained"


class ExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    ABSTAINED = "abstained"


class PipelineFindingCode(StrEnum):
    NONDETERMINISTIC_STEP = "nondeterministic_step"
    MISSING_CHECKPOINT = "missing_checkpoint"
    RETRY_EXHAUSTED = "retry_exhausted"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    RECOVERY_FAILURE = "recovery_failure"
    QUARANTINED_INPUT = "quarantined_input"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class WorkflowStep(FrozenModel):
    """Deterministic, container-pinned workflow DAG node."""

    step_id: Identifier
    name: NonEmptyStr
    version: SemanticVersion
    dependencies: tuple[Identifier, ...] = Field(default=(), max_length=M2603_MAX_STEPS)
    container_digest: Sha256Digest
    resource_class: NonEmptyStr
    deterministic: Literal[True] = True
    checkpoint_required: Literal[True] = True
    max_retries: int = Field(ge=0, le=32)
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)


class WorkflowDefinition(FrozenModel):
    """Locked workflow graph with explicit deterministic execution policy."""

    workflow_id: Identifier
    version: SemanticVersion
    steps: tuple[WorkflowStep, ...] = Field(min_length=1, max_length=M2603_MAX_STEPS)
    entry_step_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M2603_MAX_STEPS)
    output_step_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M2603_MAX_STEPS)
    workflow_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)

    @model_validator(mode="after")
    def workflow_is_closed(self) -> WorkflowDefinition:
        step_ids = tuple(item.step_id for item in self.steps)
        known = set(step_ids)
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("workflow step ids must be unique")
        if any(step_id not in known for step_id in (*self.entry_step_ids, *self.output_step_ids)):
            raise ValueError("workflow entry/output references an unknown step")
        if any(
            dependency not in known or dependency == step.step_id
            for step in self.steps
            for dependency in step.dependencies
        ):
            raise ValueError("workflow dependency references an unknown or self step")
        if not any(step.deterministic and step.checkpoint_required for step in self.steps):
            raise ValueError("workflow must declare deterministic checkpointed steps")
        return self


class EnvironmentCapture(FrozenModel):
    """Pinned runtime environment required for deterministic replay."""

    environment_id: Identifier
    version: SemanticVersion
    container_runtime: NonEmptyStr
    dependency_lock_digest: Sha256Digest
    operating_system: NonEmptyStr
    architecture: NonEmptyStr
    environment_digest: Sha256Digest
    reproducible: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)


class ExecutionAttempt(FrozenModel):
    """One step attempt with retry and checkpoint state."""

    attempt_id: Identifier
    step_id: Identifier
    retry_index: int = Field(ge=0, le=32)
    status: StepStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    output_digest: Sha256Digest | None = None
    checkpoint_digest: Sha256Digest | None = None
    failure_reason: NonEmptyStr | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)

    @model_validator(mode="after")
    def attempt_state_is_consistent(self) -> ExecutionAttempt:
        if self.status is StepStatus.COMPLETED and (
            self.finished_at is None or self.output_digest is None or self.checkpoint_digest is None
        ):
            raise ValueError("completed attempts require finish, output, and checkpoint digests")
        if self.status is StepStatus.FAILED and self.failure_reason is None:
            raise ValueError("failed attempts require a failure reason")
        return self


class ExecutionRecord(FrozenModel):
    """Auditable execution record for a locked workflow and environment."""

    execution_id: Identifier
    workflow: WorkflowDefinition
    environment: EnvironmentCapture
    attempts: tuple[ExecutionAttempt, ...] = Field(min_length=1, max_length=M2603_MAX_ATTEMPTS)
    execution_status: ExecutionStatus
    execution_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)

    @model_validator(mode="after")
    def record_is_closed(self) -> ExecutionRecord:
        attempt_ids = tuple(item.attempt_id for item in self.attempts)
        known_steps = {item.step_id for item in self.workflow.steps}
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("execution attempt ids must be unique")
        if any(item.step_id not in known_steps for item in self.attempts):
            raise ValueError("execution attempt references an unknown workflow step")
        if self.execution_status is ExecutionStatus.COMPLETED and any(
            item.status is not StepStatus.COMPLETED for item in self.attempts
        ):
            raise ValueError("completed execution requires completed attempts")
        return self


class ReproducibleResultPackage(FrozenModel):
    """Signed package containing exact replay manifests and result material."""

    package_id: Identifier
    version: SemanticVersion
    execution_id: Identifier
    result_artifact: ArtifactReference
    manifest_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2603_MAX_ARTIFACTS
    )
    replay_command: NonEmptyStr
    package_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)


class PipelineFinding(FrozenModel):
    finding_id: Identifier
    code: PipelineFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)


class ExecuteProteinSubtypeWorkflowRequest(FrozenModel):
    """Provisional request for deterministic workflow execution and packaging."""

    operation: Literal["execute_protein_subtype_reproducible_workflow"] = M2603_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2603_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    workflow: WorkflowDefinition
    environment: EnvironmentCapture
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2603_MAX_ARTIFACTS
    )
    supersedes_result_digest: Sha256Digest | None = None


class ProteinSubtypeExecutionResult(FrozenModel):
    """Execution record and reproducible result package with safe abstention."""

    output_type: Literal["protein_subtype_execution"] = "protein_subtype_execution"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2603_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ExecuteProteinSubtypeWorkflowRequest
    status: ExecutionStatus
    execution_record: ExecutionRecord | None = None
    reproducible_package: ReproducibleResultPackage | None = None
    findings: tuple[PipelineFinding, ...] = Field(default=(), max_length=M2603_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2603_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2603_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeExecutionResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        if self.status is ExecutionStatus.COMPLETED:
            if (
                self.execution_record is None
                or self.reproducible_package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("completed result requires supported execution and package")
        elif (
            self.execution_record is not None
            or self.reproducible_package is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no execution or package and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2603_CONTRACT_VERSION",
    "M2603_EVIDENCE_CLAIM",
    "M2603_GATE",
    "M2603_MAX_ARTIFACTS",
    "M2603_MAX_ATTEMPTS",
    "M2603_MAX_CANONICAL_REQUEST_BYTES",
    "M2603_MAX_CANONICAL_RESULT_BYTES",
    "M2603_MAX_EVIDENCE",
    "M2603_MAX_FINDINGS",
    "M2603_MAX_STEPS",
    "M2603_MODULE_ID",
    "M2603_OPERATION",
    "M2603_OUTPUT_MEDIA_TYPE",
    "M2603_OWNER",
    "M2603_PARENT",
    "M2603_PROVISIONAL_ABI",
    "M2603_SAFETY_CLASS",
    "EnvironmentCapture",
    "ExecuteProteinSubtypeWorkflowRequest",
    "ExecutionAttempt",
    "ExecutionRecord",
    "ExecutionStatus",
    "PipelineFinding",
    "PipelineFindingCode",
    "ProteinSubtypeExecutionResult",
    "ReproducibleResultPackage",
    "StepStatus",
    "WorkflowDefinition",
    "WorkflowStep",
]
