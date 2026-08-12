"""Focused service and plugin lifecycle checks for M02-05."""

from __future__ import annotations

from typing import Any

import pytest
from evals.m02_05.run import build_scenario_request

from glio_proteogen.contracts.m02_05 import DetectionDisposition
from glio_proteogen.modules.c02_identification_qc.m02_05_artifact_detection import (
    IdentificationArtifactAuthorizationError,
    M0205Plugin,
    M0205Service,
)


def test_service_revalidates_mapping_and_executes() -> None:
    request = build_scenario_request()

    result = M0205Service().execute(request.model_dump(mode="python"))

    assert result.disposition is DetectionDisposition.ACCEPTED
    assert result.parent_target == "protein_subtype"
    assert result.mask_scope == "identification_evidence"


def test_plugin_strict_json_round_trip_and_descriptor() -> None:
    request = build_scenario_request()
    plugin = M0205Plugin(M0205Service())

    token = plugin.validate(request.model_dump_json())
    result = plugin.run(token)

    assert result.disposition is DetectionDisposition.ACCEPTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M02-05"
    assert plugin.descriptor().owner == "Clinical science"


def test_plugin_rejects_unvalidated_execution() -> None:
    plugin = M0205Plugin(M0205Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(build_scenario_request())  # type: ignore[arg-type]


class _HostileSignals:
    _MESSAGE = "signals were traversed"

    def __iter__(self) -> Any:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def test_service_authorizes_before_hostile_signal_traversal() -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["signals"] = _HostileSignals()

    with pytest.raises(IdentificationArtifactAuthorizationError):
        M0205Service.validate_request(payload)
