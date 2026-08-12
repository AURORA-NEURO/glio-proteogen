"""Public request-contract checks for M02-06 identification harmonization."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
from evals.m02_06.run import build_scenario_request
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m02_06 import (
    M0206_MAX_INVARIANTS,
    M0206_MAX_OBSERVATIONS,
    M0206_MAX_STAGES,
    BiologicalControlInvariant,
    BiologicalInvariantKind,
    HarmonizationValueState,
    HarmonizeIdentificationEvidenceRequest,
    IdentificationAbundanceObservation,
    IdentificationHarmonizationPolicy,
    IdentificationHarmonizationProfile,
    IdentificationNormalizationStage,
    IdentificationTechnicalFactor,
    canonical_request_digest,
    contract_json_schema,
    invariant_digest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    UpstreamDecisionState,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from glio_proteogen.contracts.m02_06.schema import ContractName

pytestmark = pytest.mark.contract

_SENTINEL_DIGEST = "sha256:" + ("0" * 64)
_MAX_EVIDENCE_PER_OBSERVATION = 64


@cache
def _base_request_payload(case: str) -> dict[str, Any]:
    return build_scenario_request(case).model_dump(mode="python")


def _request_payload(case: str = "conformant_eight_factor") -> dict[str, Any]:
    return deepcopy(_base_request_payload(case))


def _set(mapping: dict[str, Any], key: str, value: object) -> object:
    mapping[key] = value
    return value


@pytest.mark.parametrize(
    "name",
    [
        "request",
        "output",
        "prerequisites",
        "profile",
        "policy",
        "observation",
        "value",
        "manifest",
    ],
)
def test_public_schema_is_strict_valid_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert str(schema["$id"]).endswith(f":{name}")
    expected_metadata = {
        "moduleId": "GLIO-PROTEOGEN-M02-06",
        "contractVersion": "1.0.0",
        "strict": True,
        "rawPayload": False,
        "biologicalInterpretation": False,
    }
    if name == "request":
        expected_metadata["maxRequestBytes"] = 4_194_304
    assert schema["x-glio-contract"] == expected_metadata
    Draft202012Validator.check_schema(schema)


def test_factor_and_value_state_vocabularies_are_closed() -> None:
    assert tuple(item.value for item in IdentificationTechnicalFactor) == (
        "platform",
        "batch",
        "laboratory",
        "build",
        "depth",
        "purity",
        "composition",
        "preanalytic",
    )
    assert tuple(item.value for item in HarmonizationValueState) == (
        "observed",
        "missing",
        "censored",
        "not_applicable",
        "unsupported",
        "excluded",
    )
    assert len(IdentificationTechnicalFactor) == M0206_MAX_STAGES


def test_request_forbids_unknown_fields_and_primitive_coercion() -> None:
    request = _request_payload()
    request["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HarmonizeIdentificationEvidenceRequest.model_validate(request, strict=True)

    policy = _request_payload()["policy"]
    policy["max_observations"] = "128"
    with pytest.raises(ValidationError, match="valid integer"):
        IdentificationHarmonizationPolicy.model_validate(policy, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: _set(item, "value", None), "requires a value"),
        (
            lambda item: _set(item, "censoring_limit", 1.0),
            "cannot carry a censoring limit",
        ),
        (
            lambda item: (
                _set(item, "state", HarmonizationValueState.CENSORED),
                _set(item, "value", None),
                _set(item, "censoring_limit", None),
            ),
            "requires only its limit",
        ),
        (
            lambda item: (
                _set(item, "state", HarmonizationValueState.MISSING),
                _set(item, "value", 0.0),
            ),
            "cannot carry a number",
        ),
        (
            lambda item: (
                _set(item, "state", HarmonizationValueState.EXCLUDED),
                _set(item, "value", None),
            ),
            "input exclusion is derived only",
        ),
        (
            lambda item: _set(
                item,
                "factor_levels",
                (*item["factor_levels"][:-1], item["factor_levels"][0]),
            ),
            "every technical factor exactly once",
        ),
        (
            lambda item: _set(item, "evidence", (*item["evidence"], item["evidence"][0])),
            "evidence digests must be unique",
        ),
    ],
)
def test_observation_state_factor_and_evidence_closure(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    observation = _request_payload()["observations"][0]
    mutate(observation)

    with pytest.raises(ValidationError, match=message):
        IdentificationAbundanceObservation.model_validate(observation, strict=True)


@pytest.mark.parametrize("field", ["control_target_ids", "control_feature_ids"])
def test_stage_controls_are_unique(field: str) -> None:
    stage = _request_payload()["profile"]["stages"][0]
    stage[field] = (*stage[field], stage[field][0])

    with pytest.raises(ValidationError, match="must be unique"):
        IdentificationNormalizationStage.model_validate(stage, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda stages: _set(stages[0], "ordinal", 2), "ordered ordinals"),
        (
            lambda stages: _set(stages[1], "stage_id", stages[0]["stage_id"]),
            "identifiers must be unique",
        ),
        (
            lambda stages: _set(stages[1], "factor", stages[0]["factor"]),
            "all eight technical factors exactly once",
        ),
    ],
)
def test_profile_is_the_exact_ordered_eight_factor_plan(
    mutate: Callable[[tuple[dict[str, Any], ...]], object],
    message: str,
) -> None:
    profile = _request_payload()["profile"]
    mutate(profile["stages"])

    with pytest.raises(ValidationError, match=message):
        IdentificationHarmonizationProfile.model_validate(profile, strict=True)


@pytest.mark.parametrize(
    ("kind", "features", "groups", "expected_error"),
    [
        (BiologicalInvariantKind.DIRECTION, ("feature.a",), ("group.a", "group.b"), None),
        (BiologicalInvariantKind.RANK, ("feature.a", "feature.b"), ("group.a",), None),
        (
            BiologicalInvariantKind.DIRECTION,
            ("feature.a", "feature.b"),
            ("group.a",),
            "members do not match",
        ),
        (
            BiologicalInvariantKind.RANK,
            ("feature.a",),
            ("group.a", "group.b"),
            "members do not match",
        ),
    ],
)
def test_invariant_kind_has_exact_ordered_member_shape(
    kind: BiologicalInvariantKind,
    features: tuple[str, ...],
    groups: tuple[str, ...],
    expected_error: str | None,
) -> None:
    values = {
        "invariant_id": "invariant.test",
        "kind": kind,
        "feature_ids": features,
        "biological_group_ids": groups,
    }

    if expected_error is None:
        assert BiologicalControlInvariant.model_validate(values, strict=True).kind is kind
    else:
        with pytest.raises(ValidationError, match=expected_error):
            BiologicalControlInvariant.model_validate(values, strict=True)


@pytest.mark.parametrize("field", ["feature_ids", "biological_group_ids"])
def test_invariant_members_are_unique(field: str) -> None:
    index = 1 if field == "feature_ids" else 0
    values = _request_payload()["biological_controls"][index]
    values[field] = tuple(values[field][0] for _ in values[field])

    with pytest.raises(ValidationError, match="must be unique"):
        BiologicalControlInvariant.model_validate(values, strict=True)


def test_invariant_member_order_is_semantic_and_digest_bound() -> None:
    controls = build_scenario_request().biological_controls
    direction = controls[0]
    rank = controls[1]
    reversed_direction = direction.model_copy(
        update={"biological_group_ids": tuple(reversed(direction.biological_group_ids))}
    )
    reversed_rank = rank.model_copy(update={"feature_ids": tuple(reversed(rank.feature_ids))})

    assert invariant_digest(direction) != invariant_digest(reversed_direction)
    assert invariant_digest(rank) != invariant_digest(reversed_rank)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value["policy"], "max_observations", 127),
            "request exceeds its policy",
        ),
        (
            lambda value: _set(value["policy"], "max_invariants", 1),
            "request exceeds its policy",
        ),
        (
            lambda value: _set(
                value,
                "observations",
                (*value["observations"], value["observations"][0]),
            ),
            "unique by target and feature",
        ),
        (
            lambda value: _set(
                value,
                "biological_controls",
                (*value["biological_controls"], value["biological_controls"][0]),
            ),
            "control identifiers must be unique",
        ),
        (
            lambda value: _set(value["observations"][0], "unit", "different_unit"),
            "log2_abundance",
        ),
        (
            lambda value: _set(
                value["profile"]["stages"][0],
                "control_target_ids",
                ("target.unknown",),
            ),
            "unknown control target",
        ),
        (
            lambda value: _set(
                value["profile"]["stages"][0],
                "control_feature_ids",
                ("feature.unknown",),
            ),
            "unknown control feature",
        ),
        (
            lambda value: _set(
                value["profile"]["stages"][0],
                "reference_level_id",
                "level.unknown",
            ),
            "declared reference and comparison level",
        ),
        (
            lambda value: _set(
                value["biological_controls"][0],
                "biological_group_ids",
                ("group.baseline", "group.unknown"),
            ),
            "unknown observation member",
        ),
        (
            lambda value: _set(
                value["context"]["references"]["approved_configuration"]["evidence"],
                "digest",
                _SENTINEL_DIGEST,
            ),
            "configuration does not bind",
        ),
        (
            lambda value: _set(
                value["context"]["references"]["identity_lineage"],
                "binding_digest",
                _SENTINEL_DIGEST,
            ),
            "identity control does not bind",
        ),
        (
            lambda value: _set(value["observations"][0], "target_id", "sample.unchecked"),
            "every harmonization target must be evaluated",
        ),
    ],
)
def test_request_relations_fail_closed(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _request_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        HarmonizeIdentificationEvidenceRequest.model_validate(values, strict=True)


def test_request_requires_consistent_factor_levels_within_target() -> None:
    values = _request_payload()
    first = values["observations"][0]
    same_target = next(
        item for item in values["observations"][1:] if item["target_id"] == first["target_id"]
    )
    same_target["factor_levels"][0]["level_id"] = "level.m0206.platform.conflict"

    with pytest.raises(ValidationError, match="consistent within each target"):
        HarmonizeIdentificationEvidenceRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("role", "state", "message"),
    [
        ("consent", ConsentState.REVOKED, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage"),
        ("quality", UpstreamDecisionState.REJECTED, "every upstream control"),
    ],
)
def test_request_requires_all_authorized_controls(
    role: str,
    state: object,
    message: str,
) -> None:
    values = _request_payload()
    values["context"]["references"][role]["state"] = state

    with pytest.raises(ValidationError, match=message):
        HarmonizeIdentificationEvidenceRequest.model_validate(values, strict=True)


def test_declared_capacity_limits_fail_closed() -> None:
    policy = _request_payload()["policy"]
    policy["max_observations"] = M0206_MAX_OBSERVATIONS + 1
    with pytest.raises(ValidationError, match="less than or equal"):
        IdentificationHarmonizationPolicy.model_validate(policy, strict=True)

    policy = _request_payload()["policy"]
    policy["max_invariants"] = M0206_MAX_INVARIANTS + 1
    with pytest.raises(ValidationError, match="less than or equal"):
        IdentificationHarmonizationPolicy.model_validate(policy, strict=True)

    observation = _request_payload()["observations"][0]
    observation["evidence"] = tuple(
        {
            **observation["evidence"][0],
            "artifact_id": f"artifact.capacity.{index}",
            "digest": f"sha256:{index:064x}",
        }
        for index in range(_MAX_EVIDENCE_PER_OBSERVATION + 1)
    )
    with pytest.raises(ValidationError, match="at most 64 items"):
        IdentificationAbundanceObservation.model_validate(observation, strict=True)

    stage = _request_payload()["profile"]["stages"][0]
    stage["control_target_ids"] = tuple(f"sample.capacity.{index}" for index in range(1001))
    with pytest.raises(ValidationError, match="at most 1000 items"):
        IdentificationNormalizationStage.model_validate(stage, strict=True)


def test_semantically_unordered_request_has_one_canonical_digest() -> None:
    request = build_scenario_request()
    values = request.model_dump(mode="python")
    values["observations"] = tuple(reversed(values["observations"]))
    values["biological_controls"] = tuple(reversed(values["biological_controls"]))
    for observation in values["observations"]:
        observation["factor_levels"] = tuple(reversed(observation["factor_levels"]))
        observation["evidence"] = tuple(reversed(observation["evidence"]))
    for stage in values["profile"]["stages"]:
        stage["control_target_ids"] = tuple(reversed(stage["control_target_ids"]))
        stage["control_feature_ids"] = tuple(reversed(stage["control_feature_ids"]))
    reordered = HarmonizeIdentificationEvidenceRequest.model_validate(values, strict=True)

    assert canonical_request_digest(reordered) == canonical_request_digest(request)  # type: ignore[arg-type]
