"""Provisional M26-02 data, model, and version-lineage contracts.

M26-02 emits a queryable lineage graph and reproducibility bundle beneath the
Proteomics standards registry. The ABI is inferred from dossier lines
9080-9120 and remains provisional pending Bioinformatics confirmation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal

from pydantic import Field, model_validator

from glio_proteogen.contracts.m26_02.canonical import (
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

# PROVISIONAL ABI: inferred solely from dossier lines 9080-9120.
M2602_MODULE_ID: Final = "GLIO-PROTEOGEN-M26-02"
M2602_OPERATION: Final = "build_protein_subtype_lineage_graph"
M2602_CONTRACT_VERSION: Final = "0.1.0-provisional"
M2602_OUTPUT_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-02+json"
# M26-01 is not imported at runtime.  This is the caller-declared media
# boundary from the upstream registry/configuration service.
M2602_UPSTREAM_MEDIA_TYPE: Final = "application/vnd.glio-proteogen.m26-01+json"
M2602_PARENT: Final = "protein subtype"
M2602_OWNER: Final = "Bioinformatics"
M2602_SAFETY_CLASS: Final = "S3"
M2602_GATE: Final = "G0"
M2602_PROVISIONAL_ABI: Final = True
M2602_MAX_NODES: Final = 256
M2602_MAX_EDGES: Final = 512
M2602_MAX_ROOTS: Final = 32
M2602_REQUIRED_NODE_KINDS: Final = 7
M2602_MAX_EVIDENCE: Final = 64
M2602_MAX_FINDINGS: Final = 64
M2602_MAX_CANONICAL_REQUEST_BYTES: Final = 4 * 1024 * 1024
M2602_MAX_CANONICAL_RESULT_BYTES: Final = 8 * 1024 * 1024
M2602_EVIDENCE_CLAIM: Final = (
    "Caller-declared M26-02 lineage graph, exact-version traceability and "
    "reproducibility material; issuer authority is not authenticated."
)


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
    TRANSFORMED_BY = "transformed_by"
    FITTED_FROM = "fitted_from"
    VALIDATED_BY = "validated_by"
    GOVERNED_BY = "governed_by"


class LineageStatus(StrEnum):
    BUILT = "built"
    ABSTAINED = "abstained"


class LineageFindingCode(StrEnum):
    BROKEN_LINK = "broken_link"
    VERSION_MISMATCH = "version_mismatch"
    MISSING_ROOT = "missing_root"
    REPRODUCIBILITY_GAP = "reproducibility_gap"
    QUARANTINED_INPUT = "quarantined_input"
    PROVISIONAL_ABI_PENDING_REVIEW = "provisional_abi_pending_review"


class LineageNode(FrozenModel):
    """Immutable versioned source, transform, feature, model, or control node."""

    node_id: Identifier
    kind: LineageNodeKind
    name: NonEmptyStr
    version: SemanticVersion
    artifact: ArtifactReference
    producer: Identifier
    node_digest: Sha256Digest
    immutable: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def artifact_version_is_exact(self) -> LineageNode:
        if self.artifact.version != self.version:
            raise ValueError("lineage node version must match its artifact version")
        return self


class LineageEdge(FrozenModel):
    """One directed, versioned relationship in the lineage graph."""

    edge_id: Identifier
    parent_node_id: Identifier
    child_node_id: Identifier
    relation: LineageRelation
    transformation_version: SemanticVersion | None = None
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def edge_is_directed(self) -> LineageEdge:
        if self.parent_node_id == self.child_node_id:
            raise ValueError("lineage edges cannot self-reference")
        if self.relation is LineageRelation.TRANSFORMED_BY and self.transformation_version is None:
            raise ValueError("transformed-by edges require a transformation version")
        return self


class ReproducibilityBundle(FrozenModel):
    """Locked manifest sufficient to replay a released lineage result."""

    bundle_id: Identifier
    version: SemanticVersion
    root_node_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=M2602_MAX_ROOTS)
    required_kinds: tuple[LineageNodeKind, ...] = Field(
        min_length=M2602_REQUIRED_NODE_KINDS,
        max_length=M2602_REQUIRED_NODE_KINDS,
    )
    graph_digest: Sha256Digest
    environment_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def all_lineage_kinds_are_required(self) -> ReproducibilityBundle:
        if set(self.required_kinds) != set(LineageNodeKind) or len(self.required_kinds) != len(
            set(self.required_kinds)
        ):
            raise ValueError("reproducibility bundle must require every lineage node kind")
        if len(self.root_node_ids) != len(set(self.root_node_ids)):
            raise ValueError("reproducibility root ids must be unique")
        return self


class LineageGraph(FrozenModel):
    """Closed queryable graph with exact node and edge references."""

    graph_id: Identifier
    version: SemanticVersion
    nodes: tuple[LineageNode, ...] = Field(
        min_length=M2602_REQUIRED_NODE_KINDS,
        max_length=M2602_MAX_NODES,
    )
    edges: tuple[LineageEdge, ...] = Field(min_length=6, max_length=M2602_MAX_EDGES)
    graph_digest: Sha256Digest
    locked: Literal[True] = True
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2602_MAX_EVIDENCE)

    @model_validator(mode="after")
    def graph_is_closed(self) -> LineageGraph:
        node_ids = tuple(item.node_id for item in self.nodes)
        edge_ids = tuple(item.edge_id for item in self.edges)
        known = set(node_ids)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("lineage node ids must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("lineage edge ids must be unique")
        if any(
            edge.parent_node_id not in known or edge.child_node_id not in known
            for edge in self.edges
        ):
            raise ValueError("lineage edge references an unknown node")
        if {item.kind for item in self.nodes} != set(LineageNodeKind):
            raise ValueError("lineage graph must cover every required node kind")
        parents = {edge.child_node_id: edge.parent_node_id for edge in self.edges}
        for node_id in known:
            seen: set[str] = set()
            current = node_id
            while current in parents:
                if current in seen:
                    raise ValueError("lineage graph cannot contain a directed cycle")
                seen.add(current)
                current = parents[current]
        return self


class LineageFinding(FrozenModel):
    finding_id: Identifier
    code: LineageFindingCode
    message: NonEmptyStr
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2602_MAX_EVIDENCE)


class BuildProteinSubtypeLineageRequest(FrozenModel):
    """Provisional request for a queryable graph and replay bundle."""

    operation: Literal["build_protein_subtype_lineage_graph"] = M2602_OPERATION
    contract_version: Literal["0.1.0-provisional"] = M2602_CONTRACT_VERSION
    request_id: Identifier
    context: ExecutionContext
    graph_id: Identifier
    graph_version: SemanticVersion
    nodes: tuple[LineageNode, ...] = Field(
        min_length=M2602_REQUIRED_NODE_KINDS,
        max_length=M2602_MAX_NODES,
    )
    edges: tuple[LineageEdge, ...] = Field(min_length=6, max_length=M2602_MAX_EDGES)
    reproducibility_bundle: ReproducibilityBundle
    upstream_registry_artifact: ArtifactReference
    source_artifacts: tuple[ArtifactReference, ...] = Field(
        min_length=1, max_length=M2602_MAX_EVIDENCE
    )
    supersedes_result_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def request_is_closed(self) -> BuildProteinSubtypeLineageRequest:
        node_ids = tuple(item.node_id for item in self.nodes)
        known = set(node_ids)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("request lineage node ids must be unique")
        if any(
            edge.parent_node_id not in known or edge.child_node_id not in known
            for edge in self.edges
        ):
            raise ValueError("request edge references an unknown node")
        if any(root not in known for root in self.reproducibility_bundle.root_node_ids):
            raise ValueError("reproducibility bundle references an unknown root")
        if {item.kind for item in self.nodes} != set(LineageNodeKind):
            raise ValueError("request must cover every required lineage node kind")
        if self.upstream_registry_artifact.media_type != M2602_UPSTREAM_MEDIA_TYPE:
            raise ValueError("upstream registry artifact must use the declared M26-01 media type")
        if self.upstream_registry_artifact not in self.source_artifacts:
            raise ValueError("upstream registry artifact must be included in source artifacts")
        if len(self.edges) != len({edge.edge_id for edge in self.edges}):
            raise ValueError("request lineage edge ids must be unique")
        return self


class ProteinSubtypeLineageResult(FrozenModel):
    """Queryable lineage graph and replay bundle with safe abstention."""

    output_type: Literal["protein_subtype_lineage"] = "protein_subtype_lineage"
    result_id: Identifier
    result_version: Literal["0.1.0-provisional"] = M2602_CONTRACT_VERSION
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    request: BuildProteinSubtypeLineageRequest
    status: LineageStatus
    lineage_graph: LineageGraph | None = None
    reproducibility_bundle: ReproducibilityBundle | None = None
    findings: tuple[LineageFinding, ...] = Field(default=(), max_length=M2602_MAX_FINDINGS)
    abstention_reason: NonEmptyStr | None = None
    parent_target: Literal["protein subtype"] = M2602_PARENT
    emits_parent: Literal[False] = False
    support_decision: SupportDecision
    uncertainty: UncertaintyProfile
    provenance: ProvenanceRecord
    evidence: tuple[EvidenceReference, ...] = Field(default=(), max_length=M2602_MAX_EVIDENCE)
    limitations: tuple[Limitation, ...] = Field(min_length=1, max_length=32)
    human_review_required: Literal[True] = True

    @model_validator(mode="after")
    def result_is_closed(self) -> ProteinSubtypeLineageResult:
        if self.request_digest != canonical_request_digest(self.request):
            raise ValueError("result request digest does not bind exact request")
        expected_result_id = "result.m2602." + self.request_digest.removeprefix("sha256:")
        if self.result_id != expected_result_id:
            raise ValueError("result id must bind the request digest")
        if self.status is LineageStatus.BUILT:
            if (
                self.lineage_graph is None
                or self.reproducibility_bundle is None
                or self.abstention_reason is not None
                or self.support_decision.status is not SupportStatus.SUPPORTED
            ):
                raise ValueError("built result requires supported graph and bundle")
            if self.reproducibility_bundle != self.request.reproducibility_bundle:
                raise ValueError("built result bundle must bind the exact request bundle")
            if (
                self.lineage_graph.graph_id != self.request.graph_id
                or self.lineage_graph.version != self.request.graph_version
                or self.lineage_graph.nodes != self.request.nodes
                or self.lineage_graph.edges != self.request.edges
                or self.lineage_graph.graph_digest != self.reproducibility_bundle.graph_digest
            ):
                raise ValueError("built lineage graph must bind exact request graph material")
        elif (
            self.lineage_graph is not None
            or self.reproducibility_bundle is not None
            or self.abstention_reason is None
            or self.support_decision.status
            not in {SupportStatus.UNSUPPORTED, SupportStatus.REVIEW_REQUIRED}
        ):
            raise ValueError("abstained result requires no graph or bundle and safe status")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


__all__ = [
    "M2602_CONTRACT_VERSION",
    "M2602_EVIDENCE_CLAIM",
    "M2602_GATE",
    "M2602_MAX_CANONICAL_REQUEST_BYTES",
    "M2602_MAX_CANONICAL_RESULT_BYTES",
    "M2602_MAX_EDGES",
    "M2602_MAX_EVIDENCE",
    "M2602_MAX_FINDINGS",
    "M2602_MAX_NODES",
    "M2602_MAX_ROOTS",
    "M2602_MODULE_ID",
    "M2602_OPERATION",
    "M2602_OUTPUT_MEDIA_TYPE",
    "M2602_OWNER",
    "M2602_PARENT",
    "M2602_PROVISIONAL_ABI",
    "M2602_REQUIRED_NODE_KINDS",
    "M2602_SAFETY_CLASS",
    "M2602_UPSTREAM_MEDIA_TYPE",
    "BuildProteinSubtypeLineageRequest",
    "LineageEdge",
    "LineageFinding",
    "LineageFindingCode",
    "LineageGraph",
    "LineageNode",
    "LineageNodeKind",
    "LineageRelation",
    "LineageStatus",
    "ProteinSubtypeLineageResult",
    "ReproducibilityBundle",
]
