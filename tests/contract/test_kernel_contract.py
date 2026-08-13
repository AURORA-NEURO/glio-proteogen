"""Cross-module kernel invariants exercised by M01-01."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    EstimateState,
    UncertaintyEstimate,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from tests.m01_01_support import load_request

pytestmark = pytest.mark.contract


def test_canonical_json_supports_every_declared_primitive_family() -> None:
    payload = {
        "model": load_request("evaluate_conformant.valid.json"),
        "enum": EstimateState.ESTIMATED,
        "datetime": datetime(2026, 1, 1, tzinfo=UTC),
        "date": date(2026, 1, 1),
        "float": 1.25,
        "sequence": ("a", 1, True, None),
    }

    encoded = canonical_json_bytes(payload)

    assert b'"datetime":"2026-01-01T00:00:00.000000Z"' in encoded
    assert b'"enum":"estimated"' in encoded
    assert sha256_digest(payload).startswith("sha256:")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_canonical_json_rejects_nonfinite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="NaN and infinity"):
        canonical_json_bytes(value)


def test_canonical_json_rejects_unsupported_python_objects() -> None:
    with pytest.raises(TypeError, match="unsupported canonical JSON value"):
        canonical_json_bytes({1, 2})


def test_canonical_json_normalizes_equivalent_instants_and_signed_zero() -> None:
    utc_instant = datetime(2026, 1, 1, 12, tzinfo=UTC)
    offset_instant = utc_instant.astimezone(timezone(-timedelta(hours=5)))

    assert canonical_json_bytes(utc_instant) == canonical_json_bytes(offset_instant)
    assert canonical_json_bytes(-0.0) == canonical_json_bytes(0.0) == b"0.0"


@pytest.mark.parametrize(
    "mapping",
    [
        {1: "integer key"},
        {"1": "string key", 1: "colliding integer key"},
    ],
)
def test_canonical_json_rejects_non_string_and_mixed_mapping_keys(
    mapping: dict[object, str],
) -> None:
    with pytest.raises(TypeError, match="object keys must be strings"):
        canonical_json_bytes(mapping)


@pytest.mark.parametrize(
    ("state", "probability"),
    [
        (EstimateState.ESTIMATED, None),
        (EstimateState.NOT_ESTIMABLE, 0.5),
        (EstimateState.NOT_APPLICABLE, 0.5),
    ],
)
def test_uncertainty_probability_matches_estimate_state(
    state: EstimateState,
    probability: float | None,
) -> None:
    with pytest.raises(ValidationError):
        UncertaintyEstimate(state=state, probability=probability, rationale="Synthetic evidence.")


def test_minimal_plugin_abi_is_runtime_checkable() -> None:
    class SyntheticPlugin:
        def descriptor(self) -> ModuleDescriptor:
            return ModuleDescriptor(
                module_id="GLIO-PROTEOGEN-M01-01",
                title="Protocol and metadata specification",
                version="1.0.0",
                owner="Scientific engineering",
                safety_class="S2",
                gate="G0",
                prohibited_outputs=("treatment recommendations",),
            )

        def validate(self, request: object) -> object:
            return request

        def run(self, request: object) -> object:
            return request

    plugin = SyntheticPlugin()

    assert isinstance(plugin, ModulePlugin)
    assert plugin.descriptor().gate == "G0"
    assert plugin.run(plugin.validate("synthetic")) == "synthetic"
