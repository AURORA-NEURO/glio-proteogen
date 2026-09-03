"""Versioned synthetic bulk-protein input for the functional-proteotype lane."""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from .canonical import sha256_digest
from .catalog import functional_proteotype_catalog
from .contracts import (
    AXIS_ORDER,
    FunctionalProteotypeAxis,
    FunctionalProteotypeRequest,
    ProteinEvidence,
    ProteinEvidenceState,
)

DEMO_ID: Final = "synthetic-migliozzi-functional-proteotype-v1"
_SYNTHETIC_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "observation_semantics": "synthetic_standardized_log2_abundance_contrast",
        "patient_data": False,
        "source_catalog_role": "identifier_and_topology_selection_only",
    }
)
_AXIS_EFFECTS: Final = {
    FunctionalProteotypeAxis.GPM: 1.35,
    FunctionalProteotypeAxis.MTC: 0.45,
    FunctionalProteotypeAxis.NEU: -0.45,
    FunctionalProteotypeAxis.PPR: -1.35,
}


@lru_cache(maxsize=1)
def synthetic_demo_request() -> FunctionalProteotypeRequest:
    """Return a deterministic non-patient example using exact catalog genes."""

    catalog = functional_proteotype_catalog()
    observations: list[ProteinEvidence] = []
    for axis in AXIS_ORDER:
        rows = catalog.axes[axis.value]
        base_effect = _AXIS_EFFECTS[axis]
        direction = 1.0 if base_effect >= 0.0 else -1.0
        for row in rows[:24]:
            rank_taper = direction * (25 - row.source_rank) * 0.008
            observations.append(
                ProteinEvidence(
                    observation_id=f"demo.{axis.value}.{row.source_rank:03d}",
                    gene_symbol=row.gene_symbol,
                    state=ProteinEvidenceState.OBSERVED,
                    standardized_effect=round(base_effect + rank_taper, 6),
                    standard_error=round(0.28 + (row.source_rank % 4) * 0.02, 6),
                    quality_weight=0.95,
                    provenance_digest=_SYNTHETIC_SOURCE_DIGEST,
                )
            )
        censored = rows[24]
        observations.append(
            ProteinEvidence(
                observation_id=f"demo.{axis.value}.left_censored",
                gene_symbol=censored.gene_symbol,
                state=ProteinEvidenceState.LEFT_CENSORED,
                standardized_effect=round(base_effect - 0.30, 6),
                standard_error=0.35,
                quality_weight=0.80,
                provenance_digest=_SYNTHETIC_SOURCE_DIGEST,
            )
        )
        missing = rows[25]
        unsupported = rows[26]
        observations.extend(
            (
                ProteinEvidence(
                    observation_id=f"demo.{axis.value}.missing",
                    gene_symbol=missing.gene_symbol,
                    state=ProteinEvidenceState.MISSING,
                    quality_weight=0.0,
                    provenance_digest=_SYNTHETIC_SOURCE_DIGEST,
                ),
                ProteinEvidence(
                    observation_id=f"demo.{axis.value}.unsupported",
                    gene_symbol=unsupported.gene_symbol,
                    state=ProteinEvidenceState.UNSUPPORTED,
                    quality_weight=0.0,
                    provenance_digest=_SYNTHETIC_SOURCE_DIGEST,
                ),
            )
        )
    return FunctionalProteotypeRequest(
        sample_id=DEMO_ID,
        observations=tuple(observations),
        bootstrap_replicates=64,
        permutation_replicates=256,
        effect_reference_id="synthetic.bulk-reference.v1",
    )


def demo_request_digest() -> str:
    """Return the canonical request receipt for the versioned synthetic demo."""

    return synthetic_demo_request().request_digest


__all__ = ["DEMO_ID", "demo_request_digest", "synthetic_demo_request"]
