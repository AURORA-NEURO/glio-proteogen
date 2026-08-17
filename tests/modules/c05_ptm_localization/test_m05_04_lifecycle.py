"""Capability, firewall, service, and plugin lifecycle checks for M05-04."""

from __future__ import annotations

import gc
from collections.abc import Iterator, Mapping
from dataclasses import replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast

import pytest
from evals.m05_04.run import build_scenario_request
from pydantic import TypeAdapter

from glio_proteogen.contracts.m05_04 import (
    ComputePtmLocalizationQualityMetricsRequest,
    PtmLocalizationQualityResult,
    canonical_request_digest,
    configuration_digest,
    normalized_request,
    policy_digest,
)
from glio_proteogen.contracts.m05_04 import v1 as m0504_contract
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics import (
    M0504Plugin,
    M0504PtmLocalizationQualityEngine,
    M0504Service,
    PtmLocalizationQualityAuthorizationError,
    ValidatedM0504Request,
    compute_ptm_localization_quality_metrics,
    preflight_ptm_localization_quality_authorization,
)
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics import (
    engine as m0504_engine,
)
from glio_proteogen.modules.c05_ptm_localization.m05_04_quality_metrics import (
    plugin as m0504_plugin,
)


@pytest.fixture(scope="module")
def m0504_request() -> ComputePtmLocalizationQualityMetricsRequest:
    return build_scenario_request()


def _fresh_request(
    source: ComputePtmLocalizationQualityMetricsRequest,
) -> ComputePtmLocalizationQualityMetricsRequest:
    return TypeAdapter(ComputePtmLocalizationQualityMetricsRequest).validate_json(
        canonical_json_bytes(normalized_request(source)),
        strict=True,
    )


def test_engine_service_and_plugin_surfaces_are_exactly_equal(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    public = compute_ptm_localization_quality_metrics(m0504_request)
    engine = M0504PtmLocalizationQualityEngine()
    service = M0504Service(engine)
    assert service.validate_request(m0504_request) == public.request
    assert engine.compute(m0504_request) == public
    assert service.execute(m0504_request) == public
    capability = service._admit_request(m0504_request)
    assert service._execute_validated(capability) == public

    plugin = M0504Plugin(service)
    descriptor = plugin.descriptor()
    assert (descriptor.module_id, descriptor.owner, descriptor.gate) == (
        "GLIO-PROTEOGEN-M05-04",
        "Platform engineering",
        "G1",
    )
    typed_token = plugin.validate(m0504_request)
    json_token = plugin.validate(canonical_json_bytes(normalized_request(m0504_request)))
    assert plugin.run(typed_token) == public
    assert plugin.run(json_token) == public


def test_authorization_preflight_accepts_only_exact_supported_shapes(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    preflight_ptm_localization_quality_authorization(m0504_request)
    payload = cast("dict[str, object]", m0504_request.model_dump(mode="python"))
    preflight_ptm_localization_quality_authorization(payload)
    with pytest.raises(PtmLocalizationQualityAuthorizationError):
        preflight_ptm_localization_quality_authorization(object())

    class ExplodingDict(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            raise RuntimeError((key, default))

    with pytest.raises(PtmLocalizationQualityAuthorizationError):
        preflight_ptm_localization_quality_authorization(ExplodingDict(payload))


def test_json_and_typed_private_admission_boundaries_match(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    serialized = canonical_json_bytes(normalized_request(m0504_request))
    decoded = cast("dict[str, object]", m0504_request.model_dump(mode="python"))
    typed = m0504_engine._validate_typed_request(m0504_request)
    json_typed = m0504_engine._validate_json_request(decoded, serialized)
    json_capability = m0504_engine._validate_json_request_capability(decoded, serialized)
    assert typed == json_typed == json_capability.request
    assert m0504_engine._compute_result(
        json_capability
    ) == compute_ptm_localization_quality_metrics(m0504_request)
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._compute_result(cast("Any", object()))


def test_cached_request_is_identity_and_snapshot_bound(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    fresh = _fresh_request(m0504_request)
    initial = compute_ptm_localization_quality_metrics(fresh)
    assert compute_ptm_localization_quality_metrics(fresh) == initial
    superseded = sha256_digest("m0504-cache-refresh")
    object.__setattr__(fresh, "supersedes_result_digest", superseded)
    refreshed = compute_ptm_localization_quality_metrics(fresh)
    assert refreshed.request_digest != initial.request_digest
    assert superseded in refreshed.provenance.input_digests

    forged = _fresh_request(m0504_request)
    compute_ptm_localization_quality_metrics(forged)
    object.__setattr__(forged.raw_input_result, "result_digest", sha256_digest("forged"))
    with pytest.raises(ValueError, match="digest"):
        compute_ptm_localization_quality_metrics(forged)


def test_request_cache_entry_retires_with_source_identity(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    fresh = _fresh_request(m0504_request)
    key = id(fresh)
    compute_ptm_localization_quality_metrics(fresh)
    assert key in m0504_engine._ISSUED_REQUESTS
    del fresh
    gc.collect()
    assert key not in m0504_engine._ISSUED_REQUESTS


class _UntouchedMapping(Mapping[str, object]):
    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError

    def __len__(self) -> int:
        raise AssertionError


class _ListSubclass(list[object]):
    pass


class _TupleSubclass(tuple[object, ...]):
    __slots__ = ()


class _DictSubclass(dict[str, object]):
    pass


class _BadState(StrEnum):
    VALUE = "value"


@pytest.mark.parametrize(
    "candidate",
    [
        MappingProxyType({}),
        _UntouchedMapping(),
        range(1),
        _ListSubclass(),
        _TupleSubclass(),
        _DictSubclass(),
    ],
)
def test_plain_value_rejects_nonexact_container_families_without_access(
    candidate: object,
) -> None:
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._plain_value(candidate)


def test_plain_value_enforces_depth_node_and_sequence_caps() -> None:
    nested: object = "leaf"
    for _ in range(m0504_engine._MAX_PLAIN_DEPTH + 2):
        nested = [nested]
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._plain_value(nested)
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._plain_value("leaf", _budget=[0])
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._plain_value([None] * (m0504_engine._MAX_PLAIN_SEQUENCE + 1))
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._plain_value(tuple([None] * (m0504_engine._MAX_PLAIN_SEQUENCE + 1)))
    bad_state = _BadState.VALUE
    object.__setattr__(bad_state, "_value_", 1)
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._plain_value(bad_state)


def test_outer_shape_and_mapping_firewalls_fail_closed(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._validate_plain_mapping(cast("dict[object, object]", {1: "value"}))
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._validate_outer_request_shape(_DictSubclass())
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._validate_outer_request_shape({"unknown": "field"})
    fresh = _fresh_request(m0504_request)
    object.__delattr__(fresh, "operation")
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_engine._validate_outer_request_shape(fresh)
    assert m0504_engine._state_text("accepted") == "accepted"
    assert m0504_engine._state_text(object()) is None


def test_raw_replay_capabilities_reject_forgery_and_mismatch(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    with pytest.raises(TypeError, match="exact model or built-in dict"):
        m0504_contract._raw_input_value(object())
    with pytest.raises(TypeError, match="exact result or built-in dict"):
        m0504_contract._issue_raw_input_replay_capability({"raw_input_result": "invalid"})
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_contract._materialize_raw_input_value({1: "invalid"})

    malformed = m0504_request.raw_input_result.model_copy(deep=True)
    cast("dict[object, object]", malformed.__dict__)[1] = "invalid"
    with pytest.raises(TypeError, match="exact string keys"):
        m0504_contract._materialize_raw_input_value(malformed)

    raw_capability = m0504_contract._issue_raw_input_replay_capability(
        {"raw_input_result": m0504_request.raw_input_result}
    )
    mismatched = replace(raw_capability, seal=object())
    with pytest.raises(TypeError, match="invalid or mismatched"):
        m0504_contract._validate_request_with_raw_capability(
            m0504_request,
            mismatched,
        )
    with pytest.raises(TypeError, match="invalid or mismatched"):
        m0504_contract._validate_json_request_with_raw_capability(
            canonical_json_bytes(normalized_request(m0504_request)),
            m0504_request.model_dump(mode="python"),
            mismatched,
        )


def test_result_capability_and_plugin_tokens_cannot_be_forged(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    service = M0504Service()
    capability = service._admit_request(m0504_request)
    forged_capability = replace(capability, seal=object())
    result = service._execute_validated(capability)
    with pytest.raises(TypeError, match="invalid M05-04 request-validation"):
        m0504_contract._validate_result_with_capability(result, forged_capability)

    plugin = M0504Plugin(service)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(cast("Any", object()))
    forged_token = ValidatedM0504Request(
        request=capability.request,
        _capability=capability,
        _seal=m0504_plugin._TOKEN_SEAL,
    )
    assert not m0504_plugin._token_is_issued(forged_token)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(forged_token)

    issued = plugin.validate(canonical_json_bytes(normalized_request(m0504_request)))
    object.__delattr__(issued.request, "operation")
    assert not m0504_plugin._token_is_issued(issued)
    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(issued)


def test_request_digest_cache_values_are_exact(
    m0504_request: ComputePtmLocalizationQualityMetricsRequest,
) -> None:
    capability = m0504_engine._validated_request_capability(m0504_request)
    assert capability.request_digest == canonical_request_digest(capability.request)
    assert capability.policy_digest == policy_digest(capability.request.policy)
    assert capability.configuration_digest == configuration_digest(capability.request.policy)
    assert isinstance(M0504Service().execute(m0504_request), PtmLocalizationQualityResult)
