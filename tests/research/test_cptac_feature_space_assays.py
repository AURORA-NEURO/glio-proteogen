"""Synthetic admission proofs for arbitrary, exact HGNC assay projections."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict, fields, replace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission import assays as legacy
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    HgncReference,
    SourceLock,
    SourceVerificationError,
)
from glio_proteogen.research.cptac_gbm_feature_space import assays
from glio_proteogen.research.cptac_gbm_feature_space.contracts import STATES, FeatureAxis


def _gene(index, symbol=None, *, ensembl=None):
    return GeneIdentity(
        f"HGNC:{index}",
        symbol or f"SYNTHETIC{index}",
        str(index),
        ensembl if ensembl is not None else f"ENSG{index:011d}",
    )


def _reference(*genes):
    groups = {}
    for gene in genes:
        if gene.ensembl_gene_id is not None:
            groups.setdefault(gene.ensembl_gene_id, []).append(gene)
    return HgncReference(
        {gene.hgnc_id: gene for gene in genes},
        {key: tuple(value) for key, value in groups.items()},
        {gene.symbol: gene for gene in genes},
    )


def _axis(*genes):
    return FeatureAxis(tuple(sorted(genes, key=lambda gene: gene.hgnc_id)))


def _row(gene, *, cnv=False, value="4"):
    assert gene.ensembl_gene_id is not None
    identifier = gene.ensembl_gene_id.replace("_PAR_Y", ".7_PAR_Y")
    if not identifier.endswith("_PAR_Y"):
        identifier += ".7"
    if cnv:
        bounds = ("", "") if value == "" else ("0", "100")
        return [identifier, gene.symbol, "chr1", "10", "100", value, *bounds]
    return [identifier, gene.symbol, "protein_coding", "10", "20", "30", "41", "52", value]


def _summaries():
    return [
        [label, "", "", "10", "20", "30", "", "", ""] for label in sorted(legacy.RNA_SUMMARY_LABELS)
    ]


def _payload(rows, *, cnv=False, summaries=None):
    lines = [] if cnv else [legacy.RNA_ANNOTATION_COMMENT]
    lines.append("\t".join(legacy.CNV_COLUMNS if cnv else legacy.RNA_COLUMNS))
    records = rows if cnv else [*(_summaries() if summaries is None else summaries), *rows]
    return ("\n".join([*lines, *("\t".join(row) for row in records)]) + "\n").encode()


def _lock(payload):
    return SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _read(tmp_path, payload, hgnc, axis, *, cnv=False):
    path = tmp_path / "synthetic-assay.tsv"
    path.write_bytes(payload)
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    return reader(path, lock=_lock(payload), hgnc=hgnc, axis=axis)


@pytest.mark.parametrize("cnv", [False, True])
def test_exact_sixteen_gene_projection_matches_frozen_reader(tmp_path, cnv):
    genes = tuple(_gene(index, symbol) for index, symbol in enumerate(PANEL, start=1))
    hgnc, axis = _reference(*genes), _axis(*genes)
    rows = [_row(gene, cnv=cnv, value=str(index)) for index, gene in enumerate(genes) if index != 2]
    if cnv:
        rows[4][5:8] = ["", "", ""]
    rows.reverse()
    payload = _payload(rows, cnv=cnv)
    projected = _read(tmp_path, payload, hgnc, axis, cnv=cnv)
    original_reader = legacy.parse_ascat_gene_cnv if cnv else legacy.parse_star_counts_v36
    original = original_reader(tmp_path / "synthetic-assay.tsv", lock=_lock(payload), hgnc=hgnc)
    ordering = [PANEL.index(identity.symbol) for identity in axis.identities]
    np.testing.assert_array_equal(projected.values, original.values[ordering])
    assert projected.states.tolist() == [
        STATES.index(original.panel_states[index]) for index in ordering
    ]
    for field in fields(projected.receipt):
        if hasattr(original.receipt, field.name):
            assert getattr(projected.receipt, field.name) == getattr(original.receipt, field.name)
    assert projected.receipt.state_counts == tuple(
        original.panel_states.count(state) for state in STATES
    )
    assert projected.receipt.feature_count == 16
    assert projected.receipt.feature_axis_digest == axis.digest


@pytest.mark.parametrize("cnv", [False, True])
def test_nonpanel_projection_follows_hgnc_axis_and_exact_ids_not_record_order(tmp_path, cnv):
    first, second, third = _gene(2), _gene(10), _gene(90)
    hgnc, axis = _reference(first, second, third), _axis(first, second, third)
    rows = [
        _row(first, cnv=cnv, value="9"),
        _row(third, cnv=cnv, value="0"),
        _row(second, cnv=cnv, value="7"),
    ]
    result = _read(tmp_path, _payload(rows, cnv=cnv), hgnc, axis, cnv=cnv)
    assert axis.hgnc_ids == ("HGNC:10", "HGNC:2", "HGNC:90")
    assert result.values.tolist() == [7.0, 9.0, 0.0]
    assert result.states.tolist() == [0, 0, 0]
    assert result.receipt.observed_zero_gene_rows == 1
    assert result.receipt.feature_count == 3


def test_six_unavailability_states_are_distinct_and_missing_is_not_zero(tmp_path):
    observed, absent, no_reference, ambiguous, disagreement, missing = (
        _gene(index) for index in range(1, 7)
    )
    no_reference = replace(no_reference, ensembl_gene_id=None)
    collision = _gene(7, ensembl=ambiguous.ensembl_gene_id)
    axis = _axis(observed, absent, no_reference, ambiguous, disagreement, missing)
    hgnc = _reference(*axis.identities, collision)
    wrong_symbol = _row(disagreement, cnv=True)
    wrong_symbol[1] = "SYNTHETIC_OLD_SYMBOL"
    rows = [
        _row(observed, cnv=True, value="0"),
        _row(ambiguous, cnv=True),
        wrong_symbol,
        _row(missing, cnv=True, value=""),
    ]
    result = _read(tmp_path, _payload(rows, cnv=True), hgnc, axis, cnv=True)
    assert result.states.tolist() == list(range(6))
    assert result.values[0] == 0.0
    assert np.isnan(result.values[1:]).all()
    assert result.receipt.state_counts == (1, 1, 1, 1, 1, 1)
    assert result.receipt.ambiguous_reference_gene_ids == 1
    assert result.receipt.missing_gene_rows == 1
    assert result.receipt.observed_zero_gene_rows == 1


@pytest.mark.parametrize("cnv", [False, True])
def test_symbol_on_wrong_gene_never_fills_an_absent_identity(tmp_path, cnv):
    wanted, unrelated = _gene(1), _gene(2)
    row = _row(unrelated, cnv=cnv, value="99")
    row[1] = wanted.symbol
    result = _read(
        tmp_path, _payload([row], cnv=cnv), _reference(wanted, unrelated), _axis(wanted), cnv=cnv
    )
    assert result.states.tolist() == [1]
    assert np.isnan(result.values).all()


@pytest.mark.parametrize("cnv", [False, True])
def test_unrelated_duplicate_symbol_withholds_exact_gene_instead_of_taking_first(tmp_path, cnv):
    wanted, unrelated = _gene(1), _gene(2)
    foreign_row = _row(unrelated, cnv=cnv, value="99")
    foreign_row[1] = wanted.symbol
    for rows in ([_row(wanted, cnv=cnv), foreign_row], [foreign_row, _row(wanted, cnv=cnv)]):
        result = _read(
            tmp_path, _payload(rows, cnv=cnv), _reference(wanted, unrelated), _axis(wanted), cnv=cnv
        )
        assert result.states.tolist() == [3]
        assert np.isnan(result.values).all()
        assert result.receipt.duplicate_gene_symbol_groups == 1


@pytest.mark.parametrize("cnv", [False, True])
def test_par_y_identity_is_preserved_and_never_merged_with_base_gene(tmp_path, cnv):
    base = _gene(1)
    par = _gene(2, ensembl=f"{base.ensembl_gene_id}_PAR_Y")
    hgnc, axis = _reference(base, par), _axis(base, par)
    result = _read(
        tmp_path,
        _payload([_row(par, cnv=cnv, value="8"), _row(base, cnv=cnv, value="3")], cnv=cnv),
        hgnc,
        axis,
        cnv=cnv,
    )
    assert result.values.tolist() == [3.0, 8.0]
    assert result.receipt.par_y_gene_rows == 1
    assert result.receipt.versioned_gene_rows == 2
    absent = _read(tmp_path, _payload([_row(base, cnv=cnv)], cnv=cnv), hgnc, axis, cnv=cnv)
    assert absent.states.tolist() == [0, 1]


@pytest.mark.parametrize("cnv", [False, True])
@pytest.mark.parametrize("duplicate", ["exact", "version", "par_version"])
def test_duplicate_unrelated_gene_ids_reject_entire_source(tmp_path, cnv, duplicate):
    wanted, unrelated = _gene(1), _gene(2)
    if duplicate == "par_version":
        unrelated = replace(unrelated, ensembl_gene_id=f"{unrelated.ensembl_gene_id}_PAR_Y")
    first = _row(unrelated, cnv=cnv)
    second = first.copy()
    if duplicate != "exact":
        second[0] = second[0].replace(".7", ".8")
    with pytest.raises(assays.AssayFormatError, match="duplicate"):
        _read(
            tmp_path,
            _payload([_row(wanted, cnv=cnv), first, second], cnv=cnv),
            _reference(wanted, unrelated),
            _axis(wanted),
            cnv=cnv,
        )


@pytest.mark.parametrize("cnv", [False, True])
@pytest.mark.parametrize("mismatch", ["ensembl", "symbol", "entrez", "missing_hgnc"])
def test_axis_reference_mismatch_fails_before_source_access(tmp_path, monkeypatch, cnv, mismatch):
    identity = _gene(1)
    replacements = {
        "ensembl": replace(identity, ensembl_gene_id="ENSG00000000002"),
        "symbol": replace(identity, symbol="SYNTHETIC_DRIFT"),
        "entrez": replace(identity, entrez_id="2"),
        "missing_hgnc": _gene(2),
    }

    def forbidden_read(*_args, **_kwargs):
        pytest.fail("unmatched axis reached source access")

    monkeypatch.setattr(assays, "read_verified_source", forbidden_read)
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    with pytest.raises(assays.AssayFormatError, match="identities disagree") as error:
        reader(
            tmp_path / "PRIVATE-TAINTED-PATH",
            lock=_lock(b"synthetic"),
            hgnc=_reference(identity),
            axis=_axis(replacements[mismatch]),
        )
    assert "PRIVATE" not in str(error.value)
    assert replacements[mismatch].symbol not in str(error.value)


@pytest.mark.parametrize("cnv", [False, True])
@pytest.mark.parametrize("bad_argument", ["axis", "hgnc"])
def test_unadmitted_projection_arguments_are_rejected_safely(tmp_path, cnv, bad_argument):
    identity = _gene(1)
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    with pytest.raises(assays.AssayFormatError, match="admitted axis"):
        reader(
            tmp_path / "unopened",
            lock=_lock(b"synthetic"),
            hgnc=None if bad_argument == "hgnc" else _reference(identity),
            axis=None if bad_argument == "axis" else _axis(identity),
        )


@pytest.mark.parametrize("cnv", [False, True])
@pytest.mark.parametrize("component", ["bytes", "md5", "sha256"])
def test_exact_byte_identity_is_verified_before_any_table_decode(
    tmp_path, monkeypatch, cnv, component
):
    identity = _gene(1)
    payload = b"\xffPRIVATE-TAINTED-RECORD"
    changes = {"bytes": len(payload) + 1, "md5": "0" * 32, "sha256": "0" * 64}
    lock = replace(_lock(payload), **{component: changes[component]})

    def forbidden_decode(*_args, **_kwargs):
        pytest.fail("unverified bytes reached table decoding")

    monkeypatch.setattr(legacy, "_records", forbidden_decode)
    path = tmp_path / "synthetic-locked-source.tsv"
    path.write_bytes(payload)
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    with pytest.raises(SourceVerificationError) as error:
        reader(path, lock=lock, hgnc=_reference(identity), axis=_axis(identity))
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("cnv", [False, True])
def test_assay_byte_cap_is_enforced_before_file_open(tmp_path, cnv):
    identity = _gene(1)
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    with pytest.raises(SourceVerificationError):
        reader(
            tmp_path / "unopened",
            lock=SourceLock(legacy.MAX_ASSAY_BYTES + 1, "0" * 32, "0" * 64),
            hgnc=_reference(identity),
            axis=_axis(identity),
        )


@pytest.mark.parametrize(
    ("cnv", "field", "value"),
    [
        (False, 0, "PRIVATE-TAINTED-IDENTIFIER"),
        (False, 1, "PRIVATE TAINTED SYMBOL"),
        (False, 2, ""),
        (False, 3, "1.5"),
        (False, 6, "nan"),
        (False, 7, "-1"),
        (False, 8, ""),
        (True, 0, "PRIVATE-TAINTED-IDENTIFIER"),
        (True, 1, "PRIVATE TAINTED SYMBOL"),
        (True, 3, "-1"),
        (True, 4, "0"),
        (True, 5, "3.5"),
        (True, 6, ""),
        (True, 7, "nan"),
    ],
)
def test_malformed_unrelated_records_cannot_hide_outside_requested_axis(
    tmp_path, cnv, field, value
):
    wanted, unrelated = _gene(1), _gene(2)
    row = _row(unrelated, cnv=cnv)
    row[field] = value
    with pytest.raises(assays.AssayFormatError) as error:
        _read(
            tmp_path,
            _payload([_row(wanted, cnv=cnv), row], cnv=cnv),
            _reference(wanted, unrelated),
            _axis(wanted),
            cnv=cnv,
        )
    assert "PRIVATE" not in str(error.value)
    assert unrelated.symbol not in str(error.value)


@pytest.mark.parametrize("failure", ["missing", "duplicate", "normalized", "metadata", "count"])
def test_rna_summary_admission_remains_exact_without_fallback(tmp_path, failure):
    gene = _gene(1)
    summaries = _summaries()
    if failure == "missing":
        summaries.pop()
    elif failure == "duplicate":
        summaries.append(summaries[0].copy())
    elif failure == "normalized":
        summaries[0][8] = "0"
    elif failure == "metadata":
        summaries[0][2] = "PRIVATE-TAINTED"
    else:
        summaries[0][3] = "1.5"
    with pytest.raises(assays.AssayFormatError) as error:
        _read(tmp_path, _payload([_row(gene)], summaries=summaries), _reference(gene), _axis(gene))
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("cnv", [False, True])
def test_headers_width_controls_and_empty_gene_body_remain_fail_closed(tmp_path, cnv):
    gene = _gene(1)
    valid = _payload([_row(gene, cnv=cnv)], cnv=cnv)
    variants = [
        valid.replace(b"gene_id", b"gene_identifier", 1),
        valid.replace(gene.symbol.encode(), b"PRIVATE\x00TAINTED"),
        _payload([_row(gene, cnv=cnv)[:-1]], cnv=cnv),
        _payload([], cnv=cnv),
    ]
    if not cnv:
        variants.append(valid.replace(b"GENCODE v36", b"GENCODE v35"))
    for payload in variants:
        with pytest.raises(assays.AssayFormatError) as error:
            _read(tmp_path, payload, _reference(gene), _axis(gene), cnv=cnv)
        assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("cnv", [False, True])
def test_large_arbitrary_axis_decodes_once_and_validates_every_gene(tmp_path, monkeypatch, cnv):
    genes = tuple(_gene(index) for index in range(1, 1001))
    hgnc, axis = _reference(*genes), _axis(*genes)
    selected = (genes[0], genes[400], genes[999])
    payload = _payload([_row(gene, cnv=cnv) for gene in selected], cnv=cnv)
    original_records = legacy._records
    original_value = legacy._cnv_value if cnv else legacy._rna_value
    decoded, checked = [], []

    def records(*args, **kwargs):
        decoded.append(1)
        return original_records(*args, **kwargs)

    def value(row):
        checked.append(row[0])
        return original_value(row)

    monkeypatch.setattr(legacy, "_records", records)
    monkeypatch.setattr(legacy, "_cnv_value" if cnv else "_rna_value", value)
    result = _read(tmp_path, payload, hgnc, axis, cnv=cnv)
    assert len(decoded) == 1
    assert len(checked) == 3
    assert result.values.shape == result.states.shape == (1000,)
    assert result.receipt.state_counts == (3, 997, 0, 0, 0, 0)
    assert {axis.identities[index].hgnc_id for index in np.flatnonzero(result.states == 0)} == {
        gene.hgnc_id for gene in selected
    }


@pytest.mark.parametrize("cnv", [False, True])
def test_transient_projection_is_private_immutable_and_source_is_unchanged(tmp_path, cnv):
    gene = _gene(1, "PRIVATE_SYNTHETIC_SYMBOL")
    payload = _payload([_row(gene, cnv=cnv, value="73")], cnv=cnv)
    path = tmp_path / "synthetic-assay.tsv"
    path.write_bytes(payload)
    before = path.stat().st_mtime_ns
    reader = assays.parse_ascat_gene_cnv if cnv else assays.parse_star_counts_v36
    result = reader(path, lock=_lock(payload), hgnc=_reference(gene), axis=_axis(gene))
    assert "PRIVATE" not in repr(result)
    assert "values=" not in repr(result) and "states=" not in repr(result)
    assert not result.values.flags.writeable and not result.states.flags.writeable
    for array in (result.values, result.states):
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(result)
    receipt = json.dumps(asdict(result.receipt), allow_nan=False)
    assert "PRIVATE" not in receipt and "HGNC:" not in receipt and "ENSG" not in receipt
    assert "values" not in receipt and "73.0" not in receipt
    assert path.read_bytes() == payload
    assert path.stat().st_mtime_ns == before
    assert list(tmp_path.iterdir()) == [path]
