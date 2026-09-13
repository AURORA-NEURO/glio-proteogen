"""Stateless service facade for GBM functional-proteotype concordance."""

from __future__ import annotations

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import (
    canonical_request_digest,
    result_payload_digest,
    semantic_result_equal,
)
from .contracts import (
    FunctionalProteotypeRequest,
    FunctionalProteotypeResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from .engine import analyze_functional_proteotype as _run_engine
from .profile import algorithm_profile


class FunctionalProteotypeService:
    """Narrow stateless facade suitable for synchronous CLI and HTTP adapters."""

    def analyze(
        self,
        request: FunctionalProteotypeRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> FunctionalProteotypeResult:
        return analyze_functional_proteotype(request, cancellation=cancellation)

    def verify(
        self,
        verification: ReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> ReplayVerificationResult:
        return verify_replay(verification, cancellation=cancellation)


def analyze_functional_proteotype(
    request: FunctionalProteotypeRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> FunctionalProteotypeResult:
    """Analyze a validated request without persisting input or output."""

    return _run_engine(request, cancellation=cancellation)


def verify_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Recompute and compare the complete deterministic research receipt."""

    checkpoint(cancellation)
    provided = verification.result
    recomputed_request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_functional_proteotype(
        verification.request,
        cancellation=cancellation,
    )
    current_profile = algorithm_profile()
    request_match = (
        provided.request_digest == recomputed_request_digest
        and recomputed.request_digest == recomputed_request_digest
    )
    profile_match = (
        provided.profile_digest == current_profile.profile_digest
        and recomputed.profile_digest == current_profile.profile_digest
    )
    provided_digest_valid = provided.result_digest == result_payload_digest(provided)
    result_match = provided_digest_valid and provided.result_digest == recomputed.result_digest
    trace_match = provided.solver.objective_trace_digest == recomputed.solver.objective_trace_digest
    semantic_match = semantic_result_equal(provided, recomputed)
    verified = request_match and profile_match and result_match and trace_match and semantic_match
    result = ReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        solver_trace_match=trace_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        provided_result_digest=provided.result_digest,
        recomputed_result_digest=recomputed.result_digest,
        provided_solver_trace_digest=provided.solver.objective_trace_digest,
        recomputed_solver_trace_digest=recomputed.solver.objective_trace_digest,
        message=(
            "Replay exactly matches the deterministic functional-proteotype receipt."
            if verified
            else (
                "Replay differs from the supplied receipt; no functional-proteotype "
                "claim is accepted."
            )
        ),
    )
    checkpoint(cancellation)
    return result


def verify_functional_proteotype_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Explicitly named alias retained for adapter readability."""

    return verify_replay(verification, cancellation=cancellation)


__all__ = [
    "FunctionalProteotypeService",
    "analyze_functional_proteotype",
    "verify_functional_proteotype_replay",
    "verify_replay",
]
