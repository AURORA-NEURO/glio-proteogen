"""Runtime, replay, and safe-abstention tests for provisional M17-02."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m17_02 import AlignmentResultStatus, AlignmentStatus
from glio_proteogen.contracts.m17_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_02_cross_source_alignment_reconciliation as m1702,
)
from tests.contract.test_m17_02_deep import _observation, _request


def test_supported_sources_reconcile_with_explicit_uncertainty_and_provenance() -> None:
    result = m1702.M1702AlignmentEngine().export(_request())

    assert result.status is AlignmentResultStatus.RECONCILED
    assert result.aligned_bundle is not None
    assert result.aligned_bundle.alignment_status is AlignmentStatus.ALIGNED
    assert not result.discrepancy_map
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert result.uncertainty.transport.probability == 0.9
    assert len(result.provenance.control_decisions) == 7
    assert result.human_review_required is False


def test_axis_disagreement_is_preserved_and_abstains_for_review() -> None:
    request = _request().model_copy(
        update={
            "observations": (
                _observation("observation.a"),
                _observation("observation.b").model_copy(update={"sample_id": "sample.002"}),
            )
        }
    )
    result = m1702.M1702AlignmentEngine().export(request)

    assert result.status is AlignmentResultStatus.ABSTAINED
    assert result.aligned_bundle is None
    assert len(result.discrepancy_map) == 1
    assert result.discrepancy_map[0].review_required
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required


@pytest.mark.parametrize("marker", ["unsupported", "ood", "kinase", "treatment"])
def test_boundary_markers_abstain_without_negative_finding(marker: str) -> None:
    request = _request().model_copy(
        update={
            "observations": (
                _observation("observation.a").model_copy(update={"analyte": marker}),
                _observation("observation.b"),
            )
        }
    )
    result = m1702.M1702AlignmentEngine().export(request)

    assert result.status is AlignmentResultStatus.ABSTAINED
    assert result.aligned_bundle is None
    assert result.support_decision.status is SupportStatus.UNSUPPORTED
    assert result.abstention_reason


def test_service_replay_and_tamper_are_deterministic() -> None:
    service = m1702.M1702Service()
    request = _request()
    first = service.execute(request)
    second = service.execute(request)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert service.verify(first).result_digest == first.result_digest
    with pytest.raises(m1702.M1702ReplayVerificationError):
        service.verify(
            first.model_copy(update={"result_digest": sha256_digest("tampered")}), replay=False
        )
    mutated = first.model_copy(update={"human_review_required": True})
    resigned = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    with pytest.raises(m1702.M1702ReplayVerificationError):
        service.verify(resigned, replay=False)


def test_preflight_and_invalid_requests_fail_closed() -> None:
    with pytest.raises(m1702.M1702AuthorizationError):
        m1702.preflight_alignment_authorization({"context": {"references": {}}})
    with pytest.raises(m1702.M1702AuthorizationError):
        m1702.preflight_alignment_authorization(_request().model_copy(update={"context": None}))
    with pytest.raises(m1702.M1702ExportError):
        m1702.M1702AlignmentEngine().export(_request().model_copy(update={"observations": ()}))


def test_mapping_preflight_rejects_malformed_controls() -> None:
    with pytest.raises(m1702.M1702AuthorizationError):
        m1702.preflight_alignment_authorization({"context": None})
    with pytest.raises(m1702.M1702AuthorizationError):
        m1702.preflight_alignment_authorization(
            {"context": {"references": {"approved_configuration": {"state": 1}}}}
        )
