"""Independent aggregate arithmetic and binding oracles; no source files or fits."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from fractions import Fraction
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError
from tools.run_gbmap_hierarchy_tasks import GbmapHierarchyCheckpoint, GbmapHierarchyRunManifest

from glio_proteogen.research.gbmap_deconvolution.extraction import PRODUCTION_SOURCE_LABELS
from glio_proteogen.research.gbmap_development_reduction import (
    SHRINKAGE_GRID,
    CandidateSelectionReceipt,
    EvaluationOutput,
    FoldPreparation,
    LineageValidationCoverage,
    PlanningFeasibilityReceipt,
    ReducedCandidate,
    ReducedFold,
    ReductionError,
    ValidationCheckpoint,
    ValidationRunManifest,
    ValidationTask,
    assess_manifest_feasibility,
    reduce_completed_validation,
)

if TYPE_CHECKING:
    from collections.abc import Callable

LABELS = ("AC-like", "Astrocyte")
FLAGS = (
    "source_admission_granted",
    "final_model_fitted",
    "model_artifact_emitted",
    "production_artifact_permitted",
    "runtime_mount_permitted",
    "public_http_mounted",
    "public_cli_mounted",
    "source_path_retained",
    "donor_identifiers_retained",
    "donor_hashes_retained",
    "donor_profiles_retained",
    "feature_identities_retained",
    "raw_material_retained",
)


def _digest(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _seal(body: dict[str, Any], field: str, schema: str | None = None) -> dict[str, Any]:
    result = deepcopy(body)
    result.pop(field, None)
    return {**result, field: _digest(result if schema is None else {"schema": schema, **result})}


def _hash(label: str) -> str:
    return _digest({"invented": label})


def _score(index: int, kind: str, label: str) -> float:
    first = label == LABELS[0]
    if index == 0:
        return (1.0 if first else 3.0) if kind == "whole_study" else (4.0 if first else 8.0)
    if index == 1:
        return 3.0
    if index == 2:
        return 2.0 if kind == "whole_study" else 4.0
    return 5.0 if kind == "whole_study" else 1.0


def _fixture(
    *,
    whole: int = 3,
    within: int = 5,
    preparation_abstention: bool = True,
    score: Callable[[int, str, str], float] = _score,
    failure: tuple[str, int, str, str] | None = None,
) -> tuple[ValidationRunManifest, tuple[ValidationCheckpoint, ...]]:
    preparation = []
    tasks = []
    for kind, count in (("whole_study", whole), ("within_study_donor", within)):
        prefix = "whole-study" if kind == "whole_study" else "within-study-donor"
        for number in range(1, count + 1):
            fold = f"{prefix}-{number:04d}"
            preparation.append(
                {
                    "fold_id": fold,
                    "kind": kind,
                    "state": "prepared",
                    "abstention_reason": None,
                    "eligible_lineage_count": 2,
                    "selected_feature_count": 12,
                }
            )
            for index, shrinkage in enumerate(SHRINKAGE_GRID):
                for label in LABELS:
                    task = {
                        "fold_id": fold,
                        "kind": kind,
                        "shrinkage_index": index,
                        "shrinkage": shrinkage,
                        "modeled_label": label,
                        "training_record_count": 8 if label == LABELS[0] else 80,
                        "training_study_count": 3,
                        "selected_feature_count": 12,
                        "selected_feature_axis_digest": _hash(fold + "features"),
                        "training_matrix_digest": _hash(fold + label + "training"),
                    }
                    tasks.append(
                        _seal(task, "task_digest", "gbmap-hierarchy-validation-task/1.0.0")
                    )
    if preparation_abstention:
        preparation.append(
            {
                "fold_id": "within-study-donor-9999",
                "kind": "within_study_donor",
                "state": "abstained",
                "abstention_reason": "split_not_evaluable",
                "eligible_lineage_count": 0,
                "selected_feature_count": 0,
            }
        )
    tasks.sort(key=lambda x: (x["fold_id"], x["shrinkage_index"], x["modeled_label"]))
    preparation.sort(key=lambda x: x["fold_id"])
    manifest_body = {
        "schema_version": "glio-proteogen.gbmap-hierarchy-run-manifest/1.0.0",
        "run_state": "development_validation_hierarchy_tasks_only",
        "reviewed_sha256": _hash("invented-source-not-real-data"),
        "source_bytes": 99,
        "taxonomy_digest": _hash("taxonomy"),
        "extraction_recipe_digest": _hash("recipe"),
        "extraction_receipt_digest": _hash("extraction"),
        "preflight_receipt_digest": _hash("preflight"),
        "preflight_task_dimensions_digest": _hash("dimensions"),
        "profile_id": "gbmap-dm-composition/0.1.0-dev",
        "profile_digest": _hash("profile"),
        "engine_semantic_digest": _hash("engine"),
        "training_configuration_digest": _hash("config"),
        "split_receipt_digest": _hash("splits"),
        "feature_order_digest": _hash("features"),
        "preparation_receipts": tuple(preparation),
        "task_count": len(tasks),
        "preflight_hierarchy_fit_upper_bound": len(tasks),
        "tasks": tuple(tasks),
        "task_inventory_digest": _digest(
            {"schema": "gbmap-hierarchy-task-inventory/1.0.0", "tasks": tasks}
        ),
        **dict.fromkeys(FLAGS, False),
    }
    manifest = ValidationRunManifest.model_validate(_seal(manifest_body, "manifest_digest"))
    checkpoints = []
    for task in tasks:
        reason = None
        if (
            failure is not None
            and (task["fold_id"], task["shrinkage_index"], task["modeled_label"]) == failure[:3]
        ):
            reason = failure[3]
        fit_failed = reason == "hierarchy_fit_failed"
        evaluation = {
            "state": "evaluated" if reason is None else "abstained",
            "abstention_reason": reason,
            "hierarchy_fit_digest": None if fit_failed else _hash(task["task_digest"] + "fit"),
            "hierarchy_trace_digest": None if fit_failed else _hash(task["task_digest"] + "trace"),
            "hierarchy_converged": None if fit_failed else reason != "hierarchy_did_not_converge",
            "hierarchy_iterations": None if fit_failed else 10,
            "hierarchy_initial_objective": None if fit_failed else 10.0,
            "hierarchy_objective": None if fit_failed else 5.0,
            "hierarchy_kkt_residual": None if fit_failed else 1e-8,
            "evaluated_held_record_count": 0
            if reason
            else (1 if task["modeled_label"] == LABELS[0] else 100),
            "evaluated_held_study_count": 0 if reason else 1,
            "mean_per_count_nll": None
            if reason
            else score(task["shrinkage_index"], task["kind"], task["modeled_label"]),
        }
        evaluation = _seal(
            evaluation, "evaluation_output_digest", "gbmap-hierarchy-evaluation-output/1.0.0"
        )
        body = {
            "schema_version": "glio-proteogen.gbmap-hierarchy-checkpoint/1.0.0",
            "manifest_digest": manifest.manifest_digest,
            **{
                key: task[key]
                for key in (
                    "task_digest",
                    "fold_id",
                    "kind",
                    "shrinkage_index",
                    "shrinkage",
                    "modeled_label",
                    "selected_feature_axis_digest",
                    "training_matrix_digest",
                )
            },
            **{
                key: manifest_body[key]
                for key in (
                    "reviewed_sha256",
                    "profile_digest",
                    "engine_semantic_digest",
                    "training_configuration_digest",
                    "split_receipt_digest",
                    "feature_order_digest",
                )
            },
            "evaluation": evaluation,
            **dict.fromkeys(FLAGS, False),
        }
        checkpoints.append(ValidationCheckpoint.model_validate(_seal(body, "checkpoint_digest")))
    return manifest, tuple(checkpoints)


def _checkpoint(row: ValidationCheckpoint, **changes: Any) -> ValidationCheckpoint:
    return ValidationCheckpoint.model_validate(
        _seal({**row.model_dump(mode="python"), **changes}, "checkpoint_digest")
    )


def _manifest(body: dict[str, Any]) -> ValidationRunManifest:
    body = deepcopy(body)
    body["task_count"] = len(body["tasks"])
    body["task_inventory_digest"] = _digest(
        {"schema": "gbmap-hierarchy-task-inventory/1.0.0", "tasks": body["tasks"]}
    )
    return ValidationRunManifest.model_validate(_seal(body, "manifest_digest"))


def test_independent_equal_lineage_then_equal_family_oracle_and_exact_tie() -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    expected = float((Fraction(2) + Fraction(6)) / 2)
    first = result.candidates[0]
    assert (
        first.whole_study_mean_nll,
        first.within_study_donor_mean_nll,
        first.selection_score,
    ) == (2.0, 6.0, expected)
    assert first.selection_score != float((Fraction(2) * 3 + Fraction(6) * 5) / 8)
    assert first.folds[0].mean_per_count_nll == float((Fraction(1) + Fraction(3)) / 2)
    assert first.folds[0].mean_per_count_nll != float((Fraction(1) + Fraction(3) * 100) / 101)
    assert result.selected_shrinkage == 1.0
    assert [x.selection_score for x in result.candidates] == [4.0, 3.0, 3.0, 3.0]
    assert result.selected_shrinkage_index == 1
    assert result.selection_abstention_reason is None
    assert result.receipt_digest == _digest(
        result.model_dump(mode="json", exclude={"receipt_digest"})
    )
    assert result.checkpoint_set_digest == _digest(
        {
            "schema": "gbmap-complete-checkpoint-set/1.0.0",
            "checkpoint_digests": [x.checkpoint_digest for x in rows],
        }
    )


def test_complete_checkpoint_order_is_irrelevant_and_exact_original_tool_shapes_adapt() -> None:
    manifest, rows = _fixture()
    old_manifest = GbmapHierarchyRunManifest.model_validate(manifest.model_dump(mode="python"))
    old_rows = tuple(
        GbmapHierarchyCheckpoint.model_validate(x.model_dump(mode="python")) for x in rows
    )
    adapted = ValidationRunManifest.model_validate(old_manifest.model_dump(mode="python"))
    checkpoints = tuple(
        ValidationCheckpoint.model_validate(x.model_dump(mode="python")) for x in old_rows
    )
    assert reduce_completed_validation(adapted, checkpoints) == reduce_completed_validation(
        manifest, tuple(reversed(rows))
    )


def test_preparation_abstentions_retained_for_every_candidate() -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    for candidate in result.candidates:
        abstained = candidate.folds[-1]
        assert abstained.fold_id == "within-study-donor-9999"
        assert abstained.state == "abstained"
        assert abstained.abstention_reason == "split_not_evaluable"
        assert (
            abstained.task_count
            == abstained.evaluated_task_count
            == abstained.evaluated_held_record_count
            == 0
        )
        assert abstained.mean_per_count_nll is None


@pytest.mark.parametrize(
    ("reason", "fold_reason"),
    [
        ("hierarchy_fit_failed", "hierarchy_fit_failed"),
        ("hierarchy_trace_invalid", "hierarchy_did_not_converge"),
        ("hierarchy_did_not_converge", "hierarchy_did_not_converge"),
        ("no_positive_held_marker_counts", "no_positive_held_marker_counts"),
    ],
)
def test_one_lineage_failure_abstains_whole_fold_without_partial_score(
    reason: str, fold_reason: str
) -> None:
    manifest, rows = _fixture(failure=("within-study-donor-0001", 1, LABELS[0], reason))
    result = reduce_completed_validation(manifest, rows)
    candidate = result.candidates[1]
    fold = next(x for x in candidate.folds if x.fold_id == "within-study-donor-0001")
    assert fold.state == "abstained" and fold.abstention_reason == fold_reason
    assert fold.evaluated_task_count == 1 and fold.task_count == 2
    assert fold.mean_per_count_nll is None and fold.evaluated_held_record_count == 0
    assert candidate.within_study_donor_fold_count == 4
    assert candidate.selection_score is None and not candidate.selectable
    assert result.selected_shrinkage == 10.0
    assert not candidate.lineage_coverage[0].validation_coverage_eligible
    assert candidate.lineage_coverage[1].within_study_donor_fold_count == 4


def test_planning_identifies_four_of_five_infeasibility_before_any_checkpoints() -> None:
    manifest, rows = _fixture(within=4)
    planning = assess_manifest_feasibility(manifest)
    assert planning.planning_gate_status == "infeasible_preparation_support"
    assert planning.prepared_within_study_donor_folds == 4
    assert planning.within_study_donor_shortfall == 1
    assert planning.minimum_within_study_donor_folds == 5
    assert planning.model_selection_performed is False
    result = reduce_completed_validation(manifest, rows)
    assert result.selected_shrinkage is None and result.selected_shrinkage_index is None
    assert result.selection_abstention_reason == "no_candidate_passes_validation_family_gates"
    assert all(not x.selectable for x in result.candidates)
    assert len(result.lineage_coverage) == 20
    assert all(x.abstention_reasons[0] == "no_selected_candidate" for x in result.lineage_coverage)


def test_new_three_and_five_policy_is_count_coverage_only_with_all_twenty_labels() -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    assert result.planning.planning_gate_status == "potentially_feasible"
    assert tuple(x.modeled_label for x in result.lineage_coverage) == PRODUCTION_SOURCE_LABELS
    for record in result.lineage_coverage:
        if record.modeled_label in LABELS:
            assert (record.whole_study_fold_count, record.within_study_donor_fold_count) == (3, 5)
            assert record.validation_coverage_eligible and record.abstention_reasons == ()
        else:
            assert (record.whole_study_fold_count, record.within_study_donor_fold_count) == (0, 0)
            assert not record.validation_coverage_eligible and len(record.abstention_reasons) == 2
        assert record.full_source_support_rechecked is False
        assert record.final_fit_eligibility_established is False
    assert result.mixture_accuracy_established is False
    assert result.external_validation_established is False
    assert result.private_training_matrix_reconstruction_performed is False
    assert result.selection_score_is_unbiased_performance_estimate is False
    assert all(getattr(result, flag) is False for flag in FLAGS)


@pytest.mark.parametrize(
    ("whole", "within", "expected"),
    [(2, 5, False), (3, 4, False), (3, 5, True), (4, 6, True), (0, 0, False)],
)
def test_support_boundaries_and_empty_task_inventory(
    whole: int, within: int, *, expected: bool
) -> None:
    manifest, rows = _fixture(whole=whole, within=within)
    result = reduce_completed_validation(manifest, rows)
    assert all(x.selectable is expected for x in result.candidates)
    assert (result.selected_shrinkage is not None) is expected
    assert result.completed_checkpoint_count == len(rows)


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "list", "foreign_type"])
def test_incomplete_duplicate_extra_and_nonclosed_checkpoint_input_fail(change: str) -> None:
    manifest, rows = _fixture()
    value: Any = rows
    if change == "missing":
        value = rows[:-1]
    elif change == "duplicate":
        value = (*rows[:-1], rows[0])
    elif change == "extra":
        value = (*rows[:-1], _checkpoint(rows[-1], task_digest=_hash("extra-task")))
    elif change == "list":
        value = list(rows)
    else:
        value = (*rows[:-1], rows[-1].model_dump(mode="python"))
    with pytest.raises(ReductionError):
        reduce_completed_validation(manifest, value)


@pytest.mark.parametrize(
    "field",
    [
        "manifest_digest",
        "reviewed_sha256",
        "profile_digest",
        "engine_semantic_digest",
        "training_configuration_digest",
        "split_receipt_digest",
        "feature_order_digest",
        "selected_feature_axis_digest",
        "training_matrix_digest",
    ],
)
def test_resealed_foreign_provenance_or_training_basis_is_rejected(field: str) -> None:
    manifest, rows = _fixture()
    changed = _checkpoint(rows[0], **{field: _hash("foreign-" + field)})
    with pytest.raises(ReductionError, match="provenance"):
        reduce_completed_validation(manifest, (changed, *rows[1:]))


@pytest.mark.parametrize(
    "field", ["fold_id", "kind", "shrinkage_index", "shrinkage", "modeled_label"]
)
def test_resealed_foreign_task_coordinates_fail(field: str) -> None:
    manifest, rows = _fixture()
    changes: dict[str, Any] = {"modeled_label": "MES-like"}
    if field in ("shrinkage", "shrinkage_index"):
        changes = {"shrinkage": 1.0, "shrinkage_index": 1}
    elif field in ("fold_id", "kind"):
        changes = {"fold_id": "within-study-donor-0001", "kind": "within_study_donor"}
    with pytest.raises(ReductionError, match="provenance"):
        reduce_completed_validation(manifest, (_checkpoint(rows[0], **changes), *rows[1:]))


@pytest.mark.parametrize("which", ["task", "evaluation", "checkpoint", "inventory", "manifest"])
def test_every_individual_canonical_seal_is_recomputed(which: str) -> None:
    manifest, rows = _fixture()
    if which == "task":
        body = manifest.tasks[0].model_dump(mode="python")
        body["training_record_count"] += 1
        with pytest.raises(ValidationError):
            ValidationTask.model_validate(body)
    elif which == "evaluation":
        body = rows[0].evaluation.model_dump(mode="python")
        body["mean_per_count_nll"] += 1.0
        with pytest.raises(ValidationError):
            EvaluationOutput.model_validate(body)
    elif which == "checkpoint":
        body = rows[0].model_dump(mode="python")
        body["manifest_digest"] = _hash("changed")
        with pytest.raises(ValidationError):
            ValidationCheckpoint.model_validate(body)
    else:
        body = manifest.model_dump(mode="python")
        body["task_inventory_digest" if which == "inventory" else "manifest_digest"] = _hash(
            "changed"
        )
        with pytest.raises(ValidationError):
            ValidationRunManifest.model_validate(body)


def test_forged_frozen_instances_revalidated_and_no_input_mutation() -> None:
    manifest, rows = _fixture()
    before = manifest.model_dump(mode="json"), [x.model_dump(mode="json") for x in rows]
    reduce_completed_validation(manifest, rows)
    assert before == (manifest.model_dump(mode="json"), [x.model_dump(mode="json") for x in rows])
    with pytest.raises(ValidationError):
        manifest.task_count = 0  # type: ignore[misc]
    corrupt = rows[0].model_copy(
        update={"evaluation": rows[0].evaluation.model_copy(update={"mean_per_count_nll": 999.0})}
    )
    with pytest.raises(ReductionError, match="revalidation"):
        reduce_completed_validation(manifest, (corrupt, *rows[1:]))
    corrupt_manifest = manifest.model_copy(update={"source_bytes": 100})
    with pytest.raises(ReductionError, match="revalidation"):
        assess_manifest_feasibility(corrupt_manifest)


@pytest.mark.parametrize(
    "mutation",
    [
        "task_missing_candidate",
        "task_duplicate",
        "task_unknown_fold",
        "task_wrong_family",
        "axis_changed",
        "matrix_changed",
        "prep_count",
        "prep_abstained",
        "fold_duplicate",
        "task_order",
    ],
)
def test_resealed_structurally_inconsistent_manifests_fail(mutation: str) -> None:
    manifest, _rows = _fixture()
    body = manifest.model_dump(mode="python")
    tasks = list(body["tasks"])
    preparations = list(body["preparation_receipts"])
    if mutation == "task_missing_candidate":
        tasks.pop(0)
    elif mutation == "task_duplicate":
        tasks[1] = tasks[0]
    elif mutation == "task_order":
        tasks[0], tasks[1] = tasks[1], tasks[0]
    elif mutation == "fold_duplicate":
        preparations.append(preparations[-1])
    elif mutation in ("prep_count", "prep_abstained"):
        preparations[0] = {
            **preparations[0],
            **(
                {"eligible_lineage_count": 3}
                if mutation == "prep_count"
                else {"state": "abstained", "abstention_reason": "split_not_evaluable"}
            ),
        }
    else:
        changed = dict(tasks[2])
        if mutation == "task_unknown_fold":
            changed["fold_id"] = "whole-study-9999"
        elif mutation == "task_wrong_family":
            changed["kind"] = "within_study_donor"
        elif mutation == "axis_changed":
            changed["selected_feature_axis_digest"] = _hash("different-axis")
        else:
            changed["training_matrix_digest"] = _hash("different-matrix")
        tasks[2] = _seal(changed, "task_digest", "gbmap-hierarchy-validation-task/1.0.0")
    body.update(tasks=tuple(tasks), preparation_receipts=tuple(preparations))
    with pytest.raises(ValidationError):
        _manifest(body)


@pytest.mark.parametrize("value", [True, 1, "1.0", float("nan"), float("inf")])
def test_strict_finite_source_float_contracts(value: Any) -> None:
    manifest, rows = _fixture()
    task = {**manifest.tasks[0].model_dump(mode="python"), "shrinkage": value}
    with pytest.raises(ValidationError):
        ValidationTask.model_validate(task)
    evaluation = {**rows[0].evaluation.model_dump(mode="python"), "mean_per_count_nll": value}
    with pytest.raises(ValidationError):
        EvaluationOutput.model_validate(evaluation)


@pytest.mark.parametrize("flag", FLAGS)
@pytest.mark.parametrize("value", [0, True, "false"])
def test_permission_and_privacy_flags_cannot_be_coerced(flag: str, value: Any) -> None:
    manifest, _rows = _fixture()
    with pytest.raises(ValidationError):
        ValidationRunManifest.model_validate({**manifest.model_dump(mode="python"), flag: value})


def test_generic_versioned_profile_binding_not_current_digest_hardcoding() -> None:
    manifest, _rows = _fixture()
    body = manifest.model_dump(mode="python")
    body.update(
        profile_id="gbmap-dm-composition/0.2.0-dev",
        profile_digest=_hash("future-reviewed-profile"),
        engine_semantic_digest=_hash("future-reviewed-engine"),
    )
    future = _manifest(body)
    assert assess_manifest_feasibility(future).planning_gate_status == "potentially_feasible"


def test_no_source_io_fitting_or_numerical_truth_claim_in_public_receipt() -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    raw = result.model_dump_json()
    assert "invented-source-not-real-data" not in raw
    assert all(
        token not in raw
        for token in (
            "donor_key",
            "gene_counts",
            "detected_cell_counts",
            "signature_matrix",
            "concentrations",
            "training_matrix_digest",
        )
    )
    assert len(result.lineage_coverage) == 20
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(
            {**result.model_dump(mode="python"), "patient_values": (1, 2, 3)}
        )


def test_resealed_selection_cannot_change_winner_or_drop_taxonomy() -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    body = result.model_dump(mode="python")
    body.update(selected_shrinkage_index=2, selected_shrinkage=10.0)
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(_seal(body, "receipt_digest"))
    body = result.model_dump(mode="python")
    body["lineage_coverage"] = body["lineage_coverage"][:-1]
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(_seal(body, "receipt_digest"))


def test_closed_output_receipts_reject_resealed_arithmetic_and_coverage_fictions() -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    with pytest.raises(ValidationError):
        ReducedCandidate.model_validate(
            {**result.candidates[0].model_dump(mode="python"), "selection_score": 1.0}
        )
    with pytest.raises(ValidationError):
        ReducedFold.model_validate(
            {**result.candidates[0].folds[0].model_dump(mode="python"), "evaluated_task_count": 1}
        )
    with pytest.raises(ValidationError):
        LineageValidationCoverage.model_validate(
            {
                **result.lineage_coverage[0].model_dump(mode="python"),
                "validation_coverage_eligible": False,
            }
        )
    planning = result.planning.model_dump(mode="python")
    planning["within_study_donor_shortfall"] = 1
    with pytest.raises(ValidationError):
        PlanningFeasibilityReceipt.model_validate(_seal(planning, "receipt_digest"))
    with pytest.raises(ValidationError):
        FoldPreparation.model_validate(
            {
                "fold_id": "whole-study-0001",
                "kind": "within_study_donor",
                "state": "prepared",
                "abstention_reason": None,
                "eligible_lineage_count": 2,
                "selected_feature_count": 12,
            }
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "prepared", "abstention_reason": "split_not_evaluable"},
        {"eligible_lineage_count": 1},
        {"selected_feature_count": 1},
        {"state": "abstained", "abstention_reason": None},
    ],
)
def test_preparation_state_and_dimensions_are_closed(changes: dict[str, Any]) -> None:
    manifest, _ = _fixture()
    body = {**manifest.preparation_receipts[0].model_dump(mode="python"), **changes}
    with pytest.raises(ValidationError):
        FoldPreparation.model_validate(body)


@pytest.mark.parametrize(
    "changes",
    [
        {"modeled_label": "unknown-label"},
        {"shrinkage": 1.0},
        {"training_study_count": 9},
        {"training_record_count": True},
        {"selected_feature_count": 513},
        {"shrinkage_index": 4},
    ],
)
def test_task_taxonomy_grid_and_integer_domains_are_closed(changes: dict[str, Any]) -> None:
    manifest, _ = _fixture()
    body = {**manifest.tasks[0].model_dump(mode="python"), **changes}
    with pytest.raises(ValidationError):
        ValidationTask.model_validate(
            _seal(body, "task_digest", "gbmap-hierarchy-validation-task/1.0.0")
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"hierarchy_converged": False},
        {"hierarchy_fit_digest": None},
        {"mean_per_count_nll": None},
        {"evaluated_held_record_count": 0},
        {"state": "abstained", "abstention_reason": "hierarchy_fit_failed"},
        {
            "state": "abstained",
            "abstention_reason": "hierarchy_fit_failed",
            "mean_per_count_nll": None,
            "evaluated_held_record_count": 0,
            "evaluated_held_study_count": 0,
        },
        {
            "state": "abstained",
            "abstention_reason": "hierarchy_did_not_converge",
            "mean_per_count_nll": None,
            "evaluated_held_record_count": 0,
            "evaluated_held_study_count": 0,
            "hierarchy_fit_digest": None,
        },
        {"evaluated_held_study_count": 2},
    ],
)
def test_evaluation_diagnostics_and_missing_held_scores_cannot_be_fabricated(
    changes: dict[str, Any],
) -> None:
    _, rows = _fixture()
    body = {**rows[0].evaluation.model_dump(mode="python"), **changes}
    with pytest.raises(ValidationError):
        EvaluationOutput.model_validate(
            _seal(body, "evaluation_output_digest", "gbmap-hierarchy-evaluation-output/1.0.0")
        )


@pytest.mark.parametrize("changes", [{"modeled_label": "unknown-label"}, {"shrinkage": 1.0}])
def test_checkpoint_taxonomy_grid_violations_rejected_even_when_resealed(
    changes: dict[str, Any],
) -> None:
    _, rows = _fixture()
    with pytest.raises(ValidationError):
        _checkpoint(rows[0], **changes)


@pytest.mark.parametrize(
    "change",
    [
        "count",
        "upper_bound",
        "unknown_fold",
        "first_axis",
        "missing_second_candidate",
        "feature_dimensions",
    ],
)
def test_manifest_semantic_conservation_is_checked_before_reduction(change: str) -> None:
    manifest, _ = _fixture()
    body = manifest.model_dump(mode="python")
    if change == "count":
        body["task_count"] -= 1
    elif change == "upper_bound":
        body["preflight_hierarchy_fit_upper_bound"] -= 1
    else:
        tasks = list(body["tasks"])
        if change == "missing_second_candidate":
            tasks.pop(2)
        else:
            changed = dict(tasks[1] if change == "first_axis" else tasks[2])
            if change == "unknown_fold":
                changed["fold_id"] = "whole-study-9999"
            elif change == "first_axis":
                changed["selected_feature_axis_digest"] = _hash("other-union")
            else:
                changed["selected_feature_count"] = 13
            tasks[1 if change == "first_axis" else 2] = _seal(
                changed, "task_digest", "gbmap-hierarchy-validation-task/1.0.0"
            )
        tasks.sort(key=lambda x: (x["fold_id"], x["shrinkage_index"], x["modeled_label"]))
        body["tasks"] = tuple(tasks)
        body["task_count"] = len(tasks)
        body["task_inventory_digest"] = _digest(
            {"schema": "gbmap-hierarchy-task-inventory/1.0.0", "tasks": tasks}
        )
    with pytest.raises(ValidationError):
        ValidationRunManifest.model_validate(_seal(body, "manifest_digest"))


@pytest.mark.parametrize(
    "changes",
    [
        {"evaluated_task_count": 3},
        {"selected_feature_count": 0},
        {"state": "abstained", "abstention_reason": "hierarchy_fit_failed"},
        {
            "state": "abstained",
            "abstention_reason": "split_not_evaluable",
            "mean_per_count_nll": None,
            "evaluated_held_record_count": 0,
        },
        {
            "state": "abstained",
            "abstention_reason": "hierarchy_fit_failed",
            "mean_per_count_nll": None,
            "evaluated_held_record_count": 0,
        },
    ],
)
def test_fold_partial_success_cannot_become_an_accepted_or_preparation_fold(
    changes: dict[str, Any],
) -> None:
    manifest, rows = _fixture()
    fold = reduce_completed_validation(manifest, rows).candidates[0].folds[0]
    with pytest.raises(ValidationError):
        ReducedFold.model_validate({**fold.model_dump(mode="python"), **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"modeled_label": "unknown-label"},
        {"abstention_reasons": ("no_selected_candidate",)},
        {"full_source_support_rechecked": 0},
    ],
)
def test_lineage_ledgers_do_not_invent_identity_or_completed_source_support(
    changes: dict[str, Any],
) -> None:
    manifest, rows = _fixture()
    ledger = reduce_completed_validation(manifest, rows).lineage_coverage[0]
    with pytest.raises(ValidationError):
        LineageValidationCoverage.model_validate({**ledger.model_dump(mode="python"), **changes})


@pytest.mark.parametrize(
    "change", ["index", "fold_axis", "family_count", "taxonomy", "lineage_upper_bound"]
)
def test_candidate_resealed_aggregate_contradictions_rejected(change: str) -> None:
    manifest, rows = _fixture()
    candidate = reduce_completed_validation(manifest, rows).candidates[0]
    body = candidate.model_dump(mode="python")
    if change == "index":
        body["shrinkage"] = 1.0
    elif change == "fold_axis":
        body["folds"] = tuple(reversed(body["folds"]))
    elif change == "family_count":
        body["whole_study_fold_count"] += 1
    elif change == "taxonomy":
        body["lineage_coverage"] = tuple(reversed(body["lineage_coverage"]))
    else:
        ledger = list(body["lineage_coverage"])
        ledger[0] = {**ledger[0], "whole_study_fold_count": 4}
        body["lineage_coverage"] = tuple(ledger)
    with pytest.raises(ValidationError):
        ReducedCandidate.model_validate(body)


@pytest.mark.parametrize(
    "change",
    [
        "checkpoint_count",
        "candidate_order",
        "planning_binding",
        "planning_counts",
        "missing_selected",
        "taxonomy",
        "receipt_seal",
        "false_scope",
    ],
)
def test_selection_receipt_closed_and_self_consistent_beyond_its_hash(change: str) -> None:
    manifest, rows = _fixture()
    result = reduce_completed_validation(manifest, rows)
    body = result.model_dump(mode="python")
    if change == "checkpoint_count":
        body["completed_checkpoint_count"] -= 1
    elif change == "candidate_order":
        body["candidates"] = tuple(reversed(body["candidates"]))
    elif change in ("planning_binding", "planning_counts"):
        planning = body["planning"]
        if change == "planning_binding":
            planning["manifest_digest"] = _hash("foreign")
        else:
            planning["prepared_whole_study_folds"] = 4
        body["planning"] = _seal(planning, "receipt_digest")
    elif change == "missing_selected":
        body["selected_shrinkage"] = None
    elif change == "taxonomy":
        body["lineage_coverage"] = tuple(reversed(body["lineage_coverage"]))
    elif change == "false_scope":
        body["external_validation_established"] = 0
    else:
        body["receipt_digest"] = _hash("not-a-seal")
        with pytest.raises(ValidationError):
            CandidateSelectionReceipt.model_validate(body)
        return
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(_seal(body, "receipt_digest"))


def test_none_selection_remains_explicit_and_ledgers_cannot_launder_an_unsupported_candidate() -> (
    None
):
    manifest, rows = _fixture(within=4)
    result = reduce_completed_validation(manifest, rows)
    body = result.model_dump(mode="python")
    body["selected_shrinkage"] = 0.1
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(_seal(body, "receipt_digest"))
    body = result.model_dump(mode="python")
    body["lineage_coverage"] = body["candidates"][0]["lineage_coverage"]
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(_seal(body, "receipt_digest"))
    body = result.model_dump(mode="python")
    body["lineage_coverage"] = tuple(reversed(body["lineage_coverage"]))
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(_seal(body, "receipt_digest"))


def test_planning_bound_and_seal_and_exact_manifest_type() -> None:
    manifest, _ = _fixture()
    planning = assess_manifest_feasibility(manifest).model_dump(mode="python")
    planning.update(prepared_whole_study_folds=1024, prepared_within_study_donor_folds=5)
    with pytest.raises(ValidationError):
        PlanningFeasibilityReceipt.model_validate(_seal(planning, "receipt_digest"))
    planning = assess_manifest_feasibility(manifest).model_dump(mode="python")
    planning["receipt_digest"] = _hash("wrong")
    with pytest.raises(ValidationError):
        PlanningFeasibilityReceipt.model_validate(planning)
    with pytest.raises(ReductionError):
        assess_manifest_feasibility(manifest.model_dump(mode="python"))  # type: ignore[arg-type]


@pytest.mark.parametrize("within", [4, 5])
def test_closed_json_roundtrip_preserves_strict_nested_tuple_context_and_exact_false(
    within: int,
) -> None:
    manifest, checkpoints = _fixture(within=within)
    manifest_json = manifest.model_dump_json()
    restored_manifest = ValidationRunManifest.model_validate_json(manifest_json)
    restored_checkpoints = tuple(
        ValidationCheckpoint.model_validate_json(row.model_dump_json()) for row in checkpoints
    )
    expected = reduce_completed_validation(manifest, checkpoints)
    actual = reduce_completed_validation(restored_manifest, restored_checkpoints)
    assert actual == expected
    assert CandidateSelectionReceipt.model_validate_json(expected.model_dump_json()) == expected
    assert (
        PlanningFeasibilityReceipt.model_validate_json(expected.planning.model_dump_json())
        == expected.planning
    )
    assert isinstance(actual.candidates, tuple) and isinstance(actual.lineage_coverage, tuple)
    assert all(isinstance(row.folds, tuple) for row in actual.candidates)
    document = expected.model_dump(mode="json")
    document["external_validation_established"] = 0
    with pytest.raises(ValidationError, match="fixed false"):
        CandidateSelectionReceipt.model_validate_json(json.dumps(document))
    python_manifest = manifest.model_dump(mode="python")
    python_manifest["tasks"] = list(python_manifest["tasks"])
    with pytest.raises(ValidationError):
        ValidationRunManifest.model_validate(python_manifest)
    python_result = expected.model_dump(mode="python")
    python_result["candidates"] = list(python_result["candidates"])
    with pytest.raises(ValidationError):
        CandidateSelectionReceipt.model_validate(python_result)


def test_every_closed_fixed_false_field_has_scalar_exact_false_validation() -> None:
    manifest, checkpoints = _fixture()
    result = reduce_completed_validation(manifest, checkpoints)
    objects = (manifest, checkpoints[0], result.planning, result.lineage_coverage[0], result)
    checked_names = set()
    for instance in objects:
        model = type(instance)
        for name, field in model.model_fields.items():
            if field.default is not False:
                continue
            checked_names.add(name)
            body = {**instance.model_dump(mode="json"), name: 0}
            with pytest.raises(ValidationError, match="fixed false"):
                model.model_validate_json(json.dumps(body))
    assert len(checked_names) == 21
