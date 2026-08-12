"""Focused qualification for the public M01-07 router."""

from __future__ import annotations

from typing import cast

import pytest
from evals.m01_07.run import build_scenario_request

from glio_proteogen.contracts.m01_07 import (
    CriterionDecision,
    EvidenceState,
    RouteDecision,
    RouteSupportRequest,
    SupportDimension,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router import (
    M0107Plugin,
    M0107Service,
    M0107SupportRouter,
    SupportRoutingAuthorizationError,
    ValidatedM0107Request,
    preflight_support_routing_authorization,
    route_support_request,
)


def test_all_dimensions_supported_and_replay_identically() -> None:
    request = build_scenario_request("supported")

    result = route_support_request(request)
    replay = M0107SupportRouter().route(request)

    assert replay == result
    assert result.decision is RouteDecision.SUPPORTED
    assert all(item.decision is CriterionDecision.SUPPORTED for item in result.assessments)
    assert result.human_review_required is False


def test_observed_unsupported_dimension_abstains_with_remediation() -> None:
    request = build_scenario_request(
        "unsupported_matrix",
        unsupported_dimension=SupportDimension.ASSAY,
    )

    result = route_support_request(request)
    assessment = result.assessments[0]

    assert result.decision is RouteDecision.ABSTAINED
    assert assessment.dimension is SupportDimension.ASSAY
    assert assessment.decision is CriterionDecision.UNSUPPORTED
    assert assessment.blocks_route is True
    assert assessment.remediation_code == "remediate.assay"


@pytest.mark.parametrize(
    ("case", "dimension", "state"),
    [
        ("missing_required", SupportDimension.QUALITY, EvidenceState.MISSING),
        ("unknown_required", SupportDimension.REFERENCE, EvidenceState.UNKNOWN),
    ],
)
def test_required_absent_evidence_is_indeterminate_and_abstains(
    case: str,
    dimension: SupportDimension,
    state: EvidenceState,
) -> None:
    result = route_support_request(build_scenario_request(case))
    assessment = next(item for item in result.assessments if item.dimension is dimension)

    assert assessment.evidence_state is state
    assert assessment.decision is CriterionDecision.INDETERMINATE
    assert assessment.blocks_route is True
    assert result.decision is RouteDecision.ABSTAINED


def test_allowed_optional_not_applicable_is_supported() -> None:
    result = route_support_request(build_scenario_request("optional_not_applicable"))
    assessment = next(
        item for item in result.assessments if item.dimension is SupportDimension.COMPLETENESS
    )

    assert assessment.evidence_state is EvidenceState.NOT_APPLICABLE
    assert assessment.decision is CriterionDecision.SUPPORTED
    assert assessment.blocks_route is False
    assert result.decision is RouteDecision.SUPPORTED


def test_multiple_failures_remain_in_canonical_dimension_order() -> None:
    result = route_support_request(build_scenario_request("multiple_failures"))
    blocked = tuple(item.dimension for item in result.assessments if item.blocks_route)

    assert blocked == (
        SupportDimension.ASSAY,
        SupportDimension.QUALITY,
        SupportDimension.REFERENCE,
    )


def test_reordered_request_is_semantically_identical() -> None:
    request = build_scenario_request("supported")
    reordered = RouteSupportRequest(
        context=request.context,
        profile=type(request.profile)(
            profile_id=request.profile.profile_id,
            version=request.profile.version,
            criteria=tuple(reversed(request.profile.criteria)),
            evidence=request.profile.evidence,
        ),
        policy=request.policy,
        evidence=tuple(reversed(request.evidence)),
    )

    assert route_support_request(request) == route_support_request(reordered)


def test_service_and_json_plugin_execute() -> None:
    request = build_scenario_request("supported")
    service = M0107Service()
    plugin = M0107Plugin(service)

    assert service.execute(request).decision is RouteDecision.SUPPORTED
    token = plugin.validate(request.model_dump_json())
    assert isinstance(token, ValidatedM0107Request)
    assert plugin.run(token).decision is RouteDecision.SUPPORTED
    assert plugin.descriptor().module_id == "GLIO-PROTEOGEN-M01-07"


def test_plugin_rejects_unvalidated_token() -> None:
    with pytest.raises(TypeError, match="validated request token"):
        M0107Plugin(M0107Service()).run(cast("ValidatedM0107Request", object()))


def test_plugin_descriptor_matches_module_ownership_and_gate() -> None:
    descriptor = M0107Plugin(M0107Service()).descriptor()

    assert descriptor.module_id == "GLIO-PROTEOGEN-M01-07"
    assert descriptor.owner == "Data engineering"
    assert descriptor.safety_class == "S2"
    assert descriptor.gate == "G1"


def test_raw_authorization_rejects_before_evidence_access() -> None:
    payload = build_scenario_request("supported").model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "revoked"
    payload["evidence"] = object()

    with pytest.raises(SupportRoutingAuthorizationError):
        preflight_support_routing_authorization(payload)
