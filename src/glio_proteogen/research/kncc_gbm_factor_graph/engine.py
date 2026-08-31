"""Independent execution engine for the two-block KNCC GBM factor graph."""

from __future__ import annotations

from glio_proteogen.research.longitudinal_gbm_kinase_transition.canonical import (
    canonical_request_digest as canonical_kinase_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.contracts import (
    LongitudinalGbmKinaseTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_kinase_transition.service import (
    analyze_longitudinal_gbm_kinase_transition,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.canonical import (
    canonical_request_digest as canonical_reactome_request_digest,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.contracts import (
    LongitudinalGbmReactomeTransitionResult,
)
from glio_proteogen.research.longitudinal_gbm_reactome_transition.service import (
    analyze_longitudinal_gbm_reactome_transition,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    checkpoint,
)

from .canonical import canonical_request_digest, result_payload_digest
from .contracts import (
    FactorGraphBlock,
    FactorGraphChildProfileBinding,
    FactorGraphChildResultBinding,
    KnccGbmFactorGraphProvenance,
    KnccGbmFactorGraphRequest,
    KnccGbmFactorGraphResult,
    UnverifiedKnccGbmFactorGraphResult,
)
from .errors import (
    KnccGbmFactorGraphInferenceError,
    KnccGbmFactorGraphProfileIntegrityError,
)
from .profile import algorithm_profile

type _ChildResult = LongitudinalGbmReactomeTransitionResult | LongitudinalGbmKinaseTransitionResult

_LIMITATIONS = (
    "Research use only; this composition is not diagnostic, prognostic, or prescriptive.",
    "The Reactome block reports fitted recurrence concordance, not pathway activation.",
    "The SPHINKS block reports fitted signature-transition concordance, not kinase activity.",
    "The two child engines run independently; no cross-modal numerical edge is evaluated.",
    "Parallel describes graph independence only; runtime executes Reactome then SPHINKS "
    "deterministically in serial under one deadline.",
    "No kinase result feeds back into the protein or Reactome calculation.",
    "Both child models are same-source-cohort research coordinates, not external validation.",
    "The outer receipt preserves child missingness and censoring semantics without remapping.",
    "Containment edges are annotations only; the outer layer adds no fitted estimator.",
)


def _bind_child_result(
    *,
    block: FactorGraphBlock,
    result: _ChildResult,
    expected: FactorGraphChildProfileBinding,
    expected_request_digest: str,
) -> FactorGraphChildResultBinding:
    if expected.block is not block:
        raise KnccGbmFactorGraphProfileIntegrityError(
            f"factor-graph profile assigns {block.value} to the wrong child block"
        )
    if (
        result.profile_id != expected.child_profile_id
        or result.profile_digest != expected.child_profile_digest
    ):
        raise KnccGbmFactorGraphProfileIntegrityError(
            f"{block.value} result does not match the locked child profile"
        )
    if result.request_digest != expected_request_digest:
        raise KnccGbmFactorGraphInferenceError(
            f"{block.value} result is not bound to the supplied child request"
        )
    return FactorGraphChildResultBinding(
        block=block,
        child_profile_id=result.profile_id,
        child_profile_digest=result.profile_digest,
        child_request_digest=result.request_digest,
        child_result_digest=result.result_digest,
    )


def infer_kncc_gbm_factor_graph(
    request: KnccGbmFactorGraphRequest,
    *,
    cancellation: CancellationContext | None = None,
) -> KnccGbmFactorGraphResult:
    """Run the exact child services independently, in serial, and bind their receipts."""

    checkpoint(cancellation)
    validated = KnccGbmFactorGraphRequest.model_validate(request, strict=True)
    profile = algorithm_profile()
    request_digest = canonical_request_digest(validated)

    checkpoint(cancellation)
    reactome_result = analyze_longitudinal_gbm_reactome_transition(
        validated.reactome_request,
        cancellation=cancellation,
    )
    checkpoint(cancellation)
    kinase_result = analyze_longitudinal_gbm_kinase_transition(
        validated.kinase_request,
        cancellation=cancellation,
    )
    checkpoint(cancellation)

    reactome_binding = _bind_child_result(
        block=FactorGraphBlock.PROTEIN_REACTOME,
        result=reactome_result,
        expected=profile.reactome_child,
        expected_request_digest=canonical_reactome_request_digest(validated.reactome_request),
    )
    kinase_binding = _bind_child_result(
        block=FactorGraphBlock.PHOSPHOSITE_SPHINKS,
        result=kinase_result,
        expected=profile.kinase_child,
        expected_request_digest=canonical_kinase_request_digest(validated.kinase_request),
    )
    provenance = KnccGbmFactorGraphProvenance(
        request_digest=request_digest,
        profile_digest=profile.profile_digest,
        topology_digest=profile.topology_digest,
        source_inventory_digest=profile.source_inventory_digest,
        reactome_child=reactome_binding,
        kinase_child=kinase_binding,
        numpy_version=profile.numpy_version,
    )
    unverified = UnverifiedKnccGbmFactorGraphResult(
        profile_digest=profile.profile_digest,
        topology_digest=profile.topology_digest,
        request_digest=request_digest,
        result_digest="sha256:" + "0" * 64,
        analysis_id=validated.analysis_id,
        reactome_result=reactome_result,
        kinase_result=kinase_result,
        provenance=provenance,
        limitations=_LIMITATIONS,
    )
    document = unverified.model_dump(mode="python")
    document["result_digest"] = result_payload_digest(unverified)
    result = KnccGbmFactorGraphResult.model_validate(document, strict=True)
    checkpoint(cancellation)
    return result


__all__ = ["infer_kncc_gbm_factor_graph"]
