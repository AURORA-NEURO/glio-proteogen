"""Machine-readable contract and component closure for M05-01."""

from __future__ import annotations

import json

import pytest
from evals.m05_01.run import build_scenario_request
from pydantic import BaseModel, ValidationError

from glio_proteogen.contracts.m05_01 import (
    M0501_MAX_APPROVED_REFERENCE_BUNDLES,
    M0501_MAX_APPROVED_VERSIONS,
    M0501_MAX_COMPATIBILITY_RULES,
    M0501_MAX_METADATA_FIELDS,
    M0501_MAX_UNIT_POLICIES,
    M0501_MAX_VOCABULARY_TERMS,
    EvaluatePtmLocalizationProtocolRequest,
    PtmLocalizationCompatibilityRule,
    PtmLocalizationControlledVocabulary,
    PtmLocalizationMetadataFieldPolicy,
    PtmLocalizationProtocolConformanceDisposition,
    PtmLocalizationProtocolReceipt,
    PtmLocalizationProtocolSchema,
    PtmLocalizationReferenceBundle,
    PtmLocalizationUnitPolicy,
    ReviewedPtmLocalizationConformanceProfile,
    contract_json_schema,
    contract_json_schemas,
    expected_protocol_receipt,
    preflight_authorized,
    protocol_evidence_index,
    replay_ptm_localization_protocol_request,
)
from glio_proteogen.contracts.m05_01 import v1 as m0501_v1
from glio_proteogen.kernel.canonical import canonical_json_bytes
from glio_proteogen.modules.c05_ptm_localization.m05_01_protocol_metadata import (
    evaluate_ptm_localization_protocol,
)

SCHEMA_NAMES = (
    "request",
    "output",
    "protocol",
    "profile",
    "reference-bundle",
    "reference-cardinality",
    "controlled-vocabulary",
    "unit-policy",
    "metadata-field-policy",
    "compatibility-policy",
    "assay-specimen-policy",
    "variant-peptide-handoff",
    "receipt",
)


@pytest.mark.contract
def test_exact_thirteen_json_schema_2020_12_exports() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == SCHEMA_NAMES
    for name, schema in schemas.items():
        typed_schema = schema if isinstance(schema, dict) else {}
        assert schema == contract_json_schema(name)
        assert typed_schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert isinstance(typed_schema["$id"], str)
        assert typed_schema["$id"].endswith(f":{name}")
        metadata = typed_schema["x-glio-contract"]
        assert isinstance(metadata, dict)
        assert metadata["parentTarget"] == "variant_peptide"
        assert not metadata["scientificInference"]
        json.dumps(schema, sort_keys=True)


@pytest.mark.contract
def test_maximum_supported_shape_is_constructible_and_total() -> None:
    request = build_scenario_request("maximum_profile_shape_conforms")
    protocol = request.protocol_schema
    profile = request.conformance_profile
    result = evaluate_ptm_localization_protocol(request)

    assert len(profile.approved_reference_bundles) == M0501_MAX_APPROVED_REFERENCE_BUNDLES
    assert len(profile.approved_protocol_versions) == M0501_MAX_APPROVED_VERSIONS
    assert len(profile.approved_vocabulary_versions) == M0501_MAX_APPROVED_VERSIONS
    assert len(protocol.controlled_vocabularies) == M0501_MAX_APPROVED_VERSIONS
    assert len(protocol.controlled_vocabularies[0].terms) == M0501_MAX_VOCABULARY_TERMS
    assert len(protocol.unit_policies) == M0501_MAX_UNIT_POLICIES
    assert len(protocol.metadata_fields) == M0501_MAX_METADATA_FIELDS
    assert len(protocol.compatibility_rules) == M0501_MAX_COMPATIBILITY_RULES
    assert result.disposition is PtmLocalizationProtocolConformanceDisposition.CONFORMANT


@pytest.mark.parametrize(
    ("component", "mutation"),
    [
        ("reference_bundle", "duplicate_reference"),
        ("reference_bundle", "duplicate_role"),
        ("vocabulary", "duplicate_term_id"),
        ("vocabulary", "duplicate_meaning"),
        ("unit", "bad_identifier"),
        ("metadata", "coerced_boolean"),
        ("metadata", "bad_cardinality"),
        ("compatibility", "same_dimension"),
        ("protocol", "duplicate_unit_role"),
        ("protocol", "duplicate_evidence"),
        ("profile", "duplicate_bundle"),
        ("profile", "future_review"),
    ],
)
def test_component_relational_invariants_reject_invalid_shapes(  # noqa: C901, PLR0912, PLR0915
    component: str,
    mutation: str,
) -> None:
    request = build_scenario_request()
    protocol = request.protocol_schema
    profile = request.conformance_profile
    model: type[BaseModel]
    if component == "reference_bundle":
        payload = protocol.reference_bundle.model_dump(mode="python")
        if mutation == "duplicate_reference":
            payload["references"][1]["reference"] = payload["references"][0]["reference"]
        else:
            payload["references"][1]["role"] = payload["references"][0]["role"]
        model = PtmLocalizationReferenceBundle
    elif component == "vocabulary":
        payload = protocol.controlled_vocabularies[0].model_dump(mode="python")
        if mutation == "duplicate_term_id":
            payload["terms"][1]["term_id"] = payload["terms"][0]["term_id"]
        else:
            payload["terms"][1]["meaning"] = payload["terms"][0]["meaning"]
        model = PtmLocalizationControlledVocabulary
    elif component == "unit":
        payload = protocol.unit_policies[0].model_dump(mode="python")
        payload["unit_policy_id"] = "unit.not-opaque"
        model = PtmLocalizationUnitPolicy
    elif component == "metadata":
        payload = protocol.metadata_fields[0].model_dump(mode="python")
        if mutation == "coerced_boolean":
            payload["required"] = 1
        else:
            payload["maximum_cardinality"] = 0
        model = PtmLocalizationMetadataFieldPolicy
    elif component == "compatibility":
        payload = protocol.compatibility_rules[0].model_dump(mode="python")
        payload["right_dimension"] = payload["left_dimension"]
        model = PtmLocalizationCompatibilityRule
    elif component == "protocol":
        payload = protocol.model_dump(mode="python")
        if mutation == "duplicate_unit_role":
            payload["unit_policies"][1]["quantity"] = payload["unit_policies"][0]["quantity"]
        else:
            payload["variant_peptide_handoff"]["evidence"] = payload["assay_specimen_policy"][
                "evidence"
            ]
        model = PtmLocalizationProtocolSchema
    else:
        payload = profile.model_dump(mode="python")
        if mutation == "duplicate_bundle":
            payload["approved_reference_bundles"] = (
                payload["approved_reference_bundles"][0],
                payload["approved_reference_bundles"][0],
            )
            model = ReviewedPtmLocalizationConformanceProfile
        else:
            request_payload = request.model_dump(mode="python")
            request_payload["conformance_profile"]["reviewed_at"] = "2027-01-01T00:00:00Z"
            with pytest.raises(ValidationError):
                type(request).model_validate_json(
                    canonical_json_bytes(request_payload), strict=True
                )
            return
    with pytest.raises(ValidationError):
        model.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "path",
    [
        ("request_id",),
        ("context", "request_id"),
        ("conformance_profile", "protocol_schema_digest"),
        ("conformance_profile", "protocol_schema_id"),
        ("context", "references", "approved_configuration", "evidence", "digest"),
    ],
)
def test_request_binding_forgery_is_rejected(path: tuple[str, ...]) -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="python")
    cursor = payload
    for segment in path[:-1]:
        cursor = cursor[segment]
    leaf = path[-1]
    if leaf.endswith("digest"):
        cursor[leaf] = "sha256:" + ("f" * 64)
    elif leaf.endswith("id"):
        namespace = "request" if leaf == "request_id" else "schema"
        cursor[leaf] = f"{namespace}." + ("f" * 64)
    with pytest.raises(ValidationError):
        type(request).model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "reference_media_type",
        "duplicate_profile_identity",
        "authorization_state",
        "configuration_binding",
        "control_evidence_identity",
    ],
)
def test_closed_relational_request_mutations_reach_exact_invariant(
    mutation: str,
) -> None:
    request = build_scenario_request()
    payload = request.model_dump(mode="python")
    if mutation == "reference_media_type":
        payload["protocol_schema"]["reference_bundle"]["references"][0]["reference"][
            "media_type"
        ] = "application/vnd.glio-proteogen.m05-01.policy+json"
    elif mutation == "duplicate_profile_identity":
        profile = payload["conformance_profile"]
        duplicate = dict(profile["approved_reference_bundles"][0])
        duplicate["bundle_digest"] = "sha256:" + ("f" * 64)
        profile["approved_reference_bundles"] = (
            *profile["approved_reference_bundles"],
            duplicate,
        )
    elif mutation == "authorization_state":
        payload["context"]["references"]["quality"]["state"] = "rejected"
    elif mutation == "configuration_binding":
        evidence = payload["context"]["references"]["approved_configuration"]["evidence"]
        evidence["digest"] = "sha256:" + ("f" * 64)
        evidence["artifact_id"] = "evidence." + ("f" * 64)
    else:
        references = payload["context"]["references"]
        references["provenance"]["evidence"] = references["quality"]["evidence"]

    with pytest.raises(ValidationError):
        EvaluatePtmLocalizationProtocolRequest.model_validate(payload, strict=True)


def test_request_cap_and_replay_reject_semantically_mutated_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = build_scenario_request()
    monkeypatch.setattr(
        m0501_v1,
        "M0501_MAX_CANONICAL_REQUEST_BYTES",
        len(canonical_json_bytes(request)) - 1,
    )
    with pytest.raises(ValidationError, match="byte cap"):
        EvaluatePtmLocalizationProtocolRequest.model_validate(
            request.model_dump(mode="python"), strict=True
        )

    monkeypatch.undo()
    request = build_scenario_request("maximum_profile_shape_conforms")
    profile = request.conformance_profile.model_copy(
        update={
            "approved_protocol_versions": tuple(
                reversed(request.conformance_profile.approved_protocol_versions)
            )
        }
    )
    forged = request.model_copy(update={"conformance_profile": profile})
    with pytest.raises(ValueError, match="not equal to its strict replay"):
        replay_ptm_localization_protocol_request(forged)


@pytest.mark.parametrize(
    "mutation",
    ["non_string_key", "context", "references", "control"],
)
def test_authorization_preflight_rejects_malformed_builtin_shapes(mutation: str) -> None:
    payload = build_scenario_request().model_dump(mode="python")
    if mutation == "non_string_key":
        payload[1] = "hostile-key"
    elif mutation == "context":
        payload["context"] = []
    elif mutation == "references":
        payload["context"]["references"] = []
    else:
        payload["context"]["references"]["quality"] = []
    with pytest.raises(ValueError, match="authorization preflight"):
        preflight_authorized(payload)


def test_receipt_sections_digest_and_evidence_index_are_closed() -> None:
    request = build_scenario_request()
    receipt = expected_protocol_receipt(request)
    sections = receipt.model_dump(mode="python")
    sections["sections"][1]["section"] = sections["sections"][0]["section"]
    with pytest.raises(ValidationError, match="every conformance section"):
        PtmLocalizationProtocolReceipt.model_validate(sections, strict=True)

    stale_digest = receipt.model_dump(mode="python")
    stale_digest["receipt_digest"] = "sha256:" + ("f" * 64)
    with pytest.raises(ValidationError, match="canonical receipt content"):
        PtmLocalizationProtocolReceipt.model_validate(stale_digest, strict=True)

    references = request.context.references
    forged_references = references.model_copy(
        update={
            "provenance": references.provenance.model_copy(
                update={"evidence": references.quality.evidence}
            )
        }
    )
    forged = request.model_copy(
        update={"context": request.context.model_copy(update={"references": forged_references})}
    )
    with pytest.raises(ValueError, match="15 distinct evidence"):
        protocol_evidence_index(forged)
