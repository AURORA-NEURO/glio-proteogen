"""Strict contracts for the independently composed KNCC GBM factor graph.

The outer lane is deliberately not a multi-omics fusion model. It preserves the
exact fitted Reactome protein and SPHINKS phosphosite receipts as two independent
computational blocks and exposes their factor inventories through annotation-only
containment edges.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    PROFILE_ID as KINASE_PROFILE_ID,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    LongitudinalGbmKinaseTransitionRequest,
    LongitudinalGbmKinaseTransitionResult,
    UnverifiedLongitudinalGbmKinaseTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    PROFILE_ID as REACTOME_PROFILE_ID,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalGbmReactomeTransitionResult,
    UnverifiedLongitudinalGbmReactomeTransitionResult,
)

from .canonical import (
    canonical_request_digest,
    profile_payload_digest,
    result_payload_digest,
    sha256_digest,
    topology_payload_digest,
)

ALGORITHM_ID: Final = "glio-ecgi-kncc-gbm-transition"
ALGORITHM_VERSION: Final = "1.0.0"
PROFILE_ID: Final = "glio-ecgi-kncc-gbm-transition/1.0.0"
MODEL_ID: Final = "glio-ecgi-kncc-gbm-factor-graph/1.0.0"
TOPOLOGY_ID: Final = "kncc-gbm-independent-two-block-factor-topology/1.0.0"
EXPECTED_TOPOLOGY_DIGEST: Final = (
    "sha256:d9baef8ce0b125a26f547edd0441e05c772249fcef3ab57b95d0eea0c777f9c7"
)
DEMO_ID: Final = "kncc-gbm-factor-graph-synthetic-model-derived-v1"
RELATIONSHIP: Final = "independent_parallel_source_cohort_concordance_no_cross_modal_fusion"

MIN_TIME_POINTS: Final = 2
MAX_TIME_POINTS: Final = 5
MAX_REQUEST_BYTES: Final = 4_194_304
MAX_RESULT_BYTES: Final = 8_388_608
MAX_REPLAY_BYTES: Final = 16_777_216
BLOCK_COUNT: Final = 2
REACTOME_GLOBAL_FACTOR_COUNT: Final = 1
REACTOME_PATHWAY_FACTOR_COUNT: Final = 10
KINASE_FACTOR_COUNT: Final = 24
SUBTYPE_FACTOR_COUNT: Final = 4
NODE_COUNT: Final = 41
CONTAINMENT_EDGE_COUNT: Final = 39


class FactorGraphBlock(StrEnum):
    PROTEIN_REACTOME = "protein_reactome"
    PHOSPHOSITE_SPHINKS = "phosphosite_sphinks"


class FactorGraphNodeKind(StrEnum):
    COMPUTATION_BLOCK = "computation_block"
    GLOBAL_RECURRENCE_FACTOR = "global_recurrence_factor"
    REACTOME_PATHWAY_FACTOR = "reactome_pathway_factor"
    KINASE_SIGNATURE_FACTOR = "kinase_signature_factor"
    SUBTYPE_SIGNATURE_FACTOR = "subtype_signature_factor"


class FactorGraphNode(FrozenModel):
    node_id: Identifier
    block: FactorGraphBlock
    kind: FactorGraphNodeKind
    biological_identifier: NonEmptyStr
    label: NonEmptyStr
    child_profile_id: NonEmptyStr
    learned_semantics: Literal[
        "child_source_cohort_fitted_coordinate",
        "child_result_container_only",
    ]


class FactorGraphContainmentEdge(FrozenModel):
    edge_id: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    relationship: Literal["contains"] = "contains"
    computational_role: Literal["annotation_only"] = "annotation_only"
    numerical_weight: None = None


class FactorGraphTopology(FrozenModel):
    topology_id: Literal["kncc-gbm-independent-two-block-factor-topology/1.0.0"] = (
        "kncc-gbm-independent-two-block-factor-topology/1.0.0"
    )
    nodes: tuple[FactorGraphNode, ...] = Field(min_length=NODE_COUNT, max_length=NODE_COUNT)
    containment_edges: tuple[FactorGraphContainmentEdge, ...] = Field(
        min_length=CONTAINMENT_EDGE_COUNT,
        max_length=CONTAINMENT_EDGE_COUNT,
    )
    cross_block_edges: tuple[FactorGraphContainmentEdge, ...] = Field(
        default_factory=tuple,
        max_length=0,
    )
    numerical_cross_block_edge_count: Literal[0] = 0
    containment_edge_role: Literal["annotation_only"] = "annotation_only"
    topology_digest: Sha256Digest

    @model_validator(mode="after")
    def topology_is_complete_and_content_bound(self) -> Self:
        node_by_id = {node.node_id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("factor-graph node identifiers must be unique")
        edge_ids = tuple(edge.edge_id for edge in self.containment_edges)
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("factor-graph containment-edge identifiers must be unique")
        counts = {
            kind: sum(node.kind is kind for node in self.nodes) for kind in FactorGraphNodeKind
        }
        expected = {
            FactorGraphNodeKind.COMPUTATION_BLOCK: BLOCK_COUNT,
            FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR: REACTOME_GLOBAL_FACTOR_COUNT,
            FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR: REACTOME_PATHWAY_FACTOR_COUNT,
            FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR: KINASE_FACTOR_COUNT,
            FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR: SUBTYPE_FACTOR_COUNT,
        }
        if counts != expected:
            raise ValueError("factor-graph node-family counts do not match the locked topology")
        expected_node_semantics = {
            FactorGraphNodeKind.COMPUTATION_BLOCK: "child_result_container_only",
            FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR: ("child_source_cohort_fitted_coordinate"),
            FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR: ("child_source_cohort_fitted_coordinate"),
            FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR: ("child_source_cohort_fitted_coordinate"),
            FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR: ("child_source_cohort_fitted_coordinate"),
        }
        for node in self.nodes:
            is_reactome = node.kind in {
                FactorGraphNodeKind.GLOBAL_RECURRENCE_FACTOR,
                FactorGraphNodeKind.REACTOME_PATHWAY_FACTOR,
            }
            is_sphinks = node.kind in {
                FactorGraphNodeKind.KINASE_SIGNATURE_FACTOR,
                FactorGraphNodeKind.SUBTYPE_SIGNATURE_FACTOR,
            }
            if is_reactome and node.block is not FactorGraphBlock.PROTEIN_REACTOME:
                raise ValueError("Reactome factor kinds must remain in the protein block")
            if is_sphinks and node.block is not FactorGraphBlock.PHOSPHOSITE_SPHINKS:
                raise ValueError("SPHINKS factor kinds must remain in the phosphosite block")
            expected_profile_id = (
                REACTOME_PROFILE_ID
                if node.block is FactorGraphBlock.PROTEIN_REACTOME
                else KINASE_PROFILE_ID
            )
            if node.child_profile_id != expected_profile_id:
                raise ValueError("factor-graph node is bound to the wrong child profile")
            if node.learned_semantics != expected_node_semantics[node.kind]:
                raise ValueError("factor-graph node declares incompatible learned semantics")
        block_nodes = {
            node.block: node.node_id
            for node in self.nodes
            if node.kind is FactorGraphNodeKind.COMPUTATION_BLOCK
        }
        if set(block_nodes) != set(FactorGraphBlock):
            raise ValueError("factor graph must contain exactly one node for each block")
        targets: set[str] = set()
        for edge in self.containment_edges:
            source = node_by_id.get(edge.source_node_id)
            target = node_by_id.get(edge.target_node_id)
            if source is None or target is None:
                raise ValueError("containment edge references an unknown factor-graph node")
            if source.kind is not FactorGraphNodeKind.COMPUTATION_BLOCK:
                raise ValueError("containment edges must originate at computation-block nodes")
            if target.kind is FactorGraphNodeKind.COMPUTATION_BLOCK:
                raise ValueError("computation-block nodes cannot be containment targets")
            if source.block is not target.block:
                raise ValueError("cross-block containment is forbidden")
            if target.node_id in targets:
                raise ValueError("each factor node must have exactly one containment parent")
            targets.add(target.node_id)
        expected_targets = {
            node.node_id
            for node in self.nodes
            if node.kind is not FactorGraphNodeKind.COMPUTATION_BLOCK
        }
        if targets != expected_targets:
            raise ValueError("every non-block factor must have one annotation-only parent")
        if self.cross_block_edges or self.numerical_cross_block_edge_count != 0:
            raise ValueError("numerical or structural cross-block edges are forbidden")
        if self.topology_digest != topology_payload_digest(self):
            raise ValueError("topology digest does not match canonical topology content")
        if self.topology_digest != EXPECTED_TOPOLOGY_DIGEST:
            raise ValueError("topology digest is not the version-locked biological inventory")
        return self


class FactorGraphChildProfileBinding(FrozenModel):
    block: FactorGraphBlock
    child_profile_id: NonEmptyStr
    child_profile_digest: Sha256Digest
    source_digest: Sha256Digest
    fitted_digest: Sha256Digest
    bootstrap_digest: Sha256Digest
    evaluation_digest: Sha256Digest


class FactorGraphChildResultBinding(FrozenModel):
    block: FactorGraphBlock
    child_profile_id: NonEmptyStr
    child_profile_digest: Sha256Digest
    child_request_digest: Sha256Digest
    child_result_digest: Sha256Digest
    independently_computed: Literal[True] = True


class FactorGraphLimits(FrozenModel):
    minimum_time_points_per_child: Literal[2] = 2
    maximum_time_points_per_child: Literal[5] = 5
    maximum_request_bytes: Literal[4_194_304] = MAX_REQUEST_BYTES
    maximum_result_bytes: Literal[8_388_608] = MAX_RESULT_BYTES
    maximum_replay_bytes: Literal[16_777_216] = MAX_REPLAY_BYTES
    maximum_numerical_cross_block_edges: Literal[0] = 0


class FactorGraphCounts(FrozenModel):
    computation_blocks: Literal[2] = BLOCK_COUNT
    reactome_global_factors: Literal[1] = REACTOME_GLOBAL_FACTOR_COUNT
    reactome_pathway_factors: Literal[10] = REACTOME_PATHWAY_FACTOR_COUNT
    kinase_signature_factors: Literal[24] = KINASE_FACTOR_COUNT
    subtype_signature_factors: Literal[4] = SUBTYPE_FACTOR_COUNT
    nodes: Literal[41] = NODE_COUNT
    annotation_only_containment_edges: Literal[39] = CONTAINMENT_EDGE_COUNT
    numerical_cross_block_edges: Literal[0] = 0


class KnccGbmFactorGraphRequest(FrozenModel):
    profile_id: Literal["glio-ecgi-kncc-gbm-transition/1.0.0"] = PROFILE_ID
    analysis_id: Identifier
    relationship: Literal[
        "independent_parallel_source_cohort_concordance_no_cross_modal_fusion"
    ] = RELATIONSHIP
    reactome_request: LongitudinalGbmReactomeTransitionRequest
    kinase_request: LongitudinalGbmKinaseTransitionRequest

    @model_validator(mode="after")
    def child_series_respect_outer_resource_bound(self) -> Self:
        if len(self.reactome_request.time_points) > MAX_TIME_POINTS:
            raise ValueError("Reactome child requests are limited to five time points")
        if len(self.kinase_request.time_points) > MAX_TIME_POINTS:
            raise ValueError("kinase child requests are limited to five time points")
        return self

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class KnccGbmFactorGraphProfile(FrozenModel):
    algorithm_id: Literal["glio-ecgi-kncc-gbm-transition"] = ALGORITHM_ID
    algorithm_version: Literal["1.0.0"] = ALGORITHM_VERSION
    profile_id: Literal["glio-ecgi-kncc-gbm-transition/1.0.0"] = PROFILE_ID
    model_id: Literal["glio-ecgi-kncc-gbm-factor-graph/1.0.0"] = MODEL_ID
    relationship: Literal[
        "independent_parallel_source_cohort_concordance_no_cross_modal_fusion"
    ] = RELATIONSHIP
    topology: FactorGraphTopology
    topology_digest: Sha256Digest
    reactome_child: FactorGraphChildProfileBinding
    kinase_child: FactorGraphChildProfileBinding
    source_inventory_digest: Sha256Digest
    numpy_version: Literal["2.5.2"]
    composition_semantic_digest: Sha256Digest
    limits: FactorGraphLimits
    counts: FactorGraphCounts
    demo_id: Literal["kncc-gbm-factor-graph-synthetic-model-derived-v1"] = DEMO_ID
    demo_request_digest: Sha256Digest
    demo_semantic_oracle_digest: Sha256Digest
    source_attestation_state: Literal["verified_exact_child_snapshots"]
    safety_class: Literal["research_use_only"] = "research_use_only"
    claim_ceiling: Literal["independent_source_cohort_concordance_coordinates_only"] = (
        "independent_source_cohort_concordance_coordinates_only"
    )
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    independent_parallel_blocks: Literal[True] = Field(
        default=True,
        description=(
            "Parallel in graph semantics only; child engines execute deterministically "
            "in serial under one deadline."
        ),
    )
    cross_modal_fusion_performed: Literal[False] = False
    no_numerical_cross_block_edges: Literal[True] = True
    profile_digest: Sha256Digest

    @model_validator(mode="after")
    def profile_is_complete_and_content_bound(self) -> Self:
        if self.topology_digest != self.topology.topology_digest:
            raise ValueError("profile topology digest does not match embedded topology")
        if self.reactome_child.block is not FactorGraphBlock.PROTEIN_REACTOME:
            raise ValueError("Reactome child binding is assigned to the wrong block")
        if self.kinase_child.block is not FactorGraphBlock.PHOSPHOSITE_SPHINKS:
            raise ValueError("kinase child binding is assigned to the wrong block")
        if self.reactome_child.child_profile_id != REACTOME_PROFILE_ID:
            raise ValueError("Reactome child binding names the wrong child profile")
        if self.kinase_child.child_profile_id != KINASE_PROFILE_ID:
            raise ValueError("kinase child binding names the wrong child profile")
        child_profile_by_block = {
            FactorGraphBlock.PROTEIN_REACTOME: self.reactome_child.child_profile_id,
            FactorGraphBlock.PHOSPHOSITE_SPHINKS: self.kinase_child.child_profile_id,
        }
        if any(
            node.child_profile_id != child_profile_by_block[node.block]
            for node in self.topology.nodes
        ):
            raise ValueError("topology nodes disagree with their child profile binding")
        expected_source_inventory_digest = sha256_digest(
            {
                "reactome_child": self.reactome_child.model_dump(mode="json"),
                "kinase_child": self.kinase_child.model_dump(mode="json"),
            }
        )
        if self.source_inventory_digest != expected_source_inventory_digest:
            raise ValueError("source inventory digest does not match child profile bindings")
        if self.profile_digest != profile_payload_digest(self):
            raise ValueError("profile digest does not match canonical profile content")
        return self


class KnccGbmFactorGraphProvenance(FrozenModel):
    engine: Literal["glio-ecgi-kncc-gbm-transition/1.0.0"] = PROFILE_ID
    request_digest: Sha256Digest
    profile_digest: Sha256Digest
    topology_digest: Sha256Digest
    source_inventory_digest: Sha256Digest
    relationship: Literal[
        "independent_parallel_source_cohort_concordance_no_cross_modal_fusion"
    ] = RELATIONSHIP
    reactome_child: FactorGraphChildResultBinding
    kinase_child: FactorGraphChildResultBinding
    numpy_version: Literal["2.5.2"]
    independent_parallel_blocks: Literal[True] = Field(
        default=True,
        description=(
            "Parallel in graph semantics only; child engines execute deterministically "
            "in serial under one deadline."
        ),
    )
    cross_modal_fusion_performed: Literal[False] = False
    no_numerical_cross_block_edges: Literal[True] = True

    @model_validator(mode="after")
    def child_blocks_are_distinct(self) -> Self:
        if self.reactome_child.block is not FactorGraphBlock.PROTEIN_REACTOME:
            raise ValueError("Reactome provenance is assigned to the wrong block")
        if self.kinase_child.block is not FactorGraphBlock.PHOSPHOSITE_SPHINKS:
            raise ValueError("kinase provenance is assigned to the wrong block")
        return self


class _KnccGbmFactorGraphResultDocument(FrozenModel):
    algorithm_id: Literal["glio-ecgi-kncc-gbm-transition"] = ALGORITHM_ID
    algorithm_version: Literal["1.0.0"] = ALGORITHM_VERSION
    profile_id: Literal["glio-ecgi-kncc-gbm-transition/1.0.0"] = PROFILE_ID
    profile_digest: Sha256Digest
    topology_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    analysis_id: Identifier
    relationship: Literal[
        "independent_parallel_source_cohort_concordance_no_cross_modal_fusion"
    ] = RELATIONSHIP
    provenance: KnccGbmFactorGraphProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=6, max_length=20)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True
    independent_parallel_blocks: Literal[True] = Field(
        default=True,
        description=(
            "Parallel in graph semantics only; child engines execute deterministically "
            "in serial under one deadline."
        ),
    )
    cross_modal_fusion_performed: Literal[False] = False
    numerical_cross_block_edge_count: Literal[0] = 0

    def _validate_outer_and_child_bindings(
        self,
        reactome_result: (
            LongitudinalGbmReactomeTransitionResult
            | UnverifiedLongitudinalGbmReactomeTransitionResult
        ),
        kinase_result: (
            LongitudinalGbmKinaseTransitionResult | UnverifiedLongitudinalGbmKinaseTransitionResult
        ),
    ) -> None:
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("profile digest does not match provenance")
        if self.topology_digest != self.provenance.topology_digest:
            raise ValueError("topology digest does not match provenance")
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("request digest does not match provenance")
        reactome_binding = self.provenance.reactome_child
        kinase_binding = self.provenance.kinase_child
        if (
            reactome_result.profile_id != reactome_binding.child_profile_id
            or reactome_result.profile_digest != reactome_binding.child_profile_digest
            or reactome_result.request_digest != reactome_binding.child_request_digest
            or reactome_result.result_digest != reactome_binding.child_result_digest
        ):
            raise ValueError("Reactome child result does not match outer provenance")
        if (
            kinase_result.profile_id != kinase_binding.child_profile_id
            or kinase_result.profile_digest != kinase_binding.child_profile_digest
            or kinase_result.request_digest != kinase_binding.child_request_digest
            or kinase_result.result_digest != kinase_binding.child_result_digest
        ):
            raise ValueError("kinase child result does not match outer provenance")
        if len(reactome_result.time_point_ids) > MAX_TIME_POINTS:
            raise ValueError("Reactome child result exceeds the five-time-point outer limit")
        if len(kinase_result.time_point_ids) > MAX_TIME_POINTS:
            raise ValueError("kinase child result exceeds the five-time-point outer limit")


class KnccGbmFactorGraphResult(_KnccGbmFactorGraphResultDocument):
    reactome_result: LongitudinalGbmReactomeTransitionResult
    kinase_result: LongitudinalGbmKinaseTransitionResult

    @model_validator(mode="after")
    def result_is_exactly_nested_and_content_bound(self) -> Self:
        self._validate_outer_and_child_bindings(self.reactome_result, self.kinase_result)
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedKnccGbmFactorGraphResult(_KnccGbmFactorGraphResultDocument):
    reactome_result: (
        LongitudinalGbmReactomeTransitionResult | UnverifiedLongitudinalGbmReactomeTransitionResult
    )
    kinase_result: (
        LongitudinalGbmKinaseTransitionResult | UnverifiedLongitudinalGbmKinaseTransitionResult
    )

    @model_validator(mode="after")
    def result_is_exactly_nested(self) -> Self:
        self._validate_outer_and_child_bindings(self.reactome_result, self.kinase_result)
        return self


class KnccGbmFactorGraphReplayVerificationRequest(FrozenModel):
    request: KnccGbmFactorGraphRequest
    result: KnccGbmFactorGraphResult | UnverifiedKnccGbmFactorGraphResult


class KnccGbmFactorGraphReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    topology_digest_match: bool
    source_inventory_digest_match: bool
    result_digest_match: bool
    reactome_child_verified: bool
    kinase_child_verified: bool
    independent_parallel_blocks_match: bool
    no_cross_modal_fusion_match: bool
    no_numerical_cross_block_edges_match: bool
    provenance_match: bool
    document_semantic_match: bool
    semantic_match: bool
    recomputed_request_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    message: NonEmptyStr

    @model_validator(mode="after")
    def verification_summary_matches_independent_checks(self) -> Self:
        expected_semantic = all(
            (
                self.reactome_child_verified,
                self.kinase_child_verified,
                self.independent_parallel_blocks_match,
                self.no_cross_modal_fusion_match,
                self.no_numerical_cross_block_edges_match,
                self.provenance_match,
                self.document_semantic_match,
            )
        )
        if self.semantic_match is not expected_semantic:
            raise ValueError("semantic replay summary does not match independent checks")
        expected_verified = all(
            (
                self.request_digest_match,
                self.profile_digest_match,
                self.topology_digest_match,
                self.source_inventory_digest_match,
                self.result_digest_match,
                self.semantic_match,
            )
        )
        if self.verified is not expected_verified:
            raise ValueError("verified summary does not match digest and semantic checks")
        return self


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "BLOCK_COUNT",
    "CONTAINMENT_EDGE_COUNT",
    "DEMO_ID",
    "EXPECTED_TOPOLOGY_DIGEST",
    "KINASE_FACTOR_COUNT",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "MAX_TIME_POINTS",
    "MIN_TIME_POINTS",
    "MODEL_ID",
    "NODE_COUNT",
    "PROFILE_ID",
    "REACTOME_GLOBAL_FACTOR_COUNT",
    "REACTOME_PATHWAY_FACTOR_COUNT",
    "RELATIONSHIP",
    "SUBTYPE_FACTOR_COUNT",
    "TOPOLOGY_ID",
    "FactorGraphBlock",
    "FactorGraphChildProfileBinding",
    "FactorGraphChildResultBinding",
    "FactorGraphContainmentEdge",
    "FactorGraphCounts",
    "FactorGraphLimits",
    "FactorGraphNode",
    "FactorGraphNodeKind",
    "FactorGraphTopology",
    "KnccGbmFactorGraphProfile",
    "KnccGbmFactorGraphProvenance",
    "KnccGbmFactorGraphReplayVerificationRequest",
    "KnccGbmFactorGraphReplayVerificationResult",
    "KnccGbmFactorGraphRequest",
    "KnccGbmFactorGraphResult",
    "UnverifiedKnccGbmFactorGraphResult",
]
