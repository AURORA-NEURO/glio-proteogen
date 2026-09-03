"""Content-bound profile for the published GBM proteomic-axis model port."""

from __future__ import annotations

from functools import lru_cache
from typing import Final

import numpy as np

from glio_proteogen.kernel.canonical import sha256_digest

from .contracts import (
    GbmModelSource,
    GbmProteomicAxesConstants,
    GbmProteomicAxesLimits,
    GbmProteomicAxesProfile,
    GbmSignatureProfile,
)
from .data.predictor import (
    ARTIFACT_SHA256,
    MODEL_FEATURE_COUNT,
    MODEL_SOURCE_SHA256,
    SOURCE_COMMIT,
    SOURCE_REPOSITORY_URL,
    SUPPORTED_SIGNATURES,
    TREES_PER_SIGNATURE,
)
from .demo import demo_request_digest

_EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_NUMPY_VERSION_ERROR: Final = "GBM proteomic axes require the profile-pinned NumPy runtime"


def _namespaced_sha256(value: str) -> str:
    """Normalize predictor file hashes into the public digest namespace."""

    return value if value.startswith("sha256:") else f"sha256:{value}"

CONSTANTS = GbmProteomicAxesConstants(
    normalization_method="positive_lfq_geometric_mean_to_1e7",
    missing_feature_policy="published_numeric_zero_fill",
    missing_feature_interpretation="not_biological_absence",
    left_censored_point_policy="excluded_from_point_prediction",
    bootstrap_sampling_policy="observed_lfq_log2_normal_v1",
)
LIMITS = GbmProteomicAxesLimits()

_SIGNATURE_ROWS = (
    ("SWEET_KRAS_TARGETS_UP", "KRAS-like proteomic axis", "triple_axis"),
    ("HALLMARK_MYC_TARGETS_V1", "MYC-like proteomic axis", "triple_axis"),
    ("WINTER_HYPOXIA_UP", "Hypoxia proteomic axis", "triple_axis"),
    ("VERHAAK_GLIOBLASTOMA_MESENCHYMAL", "Verhaak mesenchymal reference program", "gbm_reference_program"),
    ("VERHAAK_GLIOBLASTOMA_NEURAL", "Verhaak neural reference program", "gbm_reference_program"),
    ("VERHAAK_GLIOBLASTOMA_PRONEURAL", "Verhaak proneural reference program", "gbm_reference_program"),
    ("EGFR_UP.V1_UP", "EGFR-up reference program", "egfr_program"),
)

SIGNATURES = tuple(
    GbmSignatureProfile(
        signature_id=signature_id,
        display_name=display_name,
        role=role,  # type: ignore[arg-type]
    )
    for signature_id, display_name, role in _SIGNATURE_ROWS
)
SOURCE = GbmModelSource(
    paper_title=(
        "Topographic mapping of the glioblastoma proteome reveals a triple-axis model "
        "of intra-tumoral heterogeneity"
    ),
    paper_url="https://www.nature.com/articles/s41467-021-27667-w",
    repository_url=SOURCE_REPOSITORY_URL,
    repository_commit=SOURCE_COMMIT,
    original_model_digest=_namespaced_sha256(MODEL_SOURCE_SHA256),
    converted_artifact_digest=_namespaced_sha256(ARTIFACT_SHA256),
    conversion_note=(
        "A deterministic NumPy port of seven unchanged 600-tree depth-one XGBoost ensembles; "
        "the bundled artifact is verified before use and oracle-checked against published output."
    ),
)


@lru_cache(maxsize=1)
def algorithm_profile() -> GbmProteomicAxesProfile:
    """Return the immutable numerical, provenance, and interpretation profile."""

    if np.__version__ != _EXPECTED_NUMPY_VERSION:
        raise RuntimeError(_NUMPY_VERSION_ERROR)
    if MODEL_FEATURE_COUNT != 3_025 or TREES_PER_SIGNATURE != 600:
        raise RuntimeError("bundled GBM model dimensions differ from the public profile")
    if tuple(SUPPORTED_SIGNATURES) != tuple(item.signature_id for item in SIGNATURES):
        raise RuntimeError("bundled GBM signature identifiers differ from the public profile")
    payload = {
        "algorithm_id": "gbm-proteomic-axes",
        "algorithm_version": "1.0.0",
        "profile_id": "gbm-proteomic-axes/1.0.0",
        "numpy_version": np.__version__,
        "constants": CONSTANTS.model_dump(mode="json"),
        "limits": LIMITS.model_dump(mode="json"),
        "signatures": [item.model_dump(mode="json") for item in SIGNATURES],
        "source": SOURCE.model_dump(mode="json"),
        "demo_request_digest": demo_request_digest(),
        "safety_class": "research_use_only",
        "interpretation": "non_prescriptive",
    }
    return GbmProteomicAxesProfile(
        numpy_version=np.__version__,
        constants=CONSTANTS,
        limits=LIMITS,
        signatures=SIGNATURES,
        source=SOURCE,
        demo_request_digest=demo_request_digest(),
        profile_digest=sha256_digest(payload),
    )


def signature_display_name(signature_id: str) -> str:
    return next(item.display_name for item in SIGNATURES if item.signature_id == signature_id)


__all__ = [
    "CONSTANTS",
    "LIMITS",
    "SIGNATURES",
    "SOURCE",
    "algorithm_profile",
    "signature_display_name",
]
