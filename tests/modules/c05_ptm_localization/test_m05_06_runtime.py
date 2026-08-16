"""Runtime, safe-failure, and service/plugin parity for M05-06."""

from __future__ import annotations

import json

import pytest
from evals.m05_06.run import build_scenario, run_evaluation

from glio_proteogen.contracts.m05_06 import (
    PtmLocalizationHarmonizationDisposition,
    PtmLocalizationHarmonizationFindingCode,
)
from glio_proteogen.modules.c05_ptm_localization.m05_06_harmonization import (
    M0506Plugin,
    M0506PtmLocalizationHarmonizationEngine,
    M0506Service,
    harmonize_ptm_localization_analysis,
)

_EXPECTED_FACTOR_STAGES = 8
_EXPECTED_CASES = 3
_EXPECTED_COORDINATE_PPM = 500_000


def test_clear_runtime_emits_eight_stage_analysis() -> None:
    result = harmonize_ptm_localization_analysis(build_scenario("clear").request)
    assert result.disposition is PtmLocalizationHarmonizationDisposition.ACCEPTED
    assert result.analysis is not None
    assert result.transformation_manifest is not None
    assert len(result.analysis.values) == 1
    assert len(result.transformation_manifest.stages) == _EXPECTED_FACTOR_STAGES
    assert len(result.technical_effect_diagnostics) == _EXPECTED_FACTOR_STAGES


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
    assert plugin.run(token).result_digest == harmonize_ptm_localization_analysis(
        scenario.request
    ).result_digest


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
    assert len(report["checks"]) == _EXPECTED_CASES


def test_clear_harmonized_value_preserves_coordinate_and_source_binding() -> None:
    result = harmonize_ptm_localization_analysis(build_scenario("clear").request)
    assert result.analysis is not None
    value = result.analysis.values[0]
    assert value.input_coordinate_ppm == _EXPECTED_COORDINATE_PPM
    assert value.harmonized_coordinate_ppm == value.input_coordinate_ppm
    assert value.source_observation_digest.startswith("sha256:")
