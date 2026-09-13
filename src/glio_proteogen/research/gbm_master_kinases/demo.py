"""Versioned synthetic phosphosite contrast for the SPHINKS concordance lane."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Final

from .canonical import sha256_digest
from .catalog import master_kinase_catalog
from .contracts import (
    MasterKinaseRequest,
    PhosphositeEvidenceState,
    PhosphositeObservation,
    StandardizedContrastReference,
)

DEMO_ID: Final = "synthetic-sphinks-gbm-master-kinase-concordance-v1"
_DEMO_SOURCE_DIGEST: Final = sha256_digest(
    {
        "demo_id": DEMO_ID,
        "observation_semantics": "synthetic_standardized_log2_phosphosite_contrast",
        "patient_data": False,
    }
)


def _residue_stratum(site: str) -> str:
    residues = sorted(set(re.findall(r"([STY])\d+[sty]?", site.rsplit("-", 1)[-1])))
    return "".join(residues) or "OTHER"


@lru_cache(maxsize=1)
def synthetic_demo_request() -> MasterKinaseRequest:
    """Return a synthetic four-subtype contrast over real pinned source sites."""

    catalog = master_kinase_catalog()
    subtype_effect = {"GPM": 1.10, "MTC": -0.85, "NEU": 0.72, "PPR": 1.28}
    used: set[str] = set()
    observations: list[PhosphositeObservation] = []
    phkg2_sites = {edge.source_site_label for edge in catalog.edges_by_kinase["PHKG2"]}
    site_subtypes: dict[str, set[str]] = {}
    for edge in catalog.edges:
        site_subtypes.setdefault(edge.source_site_label, set()).add(edge.subtype)
    ordered_masters = tuple(
        sorted(
            catalog.masters,
            key=lambda item: (
                item.hgnc_symbol != "PHKG2",
                len({edge.source_site_label for edge in catalog.edges_by_kinase[item.hgnc_symbol]}),
                item.hgnc_symbol,
            ),
        )
    )
    for master_index, master in enumerate(ordered_masters, start=1):
        all_candidates = {
            edge.source_site_label for edge in catalog.edges_by_kinase[master.hgnc_symbol]
        }
        if master.hgnc_symbol != "PHKG2":
            all_candidates -= phkg2_sites
        candidate_sites = tuple(
            sorted(
                all_candidates,
                key=lambda site: (
                    site_subtypes[site] != {master.subtype},
                    site,
                ),
            )
        )
        requested_count = 8 if master.hgnc_symbol == "PHKG2" else 6
        selected = tuple(site for site in candidate_sites if site not in used)[:requested_count]
        used.update(selected)
        for site_index, site in enumerate(selected, start=1):
            base = subtype_effect[master.subtype]
            effect = base + ((master_index + site_index) % 5 - 2) * 0.045
            observations.append(
                PhosphositeObservation(
                    observation_id=f"demo.signature.{master_index:02d}.{site_index:02d}",
                    phosphosite_id=site,
                    state=PhosphositeEvidenceState.OBSERVED,
                    standardized_effect=round(effect, 6),
                    standard_error=0.28,
                    quality_weight=0.95,
                    provenance_digest=_DEMO_SOURCE_DIGEST,
                )
            )
    signature_sites = {edge.source_site_label for edge in catalog.edges}
    available_background = tuple(
        site for site in sorted(catalog.background_labels - signature_sites - used)
    )
    by_stratum: dict[str, list[str]] = {}
    for site in available_background:
        by_stratum.setdefault(_residue_stratum(site), []).append(site)
    represented_strata = sorted({_residue_stratum(site) for site in used})
    background_selection: list[str] = []
    for stratum in represented_strata:
        background_selection.extend(by_stratum.get(stratum, ())[:12])
    selected_background = set(background_selection)
    for site in available_background:
        if len(background_selection) >= 128:
            break
        if site not in selected_background:
            background_selection.append(site)
            selected_background.add(site)
    background_sites = tuple(background_selection)
    for index, site in enumerate(background_sites, start=1):
        observations.append(
            PhosphositeObservation(
                observation_id=f"demo.background.{index:03d}",
                phosphosite_id=site,
                state=PhosphositeEvidenceState.OBSERVED,
                standardized_effect=round(-1.15 + (index % 37) * 0.0625, 6),
                standard_error=0.34,
                quality_weight=0.90,
                provenance_digest=_DEMO_SOURCE_DIGEST,
            )
        )
    used_observation_sites = {item.phosphosite_id for item in observations}
    inactive_site = next(
        site for site in sorted(catalog.background_labels) if site not in used_observation_sites
    )
    observations.append(
        PhosphositeObservation(
            observation_id="demo.explicit-missing",
            phosphosite_id=inactive_site,
            state=PhosphositeEvidenceState.MISSING,
            quality_weight=0.0,
            provenance_digest=_DEMO_SOURCE_DIGEST,
        )
    )
    return MasterKinaseRequest(
        sample_id=DEMO_ID,
        observations=tuple(observations),
        bootstrap_replicates=16,
        permutation_replicates=64,
        contrast_reference=StandardizedContrastReference(
            contrast_id="synthetic.glioma-like.contrast.v1",
            numerator_label="synthetic glioma-like state",
            denominator_label="synthetic reference state",
        ),
    )


def build_demo_request() -> MasterKinaseRequest:
    """Compatibility alias for callers that prefer a builder-shaped API."""

    return synthetic_demo_request()


def demo_request_digest() -> str:
    return synthetic_demo_request().request_digest


__all__ = ["DEMO_ID", "build_demo_request", "demo_request_digest", "synthetic_demo_request"]
