"""Versioned synthetic LFQ request for the published GBM proteomic models."""

from __future__ import annotations

from functools import lru_cache

from glio_proteogen.kernel.canonical import sha256_digest

from .contracts import (
    SUPPORTED_SIGNATURE_IDS,
    GbmProteinEvidenceState,
    GbmProteinMeasurement,
    GbmProteomicAxesRequest,
)
from .data.predictor import feature_names

DEMO_ID = "synthetic-gbm-lfq-demo-v1"
DEMO_OBSERVED_FEATURES = 64

# Glioblastoma-relevant proteins are preferred when present in the authors' common
# 3,025-feature model universe. The deterministic fallback keeps the demo executable
# if a preferred marker is not represented by the published proteomic feature set.
_PRIORITY_GENES = (
    "EGFR",
    "ERBB2",
    "ERBB3",
    "PDGFRA",
    "MET",
    "PTEN",
    "PIK3CA",
    "PIK3R1",
    "AKT1",
    "AKT2",
    "MTOR",
    "RPTOR",
    "MAPK1",
    "MAPK3",
    "BRAF",
    "RAF1",
    "KRAS",
    "NRAS",
    "NF1",
    "MYC",
    "MAX",
    "HIF1A",
    "EPAS1",
    "VEGFA",
    "CA9",
    "LDHA",
    "SLC2A1",
    "HK2",
    "ENO1",
    "OLIG2",
    "SOX2",
    "NES",
    "GFAP",
    "S100B",
    "VIM",
    "CHI3L1",
    "CD44",
    "STAT3",
    "CEBPB",
    "CEBPD",
    "WWTR1",
    "YAP1",
    "CDK4",
    "CDK6",
    "RB1",
    "TP53",
    "MDM2",
    "CCND1",
    "PCNA",
    "MKI67",
    "PROM1",
    "NOTCH1",
    "DLL3",
    "TGFBR1",
    "TGFBR2",
    "SMAD2",
    "SMAD3",
    "ITGA5",
    "ITGB1",
    "FN1",
    "COL1A1",
    "ANXA1",
    "LGALS3",
    "SERPINE1",
    "CXCL8",
    "CXCR4",
    "AIF1",
    "CD68",
    "CD163",
    "TREM2",
    "CSF1R",
    "P2RY12",
    "PECAM1",
    "VWF",
    "ENG",
    "KDR",
    "ACTB",
    "GAPDH",
    "TUBA1A",
    "HSP90AA1",
)

_LFQ_MULTIPLIERS = (
    5.20,
    2.10,
    2.80,
    4.40,
    2.70,
    0.62,
    2.30,
    1.90,
    2.55,
    1.85,
    2.20,
    1.75,
    2.45,
    2.15,
    1.35,
    1.48,
    1.92,
    1.55,
    0.58,
    3.20,
    2.65,
    2.75,
    1.42,
    3.10,
    2.85,
    2.60,
    2.70,
    2.35,
    2.25,
    3.35,
    3.05,
    2.40,
    2.15,
    1.80,
    3.65,
    3.90,
    3.30,
    2.95,
    2.60,
    2.50,
    2.20,
    1.95,
    1.70,
    1.80,
    1.25,
    0.82,
    1.60,
    2.10,
    2.55,
    2.30,
    1.75,
    1.60,
    1.45,
    2.25,
    2.15,
    2.05,
    1.90,
    2.30,
    2.05,
    2.50,
    1.85,
    2.40,
    2.20,
    2.65,
)


def _source_digest(
    gene_symbol: str,
    state: GbmProteinEvidenceState,
    value: float | None,
) -> str:
    return sha256_digest(
        {
            "demo_id": DEMO_ID,
            "gene_symbol": gene_symbol,
            "state": state.value,
            "synthetic_value": value,
        }
    )


def _demo_symbols() -> tuple[tuple[str, ...], tuple[str, str, str]]:
    model_features = feature_names(SUPPORTED_SIGNATURE_IDS[0])
    feature_set = set(model_features)
    prioritized = [gene for gene in _PRIORITY_GENES if gene in feature_set]
    selected = list(dict.fromkeys(prioritized))
    selected.extend(
        gene
        for gene in model_features
        if gene not in selected and len(selected) < DEMO_OBSERVED_FEATURES
    )
    observed = tuple(selected[:DEMO_OBSERVED_FEATURES])
    remaining = tuple(gene for gene in model_features if gene not in set(observed))
    if len(observed) != DEMO_OBSERVED_FEATURES or len(remaining) < 3:
        raise RuntimeError("published model feature catalog cannot construct the locked demo")
    return observed, (remaining[0], remaining[1], remaining[2])


@lru_cache(maxsize=1)
def synthetic_demo_request() -> GbmProteomicAxesRequest:
    """Return a deterministic synthetic request; no patient data are bundled."""

    observed, inactive = _demo_symbols()
    measurements: list[GbmProteinMeasurement] = []
    for index, gene_symbol in enumerate(observed):
        multiplier = _LFQ_MULTIPLIERS[index % len(_LFQ_MULTIPLIERS)]
        intensity = 1_000_000.0 * multiplier
        measurements.append(
            GbmProteinMeasurement(
                gene_symbol=gene_symbol,
                state=GbmProteinEvidenceState.OBSERVED,
                lfq_intensity=intensity,
                log2_standard_error=0.18 + 0.02 * (index % 4),
                provenance_digest=_source_digest(
                    gene_symbol, GbmProteinEvidenceState.OBSERVED, intensity
                ),
            )
        )
    left_censored, missing, unsupported = inactive
    upper_limit = 120_000.0
    measurements.extend(
        (
            GbmProteinMeasurement(
                gene_symbol=left_censored,
                state=GbmProteinEvidenceState.LEFT_CENSORED,
                lfq_upper_limit=upper_limit,
                provenance_digest=_source_digest(
                    left_censored, GbmProteinEvidenceState.LEFT_CENSORED, upper_limit
                ),
            ),
            GbmProteinMeasurement(
                gene_symbol=missing,
                state=GbmProteinEvidenceState.MISSING,
                provenance_digest=_source_digest(
                    missing, GbmProteinEvidenceState.MISSING, None
                ),
            ),
            GbmProteinMeasurement(
                gene_symbol=unsupported,
                state=GbmProteinEvidenceState.UNSUPPORTED,
                provenance_digest=_source_digest(
                    unsupported, GbmProteinEvidenceState.UNSUPPORTED, None
                ),
            ),
        )
    )
    return GbmProteomicAxesRequest(
        sample_id=DEMO_ID,
        measurements=tuple(measurements),
        bootstrap_replicates=8,
    )


def demo_request_digest() -> str:
    return synthetic_demo_request().request_digest


__all__ = ["DEMO_ID", "DEMO_OBSERVED_FEATURES", "demo_request_digest", "synthetic_demo_request"]
