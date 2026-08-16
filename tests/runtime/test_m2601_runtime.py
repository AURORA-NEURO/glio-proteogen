"""Runtime, replay, service, and plugin tests for M26-01."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m26_01 import (
    RegistryEntryStatus,
    RegistryFindingCode,
    RegistryStatus,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    ContextReferences,
    ControlRole,
    SupportStatus,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c20_biomarker_panel.m26_01_registry_configuration_service import (
    M2601AuthorizationError,
    M2601Plugin,
    M2601RegistryEngine,
    M2601ReplayError,
    M2601Service,
    M2601TokenError,
    RegistrySubmission,
    register_protein_subtype_registry,
)
from tests.contract.test_m2601_deep import _request


def _denied_references() -> ContextReferences:
    request = _request()
    current = request.context.references
    denied = UpstreamDecisionReference(
        decision_id="m2601.decision.support-denied",
        state=UpstreamDecisionState.REJECTED,
        policy_version="1.0.0",
        evidence=current.support.evidence,
    )
    return current.model_copy(update={"support": denied})


def test_engine_registers_complete_history_and_replays_exactly() -> None:
    request = _request()
    result = M2601RegistryEngine().register(request)

    assert result.status is RegistryStatus.REGISTERED
    assert result.registry is not None
    assert result.active_configuration == request.active_configuration
    assert len(result.registry.entries) == len(request.entries)
    assert len(result.registry.history) == len(request.entries)
    assert result.parent_target == "protein subtype"
    assert result.emits_parent is False
    assert len(result.provenance.control_decisions) == len(tuple(ControlRole))
    assert result.support_decision.status is SupportStatus.SUPPORTED
    assert M2601RegistryEngine().replay(result) == result


def test_quarantined_entry_abstains_without_emitting_registry() -> None:
    request = _request()
    quarantined = request.entries[0].model_copy(update={"status": RegistryEntryStatus.QUARANTINED})
    candidate = request.model_copy(update={"entries": (quarantined, *request.entries[1:])})

    result = register_protein_subtype_registry(candidate)

    assert result.status is RegistryStatus.ABSTAINED
    assert result.registry is None
    assert result.active_configuration is None
    assert result.abstention_reason
    assert result.support_decision.status is SupportStatus.REVIEW_REQUIRED
    assert any(item.code is RegistryFindingCode.QUARANTINED_INPUT for item in result.findings)


def test_incompatible_configuration_abstains_and_preserves_finding() -> None:
    request = _request()
    binding = request.active_configuration.bindings[0].model_copy(
        update={"compatibility_digest": sha256_digest("forged-compatibility")}
    )
    configuration = request.active_configuration.model_copy(
        update={"bindings": (binding, *request.active_configuration.bindings[1:])}
    )
    candidate = request.model_copy(update={"active_configuration": configuration})

    result = M2601RegistryEngine().register(candidate)

    assert result.status is RegistryStatus.ABSTAINED
    assert any(
        item.code is RegistryFindingCode.INCOMPATIBLE_CONFIGURATION for item in result.findings
    )


def test_authorization_fails_closed_for_denied_and_hostile_controls() -> None:
    request = _request()
    denied_context = request.context.model_copy(update={"references": _denied_references()})
    with pytest.raises(M2601AuthorizationError):
        M2601RegistryEngine().register(request.model_copy(update={"context": denied_context}))

    with pytest.raises(M2601AuthorizationError):
        M2601RegistryEngine().register({"context": {"references": {}}})


def test_service_accepts_mapping_and_canonical_json_boundaries() -> None:
    service = M2601Service()
    request = _request()
    encoded = canonical_json_bytes(request.model_dump(mode="json"))

    from_mapping = service.register(request.model_dump(mode="json"))
    from_json = service.register(encoded)

    assert from_mapping == from_json
    assert service.replay(from_json.model_dump(mode="json")) == from_json
    assert service.replay(from_json.model_dump_json()) == from_json
    assert service.descriptor["module_id"] == "GLIO-PROTEOGEN-M26-01"
    assert service.descriptor["unsupported_to_negative"] is False


def test_plugin_requires_validated_capability_and_preserves_parity() -> None:
    plugin = M2601Plugin()
    request = _request()
    token = plugin.validate(RegistrySubmission(request.model_dump_json()))
    result = plugin.run(token)

    assert result.request.request_id == request.request_id
    assert plugin.replay(result) == result
    assert plugin.descriptor.parent_target == "protein subtype"
    with pytest.raises(M2601TokenError):
        plugin.run(object())  # type: ignore[arg-type]


def test_replay_rejects_tampered_result_digest_and_request() -> None:
    result = M2601RegistryEngine().register(_request())
    tampered_result = result.model_copy(update={"result_digest": sha256_digest("tampered")})
    tampered_request = result.request.model_copy(update={"request_id": "m2601.request.forged"})
    tampered_request_result = result.model_copy(update={"request": tampered_request})

    with pytest.raises(M2601ReplayError):
        M2601RegistryEngine().replay(tampered_result)
    with pytest.raises(M2601ReplayError):
        M2601RegistryEngine().replay(tampered_request_result)
