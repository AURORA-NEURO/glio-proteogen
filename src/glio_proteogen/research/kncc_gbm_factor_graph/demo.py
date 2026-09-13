"""Synthetic composition of the two locked, source-model-derived KNCC demos."""

from __future__ import annotations

from functools import lru_cache

from glio_proteogen.research.longitudinal_gbm_kinase_transition.demo import (
    synthetic_demo_request as synthetic_kinase_demo_request,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.demo import (
    synthetic_demo_request as synthetic_reactome_demo_request,
)

from .canonical import canonical_request_digest
from .contracts import DEMO_ID, KnccGbmFactorGraphRequest
from .profile import algorithm_profile


@lru_cache(maxsize=1)
def synthetic_demo_request() -> KnccGbmFactorGraphRequest:
    """Return the exact Reactome and kinase synthetic requests without remapping."""

    return KnccGbmFactorGraphRequest(
        analysis_id=DEMO_ID,
        reactome_request=synthetic_reactome_demo_request(),
        kinase_request=synthetic_kinase_demo_request(),
    )


def demo_request_digest() -> str:
    """Return the content digest of the composed synthetic request."""

    return canonical_request_digest(synthetic_demo_request())


def demo_semantic_oracle_digest() -> str:
    """Return the profile-bound oracle for this exact independent composition."""

    return algorithm_profile().demo_semantic_oracle_digest


__all__ = [
    "DEMO_ID",
    "demo_request_digest",
    "demo_semantic_oracle_digest",
    "synthetic_demo_request",
]
