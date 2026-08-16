"""Runtime, replay, and strict-adapter coverage for M23-02."""

from __future__ import annotations

import pytest

from glio_proteogen.contracts.m23_02 import FixtureKind
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material import (
    m23_02_synthetic_truth_simulation_generator as m2302,
)
from tests.adversarial.test_m2302_contract_adversarial import _request

_DIGEST_LENGTH = 71


def test_engine_generates_all_locked_fixture_kinds_and_replays() -> None:
    request = _request()
    engine = m2302.M2302Engine()

    result = engine.generate(request)

    assert result.status.value == "generated"
    assert result.parent_target == "variant peptide"
    assert result.emits_parent is False
    assert result.corpus is not None
    assert len(result.corpus.cases) == request.requested_case_count
    assert {case.fixture_kind for case in result.corpus.cases} == set(FixtureKind)
    assert result.corpus.manifest.reproducibility_digest.startswith("sha256:")
    assert len(result.corpus.manifest.reproducibility_digest) == _DIGEST_LENGTH
    assert result.provenance.module_id == "GLIO-PROTEOGEN-M23-02"
    assert result.uncertainty.support.state.value == "not_estimable"
    assert engine.replay(result) == result


def test_engine_rejects_any_denied_control_before_generation() -> None:
    request = _request().model_dump(mode="json")
    request["context"]["references"]["quality"]["state"] = "rejected"

    with pytest.raises(m2302.M2302AuthorizationError, match="seven accepted controls"):
        m2302.M2302Engine().generate(request)


def test_plugin_parses_once_and_service_verifies_canonical_result() -> None:
    request = _request()
    plugin = m2302.M2302Plugin(m2302.M2302Service())
    payload = canonical_json_bytes(request.model_dump(mode="json"))

    token = plugin.validate(payload)
    result = plugin.run(token)

    assert isinstance(token, m2302.ValidatedM2302Request)
    assert plugin.verify(result) == result
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M23-02"


def test_plugin_rejects_forged_token() -> None:
    request = _request()
    plugin = m2302.M2302Plugin()
    forged = m2302.ValidatedM2302Request(request=request, _seal=object())

    with pytest.raises(TypeError):
        plugin.run(forged)


def test_replay_rejects_tampered_case_payload() -> None:
    result = m2302.M2302Engine().generate(_request())
    tampered = result.model_dump(mode="python")
    tampered["corpus"]["cases"][0]["seed"] += 1

    with pytest.raises(m2302.M2302ReplayError, match="result is invalid"):
        m2302.M2302Engine().replay(tampered)
