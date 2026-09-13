"""M11-compatible research facade for published bulk protein-axis evidence."""

from glio_proteogen.research.gbm_proteomic_axes import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    GbmProteomicAxesRequest,
    GbmProteomicAxesResult,
    GbmReplayVerificationRequest,
    GbmReplayVerificationResult,
)

from .contracts import (
    FACADE_ID,
    FACADE_PROFILE_ID,
    FACADE_VERSION,
    ROUTE_PREFIX,
    M11FacadeClaimCeiling,
    M11FacadeDelegation,
    M11ProteinNativeSubtypeFacadeProfile,
    M11ResponsibilityBoundary,
    M11ResponsibilityDisposition,
)
from .service import (
    analyze_m11_protein_axis_evidence,
    m11_facade_demo,
    m11_facade_profile,
    verify_m11_protein_axis_replay,
)

__all__ = [
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "ROUTE_PREFIX",
    "GbmProteomicAxesRequest",
    "GbmProteomicAxesResult",
    "GbmReplayVerificationRequest",
    "GbmReplayVerificationResult",
    "M11FacadeClaimCeiling",
    "M11FacadeDelegation",
    "M11ProteinNativeSubtypeFacadeProfile",
    "M11ResponsibilityBoundary",
    "M11ResponsibilityDisposition",
    "analyze_m11_protein_axis_evidence",
    "m11_facade_demo",
    "m11_facade_profile",
    "verify_m11_protein_axis_replay",
]
