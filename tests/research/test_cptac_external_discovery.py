"""Discovery-specific source policies, using invented measurements and aliases."""

from __future__ import annotations

import copy
import csv
import inspect
import io
import json
import pickle
from dataclasses import FrozenInstanceError, asdict, replace

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import discovery, protein
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    PANEL,
    GeneIdentity,
    HgncReference,
    SourceVerificationError,
)


def _tsv(rows):
    stream = io.StringIO(newline="")
    csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(rows)
    return stream.getvalue().encode()


@pytest.fixture
def source():
    identities = tuple(
        GeneIdentity(f"HGNC:{i}", symbol, str(i), None) for i, symbol in enumerate(PANEL, start=1)
    )
    extra = GeneIdentity("HGNC:100", "CURRENT_EXTRA", "100", None)
    reference = HgncReference(
        {gene.hgnc_id: gene for gene in (*identities, extra)},
        {},
        {gene.symbol: gene for gene in (*identities, extra)},
    )
    labels = tuple(f"SYN{i:03d}" for i in range(110))
    candidates = tuple(reversed(labels[:72]))
    header = ["Gene"]
    for label in labels:
        header.extend((label + " Log Ratio", label + " Unshared Log Ratio"))
    header.extend(protein._ANNOTATIONS)
    rows = [header, *[[name, *([""] * (len(header) - 1))] for name in protein._AGGREGATES]]
    genes = [gene for gene in identities if gene.symbol not in {"CDKN2B", "MDM2"}]
    for gene in (*genes, extra, None):
        symbol = (
            "UNRESOLVED_EXTRA"
            if gene is None
            else "HISTORICAL_EXTRA"
            if gene == extra
            else gene.symbol
        )
        row = [symbol]
        for index in range(110):
            value = "0" if index == 0 else "2" if index == 1 else "3" if index < 72 else "54321.25"
            row.extend(("9", "" if symbol == "EGFR" and index == 0 else value))
        row.extend(
            (
                gene.entrez_id if gene else "999",
                gene.hgnc_id if gene else "",
                "description",
                "Homo sapiens",
                "1",
                "1p",
            )
        )
        rows.append(row)
    sample_rows = [list(protein._SAMPLE_HEADER)]
    sample_rows.extend(
        [
            ".*",
            f"synthetic_plex_{index}",
            "POOL",
            *labels[index * 10 : (index + 1) * 10],
            "reagent",
            protein._RATIOS,
        ]
        for index in range(11)
    )
    sample_rows.append([""] * 15)
    shape = replace(discovery._DISCOVERY_SHAPE, biological_rows=16)
    return rows, sample_rows, reference, candidates, shape


def _decode(source, *, candidates=None, shape=None):
    rows, sample_rows, reference, aliases, profile = source
    return discovery._decode_discovery_contents(
        _tsv(rows),
        _tsv(sample_rows),
        reference,
        aliases if candidates is None else candidates,
        shape=profile if shape is None else shape,
    )


def _row(source, symbol):
    return next(row for row in source[0] if row[0] == symbol)


def test_fixed_discovery_descriptor_and_locks_are_separate_from_confirmatory():
    descriptor = discovery.SOURCE_DESCRIPTOR
    assert descriptor.candidate_count == 72
    assert descriptor.analytical_plexes == descriptor.reference_channel_assignments_excluded == 11
    assert descriptor.nonreference_ratio_aliquots == 110
    assert descriptor.ratio_pool_targets == descriptor.withdrawn_ratio_aliquots == 0
    assert descriptor.trailing_blank_map_records == 1
    assert descriptor.biological_feature_rows == 10977
    assert descriptor.source_aggregate_rows_excluded == 3
    assert set(descriptor.expected_panel_features) == set(PANEL) - {"CDKN2B", "MDM2"}
    assert descriptor.selected_measure == "Unshared Log Ratio"
    assert discovery.PROTEIN_LOCK.bytes == 48440330
    assert discovery.PROTEIN_LOCK.md5 == "ed614fb12f72b9db9bc4667b6d349949"
    assert (
        discovery.PROTEIN_LOCK.sha256
        == "fc7c7b595211b81482db9281fb1592e58492eef87ab7db1fd64f7e4ec3bc96bd"
    )
    assert discovery.SAMPLE_MAP_LOCK.bytes == 3795
    assert discovery.SAMPLE_MAP_LOCK.md5 == "b1a598ad26a66015f339366e44799d6a"
    assert (
        discovery.SAMPLE_MAP_LOCK.sha256
        == "faea4574cd423c54b064c201391a9591160dc98ac3b6a443adaf8975914d74d1"
    )
    assert discovery.PROFILE_ID != protein.PROFILE_ID
    assert discovery.PROTEIN_LOCK != protein.PROTEIN_LOCK
    assert discovery.SAMPLE_MAP_LOCK != protein.SAMPLE_MAP_LOCK


def test_common_decoder_defaults_preserve_the_confirmatory_policy():
    shape = protein._ProteinShape()
    assert shape.candidate_count == 56
    assert shape.biological_rows == 11159
    assert shape.pool_targets == 1
    assert shape.trailing_blank_rows == 0
    assert shape.expected_panel_features == frozenset(PANEL) - {"CDKN2B"}
    assert shape.measurement_targets == 150


def test_discovery_source_selects_72_ordered_nonreference_targets_without_fallback(source):
    decoded = _decode(source)
    assert decoded.values.shape == (16, 72)
    assert decoded.values[0, 0] == 3
    assert decoded.values[0, -1] == 0
    assert 54321.25 not in decoded.values
    assert 9 not in decoded.values  # Separate all-peptide values are not selected.
    assert decoded.identities[-2].symbol == "CURRENT_EXTRA"
    assert decoded.identities[-1] is None
    egfr = next(
        index
        for index, identity in enumerate(decoded.identities)
        if identity and identity.symbol == "EGFR"
    )
    assert np.isnan(decoded.values[egfr, -1])
    assert decoded.finite_unshared == 1151
    assert decoded.missing_unshared == 1
    assert decoded.zero_unshared == 15
    assert decoded.finite_all_peptide == 1152
    assert decoded.missing_all_peptide == 0
    panel = {item.gene: item for item in decoded.panel_coverage}
    for gene in ("CDKN2B", "MDM2"):
        assert panel[gene].source_rows == 0
        assert panel[gene].unshared_finite is None
        assert panel[gene].unshared_missing is None
        assert panel[gene].all_peptide_finite is None
    assert panel["EGFR"].unshared_finite == 71
    assert panel["EGFR"].all_peptide_finite == 72


def test_column_order_is_exactly_the_passed_frozen_plan_order(source):
    forward = _decode(source)
    reverse = _decode(source, candidates=tuple(reversed(source[3])))
    assert np.array_equal(forward.values[:, ::-1], reverse.values, equal_nan=True)
    assert forward.identities == reverse.identities
    assert forward.panel_coverage == reverse.panel_coverage
    assert sha256_digest(source[3]) != sha256_digest(tuple(reversed(source[3])))


@pytest.mark.parametrize(
    "mutation", ["missing", "extra", "interior", "partial", "zero_width", "after_blank"]
)
def test_only_one_full_width_empty_trailing_record_is_admitted(source, mutation):
    rows = source[1]
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append([""] * 15)
    elif mutation == "interior":
        rows.insert(2, [""] * 15)
    elif mutation == "partial":
        rows[-1][-1] = "PRIVATE_TAINT"
    elif mutation == "zero_width":
        rows[-1] = []
    else:
        rows.append(rows[1][:])
    with pytest.raises(protein.ProteinAdmissionError) as error:
        _decode(source)
    assert "PRIVATE_TAINT" not in str(error.value)


def test_confirmatory_default_still_rejects_a_trailing_empty_record(source):
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(source, shape=replace(source[4], trailing_blank_rows=0))


@pytest.mark.parametrize(
    "mutation",
    [
        "reference",
        "duplicate_alias",
        "candidate_absent",
        "withdrawn",
        "duplicate_plex",
        "ratio_definition",
    ],
)
def test_nonreference_candidate_assignment_has_no_alias_or_role_repair(source, mutation):
    rows = source[1]
    if mutation == "reference":
        rows[1][2] = source[3][-1]
    elif mutation == "duplicate_alias":
        rows[1][4] = rows[1][3]
    elif mutation == "candidate_absent":
        rows[1][3] = "UNKNOWN_SYNTHETIC_TARGET"
    elif mutation == "withdrawn":
        rows[1][3] = "Withdrawn:" + rows[1][3]
    elif mutation == "duplicate_plex":
        rows[2][1] = rows[1][1]
    else:
        rows[1][-1] = "127N/127C"
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(source)


@pytest.mark.parametrize(
    "mutation",
    ["pool_target", "missing_unshared", "all_peptide_alias", "annotation_order", "ragged"],
)
def test_discovery_measurement_family_and_no_pool_target_are_strict(source, mutation):
    rows = source[0]
    if mutation == "pool_target":
        rows[0][1] = "POOL Log Ratio"
        rows[0][2] = "POOL Unshared Log Ratio"
    elif mutation == "missing_unshared":
        rows[0][2] = rows[0][1]
    elif mutation == "all_peptide_alias":
        rows[0][2] = "UNKNOWN_SYNTHETIC_TARGET Unshared Log Ratio"
    elif mutation == "annotation_order":
        rows[0][-1], rows[0][-2] = rows[0][-2], rows[0][-1]
    else:
        rows[-1].pop()
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(source)


@pytest.mark.parametrize("gene", ["CDKN2B", "MDM2"])
@pytest.mark.parametrize("identity_axis", ["symbol", "entrez", "authority"])
def test_unresolved_rows_cannot_hide_a_structurally_absent_panel_gene(source, gene, identity_axis):
    target = source[2].by_symbol[gene]
    row = source[0].pop()
    source[0].insert(4, row)
    row[-5] = "HGNC:99999"
    if identity_axis == "symbol":
        row[0] = gene
    elif identity_axis == "entrez":
        row[-6] = target.entrez_id
    else:
        row[-5] = target.hgnc_id
        old = source[2]
        unavailable = replace(target, entrez_id=None)
        reference = HgncReference(
            {**old.by_hgnc, target.hgnc_id: unavailable},
            {},
            {**old.by_symbol, target.symbol: unavailable},
        )
        source = (*source[:2], reference, *source[3:])
    with pytest.raises(protein.ProteinAdmissionError, match="unresolved feature"):
        _decode(source)


@pytest.mark.parametrize(
    "mutation", ["authority_entrez", "panel_alias", "duplicate_stable", "duplicate_feature"]
)
def test_stable_identity_is_crosschecked_without_alias_guessing(source, mutation):
    row = _row(source, "EGFR")
    if mutation == "authority_entrez":
        row[-6] = "9999"
    elif mutation == "panel_alias":
        row[0] = "UNAPPROVED_EGFR_ALIAS"
    elif mutation == "duplicate_stable":
        extra = _row(source, "HISTORICAL_EXTRA")
        extra[-6], extra[-5] = row[-6], row[-5]
    else:
        source[0][-1][0] = "EGFR"
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(source)


@pytest.mark.parametrize("column", [1, 2, 219, 220])
@pytest.mark.parametrize("value", ["NaN", "inf", "PRIVATE_BAD_VALUE"])
def test_both_measurement_families_include_nonselected_source_schema_checks(source, column, value):
    _row(source, "EGFR")[column] = value
    with pytest.raises(protein.ProteinAdmissionError) as error:
        _decode(source)
    assert value not in str(error.value)
    assert "SYNTHETIC_TARGET" not in str(error.value)


@pytest.mark.parametrize("count", [0, 56, 71, 73])
def test_public_source_requires72_before_opening_any_source(tmp_path, monkeypatch, count):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid source candidate inventory reached file reading")

    monkeypatch.setattr(discovery, "read_verified_source", forbidden)
    with pytest.raises(protein.ProteinAdmissionError):
        discovery.admit_discovery_protein(
            protein_path=tmp_path,
            sample_map_path=tmp_path,
            hgnc_path=tmp_path,
            candidate_aliquots=tuple(f"SYNTHETIC_{i}" for i in range(count)),
        )


@pytest.mark.parametrize(
    "mutation", ["list", "duplicate", "pool", "withdrawn", "empty", "whitespace", "control"]
)
def test_public_candidate_labels_are_exact_unique_nonreference_aliases(source, tmp_path, mutation):
    aliases = list(source[3])
    if mutation == "list":
        candidates = aliases
    else:
        aliases[0] = {
            "duplicate": aliases[1],
            "pool": "POOL",
            "withdrawn": "Withdrawn:PRIVATE",
            "empty": "",
            "whitespace": "PRIVATE ALIAS",
            "control": "PRIVATE\x00ALIAS",
        }[mutation]
        candidates = tuple(aliases)
    with pytest.raises(protein.ProteinAdmissionError) as error:
        discovery.admit_discovery_protein(
            protein_path=tmp_path,
            sample_map_path=tmp_path,
            hgnc_path=tmp_path,
            candidate_aliquots=candidates,
        )
    assert "PRIVATE" not in str(error.value)


def test_counterfeit_local_bytes_never_reach_hgnc_or_decoder(tmp_path, monkeypatch, source):
    path = tmp_path / "PRIVATE_SOURCE.tsv"
    path.write_bytes(b"counterfeit")

    def forbidden(*_args, **_kwargs):
        pytest.fail("unverified source bytes reached semantic decoding")

    monkeypatch.setattr(discovery, "read_locked_hgnc", forbidden)
    monkeypatch.setattr(discovery, "_decode_discovery_contents", forbidden)
    with pytest.raises(SourceVerificationError) as error:
        discovery.admit_discovery_protein(
            protein_path=path,
            sample_map_path=path,
            hgnc_path=path,
            candidate_aliquots=source[3],
        )
    assert "PRIVATE_SOURCE" not in str(error.value)


def _admit_at_verified_boundary(source, monkeypatch):
    """Isolate wrapper orchestration, not a claim that synthetic bytes are real."""
    decoded = _decode(source)
    calls = []

    def verified(path, lock, *, max_bytes):
        calls.append((path, lock, max_bytes))
        return b"verified-protein" if lock == discovery.PROTEIN_LOCK else b"verified-map"

    def reference(path):
        assert path == "HGNC"
        calls.append("locked-HGNC")
        return source[2]

    def decoder(matrix, sample_map, hgnc, candidates):
        assert calls == [
            ("PROTEIN", discovery.PROTEIN_LOCK, discovery.PROTEIN_LOCK.bytes),
            ("MAP", discovery.SAMPLE_MAP_LOCK, discovery.SAMPLE_MAP_LOCK.bytes),
            "locked-HGNC",
        ]
        assert matrix == b"verified-protein" and sample_map == b"verified-map"
        assert hgnc is source[2] and candidates is source[3]
        return decoded

    monkeypatch.setattr(discovery, "read_verified_source", verified)
    monkeypatch.setattr(discovery, "read_locked_hgnc", reference)
    monkeypatch.setattr(discovery, "_decode_discovery_contents", decoder)
    result = discovery.admit_discovery_protein(
        protein_path="PROTEIN",
        sample_map_path="MAP",
        hgnc_path="HGNC",
        candidate_aliquots=source[3],
    )
    return result, decoded


def test_fixed_locks_and_order_digest_bind_public_orchestration(source, monkeypatch):
    result, decoded = _admit_at_verified_boundary(source, monkeypatch)
    assert result.candidate_digest == result.receipt.candidate_digest == sha256_digest(source[3])
    assert result.receipt.profile_id == discovery.PROFILE_ID
    assert result.receipt.candidate_count == 72
    assert result.receipt.protein_sha256 == discovery.PROTEIN_LOCK.sha256
    assert result.receipt.sample_map_sha256 == discovery.SAMPLE_MAP_LOCK.sha256
    assert result.receipt.hgnc_sha256 == discovery.HGNC_LOCK.sha256
    assert result.receipt.pool_targets_excluded == result.receipt.withdrawn_aliquots_excluded == 0
    assert result.receipt.identified_feature_rows == 15
    assert result.receipt.unavailable_identity_rows == 1
    assert result.values is decoded.values
    assert result.identities is decoded.identities
    assert result.source_descriptor is discovery.SOURCE_DESCRIPTOR
    assert tuple(inspect.signature(discovery.admit_discovery_protein).parameters) == (
        "protein_path",
        "sample_map_path",
        "hgnc_path",
        "candidate_aliquots",
    )


def test_transient_values_cannot_be_mutated_pickled_or_leaked_by_repr(source, monkeypatch):
    result, decoded = _admit_at_verified_boundary(source, monkeypatch)
    with pytest.raises(ValueError):
        result.values[0, 0] = 7
    with pytest.raises(ValueError):
        result.values.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        result.candidate_digest = "changed"
    for value in (result, decoded):
        with pytest.raises(TypeError):
            pickle.dumps(value)
        with pytest.raises(TypeError):
            value.__getstate__()
    encoded = json.dumps(asdict(result.receipt), allow_nan=False)
    assert not any(alias in encoded or alias in repr(result) for alias in source[3])
    assert "values=" not in repr(result) and "identities=" not in repr(result)
    assert "54321.25" not in encoded
    assert "values" not in asdict(result.receipt)
    assert not hasattr(result, "candidate_aliquots")


@pytest.mark.parametrize("source_lock", ["PROTEIN_LOCK", "SAMPLE_MAP_LOCK"])
def test_private_decoder_enforces_the_discovery_byte_caps(source, monkeypatch, source_lock):
    monkeypatch.setattr(discovery, source_lock, discovery.SourceLock(1, "0" * 32, "0" * 64))
    with pytest.raises(protein.ProteinAdmissionError):
        _decode(source)


def test_profile_override_is_private_and_the_public_function_has_no_bypass(source, tmp_path):
    with pytest.raises(TypeError):
        discovery.admit_discovery_protein(
            protein_path=tmp_path,
            sample_map_path=tmp_path,
            hgnc_path=tmp_path,
            candidate_aliquots=source[3],
            shape=source[4],
        )


def test_decoder_does_not_change_source_rows_or_map(source):
    before = copy.deepcopy(source[:2])
    _decode(source)
    assert source[:2] == before
