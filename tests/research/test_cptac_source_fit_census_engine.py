"""Synthetic every-gene fitting, source sealing, hydration and vault privacy proofs."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict, replace
from unittest.mock import patch

import numpy as np
import pytest

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.research.cptac_gbm_external_admission import transfer
from glio_proteogen.research.cptac_gbm_feature_space import atlas
from glio_proteogen.research.cptac_gbm_feature_space.contracts import FeatureMatrix
from glio_proteogen.research.cptac_gbm_source_fit_census import contracts, engine
from glio_proteogen.research.cptac_gbm_source_fit_census.storage import JsonCensusReceiptStore
from glio_proteogen.research.cptac_gbm_transcript_protein_discordance import nested_selection
from tests.research.test_cptac_feature_space_atlas import _folds, _matrix

REQUEST = "sha256:" + "f" * 64


def _sha(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class _MemoryStore:
    def __init__(self):
        self.pages = {}
        self.reads = []
        self.events = []
        self.sealed = None
        self.page_fault = None
        self.seal_fault = None
        self.read_fault = None

    def write_page(self, page):
        assert self.sealed is None
        assert page.page_number == len(self.pages)
        payload = contracts.page_bytes(page)
        self.pages[page.page_number] = page
        self.events.append(("page", page.page_number))
        result = contracts.ReceiptPageBinding(
            page.page_number,
            f"pages/{page.page_number:05d}.json",
            len(payload),
            _sha(payload),
            page.digest,
            len(page.genes),
            page.genes[0].identity.hgnc_id,
            page.genes[-1].identity.hgnc_id,
        )
        if self.page_fault == "type":
            return None
        if self.page_fault:
            return replace(result, **self.page_fault)
        return result

    def seal(self, receipt):
        assert self.sealed is None
        assert len(receipt.pages) == len(self.pages)
        assert (
            tuple(record.digest for page in self.pages.values() for record in page.genes)
            == receipt.gene_record_digests
        )
        self.events.append(("seal", receipt.total_genes))
        self.sealed = receipt
        payload = contracts.manifest_bytes(receipt)
        result = contracts.SourceManifestBinding(
            contracts.MANIFEST_NAME, len(payload), _sha(payload), receipt.digest
        )
        if self.seal_fault == "type":
            return None
        if self.seal_fault:
            return replace(result, **self.seal_fault)
        return result

    def read_page(self, binding):
        self.reads.append(binding.page_number)
        if self.read_fault == "type":
            return None
        page = self.pages[binding.page_number]
        return replace(page, **self.read_fault) if self.read_fault else page


@pytest.fixture(scope="module")
def numerical():
    rng = np.random.default_rng(271828)
    cnv, rna = rng.normal(size=72) + 10, rng.normal(size=72) + 10
    protein = 2 * (rna - 10) + 0.4 * (cnv - 10) + rng.normal(scale=0.05, size=72)
    folds = _folds()
    accepted = transfer.fit_source_gene(cnv, rna, protein, folds)
    assert accepted.receipt.accepted
    degenerate = transfer.fit_source_gene(np.ones(72), rna, protein, folds)
    assert not degenerate.receipt.accepted
    original = nested_selection._fit_candidate

    def failed_final(*args, **kwargs):
        attempt = original(*args, **kwargs)
        if kwargs["outer_fold"] == -1 and attempt.candidate == "full":
            return replace(
                attempt,
                model=None,
                median=None,
                failure_reason="candidate did not converge within 240 iterations",
            )
        return attempt

    with patch.object(nested_selection, "_fit_candidate", side_effect=failed_final):
        partial = transfer.fit_source_gene(cnv, rna, protein, folds)
    assert not partial.receipt.accepted and partial.receipt.nested_point_summary is not None
    assert partial.receipt.selected_candidate is not None and len(partial.receipt.final_fits) == 4
    return cnv, rna, protein, folds, accepted, degenerate, partial


def _context(features=3):
    matrix = _matrix(features=features)
    folds = _folds()
    return matrix, folds, atlas.build_source_catalog(matrix, folds), _MemoryStore()


def _fit(matrix, folds, catalog, store, **kwargs):
    return engine.fit_source_census(
        matrix, folds, catalog=catalog, request_digest=REQUEST, store=store, **kwargs
    )


def test_every_gene_reaches_fitter_despite_capacity_and_variation_flags(monkeypatch, numerical):
    matrix, folds, catalog, store = _context(5)
    genes = tuple(
        replace(
            gene,
            count_capacity=replace(gene.count_capacity, all_five_fold_count_support_possible=False),
            training_variation=replace(
                gene.training_variation,
                cnv_contexts_with_variation=0,
                rna_contexts_with_variation=0,
                protein_contexts_with_variation=0,
            ),
        )
        for gene in catalog.genes
    )
    catalog = replace(catalog, genes=genes, count_supported_genes=0)
    cases = [numerical[4], numerical[5], numerical[6], numerical[4], numerical[5]]
    calls, checkpoints = [], []

    def fit(cnv, rna, protein, supplied_folds):
        row = len(calls)
        for array, original in zip(
            (cnv, rna, protein),
            (matrix.cnv[row], matrix.rna[row], matrix.protein[row]),
            strict=True,
        ):
            np.testing.assert_array_equal(array, original)
            assert not array.flags.writeable and np.shares_memory(array, original)
        np.testing.assert_array_equal(supplied_folds, folds)
        assert not supplied_folds.flags.writeable
        calls.append(row)
        return cases[row]

    def forbidden_lookup(*_args, **_kwargs):
        pytest.fail("fitting used the repeated linear HGNC lookup")

    def checkpoint(binding):
        assert binding.page_number in store.pages
        assert store.sealed is None
        checkpoints.append(binding.page_number)

    monkeypatch.setattr(FeatureMatrix, "gene", forbidden_lookup)
    monkeypatch.setattr(engine, "fit_source_gene", fit)
    census = _fit(matrix, folds, catalog, store, page_size=2, checkpoint=checkpoint)
    assert calls == list(range(5)) and checkpoints == [0, 1, 2]
    assert store.events == [("page", 0), ("page", 1), ("page", 2), ("seal", 5)]
    assert census.receipt is store.sealed
    assert (
        census.receipt.accepted_genes,
        census.receipt.abstained_genes,
        census.receipt.input_domain_rejected_genes,
    ) == (2, 3, 0)
    for identity, expected in zip(matrix.axis.identities, cases, strict=True):
        record = census.source_gene_record(identity.hgnc_id, store=store)
        assert asdict(record.source) == asdict(expected.receipt)
        hydrated = census.hydrate_gene(identity.hgnc_id, store=store)
        assert hydrated._predictors is expected._predictors
        assert hydrated.receipt is record.source
    assert len(calls) == 5


def test_real_synthetic_fitter_preserves_original_acceptance_and_abstention(numerical):
    cnv, rna, protein, folds, accepted, degenerate, _ = numerical
    values = np.vstack((cnv, np.ones(72))), np.vstack((rna, rna)), np.vstack((protein, protein))
    matrix = _matrix(features=2, values=values)
    catalog, store = atlas.build_source_catalog(matrix, folds), _MemoryStore()
    census = _fit(matrix, folds, catalog, store)
    records = [
        census.source_gene_record(gene.hgnc_id, store=store) for gene in matrix.axis.identities
    ]
    assert [asdict(record.source) for record in records] == [
        asdict(accepted.receipt),
        asdict(degenerate.receipt),
    ]
    assert census.receipt.accepted_genes == census.receipt.abstained_genes == 1
    for record in records:
        assert record.source.profile_id == transfer.PROFILE_ID


def test_genuine_four_fold_acceptance_survives_false_five_fold_capacity_diagnostic():
    rng = np.random.default_rng(271828)
    folds = _folds(cases=80)
    cnv, rna = rng.normal(size=80) + 10, rng.normal(size=80) + 10
    protein = 2 * (rna - 10) + 0.4 * (cnv - 10) + rng.normal(scale=0.05, size=80)
    for values in (cnv, rna, protein):
        values[folds == 4] = np.nan
    matrix = _matrix(cases=80, values=tuple(values[None, :] for values in (cnv, rna, protein)))
    catalog = atlas.build_source_catalog(matrix, folds)
    capacity = catalog.genes[0].count_capacity
    assert capacity.fold_joint_counts == (16, 16, 16, 16, 0)
    assert capacity.minimum_outer_training_joint == 48
    assert not capacity.all_five_fold_count_support_possible
    assert catalog.count_supported_genes == 0

    original = transfer.fit_source_gene(cnv, rna, protein, folds)
    assert original.receipt.accepted
    assert original.receipt.complete_count == original.receipt.common_oof_count == 64
    assert original.receipt.valid_outer_folds == 4
    assert sum(trace.comparison_accepted for trace in original.receipt.fold_trace) == 4

    store = _MemoryStore()
    census = _fit(matrix, folds, catalog, store)
    record = census.source_gene_record(matrix.axis.hgnc_ids[0], store=store)
    assert asdict(record.source) == asdict(original.receipt)
    assert census.receipt.accepted_genes == census.receipt.total_genes == 1
    assert census.receipt.abstained_genes == census.receipt.input_domain_rejected_genes == 0


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_confirmed_input_domain_rejection_retains_gene_after_actual_fitter_attempt(
    monkeypatch, axis
):
    values = [np.ones((1, 72), dtype=np.float64) for _ in range(3)]
    values[axis][0, 0] = -2e12 if axis == 2 else 2e12
    matrix, folds = _matrix(values=tuple(values)), _folds()
    catalog, store, calls = atlas.build_source_catalog(matrix, folds), _MemoryStore(), []

    def fit(*args):
        calls.append(1)
        return transfer.fit_source_gene(*args)

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    census = _fit(matrix, folds, catalog, store)
    record = census.source_gene_record(matrix.axis.hgnc_ids[0], store=store)
    assert calls == [1] and record.source is None
    assert record.input_domain_rejection == contracts.INPUT_DOMAIN_REJECTION
    assert census.receipt.input_domain_rejected_genes == census.receipt.total_genes == 1
    assert census.receipt.accepted_genes == census.receipt.abstained_genes == 0
    assert census.hydrate_gene(matrix.axis.hgnc_ids[0], store=store) is None


@pytest.mark.parametrize("failure", [ValueError, TypeError, RuntimeError])
def test_valid_input_errors_propagate_without_fake_abstention_or_complete_seal(
    monkeypatch, numerical, failure
):
    matrix, folds, catalog, store = _context()
    calls = []
    private_message = "synthetic-private-fitter-failure"

    def fit(*_args):
        calls.append(1)
        if len(calls) == 2:
            raise failure(private_message)
        return numerical[4]

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    with pytest.raises(failure, match=private_message):
        _fit(matrix, folds, catalog, store, page_size=1)
    assert len(calls) == 2 and len(store.pages) == 1 and store.sealed is None


def test_boundary_magnitude_is_not_reclassified_as_domain_rejection(monkeypatch):
    values = [np.ones((1, 72), dtype=np.float64) for _ in range(3)]
    values[0][0, 0] = engine.MAX_ABSOLUTE_INPUT
    matrix, folds = _matrix(values=tuple(values)), _folds()
    store = _MemoryStore()

    def fail(*_args):
        raise ValueError

    monkeypatch.setattr(engine, "fit_source_gene", fail)
    with pytest.raises(ValueError):
        _fit(matrix, folds, atlas.build_source_catalog(matrix, folds), store)
    assert store.sealed is None and store.pages == {}


@pytest.mark.parametrize("stage", ["before_first", "after_page", "before_seal"])
def test_cancellation_propagates_and_never_creates_complete_seal(monkeypatch, numerical, stage):
    matrix, folds, catalog, store = _context(2)
    calls = []

    def fit(*_args):
        calls.append(1)
        return numerical[4]

    def cancel():
        if (
            stage == "before_first"
            or (stage == "after_page" and len(calls) == 1)
            or (stage == "before_seal" and len(calls) == 2)
        ):
            raise InterruptedError

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    with pytest.raises(InterruptedError):
        _fit(matrix, folds, catalog, store, page_size=1, cancel=cancel)
    assert store.sealed is None
    assert len(calls) == {"before_first": 0, "after_page": 1, "before_seal": 2}[stage]


def test_checkpoint_failure_leaves_persisted_page_but_prevents_next_fit_and_seal(
    monkeypatch, numerical
):
    matrix, folds, catalog, store = _context(3)
    calls = []

    def fit(*_args):
        calls.append(1)
        return numerical[4]

    def checkpoint(binding):
        assert binding.page_number in store.pages
        raise InterruptedError

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    with pytest.raises(InterruptedError):
        _fit(matrix, folds, catalog, store, page_size=2, checkpoint=checkpoint)
    assert len(calls) == 2 and len(store.pages) == 1 and store.sealed is None


def test_original_mutable_folds_are_snapshotted_once(monkeypatch, numerical):
    matrix, folds, catalog, store = _context(3)
    expected = folds.copy()
    calls = []

    def fit(*args):
        np.testing.assert_array_equal(args[-1], expected)
        calls.append(1)
        folds[:] = 0
        return numerical[4]

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    _fit(matrix, folds, catalog, store)
    assert len(calls) == 3


def test_hydration_is_no_refit_and_cache_retains_only_one_page(monkeypatch, numerical):
    matrix, folds, catalog, store = _context(5)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    census = _fit(matrix, folds, catalog, store, page_size=2)

    def forbidden(*_args, **_kwargs):
        pytest.fail("hydration refitted the source")

    monkeypatch.setattr(engine, "fit_source_gene", forbidden)
    for position in (0, 1, 2, 3, 0, 4):
        census.hydrate_gene(matrix.axis.hgnc_ids[position], store=store)
    assert store.reads == [0, 1, 0, 2]
    assert census._cached_page is store.pages[2]
    assert not hasattr(census, "__dict__")
    assert all(
        not isinstance(
            getattr(census, name), (FeatureMatrix, atlas.SourceFeatureCatalog, np.ndarray)
        )
        for name in census.__slots__
    )


@pytest.mark.parametrize("fault", ["type", {"request_digest": "sha256:" + "0" * 64}])
def test_untrusted_hydration_page_cannot_change_bound_source_record(monkeypatch, numerical, fault):
    matrix, folds, catalog, store = _context(2)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    census = _fit(matrix, folds, catalog, store)
    store.read_fault = fault
    with pytest.raises(contracts.CensusError):
        census.hydrate_gene(matrix.axis.hgnc_ids[0], store=store)
    assert census._cached_page is None


def test_vault_refuses_pickle_dataclass_conversion_and_mutation(monkeypatch, numerical):
    matrix, folds, catalog, store = _context()
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    census = _fit(matrix, folds, catalog, store)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(census)
    with pytest.raises(TypeError):
        asdict(census)
    with pytest.raises(AttributeError, match="immutable"):
        census._predictors = ()
    assert "_predictors" not in repr(census) and "HGNC:" not in repr(census)
    document = json.dumps(asdict(census.receipt), allow_nan=False)
    assert "_predictors" not in document and "beta" not in document
    for unknown in (None, "SYNTHETIC-PRIVATE-ID", "HGNC:999999"):
        with pytest.raises(contracts.CensusError) as error:
            census.source_gene_record(unknown, store=store)
        assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize(
    "field",
    [
        "feature_axis_digest",
        "candidate_digest",
        "source_fold_assignment_digest",
        "profile_id",
        "source_case_count",
    ],
)
def test_source_context_mismatch_fails_before_any_fit_or_page(monkeypatch, field):
    matrix, folds, catalog, store = _context()

    def forbidden(*_args):
        pytest.fail("mismatched source context reached fitting")

    monkeypatch.setattr(engine, "fit_source_gene", forbidden)
    catalog = replace(
        catalog, **{field: 71 if field == "source_case_count" else "sha256:" + "0" * 64}
    )
    with pytest.raises(contracts.CensusError):
        _fit(matrix, folds, catalog, store)
    assert not store.pages and store.sealed is None


@pytest.mark.parametrize(
    "folds",
    [
        None,
        np.arange(72, dtype=np.int64) % 5,
        np.zeros(72, dtype=np.int8),
        np.zeros(71, dtype=np.int8),
    ],
)
def test_invalid_fold_contract_never_reaches_fitter(monkeypatch, folds):
    matrix, _, catalog, store = _context()

    def forbidden(*_args):
        pytest.fail("invalid folds reached fitter")

    monkeypatch.setattr(engine, "fit_source_gene", forbidden)
    with pytest.raises(contracts.CensusError):
        _fit(matrix, folds, catalog, store)


@pytest.mark.parametrize("page_size", [False, 0, 65, 1.5])
def test_page_size_contract_is_exact_and_bounded(page_size):
    matrix, folds, catalog, store = _context()
    with pytest.raises(contracts.CensusError):
        _fit(matrix, folds, catalog, store, page_size=page_size)
    assert store.pages == {}


@pytest.mark.parametrize(
    "fault",
    ["type", {"bytes": 1}, {"sha256": "sha256:" + "0" * 64}, {"page_digest": "sha256:" + "0" * 64}],
)
def test_store_page_binding_is_independently_checked_before_checkpoint_or_seal(
    monkeypatch, numerical, fault
):
    matrix, folds, catalog, store = _context()
    store.page_fault = fault
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    with pytest.raises(contracts.CensusError):
        _fit(matrix, folds, catalog, store)
    assert store.sealed is None


@pytest.mark.parametrize("fault", ["type", {"bytes": 1}, {"sha256": "sha256:" + "0" * 64}])
def test_store_manifest_binding_is_independently_checked(monkeypatch, numerical, fault):
    matrix, folds, catalog, store = _context()
    store.seal_fault = fault
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    with pytest.raises(contracts.CensusError):
        _fit(matrix, folds, catalog, store)


def test_source_phase_byte_cap_stops_before_page_write(monkeypatch, numerical):
    matrix, folds, catalog, store = _context(1)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    monkeypatch.setattr(engine, "MAX_SOURCE_BYTES", 1)
    with pytest.raises(contracts.CensusError, match="byte bound"):
        _fit(matrix, folds, catalog, store)
    assert store.pages == {} and store.sealed is None


def test_manifest_bytes_count_toward_total_phase_bound(monkeypatch, numerical):
    matrix, folds, catalog, store = _context(1)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    first = _fit(matrix, folds, catalog, store)
    page_size = first.receipt.pages[0].bytes
    monkeypatch.setattr(engine, "MAX_SOURCE_BYTES", page_size)
    second = _MemoryStore()
    with pytest.raises(contracts.CensusError, match="including its manifest"):
        _fit(matrix, folds, catalog, second)
    assert len(second.pages) == 1 and second.sealed is None


def test_repeat_census_has_canonical_identical_pages_manifest_and_receipt_digests(
    monkeypatch, numerical
):
    matrix, folds, catalog, first = _context(5)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    a = _fit(matrix, folds, catalog, first, page_size=2)
    second = _MemoryStore()
    b = _fit(matrix, folds, catalog, second, page_size=2)
    assert contracts.manifest_bytes(a.receipt) == contracts.manifest_bytes(b.receipt)
    assert a.binding.sha256 == _sha(contracts.manifest_bytes(a.receipt))
    assert a.binding.manifest_digest == a.receipt.digest
    for number in first.pages:
        document = contracts.page_document(first.pages[number])
        assert contracts.page_bytes(first.pages[number]) == contracts.page_bytes(
            second.pages[number]
        )
        assert canonical_json_bytes(document) == contracts.page_bytes(first.pages[number])
        assert (
            sha256_digest({key: value for key, value in document.items() if key != "page_digest"})
            == document["page_digest"]
        )


@pytest.mark.parametrize(
    ("source", "rejection"), [(None, None), (None, "synthetic-private-reason"), (object(), None)]
)
def test_gene_receipt_has_exactly_one_typed_outcome(source, rejection):
    identity = _matrix().axis.identities[0]
    with pytest.raises(contracts.CensusError) as error:
        contracts.SourceGeneReceipt(identity, source, rejection)
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "fault",
    ["wrong_type", "wrong_profile", "reordered", "missing_family", "abstained_with_predictors"],
)
def test_original_fitter_contract_corruption_is_never_persisted(monkeypatch, numerical, fault):
    matrix, folds, catalog, store = _context(1)
    fitted = numerical[4]
    if fault == "wrong_type":
        fitted = object()
    elif fault == "wrong_profile":
        fitted = replace(
            fitted, receipt=replace(fitted.receipt, profile_id="synthetic-foreign-profile")
        )
    elif fault == "reordered":
        fitted = replace(fitted, _predictors=tuple(reversed(fitted._predictors)))
    elif fault == "missing_family":
        fitted = replace(fitted, _predictors=fitted._predictors[:-1])
    else:
        fitted = replace(fitted, receipt=numerical[5].receipt)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: fitted)
    with pytest.raises(contracts.CensusError):
        _fit(matrix, folds, catalog, store)
    assert not store.pages and store.sealed is None


@pytest.mark.parametrize(
    "argument", ["matrix", "catalog", "store", "checkpoint", "cancel", "request_digest"]
)
def test_unadmitted_public_arguments_fail_before_any_fitting(monkeypatch, argument):
    matrix, folds, catalog, store = _context(1)
    kwargs = {"catalog": catalog, "request_digest": REQUEST, "store": store}
    if argument == "matrix":
        matrix = None
    elif argument == "catalog":
        kwargs["catalog"] = None
    elif argument == "request_digest":
        kwargs[argument] = "SYNTHETIC-PRIVATE-REQUEST"
    else:
        kwargs[argument] = object()

    def forbidden(*_args):
        pytest.fail("invalid public arguments reached fitting")

    monkeypatch.setattr(engine, "fit_source_gene", forbidden)
    with pytest.raises(contracts.CensusError) as error:
        engine.fit_source_census(matrix, folds, **kwargs)
    assert "PRIVATE" not in str(error.value)
    assert not store.pages and store.sealed is None


def _manifest_binding(receipt):
    payload = contracts.manifest_bytes(receipt)
    return contracts.SourceManifestBinding(
        contracts.MANIFEST_NAME, len(payload), _sha(payload), receipt.digest
    )


@pytest.mark.parametrize("failure", ["foreign_context", "record_digest", "gene_identity"])
def test_rebound_pages_still_require_matching_census_context_records_and_identity(
    monkeypatch, numerical, failure
):
    matrix, folds, catalog, store = _context(1)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    census = _fit(matrix, folds, catalog, store)
    manifest, keys = census.receipt, matrix.axis.hgnc_ids
    if failure == "foreign_context":
        page = replace(store.pages[0], request_digest="sha256:" + "0" * 64)
        payload = contracts.page_bytes(page)
        original = manifest.pages[0]
        binding = replace(
            original, bytes=len(payload), sha256=_sha(payload), page_digest=page.digest
        )
        store.pages[0] = page
        manifest = replace(manifest, pages=(binding,))
    elif failure == "record_digest":
        manifest = replace(manifest, gene_record_digests=("sha256:" + "0" * 64,))
    else:
        keys = ("HGNC:999",)
    rebound = engine.FrozenSourceCensus(
        manifest, _manifest_binding(manifest), census._predictors, keys
    )
    with pytest.raises(contracts.CensusError):
        rebound.hydrate_gene(keys[0], store=store)


def test_domain_rejection_cannot_accidentally_receive_another_genes_predictors(
    monkeypatch, numerical
):
    values = [np.ones((2, 72), dtype=np.float64) for _ in range(3)]
    values[0][1, 0] = 2e12
    matrix, folds = _matrix(features=2, values=tuple(values)), _folds()
    catalog, store = atlas.build_source_catalog(matrix, folds), _MemoryStore()

    def fit(cnv, *_args):
        if np.max(cnv) > engine.MAX_ABSOLUTE_INPUT:
            raise ValueError
        return numerical[4]

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    census = _fit(matrix, folds, catalog, store)
    swapped = engine.FrozenSourceCensus(
        census.receipt, census.binding, tuple(reversed(census._predictors)), matrix.axis.hgnc_ids
    )
    with pytest.raises(contracts.CensusError, match="domain rejection"):
        swapped.hydrate_gene(matrix.axis.hgnc_ids[1], store=store)


def test_vault_constructor_rejects_mutable_or_incomplete_private_inventory(monkeypatch, numerical):
    matrix, folds, catalog, store = _context(1)
    monkeypatch.setattr(engine, "fit_source_gene", lambda *_args: numerical[4])
    census = _fit(matrix, folds, catalog, store)
    with pytest.raises(contracts.CensusError):
        engine.FrozenSourceCensus(
            census.receipt, census.binding, list(census._predictors), matrix.axis.hgnc_ids
        )
    with pytest.raises(contracts.CensusError):
        engine.FrozenSourceCensus(census.receipt, census.binding, (), ())
    with pytest.raises(TypeError, match="cannot be serialized"):
        census.__getstate__()


def test_engine_json_store_roundtrip_preserves_partial_and_domain_records_without_predictor_export(
    tmp_path,
    monkeypatch,
    numerical,
):
    cnv, rna, protein, folds, accepted, _, partial = numerical
    values = [np.tile(array, (3, 1)) for array in (cnv, rna, protein)]
    values[1][2, 0] = 2e12
    matrix = _matrix(features=3, values=tuple(values))
    catalog = atlas.build_source_catalog(matrix, folds)
    store = JsonCensusReceiptStore(tmp_path / "aggregate-source-receipts")
    calls = []

    def fit(*args):
        row = len(calls)
        calls.append(row)
        return (accepted, partial)[row] if row < 2 else transfer.fit_source_gene(*args)

    monkeypatch.setattr(engine, "fit_source_gene", fit)
    census = _fit(matrix, folds, catalog, store, page_size=2)
    assert calls == [0, 1, 2]
    assert store.read_manifest(census.binding) == census.receipt
    assert {
        path.relative_to(store.directory).as_posix() for path in store.directory.rglob("*.json")
    } == {
        contracts.MANIFEST_NAME,
        "pages/00000.json",
        "pages/00001.json",
    }
    first, second, third = (
        census.source_gene_record(gene.hgnc_id, store=store) for gene in matrix.axis.identities
    )
    assert asdict(first.source) == asdict(accepted.receipt)
    assert asdict(second.source) == asdict(partial.receipt)
    assert third.source is None and third.input_domain_rejection == contracts.INPUT_DOMAIN_REJECTION
    reopened = JsonCensusReceiptStore.open_existing(store.directory, census.binding)

    def forbidden(*_args):
        pytest.fail("rehydration through the reopened source store refitted")

    monkeypatch.setattr(engine, "fit_source_gene", forbidden)
    hydrated = census.hydrate_gene(matrix.axis.hgnc_ids[0], store=reopened)
    assert hydrated._predictors is accepted._predictors
    assert asdict(hydrated.receipt) == asdict(accepted.receipt)
    assert census.hydrate_gene(matrix.axis.hgnc_ids[2], store=reopened) is None
    for path in store.directory.rglob("*.json"):
        text = path.read_text()
        assert "_predictors" not in text and '"beta"' not in text
        assert '"values"' not in text and "2000000000000.0" not in text
