"""Substantive relational-rejection coverage for the M04-06 contract boundary."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

import pytest
from evals.m04_06.run import build_scenario_result
from pydantic import ValidationError

from glio_proteogen.contracts.m04_05 import ProteoformArtifactDisposition
from glio_proteogen.contracts.m04_06 import (
    ProteoformArtifactAction,
    ProteoformArtifactEvaluationState,
    ProteoformHarmonizationDisposition,
    ProteoformHarmonizationFindingCode,
    ProteoformHarmonizationResult,
    ProteoformStageTransformation,
    ProteoformSupportObservationState,
    ProteoformSupportShiftState,
    finding_for,
)
from glio_proteogen.kernel.models import SupportStatus

if TYPE_CHECKING:
    from collections.abc import Callable

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_UNKNOWN_LEVEL_ID = "level." + ("f" * 64)


@pytest.fixture(scope="module")
def accepted_result() -> ProteoformHarmonizationResult:
    return build_scenario_result("accepted")


def _replace(values: tuple[object, ...], index: int, value: object) -> tuple[object, ...]:
    return (*values[:index], value, *values[index + 1 :])


def _run_model_validator(value: object, name: str) -> object:
    validator = cast("Callable[[], object]", getattr(value, name))
    return validator()


def _run_field_validator(model: object, name: str, value: object) -> object:
    validator = cast("Callable[[object], object]", getattr(type(model), name))
    return validator(value)


def test_coverage_closure_artifact_receipt_rejects_each_relational_contradiction(
    accepted_result: ProteoformHarmonizationResult,
) -> None:
    receipt = accepted_result.request.artifact_receipt
    first = receipt.targets[0]
    cases = (
        (
            receipt.model_copy(update={"targets": (first, first, *receipt.targets[2:])}),
            "target identifiers must be unique",
        ),
        (receipt.model_copy(update={"targets": ()}), "exact screened target graph"),
        (
            receipt.model_copy(
                update={"artifact_disposition": ProteoformArtifactDisposition.ABSTAINED}
            ),
            "disposition contradicts",
        ),
        (
            receipt.model_copy(
                update={"evaluation_state": ProteoformArtifactEvaluationState.NOT_EVALUABLE}
            ),
            "cannot project successful targets",
        ),
        (
            receipt.model_copy(
                update={
                    "evaluation_state": ProteoformArtifactEvaluationState.NOT_EVALUABLE,
                    "targets": (),
                    "target_count": 0,
                }
            ),
            "cleared artifact receipt",
        ),
        (
            receipt.model_copy(update={"artifact_support_status": SupportStatus.UNSUPPORTED}),
            "support status contradict",
        ),
        (
            receipt.model_copy(update={"artifact_human_review_required": True}),
            "review requirement contradict",
        ),
        (
            receipt.model_copy(
                update={
                    "artifact_reference": receipt.artifact_reference.model_copy(
                        update={"media_type": "application/json"}
                    )
                }
            ),
            "exact M04-05 result ABI",
        ),
        (receipt.model_copy(update={"receipt_digest": _ZERO_DIGEST}), "digest closure failed"),
    )

    for mutant, message in cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(mutant, "receipt_is_closed")


def test_coverage_closure_observation_and_ledger_reject_each_closed_graph_violation(
    accepted_result: ProteoformHarmonizationResult,
) -> None:
    ledger = accepted_result.request.support_ledger
    assert ledger is not None
    observation = ledger.observations[0]
    evidence = observation.evidence[0]
    observation_cases = (
        (
            observation.model_copy(update={"factor_levels": observation.factor_levels[:-1]}),
            "every technical factor",
        ),
        (
            observation.model_copy(update={"evidence": (evidence, evidence)}),
            "evidence digests must be unique",
        ),
        (
            observation.model_copy(update={"artifact_action": ProteoformArtifactAction.REVIEW}),
            "artifact-target receipt",
        ),
        (
            observation.model_copy(update={"support_coordinate_ppm": None}),
            "observed support requires",
        ),
        (
            observation.model_copy(update={"state": ProteoformSupportObservationState.CENSORED}),
            "censored support requires",
        ),
        (
            observation.model_copy(update={"state": ProteoformSupportObservationState.MISSING}),
            "non-observed support cannot",
        ),
    )
    for observation_mutant, message in observation_cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(
                observation_mutant,
                "observation_is_typed_and_closed",
            )

    first_invariant = ledger.invariants[0]
    second_invariant = ledger.invariants[1]
    ledger_cases = (
        (
            ledger.model_copy(
                update={
                    "observations": (
                        ledger.observations[0],
                        ledger.observations[0],
                        *ledger.observations[2:],
                    )
                }
            ),
            "target identifiers must be unique",
        ),
        (
            ledger.model_copy(update={"invariants": ledger.invariants[:-1]}),
            "every protected invariant kind",
        ),
        (
            ledger.model_copy(
                update={
                    "invariants": _replace(
                        ledger.invariants,
                        1,
                        second_invariant.model_copy(
                            update={"invariant_id": first_invariant.invariant_id}
                        ),
                    )
                }
            ),
            "invariant identifiers must be unique",
        ),
        (
            ledger.model_copy(update={"artifact_target_binding_digest": _ZERO_DIGEST}),
            "unit binding",
        ),
        (ledger.model_copy(update={"ledger_digest": _ZERO_DIGEST}), "ledger digest"),
    )
    for ledger_mutant, message in ledger_cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(
                ledger_mutant,
                "ledger_is_content_addressed_and_relationally_closed",
            )


def test_coverage_closure_transformation_manifest_analysis_and_receipt_reject_mutations(
    accepted_result: ProteoformHarmonizationResult,
) -> None:
    manifest = accepted_result.transformation_manifest
    analysis = accepted_result.analysis
    assert manifest is not None
    assert analysis is not None
    stage = manifest.stages[0]
    reference_index = next(
        index
        for index, shift in enumerate(stage.level_shifts)
        if shift.level_id == stage.reference_level_id
    )
    comparison_index = next(
        index for index in range(len(stage.level_shifts)) if index != reference_index
    )
    reference = stage.level_shifts[reference_index]
    comparison = stage.level_shifts[comparison_index]

    def with_shift(index: int, **updates: object) -> ProteoformStageTransformation:
        shift = stage.level_shifts[index].model_copy(update=updates)
        return stage.model_copy(update={"level_shifts": _replace(stage.level_shifts, index, shift)})

    stage_cases = (
        (
            stage.model_copy(
                update={
                    "estimation_anchor_ids": (
                        stage.estimation_anchor_ids[0],
                        stage.estimation_anchor_ids[0],
                    )
                }
            ),
            "identifier collections",
        ),
        (
            stage.model_copy(
                update={
                    "level_shifts": _replace(
                        stage.level_shifts,
                        comparison_index,
                        comparison.model_copy(update={"level_id": reference.level_id}),
                    )
                }
            ),
            "level identifiers must be unique",
        ),
        (
            stage.model_copy(update={"reference_level_id": _UNKNOWN_LEVEL_ID}),
            "exactly one reference-level",
        ),
        (
            with_shift(
                comparison_index,
                state=ProteoformSupportShiftState.NOT_EVALUABLE,
                estimated_shift_ppm=None,
                applied_shift_ppm=None,
                pre_validation_residual_ppm=None,
                post_validation_residual_ppm=None,
                estimation_pair_count=stage.minimum_estimation_pairs,
                validation_pair_count=stage.minimum_validation_pairs,
            ),
            "not-evaluable shift",
        ),
        (
            with_shift(
                comparison_index,
                state=ProteoformSupportShiftState.ESTIMATED,
                estimated_shift_ppm=0,
                applied_shift_ppm=0,
                pre_validation_residual_ppm=0,
                post_validation_residual_ppm=0,
                estimation_pair_count=0,
                validation_pair_count=0,
            ),
            "meet both control-pair minima",
        ),
        (
            with_shift(
                comparison_index,
                state=ProteoformSupportShiftState.ESTIMATED,
                estimated_shift_ppm=None,
                applied_shift_ppm=0,
                pre_validation_residual_ppm=0,
                post_validation_residual_ppm=0,
                estimation_pair_count=stage.minimum_estimation_pairs,
                validation_pair_count=stage.minimum_validation_pairs,
            ),
            "shift is incomplete",
        ),
        (
            with_shift(
                comparison_index,
                state=ProteoformSupportShiftState.ESTIMATED,
                estimated_shift_ppm=stage.maximum_absolute_shift_ppm,
                applied_shift_ppm=stage.maximum_absolute_shift_ppm,
                pre_validation_residual_ppm=0,
                post_validation_residual_ppm=0,
                estimation_pair_count=stage.minimum_estimation_pairs,
                validation_pair_count=stage.minimum_validation_pairs,
            ),
            "estimated fixed-point shift",
        ),
        (
            with_shift(
                comparison_index,
                state=ProteoformSupportShiftState.CAPPED,
                estimated_shift_ppm=0,
                applied_shift_ppm=0,
                pre_validation_residual_ppm=0,
                post_validation_residual_ppm=0,
                estimation_pair_count=stage.minimum_estimation_pairs,
                validation_pair_count=stage.minimum_validation_pairs,
            ),
            "capped fixed-point shift",
        ),
        (
            with_shift(
                reference_index,
                state=ProteoformSupportShiftState.ESTIMATED,
                estimated_shift_ppm=1,
                applied_shift_ppm=1,
                pre_validation_residual_ppm=0,
                post_validation_residual_ppm=0,
                estimation_pair_count=stage.minimum_estimation_pairs,
                validation_pair_count=stage.minimum_validation_pairs,
            ),
            "reference-level shift",
        ),
    )
    for stage_mutant, message in stage_cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(stage_mutant, "transformation_is_closed")

    first_stage = manifest.stages[0]
    second_stage = manifest.stages[1]
    manifest_cases = (
        (
            manifest.model_copy(
                update={
                    "stages": _replace(
                        manifest.stages,
                        0,
                        first_stage.model_copy(update={"ordinal": 2}),
                    )
                }
            ),
            "ordinals are not exact",
        ),
        (
            manifest.model_copy(
                update={
                    "stages": _replace(
                        manifest.stages,
                        1,
                        second_stage.model_copy(update={"stage_id": first_stage.stage_id}),
                    )
                }
            ),
            "identifiers must be unique",
        ),
        (
            manifest.model_copy(
                update={
                    "stages": _replace(
                        manifest.stages,
                        1,
                        second_stage.model_copy(update={"factor": first_stage.factor}),
                    )
                }
            ),
            "cover all eight factors",
        ),
        (
            manifest.model_copy(update={"manifest_digest": _ZERO_DIGEST}),
            "manifest digest",
        ),
    )
    for manifest_mutant, message in manifest_cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(manifest_mutant, "manifest_is_content_addressed")

    first_value = analysis.values[0]
    analysis_cases = (
        (
            analysis.model_copy(
                update={
                    "retain_target_ids": (
                        analysis.retain_target_ids[0],
                        analysis.retain_target_ids[0],
                        *analysis.retain_target_ids[2:],
                    )
                }
            ),
            "partitions require unique targets",
        ),
        (
            analysis.model_copy(update={"review_target_ids": (analysis.retain_target_ids[0],)}),
            "partitions must be disjoint",
        ),
        (
            analysis.model_copy(update={"values": analysis.values[:-1]}),
            "exactly cover",
        ),
        (
            analysis.model_copy(
                update={
                    "values": _replace(
                        analysis.values,
                        0,
                        first_value.model_copy(
                            update={"artifact_action": ProteoformArtifactAction.REVIEW}
                        ),
                    )
                }
            ),
            "partition contradicts",
        ),
        (
            analysis.model_copy(update={"target_count": analysis.target_count + 1}),
            "counts must replay",
        ),
        (analysis.model_copy(update={"analysis_digest": _ZERO_DIGEST}), "analysis digest"),
    )
    for analysis_mutant, message in analysis_cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(analysis_mutant, "analysis_is_content_addressed")
    with pytest.raises(ValueError, match="platform level identifiers must be unique"):
        _run_field_validator(
            analysis,
            "platform_levels_are_canonical",
            (analysis.platform_level_ids[0], analysis.platform_level_ids[0]),
        )

    receipt = accepted_result.receipt
    assert receipt.analysis_target_count is not None
    receipt_cases = (
        (
            receipt.model_copy(update={"analysis_target_count": None}),
            "digest and counts must be present together",
        ),
        (
            receipt.model_copy(update={"analysis_platform_level_ids": ()}),
            "exact platform-level projection",
        ),
        (
            receipt.model_copy(update={"analysis_target_count": receipt.analysis_target_count + 1}),
            "counts contradict",
        ),
    )
    for receipt_mutant, message in receipt_cases:
        with pytest.raises(ValueError, match=message):
            _run_model_validator(receipt_mutant, "analysis_projection_is_closed")
    with pytest.raises(ValueError, match="platform-level identifiers must be unique"):
        _run_field_validator(
            receipt,
            "analysis_platform_levels_are_canonical",
            (
                receipt.analysis_platform_level_ids[0],
                receipt.analysis_platform_level_ids[0],
            ),
        )


def test_coverage_closure_unsealed_result_replay_rejects_each_owned_projection(
    accepted_result: ProteoformHarmonizationResult,
) -> None:
    evidence = accepted_result.evidence[0]
    limitation = accepted_result.limitations[0]
    cases = (
        ({"analysis": None}, "analysis or transformation manifest"),
        ({"technical_effect_diagnostics": ()}, "technical diagnostics"),
        ({"invariant_diagnostics": ()}, "protected invariant diagnostics"),
        (
            {
                "findings": (
                    finding_for(
                        ProteoformHarmonizationFindingCode.HARMONIZATION_PROFILE_UNSUPPORTED
                    ),
                )
            },
            "findings do not replay",
        ),
        ({"request_digest": _ZERO_DIGEST}, "output envelope"),
        (
            {
                "support": accepted_result.support.model_copy(
                    update={"rationale": "Mutated support rationale."}
                )
            },
            "support is not deterministic",
        ),
        (
            {
                "uncertainty": accepted_result.uncertainty.model_copy(
                    update={
                        "sensitivity_notes": (
                            *accepted_result.uncertainty.sensitivity_notes,
                            "mutated sensitivity",
                        )
                    }
                )
            },
            "uncertainty is not deterministic",
        ),
        (
            {
                "provenance": accepted_result.provenance.model_copy(
                    update={"actor_id": accepted_result.provenance.actor_id + ".mutated"}
                )
            },
            "provenance does not close",
        ),
        (
            {
                "evidence": _replace(
                    accepted_result.evidence,
                    0,
                    evidence.model_copy(update={"claim": "mutated evidence claim"}),
                )
            },
            "evidence index does not close",
        ),
        (
            {
                "limitations": _replace(
                    accepted_result.limitations,
                    0,
                    limitation.model_copy(update={"statement": "Mutated limitation."}),
                )
            },
            "limitations do not close",
        ),
        ({"human_review_required": True}, "human-review flag"),
        (
            {"completed_at": accepted_result.completed_at + timedelta(seconds=1)},
            "completion time",
        ),
        ({"result_digest": _ZERO_DIGEST}, "result digest"),
        (
            {"disposition": ProteoformHarmonizationDisposition.QUARANTINED},
            "output envelope",
        ),
    )
    base = accepted_result.model_dump(mode="python")
    for update, message in cases:
        payload = {**base, **update}
        with pytest.raises(ValidationError, match=message):
            ProteoformHarmonizationResult.model_validate(payload, strict=True)
