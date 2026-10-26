"""Joint-coverage oracles use synthetic measurements and no real specimens."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import FrozenInstanceError, asdict, replace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission.assays import (
    PANEL_STATES,
    AssaySchemaReceipt,
    ParsedAssayPanel,
)
from glio_proteogen.research.cptac_gbm_external_admission.contracts import PANEL, GeneIdentity
from glio_proteogen.research.cptac_gbm_external_admission.coverage import (
    ASSAY_AXES,
    PATTERNS,
    STATES,
    CohortCoverageError,
    summarize_joint_coverage,
)
from glio_proteogen.research.cptac_gbm_external_admission.protein import (
    ConfirmatoryProteinAdmission,
    ProteinAdmissionReceipt,
    ProteinPanelCoverage,
)


def synthetic_assay(values, *, rna, states=None):
    """Build the same immutable public development type returned by a reader."""
    values = np.array(values, dtype=np.float64)
    states = (
        tuple(states)
        if states is not None
        else tuple("observed" if np.isfinite(value) else "missing_measurement" for value in values)
    )
    counts = Counter(states)
    receipt = AssaySchemaReceipt(
        axis=ASSAY_AXES[1] if rna else ASSAY_AXES[0],
        workflow="STAR - Counts" if rna else "AscatNGS",
        annotation_release="GENCODE v36" if rna else None,
        input_bytes=100,
        data_rows=16 + (4 if rna else 0),
        gene_rows=16,
        summary_rows=4 if rna else 0,
        versioned_gene_rows=16,
        par_y_gene_rows=0,
        duplicate_gene_symbol_groups=0,
        ambiguous_reference_gene_ids=0,
        missing_gene_rows=counts["missing_measurement"],
        observed_zero_gene_rows=int(np.sum(values == 0)),
        panel_size=16,
        panel_observed_count=counts["observed"],
        panel_absent_count=counts["absent_feature"],
        panel_unresolved_reference_count=counts["unresolved_reference"],
        panel_ambiguous_identity_count=counts["ambiguous_identity"],
        panel_symbol_disagreement_count=counts["symbol_disagreement"],
        panel_missing_measurement_count=counts["missing_measurement"],
    )
    return ParsedAssayPanel(receipt, values, states)


def synthetic_protein(values, *, symbols=PANEL, candidate_digest="synthetic-order-digest"):
    """A genuine aggregate receipt plus private immutable synthetic matrix."""
    values = np.array(values, dtype=np.float64)
    identities = tuple(
        None if symbol is None else GeneIdentity(f"HGNC:{index}", symbol, str(index), None)
        for index, symbol in enumerate(symbols, start=1)
    )
    panel = []
    for symbol in PANEL:
        rows = [
            index
            for index, identity in enumerate(identities)
            if identity and identity.symbol == symbol
        ]
        observed = int(np.isfinite(values[rows[0]]).sum()) if rows else None
        panel.append(
            ProteinPanelCoverage(
                symbol,
                len(rows),
                observed,
                56 - observed if observed is not None else None,
                observed,
            )
        )
    receipt = ProteinAdmissionReceipt(
        profile_id="cptac-gbm-confirmatory-protein-admission/1.0.0",
        protein_sha256="1" * 64,
        sample_map_sha256="2" * 64,
        hgnc_sha256="3" * 64,
        candidate_digest=candidate_digest,
        candidate_count=56,
        biological_feature_rows=len(identities),
        identified_feature_rows=sum(identity is not None for identity in identities),
        unavailable_identity_rows=sum(identity is None for identity in identities),
        source_aggregate_rows_excluded=3,
        withdrawn_aliquots_excluded=2,
        pool_targets_excluded=1,
        finite_unshared_cells=int(np.isfinite(values).sum()),
        missing_unshared_cells=int(np.isnan(values).sum()),
        finite_zero_unshared_cells=int(np.sum(values == 0)),
        finite_all_peptide_cells=int(np.isfinite(values).sum()),
        missing_all_peptide_cells=int(np.isnan(values).sum()),
        panel_coverage=tuple(panel),
        limitations=("Synthetic source; no biological claim.",),
    )
    immutable = np.frombuffer(values.tobytes(), dtype=np.float64).reshape(values.shape)
    return ConfirmatoryProteinAdmission(candidate_digest, immutable, identities, receipt)


def synthetic_bundle(patterns=None):
    patterns = patterns or tuple(PATTERNS[index % 8] for index in range(56))
    cnv = [
        synthetic_assay([2.0 if pattern[0] == "1" else np.nan] * 16, rna=False)
        for pattern in patterns
    ]
    rna = [
        synthetic_assay([3.0 if pattern[1] == "1" else np.nan] * 16, rna=True)
        for pattern in patterns
    ]
    protein = synthetic_protein(
        [[87654.123 if pattern[2] == "1" else np.nan for pattern in patterns]] * 16
    )
    return protein, rna, cnv


def _gene(receipt, symbol):
    return next(gene for gene in receipt.genes if gene.gene == symbol)


def _states(gene, axis):
    return {count.state: count.specimens for count in gene.assay_states if count.axis == axis}


def test_all_eight_patterns_have_an_independent_exact_count_oracle():
    protein, rna, cnv = synthetic_bundle()
    result = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    assert result.panel_size == 16
    assert result.candidate_specimens == 56
    assert result.verified_rna_files == result.verified_cnv_files == 56
    assert len(result.genes) == 16
    assert tuple(gene.gene for gene in result.genes) == PANEL
    for gene in result.genes:
        assert gene.observed_cnv == gene.observed_rna == gene.observed_protein == 28
        assert gene.joint_complete == 7
        assert gene.zero_cnv == gene.zero_rna == gene.zero_protein == 0
        assert {item.pattern: item.specimens for item in gene.patterns_cnv_rna_protein} == {
            "000": 7,
            "001": 7,
            "010": 7,
            "011": 7,
            "100": 7,
            "101": 7,
            "110": 7,
            "111": 7,
        }
        assert sum(item.specimens for item in gene.patterns_cnv_rna_protein) == 56
    assert result.complete_gene_specimen_pairs == 112


def test_zero_is_observed_while_unavailable_values_stay_missing():
    protein_values = np.full((16, 56), np.nan)
    protein_values[0, 0] = 0
    protein = synthetic_protein(protein_values)
    rna = [
        synthetic_assay([0, *([np.nan] * 15)] if index == 0 else [np.nan] * 16, rna=True)
        for index in range(56)
    ]
    cnv = [
        synthetic_assay([0, *([np.nan] * 15)] if index == 0 else [np.nan] * 16, rna=False)
        for index in range(56)
    ]
    gene = _gene(
        summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv), PANEL[0]
    )
    assert gene.observed_cnv == gene.observed_rna == gene.observed_protein == 1
    assert gene.zero_cnv == gene.zero_rna == gene.zero_protein == 1
    assert gene.joint_complete == 1
    assert {pattern.pattern: pattern.specimens for pattern in gene.patterns_cnv_rna_protein} == {
        "000": 55,
        "001": 0,
        "010": 0,
        "011": 0,
        "100": 0,
        "101": 0,
        "110": 0,
        "111": 1,
    }


def test_feature_absence_differs_from_a_present_protein_row_of_blanks():
    symbols = tuple(symbol for symbol in PANEL if symbol != "CDKN2B")
    values = np.ones((len(symbols), 56))
    values[symbols.index("CDKN2A")] = np.nan
    protein = synthetic_protein(values, symbols=symbols)
    _, rna, cnv = synthetic_bundle(("111",) * 56)
    result = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    absent = _gene(result, "CDKN2B")
    blank = _gene(result, "CDKN2A")
    assert absent.protein_feature_present is False
    assert blank.protein_feature_present is True
    assert absent.observed_protein == blank.observed_protein == 0
    assert absent.joint_complete == blank.joint_complete == 0
    assert absent.zero_protein == blank.zero_protein == 0
    assert _states(absent, ASSAY_AXES[2])["absent_feature"] == 56
    assert _states(absent, ASSAY_AXES[2])["missing_measurement"] == 0
    assert _states(blank, ASSAY_AXES[2])["absent_feature"] == 0
    assert _states(blank, ASSAY_AXES[2])["missing_measurement"] == 56


def test_every_assay_reason_survives_aggregation_without_becoming_zero():
    rna_states = [PANEL_STATES[index % 6] for index in range(56)]
    cnv_states = [PANEL_STATES[(index + 2) % 6] for index in range(56)]
    rna = [
        synthetic_assay([5 if state == "observed" else np.nan] * 16, rna=True, states=(state,) * 16)
        for state in rna_states
    ]
    cnv = [
        synthetic_assay(
            [6 if state == "observed" else np.nan] * 16, rna=False, states=(state,) * 16
        )
        for state in cnv_states
    ]
    protein = synthetic_protein(np.ones((16, 56)))
    result = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    for gene in result.genes:
        assert _states(gene, ASSAY_AXES[0]) == dict(Counter(cnv_states))
        assert _states(gene, ASSAY_AXES[1]) == dict(Counter(rna_states))
        assert gene.zero_cnv == gene.zero_rna == 0
        for axis in ASSAY_AXES:
            assert sum(_states(gene, axis).values()) == 56
            assert tuple(_states(gene, axis)) == STATES


def test_alignment_is_by_supplied_candidate_column_not_independent_marginals():
    patterns = ("111", "100", "010", "001", *(("000",) * 52))
    protein, rna, cnv = synthetic_bundle(patterns)
    aligned = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    shifted = summarize_joint_coverage(
        protein=protein, rna_panels=rna[1:] + rna[:1], cnv_panels=cnv
    )
    assert aligned.genes[0].observed_rna == shifted.genes[0].observed_rna == 2
    assert aligned.genes[0].joint_complete == 1
    assert shifted.genes[0].joint_complete == 0


def test_full_56_support_never_lowers_the_existing_60_oof_gate():
    protein, rna, cnv = synthetic_bundle(("111",) * 56)
    result = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    assert result.complete_gene_specimen_pairs == 896
    assert all(gene.joint_complete == 56 for gene in result.genes)
    assert all(gene.legacy_common_oof_minimum == 60 for gene in result.genes)
    assert not any(gene.legacy_common_oof_support_possible for gene in result.genes)
    assert result.model_fits_performed is False
    assert result.values_transformed is False
    assert result.values_imputed is False
    assert result.legacy_fit_admitted is False
    assert result.independent_validation is False
    assert result.source_axis_compatibility_admitted is False
    assert result.clinical_scope_admitted is False


@pytest.mark.parametrize("assay", ["rna", "cnv"])
@pytest.mark.parametrize("count", [0, 55, 57])
def test_candidate_count_is_fixed_for_each_assay(assay, count):
    protein, rna, cnv = synthetic_bundle()
    if assay == "rna":
        rna = [rna[0]] * count
    else:
        cnv = [cnv[0]] * count
    with pytest.raises(CohortCoverageError):
        summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)


@pytest.mark.parametrize("mode", ["swapped_axes", "wrong_type"])
def test_assay_family_is_required(mode):
    protein, rna, cnv = synthetic_bundle()
    if mode == "swapped_axes":
        rna, cnv = cnv, rna
    else:
        rna[0] = object()
    with pytest.raises(CohortCoverageError):
        summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)


@pytest.mark.parametrize(
    "mode",
    ["one_dimensional", "wrong_count", "wrong_dtype", "infinite", "receipt_count", "receipt_rows"],
)
def test_protein_shape_numeric_type_and_receipt_support_are_required(mode):
    protein, rna, cnv = synthetic_bundle()
    if mode == "one_dimensional":
        protein = replace(protein, values=np.zeros(56))
    elif mode == "wrong_count":
        protein = replace(protein, values=np.zeros((16, 55)))
    elif mode == "wrong_dtype":
        protein = replace(protein, values=np.zeros((16, 56), dtype=np.float32))
    elif mode == "infinite":
        protein = replace(protein, values=np.full((16, 56), np.inf))
    elif mode == "receipt_count":
        protein = replace(protein, receipt=replace(protein.receipt, candidate_count=55))
    else:
        protein = replace(protein, receipt=replace(protein.receipt, biological_feature_rows=15))
    with pytest.raises(CohortCoverageError):
        summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)


def test_duplicate_approved_protein_identity_is_rejected_without_averaging():
    protein = synthetic_protein(np.ones((2, 56)), symbols=("TP53", "TP53"))
    _, rna, cnv = synthetic_bundle()
    with pytest.raises(CohortCoverageError, match="not unique"):
        summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)


def test_unidentified_protein_row_cannot_supply_a_panel_feature():
    protein = synthetic_protein(np.full((1, 56), 87654.123), symbols=(None,))
    _, rna, cnv = synthetic_bundle(("111",) * 56)
    result = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    assert all(
        not gene.protein_feature_present and gene.observed_protein == 0 for gene in result.genes
    )
    assert result.complete_gene_specimen_pairs == 0


def test_aggregation_preserves_inputs_and_contains_no_arrays_or_individual_values():
    protein, rna, cnv = synthetic_bundle()
    before = (
        protein.values.tobytes(),
        tuple(panel.values.tobytes() for panel in rna),
        tuple(panel.values.tobytes() for panel in cnv),
    )
    result = summarize_joint_coverage(protein=protein, rna_panels=rna, cnv_panels=cnv)
    assert before == (
        protein.values.tobytes(),
        tuple(panel.values.tobytes() for panel in rna),
        tuple(panel.values.tobytes() for panel in cnv),
    )
    encoded = json.dumps(asdict(result), allow_nan=False)
    assert "87654.123" not in encoded
    stack = [asdict(result)]
    while stack:
        value = stack.pop()
        assert not isinstance(value, np.ndarray)
        if isinstance(value, dict):
            assert not {
                "sample_id",
                "case_id",
                "file_id",
                "candidate_rows",
                "predictions",
                "residuals",
            }.intersection(value)
            stack.extend(value.values())
        elif isinstance(value, list | tuple):
            assert len(value) not in (56, 112)
            stack.extend(value)
    with pytest.raises(FrozenInstanceError):
        result.candidate_specimens = 1
    assert len(asdict(result)["genes"]) == 16
