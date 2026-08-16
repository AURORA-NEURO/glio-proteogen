"""Deep adversarial runtime and interface-boundary cases for M22-07."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m22_07.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m22_07 import HumanFactorsOperationalReport, OperationalStatus
from glio_proteogen.modules.c21_reference_material import (
    m22_07_human_factors_operational_evaluator as m2207,
)


def test_authorization_boundary_rejects_hostile_mappings_before_validation() -> None:
    with pytest.raises(m2207.M2207AuthorizationError):
        m2207.preflight_m2207_authorization({})
    with pytest.raises(ValidationError):
        m2207.M2207Service().evaluate({"context": None})


def test_strict_service_rejects_unknown_fields() -> None:
    payload = build_request().model_dump(mode="json")
    payload["unexpected"] = "must be rejected"
    with pytest.raises(ValidationError):
        m2207.M2207Service().validate_request(payload)


def test_plugin_rejects_non_object_json_and_unvalidated_execution() -> None:
    plugin = m2207.M2207Plugin(m2207.M2207Service())
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(m2207.HumanFactorsEvaluationSubmission(request=b"[]"))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", build_request()))


def test_replay_rejects_request_mutation_even_when_result_digest_is_unchanged() -> None:
    service = m2207.M2207Service()
    result = service.evaluate(build_request())
    tampered_request = result.request.model_copy(update={"request_id": "tampered-request"})
    tampered = result.model_copy(update={"request": tampered_request})

    with pytest.raises(m2207.M2207ReplayError, match="request digest"):
        service.replay(tampered)


def test_media_boundary_drift_is_rejected_without_upstream_traversal() -> None:
    payload = build_request().model_dump(mode="python")
    payload["source_artifacts"][0]["media_type"] = "application/json"
    with pytest.raises((ValidationError, ValueError)):
        m2207.M2207Service().evaluate(payload)


def test_request_closure_rejects_missing_dimensions_and_sources() -> None:
    base = build_request()
    missing_metrics = base.model_copy(update={"metrics": base.metrics[:-1]})
    with pytest.raises(ValidationError, match="measure every configured"):
        m2207.M2207Service().evaluate(missing_metrics)

    missing_fallbacks = base.model_copy(update={"fallbacks": base.fallbacks[:1]})
    with pytest.raises(ValidationError, match="cover downtime"):
        m2207.M2207Service().evaluate(missing_fallbacks)

    missing_source = base.model_copy(update={"source_artifacts": base.source_artifacts[:1]})
    with pytest.raises(ValidationError, match="include each declared input"):
        m2207.M2207Service().evaluate(missing_source)

    duplicate_boundary = base.model_copy(
        update={
            "source_artifacts": (
                *base.source_artifacts,
                base.source_artifacts[0].model_copy(
                    update={"artifact_id": "m2206.evaluator.second"}
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="exactly one M22-06"):
        m2207.M2207Service().evaluate(duplicate_boundary)


def test_report_and_result_replay_closures_reject_forgery() -> None:
    service = m2207.M2207Service()
    result = service.evaluate(build_request())
    assert result.report is not None
    report = result.report

    duplicate_metric = report.metrics[0].model_copy(
        update={"metric_id": report.metrics[1].metric_id}
    )
    with pytest.raises(ValidationError, match="metric ids must be unique"):
        HumanFactorsOperationalReport(
            **report.model_dump(mode="python")
            | {"metrics": (duplicate_metric, *report.metrics[1:])}
        )

    duplicate_fallback = report.fallbacks[0].model_copy(
        update={"scenario_id": report.fallbacks[1].scenario_id}
    )
    with pytest.raises(ValidationError, match="fallback scenario ids must be unique"):
        HumanFactorsOperationalReport(
            **report.model_dump(mode="python")
            | {"fallbacks": (duplicate_fallback, *report.fallbacks[1:])}
        )

    incomplete_report = report.model_dump(mode="python")
    incomplete_report["metrics"] = report.metrics[:-1]
    with pytest.raises(ValidationError, match="measure every configured"):
        HumanFactorsOperationalReport(**incomplete_report)

    incomplete_fallback = report.model_dump(mode="python")
    incomplete_fallback["fallbacks"] = report.fallbacks[:1]
    with pytest.raises(ValidationError, match="cover downtime"):
        HumanFactorsOperationalReport(**incomplete_fallback)

    payload = result.model_dump(mode="python")
    payload["request_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="request digest"):
        type(result).model_validate(payload)

    payload = result.model_dump(mode="python")
    payload["result_id"] = "result.forged"
    with pytest.raises(ValidationError, match="result identifier"):
        type(result).model_validate(payload)

    payload = result.model_dump(mode="python")
    payload["report"] = None
    with pytest.raises(ValidationError, match="supported operational report"):
        type(result).model_validate(payload)

    unsupported_request = build_request()
    unsupported_metric = unsupported_request.metrics[0].model_copy(
        update={"status": OperationalStatus.NOT_EVALUABLE}
    )
    abstained = service.evaluate(
        unsupported_request.model_copy(
            update={"metrics": (unsupported_metric, *unsupported_request.metrics[1:])}
        )
    )
    payload = abstained.model_dump(mode="python")
    payload["report"] = result.report
    with pytest.raises(ValidationError, match="abstained result"):
        type(abstained).model_validate(payload)

    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="result digest"):
        type(result).model_validate(payload)


def test_preflight_and_runtime_wrapper_cover_hostile_and_public_paths() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2207.M2207AuthorizationError):
        m2207.preflight_m2207_authorization(ExplodingMapping())
    result = m2207.evaluate_protein_rna_discordance_human_factors_operational(build_request())
    assert result.result_digest.startswith("sha256:")


def test_fallback_not_evaluable_abstains() -> None:
    request = build_request()
    fallback = request.fallbacks[0].model_copy(update={"status": OperationalStatus.NOT_EVALUABLE})
    result = m2207.M2207Service().evaluate(
        request.model_copy(update={"fallbacks": (fallback, *request.fallbacks[1:])})
    )
    assert result.status.value == "abstained"
