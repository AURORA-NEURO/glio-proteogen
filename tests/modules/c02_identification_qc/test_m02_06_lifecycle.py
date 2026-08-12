"""Focused service and plugin lifecycle checks for M02-06."""

from __future__ import annotations

from collections.abc import Iterator, Mapping

import pytest
from evals.m02_06.run import build_scenario_request

from glio_proteogen.contracts.m02_06 import HarmonizationDisposition
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    IdentificationHarmonizationAuthorizationError,
    M0206Plugin,
    M0206Service,
)


def test_service_revalidates_mapping_and_executes() -> None:
    request = build_scenario_request()

    result = M0206Service().execute(request.model_dump(mode="python"))

    assert result.disposition is HarmonizationDisposition.ACCEPTED
    assert result.parent_target == "protein_subtype"


def test_plugin_strict_json_round_trip_and_descriptor() -> None:
    request = build_scenario_request()
    plugin = M0206Plugin(M0206Service())

    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)

    assert result.disposition is HarmonizationDisposition.ACCEPTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M02-06"
    assert plugin.descriptor().owner == "Data engineering"


def test_plugin_rejects_unvalidated_execution() -> None:
    plugin = M0206Plugin(M0206Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(build_scenario_request())  # type: ignore[arg-type]


class _HostileObservations(Mapping[str, object]):
    _MESSAGE = "observations were traversed"

    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def _denied_hostile_payload() -> dict[str, object]:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"  # type: ignore[index]
    payload["observations"] = _HostileObservations()
    return payload


def test_engine_service_and_plugin_authorize_before_hostile_traversal() -> None:
    payload = _denied_hostile_payload()

    with pytest.raises(IdentificationHarmonizationAuthorizationError):
        M0206Service.validate_request(payload)
    with pytest.raises(IdentificationHarmonizationAuthorizationError):
        M0206Service().execute(payload)
    with pytest.raises(IdentificationHarmonizationAuthorizationError):
        M0206Plugin(M0206Service()).validate(payload)
