"""Runtime, replay, and fail-closed preflight tests for provisional M22-01."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from glio_proteogen.contracts.m22_01 import (
    AdjudicationStatus,
    CurateProteinRnaDiscordanceReferenceTruthRequest,
    CurationStatus,
)
from glio_proteogen.kernel.models import UpstreamDecisionState
from glio_proteogen.modules.c21_reference_material.m22_01_reference_truth_benchmark_curator import (
    M2201AuthorizationError,
    M2201Plugin,
    M2201ReplayError,
    M2201Service,
    ReferenceTruthSubmission,
    ValidatedM2201Request,
    curate_protein_rna_discordance_reference_truth,
    preflight_m2201_authorization,
)
from tests.adversarial.test_m2201_adversarial import _request


def test_curator_locks_complete_package_and_replays() -> None:
    service = M2201Service()
    result = service.curate(_request())
    assert result.status is CurationStatus.CURATED
    assert result.package is not None
    assert result.result_digest == service.verify_replay(result).result_digest


def test_curator_abstains_for_pending_adjudication_without_package() -> None:
    request = _request()
    pending = request.adjudications[0].model_copy(update={"status": AdjudicationStatus.REVIEWED})
    payload = request.model_dump(mode="python")
    payload["adjudications"] = (pending, *request.adjudications[1:])
    result = M2201Service().curate(CurateProteinRnaDiscordanceReferenceTruthRequest(**payload))
    assert result.status is CurationStatus.ABSTAINED
    assert result.package is None
    assert result.abstention_reason is not None
    assert result.findings


def test_authorization_fails_closed_before_material_traversal() -> None:
    request = _request()
    support = request.context.references.support.model_copy(
        update={"state": UpstreamDecisionState.REJECTED}
    )
    context = request.context.model_copy(
        update={"references": request.context.references.model_copy(update={"support": support})}
    )
    denied = request.model_copy(update={"context": context})
    with pytest.raises(M2201AuthorizationError):
        M2201Service().curate(denied)


def test_service_typed_and_json_inputs_share_canonical_path() -> None:
    service = M2201Service()
    request = _request()
    encoded = json.dumps(request.model_dump(mode="json"), separators=(",", ":"))
    typed = service.validate_request(request)
    parsed = service.validate_request(encoded)
    assert typed == parsed
    assert service.curate(typed).result_digest == service.curate(parsed).result_digest


def test_replay_rejects_request_identifier_and_digest_tampering() -> None:
    service = M2201Service()
    result = service.curate(_request())
    with pytest.raises(M2201ReplayError, match="identifier"):
        service.verify_replay(result.model_copy(update={"result_id": "m2201.result.tampered"}))
    with pytest.raises(M2201ReplayError, match="payload digest"):
        service.verify_replay(result.model_copy(update={"result_digest": "sha256:" + "f" * 64}))

    with pytest.raises(M2201ReplayError, match="request digest"):
        service.verify_replay(result.model_copy(update={"request_digest": "sha256:" + "a" * 64}))
    assert (
        curate_protein_rna_discordance_reference_truth(_request()).result_digest
        == result.result_digest
    )


def test_rejected_included_adjudication_abstains_with_lock_finding() -> None:
    request = _request()
    rejected = request.adjudications[0].model_copy(
        update={
            "status": AdjudicationStatus.REJECTED,
            "disagreement_statement": "Reviewers disagree on this included item.",
        }
    )
    payload = request.model_dump(mode="python")
    payload["adjudications"] = (rejected, *request.adjudications[1:])
    result = M2201Service().curate(type(request)(**payload))
    assert result.status is CurationStatus.ABSTAINED
    assert any(item.code.value == "lock_incomplete" for item in result.findings)


def test_hostile_mapping_fails_closed() -> None:
    class HostileMapping(Mapping[str, object]):
        def get(self, _field: str) -> object:  # type: ignore[override]
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __getitem__(self, _key: str) -> object:
            raise RuntimeError("hostile mapping")  # noqa: TRY003

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    with pytest.raises(M2201AuthorizationError):
        preflight_m2201_authorization(HostileMapping())


def test_plugin_token_rejects_forged_cross_instance_and_nested_mutation() -> None:
    request = _request()
    plugin = M2201Plugin(M2201Service())
    other = M2201Plugin(M2201Service())
    token = plugin.validate(ReferenceTruthSubmission(request=request))

    assert plugin.run(token).status is CurationStatus.CURATED

    forged = ValidatedM2201Request(request=token.request, _seal=token._seal)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged)
    with pytest.raises(TypeError, match="validated request token"):
        other.run(token)

    changed_reference = token.request.references[0].model_copy(update={"expected_label": "forged"})
    object.__setattr__(
        token.request,
        "references",
        (changed_reference, *token.request.references[1:]),
    )
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)
