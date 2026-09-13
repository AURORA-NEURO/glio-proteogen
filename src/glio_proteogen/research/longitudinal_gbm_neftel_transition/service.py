"""Stateless analysis facade and exact replay verification for the Neftel lane."""

from __future__ import annotations

from typing import Any

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    LongitudinalGbmNeftelTransitionRequest,
    LongitudinalGbmNeftelTransitionResult,
    NeftelProgramReplayVerificationRequest,
    NeftelProgramReplayVerificationResult,
    UnverifiedLongitudinalGbmNeftelTransitionResult,
)
from .engine import infer_longitudinal_gbm_neftel_transition
from .profile import algorithm_profile

type _ResultDocument = (
    LongitudinalGbmNeftelTransitionResult | UnverifiedLongitudinalGbmNeftelTransitionResult
)


class LongitudinalGbmNeftelTransitionService:
    """Small stateless facade; it retains no caller series or result."""

    def analyze(
        self,
        request: LongitudinalGbmNeftelTransitionRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> LongitudinalGbmNeftelTransitionResult:
        return analyze_longitudinal_gbm_neftel_transition(
            request,
            cancellation=cancellation,
        )

    def verify(
        self,
        verification: NeftelProgramReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> NeftelProgramReplayVerificationResult:
        return verify_longitudinal_gbm_neftel_transition_replay(
            verification,
            cancellation=cancellation,
        )


def analyze_longitudinal_gbm_neftel_transition(
    request: LongitudinalGbmNeftelTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmNeftelTransitionResult:
    """Revalidate and analyze one request without persisting it."""

    checkpoint(cancellation)
    validated = LongitudinalGbmNeftelTransitionRequest.model_validate(
        request,
        strict=True,
    )
    result = LongitudinalGbmNeftelTransitionResult.model_validate(
        infer_longitudinal_gbm_neftel_transition(
            validated,
            cancellation=cancellation,
        ),
        strict=True,
    )
    checkpoint(cancellation)
    return result


def _topology_projection(result: _ResultDocument) -> tuple[object, ...]:
    return tuple(
        (
            transition.transition_id,
            transition.transition_index,
            transition.from_time_point_id,
            transition.to_time_point_id,
            transition.duration_days,
            tuple(
                (program.program_index, program.domain_id, program.program_id)
                for program in transition.programs
            ),
        )
        for transition in result.transitions
    )


def _program_projection(result: _ResultDocument) -> tuple[dict[str, Any], ...]:
    projected: list[dict[str, Any]] = []
    for transition in result.transitions:
        for program in transition.programs:
            document = program.model_dump(mode="json")
            document.pop("uncertainty")
            document.pop("ablations")
            projected.append(document)
    return tuple(projected)


def _uncertainty_projection(result: _ResultDocument) -> tuple[dict[str, Any], ...]:
    return tuple(
        program.uncertainty.model_dump(mode="json")
        for transition in result.transitions
        for program in transition.programs
    )


def _ablation_projection(result: _ResultDocument) -> tuple[dict[str, Any], ...]:
    return tuple(
        program.ablations.model_dump(mode="json")
        for transition in result.transitions
        for program in transition.programs
    )


def verify_longitudinal_gbm_neftel_transition_replay(
    verification: NeftelProgramReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> NeftelProgramReplayVerificationResult:
    """Recompute and compare one deterministic conditional-concordance receipt."""

    checkpoint(cancellation)
    validated = NeftelProgramReplayVerificationRequest.model_validate(
        verification,
        strict=True,
    )
    provided = validated.result
    recomputed_request_digest = canonical_request_digest(validated.request)
    recomputed = analyze_longitudinal_gbm_neftel_transition(
        validated.request,
        cancellation=cancellation,
    )
    request_match = provided.request_digest == recomputed_request_digest
    profile_match = all(
        (
            provided.profile_digest == algorithm_profile().profile_digest,
            provided.profile_digest == recomputed.profile_digest,
        )
    )
    result_match = all(
        (
            provided.result_digest == result_payload_digest(provided),
            provided.result_digest == recomputed.result_digest,
        )
    )
    topology_match = _topology_projection(provided) == _topology_projection(recomputed)
    global_match = tuple(
        transition.global_transition.model_dump(mode="json") for transition in provided.transitions
    ) == tuple(
        transition.global_transition.model_dump(mode="json")
        for transition in recomputed.transitions
    )
    program_match = _program_projection(provided) == _program_projection(recomputed)
    uncertainty_match = _uncertainty_projection(provided) == _uncertainty_projection(recomputed)
    ablation_match = _ablation_projection(provided) == _ablation_projection(recomputed)
    provenance_match = provided.provenance == recomputed.provenance
    document_match = all(
        (
            provided.series_id == recomputed.series_id,
            provided.assay_compatibility == recomputed.assay_compatibility,
            provided.normalization_reference == recomputed.normalization_reference,
            provided.time_point_ids == recomputed.time_point_ids,
            provided.output_semantics == recomputed.output_semantics,
            provided.validation_scope == recomputed.validation_scope,
            provided.limitations == recomputed.limitations,
            provided.research_use_only is recomputed.research_use_only,
            provided.non_prescriptive is recomputed.non_prescriptive,
        )
    )
    semantic_match = all(
        (
            topology_match,
            global_match,
            program_match,
            uncertainty_match,
            ablation_match,
            provenance_match,
            document_match,
        )
    )
    verified = all((request_match, profile_match, result_match, semantic_match))
    result = NeftelProgramReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        transition_topology_match=topology_match,
        global_transition_semantic_match=global_match,
        program_semantic_match=program_match,
        uncertainty_semantic_match=uncertainty_match,
        ablation_semantic_match=ablation_match,
        provenance_match=provenance_match,
        document_semantic_match=document_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches the deterministic conditional-concordance receipt."
            if verified
            else (
                "Replay differs from the supplied receipt; no conditional program "
                "concordance interpretation is accepted."
            )
        ),
    )
    checkpoint(cancellation)
    return result


verify_replay = verify_longitudinal_gbm_neftel_transition_replay


__all__ = [
    "LongitudinalGbmNeftelTransitionService",
    "analyze_longitudinal_gbm_neftel_transition",
    "verify_longitudinal_gbm_neftel_transition_replay",
    "verify_replay",
]
