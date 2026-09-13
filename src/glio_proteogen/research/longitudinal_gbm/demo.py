"""Versioned, wholly synthetic KNCC longitudinal protein demonstration input."""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from .canonical import sha256_digest
from .catalog import longitudinal_gbm_catalog
from .contracts import (
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalGbmRequest,
    LongitudinalTimePoint,
    NormalizationReference,
    ProteinEvidenceState,
    ProteinObservation,
)

DEMO_ID: Final = "synthetic-kncc-longitudinal-protein-series-v1"
# This oracle binds only the transition/segmentation semantics projection, never a
# profile or result digest.  It is populated from an independently reviewed run.
EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST: Final = (
    "sha256:3e2ed92536f3a21531ef9b53710c0bc2152d30d36ff84f787b5225ba1f709ed2"
)
_DEMO_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "patient_data": False,
        "semantics": "synthetic_ordered_log2_protein_abundance",
    }
)
_NORMALIZATION_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "normalization": "one invariant synthetic log2 reference",
    }
)


def _demo_feature_indices() -> tuple[int, ...]:
    catalog = longitudinal_gbm_catalog()
    ranked = sorted(
        catalog.ensemble_feature_indices,
        key=lambda index: (
            -catalog.features[index].ensemble_mean_absolute_coefficient,
            catalog.features[index].gene_symbol,
        ),
    )
    return tuple(ranked[:256])


def _log_abundance(index: int, point_index: int) -> float:
    feature = longitudinal_gbm_catalog().features[index]
    baseline = 12.0 + (index % 17) * 0.015
    direction = 1.0 if feature.ensemble_mean_coefficient >= 0.0 else -1.0
    gene_factor = 0.75 + (index % 11) * 0.04
    aligned = direction * feature.transition_scale * 0.90 * gene_factor
    reverse = -direction * feature.transition_scale * 0.70 * (1.50 - gene_factor / 2.0)
    stable = direction * feature.transition_scale * 0.008 * gene_factor
    offsets = (0.0, aligned, aligned + reverse, aligned + reverse + stable)
    return round(baseline + offsets[point_index], 8)


def _demo_time_point(point_index: int, feature_indices: tuple[int, ...]) -> LongitudinalTimePoint:
    catalog = longitudinal_gbm_catalog()
    labels = ("baseline", "followup.a", "followup.b", "followup.c")
    offsets = (0.0, 90.0, 210.0, 365.0)
    observations: list[ProteinObservation] = []
    for order, feature_index in enumerate(feature_indices):
        feature = catalog.features[feature_index]
        state = (
            ProteinEvidenceState.LEFT_CENSORED if order % 29 == 0 else ProteinEvidenceState.OBSERVED
        )
        observations.append(
            ProteinObservation(
                observation_id=f"demo.{point_index}.{order:03d}",
                gene_symbol=feature.gene_symbol,
                state=state,
                log_abundance=_log_abundance(feature_index, point_index),
                standard_error=round(0.025 + (order % 7) * 0.002, 8),
                quality_weight=round(0.92 + (order % 5) * 0.015, 8),
                provenance_digest=_DEMO_SOURCE_DIGEST,
            )
        )
    return LongitudinalTimePoint(
        time_point_id=f"synthetic.{labels[point_index]}",
        time_offset_days=offsets[point_index],
        normalization_reference_digest=_NORMALIZATION_DIGEST,
        observations=tuple(observations),
    )


@lru_cache(maxsize=1)
def synthetic_demo_request() -> LongitudinalGbmRequest:
    """Return a four-point synthetic series spanning aligned, reverse, and stable changes."""

    feature_indices = _demo_feature_indices()
    return LongitudinalGbmRequest(
        series_id=DEMO_ID,
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=NormalizationReference(
            reference_id="synthetic.kncc.log2.reference.v1",
            binding_digest=_NORMALIZATION_DIGEST,
            normalization_method="synthetic invariant log2 protein-abundance reference",
        ),
        time_points=tuple(
            _demo_time_point(point_index, feature_indices) for point_index in range(4)
        ),
        bootstrap_replicates=32,
    )


def demo_request_digest() -> str:
    """Return the canonical digest of the versioned synthetic request."""

    return synthetic_demo_request().request_digest


__all__ = [
    "DEMO_ID",
    "EXPECTED_DEMO_SEMANTIC_ORACLE_DIGEST",
    "demo_request_digest",
    "synthetic_demo_request",
]
