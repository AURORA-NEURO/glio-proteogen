"""Synthetic native-projection parity and the separate source authority boundary.

Positive numerical tests explicitly permit a fixture-marked private source
capability at the verification seam. They do not authenticate a synthetic book
as the published TCGA supplement. Public rejection tests retain the genuine
source verifier and every production source pin. No source assay or model
artifact is read; released feature metadata is also replaced before axis setup.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
from dataclasses import replace

import numpy as np
import pytest

from glio_proteogen.research.cptac_gbm_external_admission.contracts import SourceLock
from glio_proteogen.research.cptac_gbm_rna_purity_admission import identity as old_identity
from glio_proteogen.research.cptac_gbm_rna_purity_execution import identity, inference
from glio_proteogen.research.cptac_gbm_rna_purity_execution import native_counts as native
from glio_proteogen.research.gbm_rna_purity import catalog, contracts, engine, service
from glio_proteogen.research.tcga_gbm_historical_replication import contracts as historical
from glio_proteogen.research.tcga_gbm_historical_replication import projection as p
from tests.research.test_cptac_rna_purity_execution_identity import _synthetic_axis
from tests.research.test_cptac_rna_purity_execution_native_counts import (
    _gene,
    _payload,
    _row,
)
from tests.research.test_tcga_gbm_historical_replication_source import _fixture


def _forbidden(*_args, **_kwargs):
    pytest.fail("historical count projection must not enter a model or old clinical authority lane")


@pytest.fixture(autouse=True)
def no_model_or_old_qualification(monkeypatch):
    for module, name in (
        (catalog, "_resource_bytes"),
        (catalog, "gbm_rna_purity_catalog"),
        (engine, "analyze_gbm_rna_purity"),
        (engine, "_forward"),
        (service, "analyze_gbm_rna_purity"),
        (service, "verify_gbm_rna_purity_replay"),
        (inference, "qualify_execution"),
        (inference, "run_qualified_projection"),
        (contracts, "GbmRnaPurityRequest"),
        (contracts, "GbmRnaContextAttestation"),
        (old_identity, "_read_released_metadata"),
    ):
        monkeypatch.setattr(module, name, _forbidden)


@pytest.fixture
def axis(monkeypatch):
    # The old helper constructs the genuine private axis class after replacing
    # its fixed coordinate proof. Replacing metadata first prevents any read of
    # the artifact that also contains opaque model parameters.
    special = ("ALOX12-AS1", "IQCD", "MTRNR2L1", "MTRNR2L12", "MTRNR2L8")
    names = tuple(f"SYNTHETIC_GENE_{index}" for index in range(5824)) + special
    lengths = (1000.0,) * len(names)
    monkeypatch.setattr(identity, "_released_metadata", lambda: (names, lengths))
    return _synthetic_axis(monkeypatch)[0]


def _lock(payload):
    return SourceLock(
        len(payload),
        hashlib.md5(payload, usedforsecurity=False).hexdigest(),
        hashlib.sha256(payload).hexdigest(),
    )


def _permit_synthetic_kernel_fixture(monkeypatch, fixture):
    """Controlled source-verification seam, never production authentication."""
    calls = []

    def verify(payload, *, qualification):
        calls.append(True)
        assert type(qualification) is historical.HistoricalPopulationQualification
        assert qualification is fixture.qualification
        assert qualification.receipt.source_evidence_kind == "synthetic_fixture"
        if type(payload) is not bytes or _lock(payload) != fixture.rna_lock:
            raise historical.HistoricalSourceError("SYNTHETIC_ACQUISITION_MISMATCH")
        return fixture.rna_lock

    monkeypatch.setattr(p, "verify_rna_payload", verify)
    return calls


def _project(monkeypatch, axis, payload):
    fixture = _fixture(payload)
    calls = _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    result = p.project_historical_star_counts(
        payload, qualification=fixture.qualification, model_axis=axis
    )
    return result, fixture, calls


def test_six_state_projection_matches_unchanged_native_and_preserves_zero_unavailability(
    monkeypatch, axis
):
    genes = axis.features
    payload = _payload(
        [
            _row(genes[0], "7"),
            _row(genes[1], "0"),
            _row(genes[3], symbol="SYNTHETIC_WRONG_SYMBOL"),
            _row(genes[4]),
            _row(_gene(9000, genes[4].source_symbol)),
        ]
    )
    expected = native.project_native_star_counts(payload, lock=_lock(payload), model_axis=axis)
    result, _, calls = _project(monkeypatch, axis, payload)
    np.testing.assert_array_equal(result.counts, expected.counts)
    np.testing.assert_array_equal(result.states, expected.states)
    assert result.counts[:6].tolist() == [7, 0, -1, -1, -1, -1]
    assert result.states[:6].tolist() == [0, 1, 2, 5, 4, 2]
    assert result.receipt.state_counts == (1, 1, 5825, 0, 1, 1)
    assert result.receipt.recognized_model_gene_count == 2
    assert result.receipt.observed_zero_model_gene_count == 1
    assert result.receipt.coverage_fraction == 2 / 5829
    assert result.receipt.count_ready is result.receipt.coverage_supported is False
    assert calls == [True, True, True]


@pytest.mark.parametrize("positive", [False, True])
def test_full_axis_zero_and_positive_native_readiness_never_grants_inference(
    monkeypatch, axis, positive
):
    payload = _payload(
        [
            _row(gene, "1" if positive and index == 0 else "0")
            for index, gene in enumerate(axis.features)
        ]
    )
    result, _, _ = _project(monkeypatch, axis, payload)
    assert result.counts.shape == result.states.shape == (5829,)
    assert result.receipt.state_counts == (int(positive), 5829 - int(positive), 0, 0, 0, 0)
    assert result.receipt.coverage_fraction == 1.0
    assert result.receipt.count_ready is positive
    assert result.receipt.coverage_supported is True
    assert result.receipt.inference_executed is False
    assert result.receipt.clinical_qualification_granted is False
    assert result.receipt.model_invocation_permitted is False
    assert result.receipt.population.formal_integrated_diagnosis_established is False
    assert result.receipt.population.specimen_collection_timepoint == "unknown"
    assert result.receipt.population.specimen_treatment_exposure == "unknown"


@pytest.mark.parametrize(
    ("recognized", "ready", "supported"),
    [(4663, False, False), (4664, True, False), (5770, True, False), (5771, True, True)],
)
def test_original_eighty_and_ninety_nine_percent_thresholds_are_not_relaxed(
    monkeypatch, axis, recognized, ready, supported
):
    payload = _payload([_row(gene) for gene in axis.features[:recognized]])
    result, _, _ = _project(monkeypatch, axis, payload)
    assert result.receipt.recognized_model_gene_count == recognized
    assert result.receipt.count_ready is ready
    assert result.receipt.coverage_supported is supported
    assert result.receipt.model_invocation_permitted is False


def test_public_source_boundary_rejects_the_genuine_but_fixture_marked_capability_before_parse(
    monkeypatch, axis
):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    monkeypatch.setattr(p, "project_native_star_counts", _forbidden)
    with pytest.raises(p.HistoricalProjectionError) as caught:
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )
    assert caught.value.__context__ is None
    assert fixture.target_file_id not in str(caught.value)


@pytest.mark.parametrize("kind", ["boolean", "receipt", "json", "object", "uninitialized"])
def test_receipts_or_caller_booleans_cannot_supply_source_authority(monkeypatch, axis, kind):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    values = {
        "boolean": True,
        "receipt": fixture.qualification.receipt,
        "json": fixture.qualification.receipt.model_dump(mode="json"),
        "object": object(),
        "uninitialized": object.__new__(historical.HistoricalPopulationQualification),
    }
    monkeypatch.setattr(p, "project_native_star_counts", _forbidden)
    with pytest.raises(p.HistoricalProjectionError) as caught:
        p.project_historical_star_counts(payload, qualification=values[kind], model_axis=axis)
    assert caught.value.__context__ is None


@pytest.mark.parametrize("kind", ["size", "md5", "reviewed_sha256"])
def test_reviewed_source_lock_mismatch_stops_before_native_parse(monkeypatch, axis, kind):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    changes = {
        "size": {"bytes": fixture.rna_lock.bytes + 1},
        "md5": {"md5": "0" * 32},
        "reviewed_sha256": {"sha256": "0" * 64},
    }
    fixture.rna_lock = replace(fixture.rna_lock, **changes[kind])
    _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    monkeypatch.setattr(p, "project_native_star_counts", _forbidden)
    with pytest.raises(p.HistoricalProjectionError):
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )


@pytest.mark.parametrize("value", [None, "not bytes", bytearray(b"x"), memoryview(b"x")])
def test_nonbyte_payloads_do_not_reach_native_parse(monkeypatch, axis, value):
    fixture = _fixture(b"synthetic source authority only")
    _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    monkeypatch.setattr(p, "project_native_star_counts", _forbidden)
    with pytest.raises(p.HistoricalProjectionError):
        p.project_historical_star_counts(
            value, qualification=fixture.qualification, model_axis=axis
        )


@pytest.mark.parametrize("kind", ["wrong_type", "uninitialized", "mutated_order"])
def test_wrong_or_stale_released_axis_rejects_before_payload_parse(monkeypatch, axis, kind):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    if kind == "wrong_type":
        offered = object()
    elif kind == "uninitialized":
        offered = object.__new__(identity.ModelInputAxis)
    else:
        offered = axis
        object.__setattr__(offered, "_features", tuple(reversed(axis.features)))
    monkeypatch.setattr(p, "project_native_star_counts", _forbidden)
    with pytest.raises(p.HistoricalProjectionError):
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=offered
        )


@pytest.mark.parametrize(
    "kind", ["negative", "fractional", "large", "strand", "summary", "version"]
)
def test_unchanged_full_native_schema_and_count_domain_remain_enforced(monkeypatch, axis, kind):
    row = _row(axis.features[0])
    if kind in ("negative", "fractional", "large"):
        row[3] = {"negative": "-1", "fractional": "1.5", "large": str(10**15 + 1)}[kind]
    elif kind == "strand":
        row[4] = "-1"
    elif kind == "version":
        row[0] = row[0].replace(".4", ".5")
    payload = _payload([row], summaries=[] if kind == "summary" else None)
    fixture = _fixture(payload)
    _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    with pytest.raises(p.HistoricalProjectionError) as caught:
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )
    assert caught.value.__context__ is None
    assert axis.features[0].source_symbol not in str(caught.value)


@pytest.mark.parametrize("phase", [2, 3])
@pytest.mark.parametrize("changed", ["rejected", "different_lock"])
def test_source_reverification_before_return_detects_controlled_boundary_changes(
    monkeypatch, axis, phase, changed
):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    calls = []

    def verify(_payload, *, qualification):
        assert qualification is fixture.qualification
        calls.append(True)
        if len(calls) == phase:
            if changed == "rejected":
                raise historical.HistoricalSourceError("private-source-sentinel")
            return replace(fixture.rna_lock, sha256="0" * 64)
        return fixture.rna_lock

    monkeypatch.setattr(p, "verify_rna_payload", verify)
    with pytest.raises(p.HistoricalProjectionError) as caught:
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )
    assert len(calls) == phase
    assert "private-source-sentinel" not in str(caught.value)
    assert caught.value.__context__ is None


def test_axis_mutation_by_a_controlled_parser_boundary_is_rechecked(monkeypatch, axis):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    original = p.project_native_star_counts

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        object.__setattr__(axis, "_features", tuple(reversed(axis.features)))
        return result

    monkeypatch.setattr(p, "project_native_star_counts", mutate)
    with pytest.raises(p.HistoricalProjectionError):
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )


def test_source_helper_must_return_the_exact_private_source_lock_type(monkeypatch, axis):
    fixture = _fixture(b"synthetic-not-parsed")
    monkeypatch.setattr(p, "verify_rna_payload", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(p, "project_native_star_counts", _forbidden)
    with pytest.raises(p.HistoricalProjectionError):
        p.project_historical_star_counts(
            fixture.rna_payload, qualification=fixture.qualification, model_axis=axis
        )


@pytest.mark.parametrize("kind", ["type", "source", "axis", "private_binding"])
def test_a_native_return_value_cannot_replace_the_reviewed_payload_or_axis(monkeypatch, axis, kind):
    payload = _payload([_row(axis.features[0])])
    fixture = _fixture(payload)
    _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    if kind == "type":
        supplied = object()
    else:
        source = _payload([_row(axis.features[0], "8")]) if kind == "source" else payload
        supplied = native.project_native_star_counts(source, lock=_lock(source), model_axis=axis)
        if kind == "axis":
            changed = supplied.receipt.model_copy(
                update={"model_axis_digest": "sha256:" + "0" * 64}
            )
            supplied = native.NativeCountSample(supplied.counts, supplied.states, changed)
        elif kind == "private_binding":
            object.__setattr__(supplied, "_binding_digest", "sha256:" + "0" * 64)
    monkeypatch.setattr(p, "project_native_star_counts", lambda *_args, **_kwargs: supplied)
    with pytest.raises(p.HistoricalProjectionError):
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )


def test_private_buffers_are_bytes_backed_immutable_and_cannot_be_implicitly_serialized(
    monkeypatch, axis
):
    payload = _payload([_row(axis.features[0]), _row(axis.features[1], "0")])
    result, _, _ = _project(monkeypatch, axis, payload)
    assert repr(result) == "<HistoricalCountProjection private>"
    assert not hasattr(result, "__dict__")
    for array in (result.counts, result.states):
        assert array.flags.writeable is False
        assert type(array.base) is bytes
        with pytest.raises(ValueError):
            array.setflags(write=True)
        with pytest.raises(ValueError):
            array[0] = 0
    with pytest.raises(AttributeError):
        result._count_bytes = b"changed"
    with pytest.raises(AttributeError):
        del result._state_bytes
    for operation in (pickle.dumps, copy.copy, copy.deepcopy, json.dumps):
        with pytest.raises(TypeError):
            operation(result)
    with pytest.raises(p.HistoricalProjectionError):
        p.HistoricalCountProjection()


def test_public_summary_has_no_request_values_ids_or_source_content_seals(monkeypatch, axis):
    payload = _payload([_row(axis.features[0], "987654321")])
    result, fixture, _ = _project(monkeypatch, axis, payload)
    doc = result.receipt.model_dump(mode="json")
    encoded = result.receipt.model_dump_json()
    assert p.HistoricalCountProjectionReceipt.model_validate_json(encoded) == result.receipt
    assert not set(doc) & {
        "counts",
        "states",
        "input_sha256",
        "input_bytes",
        "model_axis_digest",
        "binding_digest",
        "request_digest",
        "file_id",
        "case_id",
        "recognized_raw_count_sum",
    }
    assert "987654321" not in encoded and fixture.target_file_id not in encoded
    assert hashlib.sha256(payload).hexdigest() not in encoded
    assert doc["population"]["source_evidence_kind"] == "synthetic_fixture"
    with pytest.raises(ValueError):
        result.receipt.coverage_fraction = 1.0
    assert doc["clinical_qualification_granted"] is doc["model_invocation_permitted"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"recognized_model_gene_count": 2},
        {"nonzero_model_gene_count": 2},
        {"observed_zero_model_gene_count": 1},
        {"unavailable_model_gene_count": 0},
        {"coverage_fraction": 1.0},
        {"count_ready": True},
        {"coverage_supported": True},
        {"state_counts": (0, 0, 5828, 1, 0, 0)},
        {"state_counts": (1, 0, 5829, 0, 0, 0)},
        {"counts": [7]},
    ],
)
def test_closed_summary_cannot_forge_coverage_or_unavailable_state_conservation(
    monkeypatch, axis, change
):
    result, _, _ = _project(monkeypatch, axis, _payload([_row(axis.features[0])]))
    with pytest.raises(ValueError):
        p.HistoricalCountProjectionReceipt.model_validate(
            {**result.receipt.model_dump(mode="python"), **change}
        )


@pytest.mark.parametrize(
    "field",
    [
        "inference_executed",
        "clinical_qualification_granted",
        "original_cptac_gate_changed",
        "model_invocation_permitted",
    ],
)
@pytest.mark.parametrize("value", [True, 0, 1])
def test_summary_false_authority_flags_do_not_accept_numeric_aliases(
    monkeypatch, axis, field, value
):
    result, _, _ = _project(monkeypatch, axis, _payload([_row(axis.features[0])]))
    with pytest.raises(ValueError):
        p.HistoricalCountProjectionReceipt.model_validate(
            {**result.receipt.model_dump(mode="python"), field: value}
        )


@pytest.mark.parametrize("field", ["_count_bytes", "_state_bytes", "_receipt_bytes", "_integrity"])
def test_private_storage_corruption_is_detected_on_every_exposed_view(monkeypatch, axis, field):
    result, _, _ = _project(monkeypatch, axis, _payload([_row(axis.features[0])]))
    object.__setattr__(result, field, b"corrupted")
    for name in ("counts", "states", "receipt"):
        with pytest.raises(p.HistoricalProjectionError) as caught:
            getattr(result, name)
        assert caught.value.__context__ is None


def test_uninitialized_projection_has_no_accessible_measurement_views():
    result = object.__new__(p.HistoricalCountProjection)
    for name in ("counts", "states", "receipt"):
        with pytest.raises(p.HistoricalProjectionError):
            getattr(result, name)


@pytest.mark.parametrize(("state", "count"), [(6, 7), (0, 0), (0, 10**15 + 1), (1, 7), (2, 0)])
def test_resealing_private_storage_does_not_waive_the_native_state_domains(
    monkeypatch, axis, state, count
):
    result, _, _ = _project(monkeypatch, axis, _payload([_row(axis.features[0])]))
    counts, states = result.counts.copy(), result.states.copy()
    counts[0], states[0] = count, state
    count_bytes, state_bytes = counts.tobytes(), states.tobytes()
    object.__setattr__(result, "_count_bytes", count_bytes)
    object.__setattr__(result, "_state_bytes", state_bytes)
    object.__setattr__(
        result,
        "_integrity",
        p._storage_digest(count_bytes, state_bytes, result._receipt_bytes),
    )
    with pytest.raises(p.HistoricalProjectionError):
        _ = result.counts


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_process_cancellation_propagates_without_becoming_a_projection_rejection(
    monkeypatch, axis, exception
):
    fixture = _fixture(b"synthetic-not-parsed")

    def cancelled(*_args, **_kwargs):
        raise exception

    monkeypatch.setattr(p, "verify_rna_payload", cancelled)
    with pytest.raises(exception):
        p.project_historical_star_counts(
            fixture.rna_payload, qualification=fixture.qualification, model_axis=axis
        )


def test_sanitized_public_failure_frame_does_not_retain_payload_or_source_capability(
    monkeypatch, axis
):
    payload = b"SYNTHETIC_PRIVATE_PAYLOAD_SENTINEL"
    fixture = _fixture(payload)

    def denied(*_args, **_kwargs):
        raise historical.HistoricalSourceError("SYNTHETIC_PRIVATE_SOURCE_SENTINEL")

    monkeypatch.setattr(p, "verify_rna_payload", denied)
    with pytest.raises(p.HistoricalProjectionError) as caught:
        p.project_historical_star_counts(
            payload, qualification=fixture.qualification, model_axis=axis
        )
    assert caught.value.__context__ is None
    frames = []
    tb = caught.value.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_name == "project_historical_star_counts":
            frames.append(tb.tb_frame)
        tb = tb.tb_next
    assert len(frames) == 1
    assert not {"payload", "qualification", "model_axis"} & frames[0].f_locals.keys()
    assert "SYNTHETIC_PRIVATE" not in str(caught.value)
