"""Adversarial boundary coverage for provisional M21-03."""

from __future__ import annotations

import math
from typing import Any

import pytest
from evals.m21_03.fixture import denied_request
from pydantic import ValidationError

from glio_proteogen.contracts.m21_03 import (
    BenchmarkFinding,
    BenchmarkFindingCode,
    BenchmarkMetric,
    ComplexActivityInternalBenchmarkResult,
    RunComplexActivityInternalBenchmarkRequest,
    canonical_request_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m21_03_internal_benchmark_ablation import (
    BenchmarkSubmission,
    M2103AuthorizationError,
    M2103Plugin,
    M2103Service,
)
from tests.contract.test_m21_03_provisional import (
    _completed_result,
    _evidence,
    _metric,
    _request,
)


def _self_rehashed(
    result: ComplexActivityInternalBenchmarkResult,
    **updates: Any,
) -> ComplexActivityInternalBenchmarkResult:
    """Forge a valid-looking result whose digest covers attacker changes."""

    forged = result.model_copy(update=updates)
    return forged.model_copy(update={"result_digest": result_payload_digest(forged)})


def test_request_rejects_wrong_media_and_duplicate_source_material() -> None:
    request = _request()
    wrong_media = request.upstream_result.model_copy(
        update={"media_type": "application/octet-stream"}
    )
    with pytest.raises(ValueError, match="bind the provisional M21-02"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(update={"upstream_result": wrong_media}), strict=True
        )
    with pytest.raises(ValueError, match="source artifacts must be unique"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(
                update={
                    "source_artifacts": (request.source_artifacts[0], request.source_artifacts[0])
                }
            ),
            strict=True,
        )


def test_request_rejects_duplicate_ablation_and_comparison_ids() -> None:
    request = _request()
    with pytest.raises(ValueError, match="ablation ids"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(update={"ablations": (request.ablations[0], request.ablations[0])}),
            strict=True,
        )
    with pytest.raises(ValueError, match="comparison ids"):
        RunComplexActivityInternalBenchmarkRequest.model_validate(
            request.model_copy(
                update={"comparisons": (request.comparisons[0], request.comparisons[0])}
            ),
            strict=True,
        )


def test_finite_numeric_and_strict_enum_boundaries() -> None:
    with pytest.raises(ValidationError):
        BenchmarkMetric.model_validate(
            _metric().model_copy(update={"candidate_value": math.nan}), strict=True
        )
    with pytest.raises(ValidationError):
        BenchmarkMetric.model_validate(_metric().model_copy(update={"status": "pass"}), strict=True)


def test_result_findings_and_digest_cannot_be_replayed_after_tampering() -> None:
    request = _request()
    result = _completed_result(request)
    finding = BenchmarkFinding(
        finding_id="finding-1",
        code=BenchmarkFindingCode.BASELINE_FAILURE,
        message="Caller-declared baseline evidence requires review.",
        evidence=(_evidence("finding-evidence"),),
    )
    with pytest.raises(ValueError, match="finding ids"):
        ComplexActivityInternalBenchmarkResult.model_validate(
            result.model_copy(update={"findings": (finding, finding)}), strict=True
        )
    with pytest.raises(ValueError, match="result request digest"):
        ComplexActivityInternalBenchmarkResult.model_validate(
            result.model_copy(update={"request_digest": sha256_digest("wrong-request")}),
            strict=True,
        )
    assert result_payload_digest(result) == result.result_digest
    assert canonical_request_digest(request) == result.request_digest
    assert canonical_request_digest(request.model_dump(mode="python")) == result.request_digest


def test_replay_rejects_self_rehashed_nested_dossier_mutation() -> None:
    service = M2103Service()
    result = service.generate(_request())
    assert result.dossier is not None
    metric = result.dossier.metrics[0].model_copy(
        update={"metric_name": result.dossier.metrics[0].metric_name + "-forged"}
    )
    dossier = result.dossier.model_copy(update={"metrics": (metric, *result.dossier.metrics[1:])})
    tampered = _self_rehashed(result, dossier=dossier)

    with pytest.raises(ValueError, match="deterministic regeneration"):
        service.replay(tampered)


def test_replay_rejects_self_rehashed_provenance_mutation() -> None:
    service = M2103Service()
    result = service.generate(_request())
    tampered = _self_rehashed(
        result,
        provenance=result.provenance.model_copy(update={"activity_id": "forged-activity"}),
    )

    with pytest.raises(ValueError, match="deterministic regeneration"):
        service.replay(tampered)


def test_plugin_rejects_self_rehashed_nested_mutation() -> None:
    service = M2103Service()
    plugin = M2103Plugin(service)
    result = service.generate(_request())
    assert result.dossier is not None
    dossier = result.dossier.model_copy(
        update={"evidence": (*result.dossier.evidence, result.dossier.evidence[0])}
    )
    tampered = _self_rehashed(result, dossier=dossier)

    with pytest.raises(ValueError, match="deterministic regeneration"):
        plugin.replay(tampered)


def test_plugin_rejects_malformed_json_and_denied_mapping() -> None:
    plugin = M2103Plugin(M2103Service())
    with pytest.raises((ValueError, ValidationError)):
        plugin.validate(BenchmarkSubmission(request=b"{"))
    denied = denied_request()
    with pytest.raises(M2103AuthorizationError):
        plugin.validate(BenchmarkSubmission(request=denied.model_dump_json()))
