"""Compact public-contract checks for deterministic M01-07 routing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from evals.m01_07.run import build_scenario_request
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from glio_proteogen.contracts.m01_07 import (
    CriterionDecision,
    CriterionKind,
    EvidenceState,
    RouteDecision,
    RouteSupportRequest,
    SupportDimension,
    SupportRoutingResult,
    canonical_request_digest,
    contract_json_schema,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router import (
    route_support_request,
)

if TYPE_CHECKING:
    from glio_proteogen.contracts.m01_07.schema import ContractName

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    "name",
    ["request", "output", "policy", "profile", "criterion", "evidence", "assessment"],
)
def test_public_schema_is_valid_draft_2020_12(name: ContractName) -> None:
    schema = contract_json_schema(name)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert str(schema["$id"]).endswith(f":{name}")
    Draft202012Validator.check_schema(schema)


def test_contract_exposes_closed_dimensions_states_and_predicates() -> None:
    assert {item.value for item in SupportDimension} == {
        "assay",
        "specimen",
        "disease_class",
        "quality",
        "completeness",
        "platform",
        "reference",
        "intended_use",
    }
    assert {item.value for item in EvidenceState} == {
        "observed",
        "missing",
        "unknown",
        "not_applicable",
    }
    assert {item.value for item in CriterionKind} == {
        "term_in_set",
        "numeric_range",
        "boolean_equals",
        "required_present",
    }


def test_semantically_unordered_request_replays_to_one_result() -> None:
    request = build_scenario_request("supported")
    values = request.model_dump(mode="python")
    values["profile"]["criteria"] = tuple(reversed(values["profile"]["criteria"]))
    values["evidence"] = tuple(reversed(values["evidence"]))
    reordered = RouteSupportRequest.model_validate(values, strict=True)

    assert canonical_request_digest(reordered) == canonical_request_digest(request)
    assert route_support_request(reordered) == route_support_request(request)


def test_optional_not_applicable_is_the_only_nonblocking_nonobserved_state() -> None:
    not_applicable = route_support_request(
        build_scenario_request("optional_not_applicable")
    )
    assert not_applicable.decision is RouteDecision.SUPPORTED

    request = build_scenario_request("optional_not_applicable")
    evidence = tuple(
        item.model_copy(update={"state": EvidenceState.MISSING})
        if item.dimension is SupportDimension.COMPLETENESS
        else item
        for item in request.evidence
    )
    missing = route_support_request(request.model_copy(update={"evidence": evidence}))

    assessment = next(
        item
        for item in missing.assessments
        if item.dimension is SupportDimension.COMPLETENESS
    )
    assert assessment.decision is CriterionDecision.INDETERMINATE
    assert assessment.blocks_route is True
    assert missing.decision is RouteDecision.ABSTAINED


def test_observed_unsupported_optional_criterion_always_abstains() -> None:
    result = route_support_request(
        build_scenario_request(
            "unsupported_matrix",
            unsupported_dimension=SupportDimension.COMPLETENESS,
        )
    )

    assert result.decision is RouteDecision.ABSTAINED
    assert next(
        item
        for item in result.assessments
        if item.dimension is SupportDimension.COMPLETENESS
    ).decision is CriterionDecision.UNSUPPORTED


def test_request_rejects_configuration_and_value_type_mismatches() -> None:
    request = build_scenario_request("supported")
    values = request.model_dump(mode="python")
    values["context"]["references"]["approved_configuration"]["evidence"]["digest"] = (
        "sha256:" + ("f" * 64)
    )
    with pytest.raises(ValidationError, match="approved configuration"):
        RouteSupportRequest.model_validate(values, strict=True)

    values = request.model_dump(mode="python")
    completeness = next(
        item for item in values["evidence"] if item["dimension"] == "completeness"
    )
    completeness["value"] = True
    with pytest.raises(ValidationError, match="support evidence"):
        RouteSupportRequest.model_validate(values, strict=True)


def test_result_rejects_forged_route_and_revoked_authorization() -> None:
    result = route_support_request(build_scenario_request("missing_required"))
    forged = result.model_dump(mode="python")
    forged["decision"] = RouteDecision.SUPPORTED
    forged["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="decision contradicts"):
        SupportRoutingResult.model_validate(forged, strict=True)

    supported = route_support_request(build_scenario_request("supported"))
    forged = supported.model_dump(mode="python")
    forged["provenance"]["consent_state"] = ConsentState.REVOKED
    consent = next(
        item
        for item in forged["provenance"]["control_decisions"]
        if item["role"] == "consent"
    )
    consent["state"] = "revoked"
    forged["result_digest"] = "sha256:" + ("0" * 64)
    with pytest.raises(ValidationError, match="accepted authorization"):
        SupportRoutingResult.model_validate(forged, strict=True)
