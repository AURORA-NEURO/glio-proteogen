"""Strict replay and adversarial contract checks for M04-07."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, cast

import pytest
from evals.m04_07.run import Scenario, build_scenario
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from glio_proteogen.contracts.m04_06 import M0406_MAX_LEVELS_PER_FACTOR, M0406_MAX_TARGETS
from glio_proteogen.contracts.m04_07 import (
    M0407_CONTEXT_RECEIPT_COUNT,
    M0407_DECLARED_FACT_COUNT,
    M0407_DIMENSION_COUNT,
    M0407_MAX_ABSTENTIONS,
    M0407_MAX_ANALYSIS_TARGETS,
    M0407_MAX_APPROVED_VERSIONS,
    M0407_MAX_CANONICAL_REQUEST_BYTES,
    M0407_MAX_ENVELOPES,
    M0407_MAX_EVIDENCE,
    M0407_MAX_EVIDENCE_PER_FACT,
    M0407_MAX_FACT_VALUES,
    M0407_MAX_PLATFORM_LEVEL_IDS,
    M0407_MODULE_ID,
    M0407_OUTPUT_MEDIA_TYPE,
    M0407_QUALITY_METRIC_COUNT,
    M0407_RATE_SCALE,
    M0407_ZERO_DIGEST,
    ProteoformAbstention,
    ProteoformAbstentionCode,
    ProteoformDimensionAssessment,
    ProteoformDimensionSupportDecision,
    ProteoformHarmonizationSupportReceipt,
    ProteoformQualitySupportReceipt,
    ProteoformSupportDimension,
    ProteoformSupportPrerequisites,
    ProteoformSupportRouteResult,
    RouteProteoformSupportRequest,
    canonical_request_digest,
    configuration_digest,
    contract_json_schema,
    harmonization_support_receipt,
    harmonization_support_receipt_digest,
    normalized_request,
    normalized_result,
    quality_support_receipt,
    quality_support_receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    ProteoformSupportReceiptError,
    proteoform_support_prerequisites,
    route_proteoform_support,
)
from glio_proteogen.modules.c04_proteoform_isoform.m04_07_support_router import (
    engine as support_router_engine,
)

_SCHEMA_NAMES = (
    "request",
    "output",
    "prerequisites",
    "quality-receipt",
    "harmonization-receipt",
    "fact",
    "context-receipt",
    "profile",
    "policy",
    "envelope",
    "remediation",
    "dimension-assessment",
    "envelope-assessment",
    "abstention",
)
_EXPECTED_UPSTREAM_TARGET_CAP = M0406_MAX_TARGETS

AbstentionCapacity = Annotated[
    tuple[ProteoformAbstention, ...], Field(max_length=M0407_MAX_ABSTENTIONS)
]
_ABSTENTION_CAPACITY_ADAPTER = TypeAdapter(AbstentionCapacity)


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def canonical_result(scenario: Scenario) -> ProteoformSupportRouteResult:
    return route_proteoform_support(scenario.request)


def _payload(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="python")


def test_prerequisite_builder_preserves_specific_upstream_receipt_error(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_quality_projection(_result: object) -> ProteoformQualitySupportReceipt:
        raise ProteoformSupportReceiptError.quality()

    monkeypatch.setattr(
        support_router_engine,
        "proteoform_quality_support_receipt",
        fail_quality_projection,
    )
    with pytest.raises(ProteoformSupportReceiptError, match="M04-04 result"):
        proteoform_support_prerequisites(
            scenario.quality_result,
            scenario.harmonization_result,
        )


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_all_fourteen_schemas_and_public_caps_are_exact(name: str) -> None:
    schema = contract_json_schema(cast("Any", name))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == f"urn:aurora-neuro:glio-proteogen:{M0407_MODULE_ID}:1.0.0:{name}"
    assert schema["additionalProperties"] is False
    metadata = cast("dict[str, object]", schema["x-glio-contract"])
    assert metadata["strict"] is True
    assert metadata["rawPayloadInSchema"] is False
    assert metadata["outputMediaType"] == M0407_OUTPUT_MEDIA_TYPE
    if name == "request":
        assert metadata["maxRequestBytes"] == M0407_MAX_CANONICAL_REQUEST_BYTES

    assert (
        M0407_DIMENSION_COUNT,
        M0407_DECLARED_FACT_COUNT,
        M0407_CONTEXT_RECEIPT_COUNT,
        M0407_MAX_ENVELOPES,
        M0407_MAX_FACT_VALUES,
        M0407_MAX_APPROVED_VERSIONS,
        M0407_MAX_EVIDENCE_PER_FACT,
        M0407_MAX_ABSTENTIONS,
        M0407_MAX_EVIDENCE,
        M0407_RATE_SCALE,
    ) == (8, 4, 3, 64, 64, 32, 8, 514, 46, 1_000_000)
    assert M0407_MAX_PLATFORM_LEVEL_IDS == M0406_MAX_LEVELS_PER_FACTOR
    assert M0407_MAX_ANALYSIS_TARGETS == _EXPECTED_UPSTREAM_TARGET_CAP


def test_collection_caps_are_emitted_by_their_own_schemas() -> None:
    request = cast("dict[str, Any]", contract_json_schema("request")["properties"])
    output = cast("dict[str, Any]", contract_json_schema("output")["properties"])
    profile = cast("dict[str, Any]", contract_json_schema("profile")["properties"])
    envelope = cast("dict[str, Any]", contract_json_schema("envelope")["properties"])
    fact = cast("dict[str, Any]", contract_json_schema("fact")["properties"])
    quality = cast("dict[str, Any]", contract_json_schema("quality-receipt")["properties"])
    harmonization = cast(
        "dict[str, Any]", contract_json_schema("harmonization-receipt")["properties"]
    )
    dimension_assessment = cast(
        "dict[str, Any]", contract_json_schema("dimension-assessment")["properties"]
    )

    assert (
        request["declared_facts"]["minItems"]
        == request["declared_facts"]["maxItems"]
        == M0407_DECLARED_FACT_COUNT
    )
    assert (
        request["context_receipts"]["minItems"]
        == request["context_receipts"]["maxItems"]
        == M0407_CONTEXT_RECEIPT_COUNT
    )
    assert output["matched_envelope_ids"]["maxItems"] == M0407_MAX_ENVELOPES
    assert output["envelope_assessments"]["maxItems"] == M0407_MAX_ENVELOPES
    assert output["abstention_reasons"]["maxItems"] == M0407_MAX_ABSTENTIONS
    assert output["evidence"]["maxItems"] == M0407_MAX_EVIDENCE
    assert profile["envelopes"]["maxItems"] == M0407_MAX_ENVELOPES
    assert envelope["approved_assay_protocol_versions"]["maxItems"] == M0407_MAX_APPROVED_VERSIONS
    assert envelope["platform_level_ids"]["maxItems"] == M0407_MAX_PLATFORM_LEVEL_IDS
    assert (
        envelope["remediations"]["minItems"]
        == envelope["remediations"]["maxItems"]
        == M0407_DIMENSION_COUNT
    )
    assert fact["values"]["maxItems"] == M0407_MAX_FACT_VALUES
    assert dimension_assessment["values"]["maxItems"] == M0407_MAX_FACT_VALUES
    assert fact["evidence"]["maxItems"] == M0407_MAX_EVIDENCE_PER_FACT
    assert quality["metrics"]["maxItems"] == M0407_QUALITY_METRIC_COUNT
    assert harmonization["analysis_platform_level_ids"]["maxItems"] == M0407_MAX_PLATFORM_LEVEL_IDS
    assert harmonization["analysis_target_count"]["anyOf"][0]["maximum"] == (
        M0407_MAX_ANALYSIS_TARGETS
    )


def test_compact_receipts_are_exact_full_result_projections(scenario: Scenario) -> None:
    prerequisites = scenario.request.prerequisites
    assert prerequisites.quality_result == scenario.quality_result
    assert prerequisites.harmonization_result == scenario.harmonization_result
    assert prerequisites.quality == quality_support_receipt(scenario.quality_result)
    assert prerequisites.harmonization == harmonization_support_receipt(
        scenario.harmonization_result
    )


def test_result_provenance_preserves_shared_control_role_order(
    canonical_result: ProteoformSupportRouteResult,
) -> None:
    role_values = tuple(
        decision.role.value for decision in canonical_result.provenance.control_decisions
    )
    assert role_values == tuple(sorted(role_values))
    normalized = normalized_result(canonical_result)
    provenance = cast("dict[str, Any]", normalized["provenance"])
    control_decisions = cast("tuple[dict[str, Any], ...]", provenance["control_decisions"])
    assert tuple(decision["role"] for decision in control_decisions) == role_values
    normalized["result_digest"] = canonical_result.result_digest
    assert (
        ProteoformSupportRouteResult.model_validate_json(
            canonical_json_bytes(normalized),
            strict=True,
        )
        == canonical_result
    )


def _request_with_specimen_value_count(
    request: RouteProteoformSupportRequest,
    count: int,
) -> RouteProteoformSupportRequest:
    values = tuple(
        "specimen." + sha256_digest({"specimen_index": index}).removeprefix("sha256:")
        for index in range(count)
    )
    specimen_fact = next(
        fact
        for fact in request.declared_facts
        if fact.dimension is ProteoformSupportDimension.SPECIMEN
    )
    expanded_fact = type(specimen_fact).model_validate(
        {**specimen_fact.model_dump(mode="python"), "values": values},
        strict=True,
    )
    envelope = request.profile.envelopes[0]
    expanded_envelope = type(envelope).model_validate(
        {**envelope.model_dump(mode="python"), "specimen_terms": values},
        strict=True,
    )
    profile = type(request.profile).model_validate(
        {**request.profile.model_dump(mode="python"), "envelopes": (expanded_envelope,)},
        strict=True,
    )
    references = request.context.references
    approved = references.approved_configuration.model_copy(
        update={
            "evidence": references.approved_configuration.evidence.model_copy(
                update={"digest": configuration_digest(profile, request.policy)}
            )
        }
    )
    request_id = "request." + sha256_digest({"m0407_specimen_value_count": count}).removeprefix(
        "sha256:"
    )
    context = request.context.model_copy(
        update={
            "request_id": request_id,
            "references": references.model_copy(update={"approved_configuration": approved}),
        }
    )
    facts = tuple(
        expanded_fact if fact.dimension is ProteoformSupportDimension.SPECIMEN else fact
        for fact in request.declared_facts
    )
    return RouteProteoformSupportRequest.model_validate(
        {
            **request.model_dump(mode="python"),
            "request_id": request_id,
            "context": context,
            "profile": profile,
            "declared_facts": facts,
        },
        strict=True,
    )


def test_public_route_accepts_fact_capacity_and_rejects_first_excess(
    scenario: Scenario,
) -> None:
    request = _request_with_specimen_value_count(scenario.request, M0407_MAX_FACT_VALUES)
    result = route_proteoform_support(request)
    assessment = next(
        item
        for item in result.envelope_assessments[0].dimensions
        if item.dimension is ProteoformSupportDimension.SPECIMEN
    )
    assert len(assessment.values) == M0407_MAX_FACT_VALUES

    payload = request.model_dump(mode="python")
    excess = "specimen." + sha256_digest("first-excess").removeprefix("sha256:")
    specimen_fact = next(
        item
        for item in payload["declared_facts"]
        if item["dimension"] is ProteoformSupportDimension.SPECIMEN
    )
    specimen_fact["values"] = (*specimen_fact["values"], excess)
    payload["profile"]["envelopes"][0]["specimen_terms"] = (
        *payload["profile"]["envelopes"][0]["specimen_terms"],
        excess,
    )
    with pytest.raises(ValidationError, match="at most 64"):
        route_proteoform_support(payload)


def test_resigned_compact_receipt_forgery_is_rejected(scenario: Scenario) -> None:
    prerequisites = scenario.request.prerequisites
    quality_payload = prerequisites.quality.model_dump(mode="python", exclude={"receipt_digest"})
    quality_payload["controlled_vocabulary_version"] = "99.0.0"
    quality_payload["receipt_digest"] = quality_support_receipt_digest(quality_payload)
    forged_quality = ProteoformQualitySupportReceipt.model_validate(quality_payload, strict=True)
    with pytest.raises(ValidationError, match="exact projection"):
        ProteoformSupportPrerequisites.model_validate(
            prerequisites.model_copy(update={"quality": forged_quality}), strict=True
        )

    harmonization_payload = prerequisites.harmonization.model_dump(
        mode="python", exclude={"receipt_digest"}
    )
    harmonization_payload["controlled_vocabulary_version"] = "99.0.0"
    harmonization_payload["receipt_digest"] = harmonization_support_receipt_digest(
        harmonization_payload
    )
    forged_harmonization = ProteoformHarmonizationSupportReceipt.model_validate(
        harmonization_payload, strict=True
    )
    with pytest.raises(ValidationError, match="exact projection"):
        ProteoformSupportPrerequisites.model_validate(
            prerequisites.model_copy(update={"harmonization": forged_harmonization}),
            strict=True,
        )


@pytest.mark.parametrize(
    "forged_digest",
    [M0407_ZERO_DIGEST, sha256_digest("stale-m0407-result")],
    ids=("zero", "stale"),
)
def test_zero_and_stale_result_digests_are_rejected(
    canonical_result: ProteoformSupportRouteResult,
    forged_digest: str,
) -> None:
    payload = _payload(canonical_result)
    payload["result_digest"] = forged_digest
    with pytest.raises(ValidationError, match="result digest"):
        ProteoformSupportRouteResult.model_validate(payload, strict=True)


def test_partial_dimension_remediation_tuple_is_rejected(
    canonical_result: ProteoformSupportRouteResult,
    scenario: Scenario,
) -> None:
    assessment = canonical_result.envelope_assessments[0].dimensions[0]
    remediation = next(
        item
        for item in scenario.request.profile.envelopes[0].remediations
        if item.dimension is assessment.dimension
    )
    partial = assessment.model_copy(
        update={
            "decision": ProteoformDimensionSupportDecision.OUTSIDE_DOMAIN,
            "reason_code": remediation.outside_reason_code,
        }
    )
    with pytest.raises(ValidationError, match="require remediation"):
        ProteoformDimensionAssessment.model_validate(partial, strict=True)


def test_request_and_execution_context_identifier_mismatch_is_rejected(
    scenario: Scenario,
) -> None:
    request = scenario.request
    mismatched_context = request.context.model_copy(update={"request_id": "request." + ("f" * 64)})
    with pytest.raises(ValidationError, match="identifiers disagree"):
        RouteProteoformSupportRequest.model_validate(
            request.model_copy(update={"context": mismatched_context}), strict=True
        )


def test_semantic_reorder_reconstructs_complete_request_and_result_equality(
    scenario: Scenario,
    canonical_result: ProteoformSupportRouteResult,
) -> None:
    request = scenario.request
    payload = _payload(request)
    prerequisites = cast("dict[str, Any]", payload["prerequisites"])
    quality_result = cast("dict[str, Any]", prerequisites["quality_result"])
    harmonization_result = cast("dict[str, Any]", prerequisites["harmonization_result"])

    assay_quality = cast("tuple[dict[str, Any], ...]", quality_result["assay_quality"])
    quality_result["assay_quality"] = tuple(reversed(assay_quality))
    for assay in assay_quality:
        assay["metrics"] = tuple(reversed(cast("tuple[object, ...]", assay["metrics"])))
        assay["finding_codes"] = tuple(reversed(cast("tuple[object, ...]", assay["finding_codes"])))
    quality_findings = cast("tuple[dict[str, Any], ...]", quality_result["findings"])
    for finding in quality_findings:
        for field in ("roles", "metric_codes"):
            finding[field] = tuple(reversed(cast("tuple[object, ...]", finding[field])))
    for field in ("findings", "evidence", "limitations"):
        quality_result[field] = tuple(reversed(cast("tuple[object, ...]", quality_result[field])))
    quality_computation_receipt = cast("dict[str, Any]", quality_result["receipt"])
    for field in ("selected_profile_digests", "assay_quality_digests", "finding_codes"):
        quality_computation_receipt[field] = tuple(
            reversed(cast("tuple[object, ...]", quality_computation_receipt[field]))
        )
    for field in (
        "technical_effect_diagnostics",
        "invariant_diagnostics",
        "findings",
        "evidence",
        "limitations",
    ):
        harmonization_result[field] = tuple(
            reversed(cast("tuple[object, ...]", harmonization_result[field]))
        )
    for result in (quality_result, harmonization_result):
        provenance = cast("dict[str, Any]", result["provenance"])
        provenance["input_digests"] = tuple(
            reversed(cast("tuple[object, ...]", provenance["input_digests"]))
        )
        provenance["control_decisions"] = tuple(
            reversed(cast("tuple[object, ...]", provenance["control_decisions"]))
        )
        uncertainty = cast("dict[str, Any]", result["uncertainty"])
        uncertainty["sensitivity_notes"] = tuple(
            reversed(cast("tuple[object, ...]", uncertainty["sensitivity_notes"]))
        )

    quality_receipt = cast("dict[str, Any]", prerequisites["quality"])
    quality_receipt["metrics"] = tuple(
        reversed(cast("tuple[object, ...]", quality_receipt["metrics"]))
    )
    harmonization_receipt = cast("dict[str, Any]", prerequisites["harmonization"])
    harmonization_receipt["analysis_platform_level_ids"] = tuple(
        reversed(
            cast(
                "tuple[object, ...]",
                harmonization_receipt["analysis_platform_level_ids"],
            )
        )
    )

    profile = cast("dict[str, Any]", payload["profile"])
    envelopes = cast("tuple[dict[str, Any], ...]", profile["envelopes"])
    for envelope in envelopes:
        for field in (
            "approved_assay_protocol_versions",
            "approved_specimen_processing_versions",
            "approved_controlled_vocabulary_ids",
            "approved_controlled_vocabulary_versions",
            "approved_unit_system_versions",
            "quality_statuses",
            "platform_level_ids",
            "required_context_roles",
            "remediations",
        ):
            envelope[field] = tuple(reversed(cast("tuple[object, ...]", envelope[field])))
    payload["declared_facts"] = tuple(
        reversed(cast("tuple[object, ...]", payload["declared_facts"]))
    )
    payload["context_receipts"] = tuple(
        reversed(cast("tuple[object, ...]", payload["context_receipts"]))
    )

    reordered = RouteProteoformSupportRequest.model_validate(payload, strict=True)
    reordered_result = route_proteoform_support(reordered)
    assert reordered == request
    assert normalized_request(reordered) == normalized_request(request)
    assert canonical_request_digest(reordered) == canonical_request_digest(request)
    assert canonical_json_bytes(reordered) == canonical_json_bytes(request)
    assert reordered_result == canonical_result


@pytest.mark.parametrize(
    "field",
    ["matched_envelope_ids", "route_id", "human_review_required", "completed_at"],
)
def test_resigned_derived_result_field_forgery_is_rejected(
    canonical_result: ProteoformSupportRouteResult,
    field: str,
) -> None:
    payload = _payload(canonical_result)
    forged: object
    if field == "matched_envelope_ids":
        forged = ()
    elif field == "route_id":
        forged = "route." + ("f" * 64)
    elif field == "human_review_required":
        forged = not canonical_result.human_review_required
    else:
        forged = canonical_result.completed_at + timedelta(microseconds=1)
    payload[field] = forged
    payload["result_digest"] = result_payload_digest(payload)
    with pytest.raises(ValidationError):
        ProteoformSupportRouteResult.model_validate(payload, strict=True)


def test_abstention_field_accepts_exact_514_and_rejects_515(scenario: Scenario) -> None:
    envelope = scenario.request.profile.envelopes[0]
    remediation = envelope.remediations[0]
    abstention = ProteoformAbstention(
        code=ProteoformAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
        envelope_id=envelope.envelope_id,
        dimension=remediation.dimension,
        reason_code=remediation.outside_reason_code,
        remediation_code=remediation.remediation_code,
        remediation_path=remediation.remediation_path,
    )
    at_capacity = _ABSTENTION_CAPACITY_ADAPTER.validate_python(
        (abstention,) * M0407_MAX_ABSTENTIONS, strict=True
    )
    assert len(at_capacity) == M0407_MAX_ABSTENTIONS
    with pytest.raises(ValidationError, match="at most 514"):
        _ABSTENTION_CAPACITY_ADAPTER.validate_python(
            (abstention,) * (M0407_MAX_ABSTENTIONS + 1), strict=True
        )
