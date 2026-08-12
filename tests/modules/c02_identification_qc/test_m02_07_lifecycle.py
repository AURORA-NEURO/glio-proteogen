"""Focused engine, service, receipt, and plugin lifecycle checks for M02-07."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Final

import pytest
from evals.m02_07.run import build_scenario_request

from glio_proteogen.contracts.m02_07 import (
    IdentificationAbstentionCode,
    IdentificationSupportDimension,
    IdentificationSupportDisposition,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c02_identification_qc.m02_07_support_router import (
    IdentificationSupportAuthorizationError,
    M0207Plugin,
    M0207Service,
    route_identification_support,
)

DIMENSION_COUNT: Final = 8


def test_engine_confirms_one_whole_eight_dimension_envelope() -> None:
    result = route_identification_support(build_scenario_request())

    assert result.disposition is IdentificationSupportDisposition.SUPPORTED
    assert len(result.matched_envelope_ids) == 1
    assert len(result.envelope_assessments) == 1
    assert len(result.envelope_assessments[0].dimensions) == DIMENSION_COUNT
    assert not result.abstention_reasons


@pytest.mark.parametrize("dimension", tuple(IdentificationSupportDimension))
def test_every_isolated_outside_dimension_abstains(
    dimension: IdentificationSupportDimension,
) -> None:
    request = build_scenario_request(
        "outside_dimension_matrix",
        outside_dimension=dimension,
    )

    result = M0207Service().execute(request)

    assert result.disposition is IdentificationSupportDisposition.ABSTAINED
    failed = [
        item for item in result.envelope_assessments[0].dimensions if item.dimension is dimension
    ]
    assert len(failed) == 1
    assert failed[0].decision.value == "outside_domain"


def test_cross_envelope_union_never_becomes_support() -> None:
    result = M0207Service().execute(build_scenario_request("cross_envelope_composite"))

    assert result.disposition is IdentificationSupportDisposition.ABSTAINED
    assert not result.matched_envelope_ids
    assert any(
        item.code is IdentificationAbstentionCode.JOINT_COMBINATION_OUTSIDE_DOMAIN
        for item in result.abstention_reasons
    )


@pytest.mark.parametrize(
    ("request_case", "module_id"),
    [
        ("m0204_unreleasable", "GLIO-PROTEOGEN-M02-04"),
        ("m0206_unreleasable", "GLIO-PROTEOGEN-M02-06"),
    ],
)
def test_unreleasable_upstream_result_becomes_typed_abstention(
    request_case: str,
    module_id: str,
) -> None:
    result = M0207Service().execute(build_scenario_request(request_case))

    assert result.disposition is IdentificationSupportDisposition.ABSTAINED
    assert any(
        item.code is IdentificationAbstentionCode.PREREQUISITE_UNRELEASABLE
        and item.upstream_module_id == module_id
        for item in result.abstention_reasons
    )


@pytest.mark.parametrize("request_case", ["missing_evidence", "unknown_evidence"])
def test_nonobserved_fact_remains_indeterminate(request_case: str) -> None:
    result = M0207Service().execute(build_scenario_request(request_case))

    assert result.disposition is IdentificationSupportDisposition.ABSTAINED
    assert any(
        item.code is IdentificationAbstentionCode.DIMENSION_INDETERMINATE
        for item in result.abstention_reasons
    )


def test_public_request_uses_compact_receipts_without_harmonized_values() -> None:
    request = build_scenario_request()
    harmonization = request.prerequisites.harmonization

    assert harmonization.total_value_count > 0
    assert harmonization.evaluable_value_count <= harmonization.nonexcluded_value_count
    assert not hasattr(harmonization, "values")
    assert len(canonical_json_bytes(request)) < 4 * 1024 * 1024


def test_plugin_strict_json_round_trip_and_descriptor() -> None:
    request = build_scenario_request()
    plugin = M0207Plugin(M0207Service())

    result = plugin.run(plugin.validate(request.model_dump_json()))

    assert result.disposition is IdentificationSupportDisposition.SUPPORTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M02-07"
    assert plugin.descriptor().owner == "Platform engineering"


def test_plugin_rejects_unvalidated_execution() -> None:
    plugin = M0207Plugin(M0207Service())

    with pytest.raises(TypeError, match="validated request token"):
        plugin.run(build_scenario_request())  # type: ignore[arg-type]


class _HostilePrerequisites(Mapping[str, object]):
    _MESSAGE = "prerequisites were traversed"

    def __getitem__(self, key: str) -> object:
        raise AssertionError(key)

    def __iter__(self) -> Iterator[str]:
        raise AssertionError(self._MESSAGE)

    def __len__(self) -> int:
        raise AssertionError(self._MESSAGE)


def test_authorization_precedes_hostile_prerequisite_traversal() -> None:
    payload = build_scenario_request().model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["prerequisites"] = _HostilePrerequisites()

    with pytest.raises(IdentificationSupportAuthorizationError):
        M0207Service.validate_request(payload)
    with pytest.raises(IdentificationSupportAuthorizationError):
        M0207Service().execute(payload)
    with pytest.raises(IdentificationSupportAuthorizationError):
        M0207Plugin(M0207Service()).validate(payload)
