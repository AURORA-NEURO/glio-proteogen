"""Focused M04-06 replay, boundary-sealing, and runtime lifecycle checks."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import copy
from datetime import timedelta
from typing import TYPE_CHECKING, cast

import pytest
from evals.m04_06.run import build_scenario_request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from glio_proteogen.adapters.api import create_app
from glio_proteogen.adapters.cli import app as cli_app
from glio_proteogen.contracts.m04_05 import result_payload_digest as m0405_result_digest
from glio_proteogen.contracts.m04_06 import (
    HarmonizeProteoformAnalysisRequest,
    ProteoformHarmonizationDisposition,
    ProteoformHarmonizationResult,
)
from glio_proteogen.contracts.m04_06 import (
    result_payload_digest as m0406_result_digest,
)
from glio_proteogen.contracts.m04_06.v1 import (
    _artifact_harmonization_receipt,
    _expected_harmonization_bundle,
    _issue_artifact_replay_capability,
    _issue_validated_request_capability,
    _ReplayedM0405Capability,
    _validate_request_with_artifact_capability,
    _validate_result_with_capability,
    _ValidatedM0406RequestCapability,
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
from glio_proteogen.modules.c04_proteoform_isoform.m04_06_harmonization import (
    engine as m0406_engine,
)

if TYPE_CHECKING:
    from pathlib import Path

_HTTP_OK = 200
_HTTP_FORBIDDEN = 403
_CLI_AUTHORIZATION_ERROR = 2


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


def test_api_and_cli_parse_once_then_execute_validated(
    accepted_request: HarmonizeProteoformAnalysisRequest,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    preparation_count = 0
    original = m0406_engine._prepare_harmonization_request_candidate

    def counted(candidate: object) -> object:
        nonlocal preparation_count
        preparation_count += 1
        return original(candidate)

    monkeypatch.setattr(
        m0406_engine,
        "_prepare_harmonization_request_candidate",
        counted,
    )
    body = canonical_json_bytes(accepted_request)
    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=body,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == _HTTP_OK
    assert preparation_count == 1
    api_result = ProteoformHarmonizationResult.model_validate_json(
        response.content,
        strict=True,
    )

    preparation_count = 0
    request_path = tmp_path / "request.json"
    request_path.write_bytes(body)
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-harmonization", "harmonize", str(request_path)],
    )
    assert cli.exit_code == 0
    assert preparation_count == 1
    cli_result = ProteoformHarmonizationResult.model_validate_json(
        cli.stdout,
        strict=True,
    )
    expected = M0406Service()._execute_validated(accepted_request)
    assert api_result == cli_result == expected


def test_api_and_cli_authorization_denials_preserve_boundary_status(
    accepted_request: HarmonizeProteoformAnalysisRequest,
    tmp_path: Path,
) -> None:
    denied = accepted_request.model_dump(mode="json")
    denied["context"]["references"]["consent"]["state"] = "withheld"
    body = canonical_json_bytes(denied)
    with TestClient(create_app(tmp_path / "denied-api.sqlite3")) as client:
        response = client.post(
            "/v1/modules/M04-06/harmonization",
            content=body,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == _HTTP_FORBIDDEN

    request_path = tmp_path / "denied-request.json"
    request_path.write_bytes(body)
    cli = CliRunner().invoke(
        cli_app,
        ["proteoform-harmonization", "harmonize", str(request_path)],
    )
    assert cli.exit_code == _CLI_AUTHORIZATION_ERROR
    assert "upstream controls do not authorize" in cli.stderr


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


def test_private_artifact_capability_is_nominal_identity_bound_and_snapshot_sealed() -> None:
    request = build_scenario_request("accepted")
    artifact = request.artifact_result
    receipt = _artifact_harmonization_receipt(artifact)
    capability = _issue_artifact_replay_capability(artifact, receipt)
    payload = request.model_dump(mode="python")
    payload["artifact_result"] = artifact
    assert _validate_request_with_artifact_capability(payload, capability) == request

    reconstructed = _ReplayedM0405Capability(
        seal=capability.seal,
        result=capability.result,
        result_digest=capability.result_digest,
        normalized_snapshot_digest=capability.normalized_snapshot_digest,
        model_snapshot_digest=capability.model_snapshot_digest,
        receipt=capability.receipt,
    )
    model_copy_payload = dict(payload)
    model_copy_payload["artifact_result"] = artifact.model_copy()
    for candidate, forged_capability in (
        (payload, copy(capability)),
        (payload, reconstructed),
        (model_copy_payload, capability),
    ):
        with pytest.raises(TypeError, match="artifact-result replay capability"):
            _validate_request_with_artifact_capability(candidate, forged_capability)

    object.__setattr__(artifact, "human_review_required", not artifact.human_review_required)
    with pytest.raises(TypeError, match="artifact-result replay capability"):
        _validate_request_with_artifact_capability(payload, capability)


def test_private_request_capability_rejects_copies_and_post_issue_mutation() -> None:
    result = harmonize_proteoform_analysis(build_scenario_request("accepted"))
    request = result.request
    bundle = _expected_harmonization_bundle(
        request,
        (
            result.analysis,
            result.transformation_manifest,
            result.technical_effect_diagnostics,
            result.invariant_diagnostics,
        ),
    )
    capability = _issue_validated_request_capability(
        request,
        bundle,
        result.result_digest,
    )
    assert _validate_result_with_capability(result, capability) == result

    reconstructed = _ValidatedM0406RequestCapability(
        seal=capability.seal,
        request=capability.request,
        request_digest=capability.request_digest,
        request_snapshot_digest=capability.request_snapshot_digest,
        policy_digest=capability.policy_digest,
        configuration_digest=capability.configuration_digest,
        artifact_result=capability.artifact_result,
        artifact_snapshot_digest=capability.artifact_snapshot_digest,
        bundle=capability.bundle,
        expected_result_digest=capability.expected_result_digest,
    )
    model_copy_result = result.model_copy(update={"request": request.model_copy()})
    for candidate, forged_capability in (
        (result, copy(capability)),
        (result, reconstructed),
        (model_copy_result, capability),
    ):
        with pytest.raises(TypeError, match="request-validation capability"):
            _validate_result_with_capability(candidate, forged_capability)

    object.__setattr__(request, "supersedes_result_digest", "sha256:" + ("f" * 64))
    with pytest.raises(TypeError, match="request-validation capability"):
        _validate_result_with_capability(result, capability)


def test_public_unsealed_result_validation_replays_and_rejects_forged_output() -> None:
    result = harmonize_proteoform_analysis(build_scenario_request("accepted"))
    forged = result.model_dump(mode="python")
    forged["human_review_required"] = True
    forged["result_digest"] = m0406_result_digest(forged)

    with pytest.raises(ValidationError, match="human-review flag"):
        ProteoformHarmonizationResult.model_validate(forged, strict=True)


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
