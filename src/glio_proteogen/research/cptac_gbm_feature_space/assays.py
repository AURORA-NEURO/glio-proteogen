"""Exact GDC assay validation projected onto one admitted immutable gene axis.

Every source record is validated, including genes outside the requested axis.
This additive reader preserves the frozen FPKM-UQ and absolute AscatNGS axes;
it neither changes the sixteen-gene readers nor infers alternative measurements.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import numpy as np

from glio_proteogen.research.cptac_gbm_external_admission import assays as legacy
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    HgncReference,
    SourceLock,
)
from glio_proteogen.research.cptac_gbm_external_admission.source import read_verified_source

from .contracts import FeatureAxis, ProjectedAssay, ProjectionReceipt

if TYPE_CHECKING:
    from pathlib import Path

AssayFormatError = legacy.AssayFormatError
_STATE_CODE = {state: index for index, state in enumerate(legacy.PANEL_STATES)}


def _validate_axis(axis: FeatureAxis, hgnc: HgncReference) -> None:
    if not isinstance(axis, FeatureAxis) or not isinstance(hgnc, HgncReference):
        raise AssayFormatError("projection requires an admitted axis and exact HGNC reference")
    if any(
        hgnc.by_hgnc.get(identity.hgnc_id) != identity
        or hgnc.by_symbol.get(identity.symbol) != identity
        for identity in axis.identities
    ):
        raise AssayFormatError("feature axis identities disagree with the HGNC reference")


def _parse(payload: bytes, *, hgnc: HgncReference, axis: FeatureAxis, rna: bool) -> ProjectedAssay:
    records = legacy._records(payload, rna=rna)
    genes: dict[str, legacy._GeneRow] = {}
    originals: set[str] = set()
    symbols: Counter[str] = Counter()
    summaries: set[str] = set()
    versioned = par_y = missing = zeros = ambiguous = 0
    for row in records:
        if rna and row[0] in legacy.RNA_SUMMARY_LABELS:
            if row[0] in summaries or any(row[index] for index in (1, 2, 6, 7, 8)):
                raise AssayFormatError(
                    "RNA summary rows have invalid metadata or normalized values"
                )
            for raw_count in row[3:6]:
                legacy._unsigned_integer(raw_count)
            summaries.add(row[0])
            continue
        gene_id = legacy._identifier(row[0])
        if row[0] in originals or gene_id in genes:
            raise AssayFormatError(
                "assay contains duplicate exact or version-stripped gene identifiers"
            )
        legacy._name(row[1])
        value = legacy._rna_value(row) if rna else legacy._cnv_value(row)
        originals.add(row[0])
        genes[gene_id] = legacy._GeneRow(row[1], value)
        symbols[row[1]] += 1
        versioned += row[0] != gene_id
        par_y += gene_id.endswith("_PAR_Y")
        missing += value is None
        zeros += value == 0.0
        ambiguous += len(hgnc.by_ensembl.get(gene_id, ())) > 1
    if not genes or (rna and summaries != legacy.RNA_SUMMARY_LABELS):
        raise AssayFormatError("assay must contain gene rows and the required RNA summaries")
    values = np.full(len(axis.identities), np.nan, dtype=np.float64)
    states = np.empty(len(axis.identities), dtype=np.uint8)
    outcomes: Counter[str] = Counter()
    for index, identity in enumerate(axis.identities):
        state, value = legacy._panel_gene(identity.symbol, genes, symbols, hgnc)
        states[index] = _STATE_CODE[state]
        outcomes[state] += 1
        if value is not None:
            values[index] = value
    receipt = ProjectionReceipt(
        axis="star_fpkm_uq_unstranded" if rna else "ascat_total_copy_number",
        workflow="STAR - Counts" if rna else "AscatNGS",
        annotation_release="GENCODE v36" if rna else None,
        input_bytes=len(payload),
        data_rows=len(records),
        gene_rows=len(genes),
        summary_rows=len(summaries),
        versioned_gene_rows=versioned,
        par_y_gene_rows=par_y,
        duplicate_gene_symbol_groups=sum(count > 1 for count in symbols.values()),
        ambiguous_reference_gene_ids=ambiguous,
        missing_gene_rows=missing,
        observed_zero_gene_rows=zeros,
        feature_axis_digest=axis.digest,
        feature_count=len(axis.identities),
        state_counts=tuple(outcomes[state] for state in legacy.PANEL_STATES),
    )
    return ProjectedAssay(receipt, values, states)


def parse_star_counts_v36(
    path: Path, *, lock: SourceLock, hgnc: HgncReference, axis: FeatureAxis
) -> ProjectedAssay:
    """Project explicit unstranded FPKM-UQ after validating every source row."""
    _validate_axis(axis, hgnc)
    payload = read_verified_source(path, lock, max_bytes=legacy.MAX_ASSAY_BYTES)
    return _parse(payload, hgnc=hgnc, axis=axis, rna=True)


def parse_ascat_gene_cnv(
    path: Path, *, lock: SourceLock, hgnc: HgncReference, axis: FeatureAxis
) -> ProjectedAssay:
    """Project integer total copy number, preserving missingness and observed zero."""
    _validate_axis(axis, hgnc)
    payload = read_verified_source(path, lock, max_bytes=legacy.MAX_ASSAY_BYTES)
    return _parse(payload, hgnc=hgnc, axis=axis, rna=False)


__all__ = ["AssayFormatError", "parse_ascat_gene_cnv", "parse_star_counts_v36"]
