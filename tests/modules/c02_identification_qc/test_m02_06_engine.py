"""Focused behavior checks for the unique M02-06 harmonization engine."""

from __future__ import annotations

import pytest
from evals.m02_06.run import build_scenario_request

from glio_proteogen.contracts.m02_06 import (
    M0206_MAX_STAGES,
    DiagnosticStatus,
    HarmonizationDisposition,
    HarmonizationValueState,
    ShiftState,
)
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    harmonize_identification_evidence,
)


def test_eight_stages_reduce_technical_spread_and_preserve_biology() -> None:
    request = build_scenario_request()

    result = harmonize_identification_evidence(request)

    assert result.disposition is HarmonizationDisposition.ACCEPTED
    assert len(result.transformation_manifest.stages) == M0206_MAX_STAGES
    assert all(
        item.status is DiagnosticStatus.PASSED
        and item.before_spread is not None
        and item.after_spread is not None
        and item.after_spread < item.before_spread
        for item in result.technical_effect_diagnostics
    )
    assert all(
        item.status is DiagnosticStatus.PASSED
        for item in result.biological_invariant_diagnostics
    )
    assert all(
        len(item.applied_adjustments) == M0206_MAX_STAGES for item in result.values
    )


def test_observation_and_evidence_permutations_have_identical_json() -> None:
    request = build_scenario_request()
    reordered = request.model_copy(
        update={
            "observations": tuple(
                item.model_copy(update={"evidence": tuple(reversed(item.evidence))})
                for item in reversed(request.observations)
            ),
            "biological_controls": tuple(reversed(request.biological_controls)),
        }
    )

    first = harmonize_identification_evidence(request)
    replay = harmonize_identification_evidence(reordered)

    assert first == replay
    assert first.model_dump_json() == replay.model_dump_json()


def test_excluded_target_is_preserved_but_cannot_train_or_receive_adjustment() -> None:
    request = build_scenario_request("upstream_excluded_target")

    result = harmonize_identification_evidence(request)

    excluded_target = request.prerequisites.artifact_detection.exclusion_mask.excluded_target_ids[0]
    excluded = tuple(item for item in result.values if item.sample_id == excluded_target)
    assert excluded
    assert all(item.output_state is HarmonizationValueState.EXCLUDED for item in excluded)
    assert all(item.harmonized_value is None and not item.applied_adjustments for item in excluded)
    assert all(
        excluded_target not in stage.control_target_ids
        for stage in result.transformation_manifest.stages
    )


def test_nonobserved_values_remain_typed_and_unimputed() -> None:
    result = harmonize_identification_evidence(
        build_scenario_request("typed_nonobserved_states")
    )

    assert result.disposition is HarmonizationDisposition.ABSTAINED
    absent = tuple(
        item
        for item in result.values
        if item.input_state is not HarmonizationValueState.OBSERVED
    )
    assert {item.output_state for item in absent} == {
        HarmonizationValueState.MISSING,
        HarmonizationValueState.CENSORED,
        HarmonizationValueState.NOT_APPLICABLE,
        HarmonizationValueState.UNSUPPORTED,
    }
    assert all(item.harmonized_value is None and not item.applied_adjustments for item in absent)
    assert all(
        item.censoring_limit == item.input_censoring_limit
        for item in absent
        if item.output_state is HarmonizationValueState.CENSORED
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("insufficient_controls", HarmonizationDisposition.ABSTAINED),
        ("capped_shift", HarmonizationDisposition.QUARANTINED),
        ("direction_violation", HarmonizationDisposition.QUARANTINED),
        ("rank_violation", HarmonizationDisposition.QUARANTINED),
        ("unacceptable_prerequisite", HarmonizationDisposition.ABSTAINED),
    ],
)
def test_diagnostic_outcomes_fail_closed(
    mutation: str,
    expected: HarmonizationDisposition,
) -> None:
    result = harmonize_identification_evidence(build_scenario_request(mutation))

    assert result.disposition is expected
    assert result.human_review_required


def test_capped_stage_is_explicit_and_never_accepted() -> None:
    result = harmonize_identification_evidence(build_scenario_request("capped_shift"))

    assert any(
        shift.state is ShiftState.CAPPED
        for stage in result.transformation_manifest.stages
        for shift in stage.level_shifts
    )
    assert any(
        item.capped and item.status is DiagnosticStatus.FAILED
        for item in result.technical_effect_diagnostics
    )


def test_profile_stage_order_remains_semantic() -> None:
    request = build_scenario_request()
    payload = request.profile.model_dump(mode="python")
    payload["stages"] = tuple(reversed(request.profile.stages))

    with pytest.raises(ValueError, match="ordered ordinals"):
        type(request.profile).model_validate(payload)
