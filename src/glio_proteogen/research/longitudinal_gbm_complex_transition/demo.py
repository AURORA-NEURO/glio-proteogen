"""Versioned wholly synthetic complex-member transition demonstration."""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from .canonical import sha256_digest
from .contracts import (
    DEFAULT_BOOTSTRAPS,
    REQUIRED_ASSAY_COMPATIBILITY,
    LongitudinalGbmComplexTransitionRequest,
    LongitudinalTimePoint,
    NormalizationReference,
    ProteinEvidenceState,
    ProteinObservation,
)
from .source_catalog import complex_transition_source_catalog

DEMO_ID: Final = "synthetic-kncc-reactome-complex-transition-v1"
_DEMO_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "patient_data": False,
        "semantics": "synthetic_ordered_log2_protein_abundance_for_member_concordance",
    }
)
_NORMALIZATION_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "normalization": "one invariant synthetic log2 reference",
    }
)
_DOMAIN_TRANSITIONS: Final[dict[str, tuple[float, float]]] = {
    "egfr_erbb_signaling": (0.48, -0.22),
    "pdgf_signaling": (0.28, 0.10),
    "pi3k_akt": (0.38, -0.16),
    "mtor_energy_sensing": (0.34, -0.08),
    "raf_mapk": (0.31, -0.26),
    "wnt_pcp": (-0.32, 0.43),
    "cell_cycle": (-0.21, 0.29),
    "dna_repair": (0.17, 0.12),
    "hypoxia_vhl": (0.27, -0.31),
    "ecm_adhesion": (-0.24, 0.36),
    "innate_inflammation": (0.22, 0.33),
}


def _feature_domain_effects() -> dict[int, tuple[float, float]]:
    catalog = complex_transition_source_catalog()
    accumulated: dict[int, list[tuple[float, float]]] = {}
    for complex_item in catalog.complexes:
        effect = _DOMAIN_TRANSITIONS[complex_item.domain_id]
        for feature_index in complex_item.eligible_feature_indices:
            accumulated.setdefault(feature_index, []).append(effect)
    return {
        feature_index: (
            sum(item[0] for item in values) / len(values),
            sum(item[1] for item in values) / len(values),
        )
        for feature_index, values in accumulated.items()
    }


def _log_abundance(
    feature_index: int,
    point_index: int,
    transitions: tuple[float, float],
) -> float:
    baseline = 10.5 + (feature_index % 31) * 0.017
    gene_offset = ((feature_index % 11) - 5) * 0.006
    first = transitions[0] + gene_offset
    second = transitions[1] - 0.5 * gene_offset
    offsets = (0.0, first, first + second)
    return round(baseline + offsets[point_index], 8)


def _time_point(
    point_index: int,
    feature_effects: dict[int, tuple[float, float]],
) -> LongitudinalTimePoint:
    catalog = complex_transition_source_catalog()
    labels = ("baseline", "early_recurrence_like", "late_transition_like")
    offsets = (0.0, 120.0, 300.0)
    observations: list[ProteinObservation] = []
    for order, feature_index in enumerate(sorted(feature_effects)):
        state = (
            ProteinEvidenceState.LEFT_CENSORED
            if (point_index + order) % 53 == 0
            else ProteinEvidenceState.OBSERVED
        )
        observations.append(
            ProteinObservation(
                observation_id=f"complex.demo.{point_index}.{order:04d}",
                gene_symbol=catalog.genes[feature_index],
                state=state,
                log_abundance=_log_abundance(
                    feature_index,
                    point_index,
                    feature_effects[feature_index],
                ),
                standard_error=round(0.035 + (order % 7) * 0.003, 8),
                quality_weight=round(0.91 + (order % 5) * 0.015, 8),
                provenance_digest=_DEMO_SOURCE_DIGEST,
            )
        )
    return LongitudinalTimePoint(
        time_point_id=f"synthetic.complex.{labels[point_index]}",
        time_offset_days=offsets[point_index],
        normalization_reference_digest=_NORMALIZATION_DIGEST,
        observations=tuple(observations),
    )


@lru_cache(maxsize=1)
def synthetic_demo_request() -> LongitudinalGbmComplexTransitionRequest:
    """Return three synthetic points spanning all locked participant families."""

    feature_effects = _feature_domain_effects()
    if len(feature_effects) < 3 or len(feature_effects) > 4_096:
        raise RuntimeError("synthetic complex demo feature inventory is outside its bound")
    return LongitudinalGbmComplexTransitionRequest(
        series_id=DEMO_ID,
        assay_compatibility=REQUIRED_ASSAY_COMPATIBILITY,
        normalization_reference=NormalizationReference(
            reference_id="synthetic.kncc.complex.log2.reference.v1",
            binding_digest=_NORMALIZATION_DIGEST,
            normalization_method="synthetic invariant log2 protein-abundance reference",
        ),
        time_points=tuple(_time_point(index, feature_effects) for index in range(3)),
        bootstrap_replicates=DEFAULT_BOOTSTRAPS,
    )


def demo_request_digest() -> str:
    return synthetic_demo_request().request_digest


__all__ = ["DEMO_ID", "demo_request_digest", "synthetic_demo_request"]
