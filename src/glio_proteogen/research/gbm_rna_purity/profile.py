"""Implementation- and artifact-bound profile for the GBMPurity NumPy port."""

from __future__ import annotations

import hashlib
from importlib.resources import files
from typing import Final

import numpy as np

from .canonical import sha256_digest
from .catalog import gbm_rna_purity_catalog
from .contracts import (
    GbmRnaPurityAlgorithmConstants,
    GbmRnaPurityLimits,
    GbmRnaPurityProfile,
)
from .demo import demo_request_digest

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_COMPUTATIONAL_SOURCE_FILES: Final = (
    "canonical.py",
    "catalog.py",
    "contracts.py",
    "demo.py",
    "engine.py",
    "profile.py",
    "service.py",
)

CONSTANTS = GbmRnaPurityAlgorithmConstants()
LIMITS = GbmRnaPurityLimits()


def _source_digest(content: bytes) -> str:
    normalized = content.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return "sha256:" + hashlib.sha256(normalized.encode()).hexdigest()


def computational_source_digest() -> str:
    root = files(__package__)
    return sha256_digest(
        {
            name: _source_digest(root.joinpath(name).read_bytes())
            for name in _COMPUTATIONAL_SOURCE_FILES
        }
    )


def algorithm_profile() -> GbmRnaPurityProfile:
    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("GBMPurity inference requires NumPy 2.5.2")
    catalog = gbm_rna_purity_catalog()
    payload: dict[str, object] = {
        "schema_version": "glio-proteogen.gbm-rna-purity-profile/1.0.0",
        "algorithm_id": "gbm-rna-tumor-purity",
        "algorithm_version": "1.0.0",
        "profile_id": "gbm-rna-tumor-purity/1.0.0",
        "model_id": "gbmpurity-primary-idhwt-rna/1.0.0",
        "constants": CONSTANTS,
        "limits": LIMITS,
        "numpy_version": np.__version__,
        "converted_artifact_digest": catalog.content_digest,
        "converted_artifact_file_sha256": catalog.artifact_digest,
        "feature_order_digest": catalog.feature_order_digest,
        "weight_tensor_digest": catalog.weight_tensor_digest,
        "computational_source_digest": computational_source_digest(),
        "demo_request_digest": demo_request_digest(),
        "source_repository": "https://github.com/scmpht/GBMPurity",
        "source_commit": "af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950",
        "source_model_sha256": (
            "sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7"
        ),
        "source_gene_lengths_sha256": (
            "sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b"
        ),
        "source_license": "MIT",
        "source_article_doi": "10.1093/neuonc/noaf026",
        "source_article_license": "CC-BY-4.0",
        "intended_use": (
            "research_estimation_of_malignant_cell_fraction_in_primary_IDH_wildtype_GBM_bulk_RNA"
        ),
        "claim_ceiling": (
            "published_model_estimate_only_not_cell_type_composition_or_clinical_truth"
        ),
        "safety_class": "research_use_only",
    }
    digest_payload = {
        **payload,
        "constants": CONSTANTS.model_dump(mode="json"),
        "limits": LIMITS.model_dump(mode="json"),
    }
    return GbmRnaPurityProfile.model_validate(
        {**payload, "profile_digest": sha256_digest(digest_payload)}
    )


__all__ = [
    "CONSTANTS",
    "EXPECTED_NUMPY_VERSION",
    "LIMITS",
    "algorithm_profile",
    "computational_source_digest",
]
