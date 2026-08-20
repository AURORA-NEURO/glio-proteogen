"""Deep M26-01 registry closure, authority, and adversarial contract tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_01 import (
    M2601_DOSSIER_SHA256,
    M2601_DOSSIER_SLICE,
    ActiveConfiguration,
    ConfigurationBinding,
    RegisterProteinSubtypeRegistryRequest,
    RegistryEntry,
    RegistryEntryKind,
    RegistryEntryStatus,
    RegistryEventType,
    RegistryHistoryEvent,
    RegistryRecord,
    canonical_request_digest,
    contract_json_schemas,
    result_identifier,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    EvidenceReference,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)

_SCHEMA_COUNT = 8


def _artifact(label: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m2601.artifact.{label}",
        version="1.0.0",
        digest="sha256:" + hashlib.sha256(label.encode()).hexdigest(),
        media_type="application/json",
    )


def _evidence(label: str) -> tuple[EvidenceReference, ...]:
    return (
        EvidenceReference(
            reference=_artifact(label),
            role="evidence",
            claim="Caller-declared M26-01 registry material.",
        ),
    )


def _context(request_id: str) -> ExecutionContext:
    def decision(label: str) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"m2601.decision.{label}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(f"control-{label}"),
        )

    return ExecutionContext(
        request_id=request_id,
        actor_id="m2601.actor.registry",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="m2601.decision.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=_artifact("control-identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="m2601.decision.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("control-consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _entries() -> tuple[RegistryEntry, ...]:
    return tuple(
        RegistryEntry(
            entry_id=f"m2601.entry.{kind.value}",
            kind=kind,
            name=f"M26-01 {kind.value} registry entry",
            version="1.0.0",
            artifact=_artifact(f"entry-{kind.value}"),
            owner="m2601.owner",
            status=RegistryEntryStatus.ACTIVE,
            compatibility_digest=sha256_digest(f"compat-{kind.value}"),
            evidence=_evidence(f"entry-{kind.value}"),
        )
        for kind in RegistryEntryKind
    )


def _history(entries: tuple[RegistryEntry, ...]) -> tuple[RegistryHistoryEvent, ...]:
    return tuple(
        RegistryHistoryEvent(
            event_id=f"m2601.event.register.{entry.kind.value}",
            entry_id=entry.entry_id,
            event_type=RegistryEventType.REGISTER,
            new_digest=sha256_digest(entry),
            actor_id="m2601.actor.registry",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            reason="initial immutable registration",
            evidence=_evidence(f"history-{entry.kind.value}"),
        )
        for entry in entries
    )


def _configuration(entries: tuple[RegistryEntry, ...]) -> ActiveConfiguration:
    bindings = tuple(
        ConfigurationBinding(
            binding_id=f"m2601.binding.{entry.kind.value}",
            kind=entry.kind,
            entry_id=entry.entry_id,
            compatibility_digest=entry.compatibility_digest or sha256_digest(entry),
            evidence=_evidence(f"binding-{entry.kind.value}"),
        )
        for entry in entries
    )
    return ActiveConfiguration(
        configuration_id="m2601.configuration.locked",
        version="1.0.0",
        bindings=bindings,
        approved_by="m2601.reviewer",
        configuration_digest=sha256_digest(bindings),
        evidence=_evidence("configuration"),
    )


def _request(request_id: str = "m2601.request.1") -> RegisterProteinSubtypeRegistryRequest:
    entries = _entries()
    return RegisterProteinSubtypeRegistryRequest(
        request_id=request_id,
        context=_context(request_id),
        registry_id="m2601.registry.protein-subtype",
        registry_version="1.0.0",
        entries=entries,
        history=_history(entries),
        active_configuration=_configuration(entries),
        source_artifacts=tuple(_artifact(f"source-{kind.value}") for kind in RegistryEntryKind),
    )


def test_authority_schema_and_result_identity_are_locked() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert M2601_DOSSIER_SHA256.startswith("sha256:")
    assert M2601_DOSSIER_SLICE.endswith("9036-9076")
    assert all(
        cast("dict[str, Any]", schema)["x-glio-contract"]["dossierSha256"] == M2601_DOSSIER_SHA256
        for schema in schemas.values()
    )
    assert all(
        cast("dict[str, Any]", schema)["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    request = _request()
    digest = canonical_request_digest(request)
    assert digest.startswith("sha256:")
    assert result_identifier(digest).startswith("registry.m2601.")


def test_full_registry_request_closes_history_and_configuration() -> None:
    request = _request()
    assert len(request.entries) == len(tuple(RegistryEntryKind))
    assert {binding.kind for binding in request.active_configuration.bindings} == set(
        RegistryEntryKind
    )
    record = RegistryRecord(
        registry_id=request.registry_id,
        version=request.registry_version,
        entries=request.entries,
        history=request.history,
        lock_digest=sha256_digest({"entries": request.entries, "history": request.history}),
        evidence=_evidence("record"),
    )
    assert len(record.history) == len(record.entries)


def test_context_identity_and_source_ids_are_closed() -> None:
    request = _request()
    with pytest.raises(ValidationError, match="context request ID"):
        RegisterProteinSubtypeRegistryRequest.model_validate(
            request.model_copy(update={"context": _context("m2601.request.other")})
        )
    payload = request.model_dump(mode="python")
    payload["source_artifacts"] = (*request.source_artifacts[:-1], request.source_artifacts[0])
    with pytest.raises(ValidationError, match="unique artifact IDs"):
        RegisterProteinSubtypeRegistryRequest.model_validate(payload)


def test_history_requires_prior_for_transitions_and_covers_entries() -> None:
    entry = _entries()[0]
    with pytest.raises(ValidationError, match="require a prior"):
        RegistryHistoryEvent(
            event_id="m2601.event.invalid",
            entry_id=entry.entry_id,
            event_type=RegistryEventType.SUPERSEDE,
            new_digest=sha256_digest(entry),
            actor_id="m2601.actor.registry",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            reason="missing prior",
        )
    request = _request()
    with pytest.raises(ValidationError, match="cover every"):
        RegistryRecord(
            registry_id=request.registry_id,
            version=request.registry_version,
            entries=request.entries,
            history=request.history[:-1],
            lock_digest=sha256_digest(request.entries),
        )


def test_active_configuration_rejects_duplicate_and_missing_kinds() -> None:
    entries = _entries()
    configuration = _configuration(entries)
    duplicate = configuration.bindings[0].model_copy(
        update={"binding_id": configuration.bindings[1].binding_id}
    )
    with pytest.raises(ValidationError, match="binding ids"):
        ActiveConfiguration.model_validate(
            configuration.model_copy(update={"bindings": (duplicate, *configuration.bindings[1:])})
        )
    duplicate_kind = configuration.bindings[0].model_copy(
        update={
            "binding_id": "m2601.binding.fresh",
            "kind": configuration.bindings[1].kind,
        }
    )
    with pytest.raises(ValidationError, match="kinds must be unique"):
        ActiveConfiguration.model_validate(
            configuration.model_copy(
                update={"bindings": (duplicate_kind, *configuration.bindings[1:])}
            )
        )
    with pytest.raises(ValidationError, match="at least 7"):
        ActiveConfiguration(
            configuration_id=configuration.configuration_id,
            version=configuration.version,
            bindings=configuration.bindings[:-1],
            approved_by=configuration.approved_by,
            configuration_digest=configuration.configuration_digest,
        )


def test_registry_record_rejects_duplicate_and_unregistered_history() -> None:
    request = _request()
    duplicate_entry = request.entries[0].model_copy(
        update={"entry_id": request.entries[1].entry_id}
    )
    with pytest.raises(ValidationError, match="entry ids"):
        RegistryRecord(
            registry_id=request.registry_id,
            version=request.registry_version,
            entries=(duplicate_entry, *request.entries[1:]),
            history=request.history,
            lock_digest=sha256_digest(request.entries),
        )
    foreign = request.history[0].model_copy(update={"entry_id": "m2601.entry.foreign"})
    with pytest.raises(ValidationError, match="unknown entry"):
        RegistryRecord(
            registry_id=request.registry_id,
            version=request.registry_version,
            entries=request.entries,
            history=(foreign, *request.history[1:]),
            lock_digest=sha256_digest(request.entries),
        )
    non_register = tuple(
        event.model_copy(
            update={
                "event_type": RegistryEventType.ACTIVATE,
                "prior_digest": sha256_digest(event),
            }
        )
        for event in request.history
    )
    with pytest.raises(ValidationError, match="registration event"):
        RegistryRecord(
            registry_id=request.registry_id,
            version=request.registry_version,
            entries=request.entries,
            history=non_register,
            lock_digest=sha256_digest(request.entries),
        )


def test_request_rejects_duplicate_entries_and_missing_bound_kinds() -> None:
    request = _request()
    duplicate = request.entries[0].model_copy(update={"entry_id": request.entries[1].entry_id})
    with pytest.raises(ValidationError, match="registry entry ids"):
        type(request).model_validate(
            request.model_copy(update={"entries": (duplicate, *request.entries[1:])})
        )
    missing_binding = request.active_configuration.bindings[0].model_copy(
        update={"entry_id": "m2601.entry.foreign"}
    )
    configuration = request.active_configuration.model_copy(
        update={"bindings": (missing_binding, *request.active_configuration.bindings[1:])}
    )
    with pytest.raises(ValidationError, match="unknown entry"):
        type(request).model_validate(
            request.model_copy(update={"active_configuration": configuration})
        )
