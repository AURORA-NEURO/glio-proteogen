"""Deep adversarial runtime and interface-boundary cases for M23-07."""

from __future__ import annotations

from typing import Any, cast

import pytest
from evals.m23_07.fixture import build_request
from pydantic import ValidationError

from glio_proteogen.contracts.m23_07 import (
    HumanFactorsOperationalReport,
    OperationalStatus,
    VariantPeptideHumanFactorsResult,
    result_payload_digest,
)
from glio_proteogen.modules.c21_reference_material import (
    m23_07_human_factors_operational_evaluator as m2307,
)


def test_authorization_boundary_rejects_hostile_mappings_before_validation() -> None:
    with pytest.raises(m2307.M2307AuthorizationError):
        m2307.preflight_m2307_authorization({})
    with pytest.raises(ValidationError):
        m2307.M2307Service().evaluate({"context": None})


def test_strict_service_rejects_unknown_fields() -> None:
    payload = build_request().model_dump(mode="json")
    payload["unexpected"] = "must be rejected"
    with pytest.raises(ValidationError):
        m2307.M2307Service().validate_request(payload)


def test_plugin_rejects_non_object_json_and_unvalidated_execution() -> None:
    plugin = m2307.M2307Plugin(m2307.M2307Service())
    with pytest.raises((TypeError, ValueError)):
        plugin.validate(m2307.HumanFactorsEvaluationSubmission(request=b"[]"))
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", build_request()))


def test_replay_rejects_request_mutation_even_when_result_digest_is_unchanged() -> None:
    service = m2307.M2307Service()
    result = service.evaluate(build_request())
    tampered_request = result.request.model_copy(update={"request_id": "tampered-request"})
    tampered = result.model_copy(update={"request": tampered_request})

    with pytest.raises(m2307.M2307ReplayError, match="request digest"):
        service.replay(tampered)


def test_media_boundary_drift_is_rejected_without_upstream_traversal() -> None:
    payload = build_request().model_dump(mode="python")
    payload["upstream_result"]["media_type"] = "application/json"
    with pytest.raises((ValidationError, ValueError)):
        m2307.M2307Service().evaluate(payload)


def test_request_closure_rejects_missing_dimensions_and_fallbacks() -> None:
    base = build_request()
    missing_metrics = base.model_copy(update={"metrics": base.metrics[:-1]})
    with pytest.raises(ValidationError, match="measure every configured"):
        m2307.M2307Service().evaluate(missing_metrics)

    missing_fallbacks = base.model_copy(update={"fallbacks": base.fallbacks[:1]})
    with pytest.raises(ValidationError, match="cover downtime"):
        m2307.M2307Service().evaluate(missing_fallbacks)

    duplicate_metric = base.model_copy(
        update={
            "metrics": (
                base.metrics[0].model_copy(update={"metric_id": base.metrics[1].metric_id}),
                *base.metrics[1:],
            )
        }
    )
    with pytest.raises(ValidationError, match="metric ids must be unique"):
        m2307.M2307Service().evaluate(duplicate_metric)


def test_report_and_result_replay_closures_reject_forgery() -> None:
    service = m2307.M2307Service()
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
    with pytest.raises(ValidationError, match="result id"):
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


@pytest.mark.parametrize("mutation", ["report", "evidence"])
def test_replay_rejects_self_rehashed_semantic_mutations(mutation: str) -> None:
    service = m2307.M2307Service()
    result = service.evaluate(build_request())
    if mutation == "report":
        assert result.report is not None
        changed_report = result.report.model_copy(update={"version": "0.1.1"})
        forged = result.model_copy(update={"report": changed_report})
    else:
        assert result.evidence
        changed_evidence = result.evidence[0].model_copy(
            update={"claim": "forged operational evidence claim"}
        )
        forged = result.model_copy(update={"evidence": (changed_evidence,)})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(m2307.M2307ReplayError):
        service.replay(forged)


def test_strict_result_validation_rejects_self_rehashed_report_mutation() -> None:
    result = m2307.M2307Service().evaluate(build_request())
    assert result.report is not None
    changed_metric = result.report.metrics[0].model_copy(update={"observed_value": 999.0})
    changed_report = result.report.model_copy(
        update={"metrics": (changed_metric, *result.report.metrics[1:])}
    )
    forged = result.model_copy(update={"report": changed_report})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(ValidationError, match="exact request declarations"):
        VariantPeptideHumanFactorsResult.model_validate(
            forged.model_dump(mode="python"), strict=True
        )


def test_preflight_and_runtime_wrapper_cover_hostile_and_public_paths() -> None:
    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2307.M2307AuthorizationError):
        m2307.preflight_m2307_authorization(ExplodingMapping())
    result = m2307.evaluate_variant_peptide_human_factors_operational(build_request())
    assert result.result_digest.startswith("sha256:")


def test_fallback_not_evaluable_abstains() -> None:
    request = build_request()
    fallback = request.fallbacks[0].model_copy(update={"status": OperationalStatus.NOT_EVALUABLE})
    result = m2307.M2307Service().evaluate(
        request.model_copy(update={"fallbacks": (fallback, *request.fallbacks[1:])})
    )
    assert result.status.value == "abstained"
