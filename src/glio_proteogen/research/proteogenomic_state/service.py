"""Stateless service facade for research graph analysis and replay verification."""

from __future__ import annotations

from .cancellation import CancellationContext, checkpoint
from .canonical import canonical_request_digest, result_payload_digest, sha256_digest
from .contracts import (
    ProteogenomicStateRequest,
    ProteogenomicStateResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
    UnverifiedProteogenomicStateResult,
)
from .engine import infer_proteogenomic_state
from .profile import algorithm_profile


def analyze_proteogenomic_state(
    request: ProteogenomicStateRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ProteogenomicStateResult:
    """Analyze one validated request without storing inputs or results."""

    checkpoint(cancellation)
    result = infer_proteogenomic_state(request, cancellation=cancellation)
    checkpoint(cancellation)
    return result


def _trace_is_internally_bound(
    result: ProteogenomicStateResult | UnverifiedProteogenomicStateResult,
) -> bool:
    passes = (result.solver.first_pass, result.solver.second_pass)
    return all(item.trace_digest == sha256_digest(list(item.objective_trace)) for item in passes)


def verify_proteogenomic_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Recompute a receipt and compare digests, traces, and semantic content."""

    provided = verification.result
    checkpoint(cancellation)
    request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_proteogenomic_state(
        verification.request,
        cancellation=cancellation,
    )
    checkpoint(cancellation)
    request_match = (
        provided.request_digest == request_digest and recomputed.request_digest == request_digest
    )
    profile_match = (
        provided.profile_digest == algorithm_profile().profile_digest
        and recomputed.profile_digest == provided.profile_digest
    )
    trace_match = _trace_is_internally_bound(provided) and provided.solver == recomputed.solver
    current_payload_digest = result_payload_digest(provided)
    result_match = (
        provided.result_digest == current_payload_digest
        and provided.result_digest == recomputed.result_digest
    )
    semantic_match = provided.model_dump(
        mode="json", exclude={"result_digest"}
    ) == recomputed.model_dump(mode="json", exclude={"result_digest"})
    verified = all((request_match, profile_match, trace_match, result_match, semantic_match))
    return ReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        solver_trace_match=trace_match,
        result_digest_match=result_match,
        semantic_match=semantic_match,
        provided_result_digest=provided.result_digest,
        recomputed_result_digest=recomputed.result_digest,
        recomputed_request_digest=request_digest,
        message=(
            "Replay exactly matches the deterministic research receipt."
            if verified
            else "Replay differs from the supplied receipt; no result claims are accepted."
        ),
    )


__all__ = ["analyze_proteogenomic_state", "verify_proteogenomic_replay"]
