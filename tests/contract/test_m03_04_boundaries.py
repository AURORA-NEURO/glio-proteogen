"""Boundary and precedence checks for M03-04 quality contracts."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, cast

import pytest
from evals.m03_04.run import Scenario, build_capacity_scenario_request, build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_02 import ReconciliationFindingCode
from glio_proteogen.contracts.m03_03 import (
    M0303_MAX_DECODED_BYTES,
    M0303_MAX_SOURCE_BYTES,
)
from glio_proteogen.contracts.m03_04 import (
    M0304_MAX_COUNT,
    M0304_MAX_EVIDENCE,
    M0304_MAX_LINEAGE_ARTIFACTS,
    M0304_MAX_SOURCES,
    M0304_METRIC_COUNT,
    M0304_RATE_SCALE,
    ComputeProteinInferenceQualityRequest,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityCounts,
    ProteinInferenceQualityDisposition,
    ProteinInferenceQualityFactLedger,
    ProteinInferenceQualityFactStates,
    ProteinInferenceQualityFinding,
    ProteinInferenceQualityFindingCode,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricProvenance,
    ProteinInferenceQualityMetricResult,
    ProteinInferenceQualityMetricStatus,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityResult,
    ProteinInferenceQualityThreshold,
    ProteinInferenceRawQualityClaimReceipt,
    ProteinInferenceRawQualityReceipt,
    ProteinInferenceRawQualitySourceReceipt,
    configuration_digest,
    expected_disposition,
    expected_quality_findings,
    expected_support,
    fact_ledger_digest,
    finding_for,
    quality_evidence_index,
    raw_quality_receipt_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m03_04 import v1 as m0304_v1
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics.kernel import (
    classify_quality_ratio,
)

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_ROUNDED_TWO_THIRDS = 666_667
_EXPECTED_MULTIPLE_PEPTIDE_SOURCES = 2


@pytest.fixture(scope="module")
def canonical_scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def canonical_result(canonical_scenario: Scenario) -> ProteinInferenceQualityResult:
    return compute_protein_inference_quality(canonical_scenario.request)


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _provenance() -> ProteinInferenceQualityMetricProvenance:
    return ProteinInferenceQualityMetricProvenance(
        admission_result_digest=_ZERO_DIGEST,
        fact_ledger_digest=_ZERO_DIGEST,
        profile_digest=_ZERO_DIGEST,
        threshold_digest=_ZERO_DIGEST,
        source_binding_digest=_ZERO_DIGEST,
        claim_binding_digest=_ZERO_DIGEST,
    )


def _validate_resigned_receipt(payload: dict[str, Any]) -> ProteinInferenceRawQualityReceipt:
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    return ProteinInferenceRawQualityReceipt.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _validate_resigned_result(payload: dict[str, Any]) -> ProteinInferenceQualityResult:
    payload["result_digest"] = result_payload_digest(payload)
    return ProteinInferenceQualityResult.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


@pytest.mark.parametrize(
    ("code", "direction", "passing", "warning"),
    [
        ("peptide_assignment_coverage", "at_least", 600_000, 700_000),
        ("protein_group_ambiguity_burden", "at_most", 400_000, 300_000),
    ],
)
def test_threshold_rejects_reversed_warning_band(
    canonical_scenario: Scenario,
    code: str,
    direction: str,
    passing: int,
    warning: int,
) -> None:
    payload = _payload(canonical_scenario.request.policy.profiles[0].thresholds[0])
    payload.update(
        {
            "metric_code": code,
            "direction": direction,
            "pass_threshold_ppm": passing,
            "warning_threshold_ppm": warning,
        }
    )
    with pytest.raises(ValidationError, match="directionally invalid"):
        ProteinInferenceQualityThreshold.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_profile_and_policy_reject_duplicate_semantic_members(
    canonical_scenario: Scenario,
) -> None:
    profile = canonical_scenario.request.policy.profiles[0]
    profile_payload = _payload(profile)
    profile_payload["thresholds"][-1] = profile_payload["thresholds"][0]
    with pytest.raises(ValidationError, match="each of the eight metrics"):
        ProteinInferenceAssayQualityProfile.model_validate_json(
            canonical_json_bytes(profile_payload), strict=True
        )
    policy_payload = _payload(canonical_scenario.request.policy)
    policy_payload["profiles"].append(policy_payload["profiles"][0])
    with pytest.raises(ValidationError, match="identities must be unique"):
        type(canonical_scenario.request.policy).model_validate_json(
            canonical_json_bytes(policy_payload), strict=True
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_diagnostic",
        "decoded_count_without_digest",
        "partial_decode_with_digest",
        "decoded_overflow_without_code",
        "raw_overflow_without_code",
        "version_without_format",
    ],
)
def test_source_projection_rejects_internally_contradictory_summary(
    canonical_scenario: Scenario,
    mutation: str,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt.sources[0])
    if mutation == "duplicate_diagnostic":
        payload["diagnostic_codes"] = ["build_mismatch", "build_mismatch"]
    elif mutation == "decoded_count_without_digest":
        payload.update({"decoded_digest": None, "decoded_size_bytes": 1})
    elif mutation == "partial_decode_with_digest":
        payload["diagnostic_codes"] = ["decoded_size_limit_exceeded"]
    elif mutation == "decoded_overflow_without_code":
        payload["decoded_size_bytes"] = M0303_MAX_DECODED_BYTES + 1
    elif mutation == "raw_overflow_without_code":
        payload["source_size_bytes"] = M0303_MAX_SOURCE_BYTES + 1
    else:
        payload.update({"detected_format": None, "detected_version": "1.0.0"})
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualitySourceReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_claim_projection_rejects_duplicate_finding_codes(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt.claims[0])
    code = ReconciliationFindingCode.DUPLICATE_CONTENT_RETAINED.value
    payload["finding_codes"] = [code, code]
    with pytest.raises(ValidationError, match="finding codes must be unique"):
        ProteinInferenceRawQualityClaimReceipt.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_source_id",
        "incomplete_source_count",
        "missing_claim_binding",
        "claim_artifact_disagreement",
        "safe_failure_rows",
        "missing_spectra",
        "spectra_cap_plus_one",
        "extra_unbound_peptide",
        "missing_conditional_reference",
        "duplicate_context_role",
    ],
)
def test_compact_receipt_rejects_resigned_structural_forgery_matrix(  # noqa: C901
    canonical_scenario: Scenario,
    mutation: str,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    sources = payload["sources"]
    claims = payload["claims"]
    if mutation == "duplicate_source_id":
        sources[1]["source_id"] = sources[0]["source_id"]
    elif mutation == "incomplete_source_count":
        payload["source_count"] -= 1
    elif mutation == "missing_claim_binding":
        next(item for item in sources if item["bound_claim_id"] is not None)[
            "bound_claim_id"
        ] = None
    elif mutation == "claim_artifact_disagreement":
        claims[0]["artifact_digest"] = "sha256:" + ("b" * 64)
    elif mutation == "safe_failure_rows":
        payload.update(
            {
                "upstream_disposition": "rejected",
                "upstream_support_status": "unsupported",
                "upstream_human_review_required": True,
            }
        )
    elif mutation == "missing_spectra":
        payload["sources"] = [item for item in sources if item["role"] != "spectra"]
        payload["source_count"] = len(payload["sources"])
    elif mutation == "spectra_cap_plus_one":
        template = next(item for item in sources if item["role"] == "spectra")
        for index in range(32):
            clone = dict(template)
            clone["source_id"] = f"source.m0304.spectra.overflow.{index:02d}"
            sources.append(clone)
        payload["source_count"] = len(sources)
    elif mutation == "extra_unbound_peptide":
        template = next(item for item in sources if item["role"] == "peptide_evidence")
        clone = dict(template)
        clone.update(
            {
                "source_id": "source.m0304.peptide.unbound-extra",
                "bound_claim_id": None,
            }
        )
        sources.append(clone)
        payload["source_count"] += 1
    elif mutation == "missing_conditional_reference":
        index = next(
            index
            for index, item in enumerate(sources)
            if item["role"] in {"isoform_sequences", "variant_sequences", "contaminant_sequences"}
        )
        sources.pop(index)
        payload["source_count"] -= 1
    else:
        template = next(item for item in sources if item["role"] == "genomic_context")
        clone = dict(template)
        clone["source_id"] = "source.m0304.genomic.duplicate"
        sources.append(clone)
        payload["source_count"] += 1
    with pytest.raises(ValidationError):
        _validate_resigned_receipt(payload)


def test_compact_receipt_rejects_wrong_singleton_claim_role_cardinality(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    claim = next(
        item for item in payload["claims"] if item["claim_role"] == "protein_group_manifest"
    )
    claim["claim_role"] = "ambiguity_manifest"
    with pytest.raises(ValidationError, match="exact lineage role shape"):
        _validate_resigned_receipt(payload)


@pytest.mark.parametrize(
    ("reference", "state"),
    [
        ("consent", "withheld"),
        ("quality", "rejected"),
        ("identity_lineage", "unresolved"),
    ],
)
def test_request_model_rejects_each_authorization_class(
    canonical_scenario: Scenario,
    reference: str,
    state: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    payload["context"]["references"][reference]["state"] = state
    with pytest.raises(ValidationError):
        ComputeProteinInferenceQualityRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_request_ingress_guard_rejects_first_byte_over_active_cap(
    canonical_scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload(canonical_scenario.request)
    monkeypatch.setattr(
        m0304_v1,
        "M0304_MAX_CANONICAL_REQUEST_BYTES",
        len(canonical_json_bytes(payload)) - 1,
    )
    with pytest.raises(ValidationError, match="ingress ceiling"):
        ComputeProteinInferenceQualityRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def _safe_upstream_request(
    scenario: Scenario,
    disposition: str,
) -> ComputeProteinInferenceQualityRequest:
    request = scenario.request
    payload = _payload(request.raw_quality_receipt)
    support, review = {
        "validated": ("supported", False),
        "quarantined": ("review_required", True),
        "abstained": ("unsupported", True),
    }[disposition]
    payload.update(
        {
            "upstream_disposition": disposition,
            "upstream_support_status": support,
            "upstream_human_review_required": review,
            "sources": [],
            "claims": [],
        }
    )
    if disposition == "validated":
        payload["lineage_artifact_count"] = M0304_MAX_LINEAGE_ARTIFACTS + 1
    receipt = _validate_resigned_receipt(payload)
    return ComputeProteinInferenceQualityRequest(
        context=request.context,
        raw_quality_receipt=receipt,
        fact_ledger=None,
        policy=request.policy,
    )


@pytest.mark.parametrize(
    ("upstream", "disposition", "finding"),
    [
        ("quarantined", "quarantined", "upstream_quarantined"),
        ("abstained", "abstained", "upstream_abstained"),
        ("validated", "abstained", "upstream_shape_unsupported"),
    ],
)
def test_safe_upstream_disposition_and_finding_propagate_exactly(
    canonical_scenario: Scenario,
    upstream: str,
    disposition: str,
    finding: str,
) -> None:
    request = _safe_upstream_request(canonical_scenario, upstream)
    assert expected_disposition(request).value == disposition
    assert {item.code.value for item in expected_quality_findings(request)} == {finding}


def test_safe_result_rejects_resigned_metric_injection(
    canonical_scenario: Scenario,
    canonical_result: ProteinInferenceQualityResult,
) -> None:
    safe = compute_protein_inference_quality(
        _safe_upstream_request(canonical_scenario, "quarantined")
    )
    payload = _payload(safe)
    payload["metrics"] = [_payload(canonical_result.metrics[0])]
    with pytest.raises(ValidationError, match="safe-failure"):
        _validate_resigned_result(payload)


def test_result_rejects_digest_only_tamper(
    canonical_result: ProteinInferenceQualityResult,
) -> None:
    payload = _payload(canonical_result)
    payload["result_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError, match="digest does not match"):
        ProteinInferenceQualityResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize("mutation", ["required", "ratio", "provenance"])
def test_result_replay_rejects_resigned_metric_forgery(
    canonical_result: ProteinInferenceQualityResult,
    mutation: str,
) -> None:
    payload = _payload(canonical_result)
    metric = next(
        item
        for item in payload["metrics"]
        if item["metric_code"] == "peptide_assignment_coverage"
    )
    if mutation == "required":
        metric["required"] = not metric["required"]
    elif mutation == "ratio":
        metric.update({"numerator": 94, "denominator": 100, "value_ppm": 940_000})
    else:
        metric["provenance"]["source_binding_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError):
        _validate_resigned_result(payload)


@pytest.mark.parametrize("kind", ["required_warning", "not_evaluable", "not_applicable"])
def test_metric_fallback_disposition_never_qualifies_required_nonpass(
    canonical_scenario: Scenario,
    kind: str,
) -> None:
    common: dict[str, object] = {
        "metric_code": ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE,
        "required": True,
        "provenance": _provenance(),
    }
    if kind == "required_warning":
        common.update(
            {
                "observation_state": ProteinInferenceQualityObservationState.OBSERVED,
                "status": ProteinInferenceQualityMetricStatus.WARNING,
                "numerator": 1,
                "denominator": 2,
                "value_ppm": 500_000,
            }
        )
        expected = ProteinInferenceQualityDisposition.QUARANTINED
    elif kind == "not_evaluable":
        common.update(
            {
                "observation_state": ProteinInferenceQualityObservationState.OBSERVED,
                "status": ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
                "numerator": 0,
                "denominator": 0,
            }
        )
        expected = ProteinInferenceQualityDisposition.ABSTAINED
    else:
        common.update(
            {
                "observation_state": ProteinInferenceQualityObservationState.NOT_APPLICABLE,
                "status": ProteinInferenceQualityMetricStatus.NOT_APPLICABLE,
            }
        )
        expected = ProteinInferenceQualityDisposition.ABSTAINED
    metric = ProteinInferenceQualityMetricResult.model_validate(common, strict=True)
    assert expected_disposition(
        canonical_scenario.request,
        metrics=(metric,),
        findings=(),
    ) is expected


def test_required_unsupported_and_optional_warning_have_exact_finding_and_support(
    canonical_scenario: Scenario,
) -> None:
    unsupported = ProteinInferenceQualityMetricResult(
        metric_code=ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE,
        observation_state=ProteinInferenceQualityObservationState.UNSUPPORTED,
        status=ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
        required=True,
        provenance=_provenance(),
    )
    assert {item.code for item in expected_quality_findings(
        canonical_scenario.request, (unsupported,)
    )} == {ProteinInferenceQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED}
    optional = ProteinInferenceQualityMetricResult(
        metric_code=ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE,
        observation_state=ProteinInferenceQualityObservationState.OBSERVED,
        status=ProteinInferenceQualityMetricStatus.WARNING,
        required=False,
        numerator=1,
        denominator=2,
        value_ppm=500_000,
        provenance=_provenance(),
    )
    assert {item.code for item in expected_quality_findings(
        canonical_scenario.request, (optional,)
    )} == {ProteinInferenceQualityFindingCode.OPTIONAL_METRIC_WARNING}
    assert expected_support(
        ProteinInferenceQualityDisposition.QUALIFIED,
        (optional,),
    ).status is SupportStatus.LIMITED


def test_binding_fallback_handles_unvalidated_missing_ledger_totality(
    canonical_scenario: Scenario,
) -> None:
    candidate = canonical_scenario.request.model_copy(update={"fact_ledger": None})
    assert expected_disposition(candidate) is ProteinInferenceQualityDisposition.QUARANTINED


@pytest.mark.parametrize(
    ("code", "numerator", "denominator", "value_ppm", "censored_count"),
    [
        (ProteinInferenceQualityMetricCode.ADMITTED_SOURCE_COMPLETENESS, 13, 13, 1_000_000, 0),
        (ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE, 95, 100, 950_000, 0),
        (ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN, 10, 100, 100_000, 0),
        (
            ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE,
            15,
            20,
            750_000,
            0,
        ),
        (ProteinInferenceQualityMetricCode.PROTEIN_GROUP_DETECTION_SUPPORT, 16, 20, 800_000, 4),
        (
            ProteinInferenceQualityMetricCode.PROTEIN_GROUP_COMPETITION_CLOSURE,
            18,
            20,
            900_000,
            0,
        ),
        (ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY, 9, 10, 900_000, 0),
        (
            ProteinInferenceQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE,
            10,
            10,
            1_000_000,
            0,
        ),
    ],
)
def test_all_eight_metric_formulas_replay_exact_counts(  # noqa: PLR0913, PLR0917
    canonical_result: ProteinInferenceQualityResult,
    code: ProteinInferenceQualityMetricCode,
    numerator: int,
    denominator: int,
    value_ppm: int,
    censored_count: int,
) -> None:
    assert len(canonical_result.metrics) == M0304_METRIC_COUNT
    metric = next(item for item in canonical_result.metrics if item.metric_code is code)
    assert (metric.numerator, metric.denominator, metric.value_ppm) == (
        numerator,
        denominator,
        value_ppm,
    )
    assert metric.censored_count == censored_count
    expected_state = (
        ProteinInferenceQualityObservationState.CENSORED
        if censored_count
        else ProteinInferenceQualityObservationState.OBSERVED
    )
    assert metric.observation_state is expected_state


@pytest.mark.parametrize(
    ("code", "numerator", "denominator", "expected"),
    [
        (ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE, 7, 10, "pass"),
        (ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE, 6, 10, "warning"),
        (ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE, 4, 10, "fail"),
        (ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN, 2, 10, "pass"),
        (ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN, 1, 4, "warning"),
        (ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN, 4, 10, "fail"),
    ],
)
def test_threshold_pass_warning_fail_branches_use_directional_ratios(
    canonical_scenario: Scenario,
    code: ProteinInferenceQualityMetricCode,
    numerator: int,
    denominator: int,
    expected: str,
) -> None:
    threshold = next(
        item for item in canonical_scenario.request.policy.profiles[0].thresholds
        if item.metric_code is code
    )
    assert classify_quality_ratio(numerator, denominator, threshold).value == expected


def test_threshold_classification_uses_cross_multiplication_before_ppm_rounding(
    canonical_scenario: Scenario,
) -> None:
    base = next(
        item for item in canonical_scenario.request.policy.profiles[0].thresholds
        if item.metric_code is ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE
    )
    threshold = ProteinInferenceQualityThreshold.model_validate(
        base.model_copy(
            update={"pass_threshold_ppm": 666_667, "warning_threshold_ppm": 600_000}
        ),
        strict=True,
    )
    assert (2 * M0304_RATE_SCALE + 3 // 2) // 3 == _ROUNDED_TWO_THIRDS
    assert classify_quality_ratio(2, 3, threshold) is (
        ProteinInferenceQualityMetricStatus.WARNING
    )


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (1, 3, 333_333),
        (2, 3, 666_667),
        (1, 2, 500_000),
        (0, 1, 0),
        (1, 1, M0304_RATE_SCALE),
    ],
)
def test_metric_value_uses_exact_half_up_integer_rounding(
    numerator: int,
    denominator: int,
    expected: int,
) -> None:
    metric = ProteinInferenceQualityMetricResult(
        metric_code=ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE,
        observation_state=ProteinInferenceQualityObservationState.OBSERVED,
        status=ProteinInferenceQualityMetricStatus.PASS,
        required=True,
        numerator=numerator,
        denominator=denominator,
        value_ppm=expected,
        provenance=_provenance(),
    )
    assert metric.value_ppm == expected


def test_observed_zero_denominator_is_not_missing_or_perfect() -> None:
    metric = ProteinInferenceQualityMetricResult(
        metric_code=ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE,
        observation_state=ProteinInferenceQualityObservationState.OBSERVED,
        status=ProteinInferenceQualityMetricStatus.NOT_EVALUABLE,
        required=True,
        numerator=0,
        denominator=0,
        value_ppm=None,
        provenance=_provenance(),
    )
    assert metric.observation_state is ProteinInferenceQualityObservationState.OBSERVED
    for forged in (0, M0304_RATE_SCALE):
        payload = metric.model_dump(mode="python")
        payload["value_ppm"] = forged
        with pytest.raises(ValidationError):
            ProteinInferenceQualityMetricResult.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "state",
    [
        ProteinInferenceQualityObservationState.MISSING,
        ProteinInferenceQualityObservationState.UNSUPPORTED,
        ProteinInferenceQualityObservationState.NOT_APPLICABLE,
    ],
)
def test_no_value_states_cannot_smuggle_numeric_zero(
    state: ProteinInferenceQualityObservationState,
) -> None:
    status = (
        ProteinInferenceQualityMetricStatus.NOT_APPLICABLE
        if state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
        else ProteinInferenceQualityMetricStatus.NOT_EVALUABLE
    )
    payload = {
        "metric_code": ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY,
        "observation_state": state,
        "status": status,
        "required": True,
        "numerator": 0,
        "denominator": 0,
        "value_ppm": 0,
        "provenance": _provenance(),
    }
    with pytest.raises(ValidationError):
        ProteinInferenceQualityMetricResult.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("eligible_peptide_evidence_count", M0304_MAX_COUNT + 1),
        ("ambiguous_group_member_assignment_count", 101),
        ("discriminating_proteoform_claim_count", 21),
        ("competition_closed_group_count", 21),
        ("control_recovered_group_count", 11),
        ("context_coherent_binding_count", 11),
    ],
)
def test_count_caps_and_numerator_denominator_closures(
    canonical_scenario: Scenario,
    field: str,
    replacement: int,
) -> None:
    assert canonical_scenario.request.fact_ledger is not None
    payload = canonical_scenario.request.fact_ledger.counts.model_dump(mode="python")
    payload[field] = replacement
    with pytest.raises(ValidationError):
        ProteinInferenceQualityCounts.model_validate(payload, strict=True)


@pytest.mark.parametrize("partition", ["peptide", "detection"])
def test_count_partitions_reject_one_count_disagreement(
    canonical_scenario: Scenario,
    partition: str,
) -> None:
    assert canonical_scenario.request.fact_ledger is not None
    payload = _payload(canonical_scenario.request.fact_ledger.counts)
    if partition == "peptide":
        payload["unassigned_peptide_evidence_count"] -= 1
    else:
        payload["detection_missing_group_count"] += 1
    with pytest.raises(ValidationError, match="must partition"):
        ProteinInferenceQualityCounts.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_non_detection_fact_state_cannot_claim_censoring(
    canonical_scenario: Scenario,
) -> None:
    assert canonical_scenario.request.fact_ledger is not None
    payload = _payload(canonical_scenario.request.fact_ledger.states)
    payload["peptide_assignment"] = "censored"
    with pytest.raises(ValidationError, match="only detection support"):
        ProteinInferenceQualityFactStates.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize(
    "mutation",
    ["nonobserved_partition", "nonobserved_detection", "censored_and_missing"],
)
def test_fact_ledger_rejects_state_count_contradictions(
    canonical_scenario: Scenario,
    mutation: str,
) -> None:
    assert canonical_scenario.request.fact_ledger is not None
    payload = _payload(canonical_scenario.request.fact_ledger)
    if mutation == "nonobserved_partition":
        payload["states"]["peptide_assignment"] = "missing"
    elif mutation == "nonobserved_detection":
        payload["states"]["detection_support"] = "missing"
    else:
        payload["counts"].update(
            {
                "detection_eligible_group_count": 21,
                "detection_missing_group_count": 1,
            }
        )
    payload["ledger_digest"] = fact_ledger_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceQualityFactLedger.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "future_policy",
        "identity_binding",
        "configuration_binding",
        "missing_traversable_ledger",
        "ledger_on_policy_overflow",
    ],
)
def test_request_rejects_temporal_control_and_traversal_contradictions(
    canonical_scenario: Scenario,
    mutation: str,
) -> None:
    payload = _payload(canonical_scenario.request)
    if mutation == "future_policy":
        payload["policy"]["reviewed_at"] = "2099-01-01T00:00:00Z"
        payload["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = configuration_digest(payload["policy"])
    elif mutation == "identity_binding":
        payload["context"]["references"]["identity_lineage"]["binding_digest"] = (
            "sha256:" + ("f" * 64)
        )
    elif mutation == "configuration_binding":
        payload["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = "sha256:" + ("f" * 64)
    elif mutation == "missing_traversable_ledger":
        payload["fact_ledger"] = None
    else:
        payload["policy"]["max_sources"] = payload["raw_quality_receipt"]["source_count"] - 1
        payload["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = configuration_digest(payload["policy"])
    with pytest.raises(ValidationError):
        ComputeProteinInferenceQualityRequest.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "nonobserved_status",
        "observed_missing_numerator",
        "numerator_exceeds_denominator",
        "censored_exceeds_denominator",
        "ratio_value_disagreement",
        "censor_state_disagreement",
    ],
)
def test_metric_shape_rejects_numeric_and_state_forgery(
    canonical_result: ProteinInferenceQualityResult,
    mutation: str,
) -> None:
    payload = _payload(canonical_result.metrics[0])
    if mutation == "nonobserved_status":
        payload.update(
            {
                "observation_state": "missing",
                "status": "pass",
                "numerator": None,
                "denominator": None,
                "value_ppm": None,
            }
        )
    elif mutation == "observed_missing_numerator":
        payload["numerator"] = None
    elif mutation == "numerator_exceeds_denominator":
        payload["numerator"] = payload["denominator"] + 1
    elif mutation == "censored_exceeds_denominator":
        payload.update(
            {
                "observation_state": "censored",
                "censored_count": payload["denominator"] + 1,
            }
        )
    elif mutation == "ratio_value_disagreement":
        payload["value_ppm"] -= 1
    else:
        payload["censored_count"] = 1
    with pytest.raises(ValidationError):
        ProteinInferenceQualityMetricResult.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


@pytest.mark.parametrize("mutation", ["duplicate_reference", "closed_vocabulary"])
def test_finding_rejects_reference_and_vocabulary_forgery(mutation: str) -> None:
    finding = finding_for(
        ProteinInferenceQualityFindingCode.REQUIRED_METRIC_WARNING,
        metric_codes=(ProteinInferenceQualityMetricCode.PEPTIDE_ASSIGNMENT_COVERAGE,),
    )
    payload = _payload(finding)
    if mutation == "duplicate_reference":
        payload["metric_codes"].append(payload["metric_codes"][0])
    else:
        payload["action"] = "reject"
    with pytest.raises(ValidationError):
        ProteinInferenceQualityFinding.model_validate_json(
            canonical_json_bytes(payload), strict=True
        )


def test_detection_censor_state_and_count_are_equivalent(
    canonical_scenario: Scenario,
) -> None:
    assert canonical_scenario.request.fact_ledger is not None
    payload = _payload(canonical_scenario.request.fact_ledger)
    payload["states"]["detection_support"] = "observed"
    payload["ledger_digest"] = fact_ledger_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceQualityFactLedger.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


def test_policy_specific_shape_overflow_abstains_before_binding(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    assert request.fact_ledger is not None
    smaller_policy = request.policy.model_copy(
        update={"max_sources": request.raw_quality_receipt.source_count - 1}
    )
    candidate = ComputeProteinInferenceQualityRequest.model_construct(
        operation=request.operation,
        contract_version=request.contract_version,
        context=request.context,
        raw_quality_receipt=request.raw_quality_receipt,
        fact_ledger=None,
        policy=smaller_policy,
        supersedes_result_digest=None,
    )
    assert expected_disposition(candidate) is ProteinInferenceQualityDisposition.ABSTAINED


def test_precedence_reject_over_quarantine_over_abstain(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    findings = (
        finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_ABSTAINED),
        finding_for(ProteinInferenceQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH),
        finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_REJECTED),
    )
    assert expected_disposition(request, findings=findings) is (
        ProteinInferenceQualityDisposition.REJECTED
    )


def test_evidence_index_remains_within_locked_cap(canonical_scenario: Scenario) -> None:
    evidence = quality_evidence_index(canonical_scenario.request)
    assert len(evidence) <= M0304_MAX_EVIDENCE
    assert len(evidence) == len({item.reference.digest for item in evidence})


def test_exact_64_source_48_claim_shape_executes_totally() -> None:
    request = build_capacity_scenario_request()
    assert len(request.raw_quality_receipt.sources) == M0304_MAX_SOURCES
    assert len(request.raw_quality_receipt.claims) == M0304_MAX_LINEAGE_ARTIFACTS
    result = compute_protein_inference_quality(request)
    assert len(result.metrics) == M0304_METRIC_COUNT
    assert ProteinInferenceQualityResult.model_validate_json(
        canonical_json_bytes(result),
        strict=True,
    ) == result


def test_fact_ledger_time_accepts_upstream_equality_and_rejects_one_microsecond_before(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    assert request.fact_ledger is not None
    at_upstream = request.fact_ledger.model_copy(
        update={"recorded_at": request.raw_quality_receipt.upstream_completed_at}
    )
    at_upstream = at_upstream.model_copy(
        update={"ledger_digest": fact_ledger_digest(at_upstream)}
    )
    valid = request.model_copy(update={"fact_ledger": at_upstream})
    assert ComputeProteinInferenceQualityRequest.model_validate(valid, strict=True) == valid
    before = at_upstream.model_copy(
        update={
            "recorded_at": request.raw_quality_receipt.upstream_completed_at
            - timedelta(microseconds=1)
        }
    )
    before = before.model_copy(update={"ledger_digest": fact_ledger_digest(before)})
    with pytest.raises(ValidationError):
        ComputeProteinInferenceQualityRequest.model_validate(
            request.model_copy(update={"fact_ledger": before}),
            strict=True,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("upstream_support_status", "unsupported"),
        ("upstream_human_review_required", True),
    ],
)
def test_compact_receipt_rejects_resigned_upstream_envelope_contradiction(
    canonical_scenario: Scenario,
    field: str,
    replacement: object,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    payload[field] = replacement
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualityReceipt.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


def test_safe_failure_receipt_preserves_identity_binding(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    payload.update(
        {
            "upstream_disposition": "rejected",
            "upstream_support_status": "unsupported",
            "upstream_human_review_required": True,
            "sources": [],
            "claims": [],
        }
    )
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    safe_failure = ProteinInferenceRawQualityReceipt.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )
    forged = _payload(safe_failure)
    forged["identity_subject_digest"] = "sha256:" + ("f" * 64)
    forged["receipt_digest"] = raw_quality_receipt_digest(forged)
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualityReceipt.model_validate_json(
            canonical_json_bytes(forged),
            strict=True,
        )


@pytest.mark.parametrize("field", ["artifact_digest", "role"])
def test_compact_receipt_rejects_resigned_source_claim_binding_contradiction(
    canonical_scenario: Scenario,
    field: str,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    index = next(
        index
        for index, source in enumerate(payload["sources"])
        if source["bound_claim_id"] is not None
    )
    payload["sources"][index][field] = (
        "sha256:" + ("f" * 64) if field == "artifact_digest" else "spectra"
    )
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualityReceipt.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("identity_subject_digest",), "sha256:" + ("f" * 64)),
        (("sources", 0, "source_digest"), "sha256:" + ("f" * 64)),
        (("sources", 0, "detected_format"), "mzML"),
        (("sources", 0, "compression"), None),
        (("claims", 0, "evidence_state"), "missing"),
    ],
)
def test_compact_receipt_rejects_resigned_validated_projection_contradiction(
    canonical_scenario: Scenario,
    path: tuple[str | int, ...],
    replacement: object,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    cursor: Any = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    cursor[path[-1]] = replacement
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualityReceipt.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


@pytest.mark.parametrize("mutation", ["delete", "duplicate", "role_swap"])
def test_compact_receipt_rejects_resigned_required_role_shape_forgery(
    canonical_scenario: Scenario,
    mutation: str,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    sources = payload["sources"]
    canonical_index = next(
        index for index, item in enumerate(sources) if item["role"] == "canonical_sequences"
    )
    if mutation == "delete":
        sources.pop(canonical_index)
        payload["source_count"] -= 1
    elif mutation == "duplicate":
        duplicate = dict(sources[canonical_index])
        duplicate["source_id"] = "source.forged.duplicate"
        sources.append(duplicate)
        payload["source_count"] += 1
    else:
        sources[canonical_index]["role"] = "decoy_sequences"
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualityReceipt.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


def test_compact_receipt_accepts_multiple_exactly_bound_peptide_sources(
    canonical_scenario: Scenario,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    source = dict(next(item for item in payload["sources"] if item["role"] == "peptide_evidence"))
    claim = dict(
        next(
            item
            for item in payload["claims"]
            if item["claim_role"] == "peptide_evidence_manifest"
        )
    )
    digest = "sha256:" + ("e" * 64)
    claim.update(
        {
            "claim_id": "claim.m0304.peptide.additional",
            "artifact_digest": digest,
            "lineage_path_digest": "sha256:" + ("d" * 64),
        }
    )
    source.update(
        {
            "source_id": "source.m0304.peptide.additional",
            "bound_claim_id": claim["claim_id"],
            "artifact_digest": digest,
            "source_digest": digest,
        }
    )
    payload["sources"].append(source)
    payload["claims"].append(claim)
    payload["source_count"] += 1
    payload["lineage_artifact_count"] += 1
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    validated = ProteinInferenceRawQualityReceipt.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )
    assert (
        sum(item.role.value == "peptide_evidence" for item in validated.sources)
        == _EXPECTED_MULTIPLE_PEPTIDE_SOURCES
    )


@pytest.mark.parametrize("role", ["peptide_evidence", "ptm_vocabulary"])
def test_compact_receipt_rejects_resigned_top_level_build_binding_forgery(
    canonical_scenario: Scenario,
    role: str,
) -> None:
    payload = _payload(canonical_scenario.request.raw_quality_receipt)
    source = next(item for item in payload["sources"] if item["role"] == role)
    source["build"]["declared_build_version"] = "99.0.0"
    source["build"]["expected_build_version"] = "99.0.0"
    payload["receipt_digest"] = raw_quality_receipt_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceRawQualityReceipt.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )
