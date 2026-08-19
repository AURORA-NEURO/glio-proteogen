"""Runtime and replay tests for provisional M24-02 generation."""

from __future__ import annotations

import json

import pytest
from evals.m24_07.fixture import artifact, context

from glio_proteogen.contracts.m24_02 import (
    M2402_M2401_INPUT_MEDIA_TYPE,
    FixtureKind,
    GenerateBiomarkerPanelSyntheticTruthRequest,
    GenerationConfiguration,
    GenerationStatus,
)
from glio_proteogen.kernel.models import ArtifactReference, UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material import (
    m24_02_synthetic_truth_generator as m2402,
)

_EXPECTED_CASES = 5


def request() -> GenerateBiomarkerPanelSyntheticTruthRequest:
    return GenerateBiomarkerPanelSyntheticTruthRequest(
        request_id="m2402.test.request",
        context=context(),
        upstream_result=ArtifactReference(
            artifact_id="m2401.test.result",
            version="0.1.0-provisional",
            digest="sha256:" + "1" * 64,
            media_type=M2402_M2401_INPUT_MEDIA_TYPE,
        ),
        configuration=GenerationConfiguration(
            configuration_id="m2402.test.configuration",
            version="1.0.0",
            generator_name="locked-test-generator",
            seed=17,
            requested_fixture_kinds=(FixtureKind.NORMAL, FixtureKind.SHIFTED),
        ),
        requested_case_count=5,
        source_artifacts=(artifact("2"),),
    )


def test_generation_is_deterministic_and_replay_bound() -> None:
    service = m2402.M2402Service()
    first = service.evaluate(request())
    second = service.evaluate(json.dumps(request().model_dump(mode="json"), sort_keys=True))
    assert first.status is GenerationStatus.GENERATED
    assert first.corpus is not None
    assert len(first.corpus.cases) == _EXPECTED_CASES
    assert first.result_digest == second.result_digest
    assert service.verify_replay(first).result_digest == first.result_digest


def test_replay_rejects_self_rehashed_case_tampering() -> None:
    service = m2402.M2402Service()
    result = service.evaluate(request())
    assert result.corpus is not None
    changed_case = result.corpus.cases[0].model_copy(update={"truth_values": ("9.999999",)})
    changed_corpus = result.corpus.model_copy(
        update={"cases": (changed_case, *result.corpus.cases[1:])}
    )
    forged = result.model_copy(update={"corpus": changed_corpus})
    forged = type(forged).model_construct(
        **{**forged.__dict__, "result_digest": result.result_digest}
    )
    with pytest.raises(m2402.M2402ReplayError):
        service.verify_replay(forged)


def test_denied_control_and_invalid_upstream_fail_closed() -> None:
    typed = request()
    support = typed.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    denied = typed.model_copy(
        update={"context": typed.context.model_copy(
            update={"references": typed.context.references.model_copy(update={"support": support})}
        )}
    )
    with pytest.raises(m2402.AuthorizationError):
        m2402.M2402Service().evaluate(denied)
    bad = typed.model_copy(
        update={"upstream_result": typed.upstream_result.model_copy(update={"media_type": "bad"})}
    )
    with pytest.raises(ValueError, match="bind the provisional M24-01 sensitivity result"):
        m2402.M2402Service().evaluate(bad)


def test_plugin_requires_submission_and_preserves_replay() -> None:
    service = m2402.M2402Service()
    plugin = m2402.M2402Plugin(service)
    with pytest.raises(TypeError):
        plugin.validate(request())
    token = plugin.validate(m2402.SyntheticTruthSubmission(request().model_dump_json()))
    result = plugin.run(token)
    assert plugin.replay(result).result_digest == result.result_digest
