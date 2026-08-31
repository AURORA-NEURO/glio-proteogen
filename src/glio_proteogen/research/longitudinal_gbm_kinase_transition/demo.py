"""Versioned synthetic, non-patient demo for signature-transition concordance."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from functools import lru_cache

from glio_proteogen.research.longitudinal_gbm_phospho.contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalPhosphoTimePoint,
    NormalizationReference,
    PhosphositeEvidenceState,
    PhosphositeObservation,
)

from .canonical import canonical_request_digest, sha256_digest
from .catalog import load_kinase_transition_catalog
from .contracts import LongitudinalGbmKinaseTransitionRequest

DEMO_ID = "synthetic-kncc-sphinks-signature-transition-v1"
DEMO_REFERENCE_DIGEST = sha256_digest(
    {"demo": DEMO_ID, "reference": "single synthetic TMT11 bridge channel"}
)
DEMO_SEMANTIC_ORACLE_DIGEST = sha256_digest(
    {
        "expected_transition_order": ["aligned", "reverse", "aligned"],
        "fixed_hypothesis_count": 24,
        "full_fit_selected_count": 12,
        "CHEK2": "limited_selected_unstable",
        "all_estimable_outputs": "limited",
        "claim": "signature_transition_concordance_not_kinase_activity",
    }
)


def _family_signals() -> dict[int, float]:
    catalog = load_kinase_transition_catalog()
    signed: dict[int, float] = defaultdict(float)
    absolute: dict[int, float] = defaultdict(float)
    for kinase in catalog.selected_kinases:
        direction = 1.0 if kinase.direction == "source_recurrence_aligned" else -1.0
        for index, weight in zip(kinase.family_indices, kinase.weights, strict=True):
            signed[index] += direction * weight
            absolute[index] += weight
    output: dict[int, float] = {}
    for family in catalog.families:
        if family.family_index in absolute:
            output[family.family_index] = (
                signed[family.family_index] / absolute[family.family_index]
            )
    return output


@lru_cache(maxsize=1)
def synthetic_demo_request() -> LongitudinalGbmKinaseTransitionRequest:
    catalog = load_kinase_transition_catalog()
    family_indices = {index for item in catalog.selected_kinases for index in item.family_indices}
    for projection in catalog.bootstrap_projections:
        family_indices.update(projection.family_indices)
    families = tuple(item for item in catalog.families if item.family_index in family_indices)
    signals = _family_signals()
    offsets = (0.0, 84.0, 203.0, 391.0)
    amplitudes = (0.75, -0.60, 0.85)
    values = {
        family.family_index: 0.015 * (((family.family_index * 37) % 23) - 11) for family in families
    }
    points: list[LongitudinalPhosphoTimePoint] = []
    first_ids = {
        phosphosite_id
        for family in families[:2]
        for phosphosite_id in family.source_phosphosite_ids[:1]
    }
    base_catalog = __import__(
        "glio_proteogen.research.longitudinal_gbm_phospho.catalog",
        fromlist=["load_phosphosite_transition_catalog"],
    ).load_phosphosite_transition_catalog()
    for point_index, offset in enumerate(offsets):
        if point_index:
            for family in families:
                fallback = (
                    1.0
                    if hashlib.sha256(family.source_site_label.encode()).digest()[0] % 2
                    else -1.0
                )
                signal = signals.get(family.family_index, fallback * 0.25)
                values[family.family_index] += (
                    amplitudes[point_index - 1] * signal * family.transition_scale
                )
        observations: list[PhosphositeObservation] = []
        for family in families:
            for phosphosite_id in family.source_phosphosite_ids:
                feature = base_catalog.feature_by_id[phosphosite_id]
                state = (
                    PhosphositeEvidenceState.LEFT_CENSORED
                    if point_index == 3 and phosphosite_id in first_ids
                    else PhosphositeEvidenceState.OBSERVED
                )
                observations.append(
                    PhosphositeObservation(
                        observation_id=(f"demo-p{point_index}-f{feature.index}"),
                        phosphosite_id=phosphosite_id,
                        gene_symbol=feature.approved_gene,
                        state=state,
                        log_abundance_ratio=round(values[family.family_index], 8),
                        standard_error=0.012 + (feature.index % 4) * 0.002,
                        quality_weight=0.95,
                        provenance_digest=sha256_digest(
                            {
                                "demo": DEMO_ID,
                                "point": point_index,
                                "phosphosite_id": phosphosite_id,
                            }
                        ),
                    )
                )
        points.append(
            LongitudinalPhosphoTimePoint(
                time_point_id=f"synthetic-p{point_index}",
                time_offset_days=offset,
                normalization_reference_digest=DEMO_REFERENCE_DIGEST,
                observations=tuple(observations),
            )
        )
    return LongitudinalGbmKinaseTransitionRequest(
        series_id=DEMO_ID,
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=NormalizationReference(
            reference_id="synthetic-tmt11-bridge",
            binding_digest=DEMO_REFERENCE_DIGEST,
            normalization_method="synthetic fixed TMT11 phosphosite log2 ratio bridge",
        ),
        time_points=tuple(points),
        bootstrap_replicates=64,
    )


def demo_request_digest() -> str:
    return canonical_request_digest(synthetic_demo_request())


__all__ = [
    "DEMO_ID",
    "DEMO_REFERENCE_DIGEST",
    "DEMO_SEMANTIC_ORACLE_DIGEST",
    "demo_request_digest",
    "synthetic_demo_request",
]
