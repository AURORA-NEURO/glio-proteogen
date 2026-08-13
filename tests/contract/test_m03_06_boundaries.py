"""Adversarial boundary coverage for M03-06 support harmonization."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any, cast

import pytest
from evals.m03_06.run import build_capacity_scenario_request, build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m03_05 import (
    ProteinInferenceArtifactDisposition,
)
from glio_proteogen.contracts.m03_06 import (
    M0306_MAX_CANONICAL_REQUEST_BYTES,
    M0306_MAX_UNITS,
    M0306_ZERO_DIGEST,
    HarmonizeProteinInferenceSupportRequest,
    ProteinInferenceArtifactAction,
    ProteinInferenceArtifactEvaluationState,
    ProteinInferenceArtifactHarmonizationReceipt,
    ProteinInferenceArtifactUnitReceipt,
    ProteinInferenceHarmonizationDiagnosticStatus,
    ProteinInferenceHarmonizationDisposition,
    ProteinInferenceHarmonizationFinding,
    ProteinInferenceHarmonizationFindingCode,
    ProteinInferenceHarmonizationProfile,
    ProteinInferenceHarmonizationResult,
    ProteinInferenceHarmonizedAnalysis,
    ProteinInferenceHarmonizedSupportValue,
    ProteinInferenceInvariantDiagnostic,
    ProteinInferenceStageTransformation,
    ProteinInferenceSupportInvariantKind,
    ProteinInferenceSupportLedger,
    ProteinInferenceSupportLevelShift,
    ProteinInferenceSupportObservationState,
    ProteinInferenceSupportShiftState,
    ProteinInferenceTechnicalEffectDiagnostic,
    ProteinInferenceTransformationManifest,
    analysis_digest,
    artifact_receipt_digest,
    canonical_request_digest,
    configuration_digest,
    expected_disposition,
    expected_harmonization_findings,
    finding_for,
    harmonization_ledger_bindings_close,
    matching_harmonization_profile,
    normalized_result,
    opaque_harmonization_identifier,
    preflight_authorized,
    result_payload_digest,
    support_ledger_digest,
    transformation_manifest_digest,
    unit_binding_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c03_protein_inference.m03_06_harmonization import (
    harmonize_protein_inference_support,
)


@pytest.fixture(scope="module")
def canonical_request() -> HarmonizeProteinInferenceSupportRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def result(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> ProteinInferenceHarmonizationResult:
    return harmonize_protein_inference_support(canonical_request)


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value.model_dump(mode="python"))  # type: ignore[attr-defined]


def _receipt(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    **updates: object,
) -> ProteinInferenceArtifactHarmonizationReceipt:
    payload = canonical_request.artifact_receipt.model_dump(
        mode="python", exclude={"receipt_digest"}
    )
    payload.update(updates)
    payload["receipt_digest"] = artifact_receipt_digest(payload)
    return ProteinInferenceArtifactHarmonizationReceipt.model_validate(payload, strict=True)


def _ledger(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    **updates: object,
) -> ProteinInferenceSupportLedger:
    source = canonical_request.support_ledger
    assert source is not None
    payload = source.model_dump(mode="python", exclude={"ledger_digest"})
    payload.update(updates)
    payload["ledger_digest"] = support_ledger_digest(payload)
    return ProteinInferenceSupportLedger.model_validate(payload, strict=True)


def _manifest(
    result: ProteinInferenceHarmonizationResult,
    **updates: object,
) -> ProteinInferenceTransformationManifest:
    source = result.transformation_manifest
    assert source is not None
    payload = source.model_dump(mode="python", exclude={"manifest_digest"})
    payload.update(updates)
    payload["manifest_digest"] = transformation_manifest_digest(payload)
    return ProteinInferenceTransformationManifest.model_validate(payload, strict=True)


def _analysis(
    result: ProteinInferenceHarmonizationResult,
    **updates: object,
) -> ProteinInferenceHarmonizedAnalysis:
    source = result.analysis
    assert source is not None
    payload = source.model_dump(mode="python", exclude={"analysis_digest"})
    payload.update(updates)
    payload["analysis_digest"] = analysis_digest(payload)
    return ProteinInferenceHarmonizedAnalysis.model_validate(payload, strict=True)


def _validate_forged_result(
    result: ProteinInferenceHarmonizationResult,
    field: str,
    value: object,
) -> None:
    payload = _payload(result)
    payload[field] = value
    if field != "result_digest":
        payload["result_digest"] = result_payload_digest(payload)
    ProteinInferenceHarmonizationResult.model_validate(payload, strict=True)


def test_reviewer_and_all_graph_identifiers_are_opaque(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    assert canonical_request.policy.reviewed_by.startswith("reviewer.")
    assert len(canonical_request.policy.reviewed_by) == len("reviewer.") + 64
    with pytest.raises(ValidationError, match="reviewer identifier"):
        type(canonical_request.policy).model_validate(
            canonical_request.policy.model_copy(update={"reviewed_by": "MPEPTIDEK"}),
            strict=True,
        )


def test_unit_receipt_action_must_match_posterior(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    unit = canonical_request.artifact_receipt.units[0]
    with pytest.raises(ValidationError, match="action contradicts"):
        ProteinInferenceArtifactUnitReceipt.model_validate(
            unit.model_copy(update={"action": ProteinInferenceArtifactAction.REVIEW}),
            strict=True,
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"artifact_disposition": ProteinInferenceArtifactDisposition.QUARANTINED},
            "unit posteriors",
        ),
        (
            {
                "evaluation_state": ProteinInferenceArtifactEvaluationState.NOT_EVALUABLE,
                "artifact_disposition": ProteinInferenceArtifactDisposition.ABSTAINED,
                "artifact_support_status": SupportStatus.UNSUPPORTED,
                "artifact_human_review_required": True,
            },
            "cannot project successful units",
        ),
        (
            {
                "evaluation_state": ProteinInferenceArtifactEvaluationState.NOT_EVALUABLE,
                "unit_count": 0,
                "units": (),
                "artifact_evidence_ledger_digest": None,
                "artifact_profile_digest": None,
                "applicability": None,
            },
            "must carry a complete screen",
        ),
        ({"artifact_support_status": SupportStatus.UNSUPPORTED}, "support status contradict"),
        ({"artifact_human_review_required": True}, "review requirement contradict"),
    ],
)
def test_receipt_envelope_contradictions_are_rejected(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _receipt(canonical_request, **updates)


def test_receipt_duplicate_missing_graph_and_wrong_abi_are_rejected(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    receipt = canonical_request.artifact_receipt
    duplicate_units = (receipt.units[0], receipt.units[0], *receipt.units[2:])
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        _receipt(
            canonical_request,
            units=duplicate_units,
            unit_binding_digest=unit_binding_digest(duplicate_units),
        )
    with pytest.raises(ValidationError, match="exact screened unit graph"):
        _receipt(canonical_request, units=(), unit_binding_digest=unit_binding_digest(()))
    wrong_reference = receipt.artifact_reference.model_copy(
        update={"media_type": "application/json"}
    )
    with pytest.raises(ValidationError, match="exact M03-05 result ABI"):
        _receipt(canonical_request, artifact_reference=wrong_reference)


def test_censored_observation_requires_only_its_upper_bound(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    observation = ledger.observations[0]
    with pytest.raises(ValidationError, match="censored support"):
        type(observation).model_validate(
            observation.model_copy(
                update={
                    "state": ProteinInferenceSupportObservationState.CENSORED,
                    "support_coordinate_ppm": None,
                    "censoring_upper_bound_ppm": None,
                }
            ),
            strict=True,
        )


def test_ledger_duplicate_and_projection_closures_are_rejected(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    duplicate_observations = (
        ledger.observations[0],
        ledger.observations[0],
        *ledger.observations[2:],
    )
    with pytest.raises(ValidationError, match="observation unit identifiers must be unique"):
        _ledger(canonical_request, observations=duplicate_observations)
    duplicate_invariant = ledger.invariants[1].model_copy(
        update={"invariant_id": ledger.invariants[0].invariant_id}
    )
    with pytest.raises(ValidationError, match="invariant identifiers must be unique"):
        _ledger(
            canonical_request,
            invariants=(ledger.invariants[0], duplicate_invariant, ledger.invariants[2]),
        )
    with pytest.raises(ValidationError, match="unit binding does not match"):
        _ledger(canonical_request, artifact_unit_binding_digest=M0306_ZERO_DIGEST)


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        (ProteinInferenceSupportInvariantKind.SUPPORT_DIRECTION, "matched anchors"),
        (ProteinInferenceSupportInvariantKind.SUPPORT_RANK, "distinct anchors"),
        (ProteinInferenceSupportInvariantKind.AMBIGUITY_FRACTION, "matched ambiguity"),
    ],
)
def test_invariant_semantic_member_shapes_are_rejected(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    kind: ProteinInferenceSupportInvariantKind,
    message: str,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    target = next(item for item in ledger.invariants if item.kind is kind)
    used = {*target.left_unit_ids, *target.right_unit_ids}
    replacement = next(item.unit_id for item in ledger.observations if item.unit_id not in used)
    forged = target.model_copy(update={"right_unit_ids": (replacement,)})
    invariants = tuple(forged if item.kind is kind else item for item in ledger.invariants)
    with pytest.raises(ValidationError, match=message):
        _ledger(canonical_request, invariants=invariants)


def test_profile_exact_ordinals_and_stage_identity_are_closed(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    profile = canonical_request.policy.profiles[0]
    bad_ordinal = profile.stages[0].model_copy(update={"ordinal": 2})
    with pytest.raises(ValidationError, match="exact ordered ordinals"):
        ProteinInferenceHarmonizationProfile.model_validate(
            profile.model_copy(update={"stages": (bad_ordinal, *profile.stages[1:])}),
            strict=True,
        )
    duplicate_id = profile.stages[1].model_copy(update={"stage_id": profile.stages[0].stage_id})
    with pytest.raises(ValidationError, match="stage identifiers must be unique"):
        ProteinInferenceHarmonizationProfile.model_validate(
            profile.model_copy(
                update={"stages": (profile.stages[0], duplicate_id, *profile.stages[2:])}
            ),
            strict=True,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("future", "cannot postdate"),
        ("identity", "identity control"),
        ("quality", "quality control"),
        ("configuration", "approved configuration"),
        ("presence", "presence contradicts"),
        ("ledger_time", "support facts must follow"),
        ("invariant_cap", "invariant ceiling"),
        ("unknown_anchor", "unknown anchor"),
        ("invalid_levels", "invalid factor-level domain"),
        ("artifact_conflict", "conflicting content"),
    ],
)
def test_request_relational_authorization_matrix(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
    mutation: str,
    message: str,
) -> None:
    payload = _payload(canonical_request)
    if mutation == "future":
        payload["policy"]["reviewed_at"] = canonical_request.context.occurred_at + timedelta(
            microseconds=1
        )
    elif mutation == "identity":
        payload["context"]["references"]["identity_lineage"]["binding_digest"] = M0306_ZERO_DIGEST
    elif mutation == "quality":
        payload["context"]["references"]["quality"]["evidence"]["digest"] = M0306_ZERO_DIGEST
    elif mutation == "configuration":
        payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            M0306_ZERO_DIGEST
        )
    elif mutation == "presence":
        payload["support_ledger"] = None
    elif mutation == "ledger_time":
        payload["support_ledger"]["recorded_at"] = (
            canonical_request.artifact_receipt.artifact_completed_at - (timedelta(microseconds=1))
        )
        payload["support_ledger"]["ledger_digest"] = support_ledger_digest(
            {
                key: value
                for key, value in payload["support_ledger"].items()
                if key != "ledger_digest"
            }
        )
    elif mutation == "invariant_cap":
        payload["policy"]["max_invariants"] = 3
        extra = deepcopy(payload["support_ledger"]["invariants"][0])
        extra["invariant_id"] = opaque_harmonization_identifier("invariant", "fourth")
        payload["support_ledger"]["invariants"] = (
            *payload["support_ledger"]["invariants"],
            extra,
        )
        payload["support_ledger"]["ledger_digest"] = support_ledger_digest(
            {
                key: value
                for key, value in payload["support_ledger"].items()
                if key != "ledger_digest"
            }
        )
        payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            configuration_digest(payload["policy"])
        )
    elif mutation == "unknown_anchor":
        payload["policy"]["profiles"][0]["stages"][0]["estimation_anchor_ids"] = (
            "anchor." + ("f" * 64),
        )
        payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            configuration_digest(payload["policy"])
        )
    elif mutation == "invalid_levels":
        payload["policy"]["profiles"][0]["stages"][0]["reference_level_id"] = "level." + ("f" * 64)
        payload["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
            configuration_digest(payload["policy"])
        )
    else:
        evidence = payload["support_ledger"]["evidence"]
        evidence["artifact_id"] = payload["policy"]["evidence"]["artifact_id"]
        evidence["version"] = payload["policy"]["evidence"]["version"]
        evidence["digest"] = M0306_ZERO_DIGEST
        payload["support_ledger"]["ledger_digest"] = support_ledger_digest(
            {
                key: value
                for key, value in payload["support_ledger"].items()
                if key != "ledger_digest"
            }
        )
    with pytest.raises(ValidationError, match=message):
        HarmonizeProteinInferenceSupportRequest.model_validate(payload, strict=True)


def test_preflight_denies_hostile_and_partial_contexts_without_raising() -> None:
    class Hostile(dict[str, object]):
        def get(self, key: str, _default: object = None) -> object:
            raise RuntimeError(key)

    assert preflight_authorized({}) is False
    assert preflight_authorized(Hostile()) is False


def test_level_shift_requires_complete_numeric_tuple(
    result: ProteinInferenceHarmonizationResult,
) -> None:
    manifest = result.transformation_manifest
    assert manifest is not None
    shift = next(
        item
        for stage in manifest.stages
        for item in stage.level_shifts
        if item.state is not ProteinInferenceSupportShiftState.NOT_EVALUABLE
    )
    with pytest.raises(ValidationError, match="requires estimates"):
        ProteinInferenceSupportLevelShift.model_validate(
            shift.model_copy(update={"post_validation_residual_ppm": None}),
            strict=True,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("collections", "identifier collections"),
        ("level_ids", "level identifiers"),
        ("reference", "exactly one reference"),
        ("not_eval_pairs", "below an exact control-pair"),
        ("eval_pairs", "meet both control-pair"),
        ("capped", "apply the exact signed cap"),
        ("reference_nonzero", "reference-level shift must be exact zero"),
    ],
)
def test_stage_transformation_relational_matrix(
    result: ProteinInferenceHarmonizationResult,
    mutation: str,
    message: str,
) -> None:
    manifest = result.transformation_manifest
    assert manifest is not None
    stage = manifest.stages[0]
    shifts = list(stage.level_shifts)
    if mutation == "collections":
        candidate = stage.model_copy(update={"validation_anchor_ids": stage.estimation_anchor_ids})
    elif mutation == "level_ids":
        shifts[1] = shifts[1].model_copy(update={"level_id": shifts[0].level_id})
        candidate = stage.model_copy(update={"level_shifts": tuple(shifts)})
    elif mutation == "reference":
        candidate = stage.model_copy(
            update={"reference_level_id": opaque_harmonization_identifier("level", "absent")}
        )
    elif mutation == "not_eval_pairs":
        shifts[0] = shifts[0].model_copy(
            update={
                "state": ProteinInferenceSupportShiftState.NOT_EVALUABLE,
                "estimated_shift_ppm": None,
                "applied_shift_ppm": None,
                "pre_validation_residual_ppm": None,
                "post_validation_residual_ppm": None,
                "estimation_pair_count": stage.minimum_estimation_pairs,
                "validation_pair_count": stage.minimum_validation_pairs,
            }
        )
        candidate = stage.model_copy(update={"level_shifts": tuple(shifts)})
    elif mutation == "eval_pairs":
        target = next(
            index
            for index, item in enumerate(shifts)
            if item.state is not ProteinInferenceSupportShiftState.NOT_EVALUABLE
        )
        shifts[target] = shifts[target].model_copy(update={"estimation_pair_count": 0})
        candidate = stage.model_copy(update={"level_shifts": tuple(shifts)})
    elif mutation == "capped":
        target = next(
            index for index, item in enumerate(shifts) if item.level_id != stage.reference_level_id
        )
        shift = shifts[target]
        shifts[target] = shift.model_copy(
            update={
                "state": ProteinInferenceSupportShiftState.CAPPED,
                "estimated_shift_ppm": 1,
                "applied_shift_ppm": 1,
            }
        )
        candidate = stage.model_copy(update={"level_shifts": tuple(shifts)})
    else:
        target = next(
            index for index, item in enumerate(shifts) if item.level_id == stage.reference_level_id
        )
        shifts[target] = shifts[target].model_copy(
            update={
                "state": ProteinInferenceSupportShiftState.ESTIMATED,
                "estimated_shift_ppm": 1,
                "applied_shift_ppm": 1,
                "pre_validation_residual_ppm": 0,
                "post_validation_residual_ppm": 0,
            }
        )
        candidate = stage.model_copy(update={"level_shifts": tuple(shifts)})
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceStageTransformation.model_validate(candidate, strict=True)


def test_manifest_requires_exact_stage_permutation_and_digest(
    result: ProteinInferenceHarmonizationResult,
) -> None:
    manifest = result.transformation_manifest
    assert manifest is not None
    duplicate = manifest.stages[1].model_copy(update={"stage_id": manifest.stages[0].stage_id})
    with pytest.raises(ValidationError, match="identifiers must be unique"):
        _manifest(result, stages=(manifest.stages[0], duplicate, *manifest.stages[2:]))
    wrong_factor = manifest.stages[1].model_copy(update={"factor": manifest.stages[0].factor})
    with pytest.raises(ValidationError, match="all eight factors"):
        _manifest(result, stages=(manifest.stages[0], wrong_factor, *manifest.stages[2:]))
    with pytest.raises(ValidationError, match="digest does not match"):
        ProteinInferenceTransformationManifest.model_validate(
            manifest.model_copy(update={"manifest_digest": M0306_ZERO_DIGEST}),
            strict=True,
        )


def test_diagnostic_joint_presence_and_each_exact_status_branch(
    result: ProteinInferenceHarmonizationResult,
) -> None:
    technical = result.technical_effect_diagnostics[0]
    invariant = result.invariant_diagnostics[0]
    with pytest.raises(ValidationError, match="jointly present"):
        ProteinInferenceTechnicalEffectDiagnostic.model_validate(
            technical.model_copy(update={"after_residual_ppm": None}), strict=True
        )
    not_evaluable = ProteinInferenceTechnicalEffectDiagnostic.model_validate(
        technical.model_copy(
            update={
                "before_residual_ppm": None,
                "after_residual_ppm": None,
                "status": ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE,
            }
        ),
        strict=True,
    )
    assert not_evaluable.status is ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
    with pytest.raises(ValidationError, match="jointly present"):
        ProteinInferenceInvariantDiagnostic.model_validate(
            invariant.model_copy(update={"after_score_ppm": None}), strict=True
        )
    not_evaluable_invariant = ProteinInferenceInvariantDiagnostic.model_validate(
        invariant.model_copy(
            update={
                "before_score_ppm": None,
                "after_score_ppm": None,
                "status": ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE,
            }
        ),
        strict=True,
    )
    assert (
        not_evaluable_invariant.status
        is ProteinInferenceHarmonizationDiagnosticStatus.NOT_EVALUABLE
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_adjustment", "unique by ordinal"),
        ("relabel", "cannot relabel"),
        ("traversable_missing", "requires its exact input"),
        ("wrong_replay", "exact applied adjustments"),
        ("held_output", "cannot carry a harmonized value"),
        ("held_observed", "held observed support"),
        ("censored", "censored support output"),
        ("missing_numeric", "cannot manufacture"),
    ],
)
def test_harmonized_value_shape_matrix(
    result: ProteinInferenceHarmonizationResult,
    mutation: str,
    message: str,
) -> None:
    analysis = result.analysis
    assert analysis is not None
    value = next(item for item in analysis.values if item.adjustments)
    updates: dict[str, object]
    if mutation == "duplicate_adjustment":
        updates = {"adjustments": (value.adjustments[0], value.adjustments[0])}
    elif mutation == "relabel":
        updates = {"output_state": ProteinInferenceSupportObservationState.MISSING}
    elif mutation == "traversable_missing":
        updates = {"harmonized_support_coordinate_ppm": None}
    elif mutation == "wrong_replay":
        current = value.harmonized_support_coordinate_ppm
        assert current is not None
        updates = {"harmonized_support_coordinate_ppm": current + 1}
    elif mutation == "held_output":
        updates = {"artifact_action": ProteinInferenceArtifactAction.REVIEW}
    elif mutation == "held_observed":
        updates = {
            "artifact_action": ProteinInferenceArtifactAction.REVIEW,
            "harmonized_support_coordinate_ppm": None,
            "adjustments": (),
            "input_support_coordinate_ppm": None,
        }
    elif mutation == "censored":
        updates = {
            "artifact_action": ProteinInferenceArtifactAction.REVIEW,
            "input_state": ProteinInferenceSupportObservationState.CENSORED,
            "output_state": ProteinInferenceSupportObservationState.CENSORED,
            "harmonized_support_coordinate_ppm": None,
            "adjustments": (),
            "input_support_coordinate_ppm": None,
            "censoring_upper_bound_ppm": None,
        }
    else:
        updates = {
            "artifact_action": ProteinInferenceArtifactAction.REVIEW,
            "input_state": ProteinInferenceSupportObservationState.MISSING,
            "output_state": ProteinInferenceSupportObservationState.MISSING,
            "harmonized_support_coordinate_ppm": None,
            "adjustments": (),
            "input_support_coordinate_ppm": 1,
        }
    with pytest.raises(ValidationError, match=message):
        ProteinInferenceHarmonizedSupportValue.model_validate(
            value.model_copy(update=updates), strict=True
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicates", "partitions require unique"),
        ("overlap", "partitions must be disjoint"),
        ("coverage", "exactly cover"),
        ("action", "contradicts a unit action"),
        ("digest", "digest does not match"),
    ],
)
def test_analysis_partition_and_digest_forgery_matrix(
    result: ProteinInferenceHarmonizationResult,
    mutation: str,
    message: str,
) -> None:
    analysis = result.analysis
    assert analysis is not None
    retained = analysis.retain_unit_ids
    if mutation == "duplicates":
        updates: dict[str, object] = {"retain_unit_ids": (*retained, retained[0])}
    elif mutation == "overlap":
        updates = {"review_unit_ids": (retained[0],)}
    elif mutation == "coverage":
        updates = {"retain_unit_ids": retained[1:]}
    elif mutation == "action":
        forged = analysis.values[0].model_copy(
            update={
                "artifact_action": ProteinInferenceArtifactAction.REVIEW,
                "harmonized_support_coordinate_ppm": None,
                "adjustments": (),
                "was_clipped": False,
            }
        )
        updates = {"values": (forged, *analysis.values[1:])}
    else:
        with pytest.raises(ValidationError, match=message):
            ProteinInferenceHarmonizedAnalysis.model_validate(
                analysis.model_copy(update={"analysis_digest": M0306_ZERO_DIGEST}), strict=True
            )
        return
    with pytest.raises(ValidationError, match=message):
        _analysis(result, **updates)


def test_finding_reference_duplicates_are_rejected() -> None:
    unit_id = opaque_harmonization_identifier("unit", "finding-unit")
    finding = finding_for(
        ProteinInferenceHarmonizationFindingCode.ARTIFACT_REVIEW_REQUIRED,
        unit_ids=(unit_id,),
    )
    with pytest.raises(ValidationError, match="references must be unique"):
        ProteinInferenceHarmonizationFinding.model_validate(
            finding.model_copy(update={"unit_ids": (unit_id, unit_id)}), strict=True
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("technical_effect_diagnostics", "technical diagnostics do not replay"),
        ("invariant_diagnostics", "invariant diagnostics do not replay"),
        ("findings", "findings do not replay"),
        ("result_id", "output envelope"),
        ("support", "support is not deterministic"),
        ("uncertainty", "uncertainty is not deterministic"),
        ("provenance", "provenance does not close"),
        ("evidence", "evidence index does not close"),
        ("limitations", "limitations do not close"),
        ("human_review_required", "human-review flag"),
        ("completed_at", "completion time"),
        ("result_digest", "result digest"),
    ],
)
def test_resigned_result_envelope_forgery_matrix(
    result: ProteinInferenceHarmonizationResult,
    field: str,
    message: str,
) -> None:
    payload = _payload(result)
    if field in {"technical_effect_diagnostics", "invariant_diagnostics", "evidence"}:
        value: object = tuple(payload[field][1:])
    elif field == "findings":
        value = (
            finding_for(
                ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED
            ).model_dump(mode="python"),
        )
    elif field == "limitations":
        value = tuple(
            {**item, "statement": "forged limitation"} if index == 0 else item
            for index, item in enumerate(payload[field])
        )
    elif field == "result_id":
        value = "result.m0306." + ("f" * 64)
    elif field == "support":
        value = {**payload[field], "status": SupportStatus.UNSUPPORTED}
    elif field == "uncertainty":
        value = {
            **payload[field],
            "measurement": {**payload[field]["measurement"], "rationale": "forged"},
        }
    elif field == "provenance":
        value = {**payload[field], "input_digests": (M0306_ZERO_DIGEST,)}
    elif field == "human_review_required":
        value = True
    elif field == "completed_at":
        value = result.completed_at + timedelta(microseconds=1)
    else:
        value = M0306_ZERO_DIGEST
    with pytest.raises(ValidationError, match=message):
        _validate_forged_result(result, field, value)


def test_supersession_is_explicitly_bound_in_receipt_and_provenance(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    superseded = sha256_digest("prior-m0306-result")
    candidate = HarmonizeProteinInferenceSupportRequest.model_validate(
        canonical_request.model_copy(update={"supersedes_result_digest": superseded}), strict=True
    )
    output = harmonize_protein_inference_support(candidate)
    assert output.receipt.supersedes_result_digest == superseded
    assert superseded in output.provenance.input_digests
    assert output.request_digest != canonical_request_digest(canonical_request)


def test_expected_finding_and_disposition_precedence_branches(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    rejected = finding_for(ProteinInferenceHarmonizationFindingCode.UPSTREAM_REJECTED)
    quarantined = finding_for(
        ProteinInferenceHarmonizationFindingCode.SUPPORT_LEDGER_BINDING_MISMATCH
    )
    abstained = finding_for(ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED)
    assert expected_disposition(canonical_request, (abstained, quarantined, rejected)) is (
        ProteinInferenceHarmonizationDisposition.REJECTED
    )
    assert expected_disposition(canonical_request, (abstained, quarantined)) is (
        ProteinInferenceHarmonizationDisposition.QUARANTINED
    )
    assert expected_disposition(canonical_request, (abstained,)) is (
        ProteinInferenceHarmonizationDisposition.ABSTAINED
    )


def test_helper_fallbacks_are_typed_and_binding_sensitive(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    ledger = canonical_request.support_ledger
    assert ledger is not None
    assert matching_harmonization_profile(canonical_request) is not None
    assert harmonization_ledger_bindings_close(canonical_request)
    no_ledger = canonical_request.model_copy(update={"support_ledger": None})
    findings = expected_harmonization_findings(no_ledger)
    assert tuple(item.code for item in findings) == (
        ProteinInferenceHarmonizationFindingCode.UPSTREAM_SHAPE_UNSUPPORTED,
    )
    forged = canonical_request.model_copy(
        update={
            "support_ledger": ledger.model_copy(
                update={"artifact_result_digest": M0306_ZERO_DIGEST}
            )
        }
    )
    assert not harmonization_ledger_bindings_close(forged)


def test_exact_capacity_512_executes_within_both_canonical_caps() -> None:
    canonical_request = build_capacity_scenario_request()
    assert canonical_request.support_ledger is not None
    assert len(canonical_request.support_ledger.observations) == M0306_MAX_UNITS
    assert len(canonical_json_bytes(canonical_request)) <= M0306_MAX_CANONICAL_REQUEST_BYTES
    result = harmonize_protein_inference_support(canonical_request)
    assert result.analysis is not None
    assert len(result.analysis.values) == M0306_MAX_UNITS
    assert result.disposition is ProteinInferenceHarmonizationDisposition.ACCEPTED
    assert (
        ProteinInferenceHarmonizationResult.model_validate_json(
            canonical_json_bytes(result), strict=True
        )
        == result
    )


def test_semantic_reorder_reconstructs_full_result_equality(
    result: ProteinInferenceHarmonizationResult,
) -> None:
    payload = _payload(result)
    payload["request"]["artifact_receipt"]["units"] = tuple(
        reversed(payload["request"]["artifact_receipt"]["units"])
    )
    payload["request"]["support_ledger"]["observations"] = tuple(
        reversed(payload["request"]["support_ledger"]["observations"])
    )
    payload["request"]["support_ledger"]["invariants"] = tuple(
        reversed(payload["request"]["support_ledger"]["invariants"])
    )
    payload["request"]["policy"]["profiles"][0]["stages"] = tuple(
        reversed(payload["request"]["policy"]["profiles"][0]["stages"])
    )
    payload["findings"] = tuple(reversed(payload["findings"]))
    payload["evidence"] = tuple(reversed(payload["evidence"]))
    payload["provenance"]["input_digests"] = tuple(reversed(payload["provenance"]["input_digests"]))
    payload["result_digest"] = result_payload_digest(payload)
    reconstructed = ProteinInferenceHarmonizationResult.model_validate(payload, strict=True)
    assert reconstructed == result
    assert normalized_result(reconstructed) == normalized_result(result)


def test_public_builder_request_is_strict_and_not_a_probability_contract(
    canonical_request: HarmonizeProteinInferenceSupportRequest,
) -> None:
    encoded = canonical_json_bytes(canonical_request)
    assert len(encoded) <= M0306_MAX_CANONICAL_REQUEST_BYTES
    assert b'"is_calibrated_probability":false' in encoded
    assert (
        HarmonizeProteinInferenceSupportRequest.model_validate_json(encoded, strict=True)
        == canonical_request
    )
