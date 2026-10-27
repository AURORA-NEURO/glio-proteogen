"""Synthetic adversarial proofs for exact, distinct local GDC assay readers."""

from __future__ import annotations

import hashlib
import pickle
from dataclasses import FrozenInstanceError, asdict, replace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission import assays
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    HgncReference,
    SourceLock,
    SourceVerificationError,
)


def _reference(identities=None):
    genes = identities or tuple(
        GeneIdentity(f"HGNC:{index}", symbol, str(index), f"ENSG{index:011d}")
        for index, symbol in enumerate(PANEL, start=1)
    )
    by_ensembl = {}
    for gene in genes:
        if gene.ensembl_gene_id:
            by_ensembl.setdefault(gene.ensembl_gene_id, []).append(gene)
    return HgncReference(
        {gene.hgnc_id: gene for gene in genes},
        {key: tuple(values) for key, values in by_ensembl.items()},
        {gene.symbol: gene for gene in genes},
    )


@pytest.fixture
def hgnc():
    return _reference()


def _rna_row(index=1, *, symbol=None, uq="123456.789"):
    return [
        f"ENSG{index:011d}.7",
        symbol or PANEL[index - 1],
        "protein_coding",
        "100",
        "200",
        "300",
        "401.5",
        "502.5",
        uq,
    ]


def _cnv_row(index=1, *, symbol=None, copy="4", minimum="3", maximum="5"):
    return [
        f"ENSG{index:011d}.7",
        symbol or PANEL[index - 1],
        "chr1",
        "10",
        "100",
        copy,
        minimum,
        maximum,
    ]


def _summaries():
    return [
        [label, "", "", "10", "20", "30", "", "", ""] for label in sorted(assays.RNA_SUMMARY_LABELS)
    ]


def _rna(
    rows=None, *, summaries=None, comment=assays.RNA_ANNOTATION_COMMENT, columns=assays.RNA_COLUMNS
):
    records = [
        *(summaries if summaries is not None else _summaries()),
        *(rows if rows is not None else [_rna_row()]),
    ]
    lines = ([comment] if comment is not None else []) + ["\t".join(columns)]
    return ("\n".join([*lines, *("\t".join(row) for row in records)]) + "\n").encode()


def _cnv(rows=None, *, columns=assays.CNV_COLUMNS):
    return (
        "\n".join(
            [
                "\t".join(columns),
                *("\t".join(row) for row in (rows if rows is not None else [_cnv_row()])),
            ]
        )
        + "\n"
    ).encode()


def _lock(payload):
    return SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _read(tmp_path, hgnc, payload, *, cnv=False, lock=None):
    path = tmp_path / "synthetic-assay.tsv"
    path.write_bytes(payload)
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    return reader(path, lock=lock or _lock(payload), hgnc=hgnc)


def test_rna_exposes_only_explicit_uq_in_fixed_panel_order(tmp_path, hgnc):
    result = _read(tmp_path, hgnc, _rna([_rna_row(16, uq="0"), _rna_row(1)]))
    assert result.panel_symbols == PANEL
    assert result.values.dtype == np.float64
    assert result.values.shape == (16,)
    assert result.values[0] == 123456.789
    assert result.values[15] == 0.0
    assert np.isnan(result.values[1:15]).all()
    assert result.observed.tolist() == [True, *([False] * 14), True]
    assert result.panel_states == ("observed", *(("absent_feature",) * 14), "observed")
    assert result.receipt.axis == "star_fpkm_uq_unstranded"
    assert result.receipt.workflow == "STAR - Counts"
    assert result.receipt.annotation_release == "GENCODE v36"
    assert result.receipt.summary_rows == 4
    assert result.receipt.gene_rows == 2
    assert result.receipt.panel_observed_count == 2
    assert result.receipt.panel_absent_count == 14
    assert result.receipt.observed_zero_gene_rows == 1


def test_cnv_missing_is_distinct_from_observed_zero(tmp_path, hgnc):
    result = _read(
        tmp_path,
        hgnc,
        _cnv(
            [
                _cnv_row(1, copy="0", minimum="0", maximum="0"),
                _cnv_row(2, copy="", minimum="", maximum=""),
                _cnv_row(3, copy="4", minimum="1", maximum="8"),
            ]
        ),
        cnv=True,
    )
    assert result.values[0] == 0.0 and result.observed[0]
    assert np.isnan(result.values[1]) and not result.observed[1]
    assert result.panel_states[:3] == ("observed", "missing_measurement", "observed")
    assert result.values[2] == 4.0
    assert result.receipt.axis == "ascat_total_copy_number"
    assert result.receipt.workflow == "AscatNGS"
    assert result.receipt.annotation_release is None
    assert result.receipt.missing_gene_rows == 1
    assert result.receipt.panel_missing_measurement_count == 1
    assert result.receipt.observed_zero_gene_rows == 1
    assert result.receipt.summary_rows == 0


@pytest.mark.parametrize("field", ["bytes", "md5", "sha256"])
def test_every_frozen_lock_component_is_required_before_decoding(tmp_path, hgnc, field):
    payload = b"\xffprivate-tainted-content-not-a-valid-table"
    lock = _lock(payload)
    changes = {"bytes": len(payload) + 1, "md5": "0" * 32, "sha256": "0" * 64}
    with pytest.raises(SourceVerificationError) as error:
        _read(tmp_path, hgnc, payload, lock=replace(lock, **{field: changes[field]}))
    assert "private-tainted" not in str(error.value)


def test_changed_source_is_rejected_without_relocking(tmp_path, hgnc):
    payload = _rna()
    lock = _lock(payload)
    tampered = payload.replace(b"123456.789", b"987654.321")
    with pytest.raises(SourceVerificationError):
        _read(tmp_path, hgnc, tampered, lock=lock)


def test_assay_cap_is_stricter_than_shared_source_cap(tmp_path, hgnc):
    lock = SourceLock(assays.MAX_ASSAY_BYTES + 1, "0" * 32, "0" * 64)
    with pytest.raises(SourceVerificationError):
        assays.parse_star_counts_v36(tmp_path / "never-opened.tsv", lock=lock, hgnc=hgnc)


@pytest.mark.parametrize("cnv", [False, True])
def test_reader_never_modifies_or_creates_files(tmp_path, hgnc, cnv):
    payload = _cnv() if cnv else _rna()
    path = tmp_path / "owned-source.tsv"
    path.write_bytes(payload)
    before = path.stat()
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    reader(path, lock=_lock(payload), hgnc=hgnc)
    assert path.read_bytes() == payload
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert list(tmp_path.iterdir()) == [path]


def test_transient_values_are_hidden_immutable_nonpickleable(tmp_path, hgnc):
    result = _read(tmp_path, hgnc, _rna())
    assert "123456.789" not in repr(result)
    assert "values=" not in repr(result)
    assert "observed=" not in repr(result)
    assert "panel_states=" not in repr(result)
    with pytest.raises(ValueError):
        result.values[0] = 1
    with pytest.raises(ValueError):
        result.values.setflags(write=True)
    with pytest.raises(ValueError):
        result.observed.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        result.receipt.gene_rows = 100
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(result)
    with pytest.raises(TypeError, match="cannot be serialized"):
        result.__getstate__()
    assert not any(isinstance(value, np.ndarray) for value in asdict(result.receipt).values())


def test_transient_constructor_copies_caller_storage(tmp_path, hgnc):
    parsed = _read(tmp_path, hgnc, _rna())
    mutable = parsed.values.copy()
    result = assays.ParsedAssayPanel(parsed.receipt, mutable, parsed.panel_states)
    mutable[0] = 9.0
    assert result.values[0] == 123456.789


@pytest.mark.parametrize(
    "values", [np.zeros(15), np.zeros(16, dtype=np.float32), np.full(16, np.inf), [0.0] * 16]
)
def test_invalid_transient_storage_is_rejected(tmp_path, hgnc, values):
    parsed = _read(tmp_path, hgnc, _rna())
    with pytest.raises(assays.AssayFormatError):
        assays.ParsedAssayPanel(parsed.receipt, values, parsed.panel_states)


@pytest.mark.parametrize("mode", ["length", "unknown", "mask", "mutable", "aggregate"])
def test_transient_states_cannot_misrepresent_availability(tmp_path, hgnc, mode):
    parsed = _read(tmp_path, hgnc, _rna())
    states = parsed.panel_states
    receipt = parsed.receipt
    if mode == "length":
        states = states[:-1]
    elif mode == "unknown":
        states = ("private-tainted-state", *states[1:])
    elif mode == "mask":
        states = ("missing_measurement", *states[1:])
    elif mode == "mutable":
        states = list(states)
    else:
        receipt = replace(receipt, panel_absent_count=0)
    with pytest.raises(assays.AssayFormatError) as error:
        assays.ParsedAssayPanel(receipt, parsed.values, states)
    assert "private-tainted-state" not in str(error.value)


@pytest.mark.parametrize(
    "comment",
    [
        None,
        "# gene-model: GENCODE v35",
        "# gene-model: GENCODE v36 ",
        "# unexpected\n# gene-model: GENCODE v36",
    ],
)
def test_rna_requires_exact_annotation_declaration(tmp_path, hgnc, comment):
    with pytest.raises(assays.AssayFormatError):
        _read(tmp_path, hgnc, _rna(comment=comment))


@pytest.mark.parametrize(
    "columns",
    [
        assays.RNA_COLUMNS[:-1],
        (*assays.RNA_COLUMNS[:-1], "fpkm_fallback"),
        (*assays.RNA_COLUMNS[:-2], "fpkm_uq_unstranded", "fpkm_unstranded"),
    ],
)
def test_rna_does_not_fall_back_when_uq_column_is_missing_or_moved(tmp_path, hgnc, columns):
    with pytest.raises(assays.AssayFormatError):
        _read(tmp_path, hgnc, _rna(columns=columns))


@pytest.mark.parametrize(
    "mode",
    [
        "missing",
        "duplicate",
        "unexpected",
        "metadata",
        "normalized",
        "raw_negative",
        "raw_fractional",
    ],
)
def test_summary_rows_are_exact_counters_not_gene_measurements(tmp_path, hgnc, mode):
    rows = _summaries()
    if mode == "missing":
        rows.pop()
    elif mode == "duplicate":
        rows.append(rows[0].copy())
    elif mode == "unexpected":
        rows[0][0] = "N_unexpected"
    elif mode == "metadata":
        rows[0][1] = "tainted-case-private"
    elif mode == "normalized":
        rows[0][8] = "0"
    elif mode == "raw_negative":
        rows[0][3] = "-1"
    else:
        rows[0][3] = "1.5"
    with pytest.raises(assays.AssayFormatError) as error:
        _read(tmp_path, hgnc, _rna(summaries=rows))
    assert "tainted-case-private" not in str(error.value)


@pytest.mark.parametrize("cnv", [False, True])
@pytest.mark.parametrize("version", ["7", "8"])
def test_exact_and_core_duplicate_gene_ids_fail_closed(tmp_path, hgnc, cnv, version):
    row = _cnv_row() if cnv else _rna_row()
    duplicate = row.copy()
    duplicate[0] = f"ENSG00000000001.{version}"
    payload = _cnv([row, duplicate]) if cnv else _rna([row, duplicate])
    with pytest.raises(assays.AssayFormatError, match="duplicate"):
        _read(tmp_path, hgnc, payload, cnv=cnv)


def test_par_y_identity_is_preserved_and_never_merged_with_x(tmp_path, hgnc):
    counterpart = _rna_row(symbol="OTHER_GENE")
    counterpart[0] += "_PAR_Y"
    result = _read(tmp_path, hgnc, _rna([_rna_row(), counterpart]))
    assert result.values[0] == 123456.789
    assert result.receipt.gene_rows == 2
    assert result.receipt.par_y_gene_rows == 1
    only_y = _read(tmp_path, hgnc, _rna([counterpart]))
    assert not only_y.observed.any()
    assert only_y.receipt.panel_absent_count == 16


@pytest.mark.parametrize(
    "gene_id",
    [
        "ENSG00000000001.bad",
        "ENSG00000000001.0",
        "ENSG00000000001_PAR_Y.7",
        "ENSG00000000001.7.extra",
        "private-tainted-identifier",
    ],
)
def test_gene_id_normalization_never_guesses(tmp_path, hgnc, gene_id):
    row = _rna_row()
    row[0] = gene_id
    with pytest.raises(assays.AssayFormatError) as error:
        _read(tmp_path, hgnc, _rna([row]))
    assert gene_id not in str(error.value)


@pytest.mark.parametrize("cnv", [False, True])
def test_stable_id_requires_approved_symbol_agreement(tmp_path, hgnc, cnv):
    row = _cnv_row(symbol="UNAPPROVED_ALIAS") if cnv else _rna_row(symbol="UNAPPROVED_ALIAS")
    result = _read(tmp_path, hgnc, _cnv([row]) if cnv else _rna([row]), cnv=cnv)
    assert not result.observed.any()
    assert result.receipt.panel_symbol_disagreement_count == 1
    assert result.panel_states[0] == "symbol_disagreement"
    assert result.receipt.panel_absent_count == 15


def test_symbol_alone_cannot_substitute_for_stable_identifier(tmp_path, hgnc):
    row = _rna_row()
    row[0] = "ENSG99999999999.1"
    result = _read(tmp_path, hgnc, _rna([row]))
    assert not result.observed.any()
    assert result.receipt.panel_absent_count == 16


def test_ambiguous_reference_is_withheld_without_merging(tmp_path, hgnc):
    other = GeneIdentity("HGNC:999", "OTHER_GENE", "999", "ENSG00000000001")
    reference = _reference((*hgnc.by_hgnc.values(), other))
    result = _read(tmp_path, reference, _rna())
    assert np.isnan(result.values[0])
    assert result.receipt.panel_ambiguous_identity_count == 1
    assert result.panel_states[0] == "ambiguous_identity"
    assert result.receipt.ambiguous_reference_gene_ids == 1


def test_duplicate_symbols_do_not_choose_or_average_a_gene(tmp_path, hgnc):
    other = _rna_row(2, symbol=PANEL[0], uq="1")
    result = _read(tmp_path, hgnc, _rna([_rna_row(), other]))
    assert not result.observed.any()
    assert result.receipt.duplicate_gene_symbol_groups == 1
    assert result.receipt.panel_ambiguous_identity_count == 1
    assert result.receipt.panel_symbol_disagreement_count == 1


def test_reference_without_ensembl_identity_remains_unresolved(tmp_path, hgnc):
    genes = tuple(
        replace(gene, ensembl_gene_id=None) if gene.symbol == PANEL[0] else gene
        for gene in hgnc.by_hgnc.values()
    )
    result = _read(tmp_path, _reference(genes), _rna())
    assert not result.observed.any()
    assert result.receipt.panel_unresolved_reference_count == 1
    assert result.panel_states[0] == "unresolved_reference"
    result = _read(tmp_path, _reference(tuple(genes[1:])), _rna())
    assert result.receipt.panel_unresolved_reference_count == 1


@pytest.mark.parametrize("column", [3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize("value", ["", "NaN", "inf", "-1", "1_000", " 1"])
def test_all_rna_numeric_fields_are_validated_without_axis_fallback(tmp_path, hgnc, column, value):
    row = _rna_row()
    row[column] = value
    with pytest.raises(assays.AssayFormatError):
        _read(tmp_path, hgnc, _rna([row]))


@pytest.mark.parametrize(
    "values",
    [
        ("", "0", "0"),
        ("NA", "NA", "NA"),
        ("-1", "0", "1"),
        ("1.5", "1", "2"),
        ("3", "4", "5"),
        ("6", "4", "5"),
        ("NaN", "0", "1"),
        ("1e309", "0", "1"),
    ],
)
def test_cnv_partial_missing_invalid_or_inconsistent_calls_fail(tmp_path, hgnc, values):
    row = _cnv_row(copy=values[0], minimum=values[1], maximum=values[2])
    with pytest.raises(assays.AssayFormatError):
        _read(tmp_path, hgnc, _cnv([row]), cnv=True)


@pytest.mark.parametrize(
    ("start", "end"), [("101", "100"), ("-1", "100"), ("1.5", "100"), ("", "100")]
)
def test_cnv_requires_consistent_integer_intervals(tmp_path, hgnc, start, end):
    row = _cnv_row()
    row[3:5] = [start, end]
    with pytest.raises(assays.AssayFormatError):
        _read(tmp_path, hgnc, _cnv([row]), cnv=True)


@pytest.mark.parametrize(
    "columns",
    [
        (*assays.CNV_COLUMNS, "major_copy_number"),
        (*assays.CNV_COLUMNS[:5], "segment_mean", *assays.CNV_COLUMNS[6:]),
        (*assays.CNV_COLUMNS[:5], "gistic_score", *assays.CNV_COLUMNS[6:]),
    ],
)
def test_cnv_does_not_admit_other_copy_number_axes(tmp_path, hgnc, columns):
    with pytest.raises(assays.AssayFormatError):
        _read(tmp_path, hgnc, _cnv(columns=columns), cnv=True)


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff",
        b"",
        b"\x1f\x8bgzip",
        b"\x00private-tainted",
        _rna([_rna_row()[:-1]]),
        _rna([[*_rna_row(), "extra"]]),
        _rna([_rna_row(symbol="X" * 4097)]),
        _rna([], summaries=[]),
    ],
)
def test_invalid_encoding_width_or_empty_schema_is_sanitized(tmp_path, hgnc, payload):
    if not payload:
        payload = b"\n"
    with pytest.raises(assays.AssayFormatError) as error:
        _read(tmp_path, hgnc, payload)
    assert "private-tainted" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_row_cap_is_checked_before_gene_loop(tmp_path, hgnc):
    repeated = ["\t".join(_cnv_row())] * (assays.MAX_ASSAY_ROWS + 1)
    payload = ("\t".join(assays.CNV_COLUMNS) + "\n" + "\n".join(repeated)).encode()
    assert len(payload) < assays.MAX_ASSAY_BYTES
    with pytest.raises(assays.AssayFormatError, match="row count"):
        _read(tmp_path, hgnc, payload, cnv=True)


def test_crlf_and_utf8_bom_keep_exact_semantics(tmp_path, hgnc):
    payload = b"\xef\xbb\xbf" + _rna().replace(b"\n", b"\r\n")
    result = _read(tmp_path, hgnc, payload)
    assert result.values[0] == 123456.789
    assert result.receipt.input_bytes == len(payload)


def test_receipt_contains_counts_and_no_measurements_or_identifiers(tmp_path, hgnc):
    result = _read(tmp_path, hgnc, _rna())
    receipt = asdict(result.receipt)
    assert all(value is None or isinstance(value, str | int) for value in receipt.values())
    assert "123456.789" not in repr(receipt)
    assert "ENSG" not in repr(receipt)
    assert "synthetic-assay" not in repr(receipt)
    assert not {"file_id", "sample_id", "case_id", "gene_values", "patient_values"}.intersection(
        receipt
    )
    assert sum(
        receipt[key]
        for key in (
            "panel_observed_count",
            "panel_absent_count",
            "panel_unresolved_reference_count",
            "panel_ambiguous_identity_count",
            "panel_symbol_disagreement_count",
            "panel_missing_measurement_count",
        )
    ) == len(PANEL)
