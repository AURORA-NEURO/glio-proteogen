"""Focused M04-06 replay, boundary-sealing, and runtime lifecycle checks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import copy
from datetime import timedelta
from typing import cast

import pytest
from evals.m04_06.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m04_05 import result_payload_digest as m0405_result_digest
from glio_proteogen.contracts.m04_06 import (
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizationDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    M0406Plugin,
    M0406ProteoformHarmonizationEngine,
    M0406Service,
    ProteoformHarmonizationAuthorizationError,
    ValidatedM0406Request,
    harmonize_proteoform_analysis,
)


class _HostileValue(Mapping[str, object]):
    def __init__(self) -> None:
        self.accesses = 0

    def __getitem__(self, key: str) -> object:
        self.accesses += 1
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        self.accesses += 1
        raise AssertionError

    def __len__(self) -> int:
        self.accesses += 1
        raise AssertionError


class _CollidingKey:
    def __init__(self) -> None:
        self.comparisons = 0

    def __hash__(self) -> int:
        return hash("context")

    def __eq__(self, other: object) -> bool:
        self.comparisons += 1
        return other == "context"


@pytest.fixture(scope="module")
def accepted_request() -> HarmonizeProteoformAnalysisRequest:
    return build_scenario_request("accepted")


def test_engine_service_plugin_and_json_model_paths_are_identical(
    accepted_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    direct = harmonize_proteoform_analysis(accepted_request)
    engine = M0406ProteoformHarmonizationEngine().harmonize(accepted_request)
    service = M0406Service()
    serviced = service.execute(accepted_request)
    plugin = M0406Plugin(service)
    model_token = plugin.validate(accepted_request)
    json_token = plugin.validate(canonical_json_bytes(accepted_request))

    assert direct == engine == serviced == plugin.run(model_token) == plugin.run(json_token)
    assert direct.disposition is ProteoformHarmonizationDisposition.ACCEPTED


def test_request_ingress_replaces_reordered_existing_upstream_model(
    accepted_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    original = accepted_request.artifact_result
    reordered = original.model_copy(update={"evidence": tuple(reversed(original.evidence))})
    payload = accepted_request.model_dump(mode="python")
    payload["artifact_result"] = reordered

    sealed = HarmonizeProteoformAnalysisRequest.model_validate(payload, strict=True)

    assert sealed.artifact_result == original
    assert sealed.artifact_result is not reordered
    assert sealed.artifact_result.evidence == original.evidence


def test_request_ingress_rejects_resigned_upstream_forgery(
    accepted_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    original = accepted_request.artifact_result
    forged = original.model_copy(
        update={"completed_at": original.completed_at + timedelta(seconds=1)}
    )
    forged = forged.model_copy(update={"result_digest": m0405_result_digest(forged)})
    payload = accepted_request.model_dump(mode="python")
    payload["artifact_result"] = forged

    with pytest.raises(ValidationError):
        HarmonizeProteoformAnalysisRequest.model_validate(payload, strict=True)


def test_plugin_rejects_constructed_copied_and_model_copy_tokens(
    accepted_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    plugin = M0406Plugin(M0406Service())
    token = plugin.validate(accepted_request)
    for forged in (
        ValidatedM0406Request(request=token.request, _seal=token._seal),
        copy(token),
        ValidatedM0406Request(
            request=token.request.model_copy(),
            _seal=token._seal,
        ),
    ):
        with pytest.raises(TypeError, match="validated request token"):
            plugin.run(forged)


def test_plugin_detects_mutated_upstream_full_result_with_stale_digest(
    accepted_request: HarmonizeProteoformAnalysisRequest,
) -> None:
    plugin = M0406Plugin(M0406Service())
    token = plugin.validate(accepted_request)
    artifact_result = token.request.artifact_result
    object.__setattr__(
        artifact_result,
        "human_review_required",
        not artifact_result.human_review_required,
    )

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_safe_failure_replay_never_accesses_supplied_ledger() -> None:
    request = build_scenario_request("abstained")
    hostile = _HostileValue()
    payload = request.model_dump(mode="python")
    payload["support_ledger"] = hostile

    result = harmonize_proteoform_analysis(payload)

    assert result.disposition is ProteoformHarmonizationDisposition.ABSTAINED
    assert hostile.accesses == 0


def test_denied_preflight_never_accesses_upstream_or_ledger() -> None:
    request = build_scenario_request("abstained")
    upstream = _HostileValue()
    ledger = _HostileValue()
    payload = request.model_dump(mode="python")
    payload["artifact_result"] = upstream
    payload["support_ledger"] = ledger
    payload["context"]["references"]["consent"]["state"] = "withheld"

    with pytest.raises(ProteoformHarmonizationAuthorizationError):
        harmonize_proteoform_analysis(payload)
    assert upstream.accesses == ledger.accesses == 0


def test_colliding_non_string_key_fails_without_equality_execution() -> None:
    key = _CollidingKey()
    candidate = cast("dict[str, object]", {key: object()})

    with pytest.raises(ProteoformHarmonizationAuthorizationError):
        harmonize_proteoform_analysis(candidate)
    assert key.comparisons == 0


def test_oversized_shallow_mapping_fails_without_upstream_access() -> None:
    upstream = _HostileValue()
    ledger = _HostileValue()
    candidate: dict[str, object] = {f"field_{index}": None for index in range(513)}
    candidate["artifact_result"] = upstream
    candidate["support_ledger"] = ledger

    with pytest.raises(ProteoformHarmonizationAuthorizationError):
        harmonize_proteoform_analysis(candidate)
    assert upstream.accesses == ledger.accesses == 0
