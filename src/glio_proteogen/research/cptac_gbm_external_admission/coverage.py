"""Aggregate joint observed coverage without fitting or harmonizing assay axes."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

import numpy as np

from .assays import ParsedAssayPanel
from .contracts import PANEL

if TYPE_CHECKING:
    from .protein import ConfirmatoryProteinAdmission

PROFILE_ID: Final = "cptac-gbm-confirmatory-multimodal-admission/1.0.0"
CANDIDATE_COUNT: Final = 56
PATTERNS: Final = tuple(f"{value:03b}" for value in range(8))
ASSAY_AXES: Final = (
    "ascat_total_copy_number",
    "star_fpkm_uq_unstranded",
    "cdap_unshared_log2_specimen_reference_ratio",
)
STATES: Final = (
    "observed",
    "absent_feature",
    "unresolved_reference",
    "ambiguous_identity",
    "symbol_disagreement",
    "missing_measurement",
)


class CohortCoverageError(ValueError):
    """Sanitized rejection of a mismatched transient assay bundle."""


@dataclass(frozen=True, slots=True)
class MissingnessPattern:
    pattern: str
    specimens: int


@dataclass(frozen=True, slots=True)
class AssayStateCount:
    axis: str
    state: str
    specimens: int


@dataclass(frozen=True, slots=True)
class GeneJointCoverage:
    gene: str
    candidate_specimens: int
    protein_feature_present: bool
    observed_cnv: int
    observed_rna: int
    observed_protein: int
    joint_complete: int
    zero_cnv: int
    zero_rna: int
    zero_protein: int
    patterns_cnv_rna_protein: tuple[MissingnessPattern, ...]
    assay_states: tuple[AssayStateCount, ...]
    legacy_common_oof_minimum: int
    legacy_common_oof_support_possible: bool


@dataclass(frozen=True, slots=True)
class JointCoverageReceipt:
    profile_id: str
    candidate_specimens: int
    panel_size: int
    verified_rna_files: int
    verified_cnv_files: int
    source_axes: tuple[str, ...]
    complete_gene_specimen_pairs: int
    genes: tuple[GeneJointCoverage, ...]
    model_fits_performed: bool
    values_transformed: bool
    values_imputed: bool
    legacy_fit_admitted: bool
    source_axis_compatibility_admitted: bool
    clinical_scope_admitted: bool
    independent_validation: bool
    limitations: tuple[str, ...]


def _check_panels(panels: Sequence[ParsedAssayPanel], *, axis: str) -> None:
    if len(panels) != CANDIDATE_COUNT:
        raise CohortCoverageError("the frozen candidate panel requires exactly56 assay files")
    for panel in panels:
        if not isinstance(panel, ParsedAssayPanel) or panel.receipt.axis != axis:
            raise CohortCoverageError("assay family or ordering contract is invalid")
        if panel.panel_symbols != PANEL or panel.values.shape != (len(PANEL),):
            raise CohortCoverageError("assay panel identity or shape is invalid")


def summarize_joint_coverage(
    *,
    protein: ConfirmatoryProteinAdmission,
    rna_panels: Sequence[ParsedAssayPanel],
    cnv_panels: Sequence[ParsedAssayPanel],
) -> JointCoverageReceipt:
    """Summarize identically ordered candidates; source plan owns their exact order.

    Candidate order is supplied by the one frozen plan for all three assays.
    This pure aggregation does not establish metadata origin or patient identity.
    """
    _check_panels(rna_panels, axis=ASSAY_AXES[1])
    _check_panels(cnv_panels, axis=ASSAY_AXES[0])
    if (
        protein.values.ndim != 2
        or protein.values.shape != (len(protein.identities), CANDIDATE_COUNT)
        or protein.values.dtype != np.dtype(np.float64)
        or bool(np.any(np.isinf(protein.values)))
        or protein.receipt.candidate_count != CANDIDATE_COUNT
        or protein.receipt.biological_feature_rows != len(protein.identities)
    ):
        raise CohortCoverageError("protein shape, identity support or numeric type is invalid")
    by_symbol: dict[str, int] = {}
    for row, identity in enumerate(protein.identities):
        if identity is None:
            continue
        if identity.symbol in by_symbol:
            raise CohortCoverageError("protein approved identity is not unique")
        by_symbol[identity.symbol] = row
    rna = np.column_stack([panel.values for panel in rna_panels])
    cnv = np.column_stack([panel.values for panel in cnv_panels])
    genes = []
    for index, symbol in enumerate(PANEL):
        source_row = by_symbol.get(symbol)
        protein_values = (
            protein.values[source_row]
            if source_row is not None
            else np.full(CANDIDATE_COUNT, np.nan, dtype=np.float64)
        )
        observed = np.column_stack(
            (np.isfinite(cnv[index]), np.isfinite(rna[index]), np.isfinite(protein_values))
        )
        patterns = Counter("".join("1" if value else "0" for value in row) for row in observed)
        state_counts: list[AssayStateCount] = []
        for axis, panels in ((ASSAY_AXES[0], cnv_panels), (ASSAY_AXES[1], rna_panels)):
            counts = Counter(panel.panel_states[index] for panel in panels)
            state_counts.extend(AssayStateCount(axis, state, counts[state]) for state in STATES)
        protein_states = Counter(
            "observed"
            if finite
            else "missing_measurement"
            if source_row is not None
            else "absent_feature"
            for finite in np.isfinite(protein_values)
        )
        state_counts.extend(
            AssayStateCount(ASSAY_AXES[2], state, protein_states[state]) for state in STATES
        )
        complete = int(np.sum(np.all(observed, axis=1)))
        genes.append(
            GeneJointCoverage(
                gene=symbol,
                candidate_specimens=CANDIDATE_COUNT,
                protein_feature_present=source_row is not None,
                observed_cnv=int(np.sum(observed[:, 0])),
                observed_rna=int(np.sum(observed[:, 1])),
                observed_protein=int(np.sum(observed[:, 2])),
                joint_complete=complete,
                zero_cnv=int(np.sum(cnv[index] == 0.0)),
                zero_rna=int(np.sum(rna[index] == 0.0)),
                zero_protein=int(np.sum(protein_values == 0.0)),
                patterns_cnv_rna_protein=tuple(
                    MissingnessPattern(value, patterns[value]) for value in PATTERNS
                ),
                assay_states=tuple(state_counts),
                legacy_common_oof_minimum=60,
                legacy_common_oof_support_possible=complete >= 60,
            )
        )
    return JointCoverageReceipt(
        profile_id=PROFILE_ID,
        candidate_specimens=CANDIDATE_COUNT,
        panel_size=len(PANEL),
        verified_rna_files=len(rna_panels),
        verified_cnv_files=len(cnv_panels),
        source_axes=ASSAY_AXES,
        complete_gene_specimen_pairs=sum(gene.joint_complete for gene in genes),
        genes=tuple(genes),
        model_fits_performed=False,
        values_transformed=False,
        values_imputed=False,
        legacy_fit_admitted=False,
        source_axis_compatibility_admitted=False,
        clinical_scope_admitted=False,
        independent_validation=False,
        limitations=(
            "Coverage is measured support, not prediction quality or biological validation.",
            "Exact candidate/file bindings come from caller-trusted frozen metadata captures; hashes do not authenticate their issuer.",
            "The protein, RNA and CNV axes retain their own processing and cannot substitute for the original TableS2 source locks.",
            "No gene can reach the unchanged legacy common-OOF minimum60 with56 candidates; no support gate is lowered.",
            "Molecular WHO class, treatment context, donor independence and reuse terms remain unadmitted.",
            "Unshared protein blanks are never filled using all-peptide measurements, RNA predictions or zeros.",
            "All real-data derivatives remain local_only_terms_unverified and must not be uploaded or committed.",
        ),
    )
