"""Hostile-input, strict-JSON, and sealed-capability boundaries for M04-05."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import NoReturn
from unittest.mock import patch

import pytest
from evals.m04_05.run import build_scenario_request
from pydantic import BaseModel

from glio_proteogen.contracts.m04_04 import ProteoformQualityDisposition
from glio_proteogen.contracts.m04_05 import (
    M0405_MAX_CANONICAL_REQUEST_BYTES,
    M0405_MAX_EVENTS,
    DetectProteoformArtifactsRequest,
    ProteoformArtifactEvidenceLedger,
)
from glio_proteogen.contracts.m04_05.v1 import (
    _issue_quality_replay_capability,
    _quality_capability_is_issued,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.strict_json import StrictJsonError
from glio_proteogen.kernel.strict_json import strict_json_loads as real_strict_json_loads
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    M0405Plugin,
    M0405Service,
    ProteoformArtifactAuthorizationError,
    ProteoformArtifactInputError,
    ValidatedM0405Request,
    detect_proteoform_artifacts,
    preflight_proteoform_artifact_authorization,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    engine as m0405_engine,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    plugin as m0405_plugin,
)


class _TraversalTrap:
    touches = 0

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_") or name == "touches":
            return object.__getattribute__(self, name)
        type(self).touches += 1
        raise _TraversalDetectedError


class _TraversalDetectedError(AssertionError):
    pass


class _HostileEvents(list[object]):
    touches = 0

    def __len__(self) -> int:
        type(self).touches += 1
        raise _TraversalDetectedError

    def __iter__(self) -> Iterator[object]:
        type(self).touches += 1
        raise _TraversalDetectedError

    def __getitem__(self, key: object) -> object:
        del key
        type(self).touches += 1
        raise _TraversalDetectedError


class _OversizeEvents(list[object]):
    touches = 0

    def __iter__(self) -> Iterator[object]:
        type(self).touches += 1
        raise _TraversalDetectedError

    def __getitem__(self, key: object) -> object:
        del key
        type(self).touches += 1
        raise _TraversalDetectedError


class _HostileMapping(Mapping[str, object]):
    touches = 0

    def _fail(self) -> NoReturn:
        type(self).touches += 1
        raise _TraversalDetectedError

    def __getitem__(self, key: str) -> object:
        del key
        self._fail()

    def __iter__(self) -> Iterator[str]:
        self._fail()

    def __len__(self) -> int:  # noqa: PLE0303 - intentional hostile mapping.
        self._fail()


@pytest.fixture(scope="module")
def canonical_request() -> DetectProteoformArtifactsRequest:
    return build_scenario_request()


def test_plugin_decodes_json_once_and_token_is_unforgeable(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    plugin = M0405Plugin(M0405Service())
    calls = 0

    def counted(value: bytes | bytearray | str, *, max_bytes: int) -> object:
        nonlocal calls
        calls += 1
        return real_strict_json_loads(value, max_bytes=max_bytes)

    with patch.object(m0405_plugin, "strict_json_loads", counted):
        token = plugin.validate(canonical_json_bytes(canonical_request))
    assert calls == 1
    expected = detect_proteoform_artifacts(canonical_request)
    assert plugin.run(token) == expected

    mutated = token.request.model_copy(
        update={"request_id": "request.m0405." + ("1" * 64)}, deep=True
    )
    for forged in (
        ValidatedM0405Request(token.request, token._seal),
        ValidatedM0405Request(mutated, token._seal),
    ):
        with pytest.raises(TypeError, match="validated request token"):
            plugin.run(forged)


def test_upstream_capability_snapshots_the_entire_m0404_result(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    upstream = canonical_request.quality_result.model_copy(deep=True)
    capability = _issue_quality_replay_capability(upstream)
    assert _quality_capability_is_issued(capability)
    object.__setattr__(upstream, "disposition", ProteoformQualityDisposition.ABSTAINED)
    assert not _quality_capability_is_issued(capability)


@pytest.mark.parametrize(
    ("control", "state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "denied"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_seven_control_preflight_never_touches_quality_or_ledger(
    canonical_request: DetectProteoformArtifactsRequest,
    control: str,
    state: str,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["context"]["references"][control]["state"] = state  # type: ignore[index]
    payload["quality_result"] = _TraversalTrap()
    payload["evidence_ledger"] = _TraversalTrap()
    _TraversalTrap.touches = 0
    with pytest.raises(ProteoformArtifactAuthorizationError):
        preflight_proteoform_artifact_authorization(payload)
    assert _TraversalTrap.touches == 0


def test_non_string_colliding_key_is_rejected_without_hash_or_equality_hooks(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    class HostileKey:
        calls = 0

        def __hash__(self) -> int:
            type(self).calls += 1
            return hash("context")

        def __eq__(self, other: object) -> bool:
            del other
            type(self).calls += 1
            return True

    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload[HostileKey()] = "recursive-canary"  # type: ignore[index]
    HostileKey.calls = 0
    with pytest.raises(ProteoformArtifactAuthorizationError):
        preflight_proteoform_artifact_authorization(payload)
    assert HostileKey.calls == 0


def test_arbitrary_mapping_and_basemodel_outer_envelopes_are_never_traversed() -> None:
    class ForeignEnvelope(BaseModel):
        context: object

    _HostileMapping.touches = 0
    for candidate in (_HostileMapping(), ForeignEnvelope(context=_TraversalTrap())):
        with pytest.raises(ProteoformArtifactAuthorizationError):
            preflight_proteoform_artifact_authorization(candidate)
    assert _HostileMapping.touches == 0


def test_stale_ledger_binding_is_projected_without_event_traversal(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    ledger = payload["evidence_ledger"]
    assert isinstance(ledger, dict)
    ledger["quality_result_digest"] = sha256_digest({"stale": True})
    ledger["events"] = _HostileEvents()
    _HostileEvents.touches = 0
    result = detect_proteoform_artifacts(payload)
    assert result.disposition.value == "quarantined"
    assert result.artifact_posteriors == result.contamination_flags == result.exclusion_mask == ()
    assert _HostileEvents.touches == 0


def test_oversize_event_list_is_rejected_before_iteration(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    ledger = payload["evidence_ledger"]
    assert isinstance(ledger, dict)
    ledger["events"] = _OversizeEvents([None] * (M0405_MAX_EVENTS + 1))
    _OversizeEvents.touches = 0
    with pytest.raises(TypeError, match="exact built-in containers"):
        detect_proteoform_artifacts(payload)
    assert _OversizeEvents.touches == 0


def test_unsupported_configuration_classifies_before_ledger_traversal() -> None:
    payload = build_scenario_request("unsupported_configuration").model_dump(
        mode="python", exclude_none=False
    )
    payload["evidence_ledger"] = _TraversalTrap()
    _TraversalTrap.touches = 0
    with pytest.raises(ValueError, match="prohibits ledger traversal"):
        detect_proteoform_artifacts(payload)
    assert _TraversalTrap.touches == 0


def test_strict_json_rejects_duplicates_unknowns_coercion_and_cap(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    plugin = M0405Plugin(M0405Service())
    serialized = canonical_json_bytes(canonical_request)
    duplicate = b'{"operation":"detect_proteoform_artifacts",' + serialized[1:]
    with pytest.raises(StrictJsonError):
        plugin.validate(duplicate)

    unknown = canonical_request.model_dump(mode="json")
    unknown["recursive_canary"] = True
    with pytest.raises(ProteoformArtifactInputError):
        plugin.validate(canonical_json_bytes(unknown))

    coerced = canonical_request.model_dump(mode="json")
    coerced["contract_version"] = 1
    with pytest.raises(ProteoformArtifactInputError):
        plugin.validate(canonical_json_bytes(coerced))

    with pytest.raises(StrictJsonError):
        plugin.validate(b" " * (M0405_MAX_CANONICAL_REQUEST_BYTES + 1))


@pytest.mark.parametrize(
    "surface",
    [
        "policy",
        "profile",
        "threshold",
        "ledger",
        "event",
        "approved_configuration",
        "quality",
    ],
)
def test_owned_evidence_namespace_rejects_recursive_canary(
    canonical_request: DetectProteoformArtifactsRequest,
    surface: str,
) -> None:
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    policy = payload["policy"]  # type: ignore[assignment]
    ledger = payload["evidence_ledger"]  # type: ignore[assignment]
    context = payload["context"]  # type: ignore[assignment]
    assert isinstance(policy, dict)
    assert isinstance(ledger, dict)
    assert isinstance(context, dict)
    profile = policy["profiles"][0]
    references = context["references"]
    evidence_by_surface = {
        "policy": policy["evidence"],
        "profile": profile["evidence"],
        "threshold": profile["thresholds"][0]["evidence"],
        "ledger": ledger["evidence"],
        "event": ledger["events"][0]["evidence"][0],
        "approved_configuration": references["approved_configuration"]["evidence"],
        "quality": references["quality"]["evidence"],
    }
    evidence = evidence_by_surface[surface]
    assert isinstance(evidence, dict)
    evidence["artifact_id"] = "recursive-canary"
    with pytest.raises(ProteoformArtifactInputError) as captured:
        detect_proteoform_artifacts(payload)
    assert "recursive-canary" not in str(captured.value)


def test_preflight_sanitizes_exception_but_never_catches_baseexception(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    with (
        patch.object(m0405_engine, "_member", side_effect=RuntimeError("private-canary")),
        pytest.raises(ProteoformArtifactAuthorizationError) as sanitized,
    ):
        preflight_proteoform_artifact_authorization(canonical_request)
    assert "private-canary" not in str(sanitized.value)

    class Escape(BaseException):
        pass

    with (
        patch.object(m0405_engine, "_member", side_effect=Escape),
        pytest.raises(Escape),
    ):
        preflight_proteoform_artifact_authorization(canonical_request)


def test_correctly_bound_ledger_still_requires_full_self_digest_validation(
    canonical_request: DetectProteoformArtifactsRequest,
) -> None:
    ledger = canonical_request.evidence_ledger
    assert type(ledger) is ProteoformArtifactEvidenceLedger
    payload = canonical_request.model_dump(mode="python", exclude_none=False)
    payload["evidence_ledger"]["ledger_digest"] = "sha256:" + ("f" * 64)  # type: ignore[index]
    with pytest.raises(ProteoformArtifactInputError, match="strict validation"):
        detect_proteoform_artifacts(payload)
