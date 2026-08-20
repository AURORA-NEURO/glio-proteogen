"""Runtime, replay, control-boundary and safe-abstention tests for M24-07."""

from __future__ import annotations

import json
from typing import cast

import pytest

from glio_proteogen.contracts.m24_07 import (
    EvaluateBiomarkerPanelHumanFactorsRequest,
    EvaluationStatus,
    OperationalStatus,
)
from glio_proteogen.kernel.models import SupportStatus, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material import (
    m24_07_human_factors_operational_evaluator as m2407,
)
from tests.contract.test_m24_07_hardening import request as request_payload

_CONTROL_COUNT = 7


def request() -> EvaluateBiomarkerPanelHumanFactorsRequest:
    return EvaluateBiomarkerPanelHumanFactorsRequest.model_validate_json(
        json.dumps(request_payload()), strict=True
    )


def test_supported_result_closes_report_provenance_and_uncertainty() -> None:
    result = m2407.M2407Service().evaluate(request())
    assert result.status is EvaluationStatus.EVALUATED
    assert result.report is not None
    assert result.findings == ()
    assert result.parent_target == "biomarker panel"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.request.upstream_result.digest in result.provenance.input_digests
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M24-07"
    assert all(
        estimate.state.value == "not_estimable"
        for estimate in (
            result.uncertainty.measurement,
            result.uncertainty.sampling,
            result.uncertainty.parameter,
            result.uncertainty.model_form,
            result.uncertainty.identification,
            result.uncertainty.support,
            result.uncertainty.transport,
        )
    )


def test_result_retains_nested_operational_evidence_and_provenance() -> None:
    typed = request()
    result = m2407.M2407Service().evaluate(typed)
    references = typed.context.references
    nested_digests = {
        *(evidence.reference.digest for metric in typed.metrics for evidence in metric.evidence),
        *(
            evidence.reference.digest
            for fallback in typed.fallbacks
            for evidence in fallback.evidence
        ),
        *(evidence.reference.digest for evidence in typed.configuration.evidence),
        references.approved_configuration.evidence.digest,
        references.identity_lineage.evidence.digest,
        references.provenance.evidence.digest,
        references.consent.evidence.digest,
        references.quality.evidence.digest,
        references.support.evidence.digest,
        references.intended_use.evidence.digest,
    }
    result_evidence = {evidence.reference.digest for evidence in result.evidence}
    assert nested_digests <= result_evidence
    assert nested_digests <= set(result.provenance.input_digests)


def test_repeat_json_and_plugin_are_byte_deterministic() -> None:
    service = m2407.M2407Service()
    typed = request()
    first = service.evaluate(typed)
    second = service.evaluate(json.dumps(typed.model_dump(mode="json"), sort_keys=True))
    assert first.result_digest == second.result_digest
    assert service.export_json(first) == service.export_json(second)
    plugin = m2407.M2407Plugin(service)
    token = plugin.validate(m2407.HumanFactorsSubmission(json.dumps(typed.model_dump(mode="json"))))
    assert plugin.run(token).result_digest == first.result_digest


def test_operational_metric_failure_abstains_without_report() -> None:
    typed = request()
    metric = typed.metrics[0].model_copy(update={"status": OperationalStatus.FAIL})
    changed = typed.model_copy(update={"metrics": (metric, *typed.metrics[1:])})
    result = m2407.M2407Service().evaluate(changed)
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.report is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.findings
    assert result.findings[0].code.value == "comprehension_failure"


def test_fallback_unavailable_abstains_and_preserves_reason() -> None:
    typed = request()
    fallback = typed.fallbacks[0].model_copy(
        update={"fallback_available": False, "status": OperationalStatus.FAIL}
    )
    changed = typed.model_copy(update={"fallbacks": (fallback, *typed.fallbacks[1:])})
    result = m2407.M2407Service().evaluate(changed)
    assert result.status is EvaluationStatus.ABSTAINED
    assert result.abstention_reason is not None
    assert "fallback_unavailable" in result.abstention_reason


def test_replay_rejects_request_identity_result_id_and_digest_tampering() -> None:
    service = m2407.M2407Service()
    result = service.evaluate(request())
    changed_request = result.request.model_copy(update={"request_id": "m2407.changed"})
    with pytest.raises(m2407.M2407ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request": changed_request}))
    with pytest.raises(m2407.M2407ReplayError, match="identifier"):
        service.verify_replay(result.model_copy(update={"result_id": "m2407.forged"}))
    with pytest.raises(m2407.M2407ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))


def test_denied_control_and_hostile_mapping_fail_closed_before_content_walk() -> None:
    typed = request()
    support = typed.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    references = typed.context.references.model_copy(update={"support": support})
    denied = typed.model_copy(
        update={"context": typed.context.model_copy(update={"references": references})}
    )
    with pytest.raises(m2407.M2407AuthorizationError):
        m2407.M2407Service().evaluate(denied)

    class ExplodingMapping(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            del key, default
            raise RuntimeError("hostile mapping")  # noqa: TRY003

    with pytest.raises(m2407.M2407AuthorizationError):
        m2407.M2407Service().validate_request(ExplodingMapping())


def test_missing_upstream_media_is_rejected_by_contract() -> None:
    payload = request_payload()
    upstream = cast("dict[str, object]", payload["upstream_result"])
    payload["upstream_result"] = upstream | {
        "media_type": "application/vnd.glio-proteogen.unknown+json"
    }
    with pytest.raises(ValueError, match="M24-06"):
        m2407.M2407Service().validate_request(json.dumps(payload))
