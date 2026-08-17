"""Provisional M27-03 reproducible pipeline orchestrator contracts.

The scaffold models workflow DAGs, containers, resources, deterministic
execution, retry, checkpoint, environment capture, and safe recovery without
claiming a finalized runtime ABI.
"""

# The two closure validators deliberately enumerate independent invariants.
# ruff: noqa: PLR0912,S101,PT018

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m27_03.canonical import (
    canonical_request_digest,
    execution_id_for_request_digest,
    package_id_for_request_digest,
    result_id_for_request_digest,
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

# PROVISIONAL ABI: inferred solely from dossier SHA
# 0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181,
# lines 9484-9524. Owner confirmation and implementation details remain
# pending.
M2703_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-03"
M2703_OPERATION: Final = "orchestrate_complex_activity_pipeline"
M2703_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2703_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-03+json"
M2703_M2702_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-02+json"
M2703_PARENT: Final = "complex activity"
M2703_OWNER: Final = "Quality engineering"
M2703_SAFETY_CLASS: Final = "S3"
M2703_GATE: Final = "G1"
M2703_PROVISIONAL_ABI: Final = True
M2703_MAX_NODES: Final = 256
M2703_MAX_EDGES: Final = 512
M2703_MAX_ATTEMPTS: Final = 16
M2703_MAX_ARTIFACTS: Final = 256
M2703_MAX_EVIDENCE: Final = 64
M2703_MAX_FINDINGS: Final = 64
M2703_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2703_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


class WorkflowNodeKind(StrEnum):
    TASK = "task"
    CONTAINER = "container"
    CHECKPOINT = "checkpoint"
    VALIDATION = "validation"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABSTAINED = "abstained"
    RECOVERED = "recovered"


class PipelineStatus(StrEnum):
    EXECUTED = "executed"
    ABSTAINED = "abstained"


class FindingCode(StrEnum):
    NODE_FAILED = "node_failed"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    NONDETERMINISTIC_OUTPUT = "nondeterministic_output"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class WorkflowNode(FrozenModel):
    node_id: Identifier
    kind: WorkflowNodeKind
    name: NonEmptyStr
    container_image: NonEmptyStr
    container_digest: Sha256Digest
    version: SemanticVersion
    cpu_millis: int = Field(ge=1)
    memory_bytes: int = Field(ge=1)
    deterministic: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2703_MAX_EVIDENCE)


class WorkflowEdge(FrozenModel):
    edge_id: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2703_MAX_EVIDENCE)

    @model_validator(mode="after")
    def endpoints_are_distinct(self) -> WorkflowEdge:
        if self.source_node_id == self.target_node_id:
            raise ValueError("workflow edge endpoints must be distinct")
        return self


class WorkflowDAG(FrozenModel):
    workflow_id: Identifier
    version: SemanticVersion
    nodes: tuple[WorkflowNode, ...] = Field(min_length=1, max_length=M2703_MAX_NODES)
    edges: tuple[WorkflowEdge, ...] = Field(default=(), max_length=M2703_MAX_EDGES)
    entry_node_id: Identifier
    exit_node_id: Identifier
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2703_MAX_EVIDENCE)

    @model_validator(mode="after")
    def dag_references_are_closed(self) -> WorkflowDAG:
        node_ids = tuple(node.node_id for node in self.nodes)
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("workflow node ids must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("workflow edge ids must be unique")
        node_set = set(node_ids)
        if self.entry_node_id not in node_set or self.exit_node_id not in node_set:
            raise ValueError("workflow entry and exit must reference nodes")
        if any(
            edge.source_node_id not in node_set or edge.target_node_id not in node_set
            for edge in self.edges
        ):
            raise ValueError("workflow edge references an unknown node")
        pairs = {(edge.source_node_id, edge.target_node_id) for edge in self.edges}
        if len(pairs) != len(self.edges):
            raise ValueError("workflow edges must not duplicate source and target")
        outgoing: dict[Identifier, list[Identifier]] = {node_id: [] for node_id in node_ids}
        incoming: dict[Identifier, list[Identifier]] = {node_id: [] for node_id in node_ids}
        for edge in self.edges:
            outgoing[edge.source_node_id].append(edge.target_node_id)
            incoming[edge.target_node_id].append(edge.source_node_id)
        indegree = {node_id: len(incoming[node_id]) for node_id in node_ids}
        ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
        visited: list[Identifier] = []
        while ready:
            current = ready.pop(0)
            visited.append(current)
            for target in sorted(outgoing[current]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
                    ready.sort()
        if len(visited) != len(node_ids):
            raise ValueError("workflow graph must be acyclic")
        reachable = {self.entry_node_id}
        frontier = [self.entry_node_id]
        while frontier:
            current = frontier.pop()
            for target in outgoing[current]:
                if target not in reachable:
                    reachable.add(target)
                    frontier.append(target)
        if reachable != node_set:
            raise ValueError("every workflow node must be reachable from entry")
        reverse_reachable = {self.exit_node_id}
        frontier = [self.exit_node_id]
        while frontier:
            current = frontier.pop()
            for source in incoming[current]:
                if source not in reverse_reachable:
                    reverse_reachable.add(source)
                    frontier.append(source)
        if reverse_reachable != node_set:
            raise ValueError("every workflow node must reach exit")
        return self


class ExecutionPolicy(FrozenModel):
    policy_id: Identifier
    version: SemanticVersion
    deterministic_seed: int = Field(ge=0)
    max_retries: int = Field(ge=0, le=M2703_MAX_ATTEMPTS)
    checkpoint_interval_nodes: int = Field(ge=1)
    capture_environment: Literal[True] = True
    immutable_state: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2703_MAX_EVIDENCE)


class ExecutionRecord(FrozenModel):
    execution_id: Identifier
    workflow_id: Identifier
    policy: ExecutionPolicy
    status: ExecutionStatus
    attempts: int = Field(ge=1, le=M2703_MAX_ATTEMPTS)
    completed_node_ids: tuple[Identifier, ...] = Field(default=(), max_length=M2703_MAX_NODES)
    checkpoint_digest: Sha256Digest | None = None
    environment_digest: Sha256Digest
    output_digest: Sha256Digest | None = None
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2703_MAX_EVIDENCE)


class ReproducibleResultPackage(FrozenModel):
    package_id: Identifier
    version: SemanticVersion
    execution_id: Identifier
    artifact_references: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2703_MAX_ARTIFACTS
    )
    manifest_digest: Sha256Digest
    environment_digest: Sha256Digest
    reproducibility_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2703_MAX_EVIDENCE)


class PipelineFinding(FrozenModel):
    finding_id: Identifier
    code: FindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2703_MAX_EVIDENCE)


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2703_MAX_EVIDENCE)


class OrchestrateComplexActivityPipelineRequest(FrozenModel):
    """Provisional request bound to the M27-02 lineage result."""

    operation: Literal["orchestrate_complex_activity_pipeline"] = M2703_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2703_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    workflow: WorkflowDAG
    policy: ExecutionPolicy
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2703_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> OrchestrateComplexActivityPipelineRequest:
        if self.upstream_result.media_type != M2703_M2702_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M27-02 lineage result")
        ids = tuple(item.artifact_id for item in self.source_artifacts)
        digests = tuple(item.digest for item in self.source_artifacts)
        if len(ids) != len(set(ids)) or len(digests) != len(set(digests)):
            raise ValueError("source artifacts must have unique ids and digests")
        return self


class ComplexActivityPipelineResult(FrozenModel):
    """Execution record and reproducible result package or safe failure."""

    output_type: Literal["complex_activity_pipeline"] = "complex_activity_pipeline"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2703_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: OrchestrateComplexActivityPipelineRequest
    status: PipelineStatus
    execution_record: ExecutionRecord | None = None
    result_package: ReproducibleResultPackage | None = None
    findings: tuple[PipelineFinding, ...] = Field(default=(), max_length=M2703_MAX_FINDINGS)
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2703_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2703_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityPipelineResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        if self.result_id != result_id_for_request_digest(self.request_digest):
            raise ValueError("result id must be derived from the request digest")
        if self.status is PipelineStatus.EXECUTED:
            if (
                self.execution_record is None
                or self.result_package is None
                or self.safe_failure_report is not None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("executed result requires supported execution records")
            execution = self.execution_record
            package = self.result_package
            assert execution is not None and package is not None
            if execution.execution_id != execution_id_for_request_digest(self.request_digest):
                raise ValueError("execution id must be derived from the request digest")
            if execution.workflow_id != self.request.workflow.workflow_id:
                raise ValueError("execution record must bind the request workflow")
            expected_nodes = {node.node_id for node in self.request.workflow.nodes}
            completed = set(execution.completed_node_ids)
            if completed != expected_nodes:
                raise ValueError("executed record must close every workflow node")
            if package.execution_id != execution.execution_id:
                raise ValueError("result package must bind the execution record")
            if package.package_id != package_id_for_request_digest(self.request_digest):
                raise ValueError("result package id must be derived from the request digest")
            if package.environment_digest != execution.environment_digest:
                raise ValueError("result package must bind execution environment")
            if execution.output_digest is None:
                raise ValueError("executed record requires output digest")
            if self.human_review_required:
                raise ValueError("supported executed result cannot require human review")
        elif (
            self.execution_record is not None
            or self.result_package is not None
            or self.safe_failure_report is None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if self.status is PipelineStatus.ABSTAINED and not self.human_review_required:
            raise ValueError("abstained result requires human review")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2703_CONTRACT_VERSION",
    "M2703_GATE",
    "M2703_M2702_INPUT_MEDIA_TYPE",
    "M2703_MAX_ARTIFACTS",
    "M2703_MAX_ATTEMPTS",
    "M2703_MAX_CANONICAL_REQUEST_BYTES",
    "M2703_MAX_CANONICAL_RESULT_BYTES",
    "M2703_MAX_EDGES",
    "M2703_MAX_EVIDENCE",
    "M2703_MAX_FINDINGS",
    "M2703_MAX_NODES",
    "M2703_MODULE_ID",
    "M2703_OPERATION",
    "M2703_OUTPUT_MEDIA_TYPE",
    "M2703_OWNER",
    "M2703_PARENT",
    "M2703_PROVISIONAL_ABI",
    "M2703_SAFETY_CLASS",
    "ComplexActivityPipelineResult",
    "ExecutionPolicy",
    "ExecutionRecord",
    "ExecutionStatus",
    "FindingCode",
    "OrchestrateComplexActivityPipelineRequest",
    "PipelineFinding",
    "PipelineStatus",
    "ReproducibleResultPackage",
    "SafeFailureReport",
    "WorkflowDAG",
    "WorkflowEdge",
    "WorkflowNode",
    "WorkflowNodeKind",
]
