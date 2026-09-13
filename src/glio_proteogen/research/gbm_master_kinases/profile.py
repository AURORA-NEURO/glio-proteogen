"""Content-bound numerical profile for independent SPHINKS signature concordance."""

from __future__ import annotations

import hashlib
from importlib.resources import files
from typing import Final

import numpy as np

from .canonical import sha256_digest
from .catalog import master_kinase_catalog
from .contracts import (
    LOCATION_SEARCH_BOUND,
    LOCATION_SOLVER_ITERATIONS,
    MAX_COMPUTATIONAL_WORK_UNITS,
    WORK_ACTIVE_MEMBERSHIP_BOOTSTRAP_WEIGHT,
    WORK_ACTIVE_OBSERVATION_BOOTSTRAP_WEIGHT,
    WORK_FIXED_HYPOTHESIS_PERMUTATION_OVERHEAD,
    WORK_OBSERVED_BACKGROUND_BOOTSTRAP_WEIGHT,
    WORK_OBSERVED_MEMBERSHIP_BOOTSTRAP_WEIGHT,
    WORK_OBSERVED_MEMBERSHIP_PERMUTATION_WEIGHT,
    MasterKinaseAlgorithmConstants,
    MasterKinaseProfile,
)
from .demo import DEMO_ID, demo_request_digest

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
EXPECTED_DEMO_RESULT_ORACLE_DIGEST: Final = (
    "sha256:4422b04b101b76beba530e0cb61f52ac4f89f805a3d5b75c04d0326a46762238"
)
_COMPUTATIONAL_SOURCE_FILES: Final = ("canonical.py", "engine.py")

CONSTANTS = MasterKinaseAlgorithmConstants(
    location_estimator="collapsed_site_one_sided_huber_bisection_v2",
    duplicate_edge_policy="mean_svm_probability_per_kinase_site_v1",
    rank_estimator="residue_stratified_competitive_weighted_rank_v2",
    bootstrap_policy="request_digest_seeded_normal_and_symmetric_limit_v2",
    subtype_pooling_policy="robust_source_mww_weighted_complete_tracks_v2",
    rank_null_policy=("two_sided_residue_stratified_observation_tuple_permutation_fixed24_bh_v2"),
    work_budget_policy="active_background_membership_replicate_units_v1",
    huber_delta=1.345,
    standard_error_floor=0.25,
    location_ridge=1e-6,
    location_solver_iterations=LOCATION_SOLVER_ITERATIONS,
    location_search_bound=LOCATION_SEARCH_BOUND,
    activation_threshold=0.25,
    minimum_location_sites=3,
    supported_minimum_sites=5,
    supported_minimum_observed_sites=3,
    supported_minimum_coverage=0.02,
    supported_minimum_effective_sample_size=4.0,
    minimum_rank_signature_sites=3,
    minimum_rank_background=20,
    supported_minimum_rank_background=64,
    minimum_residue_stratum_competitors=3,
    rank_q_threshold=0.10,
    interval_lower_quantile=0.05,
    interval_upper_quantile=0.95,
    minimum_bootstrap_success_fraction=0.80,
    quantization_decimals=6,
    random_seed_bytes=8,
    default_bootstrap_replicates=64,
    default_permutation_replicates=256,
    subtype_minimum_estimated_kinases=2,
    subtype_minimum_estimated_fraction=0.5,
    subtype_minimum_supported_kinases=2,
    max_computational_work_units=MAX_COMPUTATIONAL_WORK_UNITS,
    work_active_observation_bootstrap_weight=WORK_ACTIVE_OBSERVATION_BOOTSTRAP_WEIGHT,
    work_observed_background_bootstrap_weight=WORK_OBSERVED_BACKGROUND_BOOTSTRAP_WEIGHT,
    work_active_membership_bootstrap_weight=WORK_ACTIVE_MEMBERSHIP_BOOTSTRAP_WEIGHT,
    work_observed_membership_bootstrap_weight=WORK_OBSERVED_MEMBERSHIP_BOOTSTRAP_WEIGHT,
    work_observed_membership_permutation_weight=(WORK_OBSERVED_MEMBERSHIP_PERMUTATION_WEIGHT),
    work_fixed_hypothesis_permutation_overhead=(WORK_FIXED_HYPOTHESIS_PERMUTATION_OVERHEAD),
)


def computational_source_digest() -> str:
    """Bind normalized source text that defines numerical and oracle semantics."""

    root = files(__package__)
    source_hashes = {
        name: _normalized_python_source_digest(root.joinpath(name).read_bytes())
        for name in _COMPUTATIONAL_SOURCE_FILES
    }
    return sha256_digest(source_hashes)


def _normalized_python_source_digest(content: bytes) -> str:
    text = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def algorithm_profile() -> MasterKinaseProfile:
    """Return the immutable profile binding source bytes and numerical semantics."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("SPHINKS signature concordance requires NumPy 2.5.2")
    catalog = master_kinase_catalog()
    demo_digest = demo_request_digest()
    engine_digest = computational_source_digest()
    payload = {
        "algorithm_id": "sphinks-gbm-master-kinase-concordance",
        "algorithm_version": "1.0.0",
        "catalog_artifact_digest": catalog.artifact_digest,
        "catalog_content_digest": catalog.content_digest,
        "constants": CONSTANTS.model_dump(mode="json"),
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_digest,
        "demo_result_oracle_digest": EXPECTED_DEMO_RESULT_ORACLE_DIGEST,
        "engine_source_digest": engine_digest,
        "interpretation": "independent_signature_concordance_non_prescriptive",
        "kinase_alias_digest": catalog.alias_digest,
        "numpy_version": np.__version__,
        "profile_id": "sphinks-gbm-master-kinase-concordance/1.0.0",
        "safety_class": "research_use_only",
        "source_workbook_digest": catalog.source_sha256,
        "source_attribution": f"{catalog.article_authors}, {catalog.article_title}",
        "source_license": catalog.source_license,
        "source_license_url": catalog.source_license_url,
        "source_transformation_notice": catalog.transformation_notice,
        "table5a_background_label_digest": catalog.background_label_digest,
        "table5a_background_tuple_digest": catalog.background_tuple_digest,
        "table5d_signature_edge_digest": catalog.signature_edge_digest,
        "table5e_master_kinase_digest": catalog.master_kinase_digest,
    }
    return MasterKinaseProfile(
        constants=CONSTANTS,
        numpy_version=np.__version__,
        catalog_content_digest=catalog.content_digest,
        catalog_artifact_digest=catalog.artifact_digest,
        source_workbook_digest=catalog.source_sha256,
        table5a_background_tuple_digest=catalog.background_tuple_digest,
        table5a_background_label_digest=catalog.background_label_digest,
        table5d_signature_edge_digest=catalog.signature_edge_digest,
        table5e_master_kinase_digest=catalog.master_kinase_digest,
        kinase_alias_digest=catalog.alias_digest,
        engine_source_digest=engine_digest,
        demo_id=DEMO_ID,
        demo_request_digest=demo_digest,
        demo_result_oracle_digest=EXPECTED_DEMO_RESULT_ORACLE_DIGEST,
        source_attribution=f"{catalog.article_authors}, {catalog.article_title}",
        source_license="CC-BY-4.0",
        source_license_url="https://creativecommons.org/licenses/by/4.0/",
        source_transformation_notice=catalog.transformation_notice,
        profile_digest=sha256_digest(payload),
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_DEMO_RESULT_ORACLE_DIGEST",
    "EXPECTED_NUMPY_VERSION",
    "algorithm_profile",
    "computational_source_digest",
]
