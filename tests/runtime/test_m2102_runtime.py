"""Runtime, replay, preflight and deterministic-generation tests for M21-02."""

from __future__ import annotations

import pytest
from evals.m21_02.fixture import build_request, denied_request
from pydantic import ValidationError

from glio_proteogen.contracts.m21_02 import (
    M2102_M2101_INPUT_MEDIA_TYPE,
    GenerationStatus,
)
from glio_proteogen.contracts.m21_02.canonical import result_payload_digest
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.modules.c21_reference_material.m21_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2102AuthorizationError,
    M2102ReplayError,
    M2102Service,
    generate_complex_activity_synthetic_truth,
    preflight_m2102_authorization,
)


def test_generation_is_deterministic_and_reproducible() -> None:
    request = build_request()
    service = M2102Service()
    first = service.generate(request)
    second = service.generate(request)
    assert first.status is GenerationStatus.GENERATED
    assert first.result_digest == second.result_digest
    assert first.request_digest == second.request_digest
    assert first.corpus is not None
    assert first.manifest is not None
    assert first.corpus.manifest == first.manifest
    assert len(first.corpus.cases) == request.requested_case_count
    assert {case.fixture_kind for case in first.corpus.cases} == set(
        request.configuration.requested_fixture_kinds
    )
    assert tuple(case.seed for case in first.corpus.cases) == tuple(
        request.configuration.seed + index for index in range(request.requested_case_count)
    )
    assert all("raw" not in value for case in first.corpus.cases for value in case.truth_values)


def test_replay_rejects_request_and_result_tampering() -> None:
    service = M2102Service()
    result = service.generate(build_request())
    assert service.replay(result).result_digest == result.result_digest
    with pytest.raises(M2102ReplayError, match="request digest"):
        service.replay(result.model_copy(update={"request_digest": sha256_digest("tampered")}))
    with pytest.raises(M2102ReplayError, match="payload digest"):
        service.replay(result.model_copy(update={"result_digest": sha256_digest("tampered")}))


def test_replay_rejects_self_rehashed_nested_case_tampering() -> None:
    service = M2102Service()
    result = service.generate(build_request())
    assert result.corpus is not None
    forged_case = result.corpus.cases[0].model_copy(
        update={"truth_values": ("truth:forged", "truth:forged-bounded")}
    )
    forged_corpus = result.corpus.model_copy(
        update={"cases": (forged_case, *result.corpus.cases[1:])}
    )
    forged = result.model_copy(update={"corpus": forged_corpus})
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})
    with pytest.raises(M2102ReplayError, match="deterministic replay"):
        service.replay(forged)


def test_preflight_and_service_fail_closed_before_generation() -> None:
    with pytest.raises(M2102AuthorizationError):
        preflight_m2102_authorization(object())
    with pytest.raises(M2102AuthorizationError):
        preflight_m2102_authorization({"context": {"references": {}}})
    with pytest.raises(M2102AuthorizationError):
        M2102Service().generate(denied_request())


def test_wrong_upstream_media_type_is_rejected() -> None:
    request = build_request()
    wrong = request.upstream_result.model_copy(update={"media_type": "application/json"})
    with pytest.raises(ValidationError, match="M21-01 curator result"):
        M2102Service().generate(request.model_copy(update={"upstream_result": wrong}))
    assert request.upstream_result.media_type == M2102_M2101_INPUT_MEDIA_TYPE


def test_public_generation_entrypoint_matches_service() -> None:
    request = build_request()
    assert (
        generate_complex_activity_synthetic_truth(request).result_digest
        == M2102Service().generate(request).result_digest
    )
