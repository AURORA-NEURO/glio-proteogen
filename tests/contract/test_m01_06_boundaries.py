"""Compact fail-closed validator coverage for the public M01-06 contract."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import pytest
from evals.m01_06.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m01_06 import (
    BiologicalInvariant,
    BiologicalInvariantDiagnostic,
    DiagnosticStatus,
    HarmonizationObservation,
    HarmonizationProfile,
    HarmonizationResult,
    HarmonizationStage,
    HarmonizedValue,
    HarmonizeObservationsRequest,
    InvariantKind,
    LevelShift,
    ObservationState,
    ShiftState,
    StageTransformation,
    TechnicalEffectDiagnostic,
    TechnicalFactor,
    TransformationManifest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_06_harmonization import (
    harmonize_observations,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.contract

_SENTINEL_DIGEST = "sha256:" + ("0" * 64)


def _request_payload(case: str = "supported") -> dict[str, object]:
    return deepcopy(build_scenario_request(case).model_dump(mode="python"))


def _result_payload(case: str = "supported") -> dict[str, object]:
    payload = deepcopy(
        harmonize_observations(build_scenario_request(case)).model_dump(mode="python")
    )
    payload["result_digest"] = _SENTINEL_DIGEST
    return payload


def _set(mapping: dict[str, object], key: str, value: object) -> None:
    mapping[key] = value


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(
                value,
                "factor_levels",
                (*value["factor_levels"], value["factor_levels"][0]),
            ),
            "unique by factor",
        ),
        (
            lambda value: _set(value, "evidence", (*value["evidence"], value["evidence"][0])),
            "evidence references must be unique",
        ),
        (lambda value: _set(value, "value", None), "requires a value"),
        (
            lambda value: (
                _set(value, "state", ObservationState.MISSING),
                _set(value, "value", 0.0),
            ),
            "cannot carry a value",
        ),
        (
            lambda value: (
                _set(value, "state", ObservationState.BELOW_DETECTION_LIMIT),
                _set(value, "value", None),
                _set(value, "detection_limit", None),
            ),
            "requires a detection limit",
        ),
        (lambda value: _set(value, "detection_limit", 1.0), "only censored"),
    ],
)
def test_observation_state_and_collections_fail_closed(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    value = _request_payload()["observations"][0]
    mutate(value)

    with pytest.raises(ValidationError, match=message):
        HarmonizationObservation.model_validate(value, strict=True)


@pytest.mark.parametrize("field", ["control_sample_ids", "control_feature_ids"])
def test_stage_controls_are_unique(field: str) -> None:
    stage = _request_payload()["profile"]["stages"][0]
    stage[field] = (*stage[field], stage[field][0])

    with pytest.raises(ValidationError, match="must be unique"):
        HarmonizationStage.model_validate(stage, strict=True)


@pytest.mark.parametrize("field", ["feature_ids", "group_ids"])
def test_invariant_members_are_unique(field: str) -> None:
    invariant = _request_payload()["biological_invariants"][0]
    invariant[field] = (*invariant[field], invariant[field][0])

    with pytest.raises(ValidationError, match="identifiers must be unique"):
        BiologicalInvariant.model_validate(invariant, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda stages: _set(stages[0], "ordinal", 2), "contiguous ordered"),
        (lambda stages: _set(stages[1], "stage_id", stages[0]["stage_id"]), "identifiers"),
        (lambda stages: _set(stages[1], "factor", stages[0]["factor"]), "unique by factor"),
    ],
)
def test_profile_stage_relations_are_closed(
    mutate: Callable[[tuple[dict[str, object], ...]], object],
    message: str,
) -> None:
    profile = _request_payload()["profile"]
    mutate(profile["stages"])

    with pytest.raises(ValidationError, match=message):
        HarmonizationProfile.model_validate(profile, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value["policy"], "max_observations", 1),
            "exceeds the active policy",
        ),
        (
            lambda value: _set(
                value,
                "observations",
                (*value["observations"], value["observations"][0]),
            ),
            "unique by sample and feature",
        ),
        (
            lambda value: _set(
                value,
                "biological_invariants",
                (*value["biological_invariants"], value["biological_invariants"][0]),
            ),
            "invariant identifiers must be unique",
        ),
        (
            lambda value: _set(value["profile"]["stages"][0], "control_sample_ids", ("unknown",)),
            "unknown control sample",
        ),
        (
            lambda value: _set(value["profile"]["stages"][0], "control_feature_ids", ("unknown",)),
            "unknown control feature",
        ),
        (
            lambda value: _set(value["biological_invariants"][0], "feature_ids", ("unknown",)),
            "unknown request members",
        ),
        (
            lambda value: _set(
                value["context"]["references"]["approved_configuration"]["evidence"],
                "digest",
                _SENTINEL_DIGEST,
            ),
            "does not bind",
        ),
    ],
)
def test_request_relations_fail_closed(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    value = _request_payload()
    mutate(value)

    with pytest.raises(ValidationError, match=message):
        HarmonizeObservationsRequest.model_validate(value, strict=True)


def test_request_requires_consistent_levels_within_sample() -> None:
    value = _request_payload()
    first = value["observations"][0]
    same_sample = next(
        item
        for item in value["observations"][1:]
        if item["sample_id"] == first["sample_id"]
    )
    same_sample["factor_levels"][0]["level_id"] = "different.level"

    with pytest.raises(ValidationError, match="consistent within each sample"):
        HarmonizeObservationsRequest.model_validate(value, strict=True)


@pytest.mark.parametrize(
    ("role", "state", "message"),
    [
        ("consent", ConsentState.REVOKED, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage"),
        ("quality", UpstreamDecisionState.REJECTED, "every upstream control"),
    ],
)
def test_request_requires_authorized_controls(role: str, state: object, message: str) -> None:
    value = _request_payload()
    value["context"]["references"][role]["state"] = state

    with pytest.raises(ValidationError, match=message):
        HarmonizeObservationsRequest.model_validate(value, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: _set(value, "value", None), "requires a value"),
        (
            lambda value: (
                _set(value, "state", ObservationState.MISSING),
                _set(value, "value", 0.0),
            ),
            "cannot carry a value",
        ),
        (
            lambda value: (
                _set(value, "state", ObservationState.BELOW_DETECTION_LIMIT),
                _set(value, "value", None),
                _set(value, "detection_limit", None),
            ),
            "requires a detection limit",
        ),
        (lambda value: _set(value, "detection_limit", 1.0), "only censored"),
        (
            lambda value: _set(
                value,
                "applied_stage_ids",
                (*value["applied_stage_ids"], value["applied_stage_ids"][0]),
            ),
            "stage identifiers must be unique",
        ),
    ],
)
def test_harmonized_value_state_is_closed(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    value = next(
        item for item in _result_payload()["values"] if item["applied_stage_ids"]
    )
    mutate(value)

    with pytest.raises(ValidationError, match=message):
        HarmonizedValue.model_validate(value, strict=True)


@pytest.mark.parametrize(
    ("state", "estimated", "applied", "message"),
    [
        (ShiftState.NOT_EVALUABLE, 1.0, 1.0, "cannot carry values"),
        (ShiftState.ESTIMATED, None, None, "requires estimated"),
        (ShiftState.NOT_EVALUABLE, 1.0, None, "must be paired"),
        (ShiftState.ESTIMATED, 1.0, 0.5, "exact estimate"),
    ],
)
def test_level_shift_state_is_closed(
    state: ShiftState,
    estimated: float | None,
    applied: float | None,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        LevelShift(
            level_id="level.test",
            state=state,
            estimated_shift=estimated,
            applied_shift=applied,
            unit="log2_intensity",
            control_count=1,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda stage: _set(
                stage,
                "level_shifts",
                (*stage["level_shifts"], stage["level_shifts"][0]),
            ),
            "level identifiers must be unique",
        ),
        (lambda stage: _set(stage, "reference_level_id", "unknown"), "exactly one reference"),
        (
            lambda stage: _set(stage["level_shifts"][0], "state", ShiftState.CAPPED),
            "reference shift",
        ),
        (
            lambda stage: (
                _set(stage["level_shifts"][1], "state", ShiftState.ESTIMATED),
                _set(stage["level_shifts"][1], "estimated_shift", stage["maximum_absolute_shift"]),
                _set(stage["level_shifts"][1], "applied_shift", stage["maximum_absolute_shift"]),
            ),
            "strictly within the cap",
        ),
    ],
)
def test_transformation_relations_fail_closed(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    stage = _result_payload()["transformation_manifest"]["stages"][0]
    mutate(stage)

    with pytest.raises(ValidationError, match=message):
        StageTransformation.model_validate(stage, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda stages: _set(stages[0], "ordinal", 2), "contiguous ordered"),
        (lambda stages: _set(stages[1], "stage_id", stages[0]["stage_id"]), "identifiers"),
        (lambda stages: _set(stages[1], "factor", stages[0]["factor"]), "unique by factor"),
        (
            lambda stages: _set(
                stages[1],
                "maximum_absolute_shift",
                stages[0]["maximum_absolute_shift"] * 2,
            ),
            "share one maximum",
        ),
    ],
)
def test_manifest_stage_relations_fail_closed(
    mutate: Callable[[tuple[dict[str, object], ...]], object],
    message: str,
) -> None:
    manifest = _result_payload()["transformation_manifest"]
    mutate(manifest["stages"])

    with pytest.raises(ValidationError, match=message):
        TransformationManifest.model_validate(manifest, strict=True)


@pytest.mark.parametrize(
    ("before", "after", "tolerance", "capped", "status"),
    [
        (None, None, 1.0, False, DiagnosticStatus.PASSED),
        (2.0, 1.0, 1.0, False, DiagnosticStatus.FAILED),
        (2.0, 3.0, 3.0, False, DiagnosticStatus.PASSED),
        (2.0, 1.0, 1.0, True, DiagnosticStatus.PASSED),
    ],
)
def test_technical_diagnostic_status_is_derived(
    before: float | None,
    after: float | None,
    tolerance: float,
    capped: bool,  # noqa: FBT001 - parameterized contract input.
    status: DiagnosticStatus,
) -> None:
    with pytest.raises(ValidationError, match="scores contradict"):
        TechnicalEffectDiagnostic(
            stage_id="stage.test",
            factor=TechnicalFactor.BATCH,
            before_spread=before,
            after_spread=after,
            tolerance=tolerance,
            capped=capped,
            status=status,
        )


@pytest.mark.parametrize(
    ("before", "after", "tolerance", "status"),
    [
        (None, None, 1.0, DiagnosticStatus.PASSED),
        (1.0, 1.0, 0.0, DiagnosticStatus.FAILED),
        (1.0, -1.0, 3.0, DiagnosticStatus.PASSED),
        (0.0, 0.0, 0.0, DiagnosticStatus.PASSED),
    ],
)
def test_biological_diagnostic_status_is_derived(
    before: float | None,
    after: float | None,
    tolerance: float,
    status: DiagnosticStatus,
) -> None:
    with pytest.raises(ValidationError, match="scores contradict"):
        BiologicalInvariantDiagnostic(
            invariant_id="invariant.test",
            kind=InvariantKind.DIRECTION,
            before_score=before,
            after_score=after,
            tolerance=tolerance,
            status=status,
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value, "values", (*value["values"], value["values"][0])),
            "values must be unique",
        ),
        (
            lambda value: _set(value["values"][0], "applied_stage_ids", ("unknown.stage",)),
            "follow the transformation manifest",
        ),
        (
            lambda value: _set(
                value["technical_effect_diagnostics"][0],
                "factor",
                TechnicalFactor.BUILD,
            ),
            "align with transformation stages",
        ),
        (
            lambda value: _set(
                value["transformation_manifest"],
                "profile_digest",
                _SENTINEL_DIGEST,
            ),
            "manifest contradicts",
        ),
        (lambda value: _set(value["support"], "reason_code", "wrong"), "support contradicts"),
        (
            lambda value: _set(value, "human_review_required", bool(1)),
            "review flag contradicts",
        ),
        (
            lambda value: _set(value, "harmonization_id", "harmonization.wrong"),
            "identifier does not bind",
        ),
        (
            lambda value: _set(value["provenance"], "activity_id", "activity.wrong"),
            "activity does not bind",
        ),
        (
            lambda value: _set(
                value["provenance"],
                "module_id",
                "GLIO-PROTEOGEN-M01-05",
            ),
            "wrong module",
        ),
        (
            lambda value: _set(
                value["provenance"],
                "generated_at",
                value["completed_at"].replace(year=2025),
            ),
            "timestamp",
        ),
        (
            lambda value: _set(
                value["provenance"],
                "configuration_digest",
                _SENTINEL_DIGEST,
            ),
            "provenance contradicts",
        ),
        (
            lambda value: _set(
                value["provenance"],
                "input_digests",
                tuple(
                    digest
                    for digest in value["provenance"]["input_digests"]
                    if digest != value["request_digest"]
                ),
            ),
            "input digests are incomplete",
        ),
        (
            lambda value: _set(value, "evidence", (*value["evidence"], value["evidence"][0])),
            "evidence references must be unique",
        ),
        (lambda value: _set(value["limitations"][0], "code", "wrong"), "requires both"),
        (
            lambda value: _set(value, "result_digest", "sha256:" + ("f" * 64)),
            "digest does not match",
        ),
    ],
)
def test_result_envelope_forgery_is_rejected(
    mutate: Callable[[dict[str, object]], object],
    message: str,
) -> None:
    value = _result_payload()
    mutate(value)

    with pytest.raises(ValidationError, match=message):
        HarmonizationResult.model_validate(value, strict=True)
