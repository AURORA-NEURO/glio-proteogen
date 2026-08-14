"""Genuine-chain lifecycle, acceptance, capacity, and benchmark tests for M04-05."""

from __future__ import annotations

import json
from typing import Final

import pytest
from evals.m04_05.benchmark import run_benchmark
from evals.m04_05.run import (
    SCENARIO_PATH,
    build_maximum_scenario_request,
    build_scenario_request,
    build_scenario_result,
    run_evaluation,
)

from glio_proteogen.contracts.m04_05 import (
    M0405_DETECTOR_CLASS_COUNT,
    M0405_FALSE_EXCLUSION_CEILING_PPM,
    M0405_MAX_CANONICAL_REQUEST_BYTES,
    M0405_MAX_CANONICAL_RESULT_BYTES,
    M0405_MAX_EVENTS,
    M0405_MAX_TARGETS,
    M0405_SEEDED_SENSITIVITY_FLOOR_PPM,
    ProteoformArtifactDetectorClass,
    ProteoformArtifactDisposition,
    ProteoformArtifactEvidenceLedger,
    ProteoformArtifactFindingCode,
    ProteoformArtifactObservationState,
    ProteoformArtifactPosteriorState,
    ProteoformArtifactSeverity,
    canonical_request_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c04_proteoform_isoform.m04_05_artifact_detection import (
    M0405Plugin,
    M0405Service,
    detect_proteoform_artifacts,
)

_CONTAMINATION_CLASSES: Final = {
    ProteoformArtifactDetectorClass.CONTAMINATION,
    ProteoformArtifactDetectorClass.BARCODE_INDEX,
}
_CASE_COUNT: Final = 15
_SAFE_FAILURE_EVIDENCE_COUNT: Final = 8


def test_locked_fifteen_case_panel_executes_exact_expected_outputs() -> None:
    fixture = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    case_ids = tuple(fixture["case_ids"])
    assert len(case_ids) == len(set(case_ids)) == _CASE_COUNT
    for case_id in case_ids:
        expected = fixture["expected"][case_id]
        result = build_scenario_result(case_id)
        assert result.disposition.value == expected["disposition"]
        assert len(result.artifact_posteriors) == expected["posteriors"]
        assert len(result.contamination_flags) == expected["flags"]
        assert len(result.exclusion_mask) == expected["excluded"]
        assert len(result.evidence) == expected["evidence"]


@pytest.mark.parametrize("detector_class", tuple(ProteoformArtifactDetectorClass))
def test_each_seeded_critical_class_is_detected_and_excluded(
    detector_class: ProteoformArtifactDetectorClass,
) -> None:
    result = build_scenario_result(f"critical_{detector_class.value}")
    triggered = tuple(
        posterior
        for posterior in result.artifact_posteriors
        if posterior.detector_class is detector_class
    )
    assert len(triggered) == 1
    assert triggered[0].state is ProteoformArtifactPosteriorState.DETECTED
    assert result.disposition is ProteoformArtifactDisposition.QUARANTINED
    assert len(result.exclusion_mask) == 1
    if detector_class in _CONTAMINATION_CLASSES:
        assert len(result.contamination_flags) == 1
        assert result.contamination_flags[0].severity is ProteoformArtifactSeverity.EXCLUDE
    else:
        assert result.contamination_flags == ()


def test_suspected_contamination_flags_without_false_exclusion() -> None:
    result = build_scenario_result("suspected_barcode")
    assert result.disposition is ProteoformArtifactDisposition.QUARANTINED
    assert len(result.contamination_flags) == 1
    assert result.contamination_flags[0].severity is ProteoformArtifactSeverity.REVIEW
    assert result.exclusion_mask == ()
    posterior = next(
        item
        for item in result.artifact_posteriors
        if item.detector_class is ProteoformArtifactDetectorClass.BARCODE_INDEX
    )
    assert posterior.state is ProteoformArtifactPosteriorState.SUSPECTED


@pytest.mark.parametrize(
    ("case_id", "observation"),
    [
        ("missing_mapping", ProteoformArtifactObservationState.MISSING),
        ("unsupported_context", ProteoformArtifactObservationState.UNSUPPORTED),
    ],
)
def test_missing_and_unsupported_are_indeterminate_not_negative(
    case_id: str,
    observation: ProteoformArtifactObservationState,
) -> None:
    result = build_scenario_result(case_id)
    indeterminate = tuple(
        item for item in result.artifact_posteriors if item.observation_state is observation
    )
    assert result.disposition is ProteoformArtifactDisposition.ABSTAINED
    assert len(indeterminate) == 1
    assert indeterminate[0].state is ProteoformArtifactPosteriorState.INDETERMINATE
    assert indeterminate[0].posterior_ppm is None
    assert indeterminate[0].support.status is SupportStatus.UNSUPPORTED
    assert result.exclusion_mask == ()


@pytest.mark.parametrize(
    ("case_id", "disposition", "finding"),
    [
        (
            "unsupported_profile",
            ProteoformArtifactDisposition.ABSTAINED,
            ProteoformArtifactFindingCode.DETECTOR_PROFILE_UNSUPPORTED,
        ),
        (
            "upstream_quarantined",
            ProteoformArtifactDisposition.QUARANTINED,
            ProteoformArtifactFindingCode.UPSTREAM_QUARANTINED,
        ),
        (
            "upstream_abstained",
            ProteoformArtifactDisposition.ABSTAINED,
            ProteoformArtifactFindingCode.UPSTREAM_ABSTAINED,
        ),
    ],
)
def test_safe_failures_emit_typed_zero_output_without_ledger(
    case_id: str,
    disposition: ProteoformArtifactDisposition,
    finding: ProteoformArtifactFindingCode,
) -> None:
    request = build_scenario_request(case_id)
    result = build_scenario_result(case_id)
    assert request.evidence_ledger is None
    assert result.disposition is disposition
    assert result.artifact_posteriors == result.contamination_flags == result.exclusion_mask == ()
    assert tuple(item.code for item in result.findings) == (finding,)
    assert len(result.evidence) == _SAFE_FAILURE_EVIDENCE_COUNT


def test_stale_binding_returns_a_digest_bound_nontraversing_receipt() -> None:
    request = build_scenario_request("binding_mismatch")
    result = build_scenario_result("binding_mismatch")
    assert request.evidence_ledger is not None
    assert result.receipt.evidence_ledger_digest == request.evidence_ledger.ledger_digest
    assert result.request.evidence_ledger is not None
    assert result.request.evidence_ledger.quality_result_digest == (
        request.evidence_ledger.quality_result_digest
    )
    assert result.artifact_posteriors == ()
    assert result.disposition is ProteoformArtifactDisposition.QUARANTINED
    assert result.findings[0].code is (
        ProteoformArtifactFindingCode.EVIDENCE_LEDGER_BINDING_MISMATCH
    )


def test_receipt_preserves_exact_m0404_and_authority_bindings() -> None:
    request = build_scenario_request()
    result = build_scenario_result()
    upstream = request.quality_result
    receipt = result.receipt
    assert receipt.quality_result_digest == upstream.result_digest
    assert receipt.quality_request_digest == upstream.request_digest
    assert receipt.quality_policy_digest == upstream.policy_digest
    assert receipt.quality_configuration_digest == upstream.configuration_digest
    assert receipt.quality_receipt_digest == upstream.receipt_digest
    assert receipt.identity_resolution_digest == upstream.receipt.identity_resolution_digest
    assert receipt.protocol_result_digest == upstream.receipt.protocol_result_digest
    assert receipt.reference_bundle_digest == upstream.receipt.reference_bundle_digest
    assert receipt.coordinate_policy_digest == upstream.receipt.coordinate_policy_digest
    assert receipt.intended_use_evidence_digest == (upstream.receipt.intended_use_evidence_digest)
    assert canonical_request_digest(request) in result.provenance.input_digests


def test_every_full_target_has_exactly_seven_detector_posteriors() -> None:
    result = build_scenario_result()
    targets = {item.target_id for item in result.artifact_posteriors}
    assert len(targets) == 1
    for target_id in targets:
        target_posteriors = tuple(
            item for item in result.artifact_posteriors if item.target_id == target_id
        )
        assert len(target_posteriors) == M0405_DETECTOR_CLASS_COUNT
        assert {item.detector_class for item in target_posteriors} == set(
            ProteoformArtifactDetectorClass
        )


def test_maximum_installed_shape_is_total_and_within_byte_caps() -> None:
    request = build_maximum_scenario_request()
    ledger = request.evidence_ledger
    assert type(ledger) is ProteoformArtifactEvidenceLedger
    result = detect_proteoform_artifacts(request)
    assert len({item.target_id for item in ledger.events}) == M0405_MAX_TARGETS
    assert len(ledger.events) == len(result.artifact_posteriors) == M0405_MAX_EVENTS
    assert result.disposition is ProteoformArtifactDisposition.CLEARED
    assert result.contamination_flags == result.exclusion_mask == ()
    assert len(canonical_json_bytes(request)) <= M0405_MAX_CANONICAL_REQUEST_BYTES
    assert len(canonical_json_bytes(result)) <= M0405_MAX_CANONICAL_RESULT_BYTES


def test_one_iteration_maximum_benchmark_uses_public_boundary_and_passes() -> None:
    report = run_benchmark(1)
    assert report.target_count == M0405_MAX_TARGETS
    assert report.event_count == report.posterior_count == M0405_MAX_EVENTS
    assert report.warmup_count == 1
    assert report.passed


def test_locked_evaluation_proves_sensitivity_false_exclusion_and_narrowing() -> None:
    report = run_evaluation()
    assert report["passed"] is True
    assert report["declared_case_count"] == report["executed_case_count"] == _CASE_COUNT
    assert report["seeded_sensitivity_ppm"] >= M0405_SEEDED_SENSITIVITY_FLOOR_PPM
    assert report["false_exclusion_ppm"] <= M0405_FALSE_EXCLUSION_CEILING_PPM
    assert report["nominal_coverage_ppm"] is None
    assert report["coverage_disposition"] == (
        "non_calibrated_scores_with_typed_narrowing_or_abstention"
    )
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "acceptance.non_calibrated_narrow_or_abstain"
    )
    assert check["passed"] is True


def test_plugin_descriptor_enforces_the_output_authority_ceiling() -> None:
    descriptor = M0405Plugin(M0405Service()).descriptor()
    prohibited = " ".join(descriptor.prohibited_outputs)
    assert descriptor.module_id == "GLIO-PROTEOGEN-M04-05"
    assert descriptor.safety_class == "S2"
    assert descriptor.gate == "G1"
    for term in ("identity", "consent", "kinase", "fusion", "treatment", "model"):
        assert term in prohibited
