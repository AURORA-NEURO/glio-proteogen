"""Runtime, replay, and strict-adapter coverage for M23-02."""

from __future__ import annotations

from importlib import import_module

import pytest

from glio_proteogen.contracts.m23_02 import FixtureKind, VariantPeptideSyntheticTruthResult
from glio_proteogen.contracts.m23_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c21_reference_material import (
    m23_02_synthetic_truth_simulation_generator as m2302,
)
from tests.adversarial.test_m2302_contract_adversarial import _request

m2302_engine = import_module(
    "glio_proteogen.modules.c21_reference_material."
    "m23_02_synthetic_truth_simulation_generator.engine"
)

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


def test_plugin_rejects_nested_request_mutation() -> None:
    request = _request()
    plugin = m2302.M2302Plugin()
    token = plugin.validate(request)
    object.__setattr__(token.request, "request_id", "m2302.tampered")
    with pytest.raises(TypeError):
        plugin.run(token)


def test_replay_rejects_tampered_case_payload() -> None:
    result = m2302.M2302Engine().generate(_request())
    tampered = result.model_dump(mode="python")
    tampered["corpus"]["cases"][0]["seed"] += 1

    with pytest.raises(m2302.M2302ReplayError, match="result is invalid"):
        m2302.M2302Engine().replay(tampered)


def test_generation_safely_wraps_result_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExplodingAdapter:
        def validate_python(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("internal adapter detail")  # noqa: TRY003

    monkeypatch.setattr(m2302_engine, "_RESULT_ADAPTER", ExplodingAdapter())
    with pytest.raises(m2302.M2302EvaluationError, match="result construction failed safely"):
        m2302.M2302Engine().generate(_request())


def test_replay_rejects_forged_digest_after_strict_model_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = m2302.M2302Engine()
    result = engine.generate(_request())
    forged = result.model_copy(update={"result_digest": "sha256:" + ("f" * 64)})

    with pytest.raises(m2302.M2302ReplayError, match="payload digest mismatch"):
        engine.replay(forged)

    class ReplayAdapter:
        def validate_python(self, *_args: object, **_kwargs: object) -> object:
            return forged

    monkeypatch.setattr(m2302_engine, "_RESULT_ADAPTER", ReplayAdapter())

    with pytest.raises(m2302.M2302ReplayError, match="payload digest mismatch"):
        engine.replay(result.model_dump(mode="json"))


def test_replay_rejects_deterministic_payload_drift_with_recomputed_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = m2302.M2302Engine()
    result = engine.generate(_request())
    assert result.corpus is not None
    changed_cases = list(result.corpus.cases)
    changed_cases[0] = changed_cases[0].model_copy(update={"truth_values": ("999.0", "998.0")})
    changed_corpus = result.corpus.model_copy(update={"cases": tuple(changed_cases)})
    payload = result.__dict__.copy()
    payload["corpus"] = changed_corpus
    payload["manifest"] = changed_corpus.manifest
    provisional = VariantPeptideSyntheticTruthResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    forged = VariantPeptideSyntheticTruthResult.model_construct(**payload)
    adapter = m2302_engine._RESULT_ADAPTER

    class ReplayThenValidateAdapter:
        def __init__(self) -> None:
            self._calls = 0

        def validate_python(self, candidate: object, **kwargs: object) -> object:
            self._calls += 1
            if self._calls == 1:
                return forged
            return adapter.validate_python(candidate, **kwargs)

    monkeypatch.setattr(m2302_engine, "_RESULT_ADAPTER", ReplayThenValidateAdapter())

    with pytest.raises(m2302.M2302ReplayError, match="deterministic replay mismatch"):
        engine.replay(forged)
