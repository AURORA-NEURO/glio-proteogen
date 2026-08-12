"""Meaningful relational boundary coverage for the frozen M02-01 contract."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Any

import pytest
from evals.m02_01.run import build_scenario_request
from pydantic import ValidationError

from glio_proteogen.contracts.m02_01 import (
    AllowedTermPairRule,
    ConditionalStateRule,
    ConformanceDisposition,
    ConformanceEvaluation,
    ConformanceProfile,
    ConformanceStatus,
    EvaluateConformanceRequest,
    FieldObservation,
    NumericRangeRule,
    ObservationState,
    ProtocolFieldDefinition,
    ProtocolSchema,
    RuleAction,
    TermInSetRule,
    ValueKind,
    VocabularyDefinition,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    FrozenModel,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    evaluate_conformance,
)

pytestmark = pytest.mark.contract

ZERO_DIGEST = "sha256:" + ("0" * 64)
BAD_DIGEST = "sha256:" + ("f" * 64)


def _base_request() -> EvaluateConformanceRequest:
    return build_scenario_request("canonical")


def _schema_payload() -> dict[str, Any]:
    return _base_request().protocol_schema.model_dump(mode="python")


def _field_payload(field_id: str) -> dict[str, Any]:
    schema = _base_request().protocol_schema
    return next(item for item in schema.fields if item.field_id == field_id).model_dump(
        mode="python"
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_vocabulary_term", "vocabulary terms must be unique"),
        ("minimum_above_maximum", "field cardinality is inconsistent"),
        ("required_with_zero_minimum", "field cardinality is inconsistent"),
        ("required_not_applicable", "required fields cannot allow"),
        ("term_without_vocabulary", "controlled-term fields require"),
        ("text_with_vocabulary", "controlled-term fields require"),
        ("text_with_unit", "only numeric fields may declare"),
        ("boolean_with_unit", "only numeric fields may declare"),
    ],
)
def test_field_and_vocabulary_shapes_are_closed(case: str, message: str) -> None:
    model: type[FrozenModel]
    if case == "duplicate_vocabulary_term":
        vocabulary = _base_request().protocol_schema.vocabularies[0]
        values = vocabulary.model_dump(mode="python")
        values["terms"] = (vocabulary.terms[0], vocabulary.terms[0])
        model = VocabularyDefinition
    else:
        field_id = "acquisition_mode" if case == "term_without_vocabulary" else "instrument_model"
        values = _field_payload(field_id)
        if case == "minimum_above_maximum":
            values["min_items"] = 2
        elif case == "required_with_zero_minimum":
            values["min_items"] = 0
        elif case == "required_not_applicable":
            values["allow_not_applicable"] = True
        elif case == "term_without_vocabulary":
            values["vocabulary_id"] = None
        elif case == "text_with_vocabulary":
            values["vocabulary_id"] = "vocabulary.acquisition"
        elif case == "text_with_unit":
            values["unit_id"] = "unit.ppm"
        else:
            values["value_kind"] = ValueKind.BOOLEAN
            values["unit_id"] = "unit.ppm"
        model = ProtocolFieldDefinition

    with pytest.raises(ValidationError, match=message):
        model.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_allowed_term", "term rule values must be unique"),
        ("range_without_bound", "requires at least one bound"),
        ("reversed_range", "bounds must be ordered"),
        ("duplicate_trigger_term", "trigger terms must be unique"),
        ("duplicate_allowed_pair", "term pairs must be unique"),
    ],
)
def test_rule_local_shapes_are_closed(case: str, message: str) -> None:
    model: type[FrozenModel]
    rules = _base_request().protocol_schema.compatibility_rules
    if case == "duplicate_allowed_term":
        term_rule = next(item for item in rules if isinstance(item, TermInSetRule))
        values = term_rule.model_dump(mode="python")
        values["allowed_terms"] = (
            term_rule.allowed_terms[0],
            term_rule.allowed_terms[0],
        )
        model = TermInSetRule
    elif case in {"range_without_bound", "reversed_range"}:
        range_rule = next(item for item in rules if isinstance(item, NumericRangeRule))
        values = range_rule.model_dump(mode="python")
        if case == "range_without_bound":
            values["minimum"] = None
            values["maximum"] = None
        else:
            values["minimum"] = 2.0
            values["maximum"] = 1.0
        model = NumericRangeRule
    elif case == "duplicate_trigger_term":
        conditional_rule = next(
            item for item in rules if isinstance(item, ConditionalStateRule)
        )
        values = conditional_rule.model_dump(mode="python")
        values["trigger_terms"] = (
            conditional_rule.trigger_terms[0],
            conditional_rule.trigger_terms[0],
        )
        model = ConditionalStateRule
    else:
        pair_rule = next(item for item in rules if isinstance(item, AllowedTermPairRule))
        values = pair_rule.model_dump(mode="python")
        values["allowed_pairs"] = (
            pair_rule.allowed_pairs[0],
            pair_rule.allowed_pairs[0],
        )
        model = AllowedTermPairRule

    with pytest.raises(ValidationError, match=message):
        model.model_validate(values, strict=True)


@pytest.mark.parametrize(
    "collection",
    ["fields", "vocabularies", "units", "compatibility_rules"],
)
def test_schema_identifiers_are_unique_per_collection(collection: str) -> None:
    values = _schema_payload()
    values[collection] = (*values[collection], deepcopy(values[collection][0]))

    with pytest.raises(ValidationError, match="identifiers must be unique"):
        ProtocolSchema.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unresolved_field_vocabulary", "vocabulary reference is unresolved"),
        ("unresolved_field_unit", "unit reference is unresolved"),
        ("unresolved_rule_field", "rule field reference is unresolved"),
        ("term_rule_on_text", "requires a controlled-term field"),
        ("term_rule_unknown_term", "values must belong to the field vocabulary"),
        ("numeric_rule_on_text", "numeric rule must match its field unit"),
        ("numeric_rule_wrong_unit", "numeric rule must match its field unit"),
        ("boolean_rule_on_text", "requires a boolean field"),
        ("conditional_missing_trigger", "requires a controlled-term trigger"),
        ("conditional_text_trigger", "requires a controlled-term trigger"),
        ("conditional_unknown_term", "trigger terms must belong"),
        ("pair_text_target", "requires two controlled-term fields"),
        ("pair_missing_other", "requires two controlled-term fields"),
        ("pair_text_other", "requires two controlled-term fields"),
        ("pair_unknown_left", "pairs must belong to their vocabularies"),
        ("pair_unknown_right", "pairs must belong to their vocabularies"),
    ],
)
def test_schema_rule_references_and_types_are_closed(case: str, message: str) -> None:  # noqa: C901, PLR0912
    values = _schema_payload()
    fields = {item["field_id"]: item for item in values["fields"]}
    rules = {item["kind"]: item for item in values["compatibility_rules"]}
    if case == "unresolved_field_vocabulary":
        fields["acquisition_mode"]["vocabulary_id"] = "vocabulary.missing"
    elif case == "unresolved_field_unit":
        fields["precursor_tolerance"]["unit_id"] = "unit.missing"
    elif case == "unresolved_rule_field":
        rules["required_present"]["field_id"] = "field.missing"
    elif case == "term_rule_on_text":
        rules["term_in_set"]["field_id"] = "instrument_model"
    elif case == "term_rule_unknown_term":
        rules["term_in_set"]["allowed_terms"] = ("term.missing",)
    elif case == "numeric_rule_on_text":
        rules["numeric_range"]["field_id"] = "instrument_model"
    elif case == "numeric_rule_wrong_unit":
        rules["numeric_range"]["unit_id"] = "unit.wrong"
    elif case == "boolean_rule_on_text":
        values["compatibility_rules"] = (
            *values["compatibility_rules"],
            {
                "kind": "boolean_equals",
                "rule_id": "rule.boolean",
                "field_id": "instrument_model",
                "action": RuleAction.QUARANTINE,
                "reason_code": "boolean_mismatch",
                "remediation_code": "review_boolean",
                "expected": True,
            },
        )
    elif case == "conditional_missing_trigger":
        rules["conditional_state"]["trigger_field_id"] = "field.missing"
    elif case == "conditional_text_trigger":
        rules["conditional_state"]["trigger_field_id"] = "instrument_model"
    elif case == "conditional_unknown_term":
        rules["conditional_state"]["trigger_terms"] = ("term.missing",)
    elif case == "pair_text_target":
        rules["allowed_term_pair"]["field_id"] = "instrument_model"
    elif case == "pair_missing_other":
        rules["allowed_term_pair"]["other_field_id"] = "field.missing"
    elif case == "pair_text_other":
        rules["allowed_term_pair"]["other_field_id"] = "instrument_model"
    elif case == "pair_unknown_left":
        rules["allowed_term_pair"]["allowed_pairs"][0]["left"] = "term.missing"
    else:
        rules["allowed_term_pair"]["allowed_pairs"][0]["right"] = "term.missing"

    with pytest.raises(ValidationError, match=message):
        ProtocolSchema.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("state", "values", "unit_id", "duplicate_evidence", "message"),
    [
        (ObservationState.OBSERVED, (), None, False, "observed fields require values"),
        (ObservationState.CONFLICTING, (), None, False, "at least two values"),
        (ObservationState.CONFLICTING, ("one",), None, False, "at least two values"),
        (ObservationState.MISSING, ("value",), None, False, "cannot carry values or units"),
        (ObservationState.MISSING, (), "unit.ppm", False, "cannot carry values or units"),
        (ObservationState.UNKNOWN, ("value",), None, False, "cannot carry values or units"),
        (ObservationState.NOT_APPLICABLE, (), "unit.ppm", False, "cannot carry values or units"),
        (ObservationState.OBSERVED, ("value",), None, True, "evidence references must be unique"),
    ],
)
def test_observation_state_payload_is_explicit(
    state: ObservationState,
    values: tuple[str, ...],
    unit_id: str | None,
    *,
    duplicate_evidence: bool,
    message: str,
) -> None:
    source = _base_request().observations[0]
    evidence = (source.evidence[0], source.evidence[0]) if duplicate_evidence else source.evidence
    payload = source.model_dump(mode="python")
    payload.update(state=state, values=values, unit_id=unit_id, evidence=evidence)

    with pytest.raises(ValidationError, match=message):
        FieldObservation.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    ("state", "values"),
    [
        (ObservationState.MISSING, ()),
        (ObservationState.UNKNOWN, ()),
        (ObservationState.NOT_APPLICABLE, ()),
        (ObservationState.CONFLICTING, ("left", "right")),
    ],
)
def test_valid_explicit_observation_states_remain_representable(
    state: ObservationState,
    values: tuple[str, ...],
) -> None:
    payload = _base_request().observations[0].model_dump(mode="python")
    payload.update(state=state, values=values, unit_id=None)

    assert FieldObservation.model_validate(payload, strict=True).state is state


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("schema_id", "does not pin"),
        ("schema_version", "does not pin"),
        ("schema_digest", "does not pin"),
        ("profile_cap", "count exceeds"),
        ("duplicate_observation_id", "identifiers must be unique"),
        ("duplicate_field", "only one observation"),
        ("unresolved_field", "field reference is unresolved"),
        ("configuration_digest", "does not bind"),
    ],
)
def test_request_pins_caps_and_references_are_closed(case: str, message: str) -> None:
    values = _base_request().model_dump(mode="python")
    if case == "schema_id":
        values["conformance_profile"]["schema_id"] = "schema.other"
    elif case == "schema_version":
        values["conformance_profile"]["schema_version"] = "2.0.0"
    elif case == "schema_digest":
        values["conformance_profile"]["schema_digest"] = BAD_DIGEST
    elif case == "profile_cap":
        values["conformance_profile"]["max_observations"] = 5
    elif case == "duplicate_observation_id":
        values["observations"][1]["observation_id"] = values["observations"][0][
            "observation_id"
        ]
    elif case == "duplicate_field":
        values["observations"][1]["field_id"] = values["observations"][0]["field_id"]
    elif case == "unresolved_field":
        values["observations"][0]["field_id"] = "field.missing"
    else:
        values["context"]["references"]["approved_configuration"]["evidence"][
            "digest"
        ] = BAD_DIGEST

    with pytest.raises(ValidationError, match=message):
        EvaluateConformanceRequest.model_validate(values, strict=True)


@pytest.mark.parametrize(
    ("reference", "state", "message"),
    [
        ("consent", ConsentState.WITHHELD, "consent does not authorize"),
        ("identity_lineage", IdentityLineageState.UNRESOLVED, "identity lineage must be resolved"),
        ("approved_configuration", UpstreamDecisionState.REJECTED, "every upstream control"),
        ("provenance", UpstreamDecisionState.UNKNOWN, "every upstream control"),
        ("quality", UpstreamDecisionState.REJECTED, "every upstream control"),
        ("support", UpstreamDecisionState.UNKNOWN, "every upstream control"),
        ("intended_use", UpstreamDecisionState.REJECTED, "every upstream control"),
    ],
)
def test_request_requires_all_seven_authorized_controls(
    reference: str,
    state: ConsentState | IdentityLineageState | UpstreamDecisionState,
    message: str,
) -> None:
    values = _base_request().model_dump(mode="python")
    values["context"]["references"][reference]["state"] = state

    with pytest.raises(ValidationError, match=message):
        EvaluateConformanceRequest.model_validate(values, strict=True)


@pytest.mark.parametrize("maximum", [0, 4097])
def test_profile_observation_cap_is_bounded(maximum: int) -> None:
    values = _base_request().conformance_profile.model_dump(mode="python")
    values["max_observations"] = maximum

    with pytest.raises(ValidationError):
        ConformanceProfile.model_validate(values, strict=True)


def _result_payload(case: str) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
    scenario = "canonical"
    if case.startswith("nonconformant_"):
        scenario = "unsupported_term"
    elif case.startswith("indeterminate_"):
        scenario = "missing_mandatory"
    values = evaluate_conformance(build_scenario_request(scenario)).model_dump(mode="python")
    values["evaluation_digest"] = ZERO_DIGEST
    if case == "duplicate_field_evaluation":
        values["field_evaluations"] = (
            *values["field_evaluations"],
            values["field_evaluations"][0],
        )
    elif case == "duplicate_rule_evaluation":
        values["rule_evaluations"] = (
            *values["rule_evaluations"],
            values["rule_evaluations"][0],
        )
    elif case == "duplicate_evidence":
        values["evidence"] = (*values["evidence"], values["evidence"][0])
    elif case == "conformant_status":
        values["status"] = ConformanceStatus.NONCONFORMANT
    elif case in {"nonconformant_status", "indeterminate_status"}:
        values["status"] = ConformanceStatus.CONFORMANT
    elif case in {"conformant_disposition", "nonconformant_disposition"}:
        values["disposition"] = (
            ConformanceDisposition.QUARANTINED
            if case == "conformant_disposition"
            else ConformanceDisposition.CONFORMANT
        )
    elif case == "support_status":
        values["support"]["status"] = SupportStatus.REVIEW_REQUIRED
    elif case == "support_reason":
        values["support"]["reason_code"] = "metadata_quarantined"
    elif case == "review_flag":
        values["human_review_required"] = True
    elif case == "nonconformant_support":
        values["support"]["status"] = SupportStatus.SUPPORTED
    elif case == "evaluation_id":
        values["evaluation_id"] = "evaluation.m0201.forged"
    elif case == "activity_id":
        values["provenance"]["activity_id"] = "activity.m0201.forged"
    elif case == "module_id":
        values["provenance"]["module_id"] = "GLIO-PROTEOGEN-M99-99"
    elif case == "module_version":
        values["provenance"]["module_version"] = "2.0.0"
    elif case == "generated_at":
        values["provenance"]["generated_at"] += timedelta(seconds=1)
    elif case == "provenance_configuration":
        values["provenance"]["configuration_digest"] = BAD_DIGEST
    elif case.startswith("missing_input_"):
        name = case.removeprefix("missing_input_")
        digest = values[f"{name}_digest"]
        values["provenance"]["input_digests"] = tuple(
            item for item in values["provenance"]["input_digests"] if item != digest
        )
    elif case == "consent_state":
        values["provenance"]["consent_state"] = ConsentState.WITHHELD
    elif case == "control_state":
        record = next(
            item
            for item in values["provenance"]["control_decisions"]
            if item["role"].value == "quality"
        )
        record["state"] = UpstreamDecisionState.REJECTED.value
    elif case == "duplicate_control_role":
        records = values["provenance"]["control_decisions"]
        values["provenance"]["control_decisions"] = (
            records[0],
            deepcopy(records[0]),
            *records[2:],
        )
    elif case == "limitation_codes":
        values["limitations"][1]["code"] = values["limitations"][0]["code"]
    elif case == "digest":
        values["evaluation_digest"] = BAD_DIGEST
    return values


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_field_evaluation", "identifiers must be unique"),
        ("duplicate_rule_evaluation", "identifiers must be unique"),
        ("duplicate_evidence", "evidence must be unique"),
        ("conformant_status", "status contradicts"),
        ("nonconformant_status", "status contradicts"),
        ("indeterminate_status", "status contradicts"),
        ("conformant_disposition", "disposition contradicts"),
        ("nonconformant_disposition", "disposition contradicts"),
        ("support_status", "support envelope contradicts"),
        ("support_reason", "support envelope contradicts"),
        ("review_flag", "support envelope contradicts"),
        ("nonconformant_support", "support envelope contradicts"),
        ("evaluation_id", "provenance envelope is inconsistent"),
        ("activity_id", "provenance envelope is inconsistent"),
        ("module_id", "provenance envelope is inconsistent"),
        ("module_version", "provenance envelope is inconsistent"),
        ("generated_at", "provenance envelope is inconsistent"),
        ("provenance_configuration", "provenance envelope is inconsistent"),
        ("missing_input_request", "provenance envelope is inconsistent"),
        ("missing_input_schema", "provenance envelope is inconsistent"),
        ("missing_input_profile", "provenance envelope is inconsistent"),
        ("missing_input_configuration", "provenance envelope is inconsistent"),
        ("consent_state", "provenance requires accepted controls"),
        ("control_state", "provenance requires accepted controls"),
        ("duplicate_control_role", "every upstream control role"),
        ("limitation_codes", "requires both limitation codes"),
        ("digest", "digest does not match"),
    ],
)
def test_output_relational_forgery_is_rejected(case: str, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ConformanceEvaluation.model_validate(_result_payload(case), strict=True)


def test_bound_output_digest_round_trips_strictly() -> None:
    result = evaluate_conformance(_base_request())

    assert ConformanceEvaluation.model_validate(
        result.model_dump(mode="python"),
        strict=True,
    ) == result
