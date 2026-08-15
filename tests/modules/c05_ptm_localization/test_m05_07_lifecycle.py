"""Lifecycle and replay behavior for M05-07."""

from glio_proteogen.contracts.m05_07 import (
    PtmLocalizationDimensionSupportDecision,
    PtmLocalizationSupportDisposition,
)
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    M0507Service,
    route_ptm_localization_support,
)
from tests.contract.test_m05_07_hardening import _request

_CONTROL_COUNT = 7


def test_lifecycle_replay_is_byte_semantic_and_immutable() -> None:
    request = _request()
    first = route_ptm_localization_support(request)
    replay = route_ptm_localization_support(request.model_dump(mode="json"))

    assert first == replay
    assert first.disposition is PtmLocalizationSupportDisposition.SUPPORTED
    assert first.request_digest == replay.request_digest
    assert first.result_digest == replay.result_digest


def test_lifecycle_changed_support_declaration_is_new_result() -> None:
    request = _request()
    facts = list(request.declared_facts)
    facts[0] = facts[0].model_copy(
        update={"decision": PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN}
    )
    changed = _request(declared_facts=tuple(facts))
    original_result = M0507Service().execute(request)
    changed_result = M0507Service().execute(changed)

    assert original_result.request_digest != changed_result.request_digest
    assert original_result.result_digest != changed_result.result_digest
    assert changed_result.disposition is PtmLocalizationSupportDisposition.ABSTAINED


def test_lifecycle_supersession_is_preserved_in_request_digest() -> None:
    original = M0507Service().execute(_request())
    superseding = _request(supersedes_result_digest=original.result_digest)
    result = M0507Service().execute(superseding)

    assert result.request.supersedes_result_digest == original.result_digest
    assert result.request_digest != original.request_digest


def test_lifecycle_service_result_has_provenance_controls() -> None:
    result = M0507Service().execute(_request())

    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M05-07"
    assert result.provenance.consent_state.value == "granted"
