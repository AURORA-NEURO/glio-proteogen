"""High-value M01-07 replay, capacity, and relational boundary regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from evals.m01_07.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m01_07 import (
    CriterionAssessment,
    CriterionDecision,
    CriterionKind,
    EvidenceState,
    RouteDecision,
    RouteSupportRequest,
    SupportCriterion,
    SupportDimension,
    SupportEvidence,
    SupportRoutingProfile,
    SupportRoutingResult,
    configuration_digest,
    evidence_digest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    ExecutionContext,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router import (
    route_support_request,
)

pytestmark = pytest.mark.contract

_ZERO_DIGEST = "sha256:" + ("0" * 64)
_OTHER_DIGEST = "sha256:" + ("f" * 64)
_CAPACITY_CRITERIA = 157
_COMPACT_PROVENANCE_BOUND = 16


def _bind_configuration(
    request: RouteSupportRequest,
    profile: SupportRoutingProfile,
) -> ExecutionContext:
    approved = request.context.references.approved_configuration
    approved_evidence = approved.evidence.model_copy(
        update={"digest": configuration_digest(profile, request.policy)}
    )
    references = request.context.references.model_copy(
        update={
            "approved_configuration": approved.model_copy(
                update={"evidence": approved_evidence}
            )
        }
    )
    return request.context.model_copy(update={"references": references})


def _criterion_values(kind: CriterionKind) -> dict[str, Any]:
    criterion = build_scenario_request("supported").profile.criteria[0]
    values = criterion.model_dump(mode="python")
    values.update(
        {
            "kind": kind,
            "allowed_terms": (),
            "minimum": None,
            "maximum": None,
            "expected_bool": None,
            "unit": None,
        }
    )
    if kind is CriterionKind.TERM_IN_SET:
        values["allowed_terms"] = ("supported.assay",)
    elif kind is CriterionKind.NUMERIC_RANGE:
        values.update({"minimum": 0.0, "maximum": 1.0, "unit": "ratio"})
    elif kind is CriterionKind.BOOLEAN_EQUALS:
        values["expected_bool"] = True
    return values


def _assessment_values(
    state: EvidenceState,
    decision: CriterionDecision,
    *,
    required: bool = True,
    allow_not_applicable: bool = False,
) -> dict[str, Any]:
    result = route_support_request(build_scenario_request("supported"))
    values = result.assessments[0].model_dump(mode="python")
    values.update(
        {
            "required": required,
            "allow_not_applicable": allow_not_applicable,
            "evidence_state": state,
            "decision": decision,
            "blocks_route": decision is not CriterionDecision.SUPPORTED,
            "reason_code": None,
            "remediation_code": None,
            "remediation_path": None,
        }
    )
    if decision is not CriterionDecision.SUPPORTED:
        values.update(
            {
                "reason_code": "support.synthetic.indeterminate",
                "remediation_code": "remediation.synthetic.review",
                "remediation_path": "review synthetic evidence",
            }
        )
    return values


def _result_values() -> dict[str, Any]:
    result = route_support_request(build_scenario_request("supported"))
    values = result.model_dump(mode="python")
    values["result_digest"] = _ZERO_DIGEST
    return values


def _set_path(
    values: dict[str, Any],
    path: tuple[str, ...],
    replacement: object,
) -> None:
    target = values
    for key in path[:-1]:
        target = cast("dict[str, Any]", target[key])
    target[path[-1]] = replacement


def test_reference_order_replays_to_identical_public_result() -> None:
    request = build_scenario_request("supported")
    first = request.evidence[0]
    original = first.evidence[0]
    second = original.model_copy(
        update={
            "artifact_id": "artifact.synthetic.evidence.assay.second",
            "digest": "sha256:" + ("1" * 64),
        }
    )
    forward_item = first.model_copy(update={"evidence": (original, second)})
    reverse_item = first.model_copy(update={"evidence": (second, original)})
    forward = request.model_copy(
        update={"evidence": (forward_item, *request.evidence[1:])}
    )
    reverse = request.model_copy(
        update={"evidence": (reverse_item, *request.evidence[1:])}
    )

    forward_result = route_support_request(forward)
    reverse_result = route_support_request(reverse)

    assert evidence_digest(forward_item) == evidence_digest(reverse_item)
    assert forward_result == reverse_result
    assert forward_result.model_dump_json() == reverse_result.model_dump_json()


def test_max_reference_shape_routes_with_compact_provenance() -> None:
    request = build_scenario_request("supported")
    criteria: list[SupportCriterion] = []
    evidence: list[SupportEvidence] = []
    for index in range(_CAPACITY_CRITERIA):
        source_criterion = request.profile.criteria[index % len(request.profile.criteria)]
        source_evidence = request.evidence[index % len(request.evidence)]
        evidence_id = f"evidence.capacity.{index:03d}"
        criteria.append(
            source_criterion.model_copy(
                update={
                    "criterion_id": f"criterion.capacity.{index:03d}",
                    "evidence_id": evidence_id,
                }
            )
        )
        references = tuple(
            source_evidence.evidence[0].model_copy(
                update={
                    "artifact_id": f"artifact.capacity.{index:03d}.{offset:02d}",
                    "digest": f"sha256:{(index * 64 + offset + 1):064x}",
                }
            )
            for offset in range(64)
        )
        evidence.append(
            source_evidence.model_copy(
                update={"evidence_id": evidence_id, "evidence": references}
            )
        )
    profile = SupportRoutingProfile(
        profile_id=request.profile.profile_id,
        version=request.profile.version,
        criteria=tuple(criteria),
        evidence=request.profile.evidence,
    )
    large_request = RouteSupportRequest(
        context=_bind_configuration(request, profile),
        profile=profile,
        policy=request.policy,
        evidence=tuple(evidence),
    )

    result = route_support_request(large_request)

    assert len(result.assessments) == _CAPACITY_CRITERIA
    assert len(result.provenance.input_digests) <= _COMPACT_PROVENANCE_BOUND
    assert {
        result.request_digest,
        result.profile_digest,
        result.policy_digest,
        result.configuration_digest,
    }.issubset(result.provenance.input_digests)


@pytest.mark.parametrize(
    ("kind", "updates", "message"),
    [
        (
            CriterionKind.TERM_IN_SET,
            {"required": True, "allow_not_applicable": True},
            "cannot allow not-applicable",
        ),
        (CriterionKind.TERM_IN_SET, {"allowed_terms": ()}, "unique allowed terms"),
        (
            CriterionKind.TERM_IN_SET,
            {"allowed_terms": ("term.a", "term.a")},
            "unique allowed terms",
        ),
        (CriterionKind.TERM_IN_SET, {"minimum": 0.0}, "other predicate fields"),
        (
            CriterionKind.NUMERIC_RANGE,
            {"minimum": None, "maximum": None},
            "at least one bound",
        ),
        (CriterionKind.NUMERIC_RANGE, {"unit": None}, "require a unit"),
        (
            CriterionKind.NUMERIC_RANGE,
            {"allowed_terms": ("term.a",)},
            "cannot carry term or boolean",
        ),
        (
            CriterionKind.NUMERIC_RANGE,
            {"minimum": 2.0, "maximum": 1.0},
            "bounds must be ordered",
        ),
        (
            CriterionKind.BOOLEAN_EQUALS,
            {"expected_bool": None},
            "require an expected value",
        ),
        (
            CriterionKind.BOOLEAN_EQUALS,
            {"unit": "1"},
            "cannot carry other predicate fields",
        ),
        (
            CriterionKind.REQUIRED_PRESENT,
            {"expected_bool": True},
            "cannot carry comparison fields",
        ),
    ],
)
def test_criterion_predicates_reject_ambiguous_shapes(
    kind: CriterionKind,
    updates: dict[str, object],
    message: str,
) -> None:
    values = _criterion_values(kind)
    values.update(updates)

    with pytest.raises(ValidationError, match=message):
        SupportCriterion.model_validate(values, strict=True)


@pytest.mark.parametrize("case", ["duplicate_id", "missing_dimension"])
def test_profile_requires_unique_criteria_and_all_dimensions(case: str) -> None:
    values = build_scenario_request("supported").profile.model_dump(mode="python")
    criteria = list(values["criteria"])
    if case == "duplicate_id":
        criteria[-1]["criterion_id"] = criteria[0]["criterion_id"]
        message = "identifiers must be unique"
    else:
        criteria[-1]["dimension"] = SupportDimension.ASSAY
        message = "cover every routing dimension"
    values["criteria"] = tuple(criteria)

    with pytest.raises(ValidationError, match=message):
        SupportRoutingProfile.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"value": None}, "observed support evidence requires a value"),
        (
            {"state": EvidenceState.MISSING, "value": "unexpected"},
            "non-observed support evidence",
        ),
        (
            {"state": EvidenceState.UNKNOWN, "value": None, "unit": "1"},
            "non-observed support evidence",
        ),
        ({"value": float("nan")}, "finite number"),
    ],
)
def test_evidence_state_and_value_are_relationally_closed(
    updates: dict[str, object],
    message: str,
) -> None:
    values = build_scenario_request("supported").evidence[0].model_dump(mode="python")
    values.update(updates)

    with pytest.raises(ValidationError, match=message):
        SupportEvidence.model_validate(values, strict=True)


def test_evidence_references_must_be_unique() -> None:
    values = build_scenario_request("supported").evidence[0].model_dump(mode="python")
    reference = values["evidence"][0]
    values["evidence"] = (reference, reference)

    with pytest.raises(ValidationError, match="references must be unique"):
        SupportEvidence.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("criteria_cap", "exceeds the active policy"),
        ("evidence_cap", "exceeds the active policy"),
        ("duplicate_evidence", "identifiers must be unique"),
        ("unclosed_evidence", "identifiers must close exactly"),
        ("wrong_dimension", "dimension contradicts"),
        ("configuration", "approved configuration"),
        ("consent", "consent does not authorize"),
        ("identity", "identity lineage must be resolved"),
        ("upstream", "every upstream control"),
    ],
)
def test_request_rejects_policy_closure_and_authorization_failures(
    case: str,
    message: str,
) -> None:
    values = build_scenario_request("supported").model_dump(mode="python")
    if case == "criteria_cap":
        values["policy"]["max_criteria"] = 7
    elif case == "evidence_cap":
        values["policy"]["max_evidence"] = 7
    elif case == "duplicate_evidence":
        values["evidence"][-1]["evidence_id"] = values["evidence"][0]["evidence_id"]
    elif case == "unclosed_evidence":
        values["evidence"][-1]["evidence_id"] = "evidence.unreferenced"
    elif case == "wrong_dimension":
        values["evidence"][0]["dimension"] = SupportDimension.SPECIMEN
    elif case == "configuration":
        values["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = _OTHER_DIGEST
    elif case == "consent":
        values["context"]["references"]["consent"]["state"] = ConsentState.REVOKED
    elif case == "identity":
        values["context"]["references"]["identity_lineage"][
            "state"
        ] = IdentityLineageState.UNRESOLVED
    else:
        values["context"]["references"]["support"][
            "state"
        ] = UpstreamDecisionState.REJECTED

    with pytest.raises(ValidationError, match=message):
        RouteSupportRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("kind", "value", "unit", "message"),
    [
        (CriterionKind.TERM_IN_SET, 1.0, None, "text and unitless"),
        (CriterionKind.TERM_IN_SET, "supported.assay", "1", "text and unitless"),
        (CriterionKind.NUMERIC_RANGE, "0.5", "ratio", "match its criterion unit"),
        (CriterionKind.NUMERIC_RANGE, 0.5, "%", "match its criterion unit"),
        (CriterionKind.BOOLEAN_EQUALS, "true", None, "boolean and unitless"),
        (CriterionKind.BOOLEAN_EQUALS, True, "1", "boolean and unitless"),
        (CriterionKind.REQUIRED_PRESENT, "present", "1", "presence.*unitless"),
    ],
)
def test_request_rejects_observed_type_and_unit_mismatches(
    kind: CriterionKind,
    value: object,
    unit: str | None,
    message: str,
) -> None:
    request = build_scenario_request("supported")
    criterion = SupportCriterion.model_validate(_criterion_values(kind), strict=True)
    profile = request.profile.model_copy(
        update={"criteria": (criterion, *request.profile.criteria[1:])}
    )
    item = request.evidence[0].model_copy(update={"value": value, "unit": unit})

    with pytest.raises(ValidationError, match=message):
        RouteSupportRequest(
            context=_bind_configuration(request, profile),
            profile=profile,
            policy=request.policy,
            evidence=(item, *request.evidence[1:]),
        )


@pytest.mark.parametrize(
    ("state", "decision", "policy", "message"),
    [
        (
            EvidenceState.OBSERVED,
            CriterionDecision.INDETERMINATE,
            (True, False),
            "observed evidence cannot produce an indeterminate",
        ),
        (
            EvidenceState.MISSING,
            CriterionDecision.SUPPORTED,
            (True, False),
            "missing or unknown evidence must remain indeterminate",
        ),
        (
            EvidenceState.UNKNOWN,
            CriterionDecision.UNSUPPORTED,
            (True, False),
            "missing or unknown evidence must remain indeterminate",
        ),
        (
            EvidenceState.NOT_APPLICABLE,
            CriterionDecision.INDETERMINATE,
            (False, True),
            "not-applicable evidence contradicts criterion policy",
        ),
        (
            EvidenceState.NOT_APPLICABLE,
            CriterionDecision.SUPPORTED,
            (True, False),
            "not-applicable evidence contradicts criterion policy",
        ),
    ],
)
def test_assessment_state_cannot_be_forged_into_an_impossible_decision(
    state: EvidenceState,
    decision: CriterionDecision,
    policy: tuple[bool, bool],
    message: str,
) -> None:
    required, allow_not_applicable = policy
    values = _assessment_values(
        state,
        decision,
        required=required,
        allow_not_applicable=allow_not_applicable,
    )

    with pytest.raises(ValidationError, match=message):
        CriterionAssessment.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_digests", "evidence digests must be unique"),
        ("supported_remediation", "cannot carry abstention remediation"),
        ("missing_remediation", "require reason and remediation"),
        ("blocking", "blocking state contradicts"),
    ],
)
def test_assessment_explanation_and_blocking_are_closed(case: str, message: str) -> None:
    values = _assessment_values(EvidenceState.OBSERVED, CriterionDecision.SUPPORTED)
    if case == "duplicate_digests":
        digest = values["evidence_digests"][0]
        values["evidence_digests"] = (digest, digest)
    elif case == "supported_remediation":
        values["reason_code"] = "reason.unexpected"
    elif case == "missing_remediation":
        values = _assessment_values(
            EvidenceState.OBSERVED,
            CriterionDecision.UNSUPPORTED,
        )
        values["reason_code"] = None
    else:
        values["blocks_route"] = True

    with pytest.raises(ValidationError, match=message):
        CriterionAssessment.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_assessment", "assessments must be unique"),
        ("missing_dimension", "assess every routing dimension"),
        ("aggregate", "decision contradicts its assessments"),
        ("digest", "digest does not match"),
    ],
)
def test_result_rejects_aggregate_and_digest_forgeries(case: str, message: str) -> None:
    values = _result_values()
    if case == "duplicate_assessment":
        values["assessments"][-1]["criterion_id"] = values["assessments"][0][
            "criterion_id"
        ]
    elif case == "missing_dimension":
        values["assessments"][-1]["dimension"] = SupportDimension.ASSAY
    elif case == "aggregate":
        values["decision"] = RouteDecision.ABSTAINED
    else:
        values["result_digest"] = _OTHER_DIGEST

    with pytest.raises(ValidationError, match=message):
        SupportRoutingResult.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (
            ("support", "status"),
            SupportStatus.REVIEW_REQUIRED,
            "support decision contradicts",
        ),
        (("human_review_required",), True, "review flag contradicts"),
        (("routing_id",), "routing.m0107.invalid", "identifier does not bind"),
        (
            ("provenance", "activity_id"),
            "activity.m0107.invalid",
            "provenance does not bind",
        ),
        (
            ("provenance", "module_id"),
            "GLIO-PROTEOGEN-M01-99",
            "wrong module",
        ),
        (("provenance", "module_version"), "9.9.9", "version contradicts"),
        (
            ("provenance", "generated_at"),
            datetime(2026, 8, 13, 12, tzinfo=UTC),
            "timestamp contradicts",
        ),
        (
            ("provenance", "configuration_digest"),
            _OTHER_DIGEST,
            "contradicts the configuration",
        ),
    ],
)
def test_result_rejects_forged_envelope_scalars(
    path: tuple[str, ...],
    replacement: object,
    message: str,
) -> None:
    values = _result_values()
    _set_path(values, path, replacement)

    with pytest.raises(ValidationError, match=message):
        SupportRoutingResult.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("missing_input", "input digests are incomplete"),
        ("duplicate_evidence", "evidence references must be unique"),
        ("limitations", "requires both module limitations"),
        ("control_state", "requires accepted authorization states"),
        ("configuration_control", "must bind the routing configuration"),
        ("consent_record", "consent provenance is internally inconsistent"),
    ],
)
def test_result_rejects_forged_provenance_and_evidence(case: str, message: str) -> None:
    values = _result_values()
    if case == "missing_input":
        values["provenance"]["input_digests"] = tuple(
            digest
            for digest in values["provenance"]["input_digests"]
            if digest != values["request_digest"]
        )
    elif case == "duplicate_evidence":
        evidence = list(values["evidence"])
        evidence[-1] = evidence[0]
        values["evidence"] = tuple(evidence)
    elif case == "limitations":
        values["limitations"][-1]["code"] = values["limitations"][0]["code"]
    elif case == "control_state":
        control = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"] == "quality"
        )
        control["state"] = UpstreamDecisionState.REJECTED.value
    elif case == "configuration_control":
        control = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"] == "approved_configuration"
        )
        control["evidence_digest"] = _OTHER_DIGEST
    else:
        values["provenance"]["consent_decision_id"] = "decision.forged.consent"

    with pytest.raises(ValidationError, match=message):
        SupportRoutingResult.model_validate(values, strict=True)


def test_public_result_rejects_missing_evidence_claimed_as_supported() -> None:
    values = _result_values()
    values["assessments"][0]["evidence_state"] = EvidenceState.MISSING

    with pytest.raises(
        ValidationError,
        match="missing or unknown evidence must remain indeterminate",
    ):
        SupportRoutingResult.model_validate(values, strict=True)
