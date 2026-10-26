"""Synthetic exact legacy hydration, source sealing and tamper-boundary oracles."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import asdict, replace
from types import SimpleNamespace

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission.contracts import GeneIdentity
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    PROFILE_ID as LEGACY_PROFILE_ID,
)
from glio_proteogen.research.cptac_gbm_external_admission.transfer import (
    SourceFitReceipt,
    fit_source_gene,
)
from glio_proteogen.research.cptac_gbm_source_fit_census import storage as engine
from glio_proteogen.research.cptac_gbm_source_fit_census.contracts import (
    INPUT_DOMAIN_REJECTION,
    MANIFEST_NAME,
    PROFILE_ID,
    CensusError,
    SourceCensusReceipt,
    SourceGeneReceipt,
    SourceReceiptPage,
    manifest_bytes,
    page_bytes,
)
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import (
    nested_selection as nested,
)

_DIGEST = "sha256:" + "1" * 64
_OTHER = "sha256:" + "2" * 64
_CANARY = "synthetic-private-canary"


@pytest.fixture(scope="module")
def original_receipts():
    rng = np.random.default_rng(37)
    n = 80
    cnv = rng.integers(0, 6, n).astype(np.float64)
    rna = np.exp(rng.normal(0, 0.5, n))
    protein = 0.9 * rna + 0.3 * cnv + rng.normal(0, 0.2, n)
    folds = np.tile(np.arange(5, dtype=np.int8), n // 5)
    accepted = fit_source_gene(cnv, rna, protein, folds).receipt
    assert accepted.accepted
    empty = fit_source_gene(cnv, rna, np.full(n, np.nan), folds).receipt
    partial_protein = protein.copy()
    partial_protein[np.flatnonzero(folds == 0)[1:]] = np.nan
    partial = fit_source_gene(cnv, rna, partial_protein, folds).receipt
    assert not partial.accepted and partial.nested_point_summary is not None
    real_fit = nested._fit_candidate

    def fail_final(candidate, *args, outer_fold, inner_fold):
        if outer_fold == -1 and candidate == "full":
            return nested.CandidateFit(
                candidate, None, None, "candidate is numerically unidentified"
            )
        return real_fit(candidate, *args, outer_fold=outer_fold, inner_fold=inner_fold)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(nested, "_fit_candidate", fail_final)
        final_failed = fit_source_gene(cnv, rna, protein, folds).receipt
    assert not final_failed.accepted and final_failed.selected_candidate is not None
    assert len(final_failed.final_fits) == 4
    return {"accepted": accepted, "empty": empty, "partial": partial, "final_failed": final_failed}


def _records(original_receipts, count=3):
    result = []
    for index in range(count):
        identity = GeneIdentity(
            f"HGNC:{100_000 + index}", f"SYNTHETIC{index}", str(index + 1), f"ENSG{index + 1:011}"
        )
        if index % 3 == 2:
            result.append(SourceGeneReceipt(identity, None, INPUT_DOMAIN_REJECTION))
        else:
            result.append(
                SourceGeneReceipt(
                    identity, original_receipts["accepted" if index % 3 == 0 else "partial"], None
                )
            )
    return tuple(result)


def _page(records, axis_digest, number=0):
    return SourceReceiptPage(
        PROFILE_ID, _DIGEST, axis_digest, _DIGEST, _DIGEST, _DIGEST, number, records
    )


def _store(tmp_path, original_receipts, *, count=3, page_size=2, axis_digest=None):
    records = _records(original_receipts, count)
    digest = axis_digest or sha256_digest(tuple(asdict(record.identity) for record in records))
    store = engine.JsonCensusReceiptStore(tmp_path / "source")
    bindings = tuple(
        store.write_page(_page(records[offset : offset + page_size], digest, number))
        for number, offset in enumerate(range(0, count, page_size))
    )
    manifest = SourceCensusReceipt(
        profile_id=PROFILE_ID,
        request_digest=_DIGEST,
        feature_axis_digest=digest,
        candidate_digest=_DIGEST,
        source_catalog_digest=_DIGEST,
        source_fold_assignment_digest=_DIGEST,
        total_genes=count,
        accepted_genes=sum(
            record.source is not None and record.source.accepted for record in records
        ),
        abstained_genes=sum(
            record.source is not None and not record.source.accepted for record in records
        ),
        input_domain_rejected_genes=sum(record.source is None for record in records),
        page_size=page_size,
        pages=bindings,
        gene_record_digests=tuple(record.digest for record in records),
    )
    return store, records, manifest


@pytest.mark.parametrize("kind", ["accepted", "empty", "partial", "final_failed"])
def test_hydrates_exact_original_aggregate_dataclass_graph(original_receipts, kind):
    original = original_receipts[kind]
    document = engine.source_fit_receipt_document(original)
    hydrated = engine.hydrate_source_fit_receipt(document)
    assert type(hydrated) is SourceFitReceipt
    assert hydrated == original
    assert hydrated.profile_id == LEGACY_PROFILE_ID
    assert type(hydrated.fold_trace) is tuple
    assert tuple(trace.fold for trace in hydrated.fold_trace) == (0, 1, 2, 3, 4)
    assert type(hydrated.selection_evidence) is tuple
    assert type(hydrated.fold_trace[0].candidates) is tuple
    assert not hasattr(hydrated, "_predictors")
    for forbidden in ("beta", "center", "scale", "predictions", "observed", "case_id"):
        assert forbidden not in document
    assert json.loads(canonical_json_bytes(asdict(original))) == document


def test_failed_partial_and_refit_receipts_keep_diagnostics(original_receipts):
    partial = engine.hydrate_source_fit_receipt(
        engine.source_fit_receipt_document(original_receipts["partial"])
    )
    assert partial.nested_point_summary is not None
    assert partial.common_oof_count > 0
    assert any(
        0 < item.source_oof_count < partial.complete_count for item in partial.selection_evidence
    )
    failed = engine.hydrate_source_fit_receipt(
        engine.source_fit_receipt_document(original_receipts["final_failed"])
    )
    assert failed.selected_candidate is not None
    assert failed.nested_point_summary is not None
    assert failed.final_fits[-1].available is False
    assert failed.final_fits[-1].failure_reason == "candidate is numerically unidentified"


@pytest.mark.parametrize(("page_size", "count"), [(1, 3), (2, 3), (32, 65), (64, 65)])
def test_complete_source_store_seals_and_reopens_read_only(
    tmp_path, original_receipts, page_size, count
):
    store, records, manifest = _store(tmp_path, original_receipts, count=count, page_size=page_size)
    binding = store.seal(manifest)
    assert store.read_manifest(binding) == manifest
    assert engine.decode_manifest(manifest_bytes(manifest)) == manifest
    assert (store.directory / MANIFEST_NAME).read_bytes() == manifest_bytes(manifest)
    expected_sha = "sha256:" + hashlib.sha256(manifest_bytes(manifest)).hexdigest()
    assert binding.sha256 == expected_sha
    assert binding.manifest_digest == manifest.digest
    reopened = engine.JsonCensusReceiptStore.open_existing(store.directory, binding)
    flattened = []
    for number, page_binding in enumerate(manifest.pages):
        assert page_binding.file_name == f"pages/{number:05d}.json"
        page = reopened.read_page(page_binding)
        assert engine.decode_page(page_bytes(page)) == page
        assert page_binding.sha256 == "sha256:" + hashlib.sha256(page_bytes(page)).hexdigest()
        flattened.extend(page.genes)
    assert tuple(flattened) == records
    assert all(
        type(item.source) is SourceFitReceipt for item in flattened if item.source is not None
    )
    with pytest.raises(CensusError, match="unsealed"):
        reopened.write_page(_page(records[:1], manifest.feature_axis_digest, len(manifest.pages)))
    with pytest.raises(CensusError, match="already sealed"):
        reopened.seal(manifest)


def test_null_reference_crosslinks_are_not_invented(original_receipts):
    record = SourceGeneReceipt(
        GeneIdentity("HGNC:1", "PARTIAL", None, None), original_receipts["empty"], None
    )
    digest = sha256_digest((asdict(record.identity),))
    page = _page((record,), digest)
    assert engine.decode_page(page_bytes(page)).genes[0].identity == record.identity


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("accepted", 1),
        ("complete_count", True),
        ("complete_count", -1),
        ("complete_count", 10_001),
        ("common_oof_count", 81),
        ("valid_outer_folds", 6),
        ("selected_candidate", _CANARY),
        ("failure_reason", _CANARY),
        ("profile_id", PROFILE_ID),
        ("final_fit_iterations", [None, 1, 2, 241]),
        ("fold_trace", []),
        ("selection_evidence", []),
        ("final_fits", []),
    ],
)
def test_rejects_wrong_old_receipt_types_counts_candidates_and_private_text(
    original_receipts, field, value
):
    document = engine.source_fit_receipt_document(original_receipts["accepted"])
    document[field] = value
    with pytest.raises(CensusError) as error:
        engine.hydrate_source_fit_receipt(document)
    assert _CANARY not in str(error.value)


@pytest.mark.parametrize(
    "defect",
    [
        "extra",
        "missing",
        "not_object",
        "array_coefficient",
        "int_mae",
        "infinite_mae",
        "negative_rmse",
        "candidate_order",
        "fold_order",
        "inner_private_reason",
        "inner_eligible_without_mae",
        "inner_nonboolean",
        "fit_private_reason",
        "fit_iterations",
        "selection_basis",
        "fallback_reason",
        "trace_false_availability",
        "summary_count",
        "summary_denominator",
        "summary_selection_counts",
        "summary_metric_candidate",
        "summary_private_key",
        "evidence_ineligible_mae",
        "common_count",
        "training_count",
        "comparison_flag",
        "final_iteration_mismatch",
    ],
)
def test_recursive_closed_schema_rejects_tampering(original_receipts, defect):  # noqa: C901, PLR0912, PLR0915 - explicit nested receipt attack matrix.
    document = engine.source_fit_receipt_document(original_receipts["accepted"])
    if defect == "extra":
        document[_CANARY] = 1
    elif defect == "missing":
        del document["final_fits"]
    elif defect == "not_object":
        document = []
    elif defect == "array_coefficient":
        document["fold_trace"][0]["beta"] = [1.0] * 72
    elif defect == "int_mae":
        document["selection_evidence"][0]["source_oof_mae"] = 0
    elif defect == "infinite_mae":
        document["selection_evidence"][0]["source_oof_mae"] = float("inf")
    elif defect == "negative_rmse":
        document["nested_point_summary"]["fixed"][0]["rmse"] = -1.0
    elif defect == "candidate_order":
        document["selection_evidence"].reverse()
    elif defect == "fold_order":
        document["fold_trace"].reverse()
    elif defect == "inner_private_reason":
        document["fold_trace"][0]["candidates"][0]["failure_reasons"] = [_CANARY]
    elif defect == "inner_eligible_without_mae":
        document["fold_trace"][0]["candidates"][0]["inner_mae"] = None
    elif defect == "inner_nonboolean":
        document["fold_trace"][0]["candidates"][0]["eligible"] = 1
    elif defect == "fit_private_reason":
        document["final_fits"][0]["failure_reason"] = _CANARY
    elif defect == "fit_iterations":
        document["final_fits"][0]["iterations"] = 1
    elif defect == "selection_basis":
        document["fold_trace"][0]["selection_basis"] = _CANARY
    elif defect == "fallback_reason":
        document["fold_trace"][0]["fallback_reason"] = _CANARY
    elif defect == "trace_false_availability":
        document["fold_trace"][0]["selected_prediction_available"] = False
    elif defect == "summary_count":
        document["nested_point_summary"]["fixed"][0]["observed_count"] -= 1
    elif defect == "summary_denominator":
        document["nested_point_summary"]["selection_decision_denominator"] = 4
    elif defect == "summary_selection_counts":
        document["nested_point_summary"]["selection_counts"][0]["comparison_observations"] += 1
    elif defect == "summary_metric_candidate":
        document["nested_point_summary"]["selected"]["candidate"] = "full"
    elif defect == "summary_private_key":
        document["nested_point_summary"]["selected"]["predictions"] = [1.0] * 80
    elif defect == "evidence_ineligible_mae":
        document["selection_evidence"][0]["eligible"] = False
    elif defect == "common_count":
        document["common_oof_count"] -= 1
    elif defect == "training_count":
        document["fold_trace"][0]["training_complete"] -= 1
    elif defect == "comparison_flag":
        document["fold_trace"][0]["comparison_accepted"] = False
    else:
        document["final_fit_iterations"][-1] = None
    with pytest.raises(CensusError) as error:
        engine.hydrate_source_fit_receipt(document)
    assert _CANARY not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"[]",
        b"null",
        b"\xff",
        b'{"page_digest":NaN}',
        b'{"page_digest":Infinity}',
        b'{"page_digest":1e999}',
        b'{"x":1,"x":1}',
        b'{"x":1}\n',
    ],
)
def test_rejects_noncanonical_malformed_or_nonfinite_json(payload):
    with pytest.raises(CensusError):
        engine.decode_page(payload)


@pytest.mark.parametrize(
    "defect",
    [
        "extra",
        "digest",
        "genes",
        "gene_extra",
        "identity",
        "identity_long",
        "crosslink",
        "domain_private",
        "domain_both",
        "nonboolean_page",
        "context",
    ],
)
def test_page_codec_rejects_rehashed_invalid_payloads(original_receipts, defect):  # noqa: C901 - explicit page schema attack matrix.
    records = _records(original_receipts)
    page = _page(records, sha256_digest(tuple(asdict(item.identity) for item in records)))
    document = json.loads(page_bytes(page))
    if defect == "extra":
        document[_CANARY] = 1
    elif defect == "digest":
        document["page_digest"] = _OTHER
    elif defect == "genes":
        document["genes"] = []
    elif defect == "gene_extra":
        document["genes"][0]["predictions"] = [1.0] * 72
    elif defect == "identity":
        document["genes"][0]["identity"]["hgnc_id"] = _CANARY
    elif defect == "identity_long":
        document["genes"][0]["identity"]["symbol"] = "x" * 129
    elif defect == "crosslink":
        document["genes"][0]["identity"]["entrez_id"] = 1
    elif defect == "domain_private":
        document["genes"][-1]["input_domain_rejection"] = _CANARY
    elif defect == "domain_both":
        document["genes"][0]["input_domain_rejection"] = INPUT_DOMAIN_REJECTION
    elif defect == "nonboolean_page":
        document["page_number"] = False
    else:
        document["request_digest"] = True
    if defect != "digest":
        document["page_digest"] = sha256_digest(
            {key: value for key, value in document.items() if key != "page_digest"}
        )
    with pytest.raises(CensusError) as error:
        engine.decode_page(canonical_json_bytes(document))
    assert _CANARY not in str(error.value)


@pytest.mark.parametrize(
    "field",
    [
        "profile_id",
        "request_digest",
        "feature_axis_digest",
        "candidate_digest",
        "source_catalog_digest",
        "source_fold_assignment_digest",
    ],
)
def test_store_rejects_foreign_source_page_context(tmp_path, original_receipts, field):
    store, records, manifest = _store(tmp_path, original_receipts, count=1, page_size=1)
    record = replace(records[0], identity=GeneIdentity("HGNC:200000", "OTHER", None, None))
    page = _page((record,), manifest.feature_axis_digest, 1)
    if field == "profile_id":
        with pytest.raises(CensusError):
            replace(page, profile_id=_CANARY)
    else:
        with pytest.raises(CensusError, match="context"):
            store.write_page(replace(page, **{field: _OTHER}))
    assert not (store.directory / MANIFEST_NAME).exists()
    assert len(tuple((store.directory / "pages").iterdir())) == 1


def test_page_order_and_file_collisions_never_overwrite(tmp_path, original_receipts):
    store, records, manifest = _store(tmp_path, original_receipts, count=1, page_size=1)
    payload = (store.directory / manifest.pages[0].file_name).read_bytes()
    with pytest.raises(CensusError, match="contiguous"):
        store.write_page(_page(records, manifest.feature_axis_digest, 0))
    with pytest.raises(CensusError, match="repeat or reorder"):
        store.write_page(_page(records, manifest.feature_axis_digest, 1))
    assert (store.directory / manifest.pages[0].file_name).read_bytes() == payload
    with pytest.raises(CensusError, match="fresh"):
        engine.JsonCensusReceiptStore(store.directory)
    next_record = replace(records[0], identity=GeneIdentity("HGNC:200000", "OTHER", None, None))
    collision = store.directory / "pages/00001.json"
    collision.write_bytes(b"pre-existing sentinel")
    with pytest.raises(CensusError, match="exclusively"):
        store.write_page(_page((next_record,), manifest.feature_axis_digest, 1))
    assert collision.read_bytes() == b"pre-existing sentinel"


@pytest.mark.parametrize(
    "defect", ["axis", "counts", "record_order", "foreign_binding", "duplicate_symbol"]
)
def test_manifest_cannot_seal_incomplete_or_false_source_inventory(
    tmp_path, original_receipts, defect
):
    if defect == "axis":
        store, _, manifest = _store(tmp_path, original_receipts, axis_digest=_OTHER)
    else:
        store, records, manifest = _store(tmp_path, original_receipts)
        if defect == "counts":
            manifest = replace(manifest, accepted_genes=2, abstained_genes=0)
        elif defect == "record_order":
            manifest = replace(
                manifest, gene_record_digests=tuple(reversed(manifest.gene_record_digests))
            )
        elif defect == "foreign_binding":
            manifest = replace(
                manifest, pages=(replace(manifest.pages[0], sha256=_OTHER), manifest.pages[1])
            )
        else:
            # Same HGNC cardinality, conflicting approved-symbol inventory.
            page_path = store.directory / manifest.pages[-1].file_name
            assert page_path.exists()
            other_store = engine.JsonCensusReceiptStore(tmp_path / "other-source")
            altered = (
                records[0],
                replace(
                    records[1],
                    identity=replace(records[1].identity, symbol=records[0].identity.symbol),
                ),
                records[2],
            )
            axis = sha256_digest(tuple(asdict(item.identity) for item in altered))
            bindings = (
                other_store.write_page(_page(altered[:2], axis)),
                other_store.write_page(_page(altered[2:], axis, 1)),
            )
            manifest = replace(
                manifest,
                feature_axis_digest=axis,
                pages=bindings,
                gene_record_digests=tuple(item.digest for item in altered),
            )
            store = other_store
    with pytest.raises(CensusError, match="manifest"):
        store.seal(manifest)
    assert not (store.directory / MANIFEST_NAME).exists()


@pytest.mark.parametrize(
    "defect", ["page_bytes", "manifest_bytes", "missing_page", "missing_manifest"]
)
def test_locked_aggregate_files_reject_tamper_or_absence(tmp_path, original_receipts, defect):
    store, _, manifest = _store(tmp_path, original_receipts)
    sealed = store.seal(manifest)
    path = store.directory / (manifest.pages[0].file_name if "page" in defect else MANIFEST_NAME)
    if defect.startswith("missing"):
        path.unlink()
    else:
        payload = path.read_bytes()
        path.write_bytes(payload[:-1] + (b"x" if payload[-1:] != b"x" else b"y"))
    if "page" in defect:
        with pytest.raises(CensusError):
            store.read_page(manifest.pages[0])
    else:
        with pytest.raises(CensusError):
            engine.JsonCensusReceiptStore.open_existing(store.directory, sealed)


def test_same_bytes_replaced_file_is_rejected_during_open(monkeypatch, tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    binding = manifest.pages[0]
    target = store.directory / binding.file_name
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(target.read_bytes())
    original_open = engine.os.open
    swapped = False

    def swap(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and path == target:
            swapped = True
            replacement.replace(target)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(engine.os, "open", swap)
    with pytest.raises(CensusError):
        store.read_page(binding)
    assert swapped


def test_source_directory_replacement_is_detected(monkeypatch, tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    original = engine._directory

    def replaced(path):
        identity = original(path)
        return (identity[0], identity[1] + 1) if path == store.directory else identity

    monkeypatch.setattr(engine, "_directory", replaced)
    with pytest.raises(CensusError):
        store.read_page(manifest.pages[0])


def test_link_or_reparse_file_metadata_is_rejected(monkeypatch, tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    target = store.directory / manifest.pages[0].file_name
    real_lstat = type(target).lstat

    def link_metadata(path, *args, **kwargs):
        metadata = real_lstat(path, *args, **kwargs)
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK)
        return metadata

    monkeypatch.setattr(type(target), "lstat", link_metadata)
    with pytest.raises(CensusError, match="non-link"):
        store.read_page(manifest.pages[0])


def test_encoded_receipt_and_page_byte_bounds_are_inclusive(monkeypatch, original_receipts):
    source = original_receipts["accepted"]
    encoded = canonical_json_bytes(asdict(source))
    monkeypatch.setattr(engine, "MAX_RECEIPT_BYTES", len(encoded))
    assert engine.source_fit_receipt_document(source)
    monkeypatch.setattr(engine, "MAX_RECEIPT_BYTES", len(encoded) - 1)
    with pytest.raises(CensusError):
        engine.source_fit_receipt_document(source)
    records = _records(original_receipts)
    page = _page(records, sha256_digest(tuple(asdict(item.identity) for item in records)))
    encoded_page = page_bytes(page)
    monkeypatch.setattr(engine, "MAX_PAGE_BYTES", len(encoded_page))
    assert engine.decode_page(encoded_page) == page
    monkeypatch.setattr(engine, "MAX_PAGE_BYTES", len(encoded_page) - 1)
    with pytest.raises(CensusError):
        engine.decode_page(encoded_page)


def test_source_phase_budget_accounts_for_manifest_bytes(monkeypatch, tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    total = sum(binding.bytes for binding in manifest.pages) + len(manifest_bytes(manifest))
    monkeypatch.setattr(engine, "MAX_SOURCE_BYTES", total - 1)
    with pytest.raises(CensusError, match="bounded source phase"):
        store.seal(manifest)
    assert not (store.directory / MANIFEST_NAME).exists()
    monkeypatch.setattr(engine, "MAX_SOURCE_BYTES", total)
    assert store.seal(manifest)


def test_page_budget_failure_retains_incomplete_directory(monkeypatch, tmp_path, original_receipts):
    records = _records(original_receipts)
    page = _page(records, sha256_digest(tuple(asdict(item.identity) for item in records)))
    store = engine.JsonCensusReceiptStore(tmp_path / "incomplete")
    monkeypatch.setattr(engine, "MAX_SOURCE_BYTES", len(page_bytes(page)) - 1)
    with pytest.raises(CensusError, match="bounded source phase"):
        store.write_page(page)
    assert store.directory.is_dir()
    assert not (store.directory / MANIFEST_NAME).exists()
    assert not tuple((store.directory / "pages").iterdir())


@pytest.mark.parametrize(
    "defect",
    ["extra", "missing", "path", "bool", "digest", "records", "pages", "context", "complete"],
)
def test_manifest_codec_rejects_rehashed_schema_and_path_attacks(
    tmp_path, original_receipts, defect
):
    _, _, manifest = _store(tmp_path, original_receipts)
    document = json.loads(manifest_bytes(manifest))
    if defect == "extra":
        document["case_ids"] = [_CANARY] * 72
    elif defect == "missing":
        del document["complete"]
    elif defect == "path":
        document["pages"][0]["file_name"] = "../" + _CANARY
    elif defect == "bool":
        document["accepted_genes"] = True
    elif defect == "digest":
        document["manifest_digest"] = _OTHER
    elif defect == "records":
        document["gene_record_digests"] = []
    elif defect == "pages":
        document["pages"] = []
    elif defect == "context":
        document["request_digest"] = _CANARY
    else:
        document["complete"] = False
    if defect != "digest":
        document["manifest_digest"] = sha256_digest(
            {key: value for key, value in document.items() if key != "manifest_digest"}
        )
    with pytest.raises(CensusError) as error:
        engine.decode_manifest(canonical_json_bytes(document))
    assert _CANARY not in str(error.value)


@pytest.mark.parametrize("defect", ["foreign_type", "mutable_tuple", "opaque_nested_object"])
def test_encoder_rejects_nonlegacy_or_malformed_runtime_objects(original_receipts, defect):
    receipt = original_receipts["accepted"]
    if defect == "foreign_type":
        receipt = asdict(receipt)
    elif defect == "mutable_tuple":
        receipt = replace(receipt, selection_evidence=list(receipt.selection_evidence))
    else:
        receipt = replace(receipt, nested_point_summary=object())
    with pytest.raises(CensusError) as error:
        engine.source_fit_receipt_document(receipt)
    assert _CANARY not in str(error.value)


def test_large_negative_r_squared_and_nonconverged_refit_are_preserved(original_receipts):
    receipt = original_receipts["final_failed"]
    summary = receipt.nested_point_summary
    assert summary is not None
    summary = replace(summary, selected=replace(summary.selected, r2_vs_fold_train_median=-1e40))
    final_fits = (
        *receipt.final_fits[:-1],
        replace(
            receipt.final_fits[-1],
            iterations=240,
            failure_reason="candidate did not converge within 240 iterations",
        ),
    )
    receipt = replace(
        receipt,
        nested_point_summary=summary,
        final_fits=final_fits,
        final_fit_iterations=tuple(item.iterations for item in final_fits),
    )
    hydrated = engine.hydrate_source_fit_receipt(engine.source_fit_receipt_document(receipt))
    assert hydrated == receipt
    assert hydrated.nested_point_summary.selected.r2_vs_fold_train_median == -1e40
    assert hydrated.final_fits[-1].iterations == 240


def test_manifest_byte_bound_is_inclusive(monkeypatch, tmp_path, original_receipts):
    _, _, manifest = _store(tmp_path, original_receipts)
    payload = manifest_bytes(manifest)
    monkeypatch.setattr(engine, "MAX_MANIFEST_BYTES", len(payload))
    assert engine.decode_manifest(payload) == manifest
    monkeypatch.setattr(engine, "MAX_MANIFEST_BYTES", len(payload) - 1)
    with pytest.raises(CensusError):
        engine.decode_manifest(payload)


def test_foreign_page_and_unsealed_manifest_bindings_are_rejected(tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    foreign_page = replace(manifest.pages[0], sha256=_OTHER)
    with pytest.raises(CensusError, match="outside the retained inventory"):
        store.read_page(foreign_page)
    with pytest.raises(CensusError, match="outside the sealed inventory"):
        store.read_manifest(None)
    sealed = store.seal(manifest)
    foreign_manifest = replace(sealed, sha256=_OTHER)
    with pytest.raises(CensusError, match="outside the sealed inventory"):
        store.read_manifest(foreign_manifest)


@pytest.mark.parametrize("method", ["create", "open"])
def test_store_paths_require_explicit_path_objects(tmp_path, original_receipts, method):
    if method == "create":
        with pytest.raises(CensusError):
            engine.JsonCensusReceiptStore(str(tmp_path / _CANARY))
    else:
        store, _, manifest = _store(tmp_path, original_receipts)
        sealed = store.seal(manifest)
        with pytest.raises(CensusError):
            engine.JsonCensusReceiptStore.open_existing(str(store.directory), sealed)


def test_missing_complete_store_and_removed_live_directory_fail_safely(tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    sealed = store.seal(manifest)
    with pytest.raises(CensusError, match="could not be opened") as error:
        engine.JsonCensusReceiptStore.open_existing(tmp_path / _CANARY, sealed)
    assert _CANARY not in str(error.value)
    store.directory.rename(tmp_path / "moved-source")
    with pytest.raises(CensusError, match="directory binding"):
        store.read_page(manifest.pages[0])


@pytest.mark.parametrize("size_change", [-1, 1])
def test_file_length_tampering_is_rejected_before_decode(tmp_path, original_receipts, size_change):
    store, _, manifest = _store(tmp_path, original_receipts)
    binding = manifest.pages[0]
    path = store.directory / binding.file_name
    payload = path.read_bytes()
    path.write_bytes(payload[:-1] if size_change < 0 else payload + b" ")
    with pytest.raises(CensusError):
        store.read_page(binding)


def test_metadata_change_during_single_read_is_rejected(monkeypatch, tmp_path, original_receipts):
    store, _, manifest = _store(tmp_path, original_receipts)
    original_fstat = engine.os.fstat
    calls = 0

    def changed_after_read(descriptor):
        nonlocal calls
        metadata = original_fstat(descriptor)
        calls += 1
        if calls == 2:
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino,
                st_size=metadata.st_size,
                st_mtime_ns=metadata.st_mtime_ns + 1,
                st_ctime_ns=metadata.st_ctime_ns,
                st_birthtime_ns=getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns),
            )
        return metadata

    monkeypatch.setattr(engine.os, "fstat", changed_after_read)
    with pytest.raises(CensusError):
        store.read_page(manifest.pages[0])
    assert calls == 2


def test_self_consistent_manifest_cannot_replace_the_locked_child_page_digest(
    tmp_path, original_receipts
):
    store, _, manifest = _store(tmp_path, original_receipts)
    sealed = store.seal(manifest)
    forged = replace(
        manifest, pages=(replace(manifest.pages[0], page_digest=_OTHER), manifest.pages[1])
    )
    payload = manifest_bytes(forged)
    (store.directory / MANIFEST_NAME).write_bytes(payload)
    binding = replace(
        sealed,
        bytes=len(payload),
        sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
        manifest_digest=forged.digest,
    )
    with pytest.raises(CensusError):
        engine.JsonCensusReceiptStore.open_existing(store.directory, binding)


def test_whole_manifest_digest_is_checked_independently_of_its_file_hash(
    tmp_path, original_receipts
):
    store, _, manifest = _store(tmp_path, original_receipts)
    sealed = store.seal(manifest)
    wrong_semantic_digest = replace(sealed, manifest_digest=_OTHER)
    with pytest.raises(CensusError):
        engine.JsonCensusReceiptStore.open_existing(store.directory, wrong_semantic_digest)
