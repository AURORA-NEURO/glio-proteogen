"""Stateless analysis and exact replay facade for signature-transition concordance."""

from __future__ import annotations

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    LongitudinalGbmKinaseTransitionRequest,
    LongitudinalGbmKinaseTransitionResult,
    ReplayVerificationRequest,
    ReplayVerificationResult,
)
from .engine import infer_longitudinal_gbm_kinase_transition
from .profile import algorithm_profile


class LongitudinalGbmKinaseTransitionService:
    """Small stateless facade; caller evidence and receipts are never persisted."""

    def analyze(
        self,
        request: LongitudinalGbmKinaseTransitionRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> LongitudinalGbmKinaseTransitionResult:
        return analyze_longitudinal_gbm_kinase_transition(request, cancellation=cancellation)

    def verify(
        self,
        request: ReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> ReplayVerificationResult:
        return verify_longitudinal_gbm_kinase_transition_replay(request, cancellation=cancellation)


def analyze_longitudinal_gbm_kinase_transition(
    request: LongitudinalGbmKinaseTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmKinaseTransitionResult:
    return infer_longitudinal_gbm_kinase_transition(request, cancellation=cancellation)


def verify_longitudinal_gbm_kinase_transition_replay(
    verification: ReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ReplayVerificationResult:
    checkpoint(cancellation)
    provided = verification.result
    recomputed_request_digest = canonical_request_digest(verification.request)
    recomputed = analyze_longitudinal_gbm_kinase_transition(
        verification.request, cancellation=cancellation
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
    semantic_match = (
        transition_match
        and provided.series_id == recomputed.series_id
        and provided.assay_compatibility == recomputed.assay_compatibility
        and provided.normalization_reference == recomputed.normalization_reference
        and provided.time_point_ids == recomputed.time_point_ids
        and provided.output_semantics == recomputed.output_semantics
        and provided.limitations == recomputed.limitations
        and provided.infers_kinase_activity is False
        and provided.infers_biochemical_activity is False
        and provided.makes_causal_claim is False
        and provided.independent_evidence is False
    )
    verified = request_match and profile_match and result_match and semantic_match
    checkpoint(cancellation)
    return ReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        transition_semantic_match=transition_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches the deterministic signature-transition receipt."
            if verified
            else "Replay differs; no signature-transition interpretation is accepted."
        ),
    )


verify_replay = verify_longitudinal_gbm_kinase_transition_replay

__all__ = [
    "LongitudinalGbmKinaseTransitionService",
    "analyze_longitudinal_gbm_kinase_transition",
    "verify_longitudinal_gbm_kinase_transition_replay",
    "verify_replay",
]
