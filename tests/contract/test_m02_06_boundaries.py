"""Relational and replay-boundary checks for M02-06 issued results."""

from __future__ import annotations

from copy import deepcopy
from functools import cache
from typing import TYPE_CHECKING, Any

import pytest
from evals.m02_06.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m02_06 import (
    BiologicalInvariantDiagnostic,
    BiologicalInvariantKind,
    DiagnosticStatus,
    HarmonizationDisposition,
    HarmonizationValueState,
    HarmonizedIdentificationValue,
    IdentificationHarmonizationResult,
    IdentificationLevelShift,
    IdentificationStageTransformation,
    IdentificationTechnicalFactor,
    IdentificationTransformationManifest,
    ShiftState,
    SourceObservationSummary,
    TechnicalEffectDiagnostic,
    UpstreamHarmonizationReceipt,
    invariant_digest,
    observation_summary_digest,
    request_manifest_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c02_identification_qc.m02_06_harmonization import (
    harmonize_identification_evidence,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.contract

_SENTINEL_DIGEST = "sha256:" + ("0" * 64)


@cache
def _base_result_payload(case: str) -> dict[str, Any]:
    return harmonize_identification_evidence(build_scenario_request(case)).model_dump(mode="python")


def _result_payload(case: str = "conformant_eight_factor") -> dict[str, Any]:
    values = deepcopy(_base_result_payload(case))
    values["result_digest"] = _SENTINEL_DIGEST
    return values


def _set(mapping: dict[str, Any], key: str, value: object) -> object:
    mapping[key] = value
    return value


def _clear_review_requirement(values: dict[str, Any]) -> None:
    values["human_review_required"] = False


def _validate_result(values: dict[str, Any]) -> IdentificationHarmonizationResult:
    return IdentificationHarmonizationResult.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda item: _set(item, "state", HarmonizationValueState.EXCLUDED),
            "cannot claim a derived exclusion",
        ),
        (
            lambda item: _set(item, "value", None),
            "invalid numeric state",
        ),
        (
            lambda item: _set(item, "censoring_limit", 1.0),
            "invalid numeric state",
        ),
        (
            lambda item: _set(
                item,
                "factor_levels",
                (*item["factor_levels"][:-1], item["factor_levels"][0]),
            ),
            "all factor levels",
        ),
        (
            lambda item: _set(
                item,
                "evidence_digests",
                (*item["evidence_digests"], item["evidence_digests"][0]),
            ),
            "must be unique",
        ),
    ],
)
def test_source_summary_state_and_collection_closure(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    summary = _result_payload()["values"][0]["source_observation"]
    mutate(summary)

    with pytest.raises(ValidationError, match=message):
        SourceObservationSummary.model_validate(summary, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda item: _set(item, "sample_id", "sample.contradiction"),
            "contradicts its source summary",
        ),
        (
            lambda item: _set(item, "source_observation_digest", _SENTINEL_DIGEST),
            "digest contradicts",
        ),
        (
            lambda item: _set(
                item,
                "applied_adjustments",
                tuple(reversed(item["applied_adjustments"])),
            ),
            "stage ordered",
        ),
        (
            lambda item: _set(item["applied_adjustments"][0], "unit", "different_unit"),
            "log2_abundance",
        ),
        (
            lambda item: _set(item, "harmonized_value", item["harmonized_value"] + 1.0),
            "contradicts its applied adjustments",
        ),
    ],
)
def test_value_is_exact_arithmetic_over_its_source_and_adjustments(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    value = _result_payload()["values"][0]
    mutate(value)

    with pytest.raises(ValidationError, match=message):
        HarmonizedIdentificationValue.model_validate(value, strict=True)


@pytest.mark.parametrize(
    ("case", "state", "message"),
    [
        ("typed_nonobserved_states", HarmonizationValueState.MISSING, "cannot be imputed"),
        ("typed_nonobserved_states", HarmonizationValueState.CENSORED, "cannot be imputed"),
        ("upstream_excluded_target", HarmonizationValueState.EXCLUDED, "repaired value"),
    ],
)
def test_nonobserved_and_excluded_values_cannot_be_repaired(
    case: str,
    state: HarmonizationValueState,
    message: str,
) -> None:
    values = _result_payload(case)
    value = next(item for item in values["values"] if item["output_state"] is state)
    value["harmonized_value"] = 1.0

    with pytest.raises(ValidationError, match=message):
        HarmonizedIdentificationValue.model_validate(value, strict=True)


def test_censoring_limit_is_preserved_exactly() -> None:
    value = next(
        item
        for item in _result_payload("typed_nonobserved_states")["values"]
        if item["output_state"] is HarmonizationValueState.CENSORED
    )
    value["censoring_limit"] += 1.0

    with pytest.raises(ValidationError, match="preserve the censoring limit"):
        HarmonizedIdentificationValue.model_validate(value, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda shift: (
                _set(shift, "state", ShiftState.NOT_EVALUABLE),
                _set(shift, "estimated_shift", 0.1),
                _set(shift, "applied_shift", None),
            ),
            "not-evaluable shift cannot carry",
        ),
        (
            lambda shift: _set(shift, "applied_shift", None),
            "requires estimate and applied",
        ),
        (
            lambda shift: _set(shift, "applied_shift", shift["applied_shift"] + 0.1),
            "must apply its exact estimate",
        ),
    ],
)
def test_level_shift_numeric_state_is_typed(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    shift = _result_payload()["transformation_manifest"]["stages"][0]["level_shifts"][0]
    mutate(shift)

    with pytest.raises(ValidationError, match=message):
        IdentificationLevelShift.model_validate(shift, strict=True)


@pytest.mark.parametrize(
    ("case", "mutate", "message"),
    [
        (
            "conformant_eight_factor",
            lambda stage: (
                _set(stage["level_shifts"][0], "estimated_shift", 1.0),
                _set(stage["level_shifts"][0], "applied_shift", 1.0),
            ),
            "strictly within the cap",
        ),
        (
            "capped_shift",
            lambda stage: _set(
                next(item for item in stage["level_shifts"] if item["state"] is ShiftState.CAPPED),
                "applied_shift",
                0.0,
            ),
            "declared bound exactly",
        ),
        (
            "conformant_eight_factor",
            lambda stage: _set(
                next(
                    item
                    for item in stage["level_shifts"]
                    if item["level_id"] == stage["reference_level_id"]
                ),
                "applied_shift",
                0.1,
            ),
            "exact estimate|reference-level shift",
        ),
        (
            "conformant_eight_factor",
            lambda stage: _set(
                stage,
                "level_shifts",
                (*stage["level_shifts"], stage["level_shifts"][0]),
            ),
            "levels must be unique",
        ),
        (
            "conformant_eight_factor",
            lambda stage: _set(
                stage,
                "control_target_ids",
                (*stage["control_target_ids"], stage["control_target_ids"][0]),
            ),
            "controls must be unique",
        ),
    ],
)
def test_stage_transformation_closes_reference_cap_and_collections(
    case: str,
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    stages = _result_payload(case)["transformation_manifest"]["stages"]
    stage = next(
        (
            item
            for item in stages
            if any(shift["state"] is ShiftState.CAPPED for shift in item["level_shifts"])
        ),
        stages[0],
    )
    mutate(stage)

    with pytest.raises(ValidationError, match=message):
        IdentificationStageTransformation.model_validate(stage, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda stages: _set(stages[0], "ordinal", 2), "must remain ordered"),
        (
            lambda stages: _set(stages[1], "stage_id", stages[0]["stage_id"]),
            "identifiers must be unique",
        ),
        (
            lambda stages: _set(stages[1], "factor", stages[0]["factor"]),
            "all eight technical factors",
        ),
    ],
)
def test_manifest_is_the_exact_ordered_factor_set(
    mutate: Callable[[tuple[dict[str, Any], ...]], object],
    message: str,
) -> None:
    manifest = _result_payload()["transformation_manifest"]
    mutate(manifest["stages"])

    with pytest.raises(ValidationError, match=message):
        IdentificationTransformationManifest.model_validate(manifest, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda item: _set(item, "status", DiagnosticStatus.FAILED),
            "scores contradict their status",
        ),
        (
            lambda item: _set(item, "after_spread", None),
            "scores contradict their status",
        ),
    ],
)
def test_technical_diagnostic_status_derives_from_scores(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    diagnostic = _result_payload()["technical_effect_diagnostics"][0]
    mutate(diagnostic)

    with pytest.raises(ValidationError, match=message):
        TechnicalEffectDiagnostic.model_validate(diagnostic, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda item: _set(item, "status", DiagnosticStatus.FAILED),
            "scores contradict their status",
        ),
        (
            lambda item: _set(item, "after_score", -item["after_score"]),
            "scores contradict their status",
        ),
    ],
)
def test_biological_diagnostic_status_derives_from_scores(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    diagnostic = _result_payload()["biological_invariant_diagnostics"][0]
    mutate(diagnostic)

    with pytest.raises(ValidationError, match=message):
        BiologicalInvariantDiagnostic.model_validate(diagnostic, strict=True)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value, "profile_digest", _SENTINEL_DIGEST),
            "profile digest is inconsistent",
        ),
        (
            lambda value: _set(value, "policy_digest", _SENTINEL_DIGEST),
            "policy digest is inconsistent",
        ),
        (
            lambda value: _set(value, "configuration_digest", _SENTINEL_DIGEST),
            "configuration digest is inconsistent",
        ),
        (
            lambda value: _set(
                value["transformation_manifest"],
                "configuration_digest",
                _SENTINEL_DIGEST,
            ),
            "different configuration",
        ),
        (
            lambda value: _set(value, "prerequisites_digest", _SENTINEL_DIGEST),
            "receipt digest is inconsistent",
        ),
        (
            lambda value: _set(value, "request_digest", _SENTINEL_DIGEST),
            "request digest is inconsistent",
        ),
        (
            lambda value: _set(
                value["upstream_receipts"][1],
                "module_id",
                value["upstream_receipts"][0]["module_id"],
            ),
            "one receipt for each",
        ),
    ],
)
def test_result_digest_manifests_and_prerequisite_set_are_closed(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        _validate_result(values)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value["values"][0], "feature_id", value["values"][1]["feature_id"]),
            "source summary|unique by target and feature",
        ),
        (
            lambda value: _set(value["values"][0], "unit", "different_unit"),
            "log2_abundance",
        ),
        (
            lambda value: _set(value["values"][0], "harmonized_value", 999.0),
            "applied adjustments|deterministic stage replay",
        ),
        (
            lambda value: _set(value["values"][0], "source_observation_digest", _SENTINEL_DIGEST),
            "source observation digest",
        ),
        (
            lambda value: _set(
                value["transformation_manifest"]["stages"][0],
                "input_digest",
                _SENTINEL_DIGEST,
            ),
            "deterministic replay",
        ),
        (
            lambda value: _set(
                value["transformation_manifest"]["stages"][0]["level_shifts"][0],
                "control_count",
                value["transformation_manifest"]["stages"][0]["level_shifts"][0]["control_count"]
                + 1,
            ),
            "deterministic replay",
        ),
        (
            lambda value: _set(
                value["transformation_manifest"]["stages"][0]["level_shifts"][0],
                "unit",
                "different_unit",
            ),
            "log2_abundance",
        ),
    ],
)
def test_result_values_and_manifest_are_closed_under_deterministic_replay(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        _validate_result(values)


def test_exclusion_receipt_is_an_exact_firewall() -> None:
    values = _result_payload("upstream_excluded_target")
    receipt = next(
        item for item in values["upstream_receipts"] if item["module_id"] == "GLIO-PROTEOGEN-M02-05"
    )
    excluded = receipt["excluded_target_ids"][0]
    output = next(item for item in values["values"] if item["sample_id"] == excluded)
    output["output_state"] = HarmonizationValueState.OBSERVED
    output["harmonized_value"] = output["input_value"]

    with pytest.raises(ValidationError, match="M02-05 exclusion receipt"):
        _validate_result(values)


def test_excluded_targets_cannot_reenter_transformation_controls() -> None:
    values = _result_payload("upstream_excluded_target")
    receipt = next(
        item for item in values["upstream_receipts"] if item["module_id"] == "GLIO-PROTEOGEN-M02-05"
    )
    excluded = receipt["excluded_target_ids"][0]
    stage = values["transformation_manifest"]["stages"][0]
    stage["control_target_ids"] = (*stage["control_target_ids"], excluded)

    with pytest.raises(ValidationError, match="exclusion firewall"):
        _validate_result(values)


def test_all_result_targets_require_m0205_evaluation_receipts() -> None:
    values = _result_payload()
    receipt = next(
        item for item in values["upstream_receipts"] if item["module_id"] == "GLIO-PROTEOGEN-M02-05"
    )
    receipt["evaluated_target_ids"] = receipt["evaluated_target_ids"][1:]
    receipt_payload = [
        {
            "module_id": item["module_id"],
            "result_digest": item["result_digest"],
            "disposition": item["disposition"],
            **(
                {
                    "evaluated_target_ids": sorted(item["evaluated_target_ids"]),
                    "excluded_target_ids": sorted(item["excluded_target_ids"]),
                    "review_target_ids": sorted(item["review_target_ids"]),
                }
                if item["module_id"] == "GLIO-PROTEOGEN-M02-05"
                else {}
            ),
        }
        for item in sorted(values["upstream_receipts"], key=lambda item: item["module_id"])
    ]
    values["prerequisites_digest"] = sha256_digest(receipt_payload)
    values["request_digest"] = request_manifest_digest(
        active_context_digest=values["context_digest"],
        active_prerequisites_digest=values["prerequisites_digest"],
        active_profile_digest=values["profile_digest"],
        active_policy_digest=values["policy_digest"],
        observation_digests=tuple(item["source_observation_digest"] for item in values["values"]),
        invariant_digests=tuple(
            invariant_digest(item) for item in build_scenario_request().biological_controls
        ),
        supersedes_result_digest=values["supersedes_result_digest"],
    )

    with pytest.raises(ValidationError, match="every harmonized target must have"):
        _validate_result(values)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("factor", IdentificationTechnicalFactor.BATCH, "technical diagnostic contradicts"),
        ("tolerance", 0.5, "technical diagnostic contradicts"),
        ("capped", True, "scores contradict|technical diagnostic contradicts"),
        ("after_spread", 0.0000005, "technical diagnostic contradicts"),
    ],
)
def test_technical_diagnostics_bind_exact_stage_policy_and_replay(
    field: str,
    value: object,
    message: str,
) -> None:
    values = _result_payload()
    values["technical_effect_diagnostics"][0][field] = value

    with pytest.raises(ValidationError, match=message):
        _validate_result(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", BiologicalInvariantKind.RANK),
        ("tolerance", 0.5),
        ("after_score", 0.70),
    ],
)
def test_biological_diagnostics_bind_exact_control_policy_and_replay(
    field: str,
    value: object,
) -> None:
    values = _result_payload()
    values["biological_invariant_diagnostics"][0][field] = value

    with pytest.raises(
        ValidationError,
        match=r"scores contradict|biological diagnostic contradicts",
    ):
        _validate_result(values)


@pytest.mark.parametrize(
    ("case", "disposition"),
    [
        ("conformant_eight_factor", HarmonizationDisposition.QUARANTINED),
        ("insufficient_controls", HarmonizationDisposition.ACCEPTED),
        ("capped_shift", HarmonizationDisposition.ACCEPTED),
    ],
)
def test_disposition_derives_from_complete_diagnostic_statuses(
    case: str,
    disposition: HarmonizationDisposition,
) -> None:
    values = _result_payload(case)
    values["disposition"] = disposition

    with pytest.raises(ValidationError, match="disposition contradicts"):
        _validate_result(values)


@pytest.mark.parametrize(
    ("case", "mutate", "message"),
    [
        (
            "conformant_eight_factor",
            lambda value: _set(value["support"], "status", SupportStatus.UNSUPPORTED),
            "support contradicts",
        ),
        (
            "insufficient_controls",
            _clear_review_requirement,
            "support contradicts",
        ),
        (
            "capped_shift",
            lambda value: _set(value["support"], "reason_code", "wrong_reason"),
            "support contradicts",
        ),
    ],
)
def test_support_and_review_flag_derive_from_disposition(
    case: str,
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload(case)
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        _validate_result(values)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value["provenance"], "module_id", "GLIO-PROTEOGEN-M02-05"),
            "provenance is inconsistent",
        ),
        (
            lambda value: _set(value["provenance"], "activity_id", "activity.wrong"),
            "provenance is inconsistent",
        ),
        (
            lambda value: _set(value["provenance"], "input_digests", (value["request_digest"],)),
            "exact unique input digest set",
        ),
        (
            lambda value: _set(value["provenance"]["control_decisions"][0], "state", "rejected"),
            "control decisions are inconsistent",
        ),
        (
            lambda value: _set(
                next(
                    item
                    for item in value["provenance"]["control_decisions"]
                    if str(item["role"]) == "approved_configuration"
                ),
                "evidence_digest",
                _SENTINEL_DIGEST,
            ),
            "exact unique input digest set|configuration does not bind",
        ),
        (
            lambda value: _set(
                next(
                    item
                    for item in value["provenance"]["control_decisions"]
                    if str(item["role"]) == "identity_lineage"
                ),
                "subject_digest",
                _SENTINEL_DIGEST,
            ),
            "identity control does not bind",
        ),
        (
            lambda value: _set(value["provenance"], "consent_decision_id", "consent.wrong"),
            "consent provenance is inconsistent",
        ),
    ],
)
def test_provenance_is_complete_and_control_bound(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        _validate_result(values)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: _set(value, "evidence", (*value["evidence"], value["evidence"][0])),
            "evidence.*must be unique",
        ),
        (
            lambda value: _set(value, "evidence", value["evidence"][:-1]),
            "at least 8 items|evidence index is inconsistent",
        ),
        (
            lambda value: _set(value, "limitations", (value["limitations"][0],) * 2),
            "requires both fixed limitations",
        ),
    ],
)
def test_evidence_and_limitation_indexes_are_exact(
    mutate: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    values = _result_payload()
    mutate(values)

    with pytest.raises(ValidationError, match=message):
        _validate_result(values)


def test_non_sentinel_result_digest_must_match_full_content() -> None:
    result = harmonize_identification_evidence(build_scenario_request())
    values = result.model_dump(mode="python")
    values["result_digest"] = "sha256:" + ("f" * 64)

    with pytest.raises(ValidationError, match="result digest does not match"):
        _validate_result(values)


def test_full_result_is_semantically_deterministic_under_unordered_members() -> None:
    request = build_scenario_request()
    baseline = harmonize_identification_evidence(request)
    values = request.model_dump(mode="python")
    values["observations"] = tuple(reversed(values["observations"]))
    values["biological_controls"] = tuple(reversed(values["biological_controls"]))
    for observation in values["observations"]:
        observation["factor_levels"] = tuple(reversed(observation["factor_levels"]))
        observation["evidence"] = tuple(reversed(observation["evidence"]))
    for stage in values["profile"]["stages"]:
        stage["control_target_ids"] = tuple(reversed(stage["control_target_ids"]))
        stage["control_feature_ids"] = tuple(reversed(stage["control_feature_ids"]))

    reordered = harmonize_identification_evidence(values)

    assert reordered == baseline
    assert reordered.result_digest == baseline.result_digest


def test_source_digest_canonicalizes_unordered_factor_and_evidence_members() -> None:
    output_value = harmonize_identification_evidence(build_scenario_request()).values[0]
    source = output_value.source_observation
    baseline = observation_summary_digest(
        target_id=source.target_id,
        feature_id=source.feature_id,
        biological_group_id=source.biological_group_id,
        state=source.state.value,
        value=source.value,
        censoring_limit=source.censoring_limit,
        unit=source.unit,
        factor_levels=tuple((item.factor.value, item.level_id) for item in source.factor_levels),
        evidence_digests=source.evidence_digests,
    )
    reordered = observation_summary_digest(
        target_id=source.target_id,
        feature_id=source.feature_id,
        biological_group_id=source.biological_group_id,
        state=source.state.value,
        value=source.value,
        censoring_limit=source.censoring_limit,
        unit=source.unit,
        factor_levels=tuple(
            reversed(tuple((item.factor.value, item.level_id) for item in source.factor_levels))
        ),
        evidence_digests=tuple(reversed(source.evidence_digests)),
    )

    assert reordered == baseline == output_value.source_observation_digest


@pytest.mark.parametrize("module_index", range(4))
def test_non_m0205_receipts_cannot_claim_mask_ownership(module_index: int) -> None:
    receipt = _result_payload()["upstream_receipts"][module_index]
    receipt["evaluated_target_ids"] = ("sample.000",)

    with pytest.raises(ValidationError, match="only M02-05 may issue"):
        UpstreamHarmonizationReceipt.model_validate(receipt, strict=True)


@pytest.mark.parametrize(
    ("module_index", "disposition"),
    [
        (0, "fabricated"),
        (1, "accepted"),
        (2, "conformant"),
        (3, "rejected"),
        (4, "abstained"),
    ],
)
def test_upstream_receipt_rejects_impossible_module_disposition(
    module_index: int,
    disposition: str,
) -> None:
    receipt = _result_payload()["upstream_receipts"][module_index]
    receipt["disposition"] = disposition

    with pytest.raises(ValidationError, match="disposition contradicts its module"):
        UpstreamHarmonizationReceipt.model_validate(receipt, strict=True)


@pytest.mark.parametrize(
    ("case", "disposition"),
    [
        ("upstream_excluded_target", "accepted"),
        ("conformant_eight_factor", "quarantined"),
    ],
)
def test_m0205_receipt_disposition_must_match_its_mask(
    case: str,
    disposition: str,
) -> None:
    receipt = _result_payload(case)["upstream_receipts"][4]
    receipt["disposition"] = disposition

    with pytest.raises(ValidationError, match="disposition contradicts its exclusion mask"):
        UpstreamHarmonizationReceipt.model_validate(receipt, strict=True)


def test_result_digest_canonicalizes_every_unordered_output_collection() -> None:
    baseline = harmonize_identification_evidence(build_scenario_request("upstream_excluded_target"))
    values = baseline.model_dump(mode="python")
    artifact_receipt = values["upstream_receipts"][4]
    artifact_receipt["evaluated_target_ids"] = tuple(
        reversed(artifact_receipt["evaluated_target_ids"])
    )
    values["biological_controls"] = tuple(reversed(values["biological_controls"]))
    values["technical_effect_diagnostics"] = tuple(reversed(values["technical_effect_diagnostics"]))
    for stage in values["transformation_manifest"]["stages"]:
        stage["control_target_ids"] = tuple(reversed(stage["control_target_ids"]))
        stage["control_feature_ids"] = tuple(reversed(stage["control_feature_ids"]))
        stage["level_shifts"] = tuple(reversed(stage["level_shifts"]))
    values["result_digest"] = _SENTINEL_DIGEST

    replayed = IdentificationHarmonizationResult.model_validate(values, strict=True)

    assert replayed.result_digest == baseline.result_digest
