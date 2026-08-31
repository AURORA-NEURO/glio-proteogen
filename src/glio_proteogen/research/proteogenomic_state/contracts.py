"""Strict contracts for research-only proteogenomic graph inference.

These models describe experimental, non-clinical computation.  They deliberately do
not reuse or modify the frozen governed kinase or proteogenomic-state contracts.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, field_validator, model_validator

from glio_proteogen.kernel.models import FrozenModel, Identifier, NonEmptyStr, Sha256Digest

from .canonical import (
    canonical_request_digest,
    graph_topology_digest,
    result_payload_digest,
)

ALGORITHM_ID = "glio-ecgi"
ALGORITHM_VERSION = "1.0.0"
PROFILE_ID = "glio-ecgi/1.0.0"
MAX_NODES = 256
MAX_EDGES = 2_048
MAX_OBSERVATIONS = 4_096
MAX_KINASES = 128
MAX_BOOTSTRAPS = 256
MAX_PERMUTATIONS = 2_048
MAX_REQUEST_BYTES = 2 * 1_024 * 1_024
MAX_RESULT_BYTES = 4 * 1_024 * 1_024
MAX_JSON_SAFE_INTEGER = 2**53 - 1

DisplayName = Annotated[str, StringConstraints(min_length=1, max_length=160)]
HttpsUrl = Annotated[
    str,
    StringConstraints(max_length=512, pattern=r"^https://[^\s]+$"),
]
IsoDate = Annotated[
    str,
    StringConstraints(pattern=r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$"),
]


class NodeKind(StrEnum):
    PROTEIN = "protein"
    PROTEOFORM = "proteoform"
    PHOSPHOSITE = "phosphosite"
    COMPLEX = "complex"
    PATHWAY = "pathway"
    KINASE = "kinase"


class EdgeKind(StrEnum):
    REGULATES = "regulates"
    MEMBER_OF = "member_of"
    KINASE_SUBSTRATE = "kinase_substrate"
    PARTICIPATES_IN = "participates_in"
    PROTEOFORM_OF = "proteoform_of"
    SITE_OF = "site_of"


class ResearchEvidenceState(StrEnum):
    """Research-lane evidence states, named distinctly in public OpenAPI."""

    OBSERVED = "observed"
    LEFT_CENSORED = "left_censored"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"


# Preserve the concise Python contract name without colliding with the governed
# M01-07 ``EvidenceState`` component in the shared application's OpenAPI schema.
EvidenceState = ResearchEvidenceState


class EvidenceModality(StrEnum):
    PROTEOMICS = "proteomics"
    PHOSPHOPROTEOMICS = "phosphoproteomics"
    TRANSCRIPTOMICS = "transcriptomics"
    COPY_NUMBER = "copy_number"
    EXTERNAL = "external"


class StateClassification(StrEnum):
    ACTIVATED = "activated"
    SUPPRESSED = "suppressed"
    NEUTRAL = "neutral"
    INDETERMINATE = "indeterminate"
    NOT_ESTIMABLE = "not_estimable"


class InferenceSupport(StrEnum):
    SUPPORTED = "supported"
    LIMITED = "limited"
    ABSTAINED = "abstained"


class AblationKind(StrEnum):
    EDGE_FAMILY = "edge_family"
    MODALITY = "modality"


class GraphNode(FrozenModel):
    node_id: Identifier
    kind: NodeKind
    display_name: DisplayName | None = None


class GraphEdge(FrozenModel):
    edge_id: Identifier
    source_id: Identifier
    target_id: Identifier
    kind: EdgeKind
    sign: Literal[-1, 1]
    weight: float = Field(ge=0.01, le=10.0)
    essential: bool = False

    @model_validator(mode="after")
    def essential_is_only_a_complex_membership_property(self) -> Self:
        if self.essential and self.kind is not EdgeKind.MEMBER_OF:
            raise ValueError("essential is only valid for member_of edges")
        if (
            self.kind in {EdgeKind.MEMBER_OF, EdgeKind.PROTEOFORM_OF, EdgeKind.SITE_OF}
            and self.sign != 1
        ):
            raise ValueError(f"{self.kind.value} edges must have positive sign")
        return self


class EvidenceObservation(FrozenModel):
    observation_id: Identifier
    node_id: Identifier
    modality: EvidenceModality
    state: EvidenceState
    standardized_effect: float | None = Field(default=None, ge=-20.0, le=20.0)
    standard_error: float | None = Field(default=None, gt=0.0, le=20.0)
    quality_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance_digest: Sha256Digest

    @model_validator(mode="after")
    def values_match_evidence_state(self) -> Self:
        active = self.state in {EvidenceState.OBSERVED, EvidenceState.LEFT_CENSORED}
        if active and (self.standardized_effect is None or self.standard_error is None):
            raise ValueError("observed and left-censored evidence require effect and error")
        if active and self.quality_weight <= 0.0:
            raise ValueError("active evidence requires a positive quality weight")
        if not active and (self.standardized_effect is not None or self.standard_error is not None):
            raise ValueError("missing and unsupported evidence cannot carry numeric effects")
        return self


class ExternalKinaseEstimate(FrozenModel):
    kinase_id: Identifier
    activity: float = Field(ge=-20.0, le=20.0)
    lower_bound: float = Field(ge=-20.0, le=20.0)
    upper_bound: float = Field(ge=-20.0, le=20.0)

    @model_validator(mode="after")
    def interval_contains_activity(self) -> Self:
        if not self.lower_bound <= self.activity <= self.upper_bound:
            raise ValueError("external interval must contain its activity")
        return self


class ExternalKinaseProfile(FrozenModel):
    profile_id: Identifier
    source_digest: Sha256Digest
    estimates: tuple[ExternalKinaseEstimate, ...] = Field(min_length=1, max_length=MAX_KINASES)

    @field_validator("estimates")
    @classmethod
    def kinase_estimates_are_unique(
        cls, values: tuple[ExternalKinaseEstimate, ...]
    ) -> tuple[ExternalKinaseEstimate, ...]:
        identifiers = tuple(value.kinase_id for value in values)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("external kinase identifiers must be unique")
        return values


class PublicTopologySource(FrozenModel):
    """Content-addressed public record used only to contextualize graph topology."""

    source_id: Identifier
    resource_name: DisplayName
    resource_release: DisplayName
    record_id: Identifier
    record_title: DisplayName
    source_uri: HttpsUrl
    source_format: DisplayName
    source_digest: Sha256Digest
    source_size_bytes: int = Field(gt=0, le=64 * 1_024 * 1_024)
    license_id: Identifier
    license_uri: HttpsUrl
    retrieved_on: IsoDate
    scope_node_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=MAX_NODES)
    role: Literal["biological_context"] = "biological_context"

    @field_validator("scope_node_ids")
    @classmethod
    def scoped_node_identifiers_are_unique(
        cls, values: tuple[Identifier, ...]
    ) -> tuple[Identifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("topology source scope node identifiers must be unique")
        return values


class TopologyProvenance(FrozenModel):
    """Caller declaration binding a graph topology to inspectable public records."""

    topology_digest: Sha256Digest
    derivation: Literal["caller_curated", "synthetic_abstraction"]
    sources: tuple[PublicTopologySource, ...] = Field(min_length=1, max_length=32)
    curation_note: NonEmptyStr

    @field_validator("sources")
    @classmethod
    def source_identifiers_are_unique(
        cls, values: tuple[PublicTopologySource, ...]
    ) -> tuple[PublicTopologySource, ...]:
        identifiers = tuple(value.source_id for value in values)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("topology source identifiers must be unique")
        return values


class ProteogenomicStateRequest(FrozenModel):
    profile_id: Literal["glio-ecgi/1.0.0"] = "glio-ecgi/1.0.0"
    sample_id: Identifier
    nodes: tuple[GraphNode, ...] = Field(min_length=1, max_length=MAX_NODES)
    edges: tuple[GraphEdge, ...] = Field(default=(), max_length=MAX_EDGES)
    observations: tuple[EvidenceObservation, ...] = Field(default=(), max_length=MAX_OBSERVATIONS)
    bootstrap_replicates: int = Field(default=64, ge=8, le=MAX_BOOTSTRAPS)
    permutation_replicates: int = Field(default=256, ge=32, le=MAX_PERMUTATIONS)
    external_kinase_profile: ExternalKinaseProfile | None = None
    topology_provenance: TopologyProvenance | None = None

    @model_validator(mode="after")
    def graph_is_closed_and_typed(self) -> Self:
        node_by_id = {node.node_id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("node identifiers must be unique")
        edge_ids = tuple(edge.edge_id for edge in self.edges)
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge identifiers must be unique")
        semantic_relations = tuple(
            (edge.source_id, edge.target_id, edge.kind) for edge in self.edges
        )
        if len(semantic_relations) != len(set(semantic_relations)):
            raise ValueError("parallel semantic relations are not supported")
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("observation identifiers must be unique")
        kinase_count = sum(node.kind is NodeKind.KINASE for node in self.nodes)
        if kinase_count > MAX_KINASES:
            raise ValueError("kinase count exceeds the research bound")
        for edge in self.edges:
            if edge.source_id not in node_by_id or edge.target_id not in node_by_id:
                raise ValueError("edge references an unresolved node")
            if edge.source_id == edge.target_id:
                raise ValueError("self edges are not supported")
            source = node_by_id[edge.source_id].kind
            target = node_by_id[edge.target_id].kind
            self._validate_edge_kinds(edge, source, target)
        for observation in self.observations:
            if observation.node_id not in node_by_id:
                raise ValueError("observation references an unresolved node")
        if self.external_kinase_profile is not None:
            for estimate in self.external_kinase_profile.estimates:
                node = node_by_id.get(estimate.kinase_id)
                if node is None or node.kind is not NodeKind.KINASE:
                    raise ValueError("external profile must reference exact kinase node IDs")
        if self.topology_provenance is not None:
            if self.topology_provenance.topology_digest != graph_topology_digest(self):
                raise ValueError("topology provenance digest does not match nodes and edges")
            for topology_source in self.topology_provenance.sources:
                if any(node_id not in node_by_id for node_id in topology_source.scope_node_ids):
                    raise ValueError("topology source scope references an unresolved node")
        return self

    @staticmethod
    def _validate_edge_kinds(edge: GraphEdge, source: NodeKind, target: NodeKind) -> None:
        if edge.kind is EdgeKind.MEMBER_OF and not (
            source in {NodeKind.PROTEIN, NodeKind.PROTEOFORM} and target is NodeKind.COMPLEX
        ):
            raise ValueError("member_of requires a protein/proteoform source and complex target")
        if edge.kind is EdgeKind.KINASE_SUBSTRATE and not (
            source is NodeKind.KINASE and target is NodeKind.PHOSPHOSITE
        ):
            raise ValueError("kinase_substrate requires kinase to phosphosite")
        if edge.kind is EdgeKind.PARTICIPATES_IN and target is not NodeKind.PATHWAY:
            raise ValueError("participates_in must target a pathway")
        if edge.kind is EdgeKind.PROTEOFORM_OF and not (
            source is NodeKind.PROTEOFORM and target is NodeKind.PROTEIN
        ):
            raise ValueError("proteoform_of requires proteoform to protein")
        if edge.kind is EdgeKind.SITE_OF and not (
            source is NodeKind.PHOSPHOSITE and target in {NodeKind.PROTEOFORM, NodeKind.PROTEIN}
        ):
            raise ValueError("site_of requires phosphosite to proteoform/protein")

    @property
    def request_digest(self) -> str:
        return canonical_request_digest(self)


class SolverPassDiagnostics(FrozenModel):
    pass_name: Literal["evidence_graph", "kinase_feedback"]
    solver_kind: Literal["directed_conditional_irls"] = "directed_conditional_irls"
    objective_trace_semantics: Literal["paired_frozen_parent_baseline_candidate"] = (
        "paired_frozen_parent_baseline_candidate"
    )
    convergence_measure: Literal["maximum_undamped_fixed_point_residual"] = (
        "maximum_undamped_fixed_point_residual"
    )
    converged: bool
    iterations: int = Field(ge=0, le=2_000)
    final_objective: float = Field(ge=0.0)
    max_update: float = Field(ge=0.0)
    objective_trace: tuple[float, ...] = Field(min_length=1, max_length=2_001)
    trace_digest: Sha256Digest


class SolverDiagnostics(FrozenModel):
    first_pass: SolverPassDiagnostics
    second_pass: SolverPassDiagnostics


class DriverContribution(FrozenModel):
    driver_id: Identifier
    driver_type: Literal["observation", "edge", "kinase_feedback"]
    signed_contribution: float
    strength: float = Field(ge=0.0)


class AblationEffect(FrozenModel):
    kind: AblationKind
    omitted: Identifier
    activity_delta: float


class NodeInference(FrozenModel):
    node_id: Identifier
    kind: NodeKind
    activity: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    classification: StateClassification
    support: InferenceSupport
    evidence_count: int = Field(ge=0, le=MAX_OBSERVATIONS)
    observed_count: int = Field(ge=0, le=MAX_OBSERVATIONS)
    censored_count: int = Field(ge=0, le=MAX_OBSERVATIONS)
    stability: float | None = Field(default=None, ge=0.0, le=1.0)
    discordance: float | None = Field(default=None, ge=0.0, le=1.0)
    top_drivers: tuple[DriverContribution, ...] = Field(default=(), max_length=5)
    ablation_effects: tuple[AblationEffect, ...] = Field(default=(), max_length=16)
    abstention_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def estimate_fields_are_coherent(self) -> Self:
        numeric = (self.activity, self.lower_bound, self.upper_bound)
        if self.support is InferenceSupport.ABSTAINED:
            if any(item is not None for item in numeric):
                raise ValueError("abstained states cannot carry estimates")
            if self.classification is not StateClassification.NOT_ESTIMABLE:
                raise ValueError("abstained states must be not_estimable")
            if self.abstention_reason is None:
                raise ValueError("abstained states require a reason")
        else:
            if any(item is None for item in numeric):
                raise ValueError("estimated states require activity and interval")
            activity = cast("float", self.activity)
            lower_bound = cast("float", self.lower_bound)
            upper_bound = cast("float", self.upper_bound)
            if not lower_bound <= activity <= upper_bound:
                raise ValueError("inference interval must contain activity")
            if self.classification is StateClassification.NOT_ESTIMABLE:
                raise ValueError("estimated states cannot be not_estimable")
            if self.abstention_reason is not None:
                raise ValueError("estimated states cannot carry an abstention reason")
        return self


class KinaseInference(NodeInference):
    kind: Literal[NodeKind.KINASE] = NodeKind.KINASE
    mapped_substrates: int = Field(ge=0, le=MAX_NODES)
    rank_statistic: float | None = Field(default=None, ge=-1.0, le=1.0)
    enrichment_score: float | None = None
    null_standard_deviation: float | None = Field(default=None, gt=0.0)
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    q_value: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def enrichment_fields_match_substrate_support(self) -> Self:
        values = (
            self.rank_statistic,
            self.enrichment_score,
            self.null_standard_deviation,
            self.p_value,
            self.q_value,
        )
        if self.mapped_substrates < 3 and any(value is not None for value in values):
            raise ValueError("kinases with fewer than three substrates must abstain")
        if self.mapped_substrates >= 3 and any(value is None for value in values):
            raise ValueError("mapped kinase enrichment requires score, p-value, and q-value")
        return self


class ExternalKinaseMatch(FrozenModel):
    kinase_id: Identifier
    local_activity: float
    external_activity: float
    interval_overlap: bool
    direction_agreement: bool
    activity_difference: float


class ExternalKinaseComparison(FrozenModel):
    profile_id: Identifier
    source_digest: Sha256Digest
    matches: tuple[ExternalKinaseMatch, ...] = Field(max_length=MAX_KINASES)
    unmatched_local_ids: tuple[Identifier, ...] = Field(max_length=MAX_KINASES)
    external_ids_with_abstained_local_estimates: tuple[Identifier, ...] = Field(
        max_length=MAX_KINASES
    )
    rank_correlation: float | None = Field(default=None, ge=-1.0, le=1.0)
    note: NonEmptyStr


class ResearchProvenance(FrozenModel):
    engine: Literal["glio-ecgi/1.0.0"] = "glio-ecgi/1.0.0"
    numpy_version: NonEmptyStr
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    computational_digest: Sha256Digest
    deterministic_seed: int = Field(ge=0, le=MAX_JSON_SAFE_INTEGER)
    observation_source_digests: tuple[Sha256Digest, ...] = Field(
        default=(), max_length=MAX_OBSERVATIONS
    )
    topology: TopologyProvenance | None = None
    demo_graph_digest: Sha256Digest


class ProteogenomicStateResult(FrozenModel):
    algorithm_id: Literal["glio-ecgi"] = "glio-ecgi"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["glio-ecgi/1.0.0"] = "glio-ecgi/1.0.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    solver: SolverDiagnostics
    node_states: tuple[NodeInference, ...] = Field(max_length=MAX_NODES)
    kinase_states: tuple[KinaseInference, ...] = Field(max_length=MAX_KINASES)
    external_kinase_comparison: ExternalKinaseComparison | None = None
    provenance: ResearchProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True

    @model_validator(mode="after")
    def receipt_is_content_bound(self) -> Self:
        inferred_states = (*self.node_states, *self.kinase_states)
        if any(state.support is InferenceSupport.SUPPORTED for state in inferred_states):
            raise ValueError(
                "glio-ecgi/1.0.0 authoritative results cannot claim supported inference"
            )
        if self.request_digest != self.provenance.request_digest:
            raise ValueError("provenance request digest does not match result")
        if self.profile_digest != self.provenance.profile_digest:
            raise ValueError("provenance profile digest does not match result")
        identifiers = tuple(state.node_id for state in self.node_states) + tuple(
            state.node_id for state in self.kinase_states
        )
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("result node states must be unique")
        if self.result_digest != result_payload_digest(self):
            raise ValueError("result digest does not match canonical result content")
        return self


class UnverifiedProteogenomicStateResult(FrozenModel):
    """Structurally typed receipt supplied to replay before integrity checks."""

    algorithm_id: Literal["glio-ecgi"] = "glio-ecgi"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["glio-ecgi/1.0.0"] = "glio-ecgi/1.0.0"
    profile_digest: Sha256Digest
    request_digest: Sha256Digest
    result_digest: Sha256Digest
    sample_id: Identifier
    solver: SolverDiagnostics
    node_states: tuple[NodeInference, ...] = Field(max_length=MAX_NODES)
    kinase_states: tuple[KinaseInference, ...] = Field(max_length=MAX_KINASES)
    external_kinase_comparison: ExternalKinaseComparison | None = None
    provenance: ResearchProvenance
    limitations: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    research_use_only: Literal[True] = True
    non_prescriptive: Literal[True] = True


class ReplayVerificationRequest(FrozenModel):
    request: ProteogenomicStateRequest
    result: ProteogenomicStateResult | UnverifiedProteogenomicStateResult


class ReplayVerificationResult(FrozenModel):
    verified: bool
    request_digest_match: bool
    profile_digest_match: bool
    solver_trace_match: bool
    result_digest_match: bool
    semantic_match: bool
    provided_result_digest: Sha256Digest
    recomputed_result_digest: Sha256Digest
    recomputed_request_digest: Sha256Digest
    message: NonEmptyStr


class AlgorithmConstants(FrozenModel):
    solver_semantics: Literal["directed_conditional_irls"]
    sweep_update_policy: Literal["synchronous_frozen_parent"]
    objective_trace_policy: Literal["paired_frozen_parent_baseline_candidate"]
    computational_digest_policy: Literal["explicit_numerical_projection_v1"]
    first_pass_edge_policy: Literal["exclude_kinase_substrate"]
    second_pass_kinase_edge_policy: Literal["supported_feedback_sources_only"]
    secondary_convergence_policy: Literal["relaxed_then_full_or_fail"]
    ablation_policy: Literal["full_two_pass_reestimate"]
    ablation_permutation_policy: Literal["common_base_computational_request_domain"]
    left_censor_support_policy: Literal["binding_upper_bound_or_independent_directed_evidence"]
    bootstrap_kinase_policy: Literal["conditional_supported_kinase_rescore"]
    bootstrap_sampling_policy: Literal["antithetic_normal_v1"]
    huber_delta: float = Field(gt=0.0)
    ridge_penalty: float = Field(gt=0.0)
    complex_coherence_weight: float = Field(gt=0.0)
    essential_bottleneck_weight: float = Field(gt=0.0)
    damping: float = Field(gt=0.0, le=1.0)
    tolerance: float = Field(gt=0.0)
    max_iterations: int = Field(gt=0)
    relaxed_tolerance: float = Field(gt=0.0)
    relaxed_max_iterations: int = Field(gt=0)
    objective_increase_tolerance: float = Field(ge=0.0)
    backtracking_steps: int = Field(gt=0)
    backtracking_factor: float = Field(gt=0.0, lt=1.0)
    activation_threshold: float = Field(gt=0.0)
    quantization_decimals: int = Field(ge=0, le=15)
    kinase_q_threshold: float = Field(gt=0.0, le=1.0)
    kinase_min_substrates: int = Field(ge=3, le=MAX_NODES)
    kinase_null_sd_floor: float = Field(gt=0.0)
    kinase_null_ddof: Literal[1] = 1
    kinase_score_clip: float = Field(gt=0.0)
    kinase_feedback_standard_error: float = Field(gt=0.0)
    kinase_feedback_weight: float = Field(gt=0.0)
    empirical_p_pseudocount: float = Field(gt=0.0)
    rank_center: float = Field(gt=0.0, lt=1.0)
    reliability_stratum_q1: float = Field(gt=0.0, le=0.33)
    reliability_stratum_q2: float = Field(gt=0.33, le=0.66)
    reliability_stratum_q3: float = Field(gt=0.66, lt=1.0)
    min_stratified_site_count: int = Field(ge=2)
    bootstrap_perturbation_scale: float = Field(gt=0.0)
    interval_lower_quantile: float = Field(ge=0.0, lt=0.5)
    interval_upper_quantile: float = Field(gt=0.5, le=1.0)
    bootstrap_quantile_method: Literal["linear"] = "linear"
    max_top_drivers: int = Field(ge=1, le=5)
    discordance_scale: float = Field(gt=0.0)
    min_rank_correlation_pairs: int = Field(ge=2, le=MAX_KINASES)
    random_seed_bytes: int = Field(ge=4, le=32)
    random_seed_modulus: int = Field(ge=2, le=MAX_JSON_SAFE_INTEGER + 1)


class RelationWeight(FrozenModel):
    kind: EdgeKind
    weight: float = Field(gt=0.0)


class AlgorithmLimits(FrozenModel):
    max_nodes: Literal[256] = 256
    max_edges: Literal[2048] = 2_048
    max_observations: Literal[4096] = 4_096
    max_kinases: Literal[128] = 128
    max_request_bytes: Literal[2097152] = 2_097_152
    max_result_bytes: Literal[4194304] = 4_194_304
    max_bootstrap_replicates: Literal[256] = 256
    max_permutation_replicates: Literal[2048] = 2_048


class AlgorithmProfile(FrozenModel):
    algorithm_id: Literal["glio-ecgi"] = "glio-ecgi"
    algorithm_version: Literal["1.0.0"] = "1.0.0"
    profile_id: Literal["glio-ecgi/1.0.0"] = "glio-ecgi/1.0.0"
    numpy_version: NonEmptyStr
    constants: AlgorithmConstants
    limits: AlgorithmLimits
    relation_weights: tuple[RelationWeight, ...]
    demo_graph_digest: Sha256Digest
    demo_topology_provenance_digest: Sha256Digest
    profile_digest: Sha256Digest
    claim_ceiling: Literal["limited_unvalidated_caller_graph"] = "limited_unvalidated_caller_graph"
    safety_class: Literal["research_use_only"] = "research_use_only"
    interpretation: Literal["non_prescriptive"] = "non_prescriptive"


__all__ = [
    "ALGORITHM_ID",
    "ALGORITHM_VERSION",
    "MAX_BOOTSTRAPS",
    "MAX_EDGES",
    "MAX_JSON_SAFE_INTEGER",
    "MAX_KINASES",
    "MAX_NODES",
    "MAX_OBSERVATIONS",
    "MAX_PERMUTATIONS",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "PROFILE_ID",
    "AblationEffect",
    "AblationKind",
    "AlgorithmConstants",
    "AlgorithmLimits",
    "AlgorithmProfile",
    "DriverContribution",
    "EdgeKind",
    "EvidenceModality",
    "EvidenceObservation",
    "EvidenceState",
    "ExternalKinaseComparison",
    "ExternalKinaseEstimate",
    "ExternalKinaseMatch",
    "ExternalKinaseProfile",
    "GraphEdge",
    "GraphNode",
    "InferenceSupport",
    "KinaseInference",
    "NodeInference",
    "NodeKind",
    "ProteogenomicStateRequest",
    "ProteogenomicStateResult",
    "PublicTopologySource",
    "RelationWeight",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "ResearchProvenance",
    "SolverDiagnostics",
    "SolverPassDiagnostics",
    "StateClassification",
    "TopologyProvenance",
    "UnverifiedProteogenomicStateResult",
]
