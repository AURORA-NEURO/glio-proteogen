"""Runtime, safety, and replay coverage for M19-03."""

# The repository intentionally keeps test directories namespace-only.
# ruff: noqa: INP001

from __future__ import annotations

import pytest
from tests.contract.test_m19_03_adversarial import _artifact, _evidence, _request

from glio_proteogen.contracts.m19_03 import (
    DisagreementRecord,
    DisagreementStatus,
    FusionFindingCode,
    FusionStatus,
    ReliabilityBand,
)
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_03_fusion_aggregation import (
    M1903AuthorizationError,
    M1903Engine,
    M1903Plugin,
    M1903ReplayError,
    M1903Service,
)


def test_attributable_fusion_integrates_and_replays() -> None:
    result = M1903Engine().adapt(_request())

    assert result.status is FusionStatus.INTEGRATED
    assert result.integrated_evidence is not None
    assert result.parent_target == "proteotype"
    assert result.emits_parent is False
    assert result.human_review_required is False
    assert M1903Engine().replay(result) == result


def test_resolved_disagreement_is_preserved_in_integrated_object() -> None:
    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m1903.resolved",
        source_ids=("source.m1903.proteome", "source.m1903.genome"),
        description="Synthetic cross-source difference.",
        status=DisagreementStatus.RESOLVED,
        resolution="Reviewed by the owning evidence authority.",
        evidence=(_evidence(_artifact("resolved")),),
    )
    result = M1903Engine().adapt(_request(disagreements=(disagreement,)))

    assert result.status is FusionStatus.INTEGRATED
    assert result.integrated_evidence is not None
    assert result.integrated_evidence.disagreements == (disagreement,)


def test_open_disagreement_abstains_without_erasing_conflict() -> None:
    disagreement = DisagreementRecord(
        disagreement_id="disagreement.m1903.open",
        source_ids=("source.m1903.proteome", "source.m1903.genome"),
        description="Synthetic unresolved difference.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("open")),),
    )
    result = M1903Engine().adapt(_request(disagreements=(disagreement,)))

    assert result.status is FusionStatus.ABSTAINED
    assert result.integrated_evidence is None
    assert any(item.code is FusionFindingCode.SOURCE_DISAGREEMENT for item in result.findings)
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True


def test_low_reliability_abstains() -> None:
    result = M1903Engine().adapt(_request())
    low = result.request.contributions[0].model_copy(
        update={"reliability_score": 0.2, "reliability_band": ReliabilityBand.LOW}
    )
    low_request = result.request.model_copy(
        update={"contributions": (low, result.request.contributions[1])}
    )
    abstained = M1903Engine().adapt(low_request)

    assert abstained.status is FusionStatus.ABSTAINED
    assert any(item.code is FusionFindingCode.LOW_RELIABILITY for item in abstained.findings)


def test_forbidden_ownership_claim_abstains() -> None:
    request = _request()
    forbidden = request.contributions[0].model_copy(update={"claim": "kinase state recommendation"})
    candidate = request.model_copy(update={"contributions": (forbidden, request.contributions[1])})

    result = M1903Engine().adapt(candidate)

    assert result.status is FusionStatus.ABSTAINED
    assert any(item.code is FusionFindingCode.OWNERSHIP_UNCLEAR for item in result.findings)


def test_control_denial_precedes_source_traversal() -> None:
    request = _request()
    denied = request.context.references.consent.model_copy(update={"state": "withheld"})
    references = request.context.references.model_copy(update={"consent": denied})
    context = request.context.model_copy(update={"references": references})

    with pytest.raises(M1903AuthorizationError, match="consent"):
        M1903Engine().adapt(request.model_copy(update={"context": context}))


def test_upstream_media_type_is_strict() -> None:
    request = _request()
    alignment = _artifact("alignment", "application/json")
    with pytest.raises(ValueError, match="M19-02"):
        M1903Engine().adapt(request.model_copy(update={"alignment_result": alignment}))


def test_tampered_result_digest_is_rejected() -> None:
    result = M1903Engine().adapt(_request())
    tampered = result.model_copy(update={"human_review_required": True})

    with pytest.raises(M1903ReplayError, match="payload digest"):
        M1903Engine().replay(tampered)


def test_service_and_plugin_use_same_canonical_runtime() -> None:
    request = _request()
    service_result = M1903Service().fuse(request)
    plugin = M1903Plugin()

    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M19-03"
    assert plugin.descriptor.parent_target == "proteotype"
    assert plugin.run(request) == service_result
    assert plugin.replay(service_result) == service_result
