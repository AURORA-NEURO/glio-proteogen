"""Runtime, replay, and safe-abstention tests for provisional M17-06."""

# ruff: noqa: PLR2004, ARG002, TRY003, E501

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m17_06 import QueueEntryState, QueueResultStatus, ReviewDecision
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_06_reviewer_discrepancy_adjudication as m1706,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m17_06_reviewer_discrepancy_adjudication import (
    engine as engine_module,
)
from tests.contract.test_m17_06_deep import _assignment, _entry, _request


def test_resolved_queue_emits_record_with_uncertainty_provenance() -> None:
    result = m1706.M1706AdjudicationEngine().export(_request())

    assert result.status is QueueResultStatus.RECORDED
    assert result.record is not None
    assert result.record.status.value == "resolved"
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.uncertainty.transport.probability == 0.9
    assert len(result.provenance.control_decisions) == 7
    assert result.human_review_required


def test_unresolved_queue_abstains_and_preserves_review_finding() -> None:
    request = _request(
        entries=(_entry(state=QueueEntryState.IN_REVIEW),),
        assignments=(_assignment(decision=ReviewDecision.DEFER),),
    )
    result = m1706.M1706AdjudicationEngine().export(request)

    assert result.status is QueueResultStatus.ABSTAINED
    assert result.record is None
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.abstention_reason
    assert any(item.code.value == "review_required" for item in result.findings)


@pytest.mark.parametrize("marker", ["unsupported", "ood", "kinase activity", "treatment"])
def test_boundary_markers_abstain_without_negative_finding(marker: str) -> None:
    request = _request(
        entries=(_entry().model_copy(update={"description": marker}),),
    )
    result = m1706.M1706AdjudicationEngine().export(request)

    assert result.status is QueueResultStatus.ABSTAINED
    assert result.record is None
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason


def test_service_replay_and_tamper_are_deterministic() -> None:
    service = m1706.M1706Service()
    request = _request()
    first = service.execute(request)
    second = service.execute(request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).result_digest == first.result_digest
    assert service.verify(first, replay=False).result_digest == first.result_digest
    with pytest.raises(m1706.M1706ReplayVerificationError):
        service.verify(
            first.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False
        )


def test_preflight_and_malformed_requests_fail_closed() -> None:
    with pytest.raises(m1706.M1706AuthorizationError):
        m1706.preflight_adjudication_authorization({"context": {"references": {}}})
    with pytest.raises(m1706.M1706AuthorizationError):
        m1706.preflight_adjudication_authorization(_request().model_copy(update={"context": None}))
    with pytest.raises(m1706.M1706ExportError):
        m1706.M1706AdjudicationEngine().export(_request().model_copy(update={"entries": ()}))


def test_mapping_preflight_rejects_malformed_controls() -> None:
    with pytest.raises(m1706.M1706AuthorizationError):
        m1706.preflight_adjudication_authorization("not-a-mapping")
    with pytest.raises(m1706.M1706AuthorizationError):
        m1706.preflight_adjudication_authorization({"context": None})
    with pytest.raises(m1706.M1706AuthorizationError):
        m1706.preflight_adjudication_authorization({"context": {}})
    with pytest.raises(m1706.M1706AuthorizationError):
        m1706.preflight_adjudication_authorization(
            {
                "context": {
                    "references": {
                        "approved_configuration": {"state": "rejected"},
                        "identity_lineage": {"state": "resolved"},
                        "provenance": {"state": "accepted"},
                        "consent": {"state": "granted"},
                        "quality": {"state": "accepted"},
                        "support": {"state": "accepted"},
                        "intended_use": {"state": "accepted"},
                    }
                }
            }
        )


def test_public_wrapper_and_export_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    engine = m1706.M1706AdjudicationEngine()
    result = engine.export(request)
    assert m1706.adjudicate_variant_peptide_discrepancy_queue(request) == result
    assert m1706.M1706Plugin().verify(result).result_digest == result.result_digest

    class FailingAdapter:
        def validate_python(self, _payload: object, *, strict: bool) -> object:
            raise RuntimeError("forced adapter failure")

    original_adapter = engine_module._RESULT_ADAPTER
    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", FailingAdapter())
    with pytest.raises(m1706.M1706ExportError):
        engine.export(request)
    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", original_adapter)


def test_replay_rejects_mismatched_reconstruction_and_export_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = m1706.M1706AdjudicationEngine()
    result = engine.export(_request())
    unresolved = engine.export(
        _request(
            entries=(_entry(state=QueueEntryState.IN_REVIEW),),
            assignments=(_assignment(decision=ReviewDecision.DEFER),),
        )
    )
    monkeypatch.setattr(engine, "export", lambda _request: unresolved)
    with pytest.raises(m1706.M1706ReplayVerificationError):
        engine.verify(result)


def test_replay_digest_guard_rejects_untrusted_adapter_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = m1706.M1706AdjudicationEngine()
    result = engine.export(_request())
    original_adapter = engine_module._RESULT_ADAPTER

    class TamperAdapter:
        def validate_python(self, _payload: object, *, strict: bool) -> object:
            return result.model_copy(update={"result_digest": sha256_digest("tampered")})

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", TamperAdapter())
    with pytest.raises(m1706.M1706ReplayVerificationError):
        engine.verify(result, replay=False)
    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", original_adapter)

    def fail(_request: object) -> object:
        raise RuntimeError("replay failure")

    monkeypatch.setattr(engine, "export", fail)
    with pytest.raises(m1706.M1706ReplayVerificationError):
        engine.verify(result)
