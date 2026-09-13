"""Content-bound numerical profile for KNCC longitudinal protein concordance."""

from __future__ import annotations

import ast
from importlib.resources import files
from typing import Final

import numpy as np

from .canonical import profile_payload_digest, sha256_digest
from .catalog import EXPECTED_MODEL_ID, longitudinal_gbm_catalog
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalAlgorithmConstants,
    LongitudinalGbmProfile,
    LongitudinalSourceModelCounts,
    LongitudinalSourceModelDigests,
)
from .demo import DEMO_ID, EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST, demo_request_digest
from .errors import SourceProfileIntegrityError

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_SOURCE_FILES: Final = ("canonical.py", "catalog.py", "engine.py")

CONSTANTS = LongitudinalAlgorithmConstants(
    transition_estimator="coefficient_weighted_huber_and_one_sided_hinge_location_v2",
    feature_scaling_policy="frozen_source_transition_scale_without_recentering_v1",
    missing_evidence_policy="missing_and_unsupported_never_become_negative_v1",
    censoring_policy="reported_log2_limit_bound_no_latent_abundance_imputation_v2",
    measurement_uncertainty_policy=(
        "numerical_seed_digest=computational_request_digest(request,catalog.content_digest); "
        "symmetric reported-value/limit draws share each "
        "(replicate_digest,time_point_index,gene_symbol) stream_v2"
    ),
    coefficient_uncertainty_policy=(
        "catalog-content numerical seed orders the frozen sparse ensemble; "
        "bootstrap_seed=first_8_bytes_sha256(numerical_seed_digest:receipt-bootstrap-v1) "
        "modulo 2^53_v2"
    ),
    uncertainty_interaction_policy="paired_bootstrap_covariance_identity_v1",
    source_processing_ablation_policy="paired_frozen_ordinary_log_projection_v1",
    top_driver_ablation_policy="paired_bound_aware_bootstrap_leave_one_driver_out_v2",
    change_point_estimator="exact_pelt_duration_normalized_transition_rate_huber_v2",
    pelt_time_axis_policy="duration_normalized_transition_rates_per_90_days_v2",
    huber_delta=1.345,
    location_ridge=1e-6,
    location_solver_iterations=80,
    location_search_bound=20.0,
    standard_error_floor=0.05,
    alignment_threshold=0.25,
    stable_threshold=0.05,
    supported_minimum_shared_genes=64,
    supported_minimum_coverage=0.50,
    supported_minimum_effective_sample_size=32.0,
    pelt_penalty=3.0,
    maximum_top_drivers=10,
    quantization_decimals=8,
    random_seed_bytes=8,
)


def _canonical_python_ast(source: bytes) -> str:
    """Return a location-free AST representation independent of checkout newlines."""

    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(
        ast.parse(text),
        annotate_fields=True,
        include_attributes=False,
    )


def engine_semantic_digest() -> str:
    """Dynamically bind the canonical ASTs that define numerical semantics."""

    root = files(__package__)
    projections = {
        name: _canonical_python_ast(root.joinpath(name).read_bytes())
        for name in _SEMANTIC_SOURCE_FILES
    }
    return sha256_digest(projections)


def algorithm_profile() -> LongitudinalGbmProfile:
    """Return the immutable profile after all source-model locks have passed."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("KNCC longitudinal concordance requires NumPy 2.5.2")
    catalog = longitudinal_gbm_catalog()
    if REQUIRED_ASSAY_COMPATIBILITY.source_profile_content_digest != catalog.content_digest:
        raise SourceProfileIntegrityError(
            "required assay compatibility attestation is not bound to the loaded source model"
        )
    counts = LongitudinalSourceModelCounts(
        excluded_specimen_label_count=catalog.excluded_specimen_label_count,
        excluded_patient_group_count=catalog.excluded_patient_group_count,
        source_file_count=catalog.source_file_count,
        fitted_feature_count=catalog.fitted_feature_count,
        nonzero_coefficient_count=catalog.nonzero_coefficient_count,
        nested_cv_outer_folds=catalog.nested_cv_outer_folds,
        nested_cv_inner_folds=catalog.nested_cv_inner_folds,
    )
    digests = LongitudinalSourceModelDigests(
        source_profile_content_digest=catalog.content_digest,
        source_profile_artifact_digest=catalog.artifact_byte_digest,
        source_file_lock_digest=catalog.source_file_lock_digest,
        cohort_oracle_digest=catalog.cohort_oracle_digest,
        feature_space_digest=catalog.feature_space_digest,
        transition_model_digest=catalog.transition_model_digest,
        coefficient_digest=catalog.coefficient_digest,
        bootstrap_digest=catalog.bootstrap_digest,
        source_processing_ablation_digest=catalog.source_processing_ablation_digest,
        hgnc_complete_set_digest=catalog.hgnc_complete_set_digest,
        source_to_hgnc_mapping_digest=catalog.source_to_hgnc_mapping_digest,
        engine_semantic_digest=engine_semantic_digest(),
    )
    payload = {
        "algorithm_id": "kncc-gbm-longitudinal-concordance",
        "algorithm_version": "1.0.0",
        "profile_id": "kncc-gbm-longitudinal-concordance/1.0.0",
        "model_id": EXPECTED_MODEL_ID,
        "required_assay_compatibility": REQUIRED_ASSAY_COMPATIBILITY.model_dump(mode="json"),
        "constants": CONSTANTS.model_dump(mode="json"),
        "counts": counts.model_dump(mode="json"),
        "digests": digests.model_dump(mode="json"),
        "numpy_version": np.__version__,
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest(),
        "demo_semantic_oracle_digest": EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
        "source_attribution": catalog.source_attribution,
        "source_license": catalog.source_license,
        "source_license_url": catalog.source_license_url,
        "source_transformation_notice": catalog.source_transformation_notice,
        "safety_class": "research_use_only",
        "claim_ceiling": ("protein_level_longitudinal_concordance_research_only_non_prescriptive"),
        "interpretation": "source_aligned_transition_evidence_not_patient_evolution",
    }
    return LongitudinalGbmProfile(
        model_id=EXPECTED_MODEL_ID,
        required_assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        constants=CONSTANTS,
        counts=counts,
        digests=digests,
        numpy_version=np.__version__,
        demo_id=DEMO_ID,
        demo_request_digest=demo_request_digest(),
        demo_semantic_oracle_digest=EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST,
        source_attribution=catalog.source_attribution,
        source_license=catalog.source_license,
        source_license_url=catalog.source_license_url,
        source_transformation_notice=catalog.source_transformation_notice,
        profile_digest=profile_payload_digest(payload),
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_NUMPY_VERSION",
    "algorithm_profile",
    "engine_semantic_digest",
]
