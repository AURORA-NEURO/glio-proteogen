"""M10-compatible facade for exact Migliozzi functional-proteotype evidence."""

from glio_proteogen.research.gbm_functional_proteotype import (
    DEMO_ID,
    MAX_BOOTSTRAPS,
    MAX_OBSERVATIONS,
    MAX_PERMUTATIONS,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)

from .contracts import (
    FACADE_ID,
    FACADE_PROFILE_ID,
    FACADE_VERSION,
    ROUTE_PREFIX,
    M10FacadeClaimCeiling,
    M10FacadeDelegation,
    M10FunctionalProteotypeFacadeProfile,
    M10ResponsibilityBoundary,
    M10ResponsibilityDisposition,
)
from .service import (
    analyze_m10_functional_proteotype_evidence,
    m10_facade_demo,
    m10_facade_profile,
    verify_m10_functional_proteotype_replay,
)

__all__ = [
    "DEMO_ID",
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "MAX_BOOTSTRAPS",
    "MAX_OBSERVATIONS",
    "MAX_PERMUTATIONS",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "ROUTE_PREFIX",
    "FunctionalProteotypeRequest",
    "FunctionalProteotypeResult",
    "M10FacadeClaimCeiling",
    "M10FacadeDelegation",
    "M10FunctionalProteotypeFacadeProfile",
    "M10ResponsibilityBoundary",
    "M10ResponsibilityDisposition",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "analyze_m10_functional_proteotype_evidence",
    "m10_facade_demo",
    "m10_facade_profile",
    "verify_m10_functional_proteotype_replay",
]
