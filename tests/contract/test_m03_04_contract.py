"""Focused public-contract checks for M03-04 protein-inference quality."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest
from evals.m03_04.run import Scenario, build_scenario
from pydantic import ValidationError

from glio_proteogen.contracts.m03_04 import (
    M0304_CONTRACT_VERSION,
    M0304_MAX_APPROVED_VERSIONS,
    M0304_MAX_CANONICAL_REQUEST_BYTES,
    M0304_MAX_EVIDENCE,
    M0304_MAX_PROFILES,
    M0304_METRIC_COUNT,
    M0304_OPERATION,
    ComputeProteinInferenceQualityRequest,
    ContractName,
    ProteinInferenceAssayQualityProfile,
    ProteinInferenceQualityFactLedger,
    ProteinInferenceQualityFindingAction,
    ProteinInferenceQualityFindingCode,
    ProteinInferenceQualityMetricCode,
    ProteinInferenceQualityMetricDirection,
    ProteinInferenceQualityObservationState,
    ProteinInferenceQualityPolicy,
    ProteinInferenceQualityResult,
    ProteinInferenceQualityThreshold,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    expected_quality_findings,
    fact_ledger_digest,
    finding_for,
    normalized_request,
    normalized_result,
    normalized_result_payload,
    raw_quality_receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.kernel.models import ArtifactReference
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c03_protein_inference.m03_04_quality_metrics import (
    compute_protein_inference_quality,
)

_SCHEMA_NAMES: tuple[ContractName, ...] = (
    "request",
    "output",
    "policy",
    "profile",
    "threshold",
    "raw-quality-receipt",
    "fact-ledger",
    "metric",
    "finding",
)
_EXPECTED_WARNING_FINDINGS = 2


def _artifact() -> ArtifactReference:
    return ArtifactReference(
        artifact_id="evidence.m0304.threshold",
        version="1.0.0",
        digest="sha256:" + ("a" * 64),
        media_type="application/json",
    )


@pytest.fixture(scope="module")
def canonical_scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def canonical_result(canonical_scenario: Scenario) -> ProteinInferenceQualityResult:
    return compute_protein_inference_quality(canonical_scenario.request)


def _request_with_quality_facts(
    scenario: Scenario,
    *,
    count_updates: dict[str, int] | None = None,
    state_updates: dict[str, ProteinInferenceQualityObservationState] | None = None,
    controls_applicable: bool | None = None,
) -> ComputeProteinInferenceQualityRequest:
    request = scenario.request
    ledger = request.fact_ledger
    assert ledger is not None
    counts = ledger.counts.model_copy(update=count_updates or {})
    states = ledger.states.model_copy(update=state_updates or {})
    updated_ledger = ledger.model_copy(update={"counts": counts, "states": states})
    updated_ledger = updated_ledger.model_copy(
        update={"ledger_digest": fact_ledger_digest(updated_ledger)}
    )
    updated_ledger = ProteinInferenceQualityFactLedger.model_validate(
        updated_ledger,
        strict=True,
    )
    policy = request.policy
    context = request.context
    if controls_applicable is not None:
        profile = policy.profiles[0].model_copy(
            update={"controls_applicable": controls_applicable}
        )
        policy = ProteinInferenceQualityPolicy.model_validate(
            policy.model_copy(update={"profiles": (profile,)}),
            strict=True,
        )
        references = context.references
        approved = references.approved_configuration.model_copy(
            update={
                "evidence": references.approved_configuration.evidence.model_copy(
                    update={"digest": configuration_digest(policy)}
                )
            }
        )
        context = context.model_copy(
            update={
                "references": references.model_copy(
                    update={"approved_configuration": approved}
                )
            }
        )
    return ComputeProteinInferenceQualityRequest(
        context=context,
        raw_quality_receipt=request.raw_quality_receipt,
        fact_ledger=updated_ledger,
        policy=policy,
    )


@pytest.fixture(scope="module")
def warning_result(canonical_scenario: Scenario) -> ProteinInferenceQualityResult:
    request = _request_with_quality_facts(
        canonical_scenario,
        count_updates={
            "unique_assigned_peptide_evidence_count": 60,
            "shared_group_assigned_peptide_evidence_count": 0,
            "unassigned_peptide_evidence_count": 40,
            "discriminating_proteoform_claim_count": 12,
        },
    )
    result = compute_protein_inference_quality(request)
    assert len(result.findings) == _EXPECTED_WARNING_FINDINGS
    return result


def _payload(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", strict_json_loads(canonical_json_bytes(value)))


def _validate_result(payload: dict[str, Any]) -> ProteinInferenceQualityResult:
    return ProteinInferenceQualityResult.model_validate_json(
        canonical_json_bytes(payload),
        strict=True,
    )


def _assert_recursive_objects_are_closed(value: object) -> None:
    if isinstance(value, dict):
        node = value
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
        for child in node.values():
            _assert_recursive_objects_are_closed(child)
    elif isinstance(value, list):
        for child in value:
            _assert_recursive_objects_are_closed(child)


def test_locked_operation_version_and_exact_metric_vocabulary() -> None:
    assert M0304_OPERATION == "compute_protein_inference_quality"
    assert M0304_CONTRACT_VERSION == "1.0.0"
    assert len(ProteinInferenceQualityMetricCode) == M0304_METRIC_COUNT
    assert {item.value for item in ProteinInferenceQualityMetricCode} == {
        "admitted_source_completeness",
        "peptide_assignment_coverage",
        "protein_group_ambiguity_burden",
        "proteoform_discrimination_coverage",
        "protein_group_detection_support",
        "protein_group_competition_closure",
        "control_group_recovery",
        "sample_context_binding_coherence",
    }


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_every_public_schema_is_strict_metadata_only(name: ContractName) -> None:
    schema = contract_json_schema(name)
    metadata = cast("dict[str, object]", schema["x-glio-contract"])
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert cast("str", schema["$id"]).endswith(f":{name}")
    assert metadata["strict"] is True
    assert metadata["rawPayloadInSchema"] is False
    assert metadata["reparsesRawPayload"] is False
    assert metadata["identityInference"] is False
    assert metadata["proteinInference"] is False
    assert metadata["complexActivityInference"] is False
    assert metadata["kinaseActivityInference"] is False
    if name == "request":
        assert metadata["maxRequestBytes"] == M0304_MAX_CANONICAL_REQUEST_BYTES
    _assert_recursive_objects_are_closed(schema)


@pytest.mark.parametrize(
    ("code", "direction"),
    [
        (code, ProteinInferenceQualityMetricDirection.AT_MOST)
        if code is ProteinInferenceQualityMetricCode.PROTEIN_GROUP_AMBIGUITY_BURDEN
        else (code, ProteinInferenceQualityMetricDirection.AT_LEAST)
        for code in ProteinInferenceQualityMetricCode
    ],
)
def test_threshold_direction_and_order_are_metric_closed(
    code: ProteinInferenceQualityMetricCode,
    direction: ProteinInferenceQualityMetricDirection,
) -> None:
    threshold = ProteinInferenceQualityThreshold(
        metric_code=code,
        direction=direction,
        pass_threshold_ppm=800_000 if direction.value == "at_least" else 200_000,
        warning_threshold_ppm=600_000 if direction.value == "at_least" else 400_000,
        required=True,
        evidence=_artifact(),
    )
    assert threshold.metric_code is code
    payload: dict[str, Any] = threshold.model_dump(mode="python")
    payload["direction"] = (
        ProteinInferenceQualityMetricDirection.AT_MOST
        if direction is ProteinInferenceQualityMetricDirection.AT_LEAST
        else ProteinInferenceQualityMetricDirection.AT_LEAST
    )
    with pytest.raises(ValidationError):
        ProteinInferenceQualityThreshold.model_validate(payload, strict=True)


def test_finding_vocabulary_is_exact_and_deterministic() -> None:
    assert len(ProteinInferenceQualityFindingCode) == len(
        ProteinInferenceQualityFindingAction
    ) + 9
    for code in ProteinInferenceQualityFindingCode:
        finding = finding_for(code)
        assert finding == finding_for(code)
        assert finding.message
    assert finding_for(ProteinInferenceQualityFindingCode.UPSTREAM_REJECTED).action is (
        ProteinInferenceQualityFindingAction.REJECT
    )
    assert finding_for(ProteinInferenceQualityFindingCode.OPTIONAL_METRIC_WARNING).action is (
        ProteinInferenceQualityFindingAction.RECORD
    )


def test_public_builder_request_is_strict_and_content_addressed(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    assert ComputeProteinInferenceQualityRequest.model_validate(request, strict=True) == request
    assert request.raw_quality_receipt.receipt_digest == raw_quality_receipt_digest(
        request.raw_quality_receipt
    )
    assert request.fact_ledger is not None
    assert request.fact_ledger.ledger_digest == fact_ledger_digest(request.fact_ledger)


def test_request_normalization_has_typed_dict_and_reorder_parity(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    payload = _payload(request)
    payload["raw_quality_receipt"]["sources"].reverse()
    payload["raw_quality_receipt"]["claims"].reverse()
    payload["policy"]["profiles"][0]["thresholds"].reverse()
    assert canonical_json_bytes(normalized_request(request)) == canonical_json_bytes(
        normalized_request(payload)
    )
    assert canonical_request_digest(request) == canonical_request_digest(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("raw_quality_receipt", "receipt_digest"),
        ("fact_ledger", "ledger_digest"),
    ],
)
def test_request_rejects_stale_nested_digests(
    canonical_scenario: Scenario,
    path: tuple[str, str],
) -> None:
    payload = _payload(canonical_scenario.request)
    payload[path[0]][path[1]] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError):
        ComputeProteinInferenceQualityRequest.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


def test_fact_ledger_rejects_observed_zero_coercion(
    canonical_scenario: Scenario,
) -> None:
    assert canonical_scenario.request.fact_ledger is not None
    payload = _payload(canonical_scenario.request.fact_ledger)
    payload["states"]["peptide_assignment"] = "missing"
    payload["ledger_digest"] = fact_ledger_digest(payload)
    with pytest.raises(ValidationError):
        ProteinInferenceQualityFactLedger.model_validate_json(
            canonical_json_bytes(payload),
            strict=True,
        )


def test_public_result_normalizers_share_the_strict_payload_contract() -> None:
    sentinel: dict[str, Any] = {
        "result_digest": "sha256:" + ("0" * 64),
        "request": {},
        "metrics": [],
        "findings": [],
        "provenance": {"input_digests": [], "control_decisions": []},
        "evidence": [],
        "limitations": [],
        "uncertainty": {"sensitivity_notes": []},
    }
    # Both names are deliberately the same public normalization boundary.
    with pytest.raises(KeyError):
        normalized_result(deepcopy(sentinel))
    with pytest.raises(KeyError):
        normalized_result_payload(deepcopy(sentinel))


@pytest.mark.parametrize(
    "field",
    [
        "approved_assay_protocol_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    ],
)
def test_profile_approved_versions_are_unique_and_capped(
    canonical_scenario: Scenario,
    field: str,
) -> None:
    profile = canonical_scenario.request.policy.profiles[0]
    duplicate = profile.model_dump(mode="python")
    duplicate[field] = ("1.0.0", "1.0.0")
    with pytest.raises(ValidationError):
        ProteinInferenceAssayQualityProfile.model_validate(duplicate, strict=True)
    overflow = profile.model_dump(mode="python")
    overflow[field] = tuple(
        f"1.0.{index}" for index in range(M0304_MAX_APPROVED_VERSIONS + 1)
    )
    with pytest.raises(ValidationError):
        ProteinInferenceAssayQualityProfile.model_validate(overflow, strict=True)


@pytest.mark.parametrize(
    "field",
    [
        "approved_assay_protocol_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    ],
)
def test_profile_schema_exposes_total_version_caps(field: str) -> None:
    schema = contract_json_schema("profile")
    properties = cast("dict[str, Any]", schema["properties"])
    field_schema = cast("dict[str, Any]", properties[field])
    assert field_schema["maxItems"] == M0304_MAX_APPROVED_VERSIONS


def test_policy_exact_max_profiles_is_reachable_and_first_overlap_is_rejected(
    canonical_scenario: Scenario,
) -> None:
    policy = canonical_scenario.request.policy
    base = policy.profiles[0]
    profiles = tuple(
        base.model_copy(
            update={
                "profile_id": f"profile.synthetic.m0304.{index}",
                "approved_assay_protocol_versions": (f"1.0.{index}",),
            }
        )
        for index in range(M0304_MAX_PROFILES)
    )
    exact = policy.model_copy(update={"profiles": profiles})
    validated = ProteinInferenceQualityPolicy.model_validate(exact, strict=True)
    assert set(validated.profiles) == set(profiles)
    overlapping = list(profiles)
    overlapping[1] = overlapping[1].model_copy(
        update={"approved_assay_protocol_versions": profiles[0].approved_assay_protocol_versions}
    )
    with pytest.raises(ValidationError):
        ProteinInferenceQualityPolicy.model_validate(
            policy.model_copy(update={"profiles": tuple(overlapping)}),
            strict=True,
        )


def test_policy_rejects_profile_cap_plus_one(canonical_scenario: Scenario) -> None:
    policy = canonical_scenario.request.policy
    base = policy.profiles[0]
    profiles = tuple(
        base.model_copy(
            update={
                "profile_id": f"profile.synthetic.m0304.{index}",
                "approved_assay_protocol_versions": (f"1.0.{index}",),
            }
        )
        for index in range(M0304_MAX_PROFILES + 1)
    )
    with pytest.raises(ValidationError):
        ProteinInferenceQualityPolicy.model_validate(
            policy.model_copy(update={"profiles": profiles}),
            strict=True,
        )


def test_maximum_profile_and_version_shape_executes_with_bounded_output(
    canonical_scenario: Scenario,
) -> None:
    request = canonical_scenario.request
    receipt = request.raw_quality_receipt
    base = request.policy.profiles[0]

    def versions(major: int, required: str | None = None) -> tuple[str, ...]:
        values = [] if required is None else [required]
        minor = 0
        while len(values) < M0304_MAX_APPROVED_VERSIONS:
            candidate = f"{major}.{minor}.0"
            if candidate not in values:
                values.append(candidate)
            minor += 1
        return tuple(values)

    profiles: list[ProteinInferenceAssayQualityProfile] = []
    for index in range(M0304_MAX_PROFILES):
        active = index == 0
        payload = base.model_dump(mode="python")
        payload.update(
            {
                "profile_id": f"profile.synthetic.m0304.maximum.{index:02d}",
                "approved_assay_protocol_versions": versions(
                    100 + index,
                    receipt.assay_protocol_version if active else None,
                ),
                "approved_controlled_vocabulary_versions": versions(
                    200 + index,
                    receipt.controlled_vocabulary_version if active else None,
                ),
                "approved_unit_system_versions": versions(
                    300 + index,
                    receipt.unit_system_version if active else None,
                ),
            }
        )
        profiles.append(
            ProteinInferenceAssayQualityProfile.model_validate(payload, strict=True)
        )
    policy_payload = request.policy.model_dump(mode="python")
    policy_payload["profiles"] = tuple(profiles)
    policy = ProteinInferenceQualityPolicy.model_validate(policy_payload, strict=True)
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
    maximum = ComputeProteinInferenceQualityRequest(
        context=context,
        raw_quality_receipt=receipt,
        fact_ledger=request.fact_ledger,
        policy=policy,
    )
    assert len(canonical_json_bytes(maximum)) <= M0304_MAX_CANONICAL_REQUEST_BYTES
    result = compute_protein_inference_quality(maximum)
    assert len(result.evidence) <= M0304_MAX_EVIDENCE
    assert len(result.metrics) == M0304_METRIC_COUNT
    assert ProteinInferenceQualityResult.model_validate_json(
        canonical_json_bytes(result),
        strict=True,
    ) == result


def _assert_resigned_result_rejected(
    result: ProteinInferenceQualityResult,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload = _payload(result)
    mutate(payload)
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        _validate_result(payload)


def test_canonical_result_replays_exact_request_metrics_and_envelopes(
    canonical_result: ProteinInferenceQualityResult,
) -> None:
    assert len(canonical_result.metrics) == M0304_METRIC_COUNT
    assert not canonical_result.findings
    assert canonical_result.result_id == (
        f"result.m0304.{canonical_result.request_digest.removeprefix('sha256:')}"
    )
    assert canonical_result.result_digest == result_payload_digest(canonical_result)
    assert _validate_result(_payload(canonical_result)) == canonical_result


def test_result_semantic_reordering_has_typed_dict_digest_parity(
    canonical_result: ProteinInferenceQualityResult,
) -> None:
    payload = _payload(canonical_result)
    payload["request"]["raw_quality_receipt"]["sources"].reverse()
    payload["request"]["raw_quality_receipt"]["claims"].reverse()
    payload["request"]["policy"]["profiles"][0]["thresholds"].reverse()
    for field in (
        "approved_assay_protocol_versions",
        "approved_controlled_vocabulary_versions",
        "approved_unit_system_versions",
    ):
        payload["request"]["policy"]["profiles"][0][field].reverse()
    payload["metrics"].reverse()
    payload["evidence"].reverse()
    payload["limitations"].reverse()
    payload["provenance"]["input_digests"].reverse()
    payload["provenance"]["control_decisions"].reverse()
    payload["uncertainty"]["sensitivity_notes"].reverse()
    assert canonical_json_bytes(normalized_result(canonical_result)) == canonical_json_bytes(
        normalized_result(payload)
    )
    assert result_payload_digest(canonical_result) == result_payload_digest(payload)
    payload["result_digest"] = result_payload_digest(payload)
    reconstructed = _validate_result(payload)
    assert reconstructed == canonical_result
    assert reconstructed.request == canonical_result.request


def test_resigned_result_rejects_forged_result_id(
    canonical_result: ProteinInferenceQualityResult,
) -> None:
    _assert_resigned_result_rejected(
        canonical_result,
        lambda payload: payload.__setitem__("result_id", "result.m0304.forged"),
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("parent_target", "kinase_activity"),
        ("emits_complex_activity", True),
        ("infers_identity", True),
        ("infers_protein", True),
        ("infers_kinase_activity", True),
    ],
)
def test_resigned_result_rejects_scope_forgery(
    canonical_result: ProteinInferenceQualityResult,
    field: str,
    replacement: object,
) -> None:
    _assert_resigned_result_rejected(
        canonical_result,
        lambda payload: payload.__setitem__(field, replacement),
    )


@pytest.mark.parametrize(
    "field",
    [
        "request_digest",
        "policy_digest",
        "configuration_digest",
    ],
)
def test_resigned_result_rejects_outer_digest_forgery(
    canonical_result: ProteinInferenceQualityResult,
    field: str,
) -> None:
    _assert_resigned_result_rejected(
        canonical_result,
        lambda payload: payload.__setitem__(field, "sha256:" + ("f" * 64)),
    )


@pytest.mark.parametrize("mutation", ["remove", "add", "substitute"])
def test_resigned_result_rejects_finding_set_forgery(
    warning_result: ProteinInferenceQualityResult,
    mutation: str,
) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        extra = _payload(
            finding_for(
                ProteinInferenceQualityFindingCode.CROSS_METRIC_INCONSISTENCY,
                metric_codes=(ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY,),
            )
        )
        if mutation == "remove":
            payload["findings"].pop()
        elif mutation == "add":
            payload["findings"].append(extra)
        else:
            payload["findings"][0] = extra

    _assert_resigned_result_rejected(warning_result, mutate)


def test_finding_reorder_normalizes_to_identical_result(
    warning_result: ProteinInferenceQualityResult,
) -> None:
    payload = _payload(warning_result)
    payload["findings"].reverse()
    payload["result_digest"] = result_payload_digest(payload)
    assert _validate_result(payload) == warning_result


def test_expected_finding_set_is_canonically_ordered(
    warning_result: ProteinInferenceQualityResult,
) -> None:
    assert expected_quality_findings(
        warning_result.request,
        warning_result.metrics,
    ) == warning_result.findings


@pytest.mark.parametrize(
    (
        "controls_applicable",
        "control_state",
        "expected_count",
        "recovered_count",
        "expected_disposition_value",
        "expected_code",
    ),
    [
        (False, "not_applicable", 0, 0, "qualified", None),
        (False, "observed", 10, 9, "quarantined", "cross_metric_inconsistency"),
        (True, "not_applicable", 0, 0, "quarantined", "cross_metric_inconsistency"),
    ],
)
def test_control_applicability_is_bidirectionally_profile_closed(  # noqa: PLR0913, PLR0917
    canonical_scenario: Scenario,
    controls_applicable: object,
    control_state: str,
    expected_count: int,
    recovered_count: int,
    expected_disposition_value: str,
    expected_code: str | None,
) -> None:
    assert isinstance(controls_applicable, bool)
    request = _request_with_quality_facts(
        canonical_scenario,
        count_updates={
            "control_expected_group_count": expected_count,
            "control_recovered_group_count": recovered_count,
        },
        state_updates={
            "control_recovery": ProteinInferenceQualityObservationState(control_state),
        },
        controls_applicable=controls_applicable,
    )
    result = compute_protein_inference_quality(request)
    assert any(
        item
        for item in result.metrics
        if item.metric_code is ProteinInferenceQualityMetricCode.CONTROL_GROUP_RECOVERY
    )
    assert result.disposition.value == expected_disposition_value
    if expected_code is None:
        assert not result.findings
    else:
        assert result.findings[0].code.value == expected_code


def test_required_non_control_not_applicable_cannot_qualify(
    canonical_scenario: Scenario,
) -> None:
    request = _request_with_quality_facts(
        canonical_scenario,
        count_updates={
            "eligible_proteoform_claim_count": 0,
            "discriminating_proteoform_claim_count": 0,
        },
        state_updates={
            "proteoform_discrimination": (
                ProteinInferenceQualityObservationState.NOT_APPLICABLE
            )
        },
    )
    result = compute_protein_inference_quality(request)
    metric = next(
        item
        for item in result.metrics
        if item.metric_code
        is ProteinInferenceQualityMetricCode.PROTEOFORM_DISCRIMINATION_COVERAGE
    )
    assert metric.required is True
    assert metric.observation_state is ProteinInferenceQualityObservationState.NOT_APPLICABLE
    assert result.disposition.value == "abstained"
    assert {item.code for item in result.findings} == {
        ProteinInferenceQualityFindingCode.REQUIRED_METRIC_NOT_EVALUABLE
    }


def test_cross_metric_inconsistency_preserves_simultaneous_threshold_failure(
    canonical_scenario: Scenario,
) -> None:
    request = _request_with_quality_facts(
        canonical_scenario,
        count_updates={
            "unique_assigned_peptide_evidence_count": 40,
            "shared_group_assigned_peptide_evidence_count": 0,
            "unassigned_peptide_evidence_count": 60,
            "control_expected_group_count": 10,
            "control_recovered_group_count": 9,
        },
        state_updates={
            "control_recovery": ProteinInferenceQualityObservationState.OBSERVED,
        },
        controls_applicable=False,
    )
    result = compute_protein_inference_quality(request)
    assert {item.code for item in result.findings} == {
        ProteinInferenceQualityFindingCode.CROSS_METRIC_INCONSISTENCY,
        ProteinInferenceQualityFindingCode.METRIC_THRESHOLD_FAILED,
    }
    assert result.disposition.value == "quarantined"
