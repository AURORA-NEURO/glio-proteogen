"""Stateless facade and exact replay verification for longitudinal GBM evidence."""

from __future__ import annotations

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    LongitudinalGbmRequest,
    LongitudinalGbmResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from .engine import infer_longitudinal_gbm
from .profile import algorithm_profile


class LongitudinalGbmService:
    """Small, stateless facade; it owns no storage and retains no series evidence."""

    def analyze(
        self,
        request: LongitudinalGbmRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> LongitudinalGbmResult:
        return analyze_longitudinal_gbm(request, cancellation=cancellation)

    def verify(
        self,
        verification: ReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> ReplayVerificationResult:
        return verify_longitudinal_gbm_replay(verification, cancellation=cancellation)


def analyze_longitudinal_gbm(
    request: LongitudinalGbmRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmResult:
    """Analyze a validated protein series without persisting the input or output."""

    return infer_longitudinal_gbm(request, cancellation=cancellation)


def verify_longitudinal_gbm_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    """Recompute and compare an exact deterministic longitudinal receipt."""

    checkpoint(cancellation)
    provided = verification.result
    recomputed_request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_longitudinal_gbm(
        verification.request,
        cancellation=cancellation,
    )
    request_match = provided.request_digest == recomputed_request_digest
    profile_match = provided.profile_digest == algorithm_profile().profile_digest
    result_match = (
        provided.result_digest == result_payload_digest(provided.model_dump(mode="json"))
        and provided.result_digest == recomputed.result_digest
    )
    transition_match = tuple(
        item.model_dump(mode="json") for item in provided.transitions
    ) == tuple(item.model_dump(mode="json") for item in recomputed.transitions)
    pelt_match = (
        provided.pelt_analysis.model_dump(mode="json")
        if provided.pelt_analysis is not None
        else None
    ) == (
        recomputed.pelt_analysis.model_dump(mode="json")
        if recomputed.pelt_analysis is not None
        else None
    )
    topology_match = (
        provided.series_id == recomputed.series_id
        and provided.assay_compatibility == recomputed.assay_compatibility
        and provided.normalization_reference == recomputed.normalization_reference
        and provided.time_point_ids == recomputed.time_point_ids
        and provided.output_semantics == recomputed.output_semantics
        and provided.limitations == recomputed.limitations
        and provided.research_use_only is recomputed.research_use_only
        and provided.non_prescriptive is recomputed.non_prescriptive
    )
    semantic_match = transition_match and pelt_match and topology_match
    verified = (
        request_match
        and profile_match
        and result_match
        and transition_match
        and pelt_match
        and semantic_match
    )
    result = ReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        transition_semantic_match=transition_match,
        pelt_semantic_match=pelt_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches the deterministic longitudinal protein-concordance receipt."
            if verified
            else (
                "Replay differs from the supplied receipt; no longitudinal concordance "
                "interpretation is accepted."
            )
        ),
    )
    checkpoint(cancellation)
    return result


verify_replay = verify_longitudinal_gbm_replay


__all__ = [
    "LongitudinalGbmService",
    "analyze_longitudinal_gbm",
    "verify_longitudinal_gbm_replay",
    "verify_replay",
]
