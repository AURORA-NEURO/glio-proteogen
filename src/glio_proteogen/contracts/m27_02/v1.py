"""Provisional M27-02 data, model, and version lineage contracts.

Every released object must trace to exact producing versions without broken
links. The scaffold emits only a queryable lineage graph and reproducibility
bundle, with explicit safe failure for unresolved lineage.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m27_02.canonical import (
    canonical_request_digest,
    graph_payload_digest,
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
# lines 9440-9480. Owner confirmation and implementation details remain
# pending.
M2702_MODULE_ID: Final = "GLIO-PROTEOGEN-M27-02"
M2702_OPERATION: Final = "resolve_complex_activity_lineage"
M2702_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2702_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-02+json"
M2702_M2701_INPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m27-01+json"
M2702_PARENT: Final = "complex activity"
M2702_OWNER: Final = "ML engineering"
M2702_SAFETY_CLASS: Final = "S3"
M2702_GATE: Final = "G0"
M2702_PROVISIONAL_ABI: Final = True
M2702_MAX_NODES: Final = 512
M2702_MAX_EDGES: Final = 1024
M2702_MAX_VERSIONS: Final = 256
M2702_MAX_EVIDENCE: Final = 64
M2702_MAX_FINDINGS: Final = 64
M2702_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2702_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024


def _assert_acyclic(adjacency: dict[str, set[str]], start: str) -> None:
    """Reject a directed cycle without imposing a single-parent topology."""

    seen: set[str] = set()
    active: set[str] = set()

    def visit(current: str) -> None:
        if current in active:
            raise ValueError("lineage graph cannot contain a directed cycle")
        if current in seen:
            return
        active.add(current)
        for child in adjacency[current]:
            visit(child)
        active.remove(current)
        seen.add(current)

    visit(start)


class LineageNodeKind(StrEnum):
    SOURCE_DATA = "source_data"
    TRANSFORMATION = "transformation"
    FEATURE = "feature"
    MODEL = "model"
    REFERENCE = "reference"
    POLICY = "policy"
    EVIDENCE = "evidence"


class LineageRelation(StrEnum):
    DERIVED_FROM = "derived_from"
    TRANSFORMED_TO = "transformed_to"
    USES = "uses"
    REFERENCES = "references"
    GOVERNED_BY = "governed_by"


class LineageStatus(StrEnum):
    RESOLVED = "resolved"
    ABSTAINED = "abstained"


class LineageFindingCode(StrEnum):
    BROKEN_LINK = "broken_link"
    VERSION_MISSING = "version_missing"
    DIGEST_MISMATCH = "digest_mismatch"
    UPSTREAM_UNSUPPORTED = "upstream_unsupported"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class LineageNode(FrozenModel):
    node_id: Identifier
    kind: LineageNodeKind
    name: NonEmptyStr
    version: SemanticVersion
    digest: Sha256Digest
    media_type: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2702_MAX_EVIDENCE)


class LineageEdge(FrozenModel):
    edge_id: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    relation: LineageRelation
    producing_version: SemanticVersion
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def endpoints_are_distinct(self) -> LineageEdge:
        if self.source_node_id == self.target_node_id:
            raise ValueError("lineage edge endpoints must be distinct")
        return self


class ReproducibilityBundle(FrozenModel):
    bundle_id: Identifier
    version: SemanticVersion
    root_node_id: Identifier
    node_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M2702_MAX_NODES)
    edge_ids: tuple[Identifier, ...] = Field(default=(), max_length=M2702_MAX_EDGES)
    producing_versions: tuple[SemanticVersion, ...] = Field(
        min_length=1, max_length=M2702_MAX_VERSIONS
    )
    manifest_digest: Sha256Digest
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def bundle_ids_are_unique(self) -> ReproducibilityBundle:
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("bundle node ids must be unique")
        if len(self.edge_ids) != len(set(self.edge_ids)):
            raise ValueError("bundle edge ids must be unique")
        if self.root_node_id not in self.node_ids:
            raise ValueError("bundle root must be included in bundle node ids")
        if len(self.producing_versions) != len(set(self.producing_versions)):
            raise ValueError("bundle producing versions must be unique")
        return self


class LineageGraph(FrozenModel):
    graph_id: Identifier
    version: SemanticVersion
    nodes: tuple[LineageNode, ...] = Field(min_length=1, max_length=M2702_MAX_NODES)
    edges: tuple[LineageEdge, ...] = Field(default=(), max_length=M2702_MAX_EDGES)
    reproducibility_bundle: ReproducibilityBundle
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2702_MAX_EVIDENCE)

    @model_validator(mode="after")
    def graph_is_closed(self) -> LineageGraph:
        node_ids = tuple(node.node_id for node in self.nodes)
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("lineage node ids must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("lineage edge ids must be unique")
        node_set = set(node_ids)
        if any(
            edge.source_node_id not in node_set or edge.target_node_id not in node_set
            for edge in self.edges
        ):
            raise ValueError("lineage edge references an unknown node")
        if self.reproducibility_bundle.root_node_id not in node_set:
            raise ValueError("bundle root must reference a lineage node")
        if not set(self.reproducibility_bundle.node_ids).issubset(node_set):
            raise ValueError("bundle references an unknown lineage node")
        if not set(self.reproducibility_bundle.edge_ids).issubset(set(edge_ids)):
            raise ValueError("bundle references an unknown lineage edge")
        if set(self.reproducibility_bundle.node_ids) != node_set:
            raise ValueError("bundle must enumerate every lineage node")
        if set(self.reproducibility_bundle.edge_ids) != set(edge_ids):
            raise ValueError("bundle must enumerate every lineage edge")
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_set}
        for edge in self.edges:
            adjacency[edge.source_node_id].add(edge.target_node_id)
        for node_id in node_set:
            _assert_acyclic(adjacency, node_id)
        return self


class LineageFinding(FrozenModel):
    finding_id: Identifier
    code: LineageFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2702_MAX_EVIDENCE)


class SafeFailureReport(FrozenModel):
    report_id: Identifier
    version: SemanticVersion
    trigger: NonEmptyStr
    action: NonEmptyStr
    abstained: Literal[True] = True
    recovery_note: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(min_length=1, max_length=M2702_MAX_EVIDENCE)


class ResolveComplexActivityLineageRequest(FrozenModel):
    """Provisional request bound to the M27-01 search/quant result."""

    operation: Literal["resolve_complex_activity_lineage"] = M2702_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2702_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    upstream_result: ArtifactReference
    root_object_id: Identifier
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2702_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_bound(self) -> ResolveComplexActivityLineageRequest:
        if self.upstream_result.media_type != M2702_M2701_INPUT_MEDIA_TYPE:
            raise ValueError("request must bind the provisional M27-01 search result")
        if self.upstream_result not in self.source_artifacts:
            raise ValueError("upstream result must be included in source artifacts")
        return self


def _graph_binds_exact_request(
    graph: LineageGraph,
    request: ResolveComplexActivityLineageRequest,
    request_digest: Sha256Digest,
) -> bool:
    source_ids = tuple(artifact.artifact_id for artifact in request.source_artifacts)
    source_versions = tuple(artifact.version for artifact in request.source_artifacts)
    source_digests = tuple(artifact.digest for artifact in request.source_artifacts)
    source_media_types = tuple(artifact.media_type for artifact in request.source_artifacts)
    source_nodes = graph.nodes[1:]
    edges = graph.edges
    bundle = graph.reproducibility_bundle
    root = graph.nodes[0]
    return (
        graph.graph_id == "graph.m2702." + request_digest.removeprefix("sha256:")
        and graph.version == M2702_CONTRACT_VERSION
        and tuple(node.node_id for node in graph.nodes) == (request.root_object_id, *source_ids)
        and root.kind is LineageNodeKind.TRANSFORMATION
        and root.name == "complex_activity_lineage_root"
        and root.version == M2702_CONTRACT_VERSION
        and root.digest == request_digest
        and root.media_type == M2702_OUTPUT_MEDIA_TYPE
        and tuple(node.kind for node in source_nodes)
        == (LineageNodeKind.SOURCE_DATA,) * len(source_ids)
        and tuple(node.name for node in source_nodes) == source_ids
        and tuple(node.version for node in source_nodes) == source_versions
        and tuple(node.digest for node in source_nodes) == source_digests
        and tuple(node.media_type for node in source_nodes) == source_media_types
        and tuple(edge.edge_id for edge in edges)
        == tuple(f"edge.m2702.{index}" for index in range(len(source_ids)))
        and tuple(edge.source_node_id for edge in edges) == source_ids
        and tuple(edge.target_node_id for edge in edges)
        == (request.root_object_id,) * len(source_ids)
        and tuple(edge.relation for edge in edges)
        == (LineageRelation.DERIVED_FROM,) * len(source_ids)
        and tuple(edge.producing_version for edge in edges) == source_versions
        and bundle.bundle_id == "bundle.m2702." + request_digest.removeprefix("sha256:")
        and bundle.version == M2702_CONTRACT_VERSION
        and bundle.root_node_id == request.root_object_id
        and bundle.node_ids == tuple(node.node_id for node in graph.nodes)
        and bundle.edge_ids == tuple(edge.edge_id for edge in edges)
        and bundle.producing_versions == tuple(sorted({M2702_CONTRACT_VERSION, *source_versions}))
    )


class ComplexActivityLineageResult(FrozenModel):
    """Queryable lineage graph and reproducibility bundle or safe failure."""

    output_type: Literal["complex_activity_lineage"] = "complex_activity_lineage"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2702_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: ResolveComplexActivityLineageRequest
    status: LineageStatus
    lineage_graph: LineageGraph | None = None
    findings: tuple[LineageFinding, ...] = Field(default=(), max_length=M2702_MAX_FINDINGS)
    safe_failure_report: SafeFailureReport | None = None
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["complex activity"] = M2702_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2702_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: bool = False

    @model_validator(mode="after")
    def result_is_closed(self) -> ComplexActivityLineageResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind the exact request")
        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("result finding ids must be unique")
        if self.status is LineageStatus.RESOLVED:
            if (
                self.lineage_graph is None
                or self.safe_failure_report is not None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
                or self.human_review_required
            ):
                raise ValueError("resolved result requires a supported lineage graph")
            if not _graph_binds_exact_request(
                self.lineage_graph, self.request, self.request_digest
            ):
                raise ValueError("resolved lineage graph must bind exact request dependencies")
            if self.lineage_graph.reproducibility_bundle.manifest_digest != graph_payload_digest(
                self.lineage_graph
            ):
                raise ValueError("resolved result bundle does not bind graph content")
        elif (
            self.lineage_graph is not None
            or self.safe_failure_report is None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
            or self.human_review_required
            is not (self.support_decision.status is SupportStatus.REVIEW_REQUIRED)
        ):
            raise ValueError("abstained result requires safe failure and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2702_CONTRACT_VERSION",
    "M2702_GATE",
    "M2702_M2701_INPUT_MEDIA_TYPE",
    "M2702_MAX_CANONICAL_REQUEST_BYTES",
    "M2702_MAX_CANONICAL_RESULT_BYTES",
    "M2702_MAX_EDGES",
    "M2702_MAX_EVIDENCE",
    "M2702_MAX_FINDINGS",
    "M2702_MAX_NODES",
    "M2702_MAX_VERSIONS",
    "M2702_MODULE_ID",
    "M2702_OPERATION",
    "M2702_OUTPUT_MEDIA_TYPE",
    "M2702_OWNER",
    "M2702_PARENT",
    "M2702_PROVISIONAL_ABI",
    "M2702_SAFETY_CLASS",
    "ComplexActivityLineageResult",
    "LineageEdge",
    "LineageFinding",
    "LineageFindingCode",
    "LineageGraph",
    "LineageNode",
    "LineageNodeKind",
    "LineageRelation",
    "LineageStatus",
    "ReproducibilityBundle",
    "ResolveComplexActivityLineageRequest",
    "SafeFailureReport",
]
