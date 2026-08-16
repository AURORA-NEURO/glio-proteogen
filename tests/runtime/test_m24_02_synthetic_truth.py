"""Runtime, replay, reproducibility, and fail-closed tests for M24-02."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m24_02 import FixtureKind, GenerationStatus
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m24_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2402AuthorizationError,
    M2402ReplayError,
    M2402Service,
    generate_biomarker_panel_synthetic_truth,
    preflight_m2402_authorization,
)
from tests.contract.test_m24_02_hardening import _request

_CASE_COUNT = 2
_CONTROL_COUNT = 7


def test_generator_emits_reproducible_corpus_and_replays() -> None:
    service = M2402Service()
    result = service.generate(_request())
    assert result.status is GenerationStatus.GENERATED
    assert result.corpus is not None
    assert result.manifest is not None
    assert len(result.corpus.cases) == _CASE_COUNT
    assert result.manifest.case_ids == tuple(case.case_id for case in result.corpus.cases)
    assert len(result.provenance.control_decisions) == _CONTROL_COUNT
    assert service.verify_replay(result).result_digest == result.result_digest


def test_generator_is_deterministic_across_typed_json_and_stateless_paths() -> None:
    service = M2402Service()
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.generate(request)
    parsed = service.generate(encoded)
    assert typed.result_digest == parsed.result_digest
    assert generate_biomarker_panel_synthetic_truth(request).result_digest == typed.result_digest


def test_generator_preserves_fixture_kind_and_analytic_recoverability() -> None:
    request = _request().model_copy(
        update={
            "configuration": _request().configuration.model_copy(
                update={
                    "requested_fixture_kinds": (
                        FixtureKind.NORMAL,
                        FixtureKind.MISSING,
                        FixtureKind.SHIFTED,
                        FixtureKind.ADVERSARIAL,
                    )
                }
            ),
            "requested_case_count": 4,
        }
    )
    result = M2402Service().generate(request)
    assert result.corpus is not None
    assert {case.fixture_kind for case in result.corpus.cases} == {
        FixtureKind.NORMAL,
        FixtureKind.MISSING,
        FixtureKind.SHIFTED,
        FixtureKind.ADVERSARIAL,
    }
    assert all(case.analytically_recoverable for case in result.corpus.cases)


def test_replay_rejects_identifier_digest_and_request_tampering() -> None:
    service = M2402Service()
    result = service.generate(_request())
    with pytest.raises(M2402ReplayError, match="identifier"):
        service.verify_replay(result.model_copy(update={"result_id": "tampered"}))
    with pytest.raises(M2402ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises(M2402ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))


def test_authorization_fails_closed_before_material_traversal() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    with pytest.raises(M2402AuthorizationError):
        M2402Service().generate(request.model_copy(update={"context": context}))


def test_hostile_mapping_fails_closed() -> None:
    class HostileMapping(Mapping[str, object]):
        def get(self, _field: str, _default: object = None) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __getitem__(self, _key: str) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    with pytest.raises(M2402AuthorizationError):
        preflight_m2402_authorization(HostileMapping())
