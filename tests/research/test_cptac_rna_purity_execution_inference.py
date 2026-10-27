"""Synthetic source/processing gates and exact legacy-model bridge oracles."""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass, replace
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from glio_proteogen.research.cptac_gbm_rna_purity_admission.context import ContextState
from glio_proteogen.research.cptac_gbm_rna_purity_admission.identity import _released_metadata
from glio_proteogen.research.cptac_gbm_rna_purity_execution import inference
from glio_proteogen.research.cptac_gbm_rna_purity_execution.contracts import (
    ExecutionError,
    ExecutionPolicy,
    canonical_bytes,
    checked_policy,
    digest,
    validate_digest,
)
from glio_proteogen.research.gbm_rna_purity import engine
from glio_proteogen.research.gbm_rna_purity.contracts import (
    REQUIRED_CONTEXT,
    ClippingState,
    GbmRnaPurityRequest,
    GbmRnaPurityResult,
    PuritySupport,
    RawGeneCount,
)

_D = "sha256:" + "1" * 64
_OTHER = "sha256:" + "2" * 64
_SUPPORTED = (ContextState.SOURCE_SUPPORTED,) * 7


@dataclass(frozen=True)
class _Feature:
    source_symbol: str
    source_length: float
    approved_symbol: str = "SYNTHETIC_APPROVED_REPLACEMENT"


@pytest.fixture(scope="module")
def axis():
    names, lengths = _released_metadata()
    return SimpleNamespace(
        features=tuple(_Feature(name, length) for name, length in zip(names, lengths, strict=True)),
        digest=digest({"synthetic_original_axis": [names, lengths]}),
    )


def _policy(*, limited=True):
    return ExecutionPolicy(
        research_use_only=True,
        caller_authorizes_missing_gene_zero_fill=True,
        allow_limited_support=limited,
    )


def _projection(axis, *, recognized=5829, positive=None):
    if positive is None:
        positive = recognized
    counts = np.full(5829, -1, dtype=np.int64)
    states = np.full(5829, 3, dtype=np.uint8)
    counts[:recognized] = 0
    states[:recognized] = 1
    counts[:positive] = np.arange(positive, dtype=np.int64) % 17 + 1
    states[:positive] = 0
    total = sum(int(value) for value in counts[counts >= 0])
    return SimpleNamespace(
        counts=counts,
        states=states,
        receipt=SimpleNamespace(
            model_axis_digest=axis.digest,
            recognized_model_gene_count=recognized,
            nonzero_model_gene_count=positive,
            observed_zero_model_gene_count=recognized - positive,
            recognized_raw_count_sum=total,
            count_ready=recognized >= 4664 and total > 0,
            coverage_supported=recognized >= 5771,
        ),
        binding_digest=digest({"synthetic_projection": [counts.tolist(), states.tolist()]}),
    )


def _qualification(projection, *, states=_SUPPORTED, policy=None, **changes):
    values = {
        "component_states": states,
        "protocol_digest": _D,
        "model_axis_digest": projection.receipt.model_axis_digest,
        "context_evidence_digest": _D,
        "context_source_set_digest": _D,
        "lineage_digest": _D,
        "policy": policy or _policy(),
    }
    values.update(changes)
    return inference.qualify_execution(projection, **values)


def _run(projection, axis, *, qualification=None, policy=None):
    policy = policy or _policy()
    return inference.run_qualified_projection(
        projection,
        model_axis=axis,
        qualification=qualification or _qualification(projection, policy=policy),
        policy=policy,
    )


def _forbid_runtime(monkeypatch):
    calls = []

    def forbidden(*_args, **_kwargs):
        calls.append(True)
        pytest.fail("request/profile/model must not be accessed for an abstention")

    monkeypatch.setattr(inference, "GbmRnaPurityRequest", forbidden)
    monkeypatch.setattr(inference, "algorithm_profile", forbidden)
    monkeypatch.setattr(inference, "analyze_gbm_rna_purity", forbidden)
    return calls


@pytest.mark.parametrize("component", range(7))
@pytest.mark.parametrize(
    ("state", "outcome"),
    [
        (ContextState.UNKNOWN, "context_unknown"),
        (ContextState.OUT_OF_SCOPE, "context_out_of_scope"),
        (ContextState.CONFLICTING, "context_conflicting"),
    ],
)
def test_each_source_and_processing_component_blocks_before_request_or_model(
    axis, monkeypatch, component, state, outcome
):
    projection = _projection(axis)
    states = list(_SUPPORTED)
    states[component] = state
    calls = _forbid_runtime(monkeypatch)
    summary = _run(projection, axis, qualification=_qualification(projection, states=tuple(states)))
    assert summary.outcome == outcome
    assert not summary.inference_executed
    assert summary.estimate is None and summary.support is None
    assert summary.legacy_result_digest is None and summary.request_digest is None
    assert summary.clipping_state is None and summary.explanation_reconstruction_error is None
    assert calls == []


def test_context_precedence_is_conflict_then_opposition_then_unknown(axis, monkeypatch):
    projection = _projection(axis, recognized=2)
    _forbid_runtime(monkeypatch)
    states = (
        ContextState.UNKNOWN,
        ContextState.OUT_OF_SCOPE,
        ContextState.CONFLICTING,
        *_SUPPORTED[:4],
    )
    assert (
        _run(projection, axis, qualification=_qualification(projection, states=states)).outcome
        == "context_conflicting"
    )
    states = (ContextState.UNKNOWN, ContextState.OUT_OF_SCOPE, *_SUPPORTED[:5])
    assert (
        _run(projection, axis, qualification=_qualification(projection, states=states)).outcome
        == "context_out_of_scope"
    )


@pytest.mark.parametrize(
    "case",
    [
        (0, 0, True, "below_coverage_gate"),
        (4663, 1, True, "below_coverage_gate"),
        (4663, 0, True, "below_coverage_gate"),
        (4664, 0, True, "zero_recognized_sum"),
        (5829, 0, True, "zero_recognized_sum"),
        (4664, 1, False, "limited_support_disallowed"),
        (5770, 1, False, "limited_support_disallowed"),
    ],
)
def test_native_count_and_policy_abstentions_do_not_construct_requests(axis, monkeypatch, case):
    recognized, positive, limited, outcome = case
    projection = _projection(axis, recognized=recognized, positive=positive)
    calls = _forbid_runtime(monkeypatch)
    assert _run(projection, axis, policy=_policy(limited=limited)).outcome == outcome
    assert calls == []


@pytest.mark.parametrize(
    ("recognized", "expected"),
    [
        (4664, PuritySupport.LIMITED),
        (5770, PuritySupport.LIMITED),
        (5771, PuritySupport.SUPPORTED),
        (5829, PuritySupport.SUPPORTED),
    ],
)
def test_exact_legacy_support_boundaries_with_synthetic_counts(axis, recognized, expected):
    summary = _run(_projection(axis, recognized=recognized), axis)
    assert summary.outcome == "estimated" and summary.inference_executed
    assert summary.support is expected
    assert 0 <= summary.estimate <= 1
    assert summary.clipping_state in tuple(ClippingState)
    assert summary.explanation_reconstruction_error >= 0
    assert validate_digest(summary.legacy_result_digest)
    assert validate_digest(summary.request_digest)
    assert validate_digest(summary.binding_digest)


def test_original_source_symbols_observed_zeros_and_omitted_missing_match_manual_legacy_request(
    axis, monkeypatch
):
    projection = _projection(axis, recognized=5771, positive=5770)
    qualification = _qualification(projection)
    requests = []

    def capture(request):
        requests.append(request)
        return engine.analyze_gbm_rna_purity(request)

    monkeypatch.setattr(inference, "analyze_gbm_rna_purity", capture)
    summary = _run(projection, axis, qualification=qualification)
    request = requests[0]
    source = json.loads(qualification._payload)
    provenance = digest(
        {
            key: source[key]
            for key in (
                "qualification_digest",
                "projection_digest",
                "projection_content_digest",
                "protocol_digest",
                "model_axis_digest",
                "context_evidence_digest",
                "context_source_set_digest",
                "lineage_digest",
                "policy_digest",
            )
        }
    )
    manual = GbmRnaPurityRequest(
        sample_id="source-qualified-purity",
        context=REQUIRED_CONTEXT,
        counts_provenance_digest=provenance,
        counts=tuple(
            RawGeneCount(
                gene_symbol=feature.source_symbol, raw_count=float(projection.counts[index])
            )
            for index, feature in enumerate(axis.features[:5771])
        ),
    )
    expected = engine.analyze_gbm_rna_purity(manual)
    assert request == manual
    assert len(request.counts) == 5771
    assert request.counts[-1].raw_count == 0.0
    assert all(row.gene_symbol != "SYNTHETIC_APPROVED_REPLACEMENT" for row in request.counts)
    assert summary.legacy_result_digest == expected.result_digest
    assert summary.estimate == expected.estimate.malignant_cell_fraction


def test_large_integer_counts_compare_to_unchanged_float64_reduction(axis):
    projection = _projection(axis)
    projection.counts[:] = 10**15
    projection.counts[0] -= 1
    projection.receipt.recognized_raw_count_sum = 5829 * 10**15 - 1
    # The integer sum is intentionally not exactly representable as float64.
    assert (
        int(float(projection.receipt.recognized_raw_count_sum))
        != projection.receipt.recognized_raw_count_sum
    )
    summary = _run(projection, axis)
    assert summary.outcome == "estimated"


@pytest.mark.parametrize(
    "field",
    [
        "research_use_only",
        "caller_authorizes_missing_gene_zero_fill",
        "individual_prediction_export",
        "allow_limited_support",
    ],
)
@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_policy_declarations_reject_scalar_aliases(field, value):
    values = _policy().model_dump(mode="python")
    values[field] = value
    with pytest.raises(ValidationError):
        ExecutionPolicy.model_validate(values)


@pytest.mark.parametrize("field", ["research_use_only", "caller_authorizes_missing_gene_zero_fill"])
def test_required_operational_authorization_cannot_be_false(field):
    values = _policy().model_dump(mode="python")
    values[field] = False
    with pytest.raises(ValidationError):
        ExecutionPolicy.model_validate(values)


def test_policy_is_closed_and_revalidated_against_python_bypass(axis, monkeypatch):
    values = _policy().model_dump(mode="python")
    with pytest.raises(ValidationError):
        ExecutionPolicy.model_validate({**values, "clinical_consent_inferred": True})
    with pytest.raises(ExecutionError):
        checked_policy(SimpleNamespace(**values))
    corrupted = ExecutionPolicy.model_construct(**{**values, "research_use_only": 1})
    _forbid_runtime(monkeypatch)
    with pytest.raises(ExecutionError):
        _run(_projection(axis), axis, policy=corrupted)


@pytest.mark.parametrize(
    "field",
    [
        "protocol_digest",
        "model_axis_digest",
        "context_evidence_digest",
        "context_source_set_digest",
        "lineage_digest",
    ],
)
@pytest.mark.parametrize("value", ["bad", None, 1])
def test_qualification_requires_exact_all_source_and_lineage_bindings(axis, field, value):
    with pytest.raises(ExecutionError):
        _qualification(_projection(axis), **{field: value})


@pytest.mark.parametrize(
    "states",
    [
        (),
        _SUPPORTED[:6],
        (*_SUPPORTED, ContextState.UNKNOWN),
        ("source_supported",) * 7,
        [*_SUPPORTED],
    ],
)
def test_component_partition_requires_exact_seven_typed_states(axis, states):
    with pytest.raises(ExecutionError):
        _qualification(_projection(axis), states=states)


def test_qualification_cannot_be_reused_for_different_projection_policy_or_axis(axis, monkeypatch):
    projection = _projection(axis)
    qualification = _qualification(projection)
    _forbid_runtime(monkeypatch)
    with pytest.raises(ExecutionError):
        _run(projection, axis, qualification=qualification, policy=_policy(limited=False))
    projection.binding_digest = _OTHER
    with pytest.raises(ExecutionError):
        _run(projection, axis, qualification=qualification)
    projection = _projection(axis)
    projection.counts[0] += 1
    projection.receipt.recognized_raw_count_sum += 1
    with pytest.raises(ExecutionError):
        _run(projection, axis, qualification=qualification)
    projection = _projection(axis)
    with pytest.raises(ExecutionError):
        _run(
            projection,
            SimpleNamespace(features=axis.features, digest=_OTHER),
            qualification=qualification,
        )


@pytest.mark.parametrize("attribute", ["source_symbol", "source_length"])
def test_changed_original_axis_metadata_blocks_even_ready_counts(axis, monkeypatch, attribute):
    projection = _projection(axis)
    features = list(axis.features)
    features[0] = replace(
        features[0],
        **{
            attribute: "SYNTHETIC_RENAMED"
            if attribute == "source_symbol"
            else features[0].source_length + 1
        },
    )
    changed = SimpleNamespace(features=tuple(features), digest=axis.digest)
    _forbid_runtime(monkeypatch)
    with pytest.raises(ExecutionError):
        _run(projection, changed)


@pytest.mark.parametrize(
    ("buffer", "transform"),
    [
        ("counts", lambda values: values.astype(np.float64)),
        ("counts", lambda values: values[:-1]),
        ("states", lambda values: values.astype(np.int64)),
    ],
)
def test_corrupted_projection_buffer_cannot_hide_behind_declared_digest(axis, buffer, transform):
    projection = _projection(axis, recognized=5771, positive=5770)
    setattr(projection, buffer, transform(getattr(projection, buffer)))
    with pytest.raises(ExecutionError):
        _qualification(projection)


@pytest.mark.parametrize(
    ("buffer", "index", "value"),
    [
        ("states", 0, 6),
        ("counts", 0, -1),
        ("counts", 0, 0),
        ("counts", 5770, 1),
        ("counts", 5771, 0),
        ("counts", 0, 10**15 + 1),
    ],
)
def test_corrupted_projection_values_cannot_hide_behind_declared_digest(axis, buffer, index, value):
    projection = _projection(axis, recognized=5771, positive=5770)
    getattr(projection, buffer)[index] = value
    with pytest.raises(ExecutionError):
        _qualification(projection)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recognized_model_gene_count", 5770),
        ("recognized_raw_count_sum", 1),
        ("count_ready", False),
        ("coverage_supported", False),
        ("recognized_model_gene_count", True),
    ],
)
def test_corrupted_projection_receipt_cannot_hide_behind_declared_digest(axis, field, value):
    projection = _projection(axis, recognized=5771, positive=5770)
    setattr(projection.receipt, field, value)
    with pytest.raises(ExecutionError):
        _qualification(projection)


@pytest.mark.parametrize(
    "field", ["profile_digest", "request_digest", "sample_id", "support", "coverage", "provenance"]
)
def test_service_output_substitution_is_rejected_even_after_valid_self_reseal(
    axis, monkeypatch, field
):
    projection = _projection(axis)

    def altered(request):
        result = engine.analyze_gbm_rna_purity(request)
        values = result.model_dump(mode="json")
        if field in {"profile_digest", "request_digest"}:
            values[field] = _OTHER
        elif field == "sample_id":
            values[field] = "synthetic-swapped-subject"
        elif field == "support":
            values[field] = "limited"
        elif field == "coverage":
            values[field]["nonzero_model_gene_count"] -= 1
        else:
            values[field]["weight_tensor_digest"] = _OTHER
        values.pop("result_digest")
        values["result_digest"] = digest(values)
        return GbmRnaPurityResult.model_validate_json(canonical_bytes(values))

    monkeypatch.setattr(inference, "analyze_gbm_rna_purity", altered)
    with pytest.raises(ExecutionError):
        _run(projection, axis)


def test_unexpected_service_failure_is_fatal_and_not_biological_abstention(axis, monkeypatch):
    def failure(_request):
        message = "synthetic service failure"
        raise RuntimeError(message)

    monkeypatch.setattr(inference, "analyze_gbm_rna_purity", failure)
    with pytest.raises(RuntimeError, match="synthetic service failure"):
        _run(_projection(axis), axis)


def test_private_qualification_and_summary_do_not_export_values(axis, monkeypatch):
    projection = _projection(axis)
    qualification = _qualification(projection, states=(ContextState.UNKNOWN, *_SUPPORTED[:6]))
    _forbid_runtime(monkeypatch)
    summary = _run(projection, axis, qualification=qualification)
    for value in (qualification, summary):
        assert "private" in repr(value)
        assert _D not in repr(value)
        with pytest.raises(TypeError):
            json.dumps(value)
        with pytest.raises(TypeError):
            pickle.dumps(value)
        with pytest.raises(TypeError):
            asdict(value)
        with pytest.raises(AttributeError):
            value._payload = b"changed"
        with pytest.raises(AttributeError):
            del value._payload
        with pytest.raises(TypeError):
            value.__getstate__()
    assert qualification.component_states[0] is ContextState.UNKNOWN
    assert validate_digest(qualification.binding_digest)


@pytest.mark.parametrize("payload", [b"{}", b"", "bad", b"{" * 9000])
def test_corrupted_qualification_storage_is_revalidated_at_use(axis, payload):
    projection = _projection(axis)
    qualification = _qualification(projection)
    object.__setattr__(qualification, "_payload", payload)
    with pytest.raises(ExecutionError):
        _run(projection, axis, qualification=qualification)


def test_context_changes_do_not_change_projection_snapshot(axis):
    projection = _projection(axis)
    initial = inference.projection_content_digest(projection)
    first = _qualification(projection)
    second = _qualification(projection, states=(ContextState.UNKNOWN, *_SUPPORTED[:6]))
    assert first.binding_digest != second.binding_digest
    assert inference.projection_content_digest(projection) == initial


def test_private_constructors_reject_unvalidated_documents_and_qualifications(axis):
    with pytest.raises(ExecutionError):
        inference.ExecutionQualification({})
    with pytest.raises(ExecutionError):
        inference.InferenceSummary({})
    projection = _projection(axis)
    with pytest.raises(ExecutionError):
        _run(projection, axis, qualification=SimpleNamespace(binding_digest=_D))
    with pytest.raises(ExecutionError):
        _run(projection, SimpleNamespace(digest=axis.digest))


@pytest.mark.parametrize("mutation", ["seal", "canonical"])
def test_valid_json_qualification_corruption_cannot_be_used(axis, mutation):
    projection = _projection(axis)
    qualification = _qualification(projection)
    values = json.loads(qualification._payload)
    if mutation == "seal":
        values["lineage_digest"] = _OTHER
        payload = canonical_bytes(values)
    else:
        payload = json.dumps(values, indent=2).encode()
    object.__setattr__(qualification, "_payload", payload)
    with pytest.raises(ExecutionError):
        _run(projection, axis, qualification=qualification)


@pytest.mark.parametrize("mutation", ["type", "bounds", "canonical", "json", "inconsistent"])
def test_private_summary_storage_and_outcome_are_revalidated(axis, monkeypatch, mutation):
    projection = _projection(axis)
    _forbid_runtime(monkeypatch)
    summary = _run(
        projection,
        axis,
        qualification=_qualification(projection, states=(ContextState.UNKNOWN, *_SUPPORTED[:6])),
    )
    values = json.loads(summary._payload)
    if mutation == "type":
        payload = "invalid storage"
    elif mutation == "bounds":
        payload = b"{}" * 3000
    elif mutation == "canonical":
        payload = json.dumps(values, indent=2).encode()
    elif mutation == "json":
        payload = b"invalid JSON"
    else:
        values["outcome"] = "estimated"
        values.pop("summary_digest")
        values["summary_digest"] = digest(values)
        payload = canonical_bytes(values)
    object.__setattr__(summary, "_payload", payload)
    with pytest.raises(ExecutionError):
        _ = summary.outcome


@pytest.mark.parametrize("mutation", ["type", "self_seal", "scalar_alias"])
def test_service_wrong_shape_corruption_and_literal_alias_are_sanitized(
    axis, monkeypatch, mutation
):
    def altered(request):
        if mutation == "type":
            return SimpleNamespace(synthetic_marker="not_a_result")
        result = engine.analyze_gbm_rna_purity(request)
        if mutation == "self_seal":
            return result.model_copy(update={"result_digest": _OTHER})
        # The valid original seal binds False; a bypassed literal integer alias
        # must be rejected even if validation normalizes it back to False.
        changed = result.diagnostics.model_copy(update={"dropout_active": 0})
        return result.model_copy(update={"diagnostics": changed})

    monkeypatch.setattr(inference, "analyze_gbm_rna_purity", altered)
    with pytest.raises(ExecutionError) as raised:
        _run(_projection(axis), axis)
    assert "not_a_result" not in str(raised.value)


def test_canonical_helpers_reject_nonfinite_and_digest_aliases():
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})
    assert canonical_bytes({"finite": 0}) == b'{"finite":0}'
    with pytest.raises(ValueError):
        canonical_bytes({"bad": float("nan")})
    for value in (None, 1, "sha256:" + "A" * 64, "sha256:short"):
        with pytest.raises(ExecutionError):
            validate_digest(value)
