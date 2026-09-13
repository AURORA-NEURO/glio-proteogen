"""Versioned synthetic bulk-RNA request for the GBMPurity research lane."""

from __future__ import annotations

import hashlib
from typing import Final

from .canonical import canonical_request_digest, sha256_digest
from .catalog import gbm_rna_purity_catalog
from .contracts import REQUIRED_CONTEXT, GbmRnaPurityRequest, RawGeneCount

DEMO_ID: Final = "synthetic-primary-idhwt-gbm-rna-purity-v1"
_DEMO_SIGNAL_SEED: Final = "synthetic-primary-idhwt-gbm-count-profile/1.0.0"
_DEMO_PROVENANCE: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "origin": "repository-generated deterministic counts",
        "patient_data": False,
    }
)


def _synthetic_count(symbol: str, length: float) -> float:
    """Generate non-patient integer-like counts with broad expression support."""

    token = int.from_bytes(
        hashlib.sha256(f"{_DEMO_SIGNAL_SEED}:{symbol}".encode()).digest()[:4],
        "big",
    )
    abundance = 8 + token % 4_093
    length_modulation = 0.75 + ((token >> 12) % 101) / 200.0
    return float(round(abundance * length_modulation * max(0.5, min(2.0, length / 8_000.0))))


def synthetic_demo_request() -> GbmRnaPurityRequest:
    catalog = gbm_rna_purity_catalog()
    return GbmRnaPurityRequest(
        sample_id=DEMO_ID,
        context=REQUIRED_CONTEXT,
        counts_provenance_digest=_DEMO_PROVENANCE,
        counts=tuple(
            RawGeneCount(gene_symbol=symbol, raw_count=_synthetic_count(symbol, length))
            for symbol, length in zip(
                catalog.feature_names,
                catalog.feature_lengths,
                strict=True,
            )
        ),
    )


def demo_request_digest() -> str:
    return canonical_request_digest(synthetic_demo_request())


__all__ = ["DEMO_ID", "demo_request_digest", "synthetic_demo_request"]
