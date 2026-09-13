"""Versioned synthetic, non-patient demo for the phosphosite runtime."""

from __future__ import annotations

import math
from functools import lru_cache

from .canonical import canonical_request_digest, sha256_digest
from .catalog import load_phosphosite_transition_catalog
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalGbmPhosphoRequest,
    LongitudinalPhosphoTimePoint,
    NormalizationReference,
    PhosphositeEvidenceState,
    PhosphositeObservation,
)

DEMO_ID = "synthetic-kncc-longitudinal-phosphosite-series-v1"
DEMO_REFERENCE_DIGEST = sha256_digest(
    {"demo": DEMO_ID, "reference": "single synthetic TMT11 bridge channel"}
)
DEMO_SEMANTIC_ORACLE_DIGEST = sha256_digest(
    {
        "expected_transition_order": ["aligned", "reverse", "stable"],
        "raw_phosphosite_view": "fitted",
        "occupancy_like_view": "not_fitted",
        "protein_phosphosite_fusion": "not_fitted",
        "source_model_quality_gate": "limited_until_affirmatively_bound",
    }
)


def _projection_signs() -> dict[int, float]:
    catalog = load_phosphosite_transition_catalog()
    sums: dict[int, float] = {}
    for projection in catalog.bootstrap_projections:
        for index, coefficient in zip(
            projection.feature_indices, projection.coefficients, strict=True
        ):
            sums[index] = sums.get(index, 0.0) + coefficient
    return {
        feature.index: math.copysign(
            1.0,
            feature.coefficient if feature.coefficient != 0.0 else sums.get(feature.index, 1.0),
        )
        for feature in catalog.features
    }


@lru_cache(maxsize=1)
def synthetic_demo_request() -> LongitudinalGbmPhosphoRequest:
    catalog = load_phosphosite_transition_catalog()
    needed = {feature.index for feature in catalog.selected_features}
    for projection in catalog.bootstrap_projections:
        needed.update(projection.feature_indices)
    signs = _projection_signs()
    features = tuple(catalog.features[index] for index in sorted(needed))
    offsets = (0.0, 91.0, 247.0, 461.0)
    points: list[LongitudinalPhosphoTimePoint] = []
    values = {feature.index: 0.03 * math.sin(feature.index * 0.17) for feature in features}
    censored_indices = {feature.index for feature in catalog.selected_features[:2]}
    for point_index, offset in enumerate(offsets):
        if point_index > 0:
            amplitude = (0.8, -0.65, 0.0)[point_index - 1]
            for feature in features:
                if feature.transition_scale is None:
                    raise RuntimeError("demo projection referenced a suppressed source scale")
                values[feature.index] += signs[feature.index] * feature.transition_scale * amplitude
        observations: list[PhosphositeObservation] = []
        for feature in features:
            state = (
                PhosphositeEvidenceState.LEFT_CENSORED
                if point_index == 3 and feature.index in censored_indices
                else PhosphositeEvidenceState.OBSERVED
            )
            observations.append(
                PhosphositeObservation(
                    observation_id=f"demo-p{point_index}-f{feature.index}",
                    phosphosite_id=feature.phosphosite_id,
                    gene_symbol=feature.approved_gene,
                    state=state,
                    log_abundance_ratio=round(values[feature.index], 8),
                    standard_error=0.01 + (feature.index % 5) * 0.001,
                    quality_weight=0.95,
                    provenance_digest=sha256_digest(
                        {"demo": DEMO_ID, "point": point_index, "feature": feature.index}
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
    return LongitudinalGbmPhosphoRequest(
        series_id=DEMO_ID,
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=NormalizationReference(
            reference_id="synthetic-tmt11-bridge",
            binding_digest=DEMO_REFERENCE_DIGEST,
            normalization_method="synthetic fixed TMT11 sample-to-reference log2 ratio",
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
