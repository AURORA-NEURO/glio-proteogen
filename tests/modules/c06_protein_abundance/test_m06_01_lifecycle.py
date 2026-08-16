"""Lifecycle and immutable replay checks for M06-01."""

from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    M0601Service,
)
from tests.contract.test_m06_01_hardening import _request

_CONTROL_COUNT = 7


def test_lifecycle_replay_is_exact_and_deterministic() -> None:
    request = _request()
    first = M0601Service().execute(request)
    replay = M0601Service().execute(request.model_dump(mode="json"))

    assert first == replay
    assert first.request_digest == replay.request_digest
    assert first.result_digest == replay.result_digest


def test_changed_schema_is_a_new_immutable_result() -> None:
    request = _request()
    schema = request.state_schema.model_copy(update={"version": "1.0.1"})
    changed = request.model_copy(update={"state_schema": schema})
    original = M0601Service().execute(request)
    revised = M0601Service().execute(changed)

    assert revised.request_digest != original.request_digest
    assert revised.result_digest != original.result_digest
    assert original.request.state_schema.version == "1.0.0"


def test_supersession_digest_is_preserved() -> None:
    original = M0601Service().execute(_request())
    superseding = _request().model_copy(update={"supersedes_result_digest": original.result_digest})
    result = M0601Service().execute(superseding)

    assert result.request.supersedes_result_digest == original.result_digest
    assert result.request_digest != original.request_digest


def test_result_retains_all_seven_controls_and_uncertainty_dimensions() -> None:
    result = M0601Service().execute(_request())

    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.uncertainty.measurement.state.value == "not_estimable"
    assert result.uncertainty.transport.state.value == "not_estimable"
