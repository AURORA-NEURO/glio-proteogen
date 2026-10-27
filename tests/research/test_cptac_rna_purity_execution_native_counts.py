"""Synthetic coordinate, identity, conservation and privacy oracles for native counts."""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
from dataclasses import asdict, replace

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_external_admission import assays as schema
from glio_proteogen.research.cptac_gbm_external_admission.contracts import (
    GeneIdentity,
    SourceLock,
    SourceVerificationError,
)
from glio_proteogen.research.cptac_gbm_rna_purity_execution import identity
from glio_proteogen.research.cptac_gbm_rna_purity_execution import native_counts as native
from glio_proteogen.research.gbm_rna_purity import catalog, engine, service
from tests.research.test_cptac_rna_purity_execution_identity import _synthetic_axis


def _gene(index, symbol, *, ensembl=None):
    return GeneIdentity(f"HGNC:{index}", symbol, str(index), ensembl or f"ENSG{index:011d}")


def _row(gene, count="7", *, identifier=None, symbol=None, normalized="0.25"):
    if type(gene) is identity.ModelInputFeature:
        value, name = gene.release_gene_id, gene.source_symbol
    else:
        assert gene.ensembl_gene_id is not None
        value = gene.ensembl_gene_id.replace("_PAR_Y", ".4_PAR_Y")
        if not value.endswith("_PAR_Y"):
            value += ".4"
        name = gene.symbol
    return [
        identifier or value,
        symbol or name,
        "protein_coding",
        count,
        "13",
        "17",
        "0.5",
        "0.75",
        normalized,
    ]


def _summaries():
    return [
        [name, "", "", "20", "30", "40", "", "", ""] for name in sorted(schema.RNA_SUMMARY_LABELS)
    ]


def _payload(rows, *, summaries=None, ending="\n", bom=False):
    lines = [
        schema.RNA_ANNOTATION_COMMENT,
        "\t".join(schema.RNA_COLUMNS),
        *("\t".join(row) for row in [*(_summaries() if summaries is None else summaries), *rows]),
    ]
    return (("\ufeff" if bom else "") + ending.join(lines) + ending).encode()


def _lock(payload):
    return SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


@pytest.fixture(scope="module")
def complete():
    with pytest.MonkeyPatch.context() as patch:
        axis, reference = _synthetic_axis(patch)
        yield reference, axis, axis.features


@pytest.fixture
def small(complete):
    return complete[0], complete[1], complete[2][:6]


def _project(payload, fixture):
    return native.project_native_star_counts(payload, lock=_lock(payload), model_axis=fixture[1])


def test_manual_availability_oracle_preserves_zero_and_all_5829_slots(small):
    genes = small[2]
    rows = [
        _row(genes[0]),
        _row(genes[1], "0"),
        _row(genes[3], symbol="SYNTHETIC_WRONG_SYMBOL"),
        _row(genes[4]),
        _row(_gene(9000, genes[4].source_symbol)),
    ]
    result = _project(_payload(rows), small)
    assert result.counts[:6].tolist() == [7, 0, -1, -1, -1, -1]
    assert result.states[:6].tolist() == [0, 1, 2, 5, 4, 2]
    assert result.receipt.state_counts == (1, 1, 5825, 0, 1, 1)
    assert result.receipt.recognized_raw_count_sum == 7
    assert result.receipt.ambiguous_reference_gene_ids == 0
    assert result.receipt.duplicate_gene_symbol_groups == 1
    assert result.receipt.model_axis_digest == small[1].digest


def test_only_native_unstranded_counts_not_strand_tpm_fpkm_or_fpkm_uq(small):
    gene = small[2][0]
    first = _project(_payload([_row(gene)]), small)
    altered = _row(gene, normalized="100000")
    altered[4:8] = ["900", "800", "700.5", "600.25"]
    second = _project(_payload([altered]), small)
    np.testing.assert_array_equal(first.counts, second.counts)
    np.testing.assert_array_equal(first.states, second.states)
    assert first.counts[0] == second.counts[0] == 7
    assert first.receipt.input_sha256 != second.receipt.input_sha256
    assert first.binding_digest != second.binding_digest


def test_native_counts_do_not_filter_gene_type_or_intersect_protein_panel(small):
    row = _row(small[2][0])
    row[2] = "lncRNA"
    result = _project(_payload([row]), small)
    assert result.counts[0] == 7 and result.states[0] == 0
    assert result.receipt.model_feature_count == 5829


def test_row_order_bom_and_crlf_change_only_input_bindings_not_counts(small):
    rows = [_row(small[2][0]), _row(small[2][1], "0")]
    first = _project(_payload(rows), small)
    second = _project(_payload(list(reversed(rows)), ending="\r\n", bom=True), small)
    np.testing.assert_array_equal(first.counts, second.counts)
    np.testing.assert_array_equal(first.states, second.states)
    assert first.binding_digest != second.binding_digest


@pytest.mark.parametrize(
    ("recognized", "ready", "supported"),
    [(4663, False, False), (4664, True, False), (5770, True, False), (5771, True, True)],
)
def test_genuine_parsed_5829_feature_coverage_boundaries(complete, recognized, ready, supported):
    genes = complete[2]
    rows = [_row(gene, "1" if index == 0 else "0") for index, gene in enumerate(genes[:recognized])]
    result = _project(_payload(rows), complete)
    assert result.receipt.recognized_model_gene_count == recognized
    assert result.receipt.count_ready is ready and result.receipt.coverage_supported is supported
    assert result.receipt.observed_zero_model_gene_count == recognized - 1
    assert result.receipt.recognized_raw_count_sum == 1
    assert np.all(result.counts[recognized:] == -1)


def test_full_observed_zeros_plus_off_model_positive_are_not_count_ready(complete):
    rows = [_row(gene, "0") for gene in complete[2]]
    rows.append(_row(_gene(90000, "SYNTHETIC_OFF_MODEL"), "999"))
    result = _project(_payload(rows), complete)
    assert (
        result.receipt.recognized_model_gene_count
        == result.receipt.observed_zero_model_gene_count
        == 5829
    )
    assert result.receipt.coverage_supported and not result.receipt.count_ready
    assert result.receipt.recognized_raw_count_sum == 0


def test_summary_counts_are_excluded_and_all_gene_total_cannot_overflow_model_sum(small):
    summaries = _summaries()
    for row in summaries:
        row[3:6] = [str(native.MAX_NATIVE_COUNT)] * 3
    rows = [_row(small[2][0], str(native.MAX_NATIVE_COUNT))]
    rows.extend(
        _row(_gene(1000 + index, f"SYNTHETIC_OFF_MODEL_{index}"), str(native.MAX_NATIVE_COUNT))
        for index in range(10_000)
    )
    result = _project(_payload(rows, summaries=summaries), small)
    assert result.receipt.recognized_raw_count_sum == native.MAX_NATIVE_COUNT
    assert result.receipt.gene_rows == 10_001


@pytest.mark.parametrize("token", ["", "-1", "+1", "1.0", "1e3", "NaN", "Inf", " 1", "\u0661"])
@pytest.mark.parametrize("column", [3, 4, 5])
def test_all_native_count_fields_are_ascii_unsigned_integers(small, token, column):
    row = _row(small[2][0])
    row[column] = token
    with pytest.raises(native.NativeCountFormatError):
        _project(_payload([row]), small)


@pytest.mark.parametrize("placement", ["model", "off_model", "summary"])
def test_explicit_input_domain_rejection_also_covers_off_model_and_summary(small, placement):
    rows, summaries = [_row(small[2][0])], _summaries()
    if placement == "summary":
        summaries[0][4] = str(native.MAX_NATIVE_COUNT + 1)
    elif placement == "off_model":
        rows.append(_row(_gene(9000, "SYNTHETIC_OFF_MODEL"), str(native.MAX_NATIVE_COUNT + 1)))
    else:
        rows[0][3] = str(native.MAX_NATIVE_COUNT + 1)
    with pytest.raises(native.NativeCountDomainError):
        _project(_payload(rows, summaries=summaries), small)


@pytest.mark.parametrize("token", ["", "-1", "NaN", "Infinity", "1e999", " text"])
@pytest.mark.parametrize("column", [6, 7, 8])
def test_every_normalized_column_validated_even_when_unused(small, token, column):
    row = _row(_gene(9000, "SYNTHETIC_OFF_MODEL"))
    row[column] = token
    with pytest.raises(native.NativeCountFormatError):
        _project(_payload([_row(small[2][0]), row]), small)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.replace(b"GENCODE v36", b"GENCODE v35"),
        lambda data: data.replace(b"gene_name\tgene_type", b"gene_type\tgene_name"),
        lambda data: data.replace(b"gene_id\t", b"gene_id\textra\t", 1),
        lambda data: data + b"# extra comment\n",
        lambda data: data + b"\n",
        lambda data: data + b"bad\x00row\n",
        lambda data: data + b"bad\x7frow\n",
        lambda data: data + b"\xff\n",
        lambda data: b"\x1f\x8b" + data,
    ],
)
def test_wrong_schema_encoding_compression_and_extra_records_fail_closed(small, mutation):
    with pytest.raises(native.NativeCountFormatError):
        _project(mutation(_payload([_row(small[2][0])])), small)


@pytest.mark.parametrize(
    "case", ["missing", "duplicate", "annotation", "normalized", "invalid_count"]
)
def test_exact_summary_inventory_and_fields_are_required(small, case):
    summaries = _summaries()
    if case == "missing":
        summaries.pop()
    elif case == "duplicate":
        summaries.append(summaries[0])
    elif case == "annotation":
        summaries[0][1] = "SYNTHETIC_METADATA"
    elif case == "normalized":
        summaries[0][8] = "0"
    else:
        summaries[0][3] = "1.0"
    with pytest.raises(native.NativeCountFormatError):
        _project(_payload([_row(small[2][0])], summaries=summaries), small)


@pytest.mark.parametrize(
    "case",
    [
        "exact_duplicate",
        "normalized_duplicate",
        "symbol_duplicate",
        "wrong_id",
        "wrong_symbol",
        "par_y",
    ],
)
def test_exact_identity_resolution_never_sums_renames_or_takes_first(small, case):
    gene = small[2][0]
    rows = [_row(gene)]
    if case == "exact_duplicate":
        rows.append(_row(gene))
    elif case == "normalized_duplicate":
        rows.append(_row(gene, identifier=gene.ensembl_gene_id + ".9"))
    elif case == "symbol_duplicate":
        rows.append(_row(_gene(9000, gene.source_symbol)))
    elif case == "wrong_id":
        rows = [_row(_gene(9000, gene.source_symbol))]
    elif case == "wrong_symbol":
        rows = [_row(gene, symbol="SYNTHETIC_STALE")]
    else:
        rows = [_row(gene, identifier=gene.ensembl_gene_id + ".4_PAR_Y")]
    if case.endswith("duplicate") and case != "symbol_duplicate":
        with pytest.raises(native.NativeCountFormatError):
            _project(_payload(rows), small)
    else:
        result = _project(_payload(rows), small)
        assert result.counts[0] == -1
        assert (
            result.states[0]
            == {"symbol_duplicate": 4, "wrong_id": 2, "wrong_symbol": 5, "par_y": 2}[case]
        )


@pytest.mark.parametrize(
    "identifier",
    ["ENST00000000001.1", "ENSG00000000001.0", "ENSG00000000001_extra", "ENSG1", "1-Mar"],
)
def test_invalid_ensembl_and_annotation_tokens_are_not_repaired(small, identifier):
    with pytest.raises(native.NativeCountFormatError):
        _project(_payload([_row(small[2][0], identifier=identifier)]), small)


def test_par_y_is_a_distinct_coordinate_and_cannot_fill_an_untagged_model_feature(small):
    gene = small[2][0]
    payload = _payload([_row(gene, identifier=gene.release_gene_id + "_PAR_Y")])
    result = _project(payload, small)
    assert result.counts[0] == -1 and result.states[0] == 2
    assert result.receipt.par_y_gene_rows == 1


@pytest.mark.parametrize("symbol", ["MTRNR2L1", "MTRNR2L12", "MTRNR2L8", "IQCD", "ALOX12-AS1"])
def test_historical_coordinates_are_observed_without_inventing_current_hgnc_links(complete, symbol):
    index = next(
        i for i, feature in enumerate(complete[1].features) if feature.source_symbol == symbol
    )
    feature = complete[1].features[index]
    result = _project(_payload([_row(feature, "19")]), complete)
    assert result.counts[index] == 19 and result.states[index] == 0
    if symbol.startswith("MTRNR2L"):
        assert feature.current_hgnc_ensembl_gene_id is None
    elif symbol == "ALOX12-AS1":
        assert feature.ensembl_gene_id == "ENSG00000215067" and feature.current_hgnc_symbol is None


def test_mir497hg_or_a_current_symbol_cannot_replace_the_original_source_feature(complete):
    index = next(
        i for i, feature in enumerate(complete[1].features) if feature.source_symbol == "ALOX12-AS1"
    )
    feature = complete[1].features[index]
    wrong_coordinate = _project(
        _payload([_row(feature, "999", identifier="ENSG00000267532.5", symbol="MIR497HG")]),
        complete,
    )
    assert wrong_coordinate.counts[index] == -1 and wrong_coordinate.states[index] == 2
    wrong_name = _project(_payload([_row(feature, "999", symbol="MIR497HG")]), complete)
    assert wrong_name.counts[index] == -1 and wrong_name.states[index] == 5


@pytest.mark.parametrize("field", ["bytes", "md5", "sha256"])
def test_source_lock_checks_precede_decoding_or_projection(small, monkeypatch, field):
    payload = _payload([_row(small[2][0])])
    lock = _lock(payload)
    lock = replace(
        lock,
        **{field: len(payload) + 1 if field == "bytes" else "0" * (32 if field == "md5" else 64)},
    )
    monkeypatch.setattr(
        native,
        "validate_model_axis",
        lambda *_args, **_kwargs: pytest.fail("source verification must precede axis/projection"),
    )
    with pytest.raises(SourceVerificationError):
        native.project_native_star_counts(payload, lock=lock, model_axis=small[1])


def test_bounds_and_untyped_inputs_reject_before_reading_rows(small):
    payload = b"x" * (native.MAX_ASSAY_BYTES + 1)
    with pytest.raises(SourceVerificationError):
        _project(payload, small)
    for value in (b"", bytearray(b"synthetic"), "synthetic"):
        with pytest.raises(SourceVerificationError):
            native.project_native_star_counts(value, lock=_lock(b"synthetic"), model_axis=small[1])
    with pytest.raises(SourceVerificationError):
        native.project_native_star_counts(b"synthetic", lock=object(), model_axis=small[1])
    too_many = (
        _payload([_row(small[2][0])]) + b"x\tx\tx\t0\t0\t0\t0\t0\t0\n" * native.MAX_ASSAY_ROWS
    )
    with pytest.raises(native.NativeCountFormatError):
        _project(too_many, small)
    row = _row(small[2][0], symbol="S" * 5000)
    with pytest.raises(native.NativeCountFormatError):
        _project(_payload([row]), small)
    with pytest.raises(native.NativeCountFormatError):
        _project(_payload([]), small)


def test_forged_axis_rejects_even_with_valid_exact_source_bytes(small):
    payload = _payload([_row(small[2][0])])
    forged = object.__new__(identity.ModelInputAxis)
    object.__setattr__(forged, "_features", tuple(reversed(small[1].features)))
    object.__setattr__(forged, "_receipt", small[1].receipt)
    with pytest.raises(identity.ModelAxisError):
        native.project_native_star_counts(payload, lock=_lock(payload), model_axis=forged)


@pytest.mark.parametrize(
    "mutation",
    [
        "short",
        "float",
        "state_shape",
        "state_dtype",
        "state_code",
        "positive_unavailable",
        "negative_observed",
        "zero_positive_state",
        "above_domain",
        "wrong_total",
    ],
)
def test_private_constructor_enforces_buffer_shape_dtype_state_and_receipt(small, mutation):
    result = _project(_payload([_row(small[2][0])]), small)
    counts, states = result.counts.copy(), result.states.copy()
    if mutation == "short":
        counts = counts[:1]
    elif mutation == "float":
        counts = counts.astype(np.float64)
    elif mutation == "state_shape":
        states = states[:1]
    elif mutation == "state_dtype":
        states = states.astype(np.int64)
    elif mutation == "state_code":
        states[3] = 99
    elif mutation == "positive_unavailable":
        counts[3] = 100
    elif mutation == "negative_observed":
        counts[0] = -1
    elif mutation == "zero_positive_state":
        counts[0] = 0
    elif mutation == "above_domain":
        counts[0] = native.MAX_NATIVE_COUNT + 1
    else:
        counts[0] += 1
    with pytest.raises(native.NativeCountFormatError):
        native.NativeCountSample(counts, states, result.receipt)


def test_observed_zero_state_cannot_carry_a_positive_value(small):
    result = _project(_payload([_row(small[2][0])]), small)
    states = result.states.copy()
    states[0] = 1
    with pytest.raises(native.NativeCountFormatError):
        native.NativeCountSample(result.counts, states, result.receipt)


def test_private_constructor_copies_buffers_and_rejects_implicit_exports(small):
    result = _project(_payload([_row(small[2][0])]), small)
    counts, states = result.counts.copy(), result.states.copy()
    second = native.NativeCountSample(counts, states, result.receipt)
    counts[0], states[0] = 0, 1
    assert second.counts[0] == 7 and second.states[0] == 0
    assert second.binding_digest == result.binding_digest
    for array in (second.counts, second.states):
        with pytest.raises(ValueError):
            array.flags.writeable = True
    for action in (
        lambda: pickle.dumps(second),
        lambda: copy.deepcopy(second),
        lambda: json.dumps(second),
        lambda: asdict(second),
        second.__getstate__,
    ):
        with pytest.raises(TypeError):
            action()
    with pytest.raises(AttributeError):
        second._count_bytes = b""
    assert "ENSG" not in repr(second) and "sha256:" not in repr(second) and "[" not in repr(second)
    assert "counts" not in second.receipt.model_dump()


def test_source_mutation_after_snapshot_cannot_change_payload_binding(small, monkeypatch):
    original = _project(_payload([_row(small[2][0])]), small)
    counts, states = original.counts.copy(), original.states.copy()
    contiguous = native.np.ascontiguousarray

    def snapshot(values):
        answer = contiguous(values)
        if values is states:
            counts[0] = 0
        return answer

    monkeypatch.setattr(native.np, "ascontiguousarray", snapshot)
    copied = native.NativeCountSample(counts, states, original.receipt)
    assert counts[0] == 0
    assert copied.counts[0] == 7 and copied.states[0] == 0
    assert copied.binding_digest == original.binding_digest


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("count_ready", True),
        ("recognized_model_gene_count", 2),
        ("recognized_raw_count_sum", 0),
        ("coverage_fraction", 1.0),
        ("coverage_supported", True),
        ("data_rows", 10),
        ("observed_zero_gene_rows", 100),
        ("duplicate_gene_symbol_groups", 1),
        ("state_counts", (0, 0, 0, 0, 0, 0)),
    ],
)
def test_aggregate_receipt_cannot_relabel_coverage_or_inventory(small, field, value):
    result = _project(_payload([_row(small[2][0])]), small)
    document = result.receipt.model_dump(mode="python")
    document[field] = value
    with pytest.raises(ValidationError):
        native.NativeCountReceipt.model_validate(document)


def test_revalidated_receipt_prevents_model_construct_bypass(small):
    result = _project(_payload([_row(small[2][0])]), small)
    values = result.receipt.model_dump(mode="python")
    values["count_ready"] = True
    forged = native.NativeCountReceipt.model_construct(**values)
    with pytest.raises(native.NativeCountFormatError):
        native.NativeCountSample(result.counts, result.states, forged)
    with pytest.raises(native.NativeCountFormatError):
        native.NativeCountSample(result.counts, result.states, {})


def test_sanitized_errors_never_echo_private_row_or_input_identifier(small):
    row = _row(small[2][0], identifier="PRIVATE_SPECIMEN_IDENTIFIER")
    with pytest.raises(native.NativeCountFormatError) as captured:
        _project(_payload([row]), small)
    assert "PRIVATE_SPECIMEN_IDENTIFIER" not in str(captured.value)


def test_no_preprocessing_or_model_execution_is_available_in_projection(small, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("model call or preprocessing attempted")

    for module, name in (
        (catalog, "gbm_rna_purity_catalog"),
        (engine, "_input_vector"),
        (engine, "_forward"),
        (service, "analyze_gbm_rna_purity"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    assert _project(_payload([_row(small[2][0])]), small).receipt.inference_executed is False


def test_unversioned_coordinate_is_accepted_but_wrong_release_version_is_rejected(small):
    feature = small[2][0]
    result = _project(_payload([_row(feature, identifier=feature.ensembl_gene_id)]), small)
    assert result.counts[0] == 7 and result.states[0] == 0
    assert result.receipt.versioned_gene_rows == 0
    with pytest.raises(native.NativeCountFormatError, match="annotation version"):
        _project(_payload([_row(feature, identifier=feature.ensembl_gene_id + ".999")]), small)


@pytest.mark.parametrize("field", ["bytes", "md5", "sha256"])
def test_corrupted_source_lock_is_revalidated_before_decoding(small, field):
    payload = _payload([_row(small[2][0])])
    lock = _lock(payload)
    object.__setattr__(lock, field, object())
    with pytest.raises(SourceVerificationError, match="source lock is invalid"):
        native.project_native_star_counts(payload, lock=lock, model_axis=small[1])
