"""Runtime, replay, and plugin coverage for provisional M20-08."""

from __future__ import annotations

from typing import cast

import pytest

from glio_proteogen.contracts.m20_08 import (
    HealthSignalKind,
    HealthSignalStatus,
    MonitorFindingCode,
    RollbackDecision,
    TranslationHealthStatus,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c20_biomarker_panel.m20_08_translation_monitoring_rollback import (
    M2008AuthorizationError,
    M2008Plugin,
    M2008Service,
    M2008TokenError,
    M2008TranslationMonitoringEngine,
    monitor_protein_subtype_translation_health,
    preflight_m2008_authorization,
)
from tests.contract.test_m20_08_hardening import _context, _request


def test_healthy_monitoring_emits_report_and_replays() -> None:
    engine = M2008TranslationMonitoringEngine()
    result = engine.infer(_request())
    assert result.health_status is TranslationHealthStatus.HEALTHY
    assert result.rollback_decision is RollbackDecision.CONTINUE
    assert result.report is not None
    assert result.parent_target == "protein subtype"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert engine.replay(result) == result


def test_support_drift_suspends_translation() -> None:
    request = _request()
    signal = request.signals[0].model_copy(
        update={
            "kind": HealthSignalKind.SUPPORT_DRIFT,
            "status": HealthSignalStatus.DRIFTING,
            "observed_value": 2.0,
        }
    )
    result = M2008TranslationMonitoringEngine().infer(
        request.model_copy(update={"signals": (signal,)})
    )
    assert result.health_status is TranslationHealthStatus.DEGRADED
    assert result.rollback_decision is RollbackDecision.SUSPEND
    assert result.human_review_required is True


def test_critical_discrepancy_rolls_back() -> None:
    request = _request()
    signal = request.signals[0].model_copy(
        update={
            "kind": HealthSignalKind.DISCREPANCY,
            "metric": "critical discrepancy count",
            "status": HealthSignalStatus.DRIFTING,
            "observed_value": 2.0,
        }
    )
    result = M2008TranslationMonitoringEngine().infer(
        request.model_copy(update={"signals": (signal,)})
    )
    assert result.health_status is TranslationHealthStatus.CRITICAL
    assert result.rollback_decision is RollbackDecision.ROLLBACK
    assert result.human_review_required is True


def test_not_evaluable_signal_abstains_without_report() -> None:
    request = _request()
    signal = request.signals[0].model_copy(
        update={
            "status": HealthSignalStatus.NOT_EVALUABLE,
            "lower_bound": None,
            "upper_bound": None,
        }
    )
    result = M2008TranslationMonitoringEngine().infer(
        request.model_copy(update={"signals": (signal,)})
    )
    assert result.health_status is TranslationHealthStatus.ABSTAINED
    assert result.rollback_decision is RollbackDecision.ABSTAIN
    assert result.report is None
    assert result.human_review_required is True


def test_control_denial_precedes_monitoring() -> None:
    denied = _context().model_copy(
        update={
            "references": _context().references.model_copy(
                update={
                    "consent": _context().references.consent.model_copy(
                        update={"state": ConsentState.WITHHELD}
                    )
                }
            )
        }
    )
    with pytest.raises(M2008AuthorizationError, match="consent"):
        M2008TranslationMonitoringEngine().infer(_request().model_copy(update={"context": denied}))


def test_plugin_token_is_opaque_and_service_is_deterministic() -> None:
    plugin = M2008Plugin()
    token = plugin.validate(_request())
    result = plugin.run(token)
    assert plugin.validate_request(_request()) == _request()
    assert plugin.verify(result) == result
    assert plugin.replay(result) == result
    with pytest.raises(M2008TokenError):
        plugin.run(object())  # type: ignore[arg-type]
    other_plugin = M2008Plugin()
    with pytest.raises(M2008TokenError):
        other_plugin.run(token)


def test_tampered_result_digest_is_rejected() -> None:
    engine = M2008TranslationMonitoringEngine()
    result = engine.infer(_request())
    tampered = result.model_copy(update={"result_digest": "sha256:" + "f" * 64})
    with pytest.raises(ValueError, match="replay verification failed"):
        engine.verify(tampered)


def test_verify_rejects_self_rehashed_semantic_mutation_when_replay_is_disabled() -> None:
    """A self-consistent finding still requires deterministic regeneration."""

    engine = M2008TranslationMonitoringEngine()
    result = engine.infer(_request())
    forged = result.model_copy(update={"findings": (MonitorFindingCode.POLICY_VIOLATION,)})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    assert forged.result_digest == result_payload_digest(forged)
    with pytest.raises(ValueError, match="replay verification failed"):
        engine.verify(forged, replay=False)
    with pytest.raises(ValueError, match="replay verification failed"):
        engine.verify(forged)


def test_service_supports_mapping_and_canonical_json_boundaries() -> None:
    service = M2008Service()
    request = _request()
    document = request.model_dump(mode="json")
    result_from_mapping = service.monitor(document)
    result_from_bytes = service.execute(canonical_json_bytes(document))
    assert result_from_mapping == result_from_bytes
    result_document = result_from_mapping.model_dump(mode="json")
    assert service.replay(result_document) == result_from_mapping
    assert service.verify(canonical_json_bytes(result_document)) == result_from_mapping
    assert cast("str", service.descriptor["upstream_media_type"]).endswith("m20-07+json")


def test_preflight_mapping_and_malformed_candidates_fail_closed() -> None:
    preflight_m2008_authorization(_request().model_dump(mode="json"))
    with pytest.raises(M2008AuthorizationError):
        preflight_m2008_authorization(None)
    with pytest.raises(M2008AuthorizationError):
        M2008TranslationMonitoringEngine().infer({})


def test_public_operation_matches_engine() -> None:
    assert (
        monitor_protein_subtype_translation_health(_request()).health_status
        is TranslationHealthStatus.HEALTHY
    )
