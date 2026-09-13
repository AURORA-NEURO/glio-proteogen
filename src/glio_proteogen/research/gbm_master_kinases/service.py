"""Stateless service facade for GBM master-kinase signature concordance."""

from __future__ import annotations

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    MasterKinaseRequest,
    MasterKinaseResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from .engine import infer_master_kinases
from .profile import algorithm_profile


class MasterKinaseService:
    """Small stateless facade suitable for CLI and HTTP adapters."""

    def analyze(
        self,
        request: MasterKinaseRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> MasterKinaseResult:
        return infer_master_kinases(request, cancellation=cancellation)

    def verify(
        self,
        verification: ReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> ReplayVerificationResult:
        return verify_replay(verification, cancellation=cancellation)


def analyze_master_kinases(
    request: MasterKinaseRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> MasterKinaseResult:
    """Analyze a validated request without persisting input or output."""

    return infer_master_kinases(request, cancellation=cancellation)


def verify_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Recompute and compare an exact deterministic result receipt."""

    checkpoint(cancellation)
    provided = verification.result
    recomputed_request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_master_kinases(verification.request, cancellation=cancellation)
    request_match = provided.request_digest == recomputed_request_digest
    profile_match = provided.profile_digest == algorithm_profile().profile_digest
    result_match = (
        provided.result_digest == result_payload_digest(provided.model_dump(mode="json"))
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
            "Replay exactly matches the deterministic signature-concordance receipt."
            if verified
            else "Replay differs from the supplied receipt; no master-kinase claim is accepted."
        ),
    )
    checkpoint(cancellation)
    return result


__all__ = ["MasterKinaseService", "analyze_master_kinases", "verify_replay"]
