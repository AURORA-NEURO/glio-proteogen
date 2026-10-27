"""Synthetic source joins, source locks and resealed-coordinate attack oracles."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import pickle
from dataclasses import asdict, replace

import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    GeneIdentity,
    HgncReference,
    SourceVerificationError,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution import identity
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import digest
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service


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


def _synthetic_axis(monkeypatch):
    """Fake source coordinates require replacing the fixed production proof in tests."""
    names, lengths = identity._released_metadata()
    special = {"ALOX12-AS1", "IQCD", "MTRNR2L1", "MTRNR2L12", "MTRNR2L8"}
    renamed = set(names[:89])
    assert len(renamed) == 89 and not renamed.intersection(special)
    features, approved = [], []
    for index, (name, length) in enumerate(zip(names, lengths, strict=True)):
        coordinate = f"ENSG{90_000_000_000 + index:011d}"
        release = coordinate + ".4"
        hgnc_id = f"HGNC:{100_000 + index}"
        current_symbol, current_coordinate = name, coordinate
        category = "current_hgnc_coordinate_agreement"
        if name in renamed:
            category, current_symbol = "current_hgnc_rename_agreement", f"SYNTHETIC_RENAME_{index}"
        elif name == "IQCD":
            category, current_symbol = "historical_hgnc_name_link", "DRC10"
        elif name in {"MTRNR2L1", "MTRNR2L12", "MTRNR2L8"}:
            category, current_coordinate = "historical_coordinate_current_ensembl_unasserted", None
        elif name == "ALOX12-AS1":
            category = "historical_coordinate_current_nomenclature_conflict"
            hgnc_id, release = "HGNC:51342", "ENSG00000215067.10"
            coordinate, current_symbol, current_coordinate = "ENSG00000215067", None, None
        feature = identity.ModelInputFeature(
            name,
            length,
            release,
            coordinate,
            hgnc_id,
            "protein_coding",
            current_symbol,
            current_coordinate,
            category,
        )
        features.append(feature)
        if current_symbol is not None:
            approved.append(GeneIdentity(hgnc_id, current_symbol, None, current_coordinate))
    reference = _reference(*approved)
    proof = digest(tuple(asdict(item) for item in features))
    monkeypatch.setattr(identity, "EXPECTED_MAPPING_DIGEST", proof)
    monkeypatch.setattr(
        identity,
        "EXPECTED_HGNC_REFERENCE_DIGEST",
        identity.canonical_hgnc_reference_digest(reference),
    )
    receipt = identity.ModelAxisReceipt(
        feature_length_digest=digest(lengths),
        feature_mapping_digest=proof,
        canonical_hgnc_reference_digest=identity.EXPECTED_HGNC_REFERENCE_DIGEST,
    )
    return identity.ModelInputAxis(tuple(features), receipt), reference


@pytest.fixture(scope="module")
def synthetic():
    with pytest.MonkeyPatch.context() as patch:
        yield _synthetic_axis(patch)


def _gtf_row(gene_id, symbol, *, transcript=None, kind=None, extra=""):
    attrs = f'gene_id "{gene_id}"; gene_name "{symbol}"; gene_type "protein_coding";'
    if transcript is not None:
        attrs += f' transcript_id "{transcript}";'
    return "\t".join(
        [
            "chr1",
            "HAVANA",
            kind or ("transcript" if transcript else "gene"),
            "1",
            "10",
            ".",
            "+",
            ".",
            attrs + extra,
        ]
    )


def _gz(*lines):
    return gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)


def _small_gtf():
    return _gz(
        "##description: synthetic annotation",
        _gtf_row("ENSG00000000001.4", "SYNTHETIC_A"),
        _gtf_row("ENSG00000000001.4", "SYNTHETIC_A", transcript="ENST00000000001.4"),
        _gtf_row("ENSG00000000001.4", "SYNTHETIC_A", kind="exon"),
    )


def _complete_sources(axis):
    rows, metadata = [], []
    for index, feature in enumerate(axis.features):
        tid = f"ENST{90_000_000_000 + index:011d}.4"
        rows.extend(
            [
                _gtf_row(feature.release_gene_id, feature.source_symbol),
                _gtf_row(feature.release_gene_id, feature.source_symbol, transcript=tid),
            ]
        )
        metadata.append(f"{tid}\t{feature.source_symbol}\t{feature.release_hgnc_id}")
    # ALL metadata can contain a transcript on an alternate region absent in CHR.
    metadata.append(
        f"ENST88888888888.1\t{axis.features[0].source_symbol}\t{axis.features[0].release_hgnc_id}"
    )
    names, lengths = identity._released_metadata()
    author = (
        "feature_name,feature_length\n"
        + "".join(f"{name},{int(length)}\n" for name, length in zip(names, lengths, strict=True))
    ).encode()
    return {"author": author, "gtf": _gz(*rows), "metadata": _gz(*metadata)}


def test_fixed_official_locks_and_separate_coordinate_policy():
    assert identity.GTF_LOCK.bytes == 44_507_458
    assert (
        identity.GTF_LOCK.sha256
        == "81359865bab048361cbeaf91c9441aac4c700b63978e6691d579d78bf2322d30"
    )
    assert (
        identity.HGNC_METADATA_LOCK.sha256
        == "457690081684ad9908fca9533ecd0208caa918fdd4ee6563db1791fc1afe4841"
    )
    assert (
        identity.AUTHOR_FEATURE_LOCK.sha256
        == "2f81ea201380a13a0432b670228dbd356ed1c771a64a271e0eb83bd6e060db80"
    )
    assert "gencode-v36" in identity.COORDINATE_POLICY_ID


def test_complete_axis_preserves_author_order_lengths_and_all_source_coordinates(synthetic):
    axis, _ = synthetic
    names, lengths = identity._released_metadata()
    assert tuple(f.source_symbol for f in axis.features) == names
    assert tuple(f.source_length for f in axis.features) == lengths
    assert len({f.ensembl_gene_id for f in axis.features}) == 5829
    assert len({f.release_hgnc_id for f in axis.features}) == 5829
    assert axis.receipt.unresolved_source_coordinates == 0
    assert axis.receipt.current_ensembl_unasserted_features == 3
    assert axis.receipt.current_nomenclature_conflict_features == 1
    identity.validate_model_axis(axis)


def test_admission_revalidates_all_three_locked_sources_before_building_axis(
    synthetic, monkeypatch
):
    axis, reference = synthetic
    payloads = _complete_sources(axis)
    calls = []

    def read(path, lock, *, max_bytes):
        calls.append((path, lock, max_bytes))
        return payloads[path]

    monkeypatch.setattr(identity, "read_verified_source", read)
    admitted = identity.admit_model_axis(
        hgnc=reference,
        gencode_gtf_path="gtf",
        gencode_hgnc_path="metadata",
        author_feature_path="author",
    )
    assert admitted.features == axis.features and admitted.receipt == axis.receipt
    assert calls == [
        ("author", identity.AUTHOR_FEATURE_LOCK, identity.AUTHOR_FEATURE_LOCK.bytes),
        ("gtf", identity.GTF_LOCK, identity.GTF_LOCK.bytes),
        ("metadata", identity.HGNC_METADATA_LOCK, identity.HGNC_METADATA_LOCK.bytes),
    ]


def test_missing_or_wrong_reference_bytes_reject_without_echoing_paths(synthetic, tmp_path):
    _, reference = synthetic
    private = tmp_path / "PRIVATE_REFERENCE_PATH"
    private.write_bytes(b"synthetic")
    with pytest.raises(identity.ModelAxisError) as captured:
        identity.admit_model_axis(
            hgnc=reference,
            gencode_gtf_path=private,
            gencode_hgnc_path=private,
            author_feature_path=private,
        )
    assert "PRIVATE_REFERENCE_PATH" not in str(captured.value)


@pytest.mark.parametrize(
    "reference", [None, object(), _reference(GeneIdentity("HGNC:1", "X", None, None))]
)
def test_foreign_or_corrupted_hgnc_indexes_reject_before_reference_reads(monkeypatch, reference):
    monkeypatch.setattr(
        identity, "read_verified_source", lambda *_a, **_k: pytest.fail("reference I/O")
    )
    with pytest.raises(identity.ModelAxisError):
        identity.admit_model_axis(
            hgnc=reference, gencode_gtf_path="x", gencode_hgnc_path="x", author_feature_path="x"
        )


def test_gtf_and_all_metadata_join_only_consistent_present_chr_transcripts():
    genes, transcripts = identity._decode_gtf(_small_gtf(), ("SYNTHETIC_A",))
    metadata = _gz(
        "ENST00000000001.4\tSYNTHETIC_A\tHGNC:1",
        "ENST00000000009.1\tSYNTHETIC_A\tHGNC:1",
        "ENST00000000008.1\tSYNTHETIC_OFFMODEL\tHGNC:8",
    )
    assert identity._decode_hgnc_metadata(metadata, genes, transcripts) == {"SYNTHETIC_A": "HGNC:1"}


@pytest.mark.parametrize(
    "case",
    [
        "width",
        "gene_id",
        "name",
        "missing",
        "duplicate_gene",
        "duplicate_name",
        "duplicate_transcript",
        "transcript",
        "duplicate_attribute",
        "missing_attribute",
    ],
)
def test_gtf_coordinate_ambiguities_and_invalid_records_are_not_repaired(case):
    gene = _gtf_row("ENSG00000000001.4", "SYNTHETIC_A")
    tx = _gtf_row("ENSG00000000001.4", "SYNTHETIC_A", transcript="ENST00000000001.4")
    lines = [gene, tx]
    if case == "width":
        lines[0] = "x\ty"
    elif case == "gene_id":
        lines[0] = gene.replace("ENSG00000000001.4", "ENSG1")
    elif case == "name":
        lines[0] = gene.replace("SYNTHETIC_A", "with space")
    elif case == "missing":
        lines = [gene.replace("SYNTHETIC_A", "OTHER")]
    elif case == "duplicate_gene":
        lines.append(gene)
    elif case == "duplicate_name":
        lines.append(gene.replace("ENSG00000000001.4", "ENSG00000000002.1"))
    elif case == "duplicate_transcript":
        lines.append(tx)
    elif case == "transcript":
        lines[1] = tx.replace("ENST00000000001.4", "ENST1")
    elif case == "duplicate_attribute":
        lines[0] = gene + ' gene_id "ENSG00000000001.4";'
    else:
        lines[0] = gene.replace('gene_name "SYNTHETIC_A";', "")
    with pytest.raises(identity.ModelAxisError):
        identity._decode_gtf(_gz(*lines), ("SYNTHETIC_A",))


@pytest.mark.parametrize(
    "case",
    [
        "width",
        "transcript",
        "symbol",
        "hgnc",
        "duplicate",
        "ambiguous_hgnc",
        "wrong_coordinate",
        "no_join",
    ],
)
def test_hgnc_metadata_requires_one_stable_identity_and_exact_transcript_ancestry(case):
    genes, transcripts = identity._decode_gtf(_small_gtf(), ("SYNTHETIC_A",))
    row = "ENST00000000001.4\tSYNTHETIC_A\tHGNC:1"
    lines = [row]
    if case == "width":
        lines = ["x\ty"]
    elif case == "transcript":
        lines = [row.replace("ENST00000000001.4", "ENST1")]
    elif case == "symbol":
        lines = [row.replace("SYNTHETIC_A", "with space")]
    elif case == "hgnc":
        lines = [row.replace("HGNC:1", "HGNC:0")]
    elif case == "duplicate":
        lines.append(row)
    elif case == "ambiguous_hgnc":
        lines.append("ENST00000000009.1\tSYNTHETIC_A\tHGNC:2")
    elif case == "wrong_coordinate":
        transcripts["ENST00000000001.4"] = ("ENSG00000000002.1", "SYNTHETIC_A")
    else:
        lines = [row.replace("ENST00000000001.4", "ENST00000000009.1")]
    with pytest.raises(identity.ModelAxisError):
        identity._decode_hgnc_metadata(_gz(*lines), genes, transcripts)


@pytest.mark.parametrize("case", ["gzip", "truncated", "utf8", "expansion", "line", "lines"])
def test_compressed_reference_expansion_is_bounded_and_validated(monkeypatch, case):
    payload, bound = _gz("synthetic"), 100
    if case == "gzip":
        payload = b"not gzip"
    elif case == "truncated":
        payload = payload[:-4]
    elif case == "utf8":
        payload = gzip.compress(b"\xff\n", mtime=0)
    elif case == "expansion":
        bound = 2
    elif case == "line":
        monkeypatch.setattr(identity, "MAX_REFERENCE_LINE_BYTES", 2)
    else:
        monkeypatch.setattr(identity, "MAX_REFERENCE_LINES", 0)
    with pytest.raises(identity.ModelAxisError):
        tuple(identity._gzip_lines(payload, max_bytes=bound))


def test_original_author_table_has_exact_crlf_normalization_proof(synthetic):
    payload = _complete_sources(synthetic[0])["author"]
    assert hashlib.sha256(payload).hexdigest() == identity.AUTHOR_FEATURE_LOCK.sha256
    assert (
        "sha256:" + hashlib.sha256(payload.replace(b"\n", b"\r\n")).hexdigest()
        == catalog.EXPECTED_SOURCE_FEATURE_SHA256
    )
    identity._author_table(payload)
    for changed in (payload.replace(b"\n", b"\r\n"), payload.replace(b"AAAS", b"AAAA"), b""):
        with pytest.raises(identity.ModelAxisError):
            identity._author_table(changed)


@pytest.mark.parametrize("change", ["header", "width", "number", "order", "count", "decode"])
def test_author_table_structure_is_rechecked_after_source_lock_seam(synthetic, monkeypatch, change):
    payload = _complete_sources(synthetic[0])["author"]
    if change == "header":
        payload = payload.replace(b"feature_name", b"wrong_header")
    elif change == "width":
        payload = payload.replace(b"AAAS,4727", b"AAAS,4727,extra")
    elif change == "number":
        payload = payload.replace(b"AAAS,4727", b"AAAS,bad")
    elif change == "order":
        payload = payload.replace(b"AAAS,4727", b"OTHER,4727")
    elif change == "count":
        payload = payload.rsplit(b"\n", 2)[0] + b"\n"
    else:
        payload = b"\xff"
    monkeypatch.setattr(
        identity,
        "EXPECTED_SOURCE_FEATURE_SHA256",
        "sha256:" + hashlib.sha256(payload.replace(b"\n", b"\r\n")).hexdigest(),
    )
    with pytest.raises(identity.ModelAxisError):
        identity._author_table(payload)


@pytest.mark.parametrize(
    "change",
    [
        "order",
        "length",
        "coordinate",
        "category",
        "current",
        "duplicate_hgnc",
        "duplicate_coordinate",
    ],
)
def test_resealed_or_mutated_coordinate_mappings_cannot_replace_frozen_source_evidence(
    synthetic, change
):
    axis = synthetic[0]
    features = list(axis.features)
    if change == "order":
        features[0], features[1] = features[1], features[0]
    elif change == "length":
        features[0] = replace(features[0], source_length=features[0].source_length + 1)
    elif change == "coordinate":
        features[0] = replace(
            features[0], release_gene_id="ENSG77777777777.1", ensembl_gene_id="ENSG77777777777"
        )
    elif change == "category":
        features[0] = replace(features[0], evidence_category="current_hgnc_coordinate_agreement")
    elif change == "current":
        features[0] = replace(features[0], current_hgnc_symbol="SYNTHETIC_OTHER")
    elif change == "duplicate_hgnc":
        features[0] = replace(features[0], release_hgnc_id=features[1].release_hgnc_id)
    else:
        features[0] = replace(
            features[0],
            release_gene_id=features[1].release_gene_id,
            ensembl_gene_id=features[1].ensembl_gene_id,
        )
    with pytest.raises(identity.ModelAxisError):
        identity.ModelInputAxis(tuple(features), axis.receipt)
    values = axis.receipt.model_dump(mode="python")
    values["feature_mapping_digest"] = digest(tuple(asdict(item) for item in features))
    with pytest.raises(ValidationError):
        identity.ModelAxisReceipt.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_symbol": ""},
        {"source_symbol": "with space"},
        {"source_symbol": "X\x7f"},
        {"source_length": 1},
        {"source_length": -1.0},
        {"source_length": float("nan")},
        {"release_gene_id": "ENSG1"},
        {"ensembl_gene_id": "ENSG77777777777"},
        {"release_hgnc_id": "HGNC:0"},
        {"gene_type": ""},
        {"current_hgnc_symbol": "with space"},
        {"current_hgnc_ensembl_gene_id": "ENSG1"},
        {"evidence_category": "alias_guess"},
    ],
)
def test_feature_fields_reject_invented_or_malformed_identity_states(synthetic, changes):
    with pytest.raises(identity.ModelAxisError):
        replace(synthetic[0].features[0], **changes)


@pytest.mark.parametrize(
    "field",
    [
        "model_artifact_sha256",
        "model_content_digest",
        "feature_order_digest",
        "feature_length_digest",
        "feature_mapping_digest",
        "canonical_hgnc_reference_digest",
        "hgnc_source_sha256",
        "gencode_gtf_sha256",
        "gencode_hgnc_metadata_sha256",
        "author_feature_lf_sha256",
        "author_feature_crlf_sha256",
    ],
)
def test_receipt_cannot_reseal_a_different_model_or_reference_lock(synthetic, field):
    values = synthetic[0].receipt.model_dump(mode="python")
    values[field] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError):
        identity.ModelAxisReceipt.model_validate(values)


def test_axis_immutability_revalidation_and_implicit_export_guards(synthetic):
    axis = synthetic[0]
    for action in (
        lambda: pickle.dumps(axis),
        lambda: copy.deepcopy(axis),
        lambda: json.dumps(axis),
        lambda: asdict(axis),
        axis.__getstate__,
    ):
        with pytest.raises(TypeError):
            action()
    with pytest.raises(AttributeError):
        axis._features = ()
    assert "ENSG" not in repr(axis) and "sha256:" not in repr(axis)
    for features, receipt in (
        (list(axis.features), axis.receipt),
        (axis.features, {}),
        ((object(),), axis.receipt),
    ):
        with pytest.raises(identity.ModelAxisError):
            identity.ModelInputAxis(features, receipt)
    with pytest.raises(identity.ModelAxisError):
        identity.validate_model_axis(object())
    forged = object.__new__(identity.ModelInputAxis)
    object.__setattr__(forged, "_features", axis.features[:-1])
    object.__setattr__(forged, "_receipt", axis.receipt)
    with pytest.raises(identity.ModelAxisError):
        identity.validate_model_axis(forged)
    values = axis.receipt.model_dump(mode="python")
    values["model_artifact_sha256"] = "sha256:" + "0" * 64
    forged_receipt = identity.ModelAxisReceipt.model_construct(**values)
    with pytest.raises(identity.ModelAxisError):
        identity.ModelInputAxis(axis.features, forged_receipt)


@pytest.mark.parametrize(
    "case",
    ["exact", "rename", "IQCD", "MTRNR2L1", "MTRNR2L12", "MTRNR2L8", "ALOX12-AS1", "unsupported"],
)
def test_current_nomenclature_never_replaces_historical_source_coordinate(case):
    name, gid, hid = "SYNTHETIC_SOURCE", "ENSG00000000001.4", "HGNC:1"
    current_name, current_id = name, "ENSG00000000001"
    if case == "rename":
        current_name = "SYNTHETIC_CURRENT"
    elif case == "IQCD":
        name, current_name = "IQCD", "DRC10"
    elif case.startswith("MTRNR2L"):
        name, current_name, current_id = case, case, None
    elif case == "ALOX12-AS1":
        name, gid, hid = case, "ENSG00000215067.10", "HGNC:51342"
    elif case == "unsupported":
        current_id = "ENSG00000000002"
    reference = (
        _reference(GeneIdentity(hid, current_name, None, current_id))
        if case != "ALOX12-AS1"
        else _reference(GeneIdentity("HGNC:39523", "MIR497HG", None, "ENSG00000267532"))
    )
    gene = identity._ReleaseGene(name, gid, "lncRNA")
    if case == "unsupported":
        with pytest.raises(identity.ModelAxisError):
            identity._feature(name, 6473.0, gene, hid, reference)
    else:
        feature = identity._feature(name, 6473.0, gene, hid, reference)
        assert feature.source_symbol == name and feature.release_gene_id == gid
        if case == "ALOX12-AS1":
            assert (
                feature.current_hgnc_symbol is None and feature.ensembl_gene_id == "ENSG00000215067"
            )


def test_no_model_or_assay_execution_during_reference_admission(synthetic, monkeypatch):
    axis, reference = synthetic
    payloads = _complete_sources(axis)
    monkeypatch.setattr(identity, "read_verified_source", lambda path, *_a, **_k: payloads[path])

    def forbidden(*_args, **_kwargs):
        pytest.fail("model or preprocessing invoked")

    for module, name in (
        (catalog, "gbm_rna_purity_catalog"),
        (engine, "_input_vector"),
        (engine, "_forward"),
        (service, "analyze_gbm_rna_purity"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    assert (
        identity.admit_model_axis(
            hgnc=reference,
            gencode_gtf_path="gtf",
            gencode_hgnc_path="metadata",
            author_feature_path="author",
        ).receipt.model_executed
        is False
    )


def test_reader_failure_is_sanitized_at_admission_boundary(synthetic, monkeypatch):
    def failed(*_args, **_kwargs):
        raise SourceVerificationError("PRIVATE_REFERENCE_PATH")

    monkeypatch.setattr(identity, "read_verified_source", failed)
    with pytest.raises(identity.ModelAxisError) as captured:
        identity.admit_model_axis(
            hgnc=synthetic[1], gencode_gtf_path="x", gencode_hgnc_path="x", author_feature_path="x"
        )
    assert "PRIVATE_REFERENCE_PATH" not in str(captured.value)
