"""Synthetic arithmetic and adversarial admission checks, never real-data fixtures."""

from __future__ import annotations

import copy
import csv
import io
import json
import pickle
from dataclasses import FrozenInstanceError, asdict

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import protein
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    HgncReference,
    SourceVerificationError,
)

ALIASES = ("PRIVATE_SPECIMEN_B", "PRIVATE_SPECIMEN_A")


def _tsv(rows):
    stream = io.StringIO(newline="")
    csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)
    return stream.getvalue().encode()


@pytest.fixture
def fixture():
    identities = [
        GeneIdentity(f"HGNC:{index}", gene, str(index), None)
        for index, gene in enumerate(PANEL, start=1)
    ]
    extra = GeneIdentity("HGNC:100", "CURRENT_EXTRA", "100", None)
    reference = HgncReference(
        by_hgnc={identity.hgnc_id: identity for identity in (*identities, extra)},
        by_symbol={identity.symbol: identity for identity in (*identities, extra)},
        by_ensembl={},
    )
    shape = protein._ProteinShape(
        candidate_count=2,
        active_aliquots=3,
        withdrawn_aliquots=1,
        pool_targets=1,
        sample_map_plexes=1,
        biological_rows=17,
    )
    labels = (
        "PRIVATE_SPECIMEN_A",
        "PRIVATE_SPECIMEN_B",
        "PRIVATE_SPECIMEN_C",
        "Withdrawn:PRIVATE_W",
        "POOL",
    )
    header = ["Gene"]
    for label in labels:
        header.extend((f"{label} Log Ratio", f"{label} Unshared Log Ratio"))
    header.extend(protein._ANNOTATIONS)
    rows = [header, *[[name, *([""] * (len(header) - 1))] for name in protein._AGGREGATES]]
    for identity in (*identities, extra):
        if identity.symbol == "CDKN2B":
            continue
        symbol = "HISTORICAL_EXTRA" if identity == extra else identity.symbol
        row = [symbol, "9", "0", "8", "2", "7", "3", "WITHHELD", "WITHHELD", "POOL", "POOL"]
        row.extend((identity.entrez_id, identity.hgnc_id, "description", "Homo sapiens", "1", "1p"))
        if symbol == "EGFR":
            row[2] = ""  # Shared-peptide value nine must never fill this blank.
        rows.append(row)
    rows.append(
        [
            "UNAVAILABLE_EXTRA",
            "9",
            "0",
            "8",
            "2",
            "7",
            "3",
            "WITHHELD",
            "WITHHELD",
            "POOL",
            "POOL",
            "999",
            "",
            "description",
            "Homo sapiens",
            "1",
            "1p",
        ]
    )
    sample_rows = [
        list(protein._SAMPLE_HEADER),
        [".*", "plex", "POOL", *labels[:4], *("POOL",) * 6, "reagent", protein._RATIOS],
    ]
    return rows, sample_rows, reference, shape


def _decode(fixture, *, aliases=ALIASES):
    rows, sample_rows, reference, shape = fixture
    return protein._decode_protein_contents(
        _tsv(rows), _tsv(sample_rows), reference, aliases, shape=shape
    )


def _row(rows, symbol):
    return next(row for row in rows if row[0] == symbol)


def test_unshared_matrix_has_hand_derived_order_missingness_and_identity_oracles(fixture):
    decoded = _decode(fixture)
    assert decoded.values.shape == (17, 2)
    assert decoded.identities[-1] is None
    assert decoded.identities[-2].symbol == "CURRENT_EXTRA"
    assert np.array_equal(decoded.values[0], np.array([2.0, 0.0]))
    egfr = next(
        index
        for index, identity in enumerate(decoded.identities)
        if identity and identity.symbol == "EGFR"
    )
    assert decoded.values[egfr, 0] == 2.0
    assert np.isnan(decoded.values[egfr, 1])
    assert decoded.finite_unshared == 33
    assert decoded.missing_unshared == 1
    assert decoded.zero_unshared == 16
    assert decoded.finite_all_peptide == 34
    panel = {row.gene: row for row in decoded.panel_coverage}
    assert len(panel) == 16
    assert panel["CDKN2B"].source_rows == 0
    assert panel["CDKN2B"].unshared_finite is None
    assert panel["EGFR"].unshared_finite == 1 and panel["EGFR"].all_peptide_finite == 2


def test_candidate_order_reorders_only_columns_without_identity_or_loss_changes(fixture):
    forward = _decode(fixture)
    reverse = _decode(fixture, aliases=tuple(reversed(ALIASES)))
    assert forward.identities == reverse.identities
    assert np.array_equal(forward.values[:, ::-1], reverse.values, equal_nan=True)
    assert sha256_digest(ALIASES) != sha256_digest(tuple(reversed(ALIASES)))


@pytest.mark.parametrize(
    "value", ["nan", "NaN", "inf", "-inf", "1e999", "SECRET_BAD_VALUE", " ", "1" * 129]
)
@pytest.mark.parametrize("column", [1, 2, 5, 6])
def test_nonfinite_nonnumeric_or_oversized_fields_fail_without_echo(fixture, value, column):
    rows = fixture[0]
    _row(rows, "EGFR")[column] = value
    with pytest.raises(protein.ProteinAdmissionError) as raised:
        _decode(fixture)
    if value.strip():
        assert value not in str(raised.value)
    assert "PRIVATE_SPECIMEN" not in str(raised.value)


@pytest.mark.parametrize(
    "mutation",
    [
        "ragged",
        "duplicate_header",
        "misplaced_annotation",
        "unknown_measure",
        "missing_family",
        "unknown_aliquot",
        "duplicate_gene",
        "empty_gene",
        "organism",
        "extra_gene",
        "missing_gene",
        "aggregate_missing",
        "aggregate_duplicate",
    ],
)
def test_matrix_structure_fails_closed(fixture, mutation):  # noqa: C901, PLR0912
    rows = fixture[0]
    if mutation == "ragged":
        rows[-1].pop()
    elif mutation == "duplicate_header":
        rows[0][2] = rows[0][1]
    elif mutation == "misplaced_annotation":
        rows[0][-1], rows[0][-3] = rows[0][-3], rows[0][-1]
    elif mutation == "unknown_measure":
        rows[0][2] = "PRIVATE_SPECIMEN_A Other Ratio"
    elif mutation == "missing_family":
        rows[0][2] = "PRIVATE_SPECIMEN_AA Unshared Log Ratio"
    elif mutation == "unknown_aliquot":
        rows[0][2] = "PRIVATE_X Unshared Log Ratio"
    elif mutation == "duplicate_gene":
        rows[-1][0] = "EGFR"
    elif mutation == "empty_gene":
        rows[-1][0] = ""
    elif mutation == "organism":
        rows[-1][-3] = "Mus musculus"
    elif mutation == "extra_gene":
        rows.append(rows[-1][:])
    elif mutation == "missing_gene":
        rows.pop()
    elif mutation == "aggregate_missing":
        rows.pop(1)
    elif mutation == "aggregate_duplicate":
        rows.append(rows[1][:])
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture)


@pytest.mark.parametrize(
    "mutation",
    [
        "reference",
        "ratios",
        "duplicate_alias",
        "withdrawn_candidate",
        "candidate_absent",
        "missing_row",
        "duplicate_plex",
        "ragged",
        "header",
        "empty_cell",
    ],
)
def test_sample_map_and_nonreference_candidate_assignment_are_strict(fixture, mutation):  # noqa: C901
    sample_rows = fixture[1]
    if mutation == "reference":
        sample_rows[1][2] = "PRIVATE_SPECIMEN_A"
    elif mutation == "ratios":
        sample_rows[1][-1] = "127N/127C"
    elif mutation == "duplicate_alias":
        sample_rows[1][5] = sample_rows[1][3]
    elif mutation == "withdrawn_candidate":
        sample_rows[1][3] = "Withdrawn:PRIVATE_SPECIMEN_A"
    elif mutation == "candidate_absent":
        sample_rows[1][3] = "PRIVATE_OTHER"
    elif mutation == "missing_row":
        sample_rows.pop()
    elif mutation == "duplicate_plex":
        sample_rows.append(sample_rows[-1][:])
    elif mutation == "ragged":
        sample_rows[-1].pop()
    elif mutation == "header":
        sample_rows[0][0] = "OtherHeader"
    elif mutation == "empty_cell":
        sample_rows[1][3] = ""
    with pytest.raises(protein.ProteinAdmissionError) as raised:
        _decode(fixture)
    assert "PRIVATE_SPECIMEN" not in str(raised.value)


@pytest.mark.parametrize(
    "aliases",
    [
        (),
        ("PRIVATE_SPECIMEN_A",),
        ("PRIVATE_SPECIMEN_A", "PRIVATE_SPECIMEN_A"),
        ("POOL", "PRIVATE_SPECIMEN_A"),
        ("Withdrawn:PRIVATE_W", "PRIVATE_SPECIMEN_A"),
        ("", "PRIVATE_SPECIMEN_A"),
        ("X\tY", "PRIVATE_SPECIMEN_A"),
        ["PRIVATE_SPECIMEN_A", "PRIVATE_SPECIMEN_B"],
    ],
)
def test_candidate_contract_rejects_unusable_bindings(fixture, aliases):
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture, aliases=aliases)


@pytest.mark.parametrize(
    "mutation",
    [
        "entrez_conflict",
        "symbol_conflict",
        "duplicate_entrez",
        "noninteger_entrez",
        "panel_alias",
        "missing_panel",
        "CDKN2B_added",
    ],
)
def test_gene_identity_and_frozen_panel_cannot_be_silently_replaced(fixture, mutation):
    rows = fixture[0]
    egfr = _row(rows, "EGFR")
    if mutation == "entrez_conflict":
        egfr[-6] = "123456789"
    elif mutation == "symbol_conflict":
        egfr[-5] = _row(rows, "NF1")[-5]
        egfr[-6] = _row(rows, "NF1")[-6]
    elif mutation == "duplicate_entrez":
        rows[-1][-6] = egfr[-6]
    elif mutation == "noninteger_entrez":
        egfr[-6] = "0001"
    elif mutation == "panel_alias":
        egfr[0] = "OLD_EGFR"
    elif mutation == "missing_panel":
        egfr[-5] = ""
    elif mutation == "CDKN2B_added":
        identity = fixture[2].by_symbol["CDKN2B"]
        rows[-1][0] = identity.symbol
        rows[-1][-6], rows[-1][-5] = identity.entrez_id, identity.hgnc_id
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture)


def test_unknown_authority_retains_source_row_as_explicit_unavailable_identity(fixture):
    fixture[0][-1][-5] = "HGNC:999999"
    decoded = _decode(fixture)
    assert decoded.identities[-1] is None
    assert np.array_equal(decoded.values[-1], np.array([2.0, 0.0]))


def test_values_are_bytes_backed_immutable_and_result_exposes_only_safe_receipt(fixture):
    decoded = _decode(fixture)
    receipt = protein.ProteinAdmissionReceipt(
        profile_id=protein.PROFILE_ID,
        protein_sha256="0" * 64,
        sample_map_sha256="1" * 64,
        hgnc_sha256="2" * 64,
        candidate_digest=sha256_digest(ALIASES),
        candidate_count=2,
        biological_feature_rows=17,
        identified_feature_rows=16,
        unavailable_identity_rows=1,
        source_aggregate_rows_excluded=3,
        withdrawn_aliquots_excluded=1,
        pool_targets_excluded=1,
        finite_unshared_cells=33,
        missing_unshared_cells=1,
        finite_zero_unshared_cells=16,
        finite_all_peptide_cells=34,
        missing_all_peptide_cells=0,
        panel_coverage=decoded.panel_coverage,
        limitations=("Synthetic test only.",),
    )
    result = protein.ConfirmatoryProteinAdmission(
        sha256_digest(ALIASES), decoded.values, decoded.identities, receipt
    )
    with pytest.raises(ValueError):
        result.values[0, 0] = 999
    with pytest.raises(ValueError):
        result.values.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        result.candidate_digest = "changed"
    with pytest.raises(TypeError):
        pickle.dumps(result)
    with pytest.raises(TypeError):
        result.__getstate__()
    with pytest.raises(TypeError):
        pickle.dumps(decoded)
    with pytest.raises(TypeError):
        decoded.__getstate__()
    safe = json.dumps(asdict(result.receipt))
    assert all(alias not in safe and alias not in repr(result) for alias in ALIASES)
    assert "values" not in safe and "identities" not in safe
    assert not hasattr(result, "candidate_aliquots")


def test_public_parser_rejects_counterfeit_bytes_without_a_bypass(tmp_path, monkeypatch):
    source = tmp_path / "SECRET_SOURCE.tsv"
    source.write_bytes(b"counterfeit")

    def no_decode(*_args, **_kwargs):
        pytest.fail("counterfeit bytes must not reach the decoder")

    monkeypatch.setattr(protein, "_decode_protein_contents", no_decode)
    with pytest.raises(SourceVerificationError) as raised:
        protein.admit_confirmatory_protein(
            protein_path=source,
            sample_map_path=source,
            hgnc_path=source,
            candidate_aliquots=tuple(f"ALIAS_{index}" for index in range(56)),
        )
    assert "SECRET_SOURCE" not in str(raised.value)


def test_invalid_utf8_and_oversized_contents_fail_privately(fixture, monkeypatch):
    rows, sample_rows, reference, shape = fixture
    with pytest.raises(protein.ProteinAdmissionError):
        protein._decode_protein_contents(
            b"\xff", _tsv(sample_rows), reference, ALIASES, shape=shape
        )
    monkeypatch.setattr(protein, "PROTEIN_LOCK", protein.SourceLock(1, "0" * 32, "0" * 64))
    with pytest.raises(protein.ProteinAdmissionError):
        protein._decode_protein_contents(
            _tsv(rows), _tsv(sample_rows), reference, ALIASES, shape=shape
        )


def test_public_orchestration_binds_all_exact_sources_before_private_decode(fixture, monkeypatch):
    """A mocked verified-source boundary is not a real-data admission claim."""

    decoded = _decode(fixture)
    calls = []
    aliases = tuple(f"PRIVATE_ALIAS_{index}" for index in range(56))

    def verified(path, lock, *, max_bytes):
        calls.append((path, lock, max_bytes))
        return b"verified-protein" if lock == protein.PROTEIN_LOCK else b"verified-map"

    def reference(path):
        assert path == "HGNC"
        calls.append("locked-HGNC")
        return fixture[2]

    def decode(source, sample_map, hgnc, candidate_aliquots):
        assert source == b"verified-protein" and sample_map == b"verified-map"
        assert hgnc is fixture[2] and candidate_aliquots is aliases
        assert len(calls) == 3
        return decoded

    monkeypatch.setattr(protein, "read_verified_source", verified)
    monkeypatch.setattr(protein, "read_locked_hgnc", reference)
    monkeypatch.setattr(protein, "_decode_protein_contents", decode)
    result = protein.admit_confirmatory_protein(
        protein_path="PROTEIN",
        sample_map_path="MAP",
        hgnc_path="HGNC",
        candidate_aliquots=aliases,
    )
    assert calls[:2] == [
        ("PROTEIN", protein.PROTEIN_LOCK, protein.PROTEIN_LOCK.bytes),
        ("MAP", protein.SAMPLE_MAP_LOCK, protein.SAMPLE_MAP_LOCK.bytes),
    ]
    assert result.candidate_digest == sha256_digest(aliases)
    assert result.receipt.candidate_digest == result.candidate_digest
    assert result.receipt.protein_sha256 == protein.PROTEIN_LOCK.sha256
    assert result.receipt.sample_map_sha256 == protein.SAMPLE_MAP_LOCK.sha256
    assert result.receipt.hgnc_sha256 == protein.HGNC_LOCK.sha256
    assert result.receipt.unavailable_identity_rows == 1
    assert result.receipt.identified_feature_rows == 16
    assert result.values is decoded.values
    assert all(alias not in json.dumps(asdict(result.receipt)) for alias in aliases)


def test_alias_bound_and_illegal_csv_are_sanitized(fixture):
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture, aliases=("X" * 257, ALIASES[0]))
    with pytest.raises(protein.ProteinAdmissionError) as raised:
        protein._decode_protein_contents(
            b'"UNTERMINATED', _tsv(fixture[1]), fixture[2], ALIASES, shape=fixture[3]
        )
    assert "UNTERMINATED" not in str(raised.value)


def test_absent_panel_identity_cannot_hide_under_an_unavailable_source_symbol(fixture):
    fixture[0][-1][-6] = fixture[2].by_symbol["CDKN2B"].entrez_id
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture)


@pytest.mark.parametrize("gene", PANEL)
def test_every_panel_identity_fails_closed_if_hidden_in_an_unresolved_row(fixture, gene):
    """Exercise each identity axis before duplicates or final inventory can reject it."""
    source_rows, sample_rows, reference, shape = fixture
    target = reference.by_symbol[gene]
    for axis in ("symbol", "hgnc", "entrez"):
        rows = copy.deepcopy(source_rows)
        unresolved = rows.pop()
        # Put the unresolved row first so an existing target's duplicate NCBI
        # identifier cannot mask the general unresolved-panel check.
        rows.insert(4, unresolved)
        unresolved[-5] = "HGNC:999999"
        selected_reference = reference
        if axis == "symbol":
            unresolved[0] = target.symbol
        elif axis == "entrez":
            unresolved[-6] = target.entrez_id
        else:
            # An approved authority lacking a usable NCBI cross-reference is
            # unresolved even when the source has a numeric NCBI identifier.
            no_entrez = GeneIdentity(target.hgnc_id, target.symbol, None, None)
            selected_reference = HgncReference(
                by_hgnc={**reference.by_hgnc, target.hgnc_id: no_entrez},
                by_symbol={**reference.by_symbol, target.symbol: no_entrez},
                by_ensembl={},
            )
            unresolved[-5] = target.hgnc_id
        with pytest.raises(
            protein.ProteinAdmissionError, match="unresolved feature overlaps frozen-panel identity"
        ):
            protein._decode_protein_contents(
                _tsv(rows), _tsv(sample_rows), selected_reference, ALIASES, shape=shape
            )


def test_missing_approved_entrez_crossreference_remains_explicitly_unavailable(fixture):
    old = fixture[2]
    extra = GeneIdentity("HGNC:100", "CURRENT_EXTRA", None, None)
    by_hgnc = {**old.by_hgnc, extra.hgnc_id: extra}
    by_symbol = {**old.by_symbol, extra.symbol: extra}
    reference = HgncReference(by_hgnc, {}, by_symbol)
    rows, sample_rows, _, shape = fixture
    decoded = protein._decode_protein_contents(
        _tsv(rows), _tsv(sample_rows), reference, ALIASES, shape=shape
    )
    assert decoded.identities[-2:] == (None, None)
    assert decoded.values.shape == (17, 2)


def test_control_characters_never_enter_candidate_or_feature_names(fixture):
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture, aliases=("PRIVATE\x00ALIAS", ALIASES[0]))
    fixture[0][-1][0] = "UNAVAILABLE\x00EXTRA"
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(fixture)


def test_incomplete_hgnc_panel_reference_fails_with_a_sanitized_error(fixture):
    old = fixture[2]
    by_symbol = {key: value for key, value in old.by_symbol.items() if key != "CDKN2B"}
    reference = HgncReference(
        by_hgnc={identity.hgnc_id: identity for identity in by_symbol.values()},
        by_ensembl={},
        by_symbol=by_symbol,
    )
    with pytest.raises(protein.ProteinAdmissionError):
        protein._decode_protein_contents(
            _tsv(fixture[0]), _tsv(fixture[1]), reference, ALIASES, shape=fixture[3]
        )
