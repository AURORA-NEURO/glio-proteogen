"""Compact relational boundary coverage for M02-02."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from evals.m02_02.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m01_02 import EntityKind
from glio_proteogen.contracts.m02_02 import (
    BindingAssessment,
    BindingDisposition,
    BindingState,
    FindingCode,
    IdentificationArtifactBinding,
    IdentityBindingEvaluation,
    IdentityBindingFinding,
    IdentityBindingPolicy,
    ValidateIdentityBindingsRequest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_02_identity_lineage import (
    evaluate_identity_bindings,
)

pytestmark = pytest.mark.contract
ZERO = "sha256:" + ("0" * 64)
BAD = "sha256:" + ("f" * 64)


def _request(case: str = "canonical") -> ValidateIdentityBindingsRequest:
    return build_scenario_request(case)


def _result(case: str = "canonical") -> IdentityBindingEvaluation:
    return evaluate_identity_bindings(_request(case))


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_evidence", "evidence references must be unique"),
        ("duplicate_subject", "subject component identifiers must be unique"),
        ("partial_entity", "identity claims must be supplied together"),
        ("partial_kind", "identity claims must be supplied together"),
        ("partial_component", "identity claims must be supplied together"),
        ("bound_missing_subject", "bound bindings require"),
        ("bound_missing_token", "bound bindings require"),
        ("unresolved_subject", "cannot carry observed identity evidence"),
        ("unsupported_token", "cannot carry observed identity evidence"),
    ],
)
def test_binding_state_and_claim_shape_is_closed(case: str, message: str) -> None:
    values = _request().bindings[0].model_dump(mode="python")
    if case == "duplicate_evidence":
        values["evidence"] = (values["evidence"][0], values["evidence"][0])
    elif case == "duplicate_subject":
        subject = values["observed_subject_component_ids"][0]
        values["observed_subject_component_ids"] = (subject, subject)
    elif case.startswith("partial_"):
        fields = {"entity_id", "entity_kind", "component_id"}
        retained = {
            "entity": "entity_id",
            "kind": "entity_kind",
            "component": "component_id",
        }[case.removeprefix("partial_")]
        for field in fields - {retained}:
            values[field] = None
    elif case == "bound_missing_subject":
        values["observed_subject_component_ids"] = ()
    elif case == "bound_missing_token":
        values["scoped_token"] = None
    elif case == "unresolved_subject":
        values["state"] = BindingState.UNRESOLVED
        values["scoped_token"] = None
    else:
        values["state"] = BindingState.UNSUPPORTED
        values["observed_subject_component_ids"] = ()

    with pytest.raises(ValidationError, match=message):
        IdentificationArtifactBinding.model_validate(values, strict=True)


@pytest.mark.parametrize("field", ["allowed_entity_kinds", "allowed_token_scope_ids"])
def test_policy_sets_are_unique(field: str) -> None:
    values = _request().policy.model_dump(mode="python")
    values[field] = (values[field][0], values[field][0])

    with pytest.raises(ValidationError, match="must be unique"):
        IdentityBindingPolicy.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("cap", "count exceeds"),
        ("duplicate_id", "identifiers must be unique"),
        ("resolution_digest", "does not bind the supplied resolution"),
        ("identity_state", "state contradicts"),
        ("configuration", "does not bind the active policy"),
        ("consent", "consent does not authorize"),
        ("quality", "generic upstream control"),
    ],
)
def test_request_authority_pins_and_caps_are_closed(case: str, message: str) -> None:
    values = _request().model_dump(mode="python")
    if case == "cap":
        values["policy"]["max_bindings"] = 1
        values["bindings"] = (*values["bindings"], deepcopy(values["bindings"][0]))
        values["bindings"][1]["binding_id"] = "binding.synthetic.extra"
    elif case == "duplicate_id":
        extra = deepcopy(values["bindings"][0])
        values["bindings"] = (*values["bindings"], extra)
    elif case == "resolution_digest":
        values["context"]["references"]["identity_lineage"]["binding_digest"] = BAD
    elif case == "identity_state":
        values["context"]["references"]["identity_lineage"]["state"] = (
            IdentityLineageState.UNRESOLVED
        )
    elif case == "configuration":
        values["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = BAD
    elif case == "consent":
        values["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    else:
        values["context"]["references"]["quality"]["state"] = (
            UpstreamDecisionState.REJECTED
        )

    with pytest.raises(ValidationError, match=message):
        ValidateIdentityBindingsRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_subject", "assessment values must be unique"),
        ("duplicate_code", "assessment values must be unique"),
        ("bound_missing_kind", "bound assessments require"),
        ("bound_missing_component", "bound assessments require"),
        ("bound_missing_subject", "bound assessments require"),
        ("nonbound_subject", "cannot claim observed subjects"),
    ],
)
def test_assessment_shape_is_closed(case: str, message: str) -> None:
    values = _result().bindings[0].model_dump(mode="python")
    if case == "duplicate_subject":
        subject = values["upstream_subject_component_ids"][0]
        values["upstream_subject_component_ids"] = (subject, subject)
    elif case == "duplicate_code":
        values["finding_codes"] = (FindingCode.SWAP, FindingCode.SWAP)
    elif case == "bound_missing_kind":
        values["entity_kind"] = None
    elif case == "bound_missing_component":
        values["entity_component_id"] = None
    elif case == "bound_missing_subject":
        values["upstream_subject_component_ids"] = ()
    else:
        values["state"] = BindingState.UNRESOLVED

    with pytest.raises(ValidationError, match=message):
        BindingAssessment.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_binding", "references must be unique"),
        ("duplicate_artifact", "references must be unique"),
        ("duplicate_component", "references must be unique"),
        ("upstream_with_binding", "cannot claim binding evidence"),
        ("ordinary_missing_binding", "require binding and artifact"),
        ("ordinary_missing_artifact", "require binding and artifact"),
        ("wrong_remediation", "remediation does not match"),
    ],
)
def test_finding_references_and_remediation_are_closed(case: str, message: str) -> None:
    base = _result("swap").findings[0]
    values = base.model_dump(mode="python")
    if case == "duplicate_binding":
        values["binding_ids"] = (base.binding_ids[0], base.binding_ids[0])
    elif case == "duplicate_artifact":
        values["artifact_digests"] = (base.artifact_digests[0],) * 2
    elif case == "duplicate_component":
        values["component_ids"] = (base.component_ids[0],) * 2
    elif case == "upstream_with_binding":
        values["code"] = FindingCode.UPSTREAM_IDENTITY_UNRESOLVED
        values["remediation_code"] = "resolve_upstream_identity_lineage"
    elif case == "ordinary_missing_binding":
        values["binding_ids"] = ()
    elif case == "ordinary_missing_artifact":
        values["artifact_digests"] = ()
    else:
        values["remediation_code"] = "wrong_remediation"

    with pytest.raises(ValidationError, match=message):
        IdentityBindingFinding.model_validate(values, strict=True)


def _forged_result(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    scenario = "canonical"
    if case.startswith("quarantined_") or case == "duplicate_finding":
        scenario = "token_collision" if case.endswith("artifact_mismatch") else "swap"
    elif case.startswith("abstained_"):
        scenario = "unresolved"
    case = case.removeprefix("quarantined_").removeprefix("abstained_")
    values = _result(scenario).model_dump(mode="python")
    values["result_digest"] = ZERO
    if case == "duplicate_binding":
        values["bindings"] = (*values["bindings"], values["bindings"][0])
    elif case == "duplicate_evidence":
        values["evidence"] = (*values["evidence"], values["evidence"][0])
    elif case == "unknown_assessment_component":
        values["bindings"][0]["entity_component_id"] = BAD
    elif case == "duplicate_finding":
        values["findings"] = (*values["findings"], values["findings"][0])
    elif case == "unknown_binding":
        values["findings"][0]["binding_ids"] = ("binding.missing",)
    elif case == "unknown_artifact":
        values["findings"][0]["artifact_digests"] = (BAD,)
    elif case == "unknown_component":
        values["findings"][0]["component_ids"] = (BAD,)
    elif case == "artifact_mismatch":
        values["findings"][0]["artifact_digests"] = (
            values["bindings"][1]["artifact_digest"],
        )
    elif case == "component_mismatch":
        other = next(
            node.component_id
            for node in _result("swap").lineage_graph.nodes
            if node.component_id not in set(values["findings"][0]["component_ids"])
        )
        values["findings"][0]["component_ids"] = (other,)
    elif case == "aggregate_codes":
        values["bindings"][0]["finding_codes"] = ()
    elif case == "bound_soft_code":
        values["findings"] = (
            {
                "code": FindingCode.UNRESOLVED_BINDING,
                "binding_ids": (values["bindings"][0]["binding_id"],),
                "artifact_digests": (values["bindings"][0]["artifact_digest"],),
                "component_ids": (),
                "remediation_code": "resolve_identity_binding",
            },
        )
        values["bindings"][0]["finding_codes"] = (FindingCode.UNRESOLVED_BINDING,)
        values["disposition"] = BindingDisposition.ABSTAINED
        values["support"]["status"] = SupportStatus.REVIEW_REQUIRED
        values["support"]["reason_code"] = "identity_bindings_abstained"
        values["human_review_required"] = True
    elif case == "nonbound_wrong_code":
        values["bindings"][0]["state"] = BindingState.UNSUPPORTED
    elif case == "conformant_disposition":
        values["disposition"] = BindingDisposition.ABSTAINED
    elif case == "disposition":
        values["disposition"] = BindingDisposition.CONFORMANT
    elif case == "upstream_finding":
        values["findings"] = (
            {
                "code": FindingCode.UPSTREAM_IDENTITY_UNRESOLVED,
                "binding_ids": (),
                "artifact_digests": (),
                "component_ids": (),
                "remediation_code": "resolve_upstream_identity_lineage",
            },
        )
        values["disposition"] = BindingDisposition.ABSTAINED
        values["support"]["status"] = SupportStatus.REVIEW_REQUIRED
        values["support"]["reason_code"] = "identity_bindings_abstained"
        values["human_review_required"] = True
    elif case == "support":
        values["support"]["status"] = SupportStatus.REVIEW_REQUIRED
    elif case == "graph_digest":
        values["upstream_graph_digest"] = BAD
    elif case == "limitation":
        values["limitations"][0]["code"] = "wrong_limitation"
    elif case == "evaluation_id":
        values["evaluation_id"] = "evaluation.m0202.wrong"
    elif case == "provenance_hash":
        values["provenance"]["input_digests"] = tuple(
            digest
            for digest in values["provenance"]["input_digests"]
            if digest != values["policy_digest"]
        )
    elif case == "control_state":
        next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "quality"
        )["state"] = "rejected"
    elif case == "configuration_evidence":
        next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "approved_configuration"
        )["evidence_digest"] = BAD
    elif case == "identity_subject":
        next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "identity_lineage"
        )["subject_digest"] = BAD
    elif case == "consent_record":
        values["provenance"]["consent_decision_id"] = "decision.wrong"
    elif case == "evidence_coverage":
        consent = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "consent"
        )["evidence_digest"]
        values["evidence"] = tuple(
            item for item in values["evidence"] if item["reference"]["digest"] != consent
        )
    elif case == "kind_forgery":
        values["bindings"][0]["entity_kind"] = EntityKind.PATIENT
    elif case == "subject_forgery":
        current_subjects = tuple(
            values["bindings"][0]["upstream_subject_component_ids"]
        )
        other_subjects = next(
            node.subject_component_ids
            for node in _result().lineage_graph.nodes
            if node.subject_component_ids
            and node.subject_component_ids != current_subjects
        )
        values["bindings"][0]["upstream_subject_component_ids"] = other_subjects
    elif case == "digest":
        values["result_digest"] = BAD
    return values


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_binding", "assessment identifiers must be unique"),
        ("duplicate_evidence", "evidence references must be unique"),
        ("unknown_assessment_component", "unknown identity component"),
        ("duplicate_finding", "findings must be unique"),
        ("quarantined_unknown_binding", "unknown binding"),
        ("quarantined_unknown_artifact", "unknown artifact"),
        ("quarantined_unknown_component", "unknown identity component"),
        ("quarantined_artifact_mismatch", "artifacts do not match"),
        ("quarantined_component_mismatch", "components do not match"),
        ("quarantined_aggregate_codes", "codes do not match"),
        ("bound_soft_code", "bound assessment cannot carry"),
        ("abstained_nonbound_wrong_code", "finding contradicts its state"),
        ("conformant_disposition", "disposition contradicts"),
        ("quarantined_disposition", "disposition contradicts"),
        ("abstained_disposition", "disposition contradicts"),
        ("upstream_finding", "upstream resolution finding contradicts"),
        ("support", "support contradicts"),
        ("graph_digest", "does not bind its upstream digest"),
        ("limitation", "requires both limitation codes"),
        ("evaluation_id", "provenance envelope is inconsistent"),
        ("provenance_hash", "provenance envelope is inconsistent"),
        ("control_state", "control states are inconsistent"),
        ("configuration_evidence", "provenance envelope is inconsistent"),
        ("identity_subject", "identity control does not bind"),
        ("consent_record", "consent provenance contradicts"),
        ("evidence_coverage", "does not cover every upstream control"),
        ("kind_forgery", "contradicts its upstream identity component"),
        ("subject_forgery", "contradicts its upstream identity component"),
        ("digest", "digest does not match"),
    ],
)
def test_output_forgery_is_rejected(case: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        IdentityBindingEvaluation.model_validate(_forged_result(case), strict=True)


def test_bound_result_digest_round_trips() -> None:
    result = _result()

    assert IdentityBindingEvaluation.model_validate(
        result.model_dump(mode="python"),
        strict=True,
    ) == result
