"""Runtime, safe-failure, and service/plugin parity for M05-06."""

from __future__ import annotations

import json
from typing import cast

import pytest
from evals.m05_06.run import build_scenario, run_evaluation

from glio_proteogen.contracts.m05_06 import (
    M0506_ZERO_DIGEST,
    PtmLocalizationHarmonizationDisposition,
    PtmLocalizationHarmonizationFindingCode,
    PtmLocalizationNormalizationFactor,
    PtmLocalizationSupportLedger,
    PtmLocalizationSupportObservationState,
    support_ledger_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Plugin,
    M0506PtmLocalizationHarmonizationEngine,
    M0506Service,
    harmonize_ptm_localization_analysis,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization.kernel import (
    M0506PtmLocalizationHarmonizationKernel,
)

_EXPECTED_FACTOR_STAGES = 8
_EXPECTED_CASES = 3
_EXPECTED_COORDINATE_PPM = 500_000
_ALTERNATE_COORDINATE_PPM = 800_000
_EXPECTED_SHIFT_PPM = 300_000
_EXPECTED_EVEN_MEDIAN = 200


def test_median_helper_handles_even_and_empty_anchor_sets() -> None:
    assert M0506PtmLocalizationHarmonizationKernel._median((100, 300)) == _EXPECTED_EVEN_MEDIAN
    with pytest.raises(ValueError, match="anchor median"):
        M0506PtmLocalizationHarmonizationKernel._median(())


def test_clear_runtime_emits_eight_stage_analysis() -> None:
    result = harmonize_ptm_localization_analysis(build_scenario("clear").request)
    assert result.disposition is PtmLocalizationHarmonizationDisposition.ACCEPTED
    assert result.analysis is not None
    assert result.transformation_manifest is not None
    assert len(result.analysis.values) == 1
    assert len(result.transformation_manifest.stages) == _EXPECTED_FACTOR_STAGES
    assert len(result.technical_effect_diagnostics) == _EXPECTED_FACTOR_STAGES


def test_anchor_median_shift_is_applied_to_non_reference_level() -> None:
    """The kernel removes a known platform-level offset from held-out support."""

    scenario = build_scenario("clear")
    ledger = scenario.request.support_ledger
    assert ledger is not None
    reference = ledger.observations[0]
    alternate_target = f"target.{sha256_digest('alternate-target').removeprefix('sha256:')}"
    alternate_level = f"level.{sha256_digest('alternate-platform').removeprefix('sha256:')}"
    levels = tuple(
        level.model_copy(update={"level_id": alternate_level})
        if level.factor is PtmLocalizationNormalizationFactor.PLATFORM
        else level
        for level in reference.factor_levels
    )
    alternate = reference.model_copy(
        update={
            "target_id": alternate_target,
            "support_coordinate_ppm": _ALTERNATE_COORDINATE_PPM,
            "factor_levels": levels,
        }
    )
    constructed = ledger.model_copy(
        update={
            "observations": tuple(
                sorted(
                    (
                        reference.model_copy(
                            update={"support_coordinate_ppm": _EXPECTED_COORDINATE_PPM}
                        ),
                        alternate,
                    ),
                    key=canonical_json_bytes,
                )
            ),
            "ledger_digest": M0506_ZERO_DIGEST,
        }
    )
    ledger = constructed.model_copy(
        update={"ledger_digest": support_ledger_digest(constructed)}
    )
    ledger = PtmLocalizationSupportLedger.model_validate(ledger, strict=True)
    first_stage = scenario.request.policy.profiles[0].stages[0].model_copy(
        update={
            "estimation_anchor_ids": (reference.target_id, alternate_target),
            "validation_anchor_ids": (),
        }
    )
    stages = (first_stage, *scenario.request.policy.profiles[0].stages[1:])
    profile = scenario.request.policy.profiles[0].model_copy(update={"stages": stages})
    policy = scenario.request.policy.model_copy(
        update={"profiles": (profile,), "max_absolute_shift_ppm": _EXPECTED_SHIFT_PPM}
    )
    execution = M0506PtmLocalizationHarmonizationKernel().harmonize(
        ledger,
        policy,
        profile_digest=sha256_digest(profile),
        policy_digest=sha256_digest(policy),
        configuration_digest=sha256_digest({"policy": policy}),
    )
    assert execution.analysis is not None
    adjusted = next(
        item for item in execution.analysis.values if item.target_id == alternate_target
    )
    assert adjusted.harmonized_coordinate_ppm == _EXPECTED_COORDINATE_PPM
    assert execution.transformation_manifest is not None
    shift = next(
        item
        for item in execution.transformation_manifest.stages[0].level_shifts
        if item.level_id == alternate_level
    )
    assert shift.estimated_shift_ppm == _EXPECTED_SHIFT_PPM
    assert shift.applied_shift_ppm == _EXPECTED_SHIFT_PPM

    # With no reference anchor, the alternate level is deliberately left
    # unevaluable instead of being treated as a zero-offset observation.
    unanchored_stage = first_stage.model_copy(
        update={"estimation_anchor_ids": (alternate_target,)}
    )
    unanchored_profile = profile.model_copy(
        update={"stages": (unanchored_stage, *profile.stages[1:])}
    )
    unanchored_policy = policy.model_copy(update={"profiles": (unanchored_profile,)})
    unanchored = M0506PtmLocalizationHarmonizationKernel().harmonize(
        ledger,
        unanchored_policy,
        profile_digest=sha256_digest(unanchored_profile),
        policy_digest=sha256_digest(unanchored_policy),
        configuration_digest=sha256_digest({"policy": unanchored_policy}),
    )
    assert unanchored.transformation_manifest is not None
    assert not any(
        item.level_id == alternate_level
        for item in unanchored.transformation_manifest.stages[0].level_shifts
    )


def test_censored_support_keeps_a_bound_and_receives_stage_adjustments() -> None:
    scenario = build_scenario("clear")
    source = scenario.request.support_ledger
    assert source is not None
    observation = source.observations[0].model_copy(
        update={
            "state": PtmLocalizationSupportObservationState.CENSORED,
            "support_coordinate_ppm": None,
            "censoring_upper_bound_ppm": _EXPECTED_COORDINATE_PPM,
        }
    )
    constructed = source.model_copy(
        update={"observations": (observation,), "ledger_digest": M0506_ZERO_DIGEST}
    )
    ledger = constructed.model_copy(
        update={"ledger_digest": support_ledger_digest(constructed)}
    )
    ledger = PtmLocalizationSupportLedger.model_validate(ledger, strict=True)
    execution = M0506PtmLocalizationHarmonizationKernel().harmonize(
        ledger,
        scenario.request.policy,
        profile_digest=sha256_digest(scenario.request.policy.profiles[0]),
        policy_digest=sha256_digest(scenario.request.policy),
        configuration_digest=sha256_digest({"policy": scenario.request.policy}),
    )
    assert execution.analysis is not None
    value = execution.analysis.values[0]
    assert value.harmonized_coordinate_ppm is None
    assert value.censoring_upper_bound_ppm == _EXPECTED_COORDINATE_PPM
    assert len(value.applied_adjustments) == _EXPECTED_FACTOR_STAGES

    missing = observation.model_copy(
        update={
            "state": PtmLocalizationSupportObservationState.MISSING,
            "censoring_upper_bound_ppm": None,
        }
    )
    missing_source = source.model_copy(
        update={"observations": (missing,), "ledger_digest": M0506_ZERO_DIGEST}
    )
    missing_ledger = missing_source.model_copy(
        update={"ledger_digest": support_ledger_digest(missing_source)}
    )
    missing_ledger = PtmLocalizationSupportLedger.model_validate(missing_ledger, strict=True)
    missing_execution = M0506PtmLocalizationHarmonizationKernel().harmonize(
        missing_ledger,
        scenario.request.policy,
        profile_digest=sha256_digest(scenario.request.policy.profiles[0]),
        policy_digest=sha256_digest(scenario.request.policy),
        configuration_digest=sha256_digest({"policy": scenario.request.policy}),
    )
    assert missing_execution.analysis is not None
    missing_value = missing_execution.analysis.values[0]
    assert missing_value.harmonized_coordinate_ppm is None
    assert missing_value.censoring_upper_bound_ppm is None
    assert missing_value.applied_adjustments == ()


def test_quarantined_upstream_is_not_released() -> None:
    result = harmonize_ptm_localization_analysis(build_scenario("quarantined").request)
    assert result.disposition is PtmLocalizationHarmonizationDisposition.QUARANTINED
    assert result.analysis is None
    assert result.transformation_manifest is None
    assert result.findings[0].code is PtmLocalizationHarmonizationFindingCode.UPSTREAM_QUARANTINED
    assert result.human_review_required is True


def test_abstained_upstream_is_not_downgraded_to_negative() -> None:
    result = harmonize_ptm_localization_analysis(build_scenario("abstained").request)
    assert result.disposition is PtmLocalizationHarmonizationDisposition.ABSTAINED
    assert result.analysis is None
    assert result.findings[0].code is PtmLocalizationHarmonizationFindingCode.UPSTREAM_ABSTAINED
    assert result.human_review_required is True


def test_service_object_and_json_mapping_are_digest_identical() -> None:
    scenario = build_scenario("clear")
    service = M0506Service()
    typed_result = service.execute(scenario.request)
    mapped_result = service.execute(scenario.request.model_dump(mode="json"))
    assert typed_result.result_digest == mapped_result.result_digest


def test_service_validated_execution_matches_public_engine() -> None:
    scenario = build_scenario("clear")
    service = M0506Service()
    validated = service.validate_request(scenario.request)
    assert service._execute_validated(validated).result_digest == (
        M0506PtmLocalizationHarmonizationEngine().harmonize(scenario.request).result_digest
    )


def test_plugin_validation_and_run_match_service() -> None:
    scenario = build_scenario("clear")
    service = M0506Service()
    plugin = M0506Plugin(service)
    token = plugin.validate(scenario.request.model_dump(mode="json"))
    assert plugin.run(token).result_digest == service.execute(scenario.request).result_digest


def test_plugin_json_bytes_use_the_same_canonical_result() -> None:
    scenario = build_scenario("clear")
    plugin = M0506Plugin(M0506Service())
    serialized = json.dumps(scenario.request.model_dump(mode="json"), sort_keys=True)
    token = plugin.validate(serialized)
    assert (
        plugin.run(token).result_digest
        == harmonize_ptm_localization_analysis(scenario.request).result_digest
    )


def test_engine_rejects_unvalidated_execution_type() -> None:
    with pytest.raises(TypeError, match="validated execution"):
        M0506PtmLocalizationHarmonizationEngine().harmonize_validated(object())  # type: ignore[arg-type]


def test_tampered_receipt_is_rejected_before_execution() -> None:
    scenario = build_scenario("clear")
    tampered = scenario.request.model_copy(
        update={
            "artifact_receipt": scenario.request.artifact_receipt.model_copy(
                update={"artifact_result_digest": "sha256:" + ("0" * 64)}
            )
        }
    )
    with pytest.raises(ValueError, match=r"receipt|bind"):
        M0506Service.validate_request(tampered)


def test_cleared_result_without_support_is_rejected() -> None:
    scenario = build_scenario("clear")
    missing_support = scenario.request.model_copy(update={"support_ledger": None})
    with pytest.raises(ValueError, match="support ledger"):
        M0506Service.validate_request(missing_support)


def test_failed_upstream_cannot_traverse_support_ledger() -> None:
    clear = build_scenario("clear")
    quarantined = build_scenario("quarantined")
    forged = quarantined.request.model_copy(update={"support_ledger": clear.request.support_ledger})
    with pytest.raises(ValueError, match="cannot traverse support"):
        M0506Service.validate_request(forged)


def test_evaluator_matrix_covers_all_safe_dispositions() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert len(cast("list[object]", report["checks"])) == _EXPECTED_CASES


def test_clear_harmonized_value_preserves_coordinate_and_source_binding() -> None:
    result = harmonize_ptm_localization_analysis(build_scenario("clear").request)
    assert result.analysis is not None
    value = result.analysis.values[0]
    assert value.input_coordinate_ppm == _EXPECTED_COORDINATE_PPM
    assert value.harmonized_coordinate_ppm == value.input_coordinate_ppm
    assert value.source_observation_digest.startswith("sha256:")
