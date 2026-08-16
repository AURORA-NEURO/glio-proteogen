"""Focused runtime and replay tests for provisional M16-02."""

# ruff: noqa: E501, PLR2004

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m16_02 import (
    AlignmentDecisionStatus,
    AlignmentLinkStatus,
    DiscrepancyResolutionStatus,
    DiscrepancySeverity,
    ProteinRnaDiscordanceAlignmentResult,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_02_cross_source_alignment_reconciliation import (
    M1602AlignmentEngine,
    M1602AuthorizationError,
    M1602InferenceError,
    M1602ReplayVerificationError,
    M1602Service,
    preflight_alignment_authorization,
    reconcile_cross_source_alignment,
)
from glio_proteogen.modules.c16_kinophos_object_consumer.m16_02_cross_source_alignment_reconciliation import (
    engine as engine_module,
)
from tests.contract.test_m16_02_deep import _request


def test_aligned_request_reconciles_with_complete_evidence() -> None:
    result = M1602AlignmentEngine().reconcile(_request())

    assert result.status is AlignmentDecisionStatus.RECONCILED
    assert result.bundle is not None
    assert result.bundle.links[0].status is AlignmentLinkStatus.ALIGNED
    assert not result.bundle.discrepancies
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert not result.human_review_required
    assert result.abstention_reason is None
    assert len(result.provenance.control_decisions) == 7
    assert result.uncertainty.transport.probability == 0.9


@pytest.mark.parametrize(
    ("label", "severity"),
    [("warning", DiscrepancySeverity.WARNING), ("critical", DiscrepancySeverity.CRITICAL)],
)
def test_open_discrepancy_requires_human_review(label: str, severity: DiscrepancySeverity) -> None:
    result = M1602AlignmentEngine().reconcile(_request(label=label))

    assert result.status is AlignmentDecisionStatus.REVIEW_REQUIRED
    assert result.bundle is not None
    discrepancy = result.bundle.discrepancies[0]
    assert discrepancy.severity is severity
    assert discrepancy.resolution_status is DiscrepancyResolutionStatus.OPEN
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required


def test_resolved_discrepancy_is_reconciled_but_remains_explicit() -> None:
    result = M1602AlignmentEngine().reconcile(_request(label="resolved"))

    assert result.status is AlignmentDecisionStatus.RECONCILED
    assert result.bundle is not None
    assert result.bundle.discrepancies[0].resolution_status is DiscrepancyResolutionStatus.RESOLVED
    assert result.human_review_required is False


@pytest.mark.parametrize("label", ["unsupported", "ood"])
def test_unsupported_or_ood_input_abstains_without_negative_claim(label: str) -> None:
    result = M1602AlignmentEngine().reconcile(_request(label=label))

    assert result.status is AlignmentDecisionStatus.ABSTAINED
    assert result.bundle is None
    assert result.abstention_reason
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.human_review_required


def test_prohibited_boundary_abstains() -> None:
    result = M1602AlignmentEngine().reconcile(_request(label="kinase"))

    assert result.status is AlignmentDecisionStatus.ABSTAINED
    assert result.bundle is None
    assert "upstream_unsupported" in {item.value for item in result.findings}


def test_service_and_replay_are_deterministic() -> None:
    service = M1602Service()
    request = _request()
    first = service.execute(request)
    second = service.execute(request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).result_digest == first.result_digest
    assert service.verify(first, replay=False).result_digest == first.result_digest


def test_replay_detects_tampered_result() -> None:
    engine = M1602AlignmentEngine()
    result = engine.reconcile(_request())
    tampered = result.model_copy(update={"findings": ()})

    with pytest.raises(M1602ReplayVerificationError):
        engine.verify(tampered, replay=False)


def test_preflight_rejects_untrusted_mapping_and_failed_control() -> None:
    with pytest.raises(M1602AuthorizationError):
        preflight_alignment_authorization({"context": {"references": {}}})
    with pytest.raises(M1602AuthorizationError):
        preflight_alignment_authorization(_request(accepted=False))


def test_engine_rejects_invalid_request_and_hostile_object() -> None:
    engine = M1602AlignmentEngine()
    with pytest.raises(M1602AuthorizationError):
        engine.reconcile({"context": {"references": {}}})
    with pytest.raises(M1602InferenceError):
        engine.reconcile(_request().model_copy(update={"source_artifacts": ()}))

    class Hostile:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(name)

    with pytest.raises(M1602AuthorizationError):
        preflight_alignment_authorization(Hostile())


@pytest.mark.parametrize(
    "payload",
    [
        {"context": None},
        {"context": {"references": None}},
        {"context": {"references": {"approved_configuration": None}}},
        {
            "context": {
                "references": {
                    role: {"state": "accepted"}
                    for role in (
                        "approved_configuration",
                        "identity_lineage",
                        "provenance",
                        "consent",
                        "quality",
                        "support",
                        "intended_use",
                    )
                }
            }
        },
    ],
)
def test_mapping_preflight_is_fail_closed(payload: object) -> None:
    with pytest.raises(M1602AuthorizationError):
        preflight_alignment_authorization(payload)


def test_public_operation_and_result_construction_failure_are_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert reconcile_cross_source_alignment(_request()).status is AlignmentDecisionStatus.RECONCILED

    class BrokenAdapter:
        def validate_python(self, _payload: object, *, strict: bool) -> object:
            del strict
            raise ValueError

    monkeypatch.setattr(engine_module, "_RESULT_ADAPTER", BrokenAdapter())
    with pytest.raises(M1602InferenceError):
        M1602AlignmentEngine().reconcile(_request())


def test_replay_rejects_a_deterministic_mismatch() -> None:
    result = M1602AlignmentEngine().reconcile(_request())

    class MismatchEngine(M1602AlignmentEngine):
        def reconcile(self, request: object) -> ProteinRnaDiscordanceAlignmentResult:
            del request
            return M1602AlignmentEngine().reconcile(_request(label="warning"))

    with pytest.raises(M1602ReplayVerificationError):
        MismatchEngine().verify(result)
