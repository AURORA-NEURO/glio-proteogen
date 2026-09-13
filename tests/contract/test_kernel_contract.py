"""Cross-module kernel invariants exercised by M01-01."""

from __future__ import annotations

import json
import math
from collections import UserDict, UserList
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from enum import Enum, StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import (
    EstimateState,
    UncertaintyEstimate,
)
from glio_proteogen.kernel.plugin import ModuleDescriptor, ModulePlugin
from tests.m01_01_support import load_request

pytestmark = pytest.mark.contract


class _StringSubclass(str):
    __slots__ = ()


class _IntegerSubclass(int):
    pass


class _FloatSubclass(float):
    pass


class _DictSubclass(dict[str, object]):
    pass


class _ListSubclass(list[object]):
    pass


class _CanonicalState(StrEnum):
    READY = "ready"


class _CanonicalModel(BaseModel):
    label: str


def _legacy_json_ready(value: Any) -> Any:  # noqa: C901, PLR0911
    """Reproduce the pre-fast-path traversal order as a test oracle."""

    if isinstance(value, BaseModel):
        return _legacy_json_ready(
            value.model_dump(mode="python", by_alias=True, exclude_none=False)
        )
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        instant = value.astimezone(UTC) if value.utcoffset() is not None else value
        normalized = instant.isoformat(timespec="microseconds")
        return normalized.replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("canonical JSON forbids NaN and infinity")  # noqa: TRY003
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")  # noqa: TRY003
        return {key: _legacy_json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_legacy_json_ready(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(  # noqa: TRY003
        f"unsupported canonical JSON value: {type(value).__name__}"
    )


def _legacy_canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _legacy_json_ready(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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


@pytest.mark.parametrize(
    "value",
    [
        None,
        "exact-string",
        17,
        True,
        1.25,
        {"nested": ["value", 3, False, None]},
        ["list", {"value": 2}],
        ("tuple", {"value": 2}),
        _StringSubclass("string-subclass"),
        _IntegerSubclass(23),
        _FloatSubclass(-0.0),
        _DictSubclass({"dict-subclass": (1, 2)}),
        _ListSubclass(["list-subclass", 5]),
        UserDict({"custom-mapping": ("a", "b")}),
        UserList(["custom-sequence", {"value": 7}]),
        _CanonicalState.READY,
        date(2026, 1, 2),
        datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        _CanonicalModel(label="base-model"),
    ],
)
def test_canonical_fast_path_matches_legacy_traversal(value: object) -> None:
    assert canonical_json_bytes(value) == _legacy_canonical_json_bytes(value)


@pytest.mark.parametrize(
    "value",
    [
        _FloatSubclass(float("nan")),
        _FloatSubclass(float("inf")),
        _FloatSubclass(-float("inf")),
    ],
)
def test_canonical_float_subclasses_retain_nonfinite_rejection(value: float) -> None:
    with pytest.raises(ValueError, match="NaN and infinity"):
        canonical_json_bytes(value)


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
