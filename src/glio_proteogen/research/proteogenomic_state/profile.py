"""Closed algorithm profile for the evidence-conserving graph engine."""

from __future__ import annotations

from typing import Final

import numpy as np

from .canonical import sha256_digest
from .contracts import (
    AlgorithmConstants,
    AlgorithmLimits,
    AlgorithmProfile,
    EdgeKind,
    RelationWeight,
)
from .demo import demo_graph_digest, demo_topology_provenance_digest

_EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_NUMPY_VERSION_ERROR: Final = "GLIO-ECGI requires the profile-pinned NumPy runtime"

CONSTANTS = AlgorithmConstants(
    solver_semantics="directed_conditional_irls",
    sweep_update_policy="synchronous_frozen_parent",
    objective_trace_policy="paired_frozen_parent_baseline_candidate",
    computational_digest_policy="explicit_numerical_projection_v1",
    first_pass_edge_policy="exclude_kinase_substrate",  # noqa: S106
    second_pass_kinase_edge_policy="supported_feedback_sources_only",  # noqa: S106
    secondary_convergence_policy="relaxed_then_full_or_fail",
    ablation_policy="full_two_pass_reestimate",
    ablation_permutation_policy="common_base_computational_request_domain",
    left_censor_support_policy="binding_upper_bound_or_independent_directed_evidence",
    bootstrap_kinase_policy="conditional_supported_kinase_rescore",
    bootstrap_sampling_policy="antithetic_normal_v1",
    huber_delta=1.345,
    ridge_penalty=0.035,
    complex_coherence_weight=0.45,
    essential_bottleneck_weight=1.75,
    damping=0.72,
    tolerance=1e-7,
    max_iterations=1_000,
    relaxed_tolerance=2e-5,
    relaxed_max_iterations=96,
    objective_increase_tolerance=1e-12,
    backtracking_steps=18,
    backtracking_factor=0.5,
    activation_threshold=0.25,
    quantization_decimals=8,
    kinase_q_threshold=0.10,
    kinase_min_substrates=3,
    kinase_null_sd_floor=0.05,
    kinase_null_ddof=1,
    kinase_score_clip=5.0,
    kinase_feedback_standard_error=1.0,
    kinase_feedback_weight=0.75,
    empirical_p_pseudocount=1.0,
    rank_center=0.5,
    reliability_stratum_q1=0.25,
    reliability_stratum_q2=0.50,
    reliability_stratum_q3=0.75,
    min_stratified_site_count=4,
    bootstrap_perturbation_scale=1.0,
    interval_lower_quantile=0.05,
    interval_upper_quantile=0.95,
    bootstrap_quantile_method="linear",
    max_top_drivers=5,
    discordance_scale=1.0,
    min_rank_correlation_pairs=2,
    random_seed_bytes=8,
    random_seed_modulus=2**53,
)
LIMITS = AlgorithmLimits()
RELATION_WEIGHTS = (
    RelationWeight(kind=EdgeKind.REGULATES, weight=0.75),
    RelationWeight(kind=EdgeKind.MEMBER_OF, weight=0.90),
    RelationWeight(kind=EdgeKind.KINASE_SUBSTRATE, weight=0.30),
    RelationWeight(kind=EdgeKind.PARTICIPATES_IN, weight=0.80),
    RelationWeight(kind=EdgeKind.PROTEOFORM_OF, weight=0.55),
    RelationWeight(kind=EdgeKind.SITE_OF, weight=0.20),
)


def _profile_payload() -> dict[str, object]:
    return {
        "algorithm_id": "glio-ecgi",
        "algorithm_version": "1.0.0",
        "constants": CONSTANTS.model_dump(mode="json"),
        "limits": LIMITS.model_dump(mode="json"),
        "demo_graph_digest": demo_graph_digest(),
        "demo_topology_provenance_digest": demo_topology_provenance_digest(),
        "numpy_version": np.__version__,
        "profile_id": "glio-ecgi/1.0.0",
        "relation_weights": RELATION_WEIGHTS,
        "claim_ceiling": "limited_unvalidated_caller_graph",
        "safety_class": "research_use_only",
        "interpretation": "non_prescriptive",
    }


def algorithm_profile() -> AlgorithmProfile:
    """Return the content-bound numerical and safety profile."""

    if np.__version__ != _EXPECTED_NUMPY_VERSION:
        raise RuntimeError(_NUMPY_VERSION_ERROR)
    payload = _profile_payload()
    digest_payload = {
        **payload,
        "constants": CONSTANTS.model_dump(mode="json"),
        "relation_weights": [item.model_dump(mode="json") for item in RELATION_WEIGHTS],
    }
    return AlgorithmProfile(
        numpy_version=np.__version__,
        constants=CONSTANTS,
        limits=LIMITS,
        relation_weights=RELATION_WEIGHTS,
        demo_graph_digest=demo_graph_digest(),
        demo_topology_provenance_digest=demo_topology_provenance_digest(),
        profile_digest=sha256_digest(digest_payload),
    )


def relation_weight(kind: EdgeKind) -> float:
    return next(item.weight for item in RELATION_WEIGHTS if item.kind is kind)


__all__ = ["CONSTANTS", "LIMITS", "RELATION_WEIGHTS", "algorithm_profile", "relation_weight"]
