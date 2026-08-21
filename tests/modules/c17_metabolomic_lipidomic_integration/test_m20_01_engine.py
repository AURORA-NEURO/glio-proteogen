"""Runtime, replay, and authorization tests for M20-01."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m20_01 import (
    CompatibilityStatus,
    ResolverStatus,
)
from glio_proteogen.contracts.m20_01.canonical import result_payload_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_01_upstream_contract_resolver import (  # noqa: E501
    M2001AuthorizationError,
    M2001Engine,
    M2001Plugin,
    M2001ReplayError,
    preflight_m2001_authorization,
    resolve_protein_subtype_upstream_contracts,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_01_upstream_contract_resolver.service import (  # noqa: E501
    M2001Service,
)
from tests.contract.test_m20_01_adversarial import (
    _candidate,
    _request,
)


def test_supported_resolution_is_deterministic_and_replayable() -> None:
    request = _request()
    engine = M2001Engine()
    first = engine.resolve(request)
    second = engine.resolve(request.model_dump(mode="python"))

    assert first.status is ResolverStatus.VALIDATED
    assert first.bundle is not None
    assert first.result_digest == second.result_digest
    assert first.result_id == second.result_id
    assert engine.replay(first) == first


def test_unknown_compatibility_abstains_without_negative_conversion() -> None:
    unknown = _candidate(
        "candidate.unknown",
        compatibility=CompatibilityStatus.UNKNOWN,
        support_status=SupportStatus.REVIEW_REQUIRED,
    )
    result = M2001Engine().resolve(_request((unknown,)))

    assert result.status is ResolverStatus.ABSTAINED
    assert result.bundle is None
    assert result.compatibility_report.selected_candidate_ids == ()
    assert result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.human_review_required is True
    assert result.findings[0].code.value == "compatibility_unknown"


def test_mixed_candidates_preserve_selected_rejected_and_unresolved_buckets() -> None:
    compatible = _candidate("candidate.compatible")
    rejected = _candidate(
        "candidate.rejected",
        compatibility=CompatibilityStatus.INCOMPATIBLE,
    )
    unknown = _candidate(
        "candidate.unknown",
        compatibility=CompatibilityStatus.UNKNOWN,
        support_status=SupportStatus.REVIEW_REQUIRED,
    )

    result = M2001Engine().resolve(_request((compatible, rejected, unknown)))

    assert result.status is ResolverStatus.ABSTAINED
    assert result.compatibility_report.selected_candidate_ids == ("candidate.compatible",)
    assert result.compatibility_report.rejected_candidate_ids == ("candidate.rejected",)
    assert result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
    assert result.human_review_required is True
    assert result.bundle is None


def test_preflight_fails_before_typed_traversal_for_missing_or_rejected_control() -> None:
    raw = _request().model_dump(mode="python")
    raw["context"]["references"] = None
    with pytest.raises(M2001AuthorizationError, match="seven upstream controls"):
        preflight_m2001_authorization(raw)

    rejected = _request().context.references.support.model_copy(update={"state": "rejected"})
    context = _request().context.model_copy(
        update={
            "references": _request().context.references.model_copy(update={"support": rejected})
        }
    )
    with pytest.raises(M2001AuthorizationError, match="control support"):
        preflight_m2001_authorization(_request().model_copy(update={"context": context}))


def test_replay_rejects_tampered_request_identity_and_digest() -> None:
    engine = M2001Engine()
    result = engine.resolve(_request())
    with pytest.raises(M2001ReplayError, match="identifier"):
        engine.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(M2001ReplayError, match="payload digest"):
        engine.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    with pytest.raises(M2001ReplayError, match="request digest"):
        engine.replay(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))

    semantic = result.model_copy(update={"human_review_required": not result.human_review_required})
    semantic = semantic.model_copy(update={"result_digest": result_payload_digest(semantic)})
    with pytest.raises(M2001ReplayError, match="semantic replay"):
        engine.replay(semantic)


def test_plugin_descriptor_is_sealed_to_safe_m20_01_boundary() -> None:
    plugin = M2001Plugin()
    result = plugin.run(_request())

    assert plugin.descriptor.module_id == "GLIO-PROTEOGEN-M20-01"
    assert plugin.descriptor.parent_target == "protein subtype"
    assert plugin.descriptor.owner == "ML engineering"
    assert plugin.descriptor.external_content_traversal is False
    assert plugin.descriptor.all_omics_fusion is False
    assert plugin.descriptor.kinase_activity is False
    assert plugin.descriptor.treatment_recommendation is False
    assert plugin.replay(result) == result


def test_service_plugin_and_public_wrapper_share_strict_engine_boundary() -> None:
    request = _request()
    service = M2001Service()
    plugin = M2001Plugin()
    assert service.validate_request(request) == request
    assert plugin.validate_request(request) == request
    assert (
        resolve_protein_subtype_upstream_contracts(request).result_digest
        == M2001Engine().resolve(request).result_digest
    )

