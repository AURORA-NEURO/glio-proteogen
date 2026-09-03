"""Stateless analysis and exact replay service for the independent factor graph."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

from glio_proteogen.research.longitudinal_gbm_kinase_transition.canonical import (
    canonical_request_digest as canonical_kinase_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.canonical import (
    result_payload_digest as kinase_result_payload_digest,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    LongitudinalGbmKinaseTransitionResult,
    UnverifiedLongitudinalGbmKinaseTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    canonical_request_digest as canonical_reactome_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    result_payload_digest as reactome_result_payload_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    LongitudinalGbmReactomeTransitionResult,
    UnverifiedLongitudinalGbmReactomeTransitionResult,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_json_bytes, canonical_request_digest, result_payload_digest
from .contracts import (
    MAX_REPLAY_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
    KnccGbmFactorGraphReplayVerificationRequest,
    KnccGbmFactorGraphReplayVerificationResult,
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
    UnverifiedKnccGbmFactorGraphResult,
)
from .engine import infer_kncc_gbm_factor_graph
from .errors import KnccGbmFactorGraphInferenceError, KnccGbmFactorGraphReplayError
from .profile import algorithm_profile

type _ResultDocument = KnccGbmFactorGraphResult | UnverifiedKnccGbmFactorGraphResult
type _ReactomeResultDocument = (
    LongitudinalGbmReactomeTransitionResult | UnverifiedLongitudinalGbmReactomeTransitionResult
)
type _KinaseResultDocument = (
    LongitudinalGbmKinaseTransitionResult | UnverifiedLongitudinalGbmKinaseTransitionResult
)


class KnccGbmFactorGraphService:
    """Small stateless facade; neither child inputs nor results are retained."""

    def analyze(
        self,
        request: KnccGbmFactorGraphRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphResult:
        return analyze_kncc_gbm_factor_graph(request, cancellation=cancellation)

    def verify(
        self,
        verification: KnccGbmFactorGraphReplayVerificationRequest,
        *,
        cancellation: CancellationContext | None = None,
    ) -> KnccGbmFactorGraphReplayVerificationResult:
        return verify_kncc_gbm_factor_graph_replay(
            verification,
            cancellation=cancellation,
        )


def _encoded_size(value: BaseModel) -> int:
    return len(canonical_json_bytes(value.model_dump(mode="json")))


def analyze_kncc_gbm_factor_graph(
    request: KnccGbmFactorGraphRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> KnccGbmFactorGraphResult:
    """Revalidate, execute, and size-bound one independent-block analysis."""

    checkpoint(cancellation)
    validated = KnccGbmFactorGraphRequest.model_validate(request, strict=True)
    if _encoded_size(validated) > MAX_REQUEST_BYTES:
        raise KnccGbmFactorGraphInferenceError("factor-graph request exceeds 4 MiB")
    result = KnccGbmFactorGraphResult.model_validate(
        infer_kncc_gbm_factor_graph(validated, cancellation=cancellation),
        strict=True,
    )
    if _encoded_size(result) > MAX_RESULT_BYTES:
        raise KnccGbmFactorGraphInferenceError("factor-graph result exceeds 8 MiB")
    checkpoint(cancellation)
    return result


def _document_projection(result: _ResultDocument) -> dict[str, Any]:
    document = result.model_dump(mode="json")
    for field in (
        "profile_digest",
        "topology_digest",
        "request_digest",
        "result_digest",
        "provenance",
    ):
        document.pop(field)
    return document


def _child_semantic_projection(result: BaseModel) -> dict[str, Any]:
    document = result.model_dump(mode="json")
    document.pop("result_digest")
    return document


def _reactome_child_verified(
    request_digest: str,
    provided: _ReactomeResultDocument,
    recomputed: LongitudinalGbmReactomeTransitionResult,
) -> bool:
    """Apply every child receipt and semantic check to one recomputed result."""

    return all(
        (
            provided.request_digest == request_digest,
            recomputed.request_digest == request_digest,
            provided.profile_id == recomputed.profile_id,
            provided.profile_digest == recomputed.profile_digest,
            provided.result_digest == reactome_result_payload_digest(provided),
            provided.result_digest == recomputed.result_digest,
            _child_semantic_projection(provided) == _child_semantic_projection(recomputed),
        )
    )


def _kinase_child_verified(
    request_digest: str,
    provided: _KinaseResultDocument,
    recomputed: LongitudinalGbmKinaseTransitionResult,
) -> bool:
    """Apply every child receipt and semantic check to one recomputed result."""

    return all(
        (
            provided.request_digest == request_digest,
            recomputed.request_digest == request_digest,
            provided.profile_id == recomputed.profile_id,
            provided.profile_digest == recomputed.profile_digest,
            provided.result_digest == kinase_result_payload_digest(provided),
            provided.result_digest == recomputed.result_digest,
            _child_semantic_projection(provided) == _child_semantic_projection(recomputed),
        )
    )


def verify_kncc_gbm_factor_graph_replay(
    verification: KnccGbmFactorGraphReplayVerificationRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> KnccGbmFactorGraphReplayVerificationResult:
    """Recompute both children and report each independent replay check."""

    checkpoint(cancellation)
    validated = KnccGbmFactorGraphReplayVerificationRequest.model_validate(
        verification,
        strict=True,
    )
    if _encoded_size(validated) > MAX_REPLAY_BYTES:
        raise KnccGbmFactorGraphReplayError("factor-graph replay envelope exceeds 16 MiB")
    provided = validated.result

    profile = algorithm_profile()
    recomputed_request_digest = canonical_request_digest(validated.request)
    recomputed = analyze_kncc_gbm_factor_graph(
        validated.request,
        cancellation=cancellation,
    )
    reactome_child_verified = _reactome_child_verified(
        canonical_reactome_request_digest(validated.request.reactome_request),
        provided.reactome_result,
        recomputed.reactome_result,
    )
    kinase_child_verified = _kinase_child_verified(
        canonical_kinase_request_digest(validated.request.kinase_request),
        provided.kinase_result,
        recomputed.kinase_result,
    )
    checkpoint(cancellation)
    request_match = all(
        (
            provided.request_digest == recomputed_request_digest,
            recomputed.request_digest == recomputed_request_digest,
        )
    )
    profile_match = all(
        (
            provided.profile_digest == profile.profile_digest,
            provided.provenance.profile_digest == profile.profile_digest,
            recomputed.profile_digest == profile.profile_digest,
        )
    )
    topology_match = all(
        (
            provided.topology_digest == profile.topology_digest,
            provided.provenance.topology_digest == profile.topology_digest,
            recomputed.topology_digest == profile.topology_digest,
        )
    )
    source_match = all(
        (
            provided.provenance.source_inventory_digest == profile.source_inventory_digest,
            recomputed.provenance.source_inventory_digest == profile.source_inventory_digest,
        )
    )
    result_match = all(
        (
            provided.result_digest == result_payload_digest(provided),
            provided.result_digest == recomputed.result_digest,
        )
    )
    independent_match = all(
        (
            provided.independent_parallel_blocks is True,
            provided.provenance.independent_parallel_blocks is True,
            recomputed.independent_parallel_blocks is True,
            profile.independent_parallel_blocks is True,
        )
    )
    no_fusion_match = all(
        (
            provided.cross_modal_fusion_performed is False,
            provided.provenance.cross_modal_fusion_performed is False,
            recomputed.cross_modal_fusion_performed is False,
            profile.cross_modal_fusion_performed is False,
        )
    )
    no_numerical_edges_match = all(
        (
            provided.numerical_cross_block_edge_count == 0,
            provided.provenance.no_numerical_cross_block_edges is True,
            recomputed.numerical_cross_block_edge_count == 0,
            profile.no_numerical_cross_block_edges is True,
            profile.topology.numerical_cross_block_edge_count == 0,
        )
    )
    provenance_match = provided.provenance == recomputed.provenance
    document_match = _document_projection(provided) == _document_projection(recomputed)
    semantic_match = all(
        (
            reactome_child_verified,
            kinase_child_verified,
            independent_match,
            no_fusion_match,
            no_numerical_edges_match,
            provenance_match,
            document_match,
        )
    )
    verified = all(
        (
            request_match,
            profile_match,
            topology_match,
            source_match,
            result_match,
            semantic_match,
        )
    )
    checkpoint(cancellation)
    return KnccGbmFactorGraphReplayVerificationResult(
        verified=verified,
        request_digest_match=request_match,
        profile_digest_match=profile_match,
        topology_digest_match=topology_match,
        source_inventory_digest_match=source_match,
        result_digest_match=result_match,
        reactome_child_verified=reactome_child_verified,
        kinase_child_verified=kinase_child_verified,
        independent_parallel_blocks_match=independent_match,
        no_cross_modal_fusion_match=no_fusion_match,
        no_numerical_cross_block_edges_match=no_numerical_edges_match,
        provenance_match=provenance_match,
        document_semantic_match=document_match,
        semantic_match=semantic_match,
        recomputed_request_digest=recomputed_request_digest,
        recomputed_result_digest=recomputed.result_digest,
        message=(
            "Replay exactly matches both independent child receipts and outer binding."
            if verified
            else ("Replay differs; no composed Reactome or kinase interpretation is accepted.")
        ),
    )


verify_replay = verify_kncc_gbm_factor_graph_replay


__all__ = [
    "KnccGbmFactorGraphService",
    "analyze_kncc_gbm_factor_graph",
    "verify_kncc_gbm_factor_graph_replay",
    "verify_replay",
]
