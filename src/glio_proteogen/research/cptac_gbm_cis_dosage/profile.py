"""Content-bound profile for local CPTAC GBM cis-dosage evidence."""

from __future__ import annotations

import ast
from importlib.resources import files
from typing import Final

import numpy as np

from glio_proteogen.kernel.canonical import sha256_digest

from .canonical import profile_digest
from .contracts import AlgorithmConstants, AlgorithmLimits, CisDosageProfile
from .source import EXACT_SOURCE_LOCKS

EXPECTED_NUMPY_VERSION: Final = "2.5.2"
_SEMANTIC_FILES: Final = (
    "artifact.py",
    "canonical.py",
    "contracts.py",
    "fitter.py",
    "model.py",
    "ooxml.py",
    "service.py",
    "source.py",
)


def _canonical_ast(source: bytes) -> str:
    text = source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ast.dump(ast.parse(text), annotate_fields=True, include_attributes=False)


def engine_semantic_digest() -> str:
    root = files(__package__)
    return sha256_digest(
        {name: _canonical_ast(root.joinpath(name).read_bytes()) for name in _SEMANTIC_FILES}
    )


def algorithm_profile() -> CisDosageProfile:
    if np.__version__ != EXPECTED_NUMPY_VERSION:
        raise RuntimeError("CPTAC GBM cis-dosage evidence requires NumPy 2.5.2")
    semantic_digest = engine_semantic_digest()
    payload = {
        "algorithm_id": "cptac-gbm-cis-dosage",
        "algorithm_version": "1.0.0",
        "profile_id": "cptac-gbm-cis-dosage/1.0.0",
        "engine_semantic_digest": semantic_digest,
        "numpy_version": np.__version__,
        "constants": AlgorithmConstants().model_dump(mode="json"),
        "limits": AlgorithmLimits().model_dump(mode="json"),
        "exact_source_locks": [lock.model_dump(mode="json") for lock in EXACT_SOURCE_LOCKS],
        "artifact_schema": "cptac-gbm-cis-dosage-artifact/1.0.0",
        "redistribution_status": "local_only_terms_unverified",
        "public_http_mounted": False,
        "runtime_behavior": "cohort_fitted_gene_query_never_patient_scoring",
        "claim_ceiling": "observational_cohort_association_not_causal",
        "table_s3_semantics": "positive_flag_or_not_reported_positive_never_negative",
        "local_trust_boundary": "same_user_local_artifact_integrity_only",
        "cross_user_authenticity": "signed_manifest_required_not_provided",
    }
    return CisDosageProfile(
        engine_semantic_digest=semantic_digest,
        constants=AlgorithmConstants(),
        limits=AlgorithmLimits(),
        exact_source_locks=EXACT_SOURCE_LOCKS,
        profile_digest=profile_digest(payload),
    )


__all__ = ["EXPECTED_NUMPY_VERSION", "algorithm_profile", "engine_semantic_digest"]
