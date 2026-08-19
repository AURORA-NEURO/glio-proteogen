"""Contract and replay boundaries for M04-04 proteoform quality computation."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Literal, Never, cast

import pytest
from evals.m04_04.run import build_maximum_scenario, build_scenario_request
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m04_01 import ProteoformApplicability
from glio_proteogen.contracts.m04_03 import ProteoformRawInputRole
from glio_proteogen.contracts.m04_04 import (
    M0404_COMPUTED_METRIC_COUNT,
    M0404_MAX_CANONICAL_REQUEST_BYTES,
    M0404_MAX_CANONICAL_RESULT_BYTES,
    M0404_MAX_EVIDENCE,
    M0404_RATE_SCALE,
    ComputeProteoformQualityMetricsRequest,
    ProteoformQualityComputationReceipt,
    ProteoformQualityDisposition,
    ProteoformQualityFactLedger,
    ProteoformQualityFindingAction,
    ProteoformQualityFindingCode,
    ProteoformQualityMetric,
    ProteoformQualityMetricCode,
    ProteoformQualityMetricDirection,
    ProteoformQualityMetricStatus,
    ProteoformQualityObservationState,
    ProteoformQualityPolicy,
    ProteoformQualityResult,
    ProteoformQualityRoleCounts,
    ProteoformQualityRoleFacts,
    ProteoformQualityRoleFactStates,
    ProteoformQualityThreshold,
    canonical_request_digest,
    configuration_digest,
    contract_json_schemas,
    expected_assay_quality,
    expected_disposition,
    expected_limitations,
    expected_provenance,
    expected_quality_findings,
    expected_quality_metrics,
    expected_receipt,
    expected_support,
    expected_uncertainty,
    fact_ledger_digest,
    finding_for,
    matching_quality_profiles,
    normalized_request,
    normalized_threshold,
    opaque_proteoform_quality_identifier,
    policy_digest,
    quality_evidence_index,
    receipt_digest,
    result_payload_digest,
)
from glio_proteogen.contracts.m04_04.v1 import (
    _issue_raw_input_replay_capability,
    _RawInputReplayCapability,
    _validate_request_with_capability,
    _validate_request_with_raw_capability,
    _validate_result_with_capability,
    _ValidatedRequestCapability,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.kernel.models import SupportStatus
from glio_proteogen.modules.c04_proteoform_isoform.m04_04_quality_metrics import (
    compute_proteoform_quality_metrics,
)

_ZERO = "sha256:" + ("0" * 64)
_RequiredStateCase = tuple[
    ProteoformQualityMetricCode,
    str,
    str,
    ProteoformQualityObservationState,
    ProteoformQualityFindingCode,
]


@pytest.fixture(scope="module")
def quality_request() -> ComputeProteoformQualityMetricsRequest:
    return build_scenario_request()


@pytest.fixture(scope="module")
def result(quality_request: ComputeProteoformQualityMetricsRequest) -> ProteoformQualityResult:
    return compute_proteoform_quality_metrics(quality_request)


def _validate[ModelT: BaseModel](model: ModelT, updates: dict[str, object]) -> ModelT:
    payload = model.model_dump(mode="python", exclude_none=False)
    payload.update(updates)
    return type(model).model_validate(payload, strict=True)


def _reseal_ledger(
    ledger: ProteoformQualityFactLedger,
    *,
    facts: tuple[ProteoformQualityRoleFacts, ...] | None = None,
) -> ProteoformQualityFactLedger:
    payload = ledger.model_dump(mode="python", exclude_none=False)
    if facts is not None:
        payload["role_facts"] = facts
    payload["ledger_digest"] = _ZERO
    payload["ledger_digest"] = fact_ledger_digest(payload)
    return ProteoformQualityFactLedger.model_validate(payload, strict=True)


def _request_with_policy(
    request: ComputeProteoformQualityMetricsRequest,
    policy: ProteoformQualityPolicy,
) -> ComputeProteoformQualityMetricsRequest:
    references = request.context.references
    approved_configuration = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = request.context.model_copy(
        update={
            "references": references.model_copy(
                update={"approved_configuration": approved_configuration}
            )
        }
    )
    return _validate(request, {"policy": policy, "context": context})


def _request_with_role_fact(
    request: ComputeProteoformQualityMetricsRequest,
    fact: ProteoformQualityRoleFacts,
) -> ComputeProteoformQualityMetricsRequest:
    assert request.fact_ledger is not None
    facts = tuple(
        fact if item.role is fact.role else item for item in request.fact_ledger.role_facts
    )
    return _validate(
        request,
        {"fact_ledger": _reseal_ledger(request.fact_ledger, facts=facts)},
    )


def test_canonical_full_replay_is_exact(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    assert result.disposition.value == "qualified"
    assert len(result.assay_quality) == len(ProteoformRawInputRole)
    assert sum(len(item.metrics) for item in result.assay_quality) == M0404_COMPUTED_METRIC_COUNT
    assert result.request_digest == canonical_request_digest(quality_request)
    assert result.policy_digest == policy_digest(quality_request.policy)
    assert result.receipt == expected_receipt(
        quality_request,
        result.assay_quality,
        result.findings,
        result.disposition,
    )
    assert result.result_digest == result_payload_digest(result)
    assert ProteoformQualityResult.model_validate_json(canonical_json_bytes(result)) == result


def test_result_replay_enforces_canonical_byte_ceiling(
    result: ProteoformQualityResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid digest cannot bypass the public result resource boundary."""

    assert len(canonical_json_bytes(result)) <= M0404_MAX_CANONICAL_RESULT_BYTES
    monkeypatch.setattr(
        "glio_proteogen.contracts.m04_04.v1.M0404_MAX_CANONICAL_RESULT_BYTES",
        len(canonical_json_bytes(result)) - 1,
    )
    with pytest.raises(ValidationError, match="byte ceiling"):
        ProteoformQualityResult.model_validate_json(canonical_json_bytes(result))


def test_public_helpers_replay_every_result_region(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    profiles = matching_quality_profiles(quality_request)
    metrics = expected_quality_metrics(quality_request, profiles)
    findings = expected_quality_findings(quality_request, metrics)
    disposition = expected_disposition(quality_request, metrics, findings)
    assays = expected_assay_quality(quality_request, metrics, findings)
    receipt = expected_receipt(quality_request, assays, findings, disposition)
    assert profiles
    assert metrics == tuple(
        sorted(
            (metric for assay in result.assay_quality for metric in assay.metrics),
            key=canonical_json_bytes,
        )
    )
    assert assays == result.assay_quality
    assert findings == result.findings
    assert disposition is result.disposition
    assert receipt == result.receipt
    assert expected_support(quality_request) == result.support
    assert expected_uncertainty() == result.uncertainty
    assert expected_provenance(quality_request, metrics, receipt) == result.provenance
    assert expected_limitations() == result.limitations
    assert quality_evidence_index(quality_request) == result.evidence


def test_exact_thirteen_schema_inventory() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "policy",
        "threshold",
        "assay-profile",
        "fact-counts",
        "fact-states",
        "role-facts",
        "fact-ledger",
        "metric",
        "assay-quality",
        "finding",
        "receipt",
    )
    assert all(
        cast("str", value["$schema"]).endswith("2020-12/schema") for value in schemas.values()
    )
    metadata = cast("dict[str, object]", schemas["request"]["x-glio-contract"])
    output_metadata = cast("dict[str, object]", schemas["output"]["x-glio-contract"])
    assert metadata["maxRequestBytes"] == M0404_MAX_CANONICAL_REQUEST_BYTES
    assert output_metadata["maxResultBytes"] == M0404_MAX_CANONICAL_RESULT_BYTES
    assert metadata["rateScale"] == M0404_RATE_SCALE
    assert metadata["parentTarget"] == "protein_rna_discordance"
    assert metadata["externalContentTraversal"] is False


def test_round_half_up_occurs_before_threshold_classification(
    result: ProteoformQualityResult,
) -> None:
    metrics = [
        metric
        for assay in result.assay_quality
        for metric in assay.metrics
        if metric.metric_code is ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS
    ]
    assert all(metric.value_ppm == round((2 / 3) * M0404_RATE_SCALE) for metric in metrics)
    assert all(metric.status is ProteoformQualityMetricStatus.PASS for metric in metrics)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"parsed_record_count": 4}, "numerator"),
        ({"valid_record_count": 3}, "numerator"),
        ({"observed_feature_count": 4}, "numerator"),
        ({"reference_mapped_count": 4}, "numerator"),
        ({"control_recovered_count": 4}, "numerator"),
        ({"context_coherent_count": 4}, "numerator"),
        ({"cross_input_coherent_count": 4}, "numerator"),
        ({"above_detection_limit_count": 2}, "partition"),
    ],
)
def test_count_partitions_reject_impossible_values(
    quality_request: ComputeProteoformQualityMetricsRequest,
    updates: dict[str, object],
    message: str,
) -> None:
    assert quality_request.fact_ledger is not None
    counts = quality_request.fact_ledger.role_facts[0].counts
    with pytest.raises(ValidationError, match=message):
        _validate(counts, updates)


def test_detection_censoring_is_retained_and_exclusive(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    fact = quality_request.fact_ledger.role_facts[0]
    counts = _validate(
        fact.counts,
        {"above_detection_limit_count": 2, "below_detection_limit_count": 1},
    )
    states = _validate(
        fact.states,
        {"detection_limit_burden": ProteoformQualityObservationState.CENSORED},
    )
    censored = _validate(fact, {"counts": counts, "states": states})
    assert isinstance(censored, ProteoformQualityRoleFacts)
    with pytest.raises(ValidationError, match="only detection"):
        _validate(
            fact,
            {
                "states": _validate(
                    fact.states,
                    {"raw_input_completeness": ProteoformQualityObservationState.CENSORED},
                )
            },
        )
    with pytest.raises(ValidationError, match="exactly retain"):
        _validate(fact, {"counts": counts})


def test_nonobserved_partitions_must_be_zero(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    fact = quality_request.fact_ledger.role_facts[0]
    for state in (
        ProteoformQualityObservationState.MISSING,
        ProteoformQualityObservationState.INDETERMINATE,
        ProteoformQualityObservationState.UNSUPPORTED,
        ProteoformQualityObservationState.NOT_APPLICABLE,
    ):
        with pytest.raises(ValidationError, match="zero count"):
            _validate(
                fact,
                {"states": _validate(fact.states, {"valid_record_coverage": state})},
            )


def test_threshold_direction_and_warning_order_are_closed(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    threshold = quality_request.policy.profiles[0].thresholds[0]
    wrong_direction = (
        ProteoformQualityMetricDirection.AT_MOST
        if threshold.direction is ProteoformQualityMetricDirection.AT_LEAST
        else ProteoformQualityMetricDirection.AT_LEAST
    )
    with pytest.raises(ValidationError, match="direction"):
        _validate(threshold, {"direction": wrong_direction})
    with pytest.raises(ValidationError, match="warning"):
        ProteoformQualityThreshold(
            metric_code=ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS,
            direction=ProteoformQualityMetricDirection.AT_LEAST,
            pass_threshold_ppm=500_000,
            warning_threshold_ppm=500_001,
            required=True,
        )
    at_most = ProteoformQualityThreshold(
        metric_code=ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN,
        direction=ProteoformQualityMetricDirection.AT_MOST,
        pass_threshold_ppm=100_000,
        warning_threshold_ppm=200_000,
        required=True,
    )
    assert at_most.warning_threshold_ppm > at_most.pass_threshold_ppm


def test_profile_requires_exact_metrics_and_role_applicability(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    proteome = next(
        item
        for item in quality_request.policy.profiles
        if item.role is ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
    )
    genome = next(
        item
        for item in quality_request.policy.profiles
        if item.role is ProteoformRawInputRole.GENOME
    )
    with pytest.raises(ValidationError, match="every metric"):
        _validate(proteome, {"thresholds": (*proteome.thresholds[:-1], proteome.thresholds[0])})
    with pytest.raises(ValidationError, match="required only"):
        _validate(proteome, {"applicability": None})
    with pytest.raises(ValidationError, match="required only"):
        _validate(genome, {"applicability": proteome.applicability})


def test_policy_rejects_overlapping_match_domains(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    duplicate = quality_request.policy.profiles[0].model_copy(
        update={"profile_id": "profile." + ("f" * 64), "version": "2.0.0"}
    )
    with pytest.raises(ValidationError, match="disjoint"):
        _validate(
            quality_request.policy,
            {"profiles": (*quality_request.policy.profiles, duplicate)},
        )


@pytest.mark.parametrize(
    ("profile_field", "finding_code"),
    [
        (
            "approved_assay_protocol_versions",
            ProteoformQualityFindingCode.ASSAY_PROTOCOL_VERSION_MISMATCH,
        ),
        (
            "approved_specimen_processing_versions",
            ProteoformQualityFindingCode.SPECIMEN_PROCESSING_VERSION_MISMATCH,
        ),
        (
            "approved_unit_definition_versions",
            ProteoformQualityFindingCode.UNIT_DEFINITION_VERSION_MISMATCH,
        ),
    ],
)
def test_public_version_mismatch_matrix_is_exact(
    quality_request: ComputeProteoformQualityMetricsRequest,
    profile_field: str,
    finding_code: ProteoformQualityFindingCode,
) -> None:
    profile = quality_request.policy.profiles[0]
    replacement = _validate(profile, {profile_field: ("9.9.9",)})
    policy = _validate(
        quality_request.policy,
        {
            "profiles": tuple(
                replacement if item.profile_id == profile.profile_id else item
                for item in quality_request.policy.profiles
            )
        },
    )
    candidate = _request_with_policy(quality_request, policy)

    assert matching_quality_profiles(candidate) == ()
    assert expected_quality_metrics(candidate) == ()
    findings = expected_quality_findings(candidate)
    assert tuple((item.code, item.action, item.roles) for item in findings) == (
        (finding_code, ProteoformQualityFindingAction.QUARANTINE, (profile.role,)),
    )
    assert expected_disposition(candidate, (), findings) is ProteoformQualityDisposition.QUARANTINED

    computed = compute_proteoform_quality_metrics(candidate)
    assert computed.assay_quality == ()
    assert computed.findings == findings
    assert computed.disposition is ProteoformQualityDisposition.QUARANTINED


@pytest.mark.parametrize("domain", ["controls", "applicability"])
def test_public_unmatched_profile_domain_abstains(
    quality_request: ComputeProteoformQualityMetricsRequest,
    domain: str,
) -> None:
    if domain == "controls":
        profile = next(
            item
            for item in quality_request.policy.profiles
            if item.role is ProteoformRawInputRole.GENOME
        )
        replacement = _validate(
            profile,
            {"controls_applicable": not profile.controls_applicable},
        )
    else:
        profile = next(
            item
            for item in quality_request.policy.profiles
            if item.role is ProteoformRawInputRole.MASS_SPECTROMETRY_PROTEOME
        )
        replacement = _validate(
            profile,
            {"applicability": ProteoformApplicability.TOP_DOWN},
        )
    policy = _validate(
        quality_request.policy,
        {
            "profiles": tuple(
                replacement if item.profile_id == profile.profile_id else item
                for item in quality_request.policy.profiles
            )
        },
    )
    candidate = _request_with_policy(quality_request, policy)

    assert matching_quality_profiles(candidate) == ()
    assert expected_quality_metrics(candidate) == ()
    findings = expected_quality_findings(candidate)
    assert tuple((item.code, item.action, item.roles) for item in findings) == (
        (
            ProteoformQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED,
            ProteoformQualityFindingAction.ABSTAIN,
            (),
        ),
    )
    assert expected_disposition(candidate, (), findings) is ProteoformQualityDisposition.ABSTAINED

    computed = compute_proteoform_quality_metrics(candidate)
    assert computed.assay_quality == ()
    assert computed.findings == findings
    assert computed.disposition is ProteoformQualityDisposition.ABSTAINED


def test_ledger_self_digest_and_role_shape_are_structural(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    ledger = quality_request.fact_ledger
    with pytest.raises(ValidationError, match="digest"):
        _validate(ledger, {"ledger_digest": sha256_digest("forged")})
    with pytest.raises(ValidationError, match="final"):
        _validate(ledger, {"ledger_digest": _ZERO})
    with pytest.raises(ValidationError, match="every role"):
        _reseal_ledger(ledger, facts=(*ledger.role_facts[:-1], ledger.role_facts[0]))


def test_semantic_fact_binding_mismatch_quarantines_without_metrics(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    first = quality_request.fact_ledger.role_facts[0]
    forged = first.model_copy(update={"document_digest": sha256_digest("stale-document")})
    ledger = _reseal_ledger(
        quality_request.fact_ledger,
        facts=(forged, *quality_request.fact_ledger.role_facts[1:]),
    )
    candidate = ComputeProteoformQualityMetricsRequest.model_validate(
        {
            **quality_request.model_dump(mode="python", exclude_none=False),
            "fact_ledger": ledger,
        },
        strict=True,
    )
    assert matching_quality_profiles(candidate) == ()
    assert expected_quality_metrics(candidate) == ()
    findings = expected_quality_findings(candidate)
    assert tuple(item.code for item in findings) == (
        ProteoformQualityFindingCode.FACT_LEDGER_BINDING_MISMATCH,
    )
    assert expected_disposition(candidate, (), findings).value == "quarantined"


def test_policy_count_ceiling_is_enforced_by_request(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    policy = _validate(quality_request.policy, {"max_count": 2})
    with pytest.raises(ValidationError, match="policy maximum"):
        ComputeProteoformQualityMetricsRequest.model_validate(
            {
                **quality_request.model_dump(mode="python", exclude_none=False),
                "policy": policy,
            },
            strict=True,
        )


def test_evidence_identity_conflict_rejects_request(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    profile = quality_request.policy.profiles[0]
    conflicting = profile.evidence.model_copy(
        update={"artifact_id": quality_request.context.references.provenance.evidence.artifact_id}
    )
    altered_profile = _validate(profile, {"evidence": conflicting})
    profiles = (altered_profile, *quality_request.policy.profiles[1:])
    policy = _validate(quality_request.policy, {"profiles": profiles})
    refs = quality_request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = quality_request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )
    with pytest.raises(ValidationError, match="conflicting content"):
        ComputeProteoformQualityMetricsRequest.model_validate(
            {
                **quality_request.model_dump(mode="python", exclude_none=False),
                "context": context,
                "policy": policy,
            },
            strict=True,
        )


def test_standalone_policy_and_ledger_reject_internal_evidence_conflicts(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    profile = quality_request.policy.profiles[0]
    conflicting_profile = profile.model_copy(
        update={
            "evidence": profile.evidence.model_copy(
                update={"artifact_id": quality_request.policy.evidence.artifact_id}
            )
        }
    )
    with pytest.raises(ValidationError, match="conflicting content"):
        _validate(
            quality_request.policy,
            {"profiles": (conflicting_profile, *quality_request.policy.profiles[1:])},
        )
    assert quality_request.fact_ledger is not None
    fact = quality_request.fact_ledger.role_facts[0]
    conflicting_fact = fact.model_copy(
        update={
            "evidence": fact.evidence.model_copy(
                update={"artifact_id": quality_request.fact_ledger.evidence.artifact_id}
            )
        }
    )
    payload = quality_request.fact_ledger.model_dump(mode="python", exclude_none=False)
    payload["role_facts"] = (conflicting_fact, *quality_request.fact_ledger.role_facts[1:])
    payload["ledger_digest"] = fact_ledger_digest(payload)
    with pytest.raises(ValidationError, match="conflicting content"):
        ProteoformQualityFactLedger.model_validate(payload, strict=True)


def test_standalone_metric_censoring_closes_code_and_count(
    result: ProteoformQualityResult,
) -> None:
    metric = result.assay_quality[0].metrics[0]
    with pytest.raises(ValidationError, match="positive censored count"):
        _validate(metric, {"censored_count": 1})
    with pytest.raises(ValidationError, match="only detection"):
        _validate(
            metric,
            {
                "observation_state": ProteoformQualityObservationState.CENSORED,
                "censored_count": 1,
            },
        )
    detection = next(
        item
        for item in result.assay_quality[0].metrics
        if item.metric_code is ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN
    )
    with pytest.raises(ValidationError, match="exact numerator"):
        _validate(
            detection,
            {
                "observation_state": ProteoformQualityObservationState.CENSORED,
                "censored_count": 1,
            },
        )


def test_finding_action_id_and_assay_disposition_are_closed(
    result: ProteoformQualityResult,
) -> None:
    finding = finding_for(
        ProteoformQualityFindingCode.OPTIONAL_METRIC_WARNING,
        roles=(ProteoformRawInputRole.GENOME,),
        metric_codes=(ProteoformQualityMetricCode.VALID_RECORD_COVERAGE,),
    )
    assert finding.action is ProteoformQualityFindingAction.RECORD
    with pytest.raises(ValidationError, match="closed vocabulary"):
        _validate(finding, {"action": ProteoformQualityFindingAction.QUARANTINE})
    assay = result.assay_quality[0]
    with pytest.raises(ValidationError, match="disposition"):
        _validate(assay, {"disposition": ProteoformQualityDisposition.ABSTAINED})


def test_receipt_regions_have_equal_reachable_shapes(result: ProteoformQualityResult) -> None:
    receipt = result.receipt
    with pytest.raises(ValidationError, match="digest"):
        _validate(receipt, {"receipt_digest": sha256_digest("forged-receipt-digest")})
    payload = receipt.model_dump(mode="python", exclude_none=False)
    payload["assay_quality_digests"] = ()
    payload["receipt_digest"] = _ZERO
    payload["receipt_digest"] = receipt_digest(payload)
    with pytest.raises(ValidationError, match="equal lengths"):
        ProteoformQualityComputationReceipt.model_validate(payload, strict=True)


def test_receipt_and_assay_collection_uniqueness_and_closed_shapes(
    result: ProteoformQualityResult,
) -> None:
    assay = result.assay_quality[0]
    warning = ProteoformQualityFindingCode.OPTIONAL_METRIC_WARNING
    with pytest.raises(ValidationError, match="unique"):
        _validate(assay, {"finding_codes": (warning, warning)})

    receipt = result.receipt
    duplicate_profile = receipt.selected_profile_digests[0]
    with pytest.raises(ValidationError, match="unique"):
        _validate(
            receipt,
            {"selected_profile_digests": (duplicate_profile,) * 4},
        )

    missing_ledger = receipt.model_dump(mode="python", exclude_none=False)
    missing_ledger["fact_ledger_digest"] = None
    missing_ledger["receipt_digest"] = _ZERO
    missing_ledger["receipt_digest"] = receipt_digest(missing_ledger)
    with pytest.raises(ValidationError, match="zero or four"):
        ProteoformQualityComputationReceipt.model_validate(missing_ledger, strict=True)

    contradicted = receipt.model_dump(mode="python", exclude_none=False)
    contradicted["disposition"] = ProteoformQualityDisposition.ABSTAINED
    contradicted["receipt_digest"] = _ZERO
    contradicted["receipt_digest"] = receipt_digest(contradicted)
    with pytest.raises(ValidationError, match="disposition"):
        ProteoformQualityComputationReceipt.model_validate(contradicted, strict=True)


@pytest.mark.parametrize(
    "region",
    ["request_digest", "policy_digest", "configuration_digest", "receipt_digest"],
)
def test_result_envelope_digest_regions_cannot_be_resigned(
    result: ProteoformQualityResult,
    region: str,
) -> None:
    payload = result.model_dump(mode="python", exclude_none=False)
    payload[region] = sha256_digest({"forged": region})
    payload["result_digest"] = _ZERO
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match="does not replay"):
        ProteoformQualityResult.model_validate(payload, strict=True)


def test_result_metric_and_finding_forgery_rejects(result: ProteoformQualityResult) -> None:
    payload = result.model_dump(mode="python", exclude_none=False)
    assay = deepcopy(payload["assay_quality"][0])
    assay["metrics"][0]["required"] = False
    payload["assay_quality"] = (assay, *payload["assay_quality"][1:])
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        ProteoformQualityResult.model_validate(payload, strict=True)
    forged = result.model_dump(mode="python", exclude_none=False)
    forged["findings"] = (finding_for(ProteoformQualityFindingCode.OPTIONAL_METRIC_WARNING),)
    forged["result_digest"] = result_payload_digest(forged)
    with pytest.raises(ValidationError, match="does not replay"):
        ProteoformQualityResult.model_validate(forged, strict=True)


def test_maximum_shape_reaches_exact_evidence_ceiling() -> None:
    maximum = build_maximum_scenario().request
    assert len(maximum.policy.profiles) == M0404_COMPUTED_METRIC_COUNT
    assert sum(len(item.thresholds) for item in maximum.policy.profiles) == (
        M0404_COMPUTED_METRIC_COUNT * len(ProteoformQualityMetricCode)
    )
    assert len(quality_evidence_index(maximum)) == M0404_MAX_EVIDENCE


def test_models_are_strict_frozen_and_unknown_fields_reject(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    with pytest.raises(ValidationError):
        ProteoformQualityRoleCounts.model_validate(
            {
                **quality_request.fact_ledger.role_facts[0].counts.model_dump(),  # type: ignore[union-attr]
                "unknown": 1,
            },
            strict=True,
        )
    with pytest.raises(ValidationError):
        ProteoformQualityRoleFactStates.model_validate(
            {
                **quality_request.fact_ledger.role_facts[0].states.model_dump(),  # type: ignore[union-attr]
                "raw_input_completeness": 1,
            },
            strict=True,
        )
    with pytest.raises(ValidationError):
        ProteoformQualityMetric.model_validate(
            {
                **compute_proteoform_quality_metrics(quality_request)
                .assay_quality[0]
                .metrics[0]
                .model_dump(),
                "required": 1,
            },
            strict=True,
        )


def test_optional_warning_support_is_limited(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    profile = quality_request.policy.profiles[0]
    threshold = next(
        item
        for item in profile.thresholds
        if item.metric_code is ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS
    )
    warning = _validate(
        threshold,
        {
            "pass_threshold_ppm": 700_000,
            "warning_threshold_ppm": 600_000,
            "required": False,
        },
    )
    thresholds = tuple(
        warning if item.metric_code is warning.metric_code else item for item in profile.thresholds
    )
    replacement = _validate(profile, {"thresholds": thresholds})
    profiles = tuple(
        replacement if item.profile_id == replacement.profile_id else item
        for item in quality_request.policy.profiles
    )
    policy = _validate(quality_request.policy, {"profiles": profiles})
    refs = quality_request.context.references
    approved = refs.approved_configuration.model_copy(
        update={
            "evidence": refs.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(policy)}
            )
        }
    )
    context = quality_request.context.model_copy(
        update={"references": refs.model_copy(update={"approved_configuration": approved})}
    )
    candidate = _validate(quality_request, {"policy": policy, "context": context})
    support = expected_support(candidate)
    assert support.status is SupportStatus.LIMITED
    assert support.reason_code == "proteoform_quality_qualified_with_optional_warning"


@pytest.mark.parametrize("requirement", ["required", "optional"])
def test_at_least_threshold_failure_quarantines(
    quality_request: ComputeProteoformQualityMetricsRequest,
    requirement: Literal["required", "optional"],
) -> None:
    required = requirement == "required"
    profile = quality_request.policy.profiles[0]
    threshold = next(
        item
        for item in profile.thresholds
        if item.metric_code is ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS
    )
    assert threshold.direction is ProteoformQualityMetricDirection.AT_LEAST
    failed = _validate(
        threshold,
        {
            "pass_threshold_ppm": 900_000,
            "warning_threshold_ppm": 800_000,
            "required": required,
        },
    )
    replacement = _validate(
        profile,
        {
            "thresholds": tuple(
                failed if item.metric_code is failed.metric_code else item
                for item in profile.thresholds
            )
        },
    )
    policy = _validate(
        quality_request.policy,
        {
            "profiles": tuple(
                replacement if item.profile_id == profile.profile_id else item
                for item in quality_request.policy.profiles
            )
        },
    )
    candidate = _request_with_policy(quality_request, policy)

    metrics = expected_quality_metrics(candidate)
    metric = next(
        item
        for item in metrics
        if item.role is profile.role
        and item.metric_code is ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS
    )
    assert metric.status is ProteoformQualityMetricStatus.FAIL
    assert metric.required is required
    findings = expected_quality_findings(candidate, metrics)
    assert tuple((item.code, item.action, item.roles, item.metric_codes) for item in findings) == (
        (
            ProteoformQualityFindingCode.METRIC_THRESHOLD_FAILED,
            ProteoformQualityFindingAction.QUARANTINE,
            (profile.role,),
            (ProteoformQualityMetricCode.RAW_INPUT_COMPLETENESS,),
        ),
    )
    assert (
        expected_disposition(candidate, metrics, findings)
        is ProteoformQualityDisposition.QUARANTINED
    )
    assert compute_proteoform_quality_metrics(candidate).disposition is (
        ProteoformQualityDisposition.QUARANTINED
    )


def test_at_most_threshold_failure_retains_censoring_and_quarantines(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    fact = quality_request.fact_ledger.role_facts[0]
    counts = _validate(
        fact.counts,
        {
            "above_detection_limit_count": 0,
            "below_detection_limit_count": fact.counts.detection_eligible_count,
        },
    )
    states = _validate(
        fact.states,
        {"detection_limit_burden": ProteoformQualityObservationState.CENSORED},
    )
    candidate = _request_with_role_fact(
        quality_request,
        _validate(fact, {"counts": counts, "states": states}),
    )

    metrics = expected_quality_metrics(candidate)
    metric = next(
        item
        for item in metrics
        if item.role is fact.role
        and item.metric_code is ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN
    )
    assert metric.observation_state is ProteoformQualityObservationState.CENSORED
    assert metric.status is ProteoformQualityMetricStatus.FAIL
    assert metric.value_ppm == M0404_RATE_SCALE
    assert metric.censored_count == fact.counts.detection_eligible_count
    findings = expected_quality_findings(candidate, metrics)
    assert tuple((item.code, item.action, item.roles, item.metric_codes) for item in findings) == (
        (
            ProteoformQualityFindingCode.METRIC_THRESHOLD_FAILED,
            ProteoformQualityFindingAction.QUARANTINE,
            (fact.role,),
            (ProteoformQualityMetricCode.DETECTION_LIMIT_BURDEN,),
        ),
    )
    assert (
        expected_disposition(candidate, metrics, findings)
        is ProteoformQualityDisposition.QUARANTINED
    )
    assert compute_proteoform_quality_metrics(candidate).disposition is (
        ProteoformQualityDisposition.QUARANTINED
    )


def test_cross_metric_inconsistency_quarantines_without_clipping(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    fact = quality_request.fact_ledger.role_facts[0]
    observed_feature_count = fact.counts.reference_eligible_count - 1
    counts = _validate(
        fact.counts,
        {"observed_feature_count": observed_feature_count},
    )
    candidate = _request_with_role_fact(
        quality_request,
        _validate(fact, {"counts": counts}),
    )

    metrics = expected_quality_metrics(candidate)
    assay_coverage = next(
        item
        for item in metrics
        if item.role is fact.role
        and item.metric_code is ProteoformQualityMetricCode.ASSAY_FEATURE_COVERAGE
    )
    assert assay_coverage.numerator == observed_feature_count
    assert assay_coverage.denominator == fact.counts.expected_feature_count
    assert assay_coverage.status is ProteoformQualityMetricStatus.PASS
    findings = expected_quality_findings(candidate, metrics)
    assert tuple((item.code, item.action, item.roles) for item in findings) == (
        (
            ProteoformQualityFindingCode.CROSS_METRIC_INCONSISTENCY,
            ProteoformQualityFindingAction.QUARANTINE,
            (fact.role,),
        ),
    )
    assert (
        expected_disposition(candidate, metrics, findings)
        is ProteoformQualityDisposition.QUARANTINED
    )
    computed = compute_proteoform_quality_metrics(candidate)
    assert len(computed.assay_quality) == len(ProteoformRawInputRole)
    assert computed.findings == findings
    assert computed.disposition is ProteoformQualityDisposition.QUARANTINED


@pytest.mark.parametrize(
    "case",
    [
        (
            ProteoformQualityMetricCode.SAMPLE_CONTEXT_BINDING_COHERENCE,
            "context_coherent_count",
            "context_applicable_count",
            ProteoformQualityObservationState.MISSING,
            ProteoformQualityFindingCode.REQUIRED_METRIC_MISSING,
        ),
        (
            ProteoformQualityMetricCode.CROSS_INPUT_CONSISTENCY,
            "cross_input_coherent_count",
            "cross_input_applicable_count",
            ProteoformQualityObservationState.UNSUPPORTED,
            ProteoformQualityFindingCode.REQUIRED_METRIC_UNSUPPORTED,
        ),
    ],
)
def test_required_missing_and_unsupported_metrics_abstain(
    quality_request: ComputeProteoformQualityMetricsRequest,
    case: _RequiredStateCase,
) -> None:
    metric_code, numerator_field, denominator_field, state, finding_code = case
    assert quality_request.fact_ledger is not None
    fact = quality_request.fact_ledger.role_facts[0]
    counts = _validate(
        fact.counts,
        {numerator_field: 0, denominator_field: 0},
    )
    states = _validate(fact.states, {metric_code.value: state})
    candidate = _request_with_role_fact(
        quality_request,
        _validate(fact, {"counts": counts, "states": states}),
    )

    metrics = expected_quality_metrics(candidate)
    metric = next(
        item for item in metrics if item.role is fact.role and item.metric_code is metric_code
    )
    assert metric.observation_state is state
    assert metric.status is ProteoformQualityMetricStatus.NOT_EVALUABLE
    assert metric.required is True
    assert metric.numerator is None
    assert metric.denominator is None
    assert metric.value_ppm is None
    findings = expected_quality_findings(candidate, metrics)
    assert tuple((item.code, item.action, item.roles, item.metric_codes) for item in findings) == (
        (
            finding_code,
            ProteoformQualityFindingAction.ABSTAIN,
            (fact.role,),
            (metric_code,),
        ),
    )
    assert (
        expected_disposition(candidate, metrics, findings) is ProteoformQualityDisposition.ABSTAINED
    )
    computed = compute_proteoform_quality_metrics(candidate)
    assert computed.findings == findings
    assert computed.disposition is ProteoformQualityDisposition.ABSTAINED


def test_nonunique_public_profile_selection_abstains(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    profile = quality_request.policy.profiles[0]
    duplicate = profile.model_copy(
        update={"profile_id": "profile." + ("d" * 64), "version": "9.9.9"}
    )
    policy = quality_request.policy.model_copy(
        update={"profiles": (*quality_request.policy.profiles, duplicate)}
    )
    candidate = quality_request.model_copy(update={"policy": policy})

    assert matching_quality_profiles(candidate) == ()
    assert expected_quality_metrics(candidate) == ()
    findings = expected_quality_findings(candidate)
    assert tuple((item.code, item.action) for item in findings) == (
        (
            ProteoformQualityFindingCode.ASSAY_PROFILE_UNSUPPORTED,
            ProteoformQualityFindingAction.ABSTAIN,
        ),
    )
    assert expected_disposition(candidate, (), findings) is ProteoformQualityDisposition.ABSTAINED


def test_expected_receipt_rejects_disposition_contradiction(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    assert result.disposition is ProteoformQualityDisposition.QUALIFIED
    with pytest.raises(ValueError, match="disposition does not match exact precedence"):
        expected_receipt(
            quality_request,
            result.assay_quality,
            result.findings,
            ProteoformQualityDisposition.QUARANTINED,
        )


def test_owned_media_types_and_version_sets_reject(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    profile = quality_request.policy.profiles[0]
    with pytest.raises(ValidationError, match="media type"):
        _validate(
            profile,
            {"evidence": profile.evidence.model_copy(update={"media_type": "application/json"})},
        )
    version = profile.approved_assay_protocol_versions[0]
    with pytest.raises(ValidationError, match="unique"):
        _validate(profile, {"approved_assay_protocol_versions": (version, version)})


def test_policy_identity_and_role_coverage_reject(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    profiles = quality_request.policy.profiles
    duplicate = profiles[1].model_copy(
        update={"profile_id": profiles[0].profile_id, "version": profiles[0].version}
    )
    with pytest.raises(ValidationError, match="identities"):
        _validate(quality_request.policy, {"profiles": (profiles[0], duplicate, *profiles[2:])})
    same_role = profiles[0].model_copy(update={"profile_id": "profile." + ("a" * 64)})
    with pytest.raises(ValidationError, match="all four roles"):
        _validate(quality_request.policy, {"profiles": (profiles[0], same_role, *profiles[2:])})


def test_request_identifier_and_chronology_close(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    assert quality_request.fact_ledger is not None
    with pytest.raises(ValueError, match="opaque local namespace"):
        opaque_proteoform_quality_identifier("policy", "profile." + ("f" * 64))
    with pytest.raises(ValidationError, match="request identifier"):
        _validate(quality_request, {"request_id": "request." + ("f" * 64)})
    with pytest.raises(ValidationError, match="policy cannot postdate"):
        _validate(
            quality_request,
            {
                "policy": quality_request.policy.model_copy(
                    update={
                        "reviewed_at": quality_request.context.occurred_at + timedelta(seconds=1)
                    }
                )
            },
        )
    early_payload = quality_request.fact_ledger.model_dump(mode="python", exclude_none=False)
    early_payload["recorded_at"] = quality_request.raw_input_result.completed_at - timedelta(
        seconds=1
    )
    early_payload["ledger_digest"] = _ZERO
    early_payload["ledger_digest"] = fact_ledger_digest(early_payload)
    early = ProteoformQualityFactLedger.model_validate(early_payload, strict=True)
    with pytest.raises(ValidationError, match="chronology"):
        _validate(quality_request, {"fact_ledger": early})


@pytest.mark.parametrize(
    "state",
    [
        ProteoformQualityObservationState.MISSING,
        ProteoformQualityObservationState.INDETERMINATE,
        ProteoformQualityObservationState.UNSUPPORTED,
        ProteoformQualityObservationState.NOT_APPLICABLE,
    ],
)
def test_standalone_nonobserved_metric_shape(
    result: ProteoformQualityResult,
    state: ProteoformQualityObservationState,
) -> None:
    metric = result.assay_quality[0].metrics[0]
    expected_status = (
        ProteoformQualityMetricStatus.NOT_APPLICABLE
        if state is ProteoformQualityObservationState.NOT_APPLICABLE
        else ProteoformQualityMetricStatus.NOT_EVALUABLE
    )
    candidate = _validate(
        metric,
        {
            "observation_state": state,
            "status": expected_status,
            "numerator": None,
            "denominator": None,
            "value_ppm": None,
            "censored_count": 0,
        },
    )
    assert candidate.status is expected_status
    with pytest.raises(ValidationError, match="cannot carry"):
        _validate(candidate, {"numerator": 0})


def test_standalone_metric_ratio_failures(result: ProteoformQualityResult) -> None:
    metric = result.assay_quality[0].metrics[0]
    with pytest.raises(ValidationError, match="require numerator"):
        _validate(metric, {"numerator": None})
    with pytest.raises(ValidationError, match="not evaluable"):
        _validate(metric, {"numerator": 0, "denominator": 0, "value_ppm": 0})
    with pytest.raises(ValidationError, match="round-half-up"):
        _validate(metric, {"value_ppm": 1})
    with pytest.raises(ValidationError, match="cannot exceed"):
        _validate(
            metric,
            {"numerator": 3, "denominator": 2, "value_ppm": M0404_RATE_SCALE},
        )


def test_finding_and_assay_reference_uniqueness(result: ProteoformQualityResult) -> None:
    finding = finding_for(
        ProteoformQualityFindingCode.CROSS_METRIC_INCONSISTENCY,
        roles=(ProteoformRawInputRole.GENOME,),
    )
    with pytest.raises(ValidationError, match="unique"):
        _validate(finding, {"roles": (ProteoformRawInputRole.GENOME,) * 2})
    assay = result.assay_quality[0]
    with pytest.raises(ValidationError, match="all eight"):
        _validate(assay, {"metrics": (*assay.metrics[:-1], assay.metrics[0])})
    wrong_role = (
        ProteoformRawInputRole.GENOME
        if assay.role is not ProteoformRawInputRole.GENOME
        else ProteoformRawInputRole.TRANSCRIPTOME
    )
    with pytest.raises(ValidationError, match="one exact role"):
        _validate(
            assay,
            {
                "metrics": (
                    assay.metrics[0].model_copy(update={"role": wrong_role}),
                    *assay.metrics[1:],
                )
            },
        )


@pytest.mark.parametrize(
    ("case_id", "status", "reason"),
    [
        (
            "quarantined_upstream_zero_ledger_traversal",
            SupportStatus.REVIEW_REQUIRED,
            "quarantined",
        ),
        (
            "abstained_upstream_zero_ledger_traversal",
            SupportStatus.UNSUPPORTED,
            "abstained",
        ),
    ],
)
def test_nonqualified_support_is_explicit(
    case_id: str,
    status: SupportStatus,
    reason: str,
) -> None:
    support = expected_support(build_scenario_request(case_id))
    assert support.status is status
    assert reason in support.reason_code


def test_provenance_optional_regions_are_bound(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    supersedes = sha256_digest("superseded")
    candidate = quality_request.model_copy(update={"supersedes_result_digest": supersedes})
    assert supersedes in expected_provenance(candidate).input_digests
    assert (
        result.receipt.receipt_digest
        in expected_provenance(quality_request, (), result.receipt).input_digests
    )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("completed_at", "completion time"),
        ("support", "support"),
        ("uncertainty", "uncertainty"),
        ("provenance", "provenance"),
        ("evidence", "evidence index"),
        ("limitations", "limitations"),
        ("human_review_required", "review flag"),
        ("result_digest", "result digest"),
    ],
)
def test_result_every_replayed_region_rejects_forgery(
    result: ProteoformQualityResult,
    field: str,
    message: str,
) -> None:
    payload = result.model_dump(mode="python", exclude_none=False)
    mutations: dict[str, object] = {
        "completed_at": result.completed_at + timedelta(seconds=1),
        "support": result.support.model_copy(update={"rationale": "Forged support."}),
        "uncertainty": result.uncertainty.model_copy(update={"sensitivity_notes": ("Forged.",)}),
        "provenance": result.provenance.model_copy(
            update={
                "input_digests": (
                    *result.provenance.input_digests,
                    sha256_digest("forged"),
                )
            }
        ),
        "evidence": result.evidence[:-1],
        "limitations": (*result.limitations[:-1], result.limitations[0]),
        "human_review_required": True,
        "result_digest": sha256_digest("forged-result"),
    }
    payload[field] = mutations[field]
    if field != "result_digest":
        payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError, match=message):
        ProteoformQualityResult.model_validate(payload, strict=True)


def test_private_capability_is_candidate_bound(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    cap = _issue_raw_input_replay_capability(quality_request)
    altered = quality_request.model_copy(
        update={
            "raw_input_result": quality_request.raw_input_result.model_copy(
                update={"result_digest": sha256_digest("forged-upstream")}
            )
        }
    )
    with pytest.raises(TypeError, match="mismatched"):
        _validate_request_with_raw_capability(altered, cap)


def test_private_capabilities_require_exact_issued_identity_and_cached_digests(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    raw_cap = _issue_raw_input_replay_capability(quality_request)
    forged_raw_cap = _RawInputReplayCapability(
        seal=raw_cap.seal,
        source_bytes=raw_cap.source_bytes,
        normalized_bytes=raw_cap.normalized_bytes,
        result=raw_cap.result,
    )
    with pytest.raises(TypeError, match="mismatched"):
        _validate_request_with_raw_capability(quality_request, forged_raw_cap)

    request_cap = _validate_request_with_capability(quality_request)
    exact_payload = result.model_copy(update={"request": request_cap.request})
    assert _validate_result_with_capability(exact_payload, request_cap) == exact_payload

    forged_request_cap = _ValidatedRequestCapability(
        seal=request_cap.seal,
        request=request_cap.request,
        request_digest=sha256_digest("forged-request-capability-digest"),
        policy_digest=request_cap.policy_digest,
        configuration_digest=request_cap.configuration_digest,
    )
    with pytest.raises(TypeError, match="invalid"):
        _validate_result_with_capability(exact_payload, forged_request_cap)


def test_public_expected_helpers_reject_forged_derived_overrides(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    profiles = matching_quality_profiles(quality_request)
    forged_profile = profiles[0].model_copy(update={"profile_id": "profile." + ("f" * 64)})
    with pytest.raises(ValueError, match="profiles"):
        expected_quality_metrics(quality_request, (forged_profile, *profiles[1:]))

    metrics = expected_quality_metrics(quality_request)
    forged_metric = metrics[0].model_copy(update={"status": ProteoformQualityMetricStatus.WARNING})
    forged_metrics = (forged_metric, *metrics[1:])
    with pytest.raises(ValueError, match="metrics"):
        expected_quality_findings(quality_request, forged_metrics)
    with pytest.raises(ValueError, match="metrics"):
        expected_disposition(quality_request, forged_metrics, result.findings)
    with pytest.raises(ValueError, match="metrics"):
        expected_assay_quality(quality_request, forged_metrics, result.findings)
    with pytest.raises(ValueError, match="metrics"):
        expected_provenance(quality_request, forged_metrics, result.receipt)

    forged_finding = finding_for(
        ProteoformQualityFindingCode.OPTIONAL_METRIC_WARNING,
        roles=(metrics[0].role,),
        metric_codes=(metrics[0].metric_code,),
    )
    forged_findings = (forged_finding,)
    with pytest.raises(ValueError, match="findings"):
        expected_disposition(quality_request, metrics, forged_findings)
    with pytest.raises(ValueError, match="findings"):
        expected_assay_quality(quality_request, metrics, forged_findings)
    with pytest.raises(ValueError, match="findings"):
        expected_receipt(
            quality_request,
            result.assay_quality,
            forged_findings,
            result.disposition,
        )

    forged_assay = result.assay_quality[0].model_copy(
        update={"profile_digest": sha256_digest("forged-assay-profile-digest")}
    )
    with pytest.raises(ValueError, match="assay quality"):
        expected_receipt(
            quality_request,
            (forged_assay, *result.assay_quality[1:]),
            result.findings,
            result.disposition,
        )

    forged_receipt = result.receipt.model_copy(
        update={"receipt_digest": sha256_digest("forged-receipt")}
    )
    with pytest.raises(ValueError, match="receipt"):
        expected_provenance(quality_request, metrics, forged_receipt)


def test_private_raw_capability_replays_forged_and_unknown_upstream(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    payload = quality_request.model_dump(mode="python", exclude_none=False)
    upstream = cast("dict[str, object]", payload["raw_input_result"])
    upstream["result_digest"] = sha256_digest("forged-upstream")
    with pytest.raises(ValidationError):
        _issue_raw_input_replay_capability(payload)
    upstream["result_digest"] = quality_request.raw_input_result.result_digest
    upstream["unknown"] = True
    with pytest.raises(ValidationError):
        _issue_raw_input_replay_capability(payload)


def test_nested_builtin_subclasses_cannot_intercept_raw_replay_or_canonicalization(
    quality_request: ComputeProteoformQualityMetricsRequest,
) -> None:
    class HostileDict(dict[str, object]):
        def __iter__(self) -> Never:
            raise AssertionError

        def __getitem__(self, key: str) -> Never:
            del key
            raise AssertionError

        def items(self) -> Never:
            raise AssertionError

        def keys(self) -> Never:
            raise AssertionError

    class HostileList(list[object]):
        def __iter__(self) -> Never:
            raise AssertionError

    class HostileTuple(tuple[object, ...]):
        __slots__ = ()

        def __iter__(self) -> Never:
            raise AssertionError

    payload = quality_request.model_dump(mode="python", exclude_none=False)
    raw = cast("dict[str, object]", payload["raw_input_result"])
    raw["validated_inputs"] = HostileList(cast("list[object]", raw["validated_inputs"]))
    receipt = cast("dict[str, object]", raw["receipt"])
    receipt["diagnostic_codes"] = HostileTuple(
        cast("tuple[object, ...]", receipt["diagnostic_codes"])
    )
    hostile_raw = HostileDict(raw)
    payload["raw_input_result"] = hostile_raw

    cap = _issue_raw_input_replay_capability({"raw_input_result": hostile_raw})
    replayed = _validate_request_with_raw_capability(payload, cap)
    assert replayed.request.raw_input_result == quality_request.raw_input_result
    assert normalized_request(payload) == normalized_request(quality_request)


def test_canonical_helpers_reject_nonstring_builtin_dict_keys() -> None:
    with pytest.raises(TypeError, match="exact strings"):
        normalized_threshold(cast("dict[str, object]", {1: "not-a-json-key"}))


def test_semantic_request_reordering_preserves_exact_result(
    quality_request: ComputeProteoformQualityMetricsRequest,
    result: ProteoformQualityResult,
) -> None:
    payload = quality_request.model_dump(mode="python", exclude_none=False)
    policy = cast("dict[str, object]", payload["policy"])
    policy["profiles"] = tuple(reversed(cast("tuple[object, ...]", policy["profiles"])))
    ledger = cast("dict[str, object]", payload["fact_ledger"])
    ledger["role_facts"] = tuple(reversed(cast("tuple[object, ...]", ledger["role_facts"])))
    reordered = ComputeProteoformQualityMetricsRequest.model_validate(payload, strict=True)
    assert canonical_request_digest(reordered) == canonical_request_digest(quality_request)
    assert compute_proteoform_quality_metrics(reordered) == result
