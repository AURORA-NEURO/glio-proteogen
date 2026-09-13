"""Versioned synthetic input for the Neftel bulk-protein research lane."""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from .canonical import sha256_digest
from .catalog import marker_catalog
from .contracts import (
    ProteinEvidenceState,
    ProteinProgramObservation,
    ProteinProgramRequest,
)

DEMO_ID: Final = "synthetic-neftel-ac-program-v1"
_DEMO_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "observation_semantics": "synthetic_standardized_log2_abundance_contrast",
        "patient_data": False,
    }
)


@lru_cache(maxsize=1)
def synthetic_demo_request() -> ProteinProgramRequest:
    """Return synthetic AC-like evidence plus a ranked background proteome."""

    catalog = marker_catalog()
    ac_markers = tuple(
        marker.normalized_symbol
        for marker in catalog.programs["AC"]
        if marker.protein_eligible
    )
    all_program_markers = {
        marker.normalized_symbol
        for markers in catalog.programs.values()
        for marker in markers
        if marker.protein_eligible
    }
    background_symbols = tuple(
        sorted(catalog.protein_background_symbols - all_program_markers)[:28]
    )
    active_markers = tuple(
        ProteinProgramObservation(
            observation_id=f"demo.ac.{index:03d}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=round(1.35 - index * 0.035, 6),
            standard_error=0.30,
            quality_weight=0.95,
            provenance_digest=_DEMO_SOURCE_DIGEST,
        )
        for index, symbol in enumerate(ac_markers[:12], start=1)
    )
    explicit_absence = (
        ProteinProgramObservation(
            observation_id="demo.ac.missing",
            gene_symbol=ac_markers[12],
            state=ProteinEvidenceState.MISSING,
            quality_weight=0.0,
            provenance_digest=_DEMO_SOURCE_DIGEST,
        ),
        ProteinProgramObservation(
            observation_id="demo.ac.unsupported",
            gene_symbol=ac_markers[13],
            state=ProteinEvidenceState.UNSUPPORTED,
            quality_weight=0.0,
            provenance_digest=_DEMO_SOURCE_DIGEST,
        ),
    )
    background = tuple(
        ProteinProgramObservation(
            observation_id=f"demo.background.{index:03d}",
            gene_symbol=symbol,
            state=ProteinEvidenceState.OBSERVED,
            standardized_effect=round(-1.2 + index * 0.065, 6),
            standard_error=0.35,
            quality_weight=0.90,
            provenance_digest=_DEMO_SOURCE_DIGEST,
        )
        for index, symbol in enumerate(background_symbols, start=1)
    )
    return ProteinProgramRequest(
        sample_id=DEMO_ID,
        observations=active_markers + explicit_absence + background,
        bootstrap_replicates=16,
        permutation_replicates=64,
        effect_scale="standardized_log2_abundance_contrast",
        effect_reference_id="synthetic.reference.v1",
    )


def demo_request_digest() -> str:
    """Return the canonical digest of the versioned synthetic request."""

    return synthetic_demo_request().request_digest


__all__ = ["DEMO_ID", "demo_request_digest", "synthetic_demo_request"]
