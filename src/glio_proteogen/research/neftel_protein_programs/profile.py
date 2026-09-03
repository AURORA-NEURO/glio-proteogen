"""Content-bound numerical profile for Neftel protein-program inference."""

from __future__ import annotations

from typing import Final

import numpy as np

from .canonical import sha256_digest
from .catalog import marker_catalog
from .contracts import NeftelAlgorithmConstants, NeftelAlgorithmProfile

EXPECTED_NUMPY_VERSION: Final = "2.5.2"

CONSTANTS = NeftelAlgorithmConstants(
    location_estimator="one_sided_huber_location_bisection_v1",
    rank_estimator="reliability_weighted_mean_percentile_rank_v1",
    bootstrap_policy="request_digest_seeded_normal_limit_perturbation_v1",
    family_pooling_policy="equal_source_program_equal_marker_mass_v1",
    rank_null_policy="two_sided_global_percentile_permutation_bh_v1",
    huber_delta=1.345,
    standard_error_floor=0.25,
    location_ridge=1e-6,
    activation_threshold=0.25,
    rank_neutral_threshold=0.10,
    rank_q_threshold=0.10,
    exploratory_minimum_active_markers=5,
    exploratory_minimum_observed_markers=3,
    exploratory_minimum_active_coverage=0.10,
    exploratory_minimum_effective_sample_size=3.0,
    supported_minimum_active_markers=10,
    supported_minimum_observed_markers=5,
    supported_minimum_active_coverage=0.30,
    supported_minimum_effective_sample_size=8.0,
    minimum_rank_background=20,
    interval_lower_quantile=0.05,
    interval_upper_quantile=0.95,
    quantization_decimals=6,
    random_seed_bytes=8,
    default_permutation_replicates=256,
)


def algorithm_profile() -> NeftelAlgorithmProfile:
    """Return the immutable profile that binds source, normalization, and constants."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("Neftel protein-program inference requires NumPy 2.5.2")
    catalog = marker_catalog()
    payload = {
        "algorithm_id": "neftel-bulk-protein-programs",
        "algorithm_version": "1.0.0",
        "catalog_artifact_digest": catalog.artifact_digest,
        "catalog_content_digest": catalog.content_digest,
        "exact_source_program_digest": catalog.source_program_digest,
        "constants": CONSTANTS.model_dump(mode="json"),
        "hgnc_source_digest": catalog.hgnc_sha256,
        "interpretation": "bulk_protein_program_evidence_non_prescriptive",
        "numpy_version": np.__version__,
        "profile_id": "neftel-bulk-protein-programs/1.0.0",
        "safety_class": "research_use_only",
        "table_s2_source_digest": catalog.source_sha256,
    }
    return NeftelAlgorithmProfile(
        constants=CONSTANTS,
        numpy_version=np.__version__,
        catalog_content_digest=catalog.content_digest,
        catalog_artifact_digest=catalog.artifact_digest,
        exact_source_program_digest=catalog.source_program_digest,
        table_s2_source_digest=catalog.source_sha256,
        hgnc_source_digest=catalog.hgnc_sha256,
        profile_digest=sha256_digest(payload),
    )


__all__ = ["CONSTANTS", "EXPECTED_NUMPY_VERSION", "algorithm_profile"]
