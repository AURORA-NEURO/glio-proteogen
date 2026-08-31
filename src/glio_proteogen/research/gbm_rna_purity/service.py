"""Stateless analyze/replay facade for the GBMPurity NumPy lane."""

from __future__ import annotations

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest, semantic_result_equal
from .contracts import (
    GbmRnaPurityReplayVerificationRequest,
    GbmRnaPurityReplayVerificationResult,
    GbmRnaPurityRequest,
    GbmRnaPurityResult,
)
from .engine import analyze_gbm_rna_purity as _analyze
from .profile import algorithm_profile


class GbmRnaPurityService:
    def analyze(
        self,
        request: GbmRnaPurityRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> GbmRnaPurityResult:
        return analyze_gbm_rna_purity(request, cancellation=cancellation)

    def verify(
        self,
        verification: GbmRnaPurityReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> GbmRnaPurityReplayVerificationResult:
        return verify_gbm_rna_purity_replay(verification, cancellation=cancellation)


def analyze_gbm_rna_purity(
    request: GbmRnaPurityRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmRnaPurityResult:
    return _analyze(request, cancellation=cancellation)


def verify_gbm_rna_purity_replay(
    verification: GbmRnaPurityReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> GbmRnaPurityReplayVerificationResult:
    checkpoint(cancellation)
    provided = verification.result
    request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_gbm_rna_purity(
        verification.request,
        cancellation=cancellation,
    )
    profile = algorithm_profile()
    request_match = (
        provided.request_digest == request_digest and recomputed.request_digest == request_digest
    )
    profile_match = (
        provided.profile_digest == profile.profile_digest
        and recomputed.profile_digest == profile.profile_digest
    )
    provided_digest_valid = provided.result_digest == result_payload_digest(provided)
    result_match = provided_digest_valid and provided.result_digest == recomputed.result_digest
    semantic_match = semantic_result_equal(provided, recomputed)
    verified = request_match and profile_match and result_match and semantic_match
    checkpoint(cancellation)
    return GbmRnaPurityReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        semantic_match=semantic_match,
        recomputed_request_digest=request_digest,
        provided_result_digest=provided.result_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches the deterministic GBMPurity NumPy receipt."
            if verified
            else "Replay differs from the supplied receipt; no purity estimate is accepted."
        ),
    )


__all__ = [
    "GbmRnaPurityService",
    "analyze_gbm_rna_purity",
    "verify_gbm_rna_purity_replay",
]
