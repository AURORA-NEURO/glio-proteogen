"""Stateless service facade for Neftel bulk-protein program evidence."""

from __future__ import annotations

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    ProteinProgramRequest,
    ProteinProgramResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from .engine import infer_neftel_protein_programs
from .profile import algorithm_profile


def analyze_neftel_protein_programs(
    request: ProteinProgramRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ProteinProgramResult:
    """Analyze a validated request without persisting the input or result."""

    return infer_neftel_protein_programs(request, cancellation=cancellation)


def verify_neftel_protein_program_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Recompute and compare a deterministic Neftel protein-program receipt."""

    checkpoint(cancellation)
    provided = verification.result
    recomputed_request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_neftel_protein_programs(
        verification.request,
        cancellation=cancellation,
    )
    request_match = provided.request_digest == recomputed_request_digest
    profile_match = provided.profile_digest == algorithm_profile().profile_digest
    result_match = (
        provided.result_digest
        == result_payload_digest(provided.model_dump(mode="json"))
        and provided.result_digest == recomputed.result_digest
    )
    semantic_match = provided.model_dump(mode="json") == recomputed.model_dump(mode="json")
    verified = request_match and profile_match and result_match and semantic_match
    result = ReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches the deterministic bulk-protein program receipt."
            if verified
            else "Replay differs from the supplied receipt; no program claim is accepted."
        ),
    )
    checkpoint(cancellation)
    return result


__all__ = [
    "analyze_neftel_protein_programs",
    "verify_neftel_protein_program_replay",
]
