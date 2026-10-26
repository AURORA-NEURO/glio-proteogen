"""Synthetic byte, filesystem, and identity oracles for exact source admission."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from glio_proteogen.research.cptac_gbm_external_admission import contracts, identity, source
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    MAX_SOURCE_BYTES,
    PANEL,
    GeneIdentity,
    HgncReference,
    IdentityResolutionError,
    SourceLock,
    SourceVerificationError,
)

_HEADER = "hgnc_id\tsymbol\tstatus\tentrez_id\tensembl_gene_id\talias_symbol\n"


def _lock(payload: bytes) -> SourceLock:
    return SourceLock(
        bytes=len(payload),
        md5=hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _reference(*rows: str) -> HgncReference:
    return identity._decode_hgnc((_HEADER + "\n".join(rows) + "\n").encode())


def _metadata(original, **changes):
    fields = {
        name: getattr(original, name)
        for name in (
            "st_mode",
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    }
    if hasattr(original, "st_birthtime_ns"):
        fields["st_birthtime_ns"] = original.st_birthtime_ns
    fields.update(changes)
    return SimpleNamespace(**fields)


class _ReadObserver:
    def __init__(self, stream, callback=None):
        self.stream = stream
        self.callback = callback
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stream.close()

    def fileno(self):
        return self.stream.fileno()

    def read(self, count):
        self.requests.append(count)
        payload = self.stream.read(count)
        if self.callback is not None:
            self.callback()
        return payload


def test_read_hashes_and_returns_one_bounded_opened_snapshot(tmp_path, monkeypatch):
    payload = b"synthetic exact bytes\x00\xff\n"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)
    original_fdopen = source.os.fdopen
    observers = []

    def opened(descriptor, mode):
        observer = _ReadObserver(original_fdopen(descriptor, mode))
        observers.append(observer)
        return observer

    monkeypatch.setattr(source.os, "fdopen", opened)
    admitted = source.read_verified_source(path, _lock(payload), max_bytes=len(payload))
    assert admitted == payload
    assert isinstance(admitted, bytes)
    assert len(observers) == 1
    assert observers[0].requests == [len(payload) + 1]
    assert observers[0].stream.closed


@pytest.mark.parametrize("field", ["md5", "sha256"])
def test_each_hash_is_required_even_when_size_and_other_hash_match(tmp_path, field):
    payload = b"synthetic hash binding"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)
    altered = replace(_lock(payload), **{field: "0" * (32 if field == "md5" else 64)})
    with pytest.raises(SourceVerificationError, match="checksums"):
        source.read_verified_source(path, altered, max_bytes=len(payload))


@pytest.mark.parametrize("delta", [-1, 1])
def test_size_mismatch_is_rejected_before_open(tmp_path, monkeypatch, delta):
    payload = b"byte count oracle"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)

    def forbidden_open(*_args, **_kwargs):
        pytest.fail("a source with the wrong byte count must not be opened")

    monkeypatch.setattr(source.os, "open", forbidden_open)
    with pytest.raises(SourceVerificationError, match="byte count"):
        source.read_verified_source(
            path, replace(_lock(payload), bytes=len(payload) + delta), max_bytes=128
        )


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1", MAX_SOURCE_BYTES + 1])
def test_source_lock_rejects_non_integer_or_unbounded_lengths(value):
    with pytest.raises(SourceVerificationError, match="byte count"):
        SourceLock(value, "a" * 32, "b" * 64)


@pytest.mark.parametrize(
    ("md5", "sha256"),
    [
        ("a" * 31, "b" * 64),
        ("a" * 33, "b" * 64),
        ("A" * 32, "b" * 64),
        ("g" * 32, "b" * 64),
        (None, "b" * 64),
        ("a" * 32, "b" * 63),
        ("a" * 32, "b" * 65),
        ("a" * 32, "B" * 64),
        ("a" * 32, "sha256:" + "b" * 64),
        ("a" * 32, None),
    ],
)
def test_source_lock_rejects_noncanonical_checksums(md5, sha256):
    with pytest.raises(SourceVerificationError, match="checksums"):
        SourceLock(1, md5, sha256)


def test_source_lock_accepts_exact_bound_and_is_frozen():
    lock = SourceLock(MAX_SOURCE_BYTES, "a" * 32, "b" * 64)
    with pytest.raises(FrozenInstanceError):
        lock.bytes = 1


@pytest.mark.parametrize("bound", [True, 0, -1, 1.0, MAX_SOURCE_BYTES + 1])
def test_read_bound_validation_precedes_filesystem_access(bound):
    with pytest.raises(SourceVerificationError, match="bound"):
        source.read_verified_source("unobserved-private-source", _lock(b"x"), max_bytes=bound)


def test_lock_larger_than_callers_bound_or_wrong_contract_is_rejected():
    with pytest.raises(SourceVerificationError, match="bound"):
        source.read_verified_source("not-opened", _lock(b"xx"), max_bytes=1)
    with pytest.raises(SourceVerificationError, match="bound"):
        source.read_verified_source("not-opened", object(), max_bytes=1)


def test_missing_and_directory_errors_are_sanitized(tmp_path):
    sensitive_path = tmp_path / "private-source-name-do-not-echo"
    with pytest.raises(SourceVerificationError) as caught:
        source.read_verified_source(sensitive_path, _lock(b"x"), max_bytes=1)
    assert sensitive_path.name not in str(caught.value)
    assert str(tmp_path) not in str(caught.value)
    assert caught.value.__suppress_context__
    with pytest.raises(SourceVerificationError, match="regular non-link"):
        source.read_verified_source(tmp_path, _lock(b"x"), max_bytes=1)


def test_leaf_symlink_is_rejected_without_reading_target(tmp_path):
    path = tmp_path / "source.bin"
    path.write_bytes(b"x")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("host does not grant synthetic symlink creation")
    with pytest.raises(SourceVerificationError, match="regular non-link"):
        source.read_verified_source(link, _lock(b"x"), max_bytes=1)


def test_windows_regular_reparse_point_metadata_is_rejected():
    metadata = SimpleNamespace(
        st_mode=stat.S_IFREG,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )
    with pytest.raises(SourceVerificationError, match="regular non-link"):
        source._regular_snapshot(metadata)


def test_path_swap_between_lstat_and_open_is_rejected_and_descriptor_closed(tmp_path, monkeypatch):
    payload = b"same bytes do not authorize replacing a path binding"
    original_path = tmp_path / "original.bin"
    replacement_path = tmp_path / "replacement.bin"
    original_path.write_bytes(payload)
    replacement_path.write_bytes(payload)
    original_open = source.os.open
    descriptors = []

    def swapped_open(_path, flags):
        descriptor = original_open(replacement_path, flags)
        descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(source.os, "open", swapped_open)
    with pytest.raises(SourceVerificationError, match="binding changed"):
        source.read_verified_source(original_path, _lock(payload), max_bytes=len(payload))
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])


def test_descriptor_change_during_single_read_is_rejected(tmp_path, monkeypatch):
    payload = b"read-time metadata change"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)
    original_fdopen = source.os.fdopen
    original_metadata = path.stat()

    def changed():
        os.utime(
            path, ns=(original_metadata.st_atime_ns, original_metadata.st_mtime_ns + 1_000_000)
        )

    monkeypatch.setattr(
        source.os,
        "fdopen",
        lambda descriptor, mode: _ReadObserver(original_fdopen(descriptor, mode), changed),
    )
    with pytest.raises(SourceVerificationError, match="binding changed"):
        source.read_verified_source(path, _lock(payload), max_bytes=len(payload))


def test_path_rebinding_after_read_is_rejected_even_if_descriptor_is_stable(tmp_path, monkeypatch):
    payload = b"post-read binding check"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)
    original_lstat = Path.lstat
    calls = 0

    def rebound(self):
        nonlocal calls
        observed = original_lstat(self)
        calls += 1
        return observed if calls == 1 else _metadata(observed, st_ino=observed.st_ino + 1)

    monkeypatch.setattr(Path, "lstat", rebound)
    with pytest.raises(SourceVerificationError, match="binding changed"):
        source.read_verified_source(path, _lock(payload), max_bytes=len(payload))
    assert calls == 2


@pytest.mark.parametrize("returned", [b"", b"x", b"x" * 9])
def test_short_or_overlong_read_is_not_accepted_as_verified_bytes(tmp_path, monkeypatch, returned):
    payload = b"exact"
    path = tmp_path / "fixture.bin"
    path.write_bytes(payload)
    original_fdopen = source.os.fdopen

    class ChangedRead(_ReadObserver):
        def read(self, _count):
            return returned

    monkeypatch.setattr(
        source.os, "fdopen", lambda descriptor, mode: ChangedRead(original_fdopen(descriptor, mode))
    )
    with pytest.raises(SourceVerificationError, match="byte count"):
        source.read_verified_source(path, _lock(payload), max_bytes=len(payload))


def test_approved_exact_indexes_preserve_ambiguity_missingness_and_ignore_aliases():
    reference = _reference(
        "HGNC:20\tFIXTUREB\tApproved\t102\tENSG00000000001\tOLD_ALIAS",
        "HGNC:10\tFIXTUREA\tApproved\t\tENSG00000000001\tOTHER_ALIAS",
        "HGNC:30\tFIXTUREC\tApproved\t\t\t",
        "HGNC:40\tWITHDRAWN\tEntry Withdrawn\t104\tENSG00000000004\t",
    )
    assert set(reference.by_symbol) == {"FIXTUREA", "FIXTUREB", "FIXTUREC"}
    assert "OLD_ALIAS" not in reference.by_symbol
    assert "OTHER_ALIAS" not in reference.by_symbol
    assert tuple(g.hgnc_id for g in reference.by_ensembl["ENSG00000000001"]) == (
        "HGNC:10",
        "HGNC:20",
    )
    assert reference.by_hgnc["HGNC:10"].entrez_id is None
    assert reference.by_hgnc["HGNC:30"].ensembl_gene_id is None
    assert len(reference.by_ensembl) == 1


def test_reference_copies_inputs_and_all_indexes_are_read_only():
    gene = GeneIdentity("HGNC:1", "FIXTURE", None, "ENSG00000000001")
    by_hgnc = {gene.hgnc_id: gene}
    by_symbol = {gene.symbol: gene}
    group = [gene]
    reference = HgncReference(by_hgnc, {gene.ensembl_gene_id: group}, by_symbol)
    by_hgnc.clear()
    by_symbol.clear()
    group.clear()
    assert reference.by_hgnc[gene.hgnc_id] == gene
    assert reference.by_ensembl[gene.ensembl_gene_id] == (gene,)
    for mapping in (reference.by_hgnc, reference.by_symbol, reference.by_ensembl):
        with pytest.raises(TypeError):
            mapping["new"] = gene
    with pytest.raises(FrozenInstanceError):
        gene.symbol = "OTHER"
    with pytest.raises(FrozenInstanceError):
        reference.by_hgnc = {}


@pytest.mark.parametrize(
    "row",
    [
        "HGNC:1\tOTHER\tApproved\t2\tENSG00000000002\t",
        "HGNC:2\tFIXTURE\tApproved\t2\tENSG00000000002\t",
    ],
)
def test_duplicate_approved_hgnc_id_or_symbol_fails_closed(row):
    with pytest.raises(IdentityResolutionError, match="not unique"):
        _reference("HGNC:1\tFIXTURE\tApproved\t1\tENSG00000000001\t", row)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\xff",
        b"symbol\tstatus\nFIXTURE\tApproved\n",
        (_HEADER.replace("alias_symbol", "symbol") + "\n").encode(),
        (_HEADER + "HGNC:1\tFIXTURE\tApproved\t1\tENSG00000000001\textra\textra\n").encode(),
        (_HEADER + "HGNC:1\tFIXTURE\tApproved\t1\n").encode(),
        (_HEADER + '"unterminated\n').encode(),
        (_HEADER + "HGNC:1\tFIXTURE\tEntry Withdrawn\t1\tENSG00000000001\t\n").encode(),
        (_HEADER + "HGNC:1\tFIXTURE\tapproved\t1\tENSG00000000001\t\n").encode(),
    ],
)
def test_hgnc_format_errors_and_empty_approved_sets_are_sanitized(payload):
    with pytest.raises(IdentityResolutionError) as caught:
        identity._decode_hgnc(payload)
    assert "HGNC:1" not in str(caught.value)
    assert "FIXTURE" not in str(caught.value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ENSG00000000001", "ENSG00000000001"),
        ("ENSG00000000001.12", "ENSG00000000001"),
        ("ENSG00000000001_PAR_Y", "ENSG00000000001_PAR_Y"),
        ("ENSG00000000001.12_PAR_Y", "ENSG00000000001_PAR_Y"),
    ],
)
def test_numeric_version_stripping_preserves_par_y_identity(raw, expected):
    assert identity.normalize_ensembl_gene_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "ENSG00000000001.0",
        "ENSG00000000001.01",
        "ENSG00000000001.1x",
        "ENSG00000000001_PAR_Y.1",
        "ENSG00000000001.1_PAR_X",
        "ENSG00000000001.extra",
        " ENSG00000000001",
        "ENSG00000000001\n",
        "ENSG0000000001",
        "ENSG000000000001",
        "ENST00000000001",
        None,
    ],
)
def test_ensembl_normalization_does_not_guess_malformed_or_transcript_ids(raw):
    with pytest.raises(IdentityResolutionError, match="format"):
        identity.normalize_ensembl_gene_id(raw)


def test_par_y_and_base_gene_remain_separate_reference_keys():
    reference = _reference(
        "HGNC:1\tFIXTUREA\tApproved\t1\tENSG00000000001.12\t",
        "HGNC:2\tFIXTUREB\tApproved\t2\tENSG00000000001.12_PAR_Y\t",
    )
    assert len(reference.by_ensembl) == 2
    assert reference.by_ensembl["ENSG00000000001"][0].hgnc_id == "HGNC:1"
    assert reference.by_ensembl["ENSG00000000001_PAR_Y"][0].hgnc_id == "HGNC:2"


@pytest.mark.parametrize(
    "changed",
    [
        {"hgnc_id": "1"},
        {"hgnc_id": None},
        {"symbol": ""},
        {"symbol": "HAS SPACE"},
        {"symbol": "x" * 129},
        {"symbol": None},
        {"entrez_id": ""},
        {"entrez_id": 1},
        {"ensembl_gene_id": "ENSG00000000001.12"},
        {"ensembl_gene_id": 1},
    ],
)
def test_gene_identity_validates_present_ids_without_inventing_missing_ids(changed):
    values = {
        "hgnc_id": "HGNC:1",
        "symbol": "FIXTURE",
        "entrez_id": None,
        "ensembl_gene_id": None,
    }
    values.update(changed)
    with pytest.raises(IdentityResolutionError, match="invalid"):
        GeneIdentity(**values)


@pytest.mark.parametrize(
    "corruption",
    [
        "hgnc_key",
        "symbol_key",
        "missing_symbol",
        "missing_ensembl",
        "wrong_ensembl",
        "duplicate_ensembl",
    ],
)
def test_manually_constructed_reference_cannot_present_inconsistent_indexes(corruption):
    gene = GeneIdentity("HGNC:1", "FIXTURE", "1", "ENSG00000000001")
    by_hgnc = {gene.hgnc_id: gene}
    by_symbol = {gene.symbol: gene}
    by_ensembl = {gene.ensembl_gene_id: (gene,)}
    if corruption == "hgnc_key":
        by_hgnc = {"HGNC:2": gene}
    elif corruption == "symbol_key":
        by_symbol = {"OTHER": gene}
    elif corruption == "missing_symbol":
        by_symbol = {}
    elif corruption == "missing_ensembl":
        by_ensembl = {}
    elif corruption == "wrong_ensembl":
        by_ensembl = {"ENSG00000000002": (gene,)}
    elif corruption == "duplicate_ensembl":
        by_ensembl = {gene.ensembl_gene_id: (gene, gene)}
    with pytest.raises(IdentityResolutionError, match="inconsistent"):
        HgncReference(by_hgnc, by_ensembl, by_symbol)


def test_public_hgnc_reader_has_no_caller_lock_or_unverified_decoder_path(tmp_path, monkeypatch):
    observed = []
    payload = (_HEADER + "HGNC:1\tFIXTURE\tApproved\t\t\t\n").encode()

    def verified(path, lock, *, max_bytes):
        observed.append((path, lock, max_bytes))
        return payload

    monkeypatch.setattr(identity, "read_verified_source", verified)
    path = tmp_path / "unopened.tsv"
    reference = identity.read_locked_hgnc(path)
    assert len(reference.by_hgnc) == 1
    assert observed == [(path, identity.HGNC_LOCK, identity.HGNC_LOCK.bytes)]
    assert identity.HGNC_LOCK.bytes == 16_948_224
    assert (
        identity.HGNC_LOCK.sha256
        == "854162118530e929f06249f3349465dd5fe0515fcccf0347f463e833609c1270"
    )
    assert identity.HGNC_LOCK.md5 == "acc6344dd46eb2942627a16e0d735fb8"


def test_small_unlocked_hgnc_file_is_rejected_by_public_reader(tmp_path):
    path = tmp_path / "fixture.tsv"
    path.write_text(_HEADER + "HGNC:1\tFIXTURE\tApproved\t\t\t\n", encoding="utf-8")
    with pytest.raises(SourceVerificationError, match="byte count"):
        identity.read_locked_hgnc(path)


def test_panel_is_fixed_sorted_distinct_and_shared_across_modules():
    assert isinstance(PANEL, tuple)
    assert tuple(sorted(set(PANEL))) == PANEL
    assert len(PANEL) == 16
    assert PANEL == (
        "CDK4",
        "CDKN2A",
        "CDKN2B",
        "EGFR",
        "IDH1",
        "MDM2",
        "MDM4",
        "NF1",
        "PDGFRA",
        "PIK3CA",
        "PIK3R1",
        "PLCG1",
        "PTEN",
        "PTPN11",
        "RB1",
        "TP53",
    )
    assert identity.PANEL is contracts.PANEL
