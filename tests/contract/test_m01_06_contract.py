"""Compact public-contract checks for deterministic M01-06 harmonization."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_06.run import build_scenario_request
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m01_06 import (
    BiologicalInvariant,
    DiagnosticStatus,
    HarmonizationDisposition,
    HarmonizationResult,
    HarmonizeObservationsRequest,
    InvariantKind,
    ShiftState,
    canonical_request_digest,
    contract_json_schema,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization import (
    harmonize_observations,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_06.schema import ContractName

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "name",
    ["request", "output", "policy", "profile", "invariant", "value", "transformation"],
)
def test_public_schema_is_valid_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert str(schema["$id"]).endswith(f":{name}")
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    ("kind", "features", "groups"),
    [
        (InvariantKind.DIRECTION, ("feature.one", "feature.two"), ("group.one", "group.two")),
        (InvariantKind.DIRECTION, ("feature.one",), ("group.one",)),
        (InvariantKind.RANK, ("feature.one",), ("group.one",)),
        (InvariantKind.RANK, ("feature.one", "feature.two"), ("group.one", "group.two")),
    ],
)
def test_invariant_kind_has_exact_member_shape(
    kind: InvariantKind,
    features: tuple[str, ...],
    groups: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError, match="members do not match"):
        BiologicalInvariant(
            invariant_id="invariant.invalid",
            kind=kind,
            feature_ids=features,
            group_ids=groups,
        )


def test_request_requires_one_common_unit_and_complete_factor_levels() -> None:
    request = build_scenario_request("supported")
    values = request.model_dump(mode="python")
    values["observations"][0]["unit"] = "different_scale"
    with pytest.raises(ValidationError, match="one common"):
        HarmonizeObservationsRequest.model_validate(values, strict=True)

    values = request.model_dump(mode="python")
    values["observations"][0]["factor_levels"] = values["observations"][0][
        "factor_levels"
    ][:-1]
    with pytest.raises(ValidationError, match="every configured technical factor"):
        HarmonizeObservationsRequest.model_validate(values, strict=True)


def test_request_requires_reference_and_nonreference_control_levels() -> None:
    request = build_scenario_request("supported")
    values = request.model_dump(mode="python")
    stage = values["profile"]["stages"][0]
    factor = stage["factor"]
    reference = stage["reference_level_id"]
    for observation in values["observations"]:
        for level in observation["factor_levels"]:
            if level["factor"] == factor:
                level["level_id"] = reference

    with pytest.raises(ValidationError, match="reference and non-reference"):
        HarmonizeObservationsRequest.model_validate(values, strict=True)


def test_semantically_unordered_request_replays_to_one_digest() -> None:
    request = build_scenario_request("supported")
    values = request.model_dump(mode="python")
    values["observations"] = tuple(reversed(values["observations"]))
    values["biological_invariants"] = tuple(reversed(values["biological_invariants"]))
    reordered = HarmonizeObservationsRequest.model_validate(values, strict=True)

    assert canonical_request_digest(reordered) == canonical_request_digest(request)
    assert harmonize_observations(reordered) == harmonize_observations(request)


def test_capped_shift_cannot_be_presented_as_accepted() -> None:
    result = harmonize_observations(build_scenario_request("capped_shift"))

    assert result.disposition is HarmonizationDisposition.QUARANTINED
    assert result.technical_effect_diagnostics[0].status is DiagnosticStatus.FAILED
    assert any(
        shift.state is ShiftState.CAPPED
        for stage in result.transformation_manifest.stages
        for shift in stage.level_shifts
    )
    forged = result.model_dump(mode="python")
    forged["disposition"] = HarmonizationDisposition.ACCEPTED
    forged["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="disposition contradicts"):
        HarmonizationResult.model_validate(forged, strict=True)


def test_result_rejects_revoked_authorization_provenance() -> None:
    result = harmonize_observations(build_scenario_request("supported"))
    forged = result.model_dump(mode="python")
    forged["provenance"]["consent_state"] = ConsentState.REVOKED
    consent = next(
        item
        for item in forged["provenance"]["control_decisions"]
        if item["role"] == "consent"
    )
    consent["state"] = "revoked"
    forged["result_digest"] = "sha256:" + ("0" * 64)

    with pytest.raises(ValidationError, match="accepted authorization"):
        HarmonizationResult.model_validate(forged, strict=True)
