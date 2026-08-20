"""Runtime, replay, and fail-closed preflight tests for provisional M22-02."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m22_02 import (
    FixtureKind,
    GenerationStatus,
    ProteinRnaDiscordanceSyntheticTruthResult,
)
from glio_proteogen.contracts.m22_02.canonical import result_payload_digest
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_02_synthetic_truth_simulation_generator import (  # noqa: E501
    M2202AuthorizationError,
    M2202Plugin,
    M2202ReplayError,
    M2202Service,
    SyntheticTruthSubmission,
    ValidatedM2202Request,
    generate_protein_rna_discordance_synthetic_truth,
    preflight_m2202_authorization,
)
from tests.contract.test_m22_02_hardening import _request


def test_generator_emits_all_requested_fixture_kinds_and_replays() -> None:
    request = _request().model_copy(
        update={
            "configuration": _request().configuration.model_copy(
                update={"requested_fixture_kinds": tuple(FixtureKind)}
            ),
            "requested_case_count": 5,
        }
    )
    service = M2202Service()
    result = service.generate(request)
    assert result.status is GenerationStatus.GENERATED
    assert result.corpus is not None
    assert tuple(item.fixture_kind for item in result.corpus.cases) == tuple(FixtureKind)
    assert result.manifest == result.corpus.manifest
    assert service.verify_replay(result).result_digest == result.result_digest


def test_generator_is_deterministic_across_typed_and_json_paths() -> None:
    service = M2202Service()
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.generate(request)
    parsed = service.generate(encoded)
    assert typed.result_digest == parsed.result_digest
    assert generate_protein_rna_discordance_synthetic_truth(request).result_digest == (
        typed.result_digest
    )


def test_replay_rejects_identifier_digest_and_request_tampering() -> None:
    service = M2202Service()
    result = service.generate(_request())
    with pytest.raises(M2202ReplayError, match="identifier"):
        service.verify_replay(result.model_copy(update={"result_id": "m2202.result.tampered"}))
    with pytest.raises(M2202ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))
    with pytest.raises(M2202ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))


def test_replay_rejects_recomputed_digest_for_forged_corpus() -> None:
    service = M2202Service()
    result = service.generate(_request())
    assert result.corpus is not None
    forged_case = result.corpus.cases[0].model_copy(update={"truth_values": ("forged",) * 3})
    forged_corpus = result.corpus.model_copy(
        update={"cases": (forged_case, *result.corpus.cases[1:])}
    )
    payload = result.model_dump(mode="python")
    payload["corpus"] = forged_corpus
    provisional = ProteinRnaDiscordanceSyntheticTruthResult.model_construct(**payload)
    payload["result_digest"] = result_payload_digest(provisional)
    forged = ProteinRnaDiscordanceSyntheticTruthResult.model_validate(payload, strict=True)
    with pytest.raises(M2202ReplayError, match="output mismatch"):
        service.verify_replay(forged)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("module_version", "9.9.9"),
        ("configuration_digest", "sha256:" + "f" * 64),
        ("input_digests", ("sha256:" + "f" * 64,)),
    ],
)
def test_replay_rejects_self_rehashed_provenance_binding_forgery(
    field: str,
    value: object,
) -> None:
    service = M2202Service()
    result = service.generate(_request())
    forged = result.model_copy(
        update={"provenance": result.provenance.model_copy(update={field: value})}
    )
    forged = forged.model_copy(update={"result_digest": result_payload_digest(forged)})

    with pytest.raises(M2202ReplayError):
        service.verify_replay(forged)


def test_authorization_fails_closed_before_material_traversal() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    with pytest.raises(M2202AuthorizationError):
        M2202Service().generate(request.model_copy(update={"context": context}))


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

    with pytest.raises(M2202AuthorizationError):
        preflight_m2202_authorization(HostileMapping())


def test_plugin_token_rejects_forged_cross_instance_and_nested_mutation() -> None:
    candidate = _request()
    plugin = M2202Plugin(M2202Service())
    other = M2202Plugin(M2202Service())
    token = plugin.validate(SyntheticTruthSubmission(request=candidate))

    assert plugin.run(token).status is GenerationStatus.GENERATED

    forged = ValidatedM2202Request(request=token.request, _seal=token._seal)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        other.run(token)

    changed_configuration = token.request.configuration.model_copy(
        update={"seed": 99}
    )
    object.__setattr__(token.request, "configuration", changed_configuration)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)
