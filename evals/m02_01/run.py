"""Replay the locked M02-01 synthetic protocol-metadata corpus."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict, cast

from glio_proteogen.contracts.m02_01 import (
    AllowedTermPair,
    AllowedTermPairRule,
    ConditionalStateRule,
    ConformanceEvaluation,
    ConformanceProfile,
    EvaluateConformanceRequest,
    FieldObservation,
    NumericRangeRule,
    ObservationState,
    PresenceRule,
    ProtocolFieldDefinition,
    ProtocolSchema,
    RuleAction,
    TermInSetRule,
    UnitDefinition,
    ValueKind,
    VocabularyDefinition,
    configuration_digest,
    schema_digest,
)
from glio_proteogen.kernel.canonical import sha256_digest
from glio_proteogen.kernel.models import (
    ArtifactReference,
    ConsentReference,
    ConsentState,
    ContextReferences,
    ExecutionContext,
    IdentityLineageReference,
    IdentityLineageState,
    UpstreamDecisionReference,
    UpstreamDecisionState,
)
from glio_proteogen.kernel.strict_json import strict_json_loads
from glio_proteogen.modules.c02_identification_qc.m02_01_protocol_metadata import (
    ConformanceAuthorizationError,
    evaluate_conformance,
    preflight_conformance_authorization,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M02-01"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m02_01" / "scenarios.json"
EXPECTED_SCENARIO_COUNT: Final = 8


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "paired_result", "authorization_rejected"]
    expected_status: NotRequired[str]
    expected_disposition: NotRequired[str]
    expected_finding_codes: NotRequired[list[str]]
    must_not_emit_finding_codes: NotRequired[list[str]]
    label_free_expected_status: NotRequired[str]
    label_free_expected_disposition: NotRequired[str]
    isobaric_expected_status: NotRequired[str]
    isobaric_expected_disposition: NotRequired[str]
    isobaric_expected_finding_codes: NotRequired[list[str]]
    expected_reason: NotRequired[str]


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
    profile_id: str
    profile_version: str
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(label: str, digest: str | None = None) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.{label}",
        version="1.0.0",
        digest=digest or sha256_digest({"m0201": label}),
        media_type="application/json",
    )


def _schema() -> ProtocolSchema:
    acquisition = VocabularyDefinition(
        vocabulary_id="vocabulary.acquisition",
        version="1.0.0",
        terms=("label_free", "isobaric"),
        evidence=_artifact("vocabulary.acquisition"),
    )
    specimen = VocabularyDefinition(
        vocabulary_id="vocabulary.specimen",
        version="1.0.0",
        terms=("fresh_frozen", "ffpe"),
        evidence=_artifact("vocabulary.specimen"),
    )
    reagent = VocabularyDefinition(
        vocabulary_id="vocabulary.reagent",
        version="1.0.0",
        terms=("tmtpro",),
        evidence=_artifact("vocabulary.reagent"),
    )
    fields = (
        ProtocolFieldDefinition(
            field_id="acquisition_mode",
            label="Acquisition mode",
            value_kind=ValueKind.TERM,
            required=True,
            min_items=1,
            max_items=1,
            vocabulary_id=acquisition.vocabulary_id,
        ),
        ProtocolFieldDefinition(
            field_id="specimen_preservation",
            label="Specimen preservation",
            value_kind=ValueKind.TERM,
            required=True,
            min_items=1,
            max_items=1,
            vocabulary_id=specimen.vocabulary_id,
        ),
        ProtocolFieldDefinition(
            field_id="precursor_tolerance",
            label="Precursor tolerance",
            value_kind=ValueKind.NUMBER,
            required=True,
            min_items=1,
            max_items=1,
            unit_id="unit.ppm",
        ),
        ProtocolFieldDefinition(
            field_id="label_reagent",
            label="Label reagent",
            value_kind=ValueKind.TERM,
            required=False,
            min_items=0,
            max_items=1,
            vocabulary_id=reagent.vocabulary_id,
            allow_not_applicable=True,
        ),
        ProtocolFieldDefinition(
            field_id="instrument_model",
            label="Instrument model",
            value_kind=ValueKind.TEXT,
            required=True,
            min_items=1,
            max_items=1,
        ),
        ProtocolFieldDefinition(
            field_id="search_engine_version",
            label="Search engine version",
            value_kind=ValueKind.TEXT,
            required=True,
            min_items=1,
            max_items=1,
        ),
    )
    rules = (
        PresenceRule(
            rule_id="rule.instrument.required",
            field_id="instrument_model",
            action=RuleAction.QUARANTINE,
            reason_code="mandatory_field_missing",
            remediation_code="supply_mandatory_metadata",
        ),
        TermInSetRule(
            rule_id="rule.acquisition.terms",
            field_id="acquisition_mode",
            action=RuleAction.QUARANTINE,
            reason_code="controlled_term_unsupported",
            remediation_code="select_supported_controlled_term",
            allowed_terms=acquisition.terms,
        ),
        TermInSetRule(
            rule_id="rule.specimen.terms",
            field_id="specimen_preservation",
            action=RuleAction.QUARANTINE,
            reason_code="controlled_term_unsupported",
            remediation_code="select_supported_controlled_term",
            allowed_terms=specimen.terms,
        ),
        NumericRangeRule(
            rule_id="rule.precursor.range",
            field_id="precursor_tolerance",
            action=RuleAction.QUARANTINE,
            reason_code="precursor_tolerance_out_of_range",
            remediation_code="review_precursor_tolerance",
            minimum=0.0,
            maximum=50.0,
            unit_id="unit.ppm",
        ),
        ConditionalStateRule(
            rule_id="rule.reagent.isobaric",
            field_id="label_reagent",
            action=RuleAction.QUARANTINE,
            reason_code="not_applicable_disallowed",
            remediation_code="supply_isobaric_label_reagent",
            trigger_field_id="acquisition_mode",
            trigger_terms=("isobaric",),
            required_state=ObservationState.OBSERVED,
        ),
        AllowedTermPairRule(
            rule_id="rule.acquisition.specimen",
            field_id="acquisition_mode",
            action=RuleAction.QUARANTINE,
            reason_code="compatibility_rule_failed",
            remediation_code="review_assay_specimen_compatibility",
            other_field_id="specimen_preservation",
            allowed_pairs=(
                AllowedTermPair(left="label_free", right="fresh_frozen"),
                AllowedTermPair(left="label_free", right="ffpe"),
                AllowedTermPair(left="isobaric", right="fresh_frozen"),
            ),
        ),
    )
    return ProtocolSchema(
        schema_id="schema.synthetic.peptide-identification",
        version="1.0.0",
        assay_type="mass_spectrometry.peptide_identification",
        specimen_type="glioma.tissue",
        fields=fields,
        vocabularies=(acquisition, specimen, reagent),
        units=(
            UnitDefinition(
                unit_id="unit.ppm",
                symbol="ppm",
                quantity_kind="mass_error",
                evidence=_artifact("unit.ppm"),
            ),
        ),
        compatibility_rules=rules,
        evidence=_artifact("protocol.schema"),
    )


def _profile(schema: ProtocolSchema) -> ConformanceProfile:
    return ConformanceProfile(
        profile_id="profile.synthetic.peptide-identification",
        version="1.0.0",
        schema_id=schema.schema_id,
        schema_version=schema.version,
        schema_digest=schema_digest(schema),
        max_observations=64,
        evidence=_artifact("conformance.profile"),
    )


def _context(configuration: str) -> ExecutionContext:
    def decision(role: str, digest: str | None = None) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.{role}",
            state=UpstreamDecisionState.ACCEPTED,
            policy_version="1.0.0",
            evidence=_artifact(role, digest),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0201",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0201": "identity-binding"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision("quality"),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _observation(
    field_id: str,
    state: ObservationState,
    values: tuple[str | int | float | bool, ...] = (),
    unit_id: str | None = None,
) -> FieldObservation:
    return FieldObservation(
        observation_id=f"observation.synthetic.{field_id}",
        field_id=field_id,
        state=state,
        values=values,
        unit_id=unit_id,
        evidence=(_artifact(f"observation.{field_id}"),),
    )


def _base_request() -> EvaluateConformanceRequest:
    schema = _schema()
    profile = _profile(schema)
    observations = (
        _observation("acquisition_mode", ObservationState.OBSERVED, ("label_free",)),
        _observation("specimen_preservation", ObservationState.OBSERVED, ("fresh_frozen",)),
        _observation(
            "precursor_tolerance",
            ObservationState.OBSERVED,
            (10.0,),
            "unit.ppm",
        ),
        _observation("label_reagent", ObservationState.NOT_APPLICABLE),
        _observation("instrument_model", ObservationState.OBSERVED, ("synthetic.instrument",)),
        _observation("search_engine_version", ObservationState.OBSERVED, ("1.0.0",)),
    )
    return EvaluateConformanceRequest(
        context=_context(configuration_digest(schema, profile)),
        protocol_schema=schema,
        conformance_profile=profile,
        observations=observations,
    )


def _replace(
    request: EvaluateConformanceRequest,
    field_id: str,
    replacement: FieldObservation | None,
) -> EvaluateConformanceRequest:
    observations = tuple(item for item in request.observations if item.field_id != field_id)
    if replacement is not None:
        observations = (*observations, replacement)
    return request.model_copy(update={"observations": observations})


def build_scenario_request(request_case: str) -> EvaluateConformanceRequest:
    """Build one deterministic strict request for eval and benchmark reuse."""

    request = _base_request()
    if request_case in {"canonical", "consent_denied"}:
        return request
    if request_case == "missing_mandatory":
        return _replace(request, "instrument_model", None)
    if request_case == "unsupported_term":
        return _replace(
            request,
            "acquisition_mode",
            _observation("acquisition_mode", ObservationState.OBSERVED, ("unsupported",)),
        )
    if request_case == "incompatible_unit":
        return _replace(
            request,
            "precursor_tolerance",
            _observation(
                "precursor_tolerance",
                ObservationState.OBSERVED,
                (0.01,),
                "unit.dalton",
            ),
        )
    if request_case == "over_cardinality":
        return _replace(
            request,
            "instrument_model",
            _observation(
                "instrument_model",
                ObservationState.OBSERVED,
                ("synthetic.instrument.a", "synthetic.instrument.b"),
            ),
        )
    if request_case == "unresolved_mandatory":
        return _replace(
            request,
            "instrument_model",
            _observation("instrument_model", ObservationState.UNKNOWN),
        )
    raise ValueError(request_case)


def conditional_requests() -> tuple[EvaluateConformanceRequest, EvaluateConformanceRequest]:
    """Return label-free accepted and isobaric rejected requests for one pinned rule."""

    label_free = _base_request()
    isobaric = _replace(
        label_free,
        "acquisition_mode",
        _observation("acquisition_mode", ObservationState.OBSERVED, ("isobaric",)),
    )
    return label_free, isobaric


def _finding_codes(result: ConformanceEvaluation) -> set[str]:
    field_codes = {
        item.reason_code
        for item in result.field_evaluations
        if item.state.value != "pass"
    }
    rule_codes = {
        item.reason_code
        for item in result.rule_evaluations
        if item.state.value != "pass"
    }
    return field_codes | rule_codes


def _result_check(scenario: Scenario) -> tuple[EvalCheck, ConformanceEvaluation]:
    result = evaluate_conformance(build_scenario_request(scenario["request_case"]))
    expected = set(scenario.get("expected_finding_codes", []))
    forbidden = set(scenario.get("must_not_emit_finding_codes", []))
    findings = _finding_codes(result)
    passed = (
        result.status.value == scenario["expected_status"]
        and result.disposition.value == scenario["expected_disposition"]
        and expected <= findings
        and not (forbidden & findings)
    )
    return (
        EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=passed,
            detail=(
                f"status={result.status.value};disposition={result.disposition.value};"
                f"findings={','.join(sorted(findings)) or 'none'}"
            ),
        ),
        result,
    )


def _conditional_check(scenario: Scenario) -> tuple[EvalCheck, tuple[ConformanceEvaluation, ...]]:
    label_free_request, isobaric_request = conditional_requests()
    label_free = evaluate_conformance(label_free_request)
    isobaric = evaluate_conformance(isobaric_request)
    findings = _finding_codes(isobaric)
    passed = (
        label_free.status.value == scenario["label_free_expected_status"]
        and label_free.disposition.value == scenario["label_free_expected_disposition"]
        and isobaric.status.value == scenario["isobaric_expected_status"]
        and isobaric.disposition.value == scenario["isobaric_expected_disposition"]
        and set(scenario["isobaric_expected_finding_codes"]) <= findings
    )
    return (
        EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=passed,
            detail=(
                f"label_free={label_free.disposition.value};"
                f"isobaric={isobaric.disposition.value};"
                f"findings={','.join(sorted(findings)) or 'none'}"
            ),
        ),
        (label_free, isobaric),
    )


def _authorization_check(scenario: Scenario) -> EvalCheck:
    request = build_scenario_request("consent_denied")
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = "withheld"
    payload["observations"] = object()
    try:
        preflight_conformance_authorization(payload)
    except ConformanceAuthorizationError:
        return EvalCheck(
            name=f"scenario.{scenario['case_id']}",
            passed=True,
            detail=scenario["expected_reason"],
        )
    return EvalCheck(
        name=f"scenario.{scenario['case_id']}",
        passed=False,
        detail="authorization was not rejected",
    )


def _determinism_check() -> tuple[EvalCheck, ConformanceEvaluation]:
    request = _base_request()
    schema = request.protocol_schema.model_copy(
        update={
            "fields": tuple(reversed(request.protocol_schema.fields)),
            "vocabularies": tuple(reversed(request.protocol_schema.vocabularies)),
            "units": tuple(reversed(request.protocol_schema.units)),
            "compatibility_rules": tuple(
                reversed(request.protocol_schema.compatibility_rules)
            ),
        }
    )
    replay = request.model_copy(
        update={
            "protocol_schema": schema,
            "observations": tuple(reversed(request.observations)),
        }
    )
    result = evaluate_conformance(request)
    replay_result = evaluate_conformance(replay)
    return (
        EvalCheck(
            name="determinism.semantic_order",
            passed=result == replay_result,
            detail=f"evaluation_digest={result.evaluation_digest}",
        ),
        result,
    )


def _boundary(results: list[ConformanceEvaluation]) -> EvalCheck:
    forbidden = {
        "biological_interpretation",
        "clinical_readiness",
        "kinase_activity",
        "peptide_identification",
        "protein_subtype",
        "raw_sequence",
        "raw_spectra",
        "treatment_recommendation",
    }
    rendered = json.dumps(
        [item.model_dump(mode="json") for item in results],
        sort_keys=True,
    )
    leaked = sorted(key for key in forbidden if key in rendered)
    return EvalCheck(
        name="boundary.closed_conformance_output",
        passed=not leaked,
        detail="closed typed output" if not leaked else f"forbidden={','.join(leaked)}",
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks: list[EvalCheck] = []
    results: list[ConformanceEvaluation] = []
    for scenario in corpus["scenarios"]:
        if scenario["outcome"] == "result":
            check, result = _result_check(scenario)
            checks.append(check)
            results.append(result)
        elif scenario["outcome"] == "paired_result":
            check, paired = _conditional_check(scenario)
            checks.append(check)
            results.extend(paired)
        else:
            checks.append(_authorization_check(scenario))
    deterministic, canonical_result = _determinism_check()
    checks.extend((deterministic, _boundary([*results, canonical_result])))
    passed = (
        corpus["module_id"] == MODULE_ID
        and len(corpus["scenarios"]) == EXPECTED_SCENARIO_COUNT
        and all(check.passed for check in checks)
    )
    report = {
        "module_id": MODULE_ID,
        "passed": passed,
        "scenario_count": len(corpus["scenarios"]),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
