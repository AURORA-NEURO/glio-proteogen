"""Synthetic historical handoff and genuine fixed-model numerical parity.

All STAR values are constructed here. The source seam explicitly permits the
existing fixture-marked qualification; it does not authenticate TCGA material.
Coordinate proofs use the existing synthetic axis helper. Only the fixed released
artifact is read/decoded for numerical service parity; no reference, clinical
corpus, real assay, saved outcome, or network input is used.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.research.cptac_gbm_rna_purity_admission import context as clinical
from glio_proteogen.research.cptac_gbm_rna_purity_execution import inference as old_inference
from glio_proteogen.research.gbm_rna_purity import catalog, contracts, service
from glio_proteogen.research.gbm_rna_purity.canonical import result_payload_digest, sha256_digest
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)
from glio_proteogen.research.tcga_gbm_historical_replication import contracts as historical
from glio_proteogen.research.tcga_gbm_historical_replication import inference as p
from glio_proteogen.research.tcga_gbm_historical_replication import projection, source
from tests.research.test_cptac_rna_purity_execution_identity import _synthetic_axis
from tests.research.test_cptac_rna_purity_execution_native_counts import _payload, _row
from tests.research.test_tcga_gbm_historical_replication_projection import (
    _permit_synthetic_kernel_fixture,
)
from tests.research.test_tcga_gbm_historical_replication_source import _fixture


def _forbidden(*_args, **_kwargs):
    pytest.fail("historical inference entered a forbidden source or clinical path")


@pytest.fixture(autouse=True)
def no_real_metadata_or_old_clinical_gate(monkeypatch):
    for module, name in (
        (source, "read_verified_source"),
        (old_inference, "qualify_execution"),
        (old_inference, "run_qualified_projection"),
        (clinical, "ReviewedContextRecord"),
        (contracts, "GbmRnaContextAttestation"),
    ):
        monkeypatch.setattr(module, name, _forbidden)


@pytest.fixture(scope="module")
def axis():
    # Real feature names/lengths are public fixed artifact metadata. The source
    # coordinates/proof are explicitly replaced; no GTF/HGNC payload is opened.
    with pytest.MonkeyPatch.context() as patch:
        yield _synthetic_axis(patch)[0]


def _policy(**changes):
    return p.HistoricalInferencePolicy(
        **{
            "historical_population_mapping": historical.POPULATION_BASIS,
            "unknown_specimen_timing_and_exposure_accepted": True,
            "research_use_only": True,
            "caller_authorizes_missing_gene_zero_fill": True,
            **changes,
        }
    )


def _permit(monkeypatch, fixture):
    calls = _permit_synthetic_kernel_fixture(monkeypatch, fixture)
    monkeypatch.setattr(p, "verify_rna_payload", projection.verify_rna_payload)
    return calls


def _data(axis, recognized=5829, *, positive=True):
    # One positive coordinate plus many observed zeros proves overlap is not
    # mistaken for a count of strictly positive genes.
    return _payload(
        [
            _row(gene, "7" if positive and i == 0 else "0")
            for i, gene in enumerate(axis.features[:recognized])
        ]
    )


def _run(payload, qualification, axis, **changes):
    return p.estimate_historical_star_counts(
        payload, qualification=qualification, model_axis=axis, policy=_policy(**changes)
    )


@pytest.fixture(scope="module")
def numerical(axis):
    """One genuine default service call, always under the labelled fixture seam."""
    payload = _data(axis)
    fixture = _fixture(payload)
    calls, requests = [], []
    with pytest.MonkeyPatch.context() as patch:
        _permit(patch, fixture)

        def record(request, **kwargs):
            requests.append(request)
            legacy = service.analyze_gbm_rna_purity(request, **kwargs)
            calls.append(legacy)
            return legacy

        patch.setattr(p, "analyze_gbm_rna_purity", record)
        result = _run(payload, fixture.qualification, axis)
    assert len(calls) == len(requests) == 1
    return SimpleNamespace(
        payload=payload, fixture=fixture, result=result, legacy=calls[0], request=requests[0]
    )


def _controlled(monkeypatch, numerical):
    _permit(monkeypatch, numerical.fixture)
    calls = []

    def saved_numerical_oracle(request, **_kwargs):
        assert request == numerical.request
        calls.append(True)
        return numerical.legacy

    monkeypatch.setattr(p, "analyze_gbm_rna_purity", saved_numerical_oracle)
    return calls


def _reseal(legacy, mutate):
    data = legacy.model_dump(mode="python")
    mutate(data)
    data["result_digest"] = result_payload_digest(data)
    return contracts.GbmRnaPurityResult.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "historical_population_mapping",
        "unknown_specimen_timing_and_exposure_accepted",
        "research_use_only",
        "caller_authorizes_missing_gene_zero_fill",
    ],
)
def test_mapping_and_operational_permissions_are_explicit(field):
    values = _policy().model_dump(mode="python")
    values.pop(field)
    with pytest.raises(ValidationError):
        p.HistoricalInferencePolicy.model_validate(values)


@pytest.mark.parametrize(
    "field",
    [
        "unknown_specimen_timing_and_exposure_accepted",
        "research_use_only",
        "caller_authorizes_missing_gene_zero_fill",
        "allow_limited_support",
    ],
)
@pytest.mark.parametrize("alias", [0, 1, "true", None])
def test_policy_rejects_boolean_aliases(field, alias):
    with pytest.raises(ValidationError):
        _policy(**{field: alias})


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown_specimen_timing_and_exposure_accepted": False},
        {"research_use_only": False},
        {"caller_authorizes_missing_gene_zero_fill": False},
        {"historical_population_mapping": "explicit_integrated_diagnosis"},
        {"clinically_eligible": True},
    ],
)
def test_policy_cannot_relabel_history_as_clinical_or_authorize_missingness_implicitly(changes):
    with pytest.raises(ValidationError):
        _policy(**changes)
    assert _policy().allow_limited_support is False


def test_genuine_fixture_capability_is_rejected_before_projection_or_model(monkeypatch, axis):
    payload = _data(axis)
    fixture = _fixture(payload)
    monkeypatch.setattr(p, "project_historical_star_counts", _forbidden)
    monkeypatch.setattr(p, "algorithm_profile", _forbidden)
    monkeypatch.setattr(p, "analyze_gbm_rna_purity", _forbidden)
    monkeypatch.setattr(catalog, "_resource_bytes", _forbidden)
    with pytest.raises(p.HistoricalInferenceError) as caught:
        _run(payload, fixture.qualification, axis)
    assert caught.value.__context__ is None
    assert fixture.target_file_id not in str(caught.value)


@pytest.mark.parametrize("bad", [None, True, {}, b"{}"])
def test_saved_receipt_or_boolean_cannot_replace_source_capability(monkeypatch, axis, bad):
    monkeypatch.setattr(p, "verify_rna_payload", _forbidden)
    with pytest.raises(p.HistoricalInferenceError):
        _run(b"SYNTHETIC", bad, axis)


@pytest.mark.parametrize("bad", [None, True, {}, b"{}"])
def test_wrong_or_bypassed_policy_fails_before_source(monkeypatch, axis, numerical, bad):
    monkeypatch.setattr(p, "verify_rna_payload", _forbidden)
    with pytest.raises(p.HistoricalInferenceError):
        p.estimate_historical_star_counts(
            numerical.payload,
            qualification=numerical.fixture.qualification,
            model_axis=axis,
            policy=bad,
        )


def test_bypassed_or_mutated_policy_fails_before_source(monkeypatch, axis, numerical):
    policy = _policy()
    object.__setattr__(policy, "research_use_only", 1)
    monkeypatch.setattr(p, "verify_rna_payload", _forbidden)
    with pytest.raises(p.HistoricalInferenceError):
        p.estimate_historical_star_counts(
            numerical.payload,
            qualification=numerical.fixture.qualification,
            model_axis=axis,
            policy=policy,
        )


def test_genuine_fixed_service_scalar_parity_and_historical_result(numerical):
    result, legacy, request = numerical.result, numerical.legacy, numerical.request
    assert result.estimate == legacy.estimate.malignant_cell_fraction
    assert result.raw_unclipped_output == legacy.estimate.raw_unclipped_output
    assert result.clipping_state is legacy.estimate.clipping_state
    assert result.feature_coverage_support is contracts.PuritySupport.SUPPORTED
    assert result.outcome == "estimated"
    assert request.context == contracts.REQUIRED_CONTEXT
    assert len(request.counts) == 5829
    assert sum(item.raw_count > 0 for item in request.counts) == 1
    assert result.receipt.population.source_evidence_kind == "synthetic_fixture"
    assert result.receipt.population.specimen_treatment_exposure == "unknown"
    assert result.receipt.population.specimen_collection_timepoint == "unknown"
    assert result.receipt.population.inference_executed is False
    assert result.receipt.model_executed is True
    assert not isinstance(result, contracts.GbmRnaPurityResult)


@pytest.mark.parametrize(
    ("recognized", "limited", "expected"),
    [
        (4663, False, "below_coverage_gate"),
        (4663, True, "below_coverage_gate"),
        (4664, False, "limited_support_disallowed"),
        (4664, True, "estimated"),
        (5770, False, "limited_support_disallowed"),
        (5770, True, "estimated"),
        (5771, False, "estimated"),
        (5771, True, "estimated"),
    ],
)
def test_recognized_including_zeros_exact_gates_and_missingness(
    monkeypatch, axis, recognized, limited, expected
):
    payload = _data(axis, recognized)
    fixture = _fixture(payload)
    _permit(monkeypatch, fixture)
    requests = []
    if expected != "estimated":
        monkeypatch.setattr(p, "algorithm_profile", _forbidden)
        monkeypatch.setattr(p, "analyze_gbm_rna_purity", _forbidden)
    else:

        def record(request, **kwargs):
            requests.append(request)
            return service.analyze_gbm_rna_purity(request, **kwargs)

        monkeypatch.setattr(p, "analyze_gbm_rna_purity", record)
    result = _run(payload, fixture.qualification, axis, allow_limited_support=limited)
    assert result.outcome == expected
    assert result.receipt.recognized_model_gene_count == recognized
    assert result.receipt.observed_zero_model_gene_count == recognized - 1
    assert result.receipt.unavailable_model_gene_count == 5829 - recognized
    if expected == "estimated":
        assert len(requests) == 1
        assert len(requests[0].counts) == recognized
        assert {row.gene_symbol for row in requests[0].counts} == {
            gene.source_symbol for gene in axis.features[:recognized]
        }
        assert sum(row.raw_count == 0 for row in requests[0].counts) == recognized - 1
        assert result.feature_coverage_support is (
            contracts.PuritySupport.SUPPORTED
            if recognized >= 5771
            else contracts.PuritySupport.LIMITED
        )
    else:
        assert result.estimate is result.raw_unclipped_output is result.clipping_state is None
        assert result.receipt.model_executed is False


def test_zero_mass_abstains_before_profile_or_service(monkeypatch, axis):
    payload = _data(axis, positive=False)
    fixture = _fixture(payload)
    _permit(monkeypatch, fixture)
    monkeypatch.setattr(p, "algorithm_profile", _forbidden)
    monkeypatch.setattr(p, "analyze_gbm_rna_purity", _forbidden)
    result = _run(payload, fixture.qualification, axis)
    assert result.outcome == "zero_recognized_sum"
    assert result.receipt.recognized_model_gene_count == 5829
    assert result.receipt.nonzero_model_gene_count == 0


@pytest.mark.parametrize("failure_call", [1, 2, 3, 4, 5])
def test_source_failure_before_or_after_real_handoff_discards_outcome(
    monkeypatch, axis, numerical, failure_call
):
    calls = _controlled(monkeypatch, numerical)
    verify = p.verify_rna_payload
    attempts = []

    def checked(payload, **kwargs):
        attempts.append(True)
        if len(attempts) == failure_call:
            raise historical.HistoricalSourceError("SYNTHETIC_PRIVATE_FAILURE")
        return verify(payload, **kwargs)

    monkeypatch.setattr(p, "verify_rna_payload", checked)
    with pytest.raises(p.HistoricalInferenceError) as caught:
        _run(numerical.payload, numerical.fixture.qualification, axis)
    assert len(calls) == int(failure_call > 3)
    assert "SYNTHETIC_PRIVATE_FAILURE" not in str(caught.value)
    assert caught.value.__context__ is None


def test_wrong_payload_rejected_before_axis_or_model(monkeypatch, axis, numerical):
    _controlled(monkeypatch, numerical)
    monkeypatch.setattr(p, "validate_model_axis", _forbidden)
    with pytest.raises(p.HistoricalInferenceError):
        _run(numerical.payload + b"SYNTHETIC", numerical.fixture.qualification, axis)


@pytest.mark.parametrize("late", [False, True])
def test_corrupted_axis_cannot_proceed_or_survive_service(monkeypatch, axis, numerical, late):
    calls = _controlled(monkeypatch, numerical)
    original = axis._features
    altered = (original[1], original[0], *original[2:])
    try:
        if late:

            def corrupt(*_args, **_kwargs):
                calls.append(True)
                object.__setattr__(axis, "_features", altered)
                return numerical.legacy

            monkeypatch.setattr(p, "analyze_gbm_rna_purity", corrupt)
        else:
            object.__setattr__(axis, "_features", altered)
        with pytest.raises(p.HistoricalInferenceError):
            _run(numerical.payload, numerical.fixture.qualification, axis)
        assert len(calls) == int(late)
    finally:
        object.__setattr__(axis, "_features", original)


@pytest.mark.parametrize("when", ["projection", "service", "result"])
def test_policy_mutation_at_each_handoff_is_rejected(monkeypatch, axis, numerical, when):
    _controlled(monkeypatch, numerical)
    policy = _policy()
    seam = {
        "projection": "project_historical_star_counts",
        "service": "analyze_gbm_rna_purity",
        "result": "_build_result",
    }[when]
    original = getattr(p, seam)

    def mutate(*args, **kwargs):
        value = original(*args, **kwargs)
        object.__setattr__(policy, "allow_limited_support", True)
        return value

    monkeypatch.setattr(p, seam, mutate)
    with pytest.raises(p.HistoricalInferenceError):
        p.estimate_historical_star_counts(
            numerical.payload,
            qualification=numerical.fixture.qualification,
            model_axis=axis,
            policy=policy,
        )


@pytest.mark.parametrize("field", ["request_digest", "profile_digest", "sample_id"])
def test_self_resealed_result_with_wrong_request_profile_or_sample_is_rejected(
    monkeypatch, axis, numerical, field
):
    _controlled(monkeypatch, numerical)
    changed = _reseal(
        numerical.legacy,
        lambda data: data.__setitem__(
            field, "synthetic-other" if field == "sample_id" else "sha256:" + "0" * 64
        ),
    )
    monkeypatch.setattr(p, "analyze_gbm_rna_purity", lambda *_args, **_kwargs: changed)
    with pytest.raises(p.HistoricalInferenceError):
        _run(numerical.payload, numerical.fixture.qualification, axis)


@pytest.mark.parametrize(
    "field",
    [
        "converted_artifact_file_sha256",
        "converted_artifact_digest",
        "feature_order_digest",
        "weight_tensor_digest",
    ],
)
def test_self_resealed_wrong_model_provenance_rejected(monkeypatch, axis, numerical, field):
    _controlled(monkeypatch, numerical)
    changed = _reseal(
        numerical.legacy,
        lambda data: data["provenance"].__setitem__(field, "sha256:" + "0" * 64),
    )
    monkeypatch.setattr(p, "analyze_gbm_rna_purity", lambda *_args, **_kwargs: changed)
    with pytest.raises(p.HistoricalInferenceError):
        _run(numerical.payload, numerical.fixture.qualification, axis)


def test_self_resealed_wrong_sum_rejected(monkeypatch, axis, numerical):
    _controlled(monkeypatch, numerical)
    changed = _reseal(
        numerical.legacy, lambda data: data["coverage"].__setitem__("recognized_raw_count_sum", 8.0)
    )
    monkeypatch.setattr(p, "analyze_gbm_rna_purity", lambda *_args, **_kwargs: changed)
    with pytest.raises(p.HistoricalInferenceError):
        _run(numerical.payload, numerical.fixture.qualification, axis)


@pytest.mark.parametrize("kind", ["type", "digest", "numeric_alias", "missing_trace"])
def test_wrong_type_corruption_alias_or_missing_computation_is_rejected(
    monkeypatch, axis, numerical, kind
):
    _controlled(monkeypatch, numerical)
    if kind == "type":
        changed = numerical.legacy.model_dump(mode="json")
    elif kind == "digest":
        changed = numerical.legacy.model_copy(update={"result_digest": "sha256:" + "0" * 64})
    elif kind == "numeric_alias":
        changed = numerical.legacy.model_copy(deep=True)
        object.__setattr__(changed.diagnostics, "finite_inference", 1)
    else:
        changed = _reseal(
            numerical.legacy, lambda data: data["diagnostics"].__setitem__("hidden_trace", None)
        )
    monkeypatch.setattr(p, "analyze_gbm_rna_purity", lambda *_args, **_kwargs: changed)
    with pytest.raises(p.HistoricalInferenceError):
        _run(numerical.payload, numerical.fixture.qualification, axis)


@pytest.mark.parametrize("stage", ["before", "after"])
def test_changed_model_profile_fails_closed(monkeypatch, axis, numerical, stage):
    calls = _controlled(monkeypatch, numerical)
    real = p.algorithm_profile
    attempts = []

    def replaced():
        attempts.append(True)
        valid = real()
        if stage == "after" and len(attempts) == 1:
            return valid
        data = valid.model_dump(mode="json")
        data["converted_artifact_digest"] = "sha256:" + "0" * 64
        data.pop("profile_digest")
        return contracts.GbmRnaPurityProfile.model_validate_json(
            canonical_json_bytes({**data, "profile_digest": sha256_digest(data)})
        )

    monkeypatch.setattr(p, "algorithm_profile", replaced)
    with pytest.raises(p.HistoricalInferenceError):
        _run(numerical.payload, numerical.fixture.qualification, axis)
    assert len(calls) == int(stage == "after")


@pytest.mark.parametrize("error", [ValueError, RuntimeError, AssertionError])
def test_callee_errors_are_sanitized_without_payload_in_public_traceback_frame(
    monkeypatch, axis, numerical, error
):
    _controlled(monkeypatch, numerical)

    def failing(*_args, **_kwargs):
        raise error("SYNTHETIC_PRIVATE_FAILURE")

    monkeypatch.setattr(p, "analyze_gbm_rna_purity", failing)
    with pytest.raises(p.HistoricalInferenceError) as caught:
        _run(numerical.payload, numerical.fixture.qualification, axis)
    assert "SYNTHETIC_PRIVATE_FAILURE" not in str(caught.value)
    assert caught.value.__context__ is None
    tb = caught.value.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_name == "estimate_historical_star_counts":
            assert (
                not {"payload", "qualification", "model_axis", "policy"}
                & tb.tb_frame.f_locals.keys()
            )
        tb = tb.tb_next


@pytest.mark.parametrize(
    "error", [InferenceCancelledError, InferenceDeadlineExceededError, KeyboardInterrupt]
)
def test_cooperative_cancellation_and_interrupts_propagate(monkeypatch, axis, numerical, error):
    _controlled(monkeypatch, numerical)

    def cancel(*_args, **_kwargs):
        raise error("SYNTHETIC_CANCEL")

    monkeypatch.setattr(p, "analyze_gbm_rna_purity", cancel)
    with pytest.raises(error):
        _run(numerical.payload, numerical.fixture.qualification, axis)


def test_already_cancelled_before_any_source_access(monkeypatch, axis, numerical):
    cancellation = CancellationContext()
    cancellation.cancel()
    monkeypatch.setattr(p, "verify_rna_payload", _forbidden)
    with pytest.raises(InferenceCancelledError):
        p.estimate_historical_star_counts(
            numerical.payload,
            qualification=numerical.fixture.qualification,
            model_axis=axis,
            policy=_policy(),
            cancellation=cancellation,
        )


def test_private_result_drops_legacy_vectors_and_denies_serialization(numerical):
    result = numerical.result
    assert repr(result) == "<HistoricalPurityResult private>"
    assert not hasattr(result, "__dict__")
    assert not hasattr(result, "counts")
    assert not hasattr(result, "diagnostics")
    for operation in (pickle.dumps, copy.copy, copy.deepcopy, json.dumps):
        with pytest.raises(TypeError):
            operation(result)
    with pytest.raises(AttributeError):
        result.estimate = 0.5
    with pytest.raises(AttributeError):
        del result._payload
    receipt = result.receipt.model_dump(mode="json")
    encoded = json.dumps(receipt)
    assert numerical.fixture.target_file_id not in encoded
    assert hashlib.sha256(numerical.payload).hexdigest() not in encoded
    assert numerical.request.counts[0].gene_symbol not in encoded

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(child) for child in value.values()))
        return set()

    assert not {"digest", "hidden_trace", "raw_count_sum", "estimate"} & keys(receipt)
    assert result.receipt is not result.receipt
    with pytest.raises(p.HistoricalInferenceError):
        p.HistoricalPurityResult()


@pytest.mark.parametrize(
    "field",
    [
        "clinical_qualification_granted",
        "formal_integrated_diagnosis_established",
        "who2021_reclassification_performed",
        "original_cptac_gate_changed",
        "independent_validation_established",
        "calibrated_uncertainty_available",
    ],
)
@pytest.mark.parametrize("alias", [True, 0])
def test_summary_cannot_claim_clinical_or_calibrated_support(numerical, field, alias):
    values = numerical.result.receipt.model_dump(mode="python")
    assert values[field] is False
    values[field] = alias
    with pytest.raises(ValidationError):
        p.HistoricalInferenceReceipt.model_validate(values)


@pytest.mark.parametrize("value", [False, 1])
def test_summary_research_only_flag_exact(numerical, value):
    values = numerical.result.receipt.model_dump(mode="python")
    values["research_use_only"] = value
    with pytest.raises(ValidationError):
        p.HistoricalInferenceReceipt.model_validate(values)


@pytest.mark.parametrize(
    ("clipping", "raw", "estimate", "accepted"),
    [
        ("none", 0.5, 0.5, True),
        ("lower_bound", -0.1, 0.0, True),
        ("lower_bound", 0.0, 0.0, True),
        ("upper_bound", 1.1, 1.0, True),
        ("upper_bound", 1.0, 1.0, True),
        ("none", 0.0, 0.0, True),
        ("none", 1.0, 1.0, True),
        ("none", 0.5, 0.6, False),
        ("lower_bound", 0.1, 0.0, False),
        ("upper_bound", 0.9, 1.0, False),
        ("lower_bound", -0.1, 0.1, False),
        ("upper_bound", 1.1, 0.9, False),
    ],
)
def test_private_scalar_clipping_consistency_respects_quantized_boundaries(
    numerical, clipping, raw, estimate, accepted
):
    document = json.loads(numerical.result._payload)
    document["receipt"]["clipping_state"] = clipping
    document["raw_unclipped_output"], document["estimate"] = raw, estimate
    copied = object.__new__(p.HistoricalPurityResult)
    object.__setattr__(copied, "_payload", canonical_json_bytes(document))
    if accepted:
        assert copied.estimate == estimate
        assert copied.raw_unclipped_output == raw
    else:
        with pytest.raises(p.HistoricalInferenceError):
            _ = copied.receipt


@pytest.mark.parametrize("bad", [b"", b"{}", "SYNTHETIC", b" " * 8193])
def test_private_storage_forgery_or_corruption_is_rejected(bad):
    copied = object.__new__(p.HistoricalPurityResult)
    object.__setattr__(copied, "_payload", bad)
    with pytest.raises(p.HistoricalInferenceError):
        _ = copied.estimate


def test_noncanonical_or_duplicate_key_storage_is_rejected(numerical):
    for payload in (
        json.dumps(json.loads(numerical.result._payload)).encode(),
        numerical.result._payload.replace(b'"estimate":', b'"estimate":0,"estimate":', 1),
    ):
        copied = object.__new__(p.HistoricalPurityResult)
        object.__setattr__(copied, "_payload", payload)
        with pytest.raises(p.HistoricalInferenceError):
            _ = copied.receipt
