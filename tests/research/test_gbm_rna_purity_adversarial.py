"""Adversarial contract, engine, catalog, and replay tests for GBMPurity."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from dataclasses import replace
from typing import Any, cast

import numpy as np
import pytest
from pydantic import ValidationError

import glio_proteogen.research.gbm_rna_purity.catalog as catalog_module
import glio_proteogen.research.gbm_rna_purity.contracts as contracts_module
import glio_proteogen.research.gbm_rna_purity.engine as engine_module
import glio_proteogen.research.gbm_rna_purity.profile as profile_module
from glio_proteogen.research.gbm_rna_purity.canonical import (
    canonical_json_bytes,
    canonical_request_digest,
    normalized_request,
    result_payload_digest,
    semantic_result_equal,
    sha256_digest,
)
from glio_proteogen.research.gbm_rna_purity.catalog import gbm_rna_purity_catalog
from glio_proteogen.research.gbm_rna_purity.contracts import (
    REQUIRED_CONTEXT,
    AttributionDirection,
    ClippingState,
    GbmRnaPurityProfile,
    GbmRnaPurityReplayVerificationRequest,
    GbmRnaPurityRequest,
    GbmRnaPurityResult,
    ModelCoverage,
    PuritySupport,
    RawGeneCount,
    UnverifiedGbmRnaPurityResult,
)
from glio_proteogen.research.gbm_rna_purity.demo import synthetic_demo_request
from glio_proteogen.research.gbm_rna_purity.errors import (
    GbmRnaPurityArtifactError,
    GbmRnaPurityInferenceError,
)
from glio_proteogen.research.gbm_rna_purity.profile import algorithm_profile
from glio_proteogen.research.gbm_rna_purity.service import (
    GbmRnaPurityService,
    analyze_gbm_rna_purity,
    verify_gbm_rna_purity_replay,
)
from glio_proteogen.research.proteogenomic_state.cancellation import (
    CancellationContext,
    InferenceCancelledError,
    InferenceDeadlineExceededError,
)


def _raw_result() -> tuple[GbmRnaPurityRequest, GbmRnaPurityResult, dict[str, Any]]:
    request = synthetic_demo_request()
    result = analyze_gbm_rna_purity(request)
    return request, result, result.model_dump(mode="python")


def _admit_document(
    monkeypatch: pytest.MonkeyPatch,
    document: object,
    *,
    bind_content: bool = True,
) -> bytes:
    if isinstance(document, dict) and bind_content:
        content = dict(document)
        content.pop("content_digest", None)
        document["content_digest"] = sha256_digest(content)
        monkeypatch.setattr(catalog_module, "EXPECTED_CONTENT_DIGEST", document["content_digest"])
    payload = canonical_json_bytes(document) + b"\n"
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_SHA256",
        "sha256:" + hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: payload)
    catalog_module.gbm_rna_purity_catalog.cache_clear()
    return payload


def _catalog_document() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(catalog_module._resource_bytes()))


def _expect_catalog_failure(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, Any],
    message: str,
) -> None:
    _admit_document(monkeypatch, document)
    try:
        with pytest.raises(GbmRnaPurityArtifactError, match=message):
            gbm_rna_purity_catalog()
    finally:
        gbm_rna_purity_catalog.cache_clear()


def test_contract_rejects_wrong_context_nonfinite_limits_and_duplicates() -> None:
    request = synthetic_demo_request()
    wrong_context = REQUIRED_CONTEXT.model_copy(update={"organism": "Mus musculus"})
    with pytest.raises(ValidationError, match=r"Homo sapiens|frozen GBMPurity scope"):
        GbmRnaPurityRequest.model_validate(
            {**request.model_dump(mode="python"), "context": wrong_context}
        )


def test_exact_context_validator_fails_closed_for_a_bypassed_nested_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    wrong_context = REQUIRED_CONTEXT.model_copy(update={"organism": "Mus musculus"})
    monkeypatch.setattr(contracts_module, "REQUIRED_CONTEXT", wrong_context)
    with pytest.raises(ValidationError, match="frozen GBMPurity scope"):
        GbmRnaPurityRequest.model_validate(request.model_dump(mode="python"), strict=True)

    with pytest.raises(ValidationError):
        RawGeneCount(gene_symbol="EGFR", raw_count=float("nan"))
    with pytest.raises(ValidationError):
        RawGeneCount(gene_symbol="EGFR", raw_count=float("inf"))
    with pytest.raises(ValidationError):
        RawGeneCount(gene_symbol="EGFR", raw_count=1.0e15 + 1.0)
    with pytest.raises(ValidationError, match="unique"):
        GbmRnaPurityRequest.model_validate(
            {
                **request.model_dump(mode="python"),
                "counts": (
                    {"gene_symbol": "EGFR", "raw_count": 1.0},
                    {"gene_symbol": "EGFR", "raw_count": 2.0},
                ),
            }
        )


@pytest.mark.parametrize("raw_count", [-1.0, float("nan"), float("inf"), 1.0e15 + 1.0])
def test_direct_call_validation_catches_bypassed_count_checks(raw_count: float) -> None:
    request = synthetic_demo_request().model_copy(
        update={"counts": (RawGeneCount.model_construct(gene_symbol="EGFR", raw_count=raw_count),)}
    )
    with pytest.raises(GbmRnaPurityInferenceError, match="exact GBMPurity request contract"):
        analyze_gbm_rna_purity(request)


def test_direct_call_validation_catches_bypassed_context_and_duplicates() -> None:
    request = synthetic_demo_request()
    wrong_context = REQUIRED_CONTEXT.model_copy(update={"organism": "Mus musculus"})
    with pytest.raises(GbmRnaPurityInferenceError, match="exact GBMPurity request contract"):
        analyze_gbm_rna_purity(request.model_copy(update={"context": wrong_context}))

    row = RawGeneCount(gene_symbol="EGFR", raw_count=1.0)
    with pytest.raises(GbmRnaPurityInferenceError, match="exact GBMPurity request contract"):
        analyze_gbm_rna_purity(request.model_copy(update={"counts": (row, row)}))


@pytest.mark.parametrize(
    "update",
    [
        {"schema_version": "wrong"},
        {"profile_id": "wrong"},
        {"sample_id": "not a valid identifier"},
        {"counts_provenance_digest": "sha256:wrong"},
        {"counts": ()},
        {
            "counts": (
                RawGeneCount.model_construct(gene_symbol="invalid symbol", raw_count=1.0),
            )
        },
        {
            "counts": (
                RawGeneCount.model_construct(gene_symbol="G" * 65, raw_count=1.0),
            )
        },
    ],
)
def test_direct_call_revalidates_every_request_identity_and_shape_field(
    update: dict[str, object],
) -> None:
    bypassed = synthetic_demo_request().model_copy(update=update)
    with pytest.raises(GbmRnaPurityInferenceError, match="exact GBMPurity request contract"):
        analyze_gbm_rna_purity(bypassed)


def test_direct_call_rejects_more_than_forty_thousand_rows() -> None:
    counts = tuple(
        RawGeneCount.model_construct(gene_symbol=f"G{index}", raw_count=1.0)
        for index in range(40_001)
    )
    bypassed = synthetic_demo_request().model_copy(update={"counts": counts})
    with pytest.raises(GbmRnaPurityInferenceError, match="exact GBMPurity request contract"):
        analyze_gbm_rna_purity(bypassed)


def test_direct_revalidation_returns_a_fresh_contract_checked_request() -> None:
    request = synthetic_demo_request()
    validated = engine_module._validate_direct_request(request)
    assert validated == request
    assert validated is not request


def test_coverage_contract_balances_every_declared_count() -> None:
    valid = {
        "supplied_gene_count": 1,
        "recognized_model_gene_count": 1,
        "missing_model_gene_count": 5_828,
        "ignored_non_model_gene_count": 0,
        "nonzero_model_gene_count": 1,
        "coverage_fraction": 1 / 5_829,
        "recognized_raw_count_sum": 2.0,
    }
    assert ModelCoverage.model_validate(valid).model_feature_count == 5_829
    for update, message in (
        ({"missing_model_gene_count": 5_827}, "recognized and missing"),
        ({"ignored_non_model_gene_count": 1}, "recognized and ignored"),
        ({"coverage_fraction": 0.5}, "coverage fraction"),
    ):
        with pytest.raises(ValidationError, match=message):
            ModelCoverage.model_validate({**valid, **update})


def test_result_contract_closes_support_payload_and_digest_combinations() -> None:
    _request, _result, document = _raw_result()
    cases = (
        ({"estimate": None}, "omit the purity estimate"),
        ({"explanation": None}, "omit the local explanation"),
        (
            {
                "support": PuritySupport.ABSTAINED,
                "estimate": None,
                "explanation": None,
                "abstention_reasons": (),
            },
            "require reasons",
        ),
        ({"abstention_reasons": ("forged reason",)}, "cannot carry abstention"),
    )
    for update, message in cases:
        with pytest.raises(ValidationError, match=message):
            UnverifiedGbmRnaPurityResult.model_validate({**document, **update})

    with pytest.raises(ValidationError, match="result_digest"):
        GbmRnaPurityResult.model_validate(
            {**document, "result_digest": "sha256:" + "0" * 64}
        )


def test_profile_contract_and_runtime_are_implementation_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = algorithm_profile()
    with pytest.raises(ValidationError, match="profile_digest"):
        GbmRnaPurityProfile.model_validate(
            {**profile.model_dump(mode="python"), "profile_digest": "sha256:" + "0" * 64}
        )

    monkeypatch.setattr(np, "__version__", "0.0.0")
    with pytest.raises(RuntimeError, match=r"NumPy 2\.5\.2"):
        profile_module.algorithm_profile()


def test_canonical_request_is_order_invariant_but_other_semantics_are_not() -> None:
    request = synthetic_demo_request()
    reversed_request = request.model_copy(update={"counts": tuple(reversed(request.counts))})
    renamed = request.model_copy(update={"sample_id": "synthetic-renamed"})

    assert normalized_request(request)["counts"][0]["gene_symbol"] == min(
        row.gene_symbol for row in request.counts
    )
    assert canonical_request_digest(request) == canonical_request_digest(reversed_request)
    assert canonical_request_digest(request) != canonical_request_digest(renamed)
    with pytest.raises(ValueError, match="Out of range float values"):
        canonical_json_bytes({"bad": float("nan")})


def test_coverage_abstention_preserves_missing_and_ignored_semantics() -> None:
    catalog = gbm_rna_purity_catalog()
    request = GbmRnaPurityRequest(
        sample_id="coverage.abstention",
        context=REQUIRED_CONTEXT,
        counts_provenance_digest=sha256_digest({"coverage": "adversarial"}),
        counts=(
            RawGeneCount(gene_symbol=catalog.feature_names[0], raw_count=0.0),
            RawGeneCount(gene_symbol="NOT_A_MODEL_GENE", raw_count=999.0),
        ),
    )
    result = analyze_gbm_rna_purity(request)

    assert result.support is PuritySupport.ABSTAINED
    assert result.coverage.recognized_model_gene_count == 1
    assert result.coverage.ignored_non_model_gene_count == 1
    assert result.coverage.recognized_raw_count_sum == 0.0
    assert result.abstention_reasons == (
        "recognized model-gene coverage is below the published 80% inference gate",
        "recognized model genes have zero total raw count",
    )
    assert result.diagnostics.hidden_trace is None


def test_forward_fails_closed_for_bad_denominator_preprocessing_and_network() -> None:
    catalog = gbm_rna_purity_catalog()
    zeros = np.zeros(len(catalog.feature_names), dtype=np.float64)
    with pytest.raises(GbmRnaPurityInferenceError, match="denominator"):
        engine_module._forward(zeros, catalog)

    signed = zeros.copy()
    signed[0] = -2.0
    signed[1] = 3.0
    with (
        np.errstate(invalid="ignore"),
        pytest.raises(GbmRnaPurityInferenceError, match="preprocessing"),
    ):
        engine_module._forward(signed, catalog)

    parameters = dict(catalog.parameters)
    bad_bias = np.asarray([np.nan], dtype=np.float32)
    bad_bias.flags.writeable = False
    parameters["out.bias"] = bad_bias
    poisoned = replace(catalog, parameters=parameters)
    positive = np.ones(len(catalog.feature_names), dtype=np.float64)
    with pytest.raises(GbmRnaPurityInferenceError, match="non-finite activations"):
        engine_module._forward(positive, poisoned)


def test_upper_clipping_and_zero_direction_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = synthetic_demo_request()
    catalog = gbm_rna_purity_catalog()
    values, _coverage, _support, _reasons = engine_module._input_vector(request, catalog)
    forward = engine_module._forward(values, catalog)
    monkeypatch.setattr(engine_module, "_forward", lambda *_args: replace(forward, raw_output=1.25))

    result = engine_module.analyze_gbm_rna_purity(request)
    assert result.estimate is not None
    assert result.estimate.malignant_cell_fraction == 1.0
    assert result.estimate.clipping_state is ClippingState.UPPER_BOUND
    assert result.explanation is not None
    assert result.explanation.clipping_changes_local_interpretation is True
    assert engine_module._direction(0.0) is AttributionDirection.ZERO_LOCAL_CONTRIBUTION
    assert engine_module._q(-1.0e-12) == 0.0


def test_reported_local_gradients_match_an_independent_active_relu_matrix_path() -> None:
    """Independently reconstruct the affine map selected by the demo's ReLU masks."""

    request = synthetic_demo_request()
    result = analyze_gbm_rna_purity(request)
    catalog = gbm_rna_purity_catalog()
    values, _coverage, _support, _reasons = engine_module._input_vector(request, catalog)
    forward = engine_module._forward(values, catalog)
    parameters = catalog.parameters

    first_mask = (forward.first_preactivation > 0.0).astype(np.float64)
    second_mask = (forward.second_preactivation > 0.0).astype(np.float64)
    output_path = parameters["out.weight"][0].astype(np.float64) * second_mask
    first_path = (output_path @ parameters["fc2.weight"].astype(np.float64)) * first_mask
    gradient = first_path @ parameters["fc1.weight"].astype(np.float64)
    transformed = forward.transformed.astype(np.float64)
    bias = (
        float(parameters["out.bias"][0])
        + float(output_path @ parameters["fc2.bias"].astype(np.float64))
        + float(first_path @ parameters["fc1.bias"].astype(np.float64))
    )
    independent_contribution_sum = float(gradient @ transformed)
    independent_reconstruction = independent_contribution_sum + bias

    assert result.explanation is not None
    assert result.estimate is not None
    assert independent_reconstruction == pytest.approx(forward.raw_output, abs=5.0e-7)
    assert result.explanation.all_gene_contribution_sum == pytest.approx(
        round(independent_contribution_sum, 8),
        abs=1.0e-8,
    )
    assert result.explanation.active_path_bias_contribution == pytest.approx(
        round(bias, 8),
        abs=1.0e-8,
    )
    assert result.explanation.reconstructed_raw_output == pytest.approx(
        round(independent_reconstruction, 8),
        abs=1.0e-8,
    )
    for attribution in result.explanation.top_gene_attributions:
        index = catalog.feature_index[attribution.gene_symbol]
        expected_gradient = round(float(gradient[index]), 8)
        expected_contribution = round(float(gradient[index] * transformed[index]), 8)
        assert attribution.local_gradient == pytest.approx(expected_gradient, abs=1.0e-8)
        assert attribution.raw_output_contribution == pytest.approx(
            expected_contribution,
            abs=1.0e-8,
        )


def test_cancellation_and_deadline_stop_before_model_execution() -> None:
    request = synthetic_demo_request()
    cancelled = CancellationContext()
    cancelled.cancel()
    with pytest.raises(InferenceCancelledError):
        analyze_gbm_rna_purity(request, cancellation=cancelled)

    expired = CancellationContext(deadline=0.0, clock=lambda: 1.0)
    with pytest.raises(InferenceDeadlineExceededError):
        analyze_gbm_rna_purity(request, cancellation=expired)


def test_service_methods_and_replay_mismatch_are_fail_closed() -> None:
    request, result, document = _raw_result()
    service = GbmRnaPurityService()
    envelope = GbmRnaPurityReplayVerificationRequest(request=request, result=result)
    assert service.analyze(request) == result
    assert service.verify(envelope).verified is True

    other_request = request.model_copy(update={"sample_id": "different.sample"})
    mismatch = verify_gbm_rna_purity_replay(
        GbmRnaPurityReplayVerificationRequest(request=other_request, result=result)
    )
    assert mismatch.verified is False
    assert mismatch.request_digest_match is False
    assert mismatch.semantic_match is False
    assert "no purity estimate is accepted" in mismatch.message

    forged_profile = UnverifiedGbmRnaPurityResult.model_validate(
        {**document, "profile_digest": "sha256:" + "f" * 64}
    )
    profile_mismatch = verify_gbm_rna_purity_replay(
        GbmRnaPurityReplayVerificationRequest(request=request, result=forged_profile)
    )
    assert profile_mismatch.profile_digest_match is False
    assert profile_mismatch.result_digest_match is False


def test_catalog_arrays_are_exact_and_immutable() -> None:
    catalog = gbm_rna_purity_catalog()
    original_index = catalog.feature_index[catalog.feature_names[0]]
    original_bias = catalog.parameters["out.bias"]
    original_commit = catalog.source["commit"]
    assert catalog.artifact_digest == catalog_module.EXPECTED_ARTIFACT_SHA256
    assert catalog.feature_order_digest == catalog_module.EXPECTED_FEATURE_ORDER_DIGEST
    assert catalog.weight_tensor_digest == catalog_module.EXPECTED_WEIGHT_TENSOR_DIGEST
    assert all(not parameter.flags.writeable for parameter in catalog.parameters.values())
    assert not catalog.feature_lengths.flags.writeable
    with pytest.raises(ValueError):
        catalog.parameters["out.bias"][0] = np.float32(0.0)
    with pytest.raises(TypeError):
        cast("Any", catalog.feature_index)[catalog.feature_names[0]] = 1
    with pytest.raises(TypeError):
        cast("Any", catalog.parameters)["out.bias"] = np.zeros(1, dtype=np.float32)
    with pytest.raises(TypeError):
        cast("Any", catalog.source)["commit"] = "substituted"
    assert catalog.feature_index[catalog.feature_names[0]] == original_index
    assert catalog.parameters["out.bias"] is original_bias
    assert catalog.source["commit"] == original_commit


def test_every_external_artifact_digest_pin_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = catalog_module._resource_bytes()

    with monkeypatch.context() as context:
        context.setattr(catalog_module, "_resource_bytes", lambda: original + b" ")
        gbm_rna_purity_catalog.cache_clear()
        with pytest.raises(GbmRnaPurityArtifactError, match="file digest mismatch"):
            gbm_rna_purity_catalog()
    gbm_rna_purity_catalog.cache_clear()

    content_substitution = json.loads(original)
    content_substitution["provenance"]["transformation_notice"] += " substituted"
    content_basis = dict(content_substitution)
    content_basis.pop("content_digest")
    content_substitution["content_digest"] = sha256_digest(content_basis)
    substituted_payload = canonical_json_bytes(content_substitution) + b"\n"
    with monkeypatch.context() as context:
        context.setattr(
            catalog_module,
            "EXPECTED_ARTIFACT_SHA256",
            "sha256:" + hashlib.sha256(substituted_payload).hexdigest(),
        )
        context.setattr(catalog_module, "_resource_bytes", lambda: substituted_payload)
        gbm_rna_purity_catalog.cache_clear()
        with pytest.raises(GbmRnaPurityArtifactError, match="not the admitted content"):
            gbm_rna_purity_catalog()
    gbm_rna_purity_catalog.cache_clear()

    for field, message in (
        ("feature_order_digest", "feature order is not the admitted feature vector"),
        ("weight_tensor_digest", "weights are not the admitted tensor bundle"),
    ):
        document = json.loads(original)
        document[field] = "sha256:" + "0" * 64
        with monkeypatch.context() as context:
            _admit_document(context, document)
            with pytest.raises(GbmRnaPurityArtifactError, match=message):
                gbm_rna_purity_catalog()
        gbm_rna_purity_catalog.cache_clear()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda document: document.update(schema_version="wrong"), "schema mismatch"),
        (lambda document: document.update(model_id="wrong"), "model identity mismatch"),
        (lambda document: document.update(input=[]), "input metadata"),
        (lambda document: document.update(parameters=[]), "parameter inventory"),
        (lambda document: document.update(source=[]), "source metadata"),
        (lambda document: document.update(provenance=[]), "provenance metadata"),
    ],
)
def test_catalog_rejects_structural_substitution_even_when_rehashed(
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    message: str,
) -> None:
    document = json.loads(catalog_module._resource_bytes())
    mutation(document)
    _admit_document(monkeypatch, document)
    try:
        with pytest.raises(GbmRnaPurityArtifactError, match=message):
            gbm_rna_purity_catalog()
    finally:
        gbm_rna_purity_catalog.cache_clear()


def test_catalog_rejects_invalid_json_root_and_declared_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = catalog_module._resource_bytes()
    for payload, message in ((b"{", "valid JSON"), (b"[]", "root is not an object")):
        monkeypatch.setattr(
            catalog_module,
            "EXPECTED_ARTIFACT_SHA256",
            "sha256:" + hashlib.sha256(payload).hexdigest(),
        )
        monkeypatch.setattr(catalog_module, "_resource_bytes", lambda payload=payload: payload)
        gbm_rna_purity_catalog.cache_clear()
        with pytest.raises(GbmRnaPurityArtifactError, match=message):
            gbm_rna_purity_catalog()
    gbm_rna_purity_catalog.cache_clear()

    document = json.loads(original)
    document["content_digest"] = "sha256:" + "0" * 64
    _admit_document(monkeypatch, document, bind_content=False)
    with pytest.raises(GbmRnaPurityArtifactError, match="not the admitted content"):
        gbm_rna_purity_catalog()
    gbm_rna_purity_catalog.cache_clear()


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"dtype": ">f4"}, "little-endian"),
        ({"shape": [2]}, "shape mismatch"),
        ({"data_base64": "***"}, "malformed"),
        ({"data_base64": base64.b64encode(b"x").decode()}, "byte count"),
    ],
)
def test_parameter_decoder_rejects_malformed_tensors(
    update: dict[str, object],
    message: str,
) -> None:
    payload = np.asarray([0.5], dtype="<f4").tobytes()
    tensor: dict[str, object] = {
        "dtype": "<f4",
        "shape": [1],
        "data_base64": base64.b64encode(payload).decode(),
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }
    tensor.update(update)
    with pytest.raises(GbmRnaPurityArtifactError, match=message):
        catalog_module._decode_parameter("out.bias", tensor)


def test_parameter_decoder_rejects_digest_and_nonfinite_tensor() -> None:
    finite = np.asarray([0.5], dtype="<f4").tobytes()
    tensor: dict[str, object] = {
        "dtype": "<f4",
        "shape": [1],
        "data_base64": base64.b64encode(finite).decode(),
        "sha256": "sha256:" + "0" * 64,
    }
    with pytest.raises(GbmRnaPurityArtifactError, match="digest mismatch"):
        catalog_module._decode_parameter("out.bias", tensor)

    nonfinite = np.asarray([np.inf], dtype="<f4").tobytes()
    tensor["data_base64"] = base64.b64encode(nonfinite).decode()
    tensor["sha256"] = "sha256:" + hashlib.sha256(nonfinite).hexdigest()
    with pytest.raises(GbmRnaPurityArtifactError, match="non-finite"):
        catalog_module._decode_parameter("out.bias", tensor)


def test_resource_and_scalar_metadata_helpers_reject_absence_and_wrong_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MissingResource:
        def joinpath(self, _path: str) -> _MissingResource:
            return self

        def read_bytes(self) -> bytes:
            raise FileNotFoundError

    monkeypatch.setitem(catalog_module.__dict__, "files", lambda _package: _MissingResource())
    with pytest.raises(GbmRnaPurityArtifactError, match="artifact is absent"):
        catalog_module._resource_bytes()

    for document in ({}, {"value": 7}, {"value": ""}):
        with pytest.raises(GbmRnaPurityArtifactError, match="value is invalid"):
            catalog_module._string(cast("dict[str, object]", document), "value")
        with pytest.raises(GbmRnaPurityArtifactError, match=r"source\.value is invalid"):
            catalog_module._source_string(cast("dict[str, object]", document), "value")


def test_parameter_decoder_rejects_nonobjects_nonlist_shapes_and_nonstring_payloads() -> None:
    with pytest.raises(GbmRnaPurityArtifactError, match="not an object"):
        catalog_module._decode_parameter("out.bias", [])
    for update, message in (
        ({"shape": "1"}, "shape mismatch"),
        ({"data_base64": 7}, "base64 payload is invalid"),
    ):
        payload = np.asarray([0.5], dtype="<f4").tobytes()
        tensor: dict[str, object] = {
            "dtype": "<f4",
            "shape": [1],
            "data_base64": base64.b64encode(payload).decode(),
            "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        }
        tensor.update(update)
        with pytest.raises(GbmRnaPurityArtifactError, match=message):
            catalog_module._decode_parameter("out.bias", tensor)


def test_catalog_rejects_internal_content_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _catalog_document()
    document["provenance"]["transformation_notice"] += " altered without digest update"
    payload = canonical_json_bytes(document) + b"\n"
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_SHA256",
        "sha256:" + hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: payload)
    gbm_rna_purity_catalog.cache_clear()
    try:
        with pytest.raises(GbmRnaPurityArtifactError, match="content digest mismatch"):
            gbm_rna_purity_catalog()
    finally:
        gbm_rna_purity_catalog.cache_clear()


@pytest.mark.parametrize("invalid_names", ["not-a-list", ["EGFR", 7]])
def test_catalog_rejects_invalid_feature_name_containers(
    monkeypatch: pytest.MonkeyPatch,
    invalid_names: object,
) -> None:
    document = _catalog_document()
    document["input"]["feature_names"] = invalid_names
    _expect_catalog_failure(monkeypatch, document, "feature names are invalid")


def test_catalog_rejects_wrong_length_and_duplicate_feature_orders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _catalog_document()
    shortened = _catalog_document()
    shortened["input"]["feature_names"] = shortened["input"]["feature_names"][:-1]
    _expect_catalog_failure(monkeypatch, shortened, "5,829 unique symbols")

    duplicate = _catalog_document()
    duplicate["input"]["feature_names"][-1] = duplicate["input"]["feature_names"][0]
    _expect_catalog_failure(monkeypatch, duplicate, "5,829 unique symbols")
    assert original["input"]["feature_names"][-1] != original["input"]["feature_names"][0]


@pytest.mark.parametrize("invalid_lengths", ["not-a-list", [1.0]])
def test_catalog_rejects_invalid_feature_length_containers(
    monkeypatch: pytest.MonkeyPatch,
    invalid_lengths: object,
) -> None:
    document = _catalog_document()
    document["input"]["feature_lengths"] = invalid_lengths
    _expect_catalog_failure(monkeypatch, document, "feature lengths are invalid")


def test_catalog_rejects_nonnumeric_nonpositive_and_nonfinite_feature_lengths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nonnumeric = _catalog_document()
    nonnumeric["input"]["feature_lengths"][0] = {}
    _expect_catalog_failure(monkeypatch, nonnumeric, "feature lengths are not numeric")

    nonpositive = _catalog_document()
    nonpositive["input"]["feature_lengths"][0] = 0.0
    _expect_catalog_failure(monkeypatch, nonpositive, "finite and positive")

    nonfinite = _catalog_document()
    nonfinite["input"]["feature_lengths"][0] = float("nan")
    declared = nonfinite["content_digest"]
    payload = json.dumps(
        nonfinite,
        allow_nan=True,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode() + b"\n"
    monkeypatch.setattr(
        catalog_module,
        "EXPECTED_ARTIFACT_SHA256",
        "sha256:" + hashlib.sha256(payload).hexdigest(),
    )
    monkeypatch.setattr(catalog_module, "_resource_bytes", lambda: payload)
    monkeypatch.setattr(catalog_module, "sha256_digest", lambda _value: declared)
    gbm_rna_purity_catalog.cache_clear()
    try:
        with pytest.raises(GbmRnaPurityArtifactError, match="finite and positive"):
            gbm_rna_purity_catalog()
    finally:
        gbm_rna_purity_catalog.cache_clear()


def test_catalog_rejects_self_consistent_content_with_wrong_feature_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _catalog_document()
    document["input"]["feature_names"][0] += "_SUBSTITUTED"
    _expect_catalog_failure(monkeypatch, document, "feature-order digest mismatch")


def test_catalog_rejects_self_consistent_tensor_with_wrong_bundle_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _catalog_document()
    tensor = document["parameters"]["out.bias"]
    payload = struct.pack("<f", 0.375)
    tensor["data_base64"] = base64.b64encode(payload).decode()
    tensor["sha256"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    _expect_catalog_failure(monkeypatch, document, "weight-tensor digest mismatch")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("commit", "0" * 40, "source commit mismatch"),
        ("model_sha256", "sha256:" + "0" * 64, "source model digest mismatch"),
        (
            "gene_table_sha256",
            "sha256:" + "0" * 64,
            "source feature-table digest mismatch",
        ),
        ("license_spdx_id", "Proprietary", "source license mismatch"),
    ],
)
def test_catalog_rejects_substituted_source_identity_fields(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
    message: str,
) -> None:
    document = _catalog_document()
    document["source"][field] = value
    _expect_catalog_failure(monkeypatch, document, message)


@pytest.mark.parametrize("invalid_notice", ["", 7])
def test_catalog_rejects_empty_and_nonstring_transformation_notices(
    monkeypatch: pytest.MonkeyPatch,
    invalid_notice: object,
) -> None:
    document = _catalog_document()
    document["provenance"]["transformation_notice"] = invalid_notice
    _expect_catalog_failure(monkeypatch, document, "transformation notice is invalid")

def test_semantic_and_payload_digest_helpers_accept_untrusted_mappings() -> None:
    _request, result, _document = _raw_result()
    document = result.model_dump(mode="json")
    assert result_payload_digest(document) == result.result_digest
    assert semantic_result_equal(result, document)
    changed = dict(document)
    changed["sample_id"] = "different.sample"
    assert semantic_result_equal(result, changed) is False
    assert cast("dict[str, object]", document)["result_digest"] == result.result_digest
