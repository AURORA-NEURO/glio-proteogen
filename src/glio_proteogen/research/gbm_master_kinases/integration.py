"""Explicit handoffs from the GBM master-kinase lane into ECGI.

The master-kinase engine and ECGI have deliberately different contracts. This
adapter is therefore a narrow, comparison-only bridge: a caller must provide an
exact one-to-one mapping from HGNC kinase symbols to ECGI kinase-node IDs, and
the resulting profile is bound to the complete master-kinase result digest.
No local score is merged with or overwritten by the ECGI estimate.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal

from glio_proteogen.research.proteogenomic_state import (
    ExternalKinaseEstimate,
    ExternalKinaseProfile,
)

from .contracts import AnalysisSupport, MasterKinaseResult

ECGI_EXTERNAL_PROFILE_ID: Final = (
    "sphinks-gbm-master-kinase-concordance-location-1.0.0"
)
ECGI_EXTERNAL_RANK_PROFILE_ID: Final = (
    "sphinks-gbm-master-kinase-concordance-rank-1.0.0"
)

MasterKinaseMethod = Literal["location", "rank_enrichment"]


def build_ecgi_external_kinase_profile(
    result: MasterKinaseResult,
    *,
    node_id_by_kinase_id: Mapping[str, str],
    method: MasterKinaseMethod = "location",
) -> ExternalKinaseProfile:
    """Build an ECGI comparison profile from one supported GBM kinase method.

    ``node_id_by_kinase_id`` is intentionally mandatory: HGNC symbols and ECGI
    graph identifiers are separate namespaces, so guessing a node identifier
    would make an apparently valid comparison scientifically ambiguous. The
    caller selects either the robust ``location`` method or the independent
    ``rank_enrichment`` method. Only records whose selected method is supported
    are emitted; limited or abstained records remain absent rather than becoming
    zero-valued observations. The profile's source digest is the exact
    master-kinase result receipt, which lets an ECGI result explain precisely
    what was compared. The two methods are never averaged or silently merged.
    """
    if method not in {"location", "rank_enrichment"}:
        raise ValueError("method must be 'location' or 'rank_enrichment'")

    if not node_id_by_kinase_id:
        raise ValueError("an explicit kinase-to-ECGI node mapping is required")
    evidence_by_kinase_id = {item.kinase_id: item for item in result.kinase_evidence}
    unknown = sorted(set(node_id_by_kinase_id).difference(evidence_by_kinase_id))
    if unknown:
        raise ValueError(f"mapping references unknown master kinases: {', '.join(unknown)}")
    node_ids = tuple(node_id_by_kinase_id.values())
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("each ECGI kinase node must map from at most one master kinase")

    estimates: list[ExternalKinaseEstimate] = []
    for kinase_id, node_id in sorted(node_id_by_kinase_id.items()):
        evidence = evidence_by_kinase_id[kinase_id]
        if evidence.support is not AnalysisSupport.SUPPORTED:
            continue
        estimate = evidence.location if method == "location" else evidence.rank_enrichment
        if estimate.score is None or estimate.lower_bound is None or estimate.upper_bound is None:
            continue
        estimates.append(
            ExternalKinaseEstimate(
                kinase_id=node_id,
                activity=estimate.score,
                lower_bound=estimate.lower_bound,
                upper_bound=estimate.upper_bound,
            )
        )
    if not estimates:
        if method == "location":
            raise ValueError("the mapping contains no supported master-kinase estimates")
        raise ValueError("the mapping contains no supported master-kinase rank_enrichment estimates")
    return ExternalKinaseProfile(
        profile_id=(
            ECGI_EXTERNAL_PROFILE_ID
            if method == "location"
            else ECGI_EXTERNAL_RANK_PROFILE_ID
        ),
        source_digest=result.result_digest,
        estimates=tuple(estimates),
    )


__all__ = [
    "ECGI_EXTERNAL_PROFILE_ID",
    "ECGI_EXTERNAL_RANK_PROFILE_ID",
    "MasterKinaseMethod",
    "build_ecgi_external_kinase_profile",
]
