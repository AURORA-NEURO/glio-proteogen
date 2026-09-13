"""M14-compatible facade for exact Neftel bulk protein-program evidence."""

from glio_proteogen.research.neftel_protein_programs import (
    DEMO_ID,
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    ProteinProgramRequest,
    ProteinProgramResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)

from .contracts import (
    FACADE_ID,
    FACADE_PROFILE_ID,
    FACADE_VERSION,
    ROUTE_PREFIX,
    M14FacadeClaimCeiling,
    M14FacadeDelegation,
    M14MicroenvironmentProteinProgramsFacadeProfile,
    M14ResponsibilityBoundary,
    M14ResponsibilityDisposition,
)
from .service import (
    analyze_m14_microenvironment_program_evidence,
    m14_facade_demo,
    m14_facade_profile,
    verify_m14_microenvironment_program_replay,
)

__all__ = [
    "DEMO_ID",
    "FACADE_ID",
    "FACADE_PROFILE_ID",
    "FACADE_VERSION",
    "MAX_REPLAY_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "ROUTE_PREFIX",
    "M14FacadeClaimCeiling",
    "M14FacadeDelegation",
    "M14MicroenvironmentProteinProgramsFacadeProfile",
    "M14ResponsibilityBoundary",
    "M14ResponsibilityDisposition",
    "ProteinProgramRequest",
    "ProteinProgramResult",
    "ReplayVerificationRequest",
    "ReplayVerificationResult",
    "analyze_m14_microenvironment_program_evidence",
    "m14_facade_demo",
    "m14_facade_profile",
    "verify_m14_microenvironment_program_replay",
]
