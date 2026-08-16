"""Focused schema and claim-ceiling smoke for provisional M16-04."""

from jsonschema import Draft202012Validator

from glio_proteogen.contracts.m16_04 import (
    M1604_OUTPUT_MEDIA_TYPE,
    M1604_PROVISIONAL_ABI,
    ClaimCeiling,
    DisplaySemantic,
    IntendedUseContext,
    PolicyDecision,
    PolicyDecisionStatus,
    contract_json_schemas,
)

_SCHEMA_COUNT = 7


def test_provisional_schemas_require_registered_use_and_claim_ceiling() -> None:
    schemas = contract_json_schemas()
    assert len(schemas) == _SCHEMA_COUNT
    assert tuple(schemas) == (
        "request",
        "output",
        "policy",
        "intended-use-object",
        "policy-decision",
        "configuration",
        "finding",
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        metadata = schema["x-glio-contract"]
        assert metadata["provisionalAbi"] is True
        assert metadata["registeredIntendedUseRequired"] is True
        assert metadata["claimCeilingRequired"] is True
        assert metadata["unsupportedToNegative"] is False
    assert schemas["output"]["x-glio-contract"]["outputMediaType"] == M1604_OUTPUT_MEDIA_TYPE
    assert M1604_PROVISIONAL_ABI is True


def test_policy_decision_is_registered_and_auditable() -> None:
    decision = PolicyDecision(
        decision_id="decision-1",
        status=PolicyDecisionStatus.QUALIFIED,
        policy_id="policy-1",
        reasons=("Evidence is suitable for scientific review only.",),
    )
    assert decision.registered_intended_use is True
    assert decision.auditable is True


def test_intended_use_enums_expose_bounded_semantics() -> None:
    assert IntendedUseContext.SCIENTIFIC_VALIDATION.value == "scientific_validation"
    assert ClaimCeiling.MECHANISTIC_HYPOTHESIS.value == "mechanistic_hypothesis"
    assert DisplaySemantic.REVIEW_ONLY.value == "review_only"
