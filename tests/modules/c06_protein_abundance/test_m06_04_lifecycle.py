"""Lifecycle and immutable replay checks for M06-04."""

from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604Service,
)
from tests.contract.test_m06_04_hardening import _request

_CONTROL_COUNT = 7
_ORIGINAL_SEED = 7


def test_lifecycle_replay_is_exact_and_deterministic() -> None:
    request = _request()
    service = M0604Service()
    first = service.estimate(request)
    replay = service.estimate(request)

    assert first == replay
    assert first.request_digest == replay.request_digest
    assert first.result_digest == replay.result_digest


def test_changed_configuration_is_a_new_immutable_result() -> None:
    request = _request()
    original = M0604Service().estimate(request)
    configuration = request["configuration"].model_copy(update={"seed": 8})
    changed = dict(request)
    changed["configuration"] = configuration
    revised = M0604Service().estimate(changed)

    assert revised.request_digest != original.request_digest
    assert revised.result_digest != original.result_digest
    assert original.request.configuration.seed == _ORIGINAL_SEED


def test_supersession_digest_is_preserved() -> None:
    original = M0604Service().estimate(_request())
    superseding = _request()
    superseding["supersedes_result_digest"] = original.result_digest
    result = M0604Service().estimate(superseding)

    assert result.request.supersedes_result_digest == original.result_digest
    assert result.request_digest != original.request_digest


def test_result_retains_controls_and_uncertainty_dimensions() -> None:
    result = M0604Service().estimate(_request())

    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert result.uncertainty.measurement.state.value == "not_estimable"
    assert result.uncertainty.transport.state.value == "not_estimable"
    assert result.emits_parent is False
