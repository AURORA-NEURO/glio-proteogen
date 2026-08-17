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
    PtmLocalizationCompatibilityRule,
    PtmLocalizationControlledVocabulary,
    PtmLocalizationMetadataFieldPolicy,
    PtmLocalizationProtocolConformanceDisposition,
    PtmLocalizationProtocolSchema,
    PtmLocalizationReferenceBundle,
    PtmLocalizationUnitPolicy,
    ReviewedPtmLocalizationConformanceProfile,
    contract_json_schema,
    contract_json_schemas,
)
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
