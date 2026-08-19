"""Strict replay and adversarial contract checks for M03-07."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Any, cast

import pytest
from evals.m03_07.run import Scenario, build_scenario
from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from glio_proteogen.contracts.m03_07 import (
    M0307_CONTEXT_RECEIPT_COUNT,
    M0307_DECLARED_FACT_COUNT,
    M0307_DIMENSION_COUNT,
    M0307_MAX_ABSTENTIONS,
    M0307_MAX_APPROVED_VERSIONS,
    M0307_MAX_CANONICAL_REQUEST_BYTES,
    M0307_MAX_ENVELOPES,
    M0307_MAX_EVIDENCE,
    M0307_MAX_EVIDENCE_PER_FACT,
    M0307_MAX_FACT_VALUES,
    M0307_MAX_PLATFORM_LEVEL_IDS,
    M0307_MODULE_ID,
    M0307_RATE_SCALE,
    M0307_ZERO_DIGEST,
    ProteinInferenceAbstention,
    ProteinInferenceAbstentionCode,
    ProteinInferenceDimensionAssessment,
    ProteinInferenceDimensionSupportDecision,
    ProteinInferenceHarmonizationSupportReceipt,
    ProteinInferenceQualitySupportReceipt,
    ProteinInferenceSupportPrerequisites,
    ProteinInferenceSupportRouteResult,
    RouteProteinInferenceSupportRequest,
    canonical_request_digest,
    contract_json_schema,
    harmonization_support_receipt,
    harmonization_support_receipt_digest,
    normalized_request,
    quality_support_receipt,
    quality_support_receipt_digest,
    result_payload_digest,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
    ProteinInferenceSupportReceiptError,
    protein_inference_support_prerequisites,
    route_protein_inference_support,
)
from glio_proteogen.modules.c03_protein_inference.m03_07_support_router import (
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

AbstentionCapacity = Annotated[
    tuple[ProteinInferenceAbstention, ...], Field(max_length=M0307_MAX_ABSTENTIONS)
]
_ABSTENTION_CAPACITY_ADAPTER = TypeAdapter(AbstentionCapacity)


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    return build_scenario()


@pytest.fixture(scope="module")
def canonical_result(scenario: Scenario) -> ProteinInferenceSupportRouteResult:
    return route_protein_inference_support(scenario.request)


def _payload(value: BaseModel) -> dict[str, Any]:
    return value.model_dump(mode="python")


def test_prerequisite_builder_preserves_specific_upstream_receipt_error(
    scenario: Scenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_quality_projection(_result: object) -> ProteinInferenceQualitySupportReceipt:
        raise ProteinInferenceSupportReceiptError.quality()

    monkeypatch.setattr(
        support_router_engine,
        "protein_inference_quality_support_receipt",
        fail_quality_projection,
    )
    with pytest.raises(ProteinInferenceSupportReceiptError, match="M03-04 result"):
        protein_inference_support_prerequisites(
            scenario.quality_result,
            scenario.harmonization_result,
        )


@pytest.mark.parametrize("name", _SCHEMA_NAMES)
def test_all_fourteen_schemas_and_public_caps_are_exact(name: str) -> None:
    schema = contract_json_schema(cast("Any", name))
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == f"urn:aurora-neuro:glio-proteogen:{M0307_MODULE_ID}:1.0.0:{name}"
    assert schema["additionalProperties"] is False
    metadata = cast("dict[str, object]", schema["x-glio-contract"])
    assert metadata["strict"] is True
    assert metadata["rawPayloadInSchema"] is False
    if name == "request":
        assert metadata["maxRequestBytes"] == M0307_MAX_CANONICAL_REQUEST_BYTES

    assert (
        M0307_DIMENSION_COUNT,
        M0307_DECLARED_FACT_COUNT,
        M0307_CONTEXT_RECEIPT_COUNT,
        M0307_MAX_ENVELOPES,
        M0307_MAX_FACT_VALUES,
        M0307_MAX_PLATFORM_LEVEL_IDS,
        M0307_MAX_APPROVED_VERSIONS,
        M0307_MAX_EVIDENCE_PER_FACT,
        M0307_MAX_ABSTENTIONS,
        M0307_MAX_EVIDENCE,
        M0307_RATE_SCALE,
    ) == (8, 4, 3, 64, 64, 512, 32, 8, 514, 46, 1_000_000)


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

    assert (
        request["declared_facts"]["minItems"]
        == request["declared_facts"]["maxItems"]
        == M0307_DECLARED_FACT_COUNT
    )
    assert (
        request["context_receipts"]["minItems"]
        == request["context_receipts"]["maxItems"]
        == M0307_CONTEXT_RECEIPT_COUNT
    )
    assert output["matched_envelope_ids"]["maxItems"] == M0307_MAX_ENVELOPES
    assert output["envelope_assessments"]["maxItems"] == M0307_MAX_ENVELOPES
    assert output["abstention_reasons"]["maxItems"] == M0307_MAX_ABSTENTIONS
    assert output["evidence"]["maxItems"] == M0307_MAX_EVIDENCE
    assert profile["envelopes"]["maxItems"] == M0307_MAX_ENVELOPES
    assert envelope["approved_assay_protocol_versions"]["maxItems"] == M0307_MAX_APPROVED_VERSIONS
    assert envelope["platform_level_ids"]["maxItems"] == M0307_MAX_PLATFORM_LEVEL_IDS
    assert (
        envelope["remediations"]["minItems"]
        == envelope["remediations"]["maxItems"]
        == M0307_DIMENSION_COUNT
    )
    assert fact["values"]["maxItems"] == M0307_MAX_FACT_VALUES
    assert fact["evidence"]["maxItems"] == M0307_MAX_EVIDENCE_PER_FACT
    assert quality["metrics"]["maxItems"] == M0307_DIMENSION_COUNT
    assert harmonization["platform_level_ids"]["maxItems"] == M0307_MAX_PLATFORM_LEVEL_IDS


def test_compact_receipts_are_exact_full_result_projections(scenario: Scenario) -> None:
    prerequisites = scenario.request.prerequisites
    assert prerequisites.quality_result == scenario.quality_result
    assert prerequisites.harmonization_result == scenario.harmonization_result
    assert prerequisites.quality == quality_support_receipt(scenario.quality_result)
    assert prerequisites.harmonization == harmonization_support_receipt(
        scenario.harmonization_result
    )


def test_resigned_compact_receipt_forgery_is_rejected(scenario: Scenario) -> None:
    prerequisites = scenario.request.prerequisites
    quality_payload = prerequisites.quality.model_dump(mode="python", exclude={"receipt_digest"})
    quality_payload["controlled_vocabulary_version"] = "99.0.0"
    quality_payload["receipt_digest"] = quality_support_receipt_digest(quality_payload)
    forged_quality = ProteinInferenceQualitySupportReceipt.model_validate(
        quality_payload, strict=True
    )
    with pytest.raises(ValidationError, match="exact projection"):
        ProteinInferenceSupportPrerequisites.model_validate(
            prerequisites.model_copy(update={"quality": forged_quality}), strict=True
        )

    harmonization_payload = prerequisites.harmonization.model_dump(
        mode="python", exclude={"receipt_digest"}
    )
    harmonization_payload["controlled_vocabulary_version"] = "99.0.0"
    harmonization_payload["receipt_digest"] = harmonization_support_receipt_digest(
        harmonization_payload
    )
    forged_harmonization = ProteinInferenceHarmonizationSupportReceipt.model_validate(
        harmonization_payload, strict=True
    )
    with pytest.raises(ValidationError, match="exact projection"):
        ProteinInferenceSupportPrerequisites.model_validate(
            prerequisites.model_copy(update={"harmonization": forged_harmonization}),
            strict=True,
        )


@pytest.mark.parametrize(
    "forged_digest",
    [M0307_ZERO_DIGEST, sha256_digest("stale-m0307-result")],
    ids=("zero", "stale"),
)
def test_zero_and_stale_result_digests_are_rejected(
    canonical_result: ProteinInferenceSupportRouteResult,
    forged_digest: str,
) -> None:
    payload = _payload(canonical_result)
    payload["result_digest"] = forged_digest
    with pytest.raises(ValidationError, match="result digest"):
        ProteinInferenceSupportRouteResult.model_validate(payload, strict=True)


def test_partial_dimension_remediation_tuple_is_rejected(
    canonical_result: ProteinInferenceSupportRouteResult,
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
            "decision": ProteinInferenceDimensionSupportDecision.OUTSIDE_DOMAIN,
            "reason_code": remediation.outside_reason_code,
        }
    )
    with pytest.raises(ValidationError, match="require remediation"):
        ProteinInferenceDimensionAssessment.model_validate(partial, strict=True)


def test_request_and_execution_context_identifier_mismatch_is_rejected(
    scenario: Scenario,
) -> None:
    request = scenario.request
    mismatched_context = request.context.model_copy(update={"request_id": "request." + ("f" * 64)})
    with pytest.raises(ValidationError, match="identifiers disagree"):
        RouteProteinInferenceSupportRequest.model_validate(
            request.model_copy(update={"context": mismatched_context}), strict=True
        )


def test_semantic_reorder_reconstructs_complete_request_and_result_equality(
    scenario: Scenario,
    canonical_result: ProteinInferenceSupportRouteResult,
) -> None:
    request = scenario.request
    payload = _payload(request)
    prerequisites = cast("dict[str, Any]", payload["prerequisites"])
    quality_result = cast("dict[str, Any]", prerequisites["quality_result"])
    harmonization_result = cast("dict[str, Any]", prerequisites["harmonization_result"])

    for field in ("metrics", "findings", "evidence", "limitations"):
        quality_result[field] = tuple(reversed(cast("tuple[object, ...]", quality_result[field])))
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

    quality_receipt = cast("dict[str, Any]", prerequisites["quality"])
    quality_receipt["metrics"] = tuple(
        reversed(cast("tuple[object, ...]", quality_receipt["metrics"]))
    )
    harmonization_receipt = cast("dict[str, Any]", prerequisites["harmonization"])
    harmonization_receipt["platform_level_ids"] = tuple(
        reversed(cast("tuple[object, ...]", harmonization_receipt["platform_level_ids"]))
    )

    profile = cast("dict[str, Any]", payload["profile"])
    envelopes = cast("tuple[dict[str, Any], ...]", profile["envelopes"])
    for envelope in envelopes:
        for field in (
            "approved_assay_protocol_versions",
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

    reordered = RouteProteinInferenceSupportRequest.model_validate(payload, strict=True)
    reordered_result = route_protein_inference_support(reordered)
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
    canonical_result: ProteinInferenceSupportRouteResult,
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
        ProteinInferenceSupportRouteResult.model_validate(payload, strict=True)


def test_abstention_field_accepts_exact_514_and_rejects_515(scenario: Scenario) -> None:
    envelope = scenario.request.profile.envelopes[0]
    remediation = envelope.remediations[0]
    abstention = ProteinInferenceAbstention(
        code=ProteinInferenceAbstentionCode.DIMENSION_OUTSIDE_DOMAIN,
        envelope_id=envelope.envelope_id,
        dimension=remediation.dimension,
        reason_code=remediation.outside_reason_code,
        remediation_code=remediation.remediation_code,
        remediation_path=remediation.remediation_path,
    )
    at_capacity = _ABSTENTION_CAPACITY_ADAPTER.validate_python(
        (abstention,) * M0307_MAX_ABSTENTIONS, strict=True
    )
    assert len(at_capacity) == M0307_MAX_ABSTENTIONS
    with pytest.raises(ValidationError, match="at most 514"):
        _ABSTENTION_CAPACITY_ADAPTER.validate_python(
            (abstention,) * (M0307_MAX_ABSTENTIONS + 1), strict=True
        )
