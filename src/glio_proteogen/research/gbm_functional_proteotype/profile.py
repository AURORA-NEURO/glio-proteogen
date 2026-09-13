"""Content-bound numerical profile for GBM functional-proteotype concordance."""

from __future__ import annotations

import hashlib
from importlib.resources import files
from typing import Final

import numpy as np

from .canonical import sha256_digest
from .catalog import functional_proteotype_catalog
from .contracts import (
    AXIS_ORDER,
    AxisCatalogProfile,
    FunctionalProteotypeAlgorithmConstants,
    FunctionalProteotypeLimits,
    FunctionalProteotypeProfile,
)
from .demo import DEMO_ID, demo_request_digest

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_COMPUTATIONAL_SOURCE_FILES: Final = (
    "canonical.py",
    "catalog.py",
    "contracts.py",
    "engine.py",
    "profile.py",
    "solver.py",
    "statistics.py",
)

CONSTANTS = FunctionalProteotypeAlgorithmConstants(
    loading_policy="source_mww_median_normalized_axis_loading_v1",
    location_solver="huber_irls_kkt_sum_to_zero_v1",
    censoring_loss="one_sided_upper_bound_huber_hinge_v1",
    damping_policy="monotone_backtracking_v1",
    bootstrap_policy="request_digest_seeded_normal_limit_perturbation_v1",
    rank_estimator="tie_corrected_mann_whitney_rank_biserial_v1",
    rank_null_policy="source_rank_quartile_stratified_two_sided_bh_v1",
    ablation_policy="quartile_state_and_top_driver_refit_v1",
    huber_delta=1.345,
    standard_error_floor=0.25,
    axis_ridge_penalty=1e-4,
    intercept_ridge_penalty=1e-6,
    coordinate_tolerance=1e-8,
    gradient_tolerance=1e-7,
    maximum_solver_iterations=64,
    initial_damping=1.0,
    minimum_damping=1.0 / 32_768.0,
    backtracking_factor=0.5,
    maximum_backtracking_steps=16,
    objective_increase_tolerance=1e-12,
    exploratory_minimum_active_proteins=6,
    supported_minimum_active_proteins=15,
    supported_minimum_observed_proteins=10,
    supported_minimum_active_fraction=0.10,
    supported_minimum_effective_sample_size=8.0,
    minimum_rank_signature_proteins=3,
    minimum_rank_background_proteins=20,
    rank_q_threshold=0.10,
    minimum_bootstrap_success_fraction=0.80,
    minimum_interval_bootstrap_replicates=16,
    quantization_decimals=6,
    random_seed_bytes=8,
    default_bootstrap_replicates=64,
    default_permutation_replicates=256,
    top_driver_limit=8,
    pathway_context_limit=8,
)

LIMITS = FunctionalProteotypeLimits()


def _normalized_python_source_digest(content: bytes) -> str:
    text = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def computational_source_digest() -> str:
    """Bind normalized source text that determines numerical semantics."""

    root = files(__package__)
    source_hashes = {
        name: _normalized_python_source_digest(root.joinpath(name).read_bytes())
        for name in _COMPUTATIONAL_SOURCE_FILES
    }
    return sha256_digest(source_hashes)


def random_stream_profile_digest(profile: FunctionalProteotypeProfile) -> str:
    """Bind numerical stream inputs without coupling RNG draws to source comments."""

    return sha256_digest(
        {
            "catalog_content_digest": profile.catalog_content_digest,
            "constants": profile.constants.model_dump(mode="json"),
            "numpy_version": profile.numpy_version,
            "profile_id": profile.profile_id,
            "signature_catalog_digest": profile.signature_catalog_digest,
            "stream_identity_schema": "gbm-functional-proteotype-rng/1.0.0",
        }
    )


def _source_text(source: dict[str, object], field: str) -> str:
    value = source.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"functional-proteotype catalog source.{field} is invalid")
    return value


def algorithm_profile() -> FunctionalProteotypeProfile:
    """Return the immutable source, implementation, and constant-bound profile."""

    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("GBM functional-proteotype inference requires NumPy 2.5.2")
    catalog = functional_proteotype_catalog()
    source_digest = _source_text(catalog.source, "source_sha256")
    if source_digest != ("sha256:865a2db1ec99dcf047d6ff56b313a21607b840e5239bb9184739f6f6f217fb88"):
        raise RuntimeError("functional-proteotype catalog source workbook is not pinned")

    axis_profiles = tuple(
        AxisCatalogProfile(
            axis=axis,
            pathway_count=len(catalog.source_cohort_pathway_context[axis.value]),
            signature_digest=catalog.axis_signature_digests[axis.value],
            pathway_digest=catalog.axis_pathway_digests[axis.value],
        )
        for axis in AXIS_ORDER
    )
    payload: dict[str, object] = {
        "algorithm_id": "migliozzi-gbm-functional-proteotype",
        "algorithm_version": "1.0.0",
        "profile_id": "migliozzi-gbm-functional-proteotype/1.0.0",
        "constants": CONSTANTS.model_dump(mode="json"),
        "limits": LIMITS.model_dump(mode="json"),
        "numpy_version": np.__version__,
        "catalog_content_digest": catalog.content_digest,
        "catalog_artifact_digest": catalog.artifact_digest,
        "source_workbook_digest": source_digest,
        "signature_catalog_digest": catalog.signature_catalog_digest,
        "pathway_catalog_digest": catalog.pathway_catalog_digest,
        "engine_source_digest": computational_source_digest(),
        "axes": axis_profiles,
        "demo_id": DEMO_ID,
        "demo_request_digest": demo_request_digest(),
        "source_article_doi": _source_text(catalog.source, "article_doi"),
        "source_article_title": _source_text(catalog.source, "article_title"),
        "source_article_authors": _source_text(catalog.source, "article_authors"),
        "source_url": _source_text(catalog.source, "source_url"),
        "source_license": _source_text(catalog.source, "license"),
        "source_license_url": _source_text(catalog.source, "license_url"),
        "source_transformation_notice": _source_text(
            catalog.source,
            "transformation_notice",
        ),
        "signature_sheet_mapping": (
            "Tab 14 - Supplementary Table 2d rows 5:154; GPM A:C; MTC E:G; "
            "NEU I:K; PPR M:O; headers Gene|Protein|MWW score"
        ),
        "pathway_sheet_mapping": (
            "Tab 15 - Supplementary Table 2e rows 5:end; GPM A:D; MTC F:I; "
            "NEU K:N; PPR P:S; headers Biological pathway|logitNES|pValue|qValue"
        ),
        "safety_class": "research_use_only",
        "interpretation": "bulk_gbm_functional_proteotype_evidence_non_prescriptive",
        "claim_ceiling": ("bulk_tumor_protein_concordance_to_source_selected_cptac_gbm_signatures"),
    }
    digest_payload = {
        **payload,
        "axes": tuple(item.model_dump(mode="json") for item in axis_profiles),
    }
    return FunctionalProteotypeProfile.model_validate(
        {**payload, "profile_digest": sha256_digest(digest_payload)}
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_NUMPY_VERSION",
    "LIMITS",
    "algorithm_profile",
    "computational_source_digest",
    "random_stream_profile_digest",
]
