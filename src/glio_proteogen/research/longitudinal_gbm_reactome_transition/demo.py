"""Versioned, wholly synthetic Reactome conditional-transition demonstration."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

from .canonical import sha256_digest
from .catalog import reactome_transition_source_catalog
from .contracts import (
    DEFAULT_BOOTSTRAPS,
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalGbmReactomeTransitionRequest,
    LongitudinalTimePoint,
    NormalizationReference,
    ProteinEvidenceState,
    ProteinObservation,
)

DEMO_ID: Final = "synthetic-kncc-reactome-conditional-transition-v1"
EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST: Final = (
    "sha256:b9b584c104781f7d485f63ebdad276f8d337880affb489657f3c5f15ccba352a"
)
_DEMO_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "patient_data": False,
        "semantics": "synthetic_ordered_log2_protein_abundance_for_conditional_concordance",
    }
)
_NORMALIZATION_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "normalization": "one invariant synthetic log2 reference",
    }
)
_REQUEST_GENE_PATTERN: Final = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")


def _demo_feature_indices() -> tuple[int, ...]:
    catalog = reactome_transition_source_catalog()
    indices = {
        index
        for pathway in catalog.pathways
        for index in pathway.eligible_feature_indices
        if _REQUEST_GENE_PATTERN.fullmatch(catalog.genes[index]) is not None
    }
    ordered = tuple(sorted(indices))
    if not ordered or len(ordered) > 4_096:
        raise RuntimeError("synthetic Reactome demo feature inventory is outside its bound")
    return ordered


def _pathway_membership_weights() -> dict[int, float]:
    catalog = reactome_transition_source_catalog()
    weights: dict[int, float] = {}
    for pathway in catalog.pathways:
        pathway_weight = ((pathway.panel_index % 5) - 2) * 0.035
        for index in pathway.eligible_feature_indices:
            weights[index] = weights.get(index, 0.0) + pathway_weight
    return weights


def _log_abundance(index: int, point_index: int, pathway_weight: float) -> float:
    baseline = 11.0 + (index % 29) * 0.0125
    gene_modulation = ((index % 13) - 6) * 0.004
    first_delta = 0.18 + pathway_weight + gene_modulation
    second_delta = -0.10 + pathway_weight * -0.55 - gene_modulation * 0.5
    third_delta = 0.015 + pathway_weight * 0.15
    offsets = (
        0.0,
        first_delta,
        first_delta + second_delta,
        first_delta + second_delta + third_delta,
    )
    return round(baseline + offsets[point_index], 8)


def _demo_time_point(
    point_index: int,
    feature_indices: tuple[int, ...],
    pathway_weights: dict[int, float],
) -> LongitudinalTimePoint:
    catalog = reactome_transition_source_catalog()
    labels = ("baseline", "followup.a", "followup.b", "followup.c")
    offsets = (0.0, 90.0, 210.0, 365.0)
    observations: list[ProteinObservation] = []
    for order, feature_index in enumerate(feature_indices):
        state = (
            ProteinEvidenceState.LEFT_CENSORED
            if order % 47 == 0
            else ProteinEvidenceState.OBSERVED
        )
        observations.append(
            ProteinObservation(
                observation_id=f"reactome.demo.{point_index}.{order:04d}",
                gene_symbol=catalog.genes[feature_index],
                state=state,
                log_abundance=_log_abundance(
                    feature_index,
                    point_index,
                    pathway_weights.get(feature_index, 0.0),
                ),
                standard_error=round(0.03 + (order % 9) * 0.002, 8),
                quality_weight=round(0.90 + (order % 6) * 0.015, 8),
                provenance_digest=_DEMO_SOURCE_DIGEST,
            )
        )
    return LongitudinalTimePoint(
        time_point_id=f"synthetic.reactome.{labels[point_index]}",
        time_offset_days=offsets[point_index],
        normalization_reference_digest=_NORMALIZATION_DIGEST,
        observations=tuple(observations),
    )


@lru_cache(maxsize=1)
def synthetic_demo_request() -> LongitudinalGbmReactomeTransitionRequest:
    """Return four synthetic time points spanning global and pathway contrasts."""

    feature_indices = _demo_feature_indices()
    pathway_weights = _pathway_membership_weights()
    return LongitudinalGbmReactomeTransitionRequest(
        series_id=DEMO_ID,
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=NormalizationReference(
            reference_id="synthetic.kncc.reactome.log2.reference.v1",
            binding_digest=_NORMALIZATION_DIGEST,
            normalization_method="synthetic invariant log2 protein-abundance reference",
        ),
        time_points=tuple(
            _demo_time_point(point_index, feature_indices, pathway_weights)
            for point_index in range(4)
        ),
        bootstrap_replicates=DEFAULT_BOOTSTRAPS,
    )


def demo_request_digest() -> str:
    return synthetic_demo_request().request_digest


__all__ = [
    "DEMO_ID",
    "EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST",
    "demo_request_digest",
    "synthetic_demo_request",
]
