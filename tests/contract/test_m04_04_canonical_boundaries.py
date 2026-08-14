"""Focused public canonical wrapper coverage for M04-04."""

from datetime import timedelta

import pytest
from evals.m04_04.run import build_scenario_request
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m04_03 import ProteoformRawInputRole
from glio_proteogen.contracts.m04_04 import (
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityMetricCode,
    ProteoformQualityMetricDirection,
    ProteoformQualityThreshold,
    context_digest,
    normalized_result,
)
from glio_proteogen.contracts.m04_04.v1 import (
    _cross_metric_roles,
    _issue_raw_input_replay_capability,
    _ledger_bindings_close,
    _materialize_raw_input_value,
    _profile_candidates,
    _raw_input_value,
    _validate_json_request_with_raw_capability,
    _version_mismatch_findings,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    compute_proteoform_quality_metrics,
)


@pytest.fixture(scope="module")
def quality_request() -> ComputeProteoformQualityMetricsRequest:
    return build_scenario_request()


def _validate_request(
    request: ComputeProteoformQualityMetricsRequest,
    **updates: object,
) -> ComputeProteoformQualityMetricsRequest:
    payload = request.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    return ComputeProteoformQualityMetricsRequest.model_validate(payload, strict=True)


def test_public_context_and_result_normalizers_preserve_final_identity(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    request = quality_request
    result = compute_proteoform_quality_metrics(request)

    assert context_digest(request) == sha256_digest(request.context)
    normalized = normalized_result(result)
    assert normalized["result_digest"] == result.result_digest
    assert normalized_result(normalized) == normalized


def test_at_most_threshold_rejects_an_inverted_warning_band() -> None:
    with pytest.raises(ValidationError, match="at-most warning threshold"):
        ProteoformQualityThreshold(
            metric_code=ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN,
            direction=ProteoformQualityMetricDirection.AT_MOST,
            pass_threshold_ppm=200_000,
            warning_threshold_ppm=100_000,
            required=True,
        )


def test_raw_result_wrapper_rejects_wrong_type_and_private_zero_digest(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    with pytest.raises(ValidationError):
        _validate_request(quality_request, raw_input_result=object())

    raw = quality_request.raw_input_result.model_dump(mode="python", exclude_none=False)
    raw["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="derived digests must be final"):
        _validate_request(quality_request, raw_input_result=raw)


def test_request_closes_ledger_shape_for_validated_and_safe_upstream(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    with pytest.raises(ValidationError, match="requires a fact ledger"):
        _validate_request(quality_request, fact_ledger=None)

    safe_request = build_scenario_request("quarantined_upstream_zero_ledger_traversal")
    with pytest.raises(ValidationError, match="prohibits fact-ledger traversal"):
        _validate_request(safe_request, fact_ledger=quality_request.fact_ledger)


def test_request_rejects_upstream_chronology_authorization_and_binding_drift(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    before_upstream = quality_request.raw_input_result.completed_at - timedelta(seconds=1)
    earlier_policy = quality_request.policy.model_copy(update={"reviewed_at": before_upstream})
    earlier_context = quality_request.context.model_copy(update={"occurred_at": before_upstream})
    with pytest.raises(ValidationError, match="result cannot postdate"):
        _validate_request(
            quality_request,
            policy=earlier_policy,
            context=earlier_context,
        )

    references = quality_request.context.references
    denied_quality = references.quality.model_copy(update={"state": UpstreamDecisionState.REJECTED})
    denied_context = quality_request.context.model_copy(
        update={"references": references.model_copy(update={"quality": denied_quality})}
    )
    with pytest.raises(ValidationError, match="not authorized"):
        _validate_request(quality_request, context=denied_context)

    stale_support = references.support.model_copy(
        update={
            "evidence": references.support.evidence.model_copy(
                update={"digest": sha256_digest("stale-support-binding")}
            )
        }
    )
    stale_context = quality_request.context.model_copy(
        update={"references": references.model_copy(update={"support": stale_support})}
    )
    with pytest.raises(ValidationError, match="does not bind the exact"):
        _validate_request(quality_request, context=stale_context)


def test_sealed_json_and_recursive_raw_materialization_fail_closed(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    with pytest.raises(TypeError, match="exact model or built-in dict"):
        _raw_input_value(object())
    with pytest.raises(TypeError, match="exact string keys"):
        _materialize_raw_input_value({1: "not-a-json-key"})

    class CorruptedStorage(BaseModel):
        value: int

    corrupted = CorruptedStorage(value=1)
    object.__getattribute__(corrupted, "__dict__")[1] = "not-a-model-key"
    with pytest.raises(TypeError, match="storage must have exact string keys"):
        _materialize_raw_input_value(corrupted)

    capability = _issue_raw_input_replay_capability(quality_request)
    with pytest.raises(TypeError, match="invalid or mismatched"):
        _validate_json_request_with_raw_capability(
            canonical_json_bytes(quality_request),
            {"raw_input_result": {}},
            capability,
        )


def test_safe_upstream_defensive_helpers_never_require_a_ledger() -> None:
    safe_request = build_scenario_request("quarantined_upstream_zero_ledger_traversal")
    assert safe_request.fact_ledger is None
    assert _ledger_bindings_close(safe_request) is False
    assert _profile_candidates(safe_request, ProteoformRawInputRole.GENOME) == ()
    assert _cross_metric_roles(safe_request) == ()
    assert _version_mismatch_findings(safe_request) == ()
