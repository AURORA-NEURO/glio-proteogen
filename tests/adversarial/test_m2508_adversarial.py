"""Hostile M25-08 contract, replay, plugin, and boundary coverage."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m25_08.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m25_08 import (
    M2508_M2506_INPUT_MEDIA_TYPE,
    AdjudicateProteotypeEvidenceGateRequest,
    BenchmarkOutcome,
    GateFinding,
    GateFindingCode,
)
from glio_proteogen.kernel.strict_json import StrictJsonError, strict_json_loads
from glio_proteogen.modules.c21_reference_material.m25_08_evidence_gate_release_adjudicator import (
    M2508Engine,
    M2508Plugin,
    M2508ReplayError,
    ValidatedM2508Request,
)


def test_request_unknown_keys_are_rejected_without_coercion() -> None:
    payload = build_request().model_dump(mode="python")
    payload["unexpected_internal_field"] = "must not cross the boundary"
    with pytest.raises(ValidationError):
        AdjudicateProteotypeEvidenceGateRequest.model_validate(payload, strict=True)


def test_upstream_media_mismatch_is_not_accepted_as_evidence() -> None:
    request = build_request()
    upstream = request.upstream_evidence.model_copy(update={"media_type": "application/json"})
    payload = request.model_dump(mode="python")
    payload["upstream_evidence"] = upstream
    payload["source_artifacts"] = tuple(
        upstream if item.artifact_id == request.upstream_evidence.artifact_id else item
        for item in request.source_artifacts
    )
    with pytest.raises(ValidationError, match="M25-07 evidence"):
        AdjudicateProteotypeEvidenceGateRequest.model_validate(payload, strict=True)


def test_media_only_boundary_cannot_be_dropped() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = tuple(
        item for item in request.source_artifacts if item.media_type != M2508_M2506_INPUT_MEDIA_TYPE
    )
    with pytest.raises(ValidationError, match="media-only evidence boundary"):
        AdjudicateProteotypeEvidenceGateRequest.model_validate(payload, strict=True)


def test_duplicate_source_artifacts_are_rejected() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts, request.source_artifacts[0])
    with pytest.raises(ValidationError, match="source artifacts must be unique"):
        AdjudicateProteotypeEvidenceGateRequest.model_validate(payload, strict=True)


def test_non_finite_benchmark_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        BenchmarkOutcome(
            benchmark_id="m2508.infinity",
            name="non-finite",
            metric_name="metric",
            observed_value=float("inf"),
            required_floor=1.0,
            passed=False,
            report_artifact=build_request().source_artifacts[0],
            evidence=(),
        )


def test_result_duplicate_findings_are_rejected_on_replay() -> None:
    result = M2508Engine().evaluate(build_request(requirement_satisfied=False))
    assert result.findings
    tampered = result.model_copy(update={"findings": (*result.findings, result.findings[0])})
    with pytest.raises(M2508ReplayError):
        M2508Engine().verify(tampered, replay=False)


def test_result_duplicate_evidence_is_rejected_on_replay() -> None:
    result = M2508Engine().evaluate(build_request())
    tampered = result.model_copy(update={"evidence": (*result.evidence, result.evidence[0])})
    with pytest.raises(M2508ReplayError):
        M2508Engine().verify(tampered, replay=False)


def test_finding_codes_remain_typed_and_caller_declared() -> None:
    result = M2508Engine().evaluate(build_request(requirement_satisfied=False))
    finding = next(
        item for item in result.findings if item.code is GateFindingCode.REQUIREMENT_UNSATISFIED
    )
    assert isinstance(finding, GateFinding)
    assert finding.finding_id.startswith("finding.m2508.")


def test_forged_plugin_token_cannot_bypass_seal() -> None:
    plugin = M2508Plugin()
    request = build_request()
    forged = ValidatedM2508Request(request=request, _seal=object())
    with pytest.raises(TypeError):
        plugin.run(forged)
    with pytest.raises(TypeError):
        plugin.run(cast("Any", object()))


def test_strict_json_rejects_duplicate_keys() -> None:
    with pytest.raises(StrictJsonError):
        strict_json_loads(b'{"request_id":"a","request_id":"b"}')


def test_result_digest_cannot_be_repaired_after_request_mutation() -> None:
    result = M2508Engine().evaluate(build_request())
    changed_request = build_request().model_copy(update={"request_id": "m2508.changed"})
    tampered = result.model_copy(update={"request": changed_request})
    with pytest.raises(M2508ReplayError):
        M2508Engine().verify(tampered, replay=False)


def test_request_context_identity_binding_is_required() -> None:
    request = build_request()
    payload = request.model_dump(mode="python")
    payload["context"] = request.context.model_copy(update={"request_id": "m2508.other"})
    with pytest.raises(ValidationError, match="bind the request identifier"):
        AdjudicateProteotypeEvidenceGateRequest.model_validate(payload, strict=True)


def test_unsupported_gate_never_emits_parent_estimate() -> None:
    result = M2508Engine().evaluate(build_request(requirement_satisfied=False))
    assert result.status.value == "abstained"
    assert result.emits_parent is False
    assert result.support_decision.status.value == "review_required"
