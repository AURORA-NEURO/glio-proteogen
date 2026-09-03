"""Stateless analysis and exact replay for complex-transition concordance."""

from __future__ import annotations

from typing import Any

from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    ComplexTransitionReplayVerificationRequest,
    ComplexTransitionReplayVerificationResult,
    LongitudinalGbmComplexTransitionRequest,
    LongitudinalGbmComplexTransitionResult,
    UnverifiedLongitudinalGbmComplexTransitionResult,
)
from .engine import infer_longitudinal_gbm_complex_transition
from .profile import algorithm_profile

type _ResultDocument = (
    LongitudinalGbmComplexTransitionResult | UnverifiedLongitudinalGbmComplexTransitionResult
)


class LongitudinalGbmComplexTransitionService:
    """Small stateless facade that retains no caller series or result."""

    def analyze(
        self,
        request: LongitudinalGbmComplexTransitionRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> LongitudinalGbmComplexTransitionResult:
        return analyze_longitudinal_gbm_complex_transition(
            request,
            cancellation=cancellation,
        )

    def verify(
        self,
        verification: ComplexTransitionReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> ComplexTransitionReplayVerificationResult:
        return verify_longitudinal_gbm_complex_transition_replay(
            verification,
            cancellation=cancellation,
        )


def analyze_longitudinal_gbm_complex_transition(
    request: LongitudinalGbmComplexTransitionRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> LongitudinalGbmComplexTransitionResult:
    """Revalidate and analyze one request without persistence."""

    checkpoint(cancellation)
    validated = LongitudinalGbmComplexTransitionRequest.model_validate(
        request,
        strict=True,
    )
    result = LongitudinalGbmComplexTransitionResult.model_validate(
        infer_longitudinal_gbm_complex_transition(
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
                (
                    complex_result.complex_index,
                    complex_result.domain_id,
                    complex_result.reactome_id,
                    complex_result.family_id,
                )
                for complex_result in transition.complexes
            ),
        )
        for transition in result.transitions
    )


def _complex_projection(result: _ResultDocument) -> tuple[dict[str, Any], ...]:
    projected: list[dict[str, Any]] = []
    for transition in result.transitions:
        for complex_result in transition.complexes:
            document = complex_result.model_dump(mode="json")
            document.pop("uncertainty")
            document.pop("ablations")
            projected.append(document)
    return tuple(projected)


def _uncertainty_projection(result: _ResultDocument) -> tuple[dict[str, Any], ...]:
    return tuple(
        complex_result.uncertainty.model_dump(mode="json")
        for transition in result.transitions
        for complex_result in transition.complexes
    )


def _ablation_projection(result: _ResultDocument) -> tuple[dict[str, Any], ...]:
    return tuple(
        complex_result.ablations.model_dump(mode="json")
        for transition in result.transitions
        for complex_result in transition.complexes
    )


def _document_projection(result: _ResultDocument) -> tuple[object, ...]:
    return (
        result.profile_id,
        result.model_id,
        result.source_catalog_digest,
        result.fitted_model_digest,
        result.computational_seed,
        result.series_id,
        result.assay_compatibility,
        result.normalization_reference,
        result.time_point_ids,
        result.output_semantics,
        result.limitations,
        result.research_use_only,
        result.non_prescriptive,
        result.infers_complex_assembly,
        result.infers_complex_activity,
        result.infers_stoichiometry,
        result.infers_essential_subunits,
        result.infers_causality,
    )


def verify_longitudinal_gbm_complex_transition_replay(
    verification: ComplexTransitionReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> ComplexTransitionReplayVerificationResult:
    """Recompute and compare one deterministic participant-concordance receipt."""

    checkpoint(cancellation)
    validated = ComplexTransitionReplayVerificationRequest.model_validate(
        verification,
        strict=True,
    )
    provided = validated.result
    recomputed_request_digest = canonical_request_digest(validated.request)
    recomputed = analyze_longitudinal_gbm_complex_transition(
        validated.request,
        cancellation=cancellation,
    )
    authoritative_profile_digest = algorithm_profile().profile_digest
    request_match = all(
        (
            provided.request_digest == recomputed_request_digest,
            provided.request_digest == recomputed.request_digest,
        )
    )
    profile_match = all(
        (
            provided.profile_digest == authoritative_profile_digest,
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
    complex_match = _complex_projection(provided) == _complex_projection(recomputed)
    uncertainty_match = _uncertainty_projection(provided) == _uncertainty_projection(recomputed)
    ablation_match = _ablation_projection(provided) == _ablation_projection(recomputed)
    provenance_match = provided.provenance == recomputed.provenance
    document_match = _document_projection(provided) == _document_projection(recomputed)
    semantic_match = all(
        (
            topology_match,
            complex_match,
            uncertainty_match,
            ablation_match,
            provenance_match,
            document_match,
        )
    )
    verified = all((request_match, profile_match, result_match, semantic_match))
    result = ComplexTransitionReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        result_digest_match=result_match,
        transition_topology_match=topology_match,
        complex_semantic_match=complex_match,
        uncertainty_semantic_match=uncertainty_match,
        ablation_semantic_match=ablation_match,
        provenance_match=provenance_match,
        document_semantic_match=document_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        recomputed_result_digest=recomputed.result_digest,
        authoritative_profile_digest=authoritative_profile_digest,
        message=(
            "Replay exactly matches the deterministic complex-transition receipt."
            if verified
            else (
                "Replay differs from the supplied receipt; no complex-transition "
                "concordance interpretation is accepted."
            )
        ),
    )
    checkpoint(cancellation)
    return result


verify_replay = verify_longitudinal_gbm_complex_transition_replay


__all__ = [
    "LongitudinalGbmComplexTransitionService",
    "analyze_longitudinal_gbm_complex_transition",
    "verify_longitudinal_gbm_complex_transition_replay",
    "verify_replay",
]
