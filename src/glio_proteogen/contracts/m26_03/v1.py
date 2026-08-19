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
    result_identifier,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
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
M2603_DOSSIER_SHA256: Final = (
    "sha256:0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
)
M2603_DOSSIER_SLICE: Final = "GLIO-PROTEOGEN_240_Module_Dossier.md:9124-9164"
M2603_M2601_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-01+json"
M2603_M2602_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-02+json"
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
    def workflow_is_closed(self) -> WorkflowDefinition:  # noqa: PLR0912, PLR0915
        step_ids = tuple(item.step_id for item in self.steps)
        known = set(step_ids)
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("workflow step ids must be unique")
        if any(len(step.dependencies) != len(set(step.dependencies)) for step in self.steps):
            raise ValueError("workflow step dependencies must be unique")
        if any(step_id not in known for step_id in (*self.entry_step_ids, *self.output_step_ids)):
            raise ValueError("workflow entry/output references an unknown step")
        if any(
            dependency not in known or dependency == step.step_id
            for step in self.steps
            for dependency in step.dependencies
        ):
            raise ValueError("workflow dependency references an unknown or self step")
        if len(self.entry_step_ids) != len(set(self.entry_step_ids)):
            raise ValueError("workflow entry step ids must be unique")
        if len(self.output_step_ids) != len(set(self.output_step_ids)):
            raise ValueError("workflow output step ids must be unique")
        if set(self.entry_step_ids) & set(self.output_step_ids) and len(step_ids) > 1:
            raise ValueError("workflow entry and output steps must be distinct for multi-step DAGs")
        if not any(step.deterministic and step.checkpoint_required for step in self.steps):
            raise ValueError("workflow must declare deterministic checkpointed steps")

        dependencies = {step.step_id: set(step.dependencies) for step in self.steps}
        dependents: dict[str, set[str]] = {step_id: set() for step_id in known}
        for step_id, parents in dependencies.items():
            for parent in parents:
                dependents[parent].add(step_id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("workflow dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for parent in dependencies[step_id]:
                visit(parent)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in step_ids:
            visit(step_id)
        if any(dependencies[step_id] for step_id in self.entry_step_ids):
            raise ValueError("workflow entry steps cannot depend on upstream steps")
        if any(dependents[step_id] for step_id in self.output_step_ids):
            raise ValueError("workflow output steps must be terminal")

        reachable = set(self.entry_step_ids)
        while True:
            expanded = reachable | {
                step_id for step_id, parents in dependencies.items() if parents <= reachable
            }
            if expanded == reachable:
                break
            reachable = expanded
        if reachable != known:
            raise ValueError("workflow contains a step unreachable from its entries")

        can_reach_output = set(self.output_step_ids)
        while True:
            expanded = can_reach_output | {
                parent for parent, children in dependents.items() if children & can_reach_output
            }
            if expanded == can_reach_output:
                break
            can_reach_output = expanded
        if can_reach_output != known:
            raise ValueError("workflow contains a dead-end step outside its outputs")

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
        if self.status is StepStatus.COMPLETED and self.failure_reason is not None:
            raise ValueError("completed attempts cannot carry a failure reason")
        if self.status is StepStatus.FAILED and (
            self.failure_reason is None or self.finished_at is None
        ):
            raise ValueError("failed attempts require a failure reason and finish time")
        if self.status in {StepStatus.PENDING, StepStatus.RUNNING} and (
            self.finished_at is not None
            or self.output_digest is not None
            or self.checkpoint_digest is not None
            or self.failure_reason is not None
        ):
            raise ValueError("unfinished attempts cannot carry terminal fields")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("attempt finish time cannot precede start time")
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
        if (
            self.execution_status is ExecutionStatus.COMPLETED
            and {item.step_id for item in self.attempts if item.status is StepStatus.COMPLETED}
            != known_steps
        ):
            raise ValueError("completed execution requires every workflow step")
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


def _validate_completed_bindings(
    request: ExecuteProteinSubtypeWorkflowRequest,
    record: ExecutionRecord,
    package: ReproducibleResultPackage,
) -> None:
    if record.workflow != request.workflow or record.environment != request.environment:
        raise ValueError("execution record must bind the request workflow and environment")
    expected_execution_digest = sha256_digest(
        {
            "workflow": record.workflow,
            "environment": record.environment,
            "attempts": record.attempts,
        }
    )
    if record.execution_digest != expected_execution_digest:
        raise ValueError("execution record digest does not match its canonical contents")
    expected_execution_id = "execution." + expected_execution_digest.removeprefix("sha256:")
    if record.execution_id != expected_execution_id:
        raise ValueError("execution record id must bind its canonical digest")
    if package.execution_id != record.execution_id:
        raise ValueError("reproducible package must bind its execution record")
    if package.version != request.workflow.version:
        raise ValueError("reproducible package version must bind the workflow version")
    if package.package_id != "package." + record.execution_digest.removeprefix("sha256:"):
        raise ValueError("reproducible package id must bind its execution digest")
    if package.manifest_artifacts != request.source_artifacts:
        raise ValueError("reproducible package manifests must bind request artifacts")
    if (
        package.result_artifact.artifact_id
        != "m2603-result." + record.execution_id.removeprefix("execution.")
        or package.result_artifact.version != M2603_CONTRACT_VERSION
        or package.result_artifact.digest != record.execution_digest
        or package.result_artifact.media_type != M2603_OUTPUT_MEDIA_TYPE
    ):
        raise ValueError("reproducible package result artifact must bind execution")
    expected_package_digest = sha256_digest(
        {
            "execution_id": record.execution_id,
            "result": package.result_artifact,
            "manifest": request.source_artifacts,
        }
    )
    if package.package_digest != expected_package_digest:
        raise ValueError("reproducible package digest does not match its contents")


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

    @model_validator(mode="after")
    def request_is_bound(self) -> ExecuteProteinSubtypeWorkflowRequest:
        if self.context.request_id != self.request_id:
            raise ValueError("execution context must bind the request identifier")
        keys = tuple(
            (item.artifact_id, item.version, item.digest, item.media_type)
            for item in self.source_artifacts
        )
        if len(keys) != len(set(keys)):
            raise ValueError("source artifacts must be unique")
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("source artifact ids must be unique")
        digests = tuple(item.digest for item in self.source_artifacts)
        if len(digests) != len(set(digests)):
            raise ValueError("source artifact digests must be unique")
        media = {item.media_type for item in self.source_artifacts}
        if M2603_M2601_INPUT_MEDIA_TYPE not in media:
            raise ValueError("source artifacts must retain the M26-01 media boundary")
        if M2603_M2602_INPUT_MEDIA_TYPE not in media:
            raise ValueError("source artifacts must retain the M26-02 media boundary")
        return self


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
        if self.result_id != result_identifier(self.request):
            raise ValueError("result identifier must be derived from request digest")
        finding_ids = tuple(item.finding_id for item in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("pipeline finding ids must be unique")
        evidence_digests = tuple(item.reference.digest for item in self.evidence)
        if len(evidence_digests) != len(set(evidence_digests)):
            raise ValueError("pipeline result evidence must be unique")
        if self.status is ExecutionStatus.COMPLETED:
            if (
                self.execution_record is None
                or self.reproducible_package is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("completed result requires supported execution and package")
            _validate_completed_bindings(
                self.request, self.execution_record, self.reproducible_package
            )
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
    "M2603_DOSSIER_SHA256",
    "M2603_DOSSIER_SLICE",
    "M2603_EVIDENCE_CLAIM",
    "M2603_GATE",
    "M2603_M2601_INPUT_MEDIA_TYPE",
    "M2603_M2602_INPUT_MEDIA_TYPE",
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
