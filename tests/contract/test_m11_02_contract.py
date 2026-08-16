"""Focused schema and context-stratifier smoke for provisional M11-02."""

from typing import cast

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m11_02 import (
    M1102_HYPOTHESIS_MEDIA_TYPE,
    M1102_OUTPUT_MEDIA_TYPE,
    ContextDimension,
    ContextObservation,
    ContextStratificationPolicy,
    ContextStratificationRule,
    MechanismApplicability,
    MechanismApplicabilityStatus,
    contract_json_schemas,
    normalized_request,
    normalized_result_payload,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ArtifactReference

_DIGEST = "sha256:" + ("a" * 64)


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=name,
        version="0.1.0",
        digest=_DIGEST,
        media_type="application/json",
    )


def test_schema_inventory_is_strict_and_explicit() -> None:
    schemas = contract_json_schemas()
    assert tuple(schemas) == (
        "request",
        "output",
        "observation",
        "profile",
        "policy",
        "rule",
        "mechanism-applicability",
        "diagnostic",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = cast("dict[str, object]", schema["x-glio-contract"])
        assert metadata["provisionalAbi"] is True
        assert metadata["contextDimensionsExplicit"] is True
        assert metadata["mechanismApplicabilityExplicit"] is True
        assert metadata["supportBoundariesRequired"] is True
        assert metadata["prohibitedProxyBlocking"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1102_OUTPUT_MEDIA_TYPE
    assert schemas["request"]["x-glio-contract"]["hypothesisInputMediaType"] == (
        M1102_HYPOTHESIS_MEDIA_TYPE
    )


def test_context_policy_observation_and_mechanism_smoke() -> None:
    rule = ContextStratificationRule(
        rule_id="rule.m1102.disease",
        dimension=ContextDimension.DISEASE_CLASS,
        criterion="disease class is declared by approved context evidence",
        allowed_values=("glioma",),
        prohibited_proxies=("postcode",),
    )
    policy = ContextStratificationPolicy(
        policy_id="policy.m1102.smoke",
        version="0.1.0",
        dimensions=(ContextDimension.DISEASE_CLASS,),
        rules=(rule,),
        minimum_support_score=0.8,
    )
    observation = ContextObservation(
        dimension=ContextDimension.DISEASE_CLASS,
        value="glioma",
        source_artifact=_artifact("artifact.context"),
        support_score=0.95,
    )
    mechanism = MechanismApplicability(
        mechanism_id="mechanism.variant-peptide",
        status=MechanismApplicabilityStatus.APPLICABLE,
        rationale="Mechanism is applicable within the declared disease context.",
        context_dimensions=(ContextDimension.DISEASE_CLASS,),
    )
    assert policy.locked is True
    assert observation.support_score >= policy.minimum_support_score
    assert mechanism.status is MechanismApplicabilityStatus.APPLICABLE


def test_canonical_helpers_accept_plain_mappings_and_strip_result_digest() -> None:
    request = {"request_id": "request.synthetic"}
    result = {"result_digest": "sha256:" + ("b" * 64), "value": 1}
    assert normalized_request(request) == request
    assert normalized_result_payload(result) == {"value": 1}
    assert result_payload_digest(result).startswith("sha256:")
