"""Focused M04-07 engine, receipt, service, and plugin lifecycle checks."""

from __future__ import annotations

import copy
import gc
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast, overload
from weakref import ref

import pytest
from evals.m04_07.run import build_scenario, build_scenario_request

from glio_proteogen.contracts.m04_07 import (
    M0407_ZERO_DIGEST,
    ProteoformAbstentionCode,
    ProteoformDeclaredSupportState,
    ProteoformDimensionSupportDecision,
    ProteoformSupportDimension,
    ProteoformSupportDisposition,
    normalized_result,
)
from glio_proteogen.contracts.m04_07 import v1 as support_router_contract
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    compute_proteoform_quality_metrics,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    M0407Plugin,
    M0407Service,
    ProteoformSupportAuthorizationError,
    ProteoformSupportReceiptError,
    ValidatedM0407Request,
    proteoform_harmonization_support_receipt,
    proteoform_quality_support_receipt,
    proteoform_support_prerequisites,
    route_proteoform_support,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    engine as support_router_engine,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    plugin as support_router_plugin,
)

_PUBLIC_EXECUTE_CANARY = "public service execution reparsed an issued capability"
_PUBLIC_VALIDATE_CANARY = "public service validation reparsed strict JSON"
_HOSTILE_KEY_CANARY = "hostile key equality was invoked"
_HOSTILE_SEQUENCE_CANARY = "hostile sequence subclass access was invoked"
_HOSTILE_EQUALITY_CANARY = "hostile equality was invoked"
_HOSTILE_PREREQUISITE_CANARY = "hostile prerequisite accessor was invoked"
_EXPECTED_BUNDLE_ATTRIBUTE = "_expected_support_route_bundle"
_STRICT_JSON_LOADS_ATTRIBUTE = "strict_json_loads"
_EXPECTED_ROUTE_COUNT = 2


class _DerivedValidatedM0407Request(ValidatedM0407Request):
    __slots__ = ()


class _HostileEquality:
    __hash__ = object.__hash__

    def __init__(self) -> None:
        self.compared = False

    def __eq__(self, _other: object) -> bool:
        self.compared = True
        raise AssertionError(_HOSTILE_EQUALITY_CANARY)


class _HostilePrerequisiteReplacement:
    def __init__(self) -> None:
        self.touched = False

    @property
    def quality_result(self) -> object:
        self.touched = True
        raise AssertionError(_HOSTILE_PREREQUISITE_CANARY)

    @property
    def harmonization_result(self) -> object:
        self.touched = True
        raise AssertionError(_HOSTILE_PREREQUISITE_CANARY)


def test_genuine_receipt_builders_reconstruct_exact_compact_chain() -> None:
    scenario = build_scenario()
    prerequisites = scenario.request.prerequisites

    assert prerequisites.quality_result == scenario.quality_result
    assert prerequisites.harmonization_result == scenario.harmonization_result
    assert proteoform_quality_support_receipt(scenario.quality_result) == prerequisites.quality
    assert (
        proteoform_harmonization_support_receipt(scenario.harmonization_result)
        == prerequisites.harmonization
    )
    assert (
        proteoform_support_prerequisites(
            scenario.quality_result,
            scenario.harmonization_result,
        )
        == prerequisites
    )


def test_receipt_builders_reject_malformed_and_cross_chain_results() -> None:
    scenario = build_scenario()
    with pytest.raises(ProteoformSupportReceiptError, match="M04-04 result"):
        proteoform_quality_support_receipt({})
    with pytest.raises(ProteoformSupportReceiptError, match="M04-06 result"):
        proteoform_harmonization_support_receipt({})
    with pytest.raises(ProteoformSupportReceiptError, match="M04-04 result"):
        proteoform_quality_support_receipt(
            scenario.quality_result.model_copy(update={"result_digest": M0407_ZERO_DIGEST})
        )
    with pytest.raises(ProteoformSupportReceiptError, match="M04-06 result"):
        proteoform_harmonization_support_receipt(
            scenario.harmonization_result.model_copy(update={"result_digest": M0407_ZERO_DIGEST})
        )

    alternate_quality_request = scenario.quality_result.request.model_copy(
        update={"supersedes_result_digest": sha256_digest("prior-quality-result")}
    )
    alternate_quality = compute_proteoform_quality_metrics(alternate_quality_request)
    with pytest.raises(ProteoformSupportReceiptError, match="prerequisite chain"):
        proteoform_support_prerequisites(
            alternate_quality,
            scenario.harmonization_result,
        )

    stale_projection = scenario.request.model_dump(mode="python")
    stale_projection["prerequisites"]["quality_result"] = alternate_quality
    with pytest.raises(ValueError, match="exact projection"):
        route_proteoform_support(stale_projection)


def test_engine_service_and_plugin_replay_one_joint_envelope() -> None:
    request = build_scenario_request()
    direct = route_proteoform_support(request)
    service = M0407Service().execute(request)
    plugin = M0407Plugin(M0407Service())
    token = plugin.validate(request.model_dump_json())
    plugin_result = plugin.run(token)

    assert direct == service == plugin_result
    assert direct.disposition is ProteoformSupportDisposition.SUPPORTED
    assert len(direct.matched_envelope_ids) == 1
    assert len(direct.envelope_assessments) == 1
    assert not direct.abstention_reasons
    assert direct.human_review_required is False
    descriptor = plugin.descriptor()
    assert descriptor.module_id == "GLIO-PROTEOGEN-M04-07"
    assert descriptor.owner == "Computational biology"


def test_plugin_rejects_unvalidated_execution_capability() -> None:
    plugin = M0407Plugin(M0407Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", build_scenario_request()))


def _reverse_mapping_keys(value: object) -> object:
    if type(value) is dict:
        mapping = value
        return {key: _reverse_mapping_keys(mapping[key]) for key in reversed(tuple(mapping))}
    if type(value) is list:
        return [_reverse_mapping_keys(item) for item in value]
    return value


def test_plugin_typed_mapping_reordered_and_json_validation_are_exact_parity() -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="json")
    reordered = _reverse_mapping_keys(payload)
    assert type(reordered) is dict
    plugin = M0407Plugin(M0407Service())

    tokens = (
        plugin.validate(request),
        plugin.validate(payload),
        plugin.validate(reordered),
        plugin.validate(json.dumps(reordered)),
        plugin.validate(canonical_json_bytes(payload)),
    )
    results = tuple(plugin.run(token) for token in tokens)

    assert all(token.request == tokens[0].request for token in tokens)
    assert all(result == results[0] for result in results)


def test_plugin_capability_is_issued_identity_not_a_constructible_dataclass() -> None:
    plugin = M0407Plugin(M0407Service())
    issued = plugin.validate(build_scenario_request())
    copied_request = issued.request.model_copy()
    forged = (
        copy.copy(issued),
        copy.deepcopy(issued),
        replace(issued),
        ValidatedM0407Request(request=issued.request, _seal=issued._seal),
        ValidatedM0407Request(request=copied_request, _seal=issued._seal),
        _DerivedValidatedM0407Request(request=issued.request, _seal=issued._seal),
    )

    for token in forged:
        with pytest.raises(TypeError, match="validated request token"):
            plugin.run(token)


def test_plugin_capability_rejects_stale_digest_upstream_object_mutation() -> None:
    plugin = M0407Plugin(M0407Service())
    token = plugin.validate(build_scenario_request())
    upstream = token.request.prerequisites.harmonization_result
    original_result_digest = upstream.result_digest
    receipt = upstream.receipt

    object.__setattr__(receipt, "analysis_evaluable_target_count", 0)

    assert upstream.result_digest == original_result_digest
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_plugin_capability_binds_equal_upstream_object_identity() -> None:
    plugin = M0407Plugin(M0407Service())
    token = plugin.validate(build_scenario_request())
    prerequisites = token.request.prerequisites
    replacement = prerequisites.harmonization_result.model_copy(deep=True)

    assert replacement == prerequisites.harmonization_result
    object.__setattr__(prerequisites, "harmonization_result", replacement)

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)


def test_plugin_capability_binds_exact_prerequisite_identity_before_access() -> None:
    plugin = M0407Plugin(M0407Service())
    token = plugin.validate(build_scenario_request())
    request = token.request
    prerequisites = request.prerequisites
    replacement = prerequisites.model_copy()

    assert replacement == prerequisites
    assert replacement.quality_result is prerequisites.quality_result
    assert replacement.harmonization_result is prerequisites.harmonization_result
    object.__setattr__(request, "prerequisites", replacement)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)

    hostile = _HostilePrerequisiteReplacement()
    object.__setattr__(request, "prerequisites", hostile)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)
    assert hostile.touched is False


def test_plugin_capability_rejects_wrong_typed_request_without_equality() -> None:
    plugin = M0407Plugin(M0407Service())
    token = plugin.validate(build_scenario_request())
    hostile = _HostileEquality()
    object.__setattr__(token, "request", hostile)

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(token)

    assert hostile.compared is False


def test_internal_prerequisite_capability_requires_issuance_and_preserves_identity() -> None:
    prepared = support_router_engine._prepare_support_request_candidate(build_scenario_request())
    payload, issued = prepared
    validated = support_router_engine._validate_prepared_request(prepared)

    assert validated.prerequisites is issued.prerequisites
    for forged in (copy.copy(issued), deepcopy(issued), replace(issued)):
        with pytest.raises(TypeError, match="prerequisite replay capability"):
            support_router_contract._validate_request_with_prerequisites_capability(
                payload,
                forged,
            )


def test_internal_prerequisite_capability_fields_and_snapshot_fail_without_callbacks() -> None:
    _payload, capability = support_router_engine._prepare_support_request_candidate(
        build_scenario_request()
    )
    assert support_router_contract._prerequisites_capability_is_issued(capability) is True

    for field in (
        "prerequisites",
        "quality_result",
        "harmonization_result",
        "normalized_snapshot_digest",
    ):
        original = getattr(capability, field)
        hostile: _HostileEquality | _HostilePrerequisiteReplacement = (
            _HostilePrerequisiteReplacement() if field == "prerequisites" else _HostileEquality()
        )
        object.__setattr__(capability, field, hostile)
        try:
            assert support_router_contract._prerequisites_capability_is_issued(capability) is False
            if isinstance(hostile, _HostilePrerequisiteReplacement):
                assert hostile.touched is False
            else:
                assert hostile.compared is False
        finally:
            object.__setattr__(capability, field, original)

    with support_router_contract._VALIDATION_CAPABILITY_LOCK:
        original_snapshot = support_router_contract._ISSUED_PREREQUISITES_CAPABILITIES[capability]
    for index in range(len(original_snapshot)):
        hostile = _HostileEquality()
        corrupted = list(original_snapshot)
        corrupted[index] = hostile
        with support_router_contract._VALIDATION_CAPABILITY_LOCK:
            cast("Any", support_router_contract._ISSUED_PREREQUISITES_CAPABILITIES)[capability] = (
                tuple(corrupted)
            )
        try:
            assert support_router_contract._prerequisites_capability_is_issued(capability) is False
            assert hostile.compared is False
        finally:
            with support_router_contract._VALIDATION_CAPABILITY_LOCK:
                support_router_contract._ISSUED_PREREQUISITES_CAPABILITIES[capability] = (
                    original_snapshot
                )


def test_owned_result_derives_once_then_validates_the_sealed_full_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cast(
        "Callable[[object], object]",
        support_router_contract._expected_support_route_bundle,
    )
    derivation_count = 0

    def count_bundle(request: object) -> object:
        nonlocal derivation_count
        derivation_count += 1
        return original(request)

    monkeypatch.setattr(support_router_contract, "_expected_support_route_bundle", count_bundle)
    monkeypatch.setattr(support_router_engine, "_expected_support_route_bundle", count_bundle)

    result = route_proteoform_support(build_scenario_request())

    assert result.disposition is ProteoformSupportDisposition.SUPPORTED
    assert derivation_count == 1


def test_public_route_reuses_only_one_fully_admitted_exact_request_and_rederives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_scenario_request()
    original_prepare = cast(
        "Callable[[object], object]",
        support_router_engine._prepare_support_request_candidate,
    )
    original_bundle = cast(
        "Callable[[object], object]",
        getattr(support_router_engine, _EXPECTED_BUNDLE_ATTRIBUTE),
    )
    prepare_count = 0
    bundle_count = 0

    def count_prepare(candidate: object) -> object:
        nonlocal prepare_count
        prepare_count += 1
        return original_prepare(candidate)

    def count_bundle(candidate: object) -> object:
        nonlocal bundle_count
        bundle_count += 1
        return original_bundle(candidate)

    monkeypatch.setattr(
        support_router_engine,
        "_prepare_support_request_candidate",
        count_prepare,
    )
    monkeypatch.setattr(support_router_engine, "_expected_support_route_bundle", count_bundle)
    monkeypatch.setattr(support_router_contract, "_expected_support_route_bundle", count_bundle)

    first = route_proteoform_support(request)
    second = route_proteoform_support(request)

    assert first == second
    assert prepare_count == 1
    assert bundle_count == _EXPECTED_ROUTE_COUNT


def test_admission_capability_and_equal_request_copies_cannot_reuse_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    capability = support_router_engine._ADMISSION_CACHE[id(request)][1]
    for forged in (copy.copy(capability), replace(capability)):
        assert support_router_engine._admission_capability_is_issued(forged, request) is False

    candidates = (copy.copy(request), request.model_copy(), request.model_dump(mode="python"))
    assert all(candidate is not request for candidate in candidates)

    class FullAdmissionRequiredError(RuntimeError):
        pass

    def fail_full_admission(_candidate: object) -> object:
        raise FullAdmissionRequiredError

    monkeypatch.setattr(
        support_router_engine,
        "_prepare_support_request_candidate",
        fail_full_admission,
    )
    for candidate in candidates:
        with pytest.raises(FullAdmissionRequiredError):
            route_proteoform_support(candidate)


def test_admission_capability_rejects_stale_request_and_upstream_mutation() -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    original_request_id = request.request_id
    object.__setattr__(
        request,
        "request_id",
        "request." + sha256_digest("stale-admitted-request").removeprefix("sha256:"),
    )
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)
    object.__setattr__(request, "request_id", original_request_id)

    route_proteoform_support(request)
    harmonization = request.prerequisites.harmonization_result
    original_digest = harmonization.result_digest
    object.__setattr__(harmonization, "result_digest", M0407_ZERO_DIGEST)
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)
    object.__setattr__(harmonization, "result_digest", original_digest)


def test_admission_capability_binds_exact_prerequisite_identity_before_access() -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    prerequisites = request.prerequisites
    replacement = prerequisites.model_copy()

    assert replacement == prerequisites
    assert replacement.quality_result is prerequisites.quality_result
    assert replacement.harmonization_result is prerequisites.harmonization_result
    object.__setattr__(request, "prerequisites", replacement)
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)

    request = build_scenario_request()
    route_proteoform_support(request)
    hostile = _HostilePrerequisiteReplacement()
    object.__setattr__(request, "prerequisites", hostile)
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)
    assert hostile.touched is False


@pytest.mark.parametrize(
    "field",
    [
        "source_request",
        "source_identity",
        "validated_request",
        "request_digest",
        "raw_snapshot",
        "normalized_snapshot",
    ],
)
def test_admission_capability_rejects_wrong_typed_fields_without_equality(
    field: str,
) -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    capability = support_router_engine._ADMISSION_CACHE[id(request)][1]
    original = getattr(capability, field)
    hostile = _HostileEquality()
    object.__setattr__(capability, field, hostile)

    try:
        assert support_router_engine._admission_capability_is_issued(capability, request) is False
        assert hostile.compared is False
    finally:
        object.__setattr__(capability, field, original)


def test_admission_capability_rejects_nested_stale_source_and_validated_state() -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    capability = support_router_engine._ADMISSION_CACHE[id(request)][1]
    source_analysis = request.prerequisites.harmonization_result.analysis
    assert source_analysis is not None
    source_count = source_analysis.target_count
    object.__setattr__(source_analysis, "target_count", source_count - 1)
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)
    object.__setattr__(source_analysis, "target_count", source_count)

    request = build_scenario_request()
    route_proteoform_support(request)
    capability = support_router_engine._ADMISSION_CACHE[id(request)][1]
    validated_analysis = capability.validated_request.prerequisites.harmonization_result.analysis
    assert validated_analysis is not None
    validated_count = validated_analysis.target_count
    object.__setattr__(validated_analysis, "target_count", validated_count - 1)
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)
    object.__setattr__(validated_analysis, "target_count", validated_count)


def test_admission_cache_drops_dead_source_and_warm_concurrency_is_deterministic() -> None:
    request = build_scenario_request()
    expected = route_proteoform_support(request)
    identity = id(request)
    source_reference = ref(request)

    with ThreadPoolExecutor(max_workers=4) as executor:
        candidates = (request,) * 4
        results = tuple(executor.map(route_proteoform_support, candidates))

    assert results == (expected,) * 4
    del candidates
    del request
    gc.collect()
    assert source_reference() is None
    assert identity not in support_router_engine._ADMISSION_CACHE


def test_admission_capability_rejects_mutated_cached_request() -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    capability = support_router_engine._ADMISSION_CACHE[id(request)][1]
    validated = capability.validated_request
    original_request_id = validated.request_id
    object.__setattr__(
        validated,
        "request_id",
        "request." + sha256_digest("stale-cached-request").removeprefix("sha256:"),
    )
    with pytest.raises(TypeError, match="admitted request capability"):
        route_proteoform_support(request)
    object.__setattr__(validated, "request_id", original_request_id)


def test_cached_admission_still_preflights_all_controls() -> None:
    request = build_scenario_request()
    route_proteoform_support(request)
    references = request.context.references
    denied = references.model_copy(
        update={
            "consent": references.consent.model_copy(update={"state": "withheld"}),
        }
    )
    object.__setattr__(request.context, "references", denied)
    with pytest.raises(ProteoformSupportAuthorizationError):
        route_proteoform_support(request)
    object.__setattr__(request.context, "references", references)


def test_owned_result_capability_rejects_mutated_cached_bundle() -> None:
    request = support_router_engine._validate_prepared_request(
        support_router_engine._prepare_support_request_candidate(build_scenario_request())
    )
    result = support_router_engine._support_route_result(request)
    bundle = support_router_contract._expected_support_route_bundle(request)
    capability = support_router_contract._issue_validated_request_capability(
        request,
        bundle,
        result.result_digest,
    )
    assert support_router_contract._validate_result_with_capability(result, capability) == result

    original_support = bundle.support
    object.__setattr__(
        bundle,
        "support",
        original_support.model_copy(update={"rationale": "Forged cached support."}),
    )
    with pytest.raises(TypeError, match="request-validation capability"):
        support_router_contract._validate_result_with_capability(result, capability)
    object.__setattr__(bundle, "support", original_support)


def test_owned_result_capability_fields_snapshots_and_bundle_fail_without_callbacks() -> None:
    request = support_router_engine._validate_prepared_request(
        support_router_engine._prepare_support_request_candidate(build_scenario_request())
    )
    result = support_router_engine._support_route_result(request)
    bundle = support_router_contract._expected_support_route_bundle(request)
    capability = support_router_contract._issue_validated_request_capability(
        request,
        bundle,
        result.result_digest,
    )
    assert support_router_contract._request_capability_is_issued(capability) is True

    for field in (
        "request",
        "request_digest",
        "request_snapshot_digest",
        "prerequisites",
        "quality_result",
        "harmonization_result",
        "bundle",
        "bundle_snapshot_digest",
        "expected_result_digest",
    ):
        original = getattr(capability, field)
        hostile: _HostileEquality | _HostilePrerequisiteReplacement = (
            _HostilePrerequisiteReplacement() if field == "prerequisites" else _HostileEquality()
        )
        object.__setattr__(capability, field, hostile)
        try:
            assert support_router_contract._request_capability_is_issued(capability) is False
            if isinstance(hostile, _HostilePrerequisiteReplacement):
                assert hostile.touched is False
            else:
                assert hostile.compared is False
        finally:
            object.__setattr__(capability, field, original)

    with support_router_contract._VALIDATION_CAPABILITY_LOCK:
        original_snapshot = support_router_contract._ISSUED_REQUEST_CAPABILITIES[capability]
    for index in range(len(original_snapshot)):
        hostile = _HostileEquality()
        corrupted = list(original_snapshot)
        corrupted[index] = hostile
        with support_router_contract._VALIDATION_CAPABILITY_LOCK:
            cast("Any", support_router_contract._ISSUED_REQUEST_CAPABILITIES)[capability] = tuple(
                corrupted
            )
        try:
            assert support_router_contract._request_capability_is_issued(capability) is False
            assert hostile.compared is False
        finally:
            with support_router_contract._VALIDATION_CAPABILITY_LOCK:
                support_router_contract._ISSUED_REQUEST_CAPABILITIES[capability] = original_snapshot

    for field in (
        "request_digest",
        "profile_digest",
        "policy_digest",
        "configuration_digest",
        "envelope_assessments",
        "matched_envelope_ids",
        "abstention_reasons",
        "disposition",
        "support",
        "uncertainty",
        "provenance",
        "evidence",
        "limitations",
    ):
        original = getattr(bundle, field)
        hostile = _HostileEquality()
        object.__setattr__(bundle, field, hostile)
        try:
            assert support_router_contract._request_capability_is_issued(capability) is False
            assert hostile.compared is False
        finally:
            object.__setattr__(bundle, field, original)


def test_plugin_run_uses_private_validated_execution_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = M0407Service()
    plugin = M0407Plugin(service)
    token = plugin.validate(build_scenario_request())

    def reject_public_execute(_service: M0407Service, _request: object) -> None:
        raise AssertionError(_PUBLIC_EXECUTE_CANARY)

    monkeypatch.setattr(M0407Service, "execute", reject_public_execute)

    assert plugin.run(token).request == token.request


def test_plugin_json_boundary_strict_decodes_once_without_service_reparse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_scenario_request()
    original_decode = cast(
        "Callable[..., object]",
        getattr(support_router_plugin, _STRICT_JSON_LOADS_ATTRIBUTE),
    )
    decode_count = 0

    def count_decode(
        payload: bytes | bytearray | str,
        *,
        max_bytes: int | None = None,
    ) -> object:
        nonlocal decode_count
        decode_count += 1
        return original_decode(payload, max_bytes=max_bytes)

    def reject_public_validation(_request: object) -> None:
        raise AssertionError(_PUBLIC_VALIDATE_CANARY)

    monkeypatch.setattr(support_router_plugin, "strict_json_loads", count_decode)
    monkeypatch.setattr(
        M0407Service,
        "validate_request",
        staticmethod(reject_public_validation),
    )

    token = M0407Plugin(M0407Service()).validate(canonical_json_bytes(request))

    assert token.request == request
    assert decode_count == 1


class _HostilePrerequisites(Mapping[str, object]):
    _MESSAGE = "prerequisites were traversed"

    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


class _HostileSequence(Sequence[object]):
    _MESSAGE = "arbitrary sequence access was invoked"

    def __init__(self) -> None:
        self.touched = False

    @overload
    def __getitem__(self, index: int) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[object]: ...

    def __getitem__(self, index: int | slice) -> object | Sequence[object]:
        self.touched = True
        raise AssertionError(index)

    def __len__(self) -> int:
        self.touched = True
        raise AssertionError(self._MESSAGE)


class _VirtualHostileSequence:
    _MESSAGE = "virtual sequence access was invoked"

    def __init__(self) -> None:
        self.touched = False

    def __getitem__(self, index: int) -> object:
        self.touched = True
        raise AssertionError(index)

    def __len__(self) -> int:
        self.touched = True
        raise AssertionError(self._MESSAGE)


Sequence.register(_VirtualHostileSequence)


class _HostileList(list[object]):
    touched = False

    def __iter__(self) -> Iterator[object]:
        type(self).touched = True
        raise AssertionError(_HOSTILE_SEQUENCE_CANARY)

    def __len__(self) -> int:
        type(self).touched = True
        raise AssertionError(_HOSTILE_SEQUENCE_CANARY)


class _HostileTuple(tuple[object, ...]):
    __slots__ = ()

    touched = False

    def __iter__(self) -> Iterator[object]:
        type(self).touched = True
        raise AssertionError(_HOSTILE_SEQUENCE_CANARY)

    def __len__(self) -> int:
        type(self).touched = True
        raise AssertionError(_HOSTILE_SEQUENCE_CANARY)


class _CollidingKey:
    def __init__(self, target: str) -> None:
        self._hash = hash(target)
        self.armed = False
        self.compared = False

    def __hash__(self) -> int:
        return self._hash

    def __eq__(self, _other: object) -> bool:
        self.compared = True
        if self.armed:
            raise AssertionError(_HOSTILE_KEY_CANARY)
        return False


def test_seven_control_denial_precedes_hostile_prerequisite_traversal() -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["prerequisites"] = _HostilePrerequisites()

    with pytest.raises(ProteoformSupportAuthorizationError):
        M0407Service.validate_request(payload)
    with pytest.raises(ProteoformSupportAuthorizationError):
        M0407Service().execute(payload)
    with pytest.raises(ProteoformSupportAuthorizationError):
        M0407Plugin(M0407Service()).validate(payload)


@pytest.mark.parametrize("container", ["dict", "model"])
def test_preflight_rejects_non_exact_string_keys_without_equality_or_upstream_traversal(
    container: str,
) -> None:
    request = build_scenario_request()
    hostile_key = _CollidingKey("context")
    if container == "dict":
        candidate: object = request.model_dump(mode="python")
        assert type(candidate) is dict
        candidate[hostile_key] = "forbidden"
        candidate["prerequisites"] = _HostilePrerequisites()
    else:
        candidate = request.model_copy()
        storage = object.__getattribute__(candidate, "__dict__")
        storage[hostile_key] = "forbidden"
        storage["prerequisites"] = _HostilePrerequisites()
    hostile_key.compared = False
    hostile_key.armed = True

    with pytest.raises(ProteoformSupportAuthorizationError):
        M0407Service.validate_request(candidate)

    assert hostile_key.compared is False


def test_preflight_caps_mapping_before_any_governed_upstream_traversal() -> None:
    candidate = build_scenario_request().model_dump(mode="python")
    candidate["prerequisites"] = _HostilePrerequisites()
    candidate.update({f"extra_{index:04d}": None for index in range(512)})

    with pytest.raises(ProteoformSupportAuthorizationError):
        M0407Service.validate_request(candidate)


@pytest.mark.parametrize(
    ("role", "denied_state"),
    [
        ("approved_configuration", "rejected"),
        ("identity_lineage", "unresolved"),
        ("provenance", "rejected"),
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("support", "rejected"),
        ("intended_use", "rejected"),
    ],
)
def test_each_control_independently_denies_before_route(
    role: str,
    denied_state: str,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"][role]["state"] = denied_state

    with pytest.raises(ProteoformSupportAuthorizationError):
        route_proteoform_support(payload)


def test_preflight_rejects_arbitrary_mapping_accessors_without_touching_them() -> None:
    with pytest.raises(ProteoformSupportAuthorizationError):
        M0407Service.validate_request(_HostilePrerequisites())


def test_authorized_materialization_rejects_arbitrary_sequence_without_touching_it() -> None:
    candidate = build_scenario_request().model_dump(mode="python")
    hostile = _HostileSequence()
    candidate["declared_facts"] = hostile

    with pytest.raises(TypeError, match="exact built-in containers"):
        M0407Service.validate_request(candidate)

    assert hostile.touched is False


def test_authorized_materialization_rejects_virtual_sequence_without_touching_it() -> None:
    candidate = build_scenario_request().model_dump(mode="python")
    hostile = _VirtualHostileSequence()
    candidate["declared_facts"] = hostile

    with pytest.raises(TypeError, match="exact built-in containers"):
        M0407Service.validate_request(candidate)

    assert hostile.touched is False


def test_authorized_materialization_rejects_list_and_tuple_subclasses_untouched() -> None:
    declared_facts = build_scenario_request().model_dump(mode="python")["declared_facts"]
    for hostile in (_HostileList(declared_facts), _HostileTuple(declared_facts)):
        type(hostile).touched = False
        candidate = build_scenario_request().model_dump(mode="python")
        candidate["declared_facts"] = hostile

        with pytest.raises(TypeError, match="exact built-in containers"):
            M0407Service.validate_request(candidate)

        assert type(hostile).touched is False


@pytest.mark.parametrize(
    ("state", "values", "decision", "code"),
    [
        (
            ProteoformDeclaredSupportState.OBSERVED,
            ("specimen." + sha256_digest("outside").removeprefix("sha256:"),),
            ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN,
            ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
        ),
        (
            ProteoformDeclaredSupportState.MISSING,
            (),
            ProteoformDimensionSupportDecision.INDETERMINATE,
            ProteoformAbstentionCode.DIMENSION_INDETERMINATE,
        ),
    ],
)
def test_outside_and_missing_declarations_remain_distinct_abstentions(
    state: ProteoformDeclaredSupportState,
    values: tuple[str, ...],
    decision: ProteoformDimensionSupportDecision,
    code: ProteoformAbstentionCode,
) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    fact = next(
        item
        for item in payload["declared_facts"]
        if item["dimension"] is ProteoformSupportDimension.SPECIMEN
    )
    fact["state"] = state
    fact["values"] = values
    if state is not ProteoformDeclaredSupportState.OBSERVED:
        fact["evidence"] = ()

    result = route_proteoform_support(payload)
    specimen = next(
        item
        for item in result.envelope_assessments[0].dimensions
        if item.dimension is ProteoformSupportDimension.SPECIMEN
    )

    assert result.disposition is ProteoformSupportDisposition.ABSTAINED
    assert specimen.decision is decision
    assert any(item.code is code for item in result.abstention_reasons)


def test_semantic_reorder_reconstructs_complete_result_equality() -> None:
    request = build_scenario_request()
    canonical = route_proteoform_support(request)
    payload = deepcopy(request.model_dump(mode="python"))
    payload["declared_facts"] = tuple(reversed(payload["declared_facts"]))
    payload["context_receipts"] = tuple(reversed(payload["context_receipts"]))
    payload["profile"]["envelopes"] = tuple(reversed(payload["profile"]["envelopes"]))
    payload["profile"]["envelopes"][0]["remediations"] = tuple(
        reversed(payload["profile"]["envelopes"][0]["remediations"])
    )

    reordered = route_proteoform_support(payload)

    assert reordered == canonical
    assert normalized_result(reordered) == normalized_result(canonical)
    assert canonical_json_bytes(reordered) == canonical_json_bytes(canonical)


def test_strict_plugin_json_rejects_unknown_members() -> None:
    payload = build_scenario_request().model_dump(mode="json")
    payload["unknown"] = True

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        M0407Plugin(M0407Service()).validate(payload)
