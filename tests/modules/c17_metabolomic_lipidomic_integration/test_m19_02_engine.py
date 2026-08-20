"""Runtime and replay gates for M19-02."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m19_02 import (
    AlignmentDimension,
    AlignmentFindingCode,
    AlignmentObservationStatus,
    AlignmentStatus,
    AlignProteotypeSourcesRequest,
)
from glio_proteogen.contracts.m19_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ConsentState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m19_02_cross_source_alignment as m1902,
)
from tests.contract.test_m19_02_deep import (
    _context,
    _discrepancy,
    _observation,
    _request,
)


def _conflicted_request() -> AlignProteotypeSourcesRequest:
    base = _request()
    conflict = _observation(
        AlignmentDimension.TIME,
        status=AlignmentObservationStatus.CONFLICTED,
        observed_values=("value.time", "other.time"),
    )
    return _request(
        observations=tuple(
            conflict if item.dimension.value == "time" else item for item in base.observations
        ),
        discrepancies=(_discrepancy(AlignmentDimension.TIME),),
    )


def test_supported_alignment_is_deterministic_and_bound_to_proteotype() -> None:
    engine = m1902.M1902Engine()
    first = engine.align(_request())
    second = engine.align(_request())
    assert first == second
    assert first.status is AlignmentStatus.ALIGNED
    assert first.aligned_bundle is not None
    assert first.parent_target == "proteotype"
    assert first.emits_parent is False
    assert first.support_decision.status is SupportStatus.SUPPORTED
    assert first.findings == ()
    assert first.result_digest == second.result_digest


def test_conflicted_alignment_abstains_without_erasing_discrepancy() -> None:
    result = m1902.M1902Engine().align(_conflicted_request())
    assert result.status is AlignmentStatus.ABSTAINED
    assert result.aligned_bundle is None
    assert result.human_review_required is True
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert result.findings[0].code is AlignmentFindingCode.DIMENSION_CONFLICT


def test_preflight_rejects_denied_controls_before_typed_traversal() -> None:
    original = _request()
    denied = original.model_copy(
        update={
            "context": _context("request.m1902").model_copy(
                update={
                    "references": _context("request.m1902").references.model_copy(
                        update={
                            "consent": original.context.references.consent.model_copy(
                                update={"state": ConsentState.UNKNOWN}
                            )
                        }
                    )
                }
            )
        }
    )
    with pytest.raises(m1902.M1902AuthorizationError, match="consent"):
        m1902.preflight_m1902_authorization(denied)
    with pytest.raises(m1902.M1902AuthorizationError, match="consent"):
        m1902.M1902Engine().align(denied)


def test_replay_accepts_exact_result_and_rejects_tampering() -> None:
    service = m1902.M1902Service()
    result = service.align(_request())
    assert service.replay(result) == result
    with pytest.raises(m1902.M1902ReplayError, match="identifier"):
        service.replay(result.model_copy(update={"result_id": "result.tampered"}))
    with pytest.raises(m1902.M1902ReplayError, match="payload"):
        service.replay(result.model_copy(update={"result_digest": "sha256:" + "0" * 64}))
    with pytest.raises((ValidationError, m1902.M1902ReplayError)):
        service.replay(result.model_copy(update={"request_digest": "sha256:" + "0" * 64}))
    assert service.validate_request(_request()) == _request()
    invalid_provenance = result.provenance.model_copy(update={"module_id": "GLIO-PROTEOGEN-M19-01"})
    tampered = result.model_copy(update={"provenance": invalid_provenance})
    tampered = tampered.model_copy(update={"result_digest": result_payload_digest(tampered)})
    with pytest.raises(m1902.M1902ReplayError, match="validation"):
        service.replay(tampered)


def test_replay_rejects_self_rehashed_semantic_mutation() -> None:
    service = m1902.M1902Service()
    result = service.align(_request())
    mutated = result.model_copy(
        update={
            "support_decision": result.support_decision.model_copy(
                update={"rationale": "forged semantic state"}
            )
        }
    )
    mutated = mutated.model_copy(update={"result_digest": result_payload_digest(mutated)})
    with pytest.raises(m1902.M1902ReplayError, match="semantic replay"):
        service.replay(mutated)


def test_plugin_descriptor_and_strict_json_boundary() -> None:
    plugin = m1902.M1902Plugin()
    descriptor = plugin.descriptor
    assert descriptor.module_id == "GLIO-PROTEOGEN-M19-02"
    assert descriptor.parent_target == "proteotype"
    assert descriptor.conflict_preservation is True
    assert descriptor.unsupported_to_negative is False
    request = _request()
    parsed = plugin.validate_json(canonical_json_bytes(request))
    result = plugin.run(parsed)
    assert plugin.replay(result) == result
    with pytest.raises(ValueError, match="valid JSON"):
        plugin.validate_json(b"not-json")
    with pytest.raises(ValueError, match="valid JSON"):
        plugin.validate_json(b'{"a":1,"a":2}')
    with pytest.raises(ValueError, match="size limit"):
        plugin.validate_json(b"{" + b" " * (4 * 1024 * 1024) + b"}")
    assert m1902.align_proteotype_sources(request) == result
