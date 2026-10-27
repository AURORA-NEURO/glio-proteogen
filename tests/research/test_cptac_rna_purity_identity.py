"""Reference-only released-axis and exact identity oracles; no inference."""

from __future__ import annotations

import copy
import io
import json
import pickle
from dataclasses import asdict, replace

import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    GeneIdentity,
    HgncReference,
)
from glio_proteogen.research.cptac_gbm_rna_purity_admission import identity
from glio_proteogen.research.cptac_gbm_rna_purity_admission.contracts import digest
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service


def _gene(index, symbol, *, ensembl="default"):
    return GeneIdentity(
        f"HGNC:{index}",
        symbol,
        str(index),
        f"ENSG{index:011d}" if ensembl == "default" else ensembl,
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


@pytest.fixture
def reference():
    names, _ = identity._released_metadata()
    first, missing, ambiguous = (
        _gene(1, names[0]),
        _gene(2, names[1], ensembl=None),
        _gene(3, names[2]),
    )
    collision = _gene(4, "SYNTHETIC_NONMODEL_COLLISION", ensembl=ambiguous.ensembl_gene_id)
    return _reference(first, missing, ambiguous, collision)


def test_exact_released_axis_retains_original_names_lengths_and_ambiguity(reference):
    names, lengths = identity._released_metadata()
    axis = identity.admit_model_axis(reference)
    assert tuple(feature.source_symbol for feature in axis.features) == names
    assert tuple(feature.source_length for feature in axis.features) == lengths
    assert len(axis.features) == 5829
    assert tuple(feature.reference_state for feature in axis.features[:3]) == (
        "resolved",
        "unresolved_reference",
        "ambiguous_identity",
    )
    assert axis.features[0].identity == reference.by_symbol[names[0]]
    assert axis.features[1].identity == reference.by_symbol[names[1]]
    assert axis.features[3].identity is None
    receipt = axis.receipt
    assert (
        receipt.resolved_features,
        receipt.unresolved_reference_features,
        receipt.ambiguous_identity_features,
    ) == (1, 5827, 1)
    assert receipt.feature_order_digest == identity.EXPECTED_FEATURE_ORDER_DIGEST
    assert receipt.feature_length_digest == digest(lengths)
    assert receipt.feature_mapping_digest == digest(
        tuple(asdict(feature) for feature in axis.features)
    )
    assert receipt.canonical_hgnc_reference_digest == identity.canonical_hgnc_reference_digest(
        reference
    )
    assert axis.digest == digest(receipt.model_dump(mode="json"))
    identity.validate_model_axis(axis, hgnc=reference)


def test_reference_digest_and_axis_are_deterministic_under_index_order(reference):
    genes = tuple(reference.by_hgnc.values())
    reordered = _reference(*reversed(genes))
    first, second = identity.admit_model_axis(reference), identity.admit_model_axis(reordered)
    assert first.receipt == second.receipt and first.digest == second.digest
    assert first.features == second.features


def test_foreign_reference_with_same_feature_count_cannot_reuse_axis(reference):
    axis = identity.admit_model_axis(reference)
    names, _ = identity._released_metadata()
    foreign = _reference(_gene(90, names[0]))
    with pytest.raises(identity.ModelAxisError, match="exact approved reference"):
        identity.validate_model_axis(axis, hgnc=foreign)
    assert (
        identity.admit_model_axis(foreign).receipt.canonical_hgnc_reference_digest
        != axis.receipt.canonical_hgnc_reference_digest
    )


def test_same_gene_symbol_with_wrong_stable_identity_changes_reference_binding(reference):
    axis = identity.admit_model_axis(reference)
    genes = list(reference.by_hgnc.values())
    genes[0] = replace(genes[0], ensembl_gene_id="ENSG99999999999")
    wrong = _reference(*genes)
    with pytest.raises(identity.ModelAxisError):
        identity.validate_model_axis(axis, hgnc=wrong)


def test_inconsistent_or_nonreference_indexes_reject_before_axis_admission(reference):
    with pytest.raises(identity.ModelAxisError):
        identity.admit_model_axis(None)
    corrupted = _reference(*reference.by_hgnc.values())
    object.__setattr__(corrupted, "by_symbol", {})
    with pytest.raises(identity.ModelAxisError, match="indexes"):
        identity.admit_model_axis(corrupted)


@pytest.mark.parametrize("change", ["order", "symbol", "length", "mapping", "partition"])
def test_forged_or_reordered_axis_is_not_accepted(reference, change):
    axis = identity.admit_model_axis(reference)
    features = list(axis.features)
    receipt = axis.receipt.model_dump(mode="python")
    if change == "order":
        features[0], features[1] = features[1], features[0]
    elif change == "symbol":
        features[3] = replace(features[3], source_symbol="SYNTHETIC_REPLACEMENT")
    elif change == "length":
        features[0] = replace(features[0], source_length=features[0].source_length + 1.0)
    elif change == "mapping":
        receipt["feature_mapping_digest"] = "sha256:" + "0" * 64
    else:
        receipt["resolved_features"] += 1
        receipt["unresolved_reference_features"] -= 1
    with pytest.raises(identity.ModelAxisError):
        identity.ModelInputAxis(tuple(features), identity.ModelAxisReceipt.model_validate(receipt))


def test_structurally_valid_forged_mapping_is_rechecked_against_actual_reference(reference):
    axis = identity.admit_model_axis(reference)
    features = (replace(axis.features[0], reference_state="ambiguous_identity"), *axis.features[1:])
    values = axis.receipt.model_dump(mode="python")
    values.update(
        feature_mapping_digest=digest(tuple(asdict(feature) for feature in features)),
        resolved_features=0,
        ambiguous_identity_features=2,
    )
    forged = identity.ModelInputAxis(features, identity.ModelAxisReceipt.model_validate(values))
    with pytest.raises(identity.ModelAxisError):
        identity.validate_model_axis(forged, hgnc=reference)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_symbol": "with space"},
        {"source_symbol": ""},
        {"source_symbol": 7},
        {"source_length": 1},
        {"source_length": 0.0},
        {"source_length": float("inf")},
        {"identity": object()},
        {"reference_state": "unknown"},
        {"identity": None, "reference_state": "resolved"},
        {"reference_state": "unresolved_reference"},
    ],
)
def test_model_feature_invariants_are_not_bypassed(reference, changes):
    feature = identity.admit_model_axis(reference).features[0]
    with pytest.raises(identity.ModelAxisError):
        replace(feature, **changes)


def test_wrong_approved_symbol_cannot_be_attached_to_source_feature(reference):
    feature = identity.admit_model_axis(reference).features[0]
    with pytest.raises(identity.ModelAxisError):
        replace(feature, identity=_gene(10, "SYNTHETIC_OTHER_SYMBOL"))


@pytest.mark.parametrize(
    "field",
    ["model_artifact_sha256", "model_content_digest", "feature_order_digest", "hgnc_source_sha256"],
)
def test_receipt_cannot_claim_a_different_release_or_hgnc_lock(reference, field):
    values = identity.admit_model_axis(reference).receipt.model_dump(mode="python")
    values[field] = "sha256:" + "1" * 64
    with pytest.raises(ValidationError):
        identity.ModelAxisReceipt.model_validate(values)


def test_axis_receipt_strictness_and_nonserialization(reference):
    axis = identity.admit_model_axis(reference)
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
    assert axis.features[0].source_symbol not in repr(axis)
    assert "ENSG" not in repr(axis)
    values = axis.receipt.model_dump(mode="python")
    values["resolved_features"] = True
    with pytest.raises(ValidationError):
        identity.ModelAxisReceipt.model_validate(values)
    with pytest.raises(identity.ModelAxisError):
        identity.ModelInputAxis(list(axis.features), axis.receipt)
    with pytest.raises(identity.ModelAxisError):
        identity.ModelInputAxis(axis.features, {})
    with pytest.raises(identity.ModelAxisError):
        identity.validate_model_axis(object(), hgnc=reference)


def test_axis_constructor_revalidates_receipt_constructed_without_pydantic_validation(reference):
    axis = identity.admit_model_axis(reference)
    values = axis.receipt.model_dump(mode="python")
    values["model_artifact_sha256"] = "sha256:" + "0" * 64
    forged = identity.ModelAxisReceipt.model_construct(**values)
    with pytest.raises(identity.ModelAxisError, match="receipt"):
        identity.ModelInputAxis(axis.features, forged)


class _Resource:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def joinpath(self, _path):
        return self

    def open(self, _mode):
        resource = self

        class Stream(io.BytesIO):
            def read(self, size=-1):
                resource.requests.append(size)
                return super().read(size)

        return Stream(self.payload)


@pytest.mark.parametrize(
    "size", [1, identity.MODEL_ARTIFACT_BYTES, identity.MODEL_ARTIFACT_BYTES + 1]
)
def test_artifact_size_hash_and_bounded_read_before_decoding(monkeypatch, size):
    resource = _Resource(b"x" * size)
    monkeypatch.setattr(identity, "files", lambda _package: resource)
    with pytest.raises(identity.ModelAxisError, match="byte lock"):
        identity._read_released_metadata()
    assert resource.requests == [identity.MODEL_ARTIFACT_BYTES + 1]


def test_missing_resource_error_is_sanitized(monkeypatch):
    def missing(_package):
        raise OSError("PRIVATE_SOURCE_PATH")

    monkeypatch.setattr(identity, "files", missing)
    with pytest.raises(identity.ModelAxisError) as captured:
        identity._read_released_metadata()
    assert "PRIVATE_SOURCE_PATH" not in str(captured.value)


@pytest.mark.parametrize(
    "metadata",
    [b"not JSON", b"{}", b'{"input":null}', b'{"input":{"feature_names":[],"feature_lengths":[]}}'],
)
def test_metadata_decoder_rejects_invalid_shapes_without_loading_parameters(monkeypatch, metadata):
    identity._released_metadata.cache_clear()
    try:
        monkeypatch.setattr(identity, "_read_released_metadata", lambda: metadata)
        with pytest.raises(identity.ModelAxisError):
            identity._released_metadata()
    finally:
        identity._released_metadata.cache_clear()


def test_no_catalog_model_or_preprocessing_call_during_axis_admission(reference, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("model execution was invoked")

    monkeypatch.setattr(catalog, "gbm_rna_purity_catalog", forbidden)
    monkeypatch.setattr(engine, "_forward", forbidden)
    monkeypatch.setattr(engine, "_input_vector", forbidden)
    monkeypatch.setattr(service, "analyze_gbm_rna_purity", forbidden)
    assert identity.admit_model_axis(reference).receipt.model_feature_count == 5829
