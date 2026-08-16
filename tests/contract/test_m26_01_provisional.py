"""Focused contract/schema smoke for provisional M26-01."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from glio_proteogen.contracts.m26_01 import (
    M2601_OUTPUT_MEDIA_TYPE,
    M2601_PROVISIONAL_ABI,
    ActiveConfiguration,
    RegistryEntryKind,
    RegistryEventType,
    RegistryHistoryEvent,
    contract_json_schemas,
)

_SCHEMA_COUNT = 8


def test_provisional_schemas_require_registry_controls() -> None:
    schemas = cast("dict[str, dict[str, Any]]", contract_json_schemas())
    assert len(schemas) == _SCHEMA_COUNT
    assert all(schema["x-glio-contract"]["provisionalAbi"] for schema in schemas.values())
    assert all(schema["x-glio-contract"]["pendingOwnerConfirmation"] for schema in schemas.values())
    assert all(
        schema["x-glio-contract"]["registryKindsRequired"]
        and schema["x-glio-contract"]["immutableHistoryRequired"]
        and schema["x-glio-contract"]["activeConfigurationRequired"]
        and schema["x-glio-contract"]["unregisteredConfigurationBlocked"]
        and schema["x-glio-contract"]["quarantineUnresolvedInputs"]
        and schema["x-glio-contract"]["explicitAbstentionRequired"]
        and schema["x-glio-contract"]["unsupportedToNegative"] is False
        for schema in schemas.values()
    )
    assert all(
        schema["x-glio-contract"]["parentTarget"] == "protein subtype"
        for schema in schemas.values()
    )
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M2601_OUTPUT_MEDIA_TYPE
    assert M2601_PROVISIONAL_ABI is True


def test_registry_history_and_configuration_invariants_are_explicit() -> None:
    assert RegistryEntryKind.INTENDED_USE.value == "intended_use"
    with pytest.raises(ValidationError, match="register events cannot carry a prior digest"):
        RegistryHistoryEvent(
            event_id="event-1",
            entry_id="entry-1",
            event_type=RegistryEventType.REGISTER,
            prior_digest="sha256:" + "a" * 64,
            new_digest="sha256:" + "b" * 64,
            actor_id="actor-1",
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            reason="initial registration",
        )
    with pytest.raises(ValidationError, match="at least 7 item"):
        ActiveConfiguration(
            configuration_id="config-1",
            version="1.0.0",
            bindings=(),
            approved_by="reviewer-1",
            configuration_digest="sha256:" + "c" * 64,
        )
