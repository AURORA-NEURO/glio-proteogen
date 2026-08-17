"""Replay the locked M01-07 support-routing fixture and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, NotRequired, TypedDict, cast

from pydantic import TypeAdapter, ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m01_07 import (
    CriterionKind,
    EvidenceState,
    RouteSupportRequest,
    SupportCriterion,
    SupportDimension,
    SupportEvidence,
    SupportRoutingPolicy,
    SupportRoutingProfile,
    SupportRoutingResult,
    configuration_digest,
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
from glio_proteogen.modules.c01_preanalytic.m01_07_support_router import (
    route_support_request,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M01-07"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m01_07" / "scenarios.json"
EXPECTED_SCENARIO_COUNT: Final = 7
EXPECTED_DIMENSION_COUNT: Final = 8
OPTIONAL_DIMENSION: Final = SupportDimension.COMPLETENESS
_REQUEST_ADAPTER: Final = TypeAdapter(RouteSupportRequest)


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "matrix", "validation_rejected"]
    expected_decision: str | None
    expected_abstentions: NotRequired[list[object]]
    expected_dimensions: NotRequired[list[str]]
    expected_reason_state: NotRequired[str]


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
    dimensions: list[str]
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
        digest=digest or sha256_digest({"m0107": label}),
        media_type="application/json",
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
        request_id="request.synthetic.m0107",
        actor_id="actor.synthetic.eval",
        occurred_at=datetime(2026, 8, 12, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", configuration),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0107": "identity-binding"}),
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


def _criterion(dimension: SupportDimension) -> SupportCriterion:
    optional = dimension is OPTIONAL_DIMENSION
    return SupportCriterion(
        criterion_id=f"criterion.{dimension.value}",
        dimension=dimension,
        evidence_id=f"evidence.{dimension.value}",
        kind=CriterionKind.TERM_IN_SET,
        required=not optional,
        allow_not_applicable=optional,
        allowed_terms=(f"supported.{dimension.value}",),
        reason_code=f"unsupported.{dimension.value}",
        remediation_code=f"remediate.{dimension.value}",
        remediation_path=f"Provide reviewed {dimension.value.replace('_', ' ')} evidence.",
    )


def _profile() -> SupportRoutingProfile:
    return SupportRoutingProfile(
        profile_id="profile.synthetic.support-routing",
        version="1.0.0",
        criteria=tuple(_criterion(dimension) for dimension in SupportDimension),
        evidence=_artifact("support-routing-profile"),
    )


def _policy() -> SupportRoutingPolicy:
    return SupportRoutingPolicy(
        policy_id="policy.synthetic.support-routing",
        version="1.0.0",
    )


def _evidence(
    dimension: SupportDimension,
    *,
    state: EvidenceState = EvidenceState.OBSERVED,
    supported: bool = True,
) -> SupportEvidence:
    value: str | None = None
    if state is EvidenceState.OBSERVED:
        value = (
            f"supported.{dimension.value}"
            if supported
            else f"unsupported.{dimension.value}"
        )
    return SupportEvidence(
        evidence_id=f"evidence.{dimension.value}",
        dimension=dimension,
        state=state,
        value=value,
        evidence=(_artifact(f"evidence.{dimension.value}"),),
    )


def _request(
    *,
    unsupported: frozenset[SupportDimension] = frozenset(),
    states: dict[SupportDimension, EvidenceState] | None = None,
) -> RouteSupportRequest:
    profile = _profile()
    policy = _policy()
    overrides = states or {}
    evidence = tuple(
        _evidence(
            dimension,
            state=overrides.get(dimension, EvidenceState.OBSERVED),
            supported=dimension not in unsupported,
        )
        for dimension in SupportDimension
    )
    return RouteSupportRequest(
        context=_context(configuration_digest(profile, policy)),
        profile=profile,
        policy=policy,
        evidence=evidence,
    )


def build_scenario_request(
    request_case: str,
    *,
    unsupported_dimension: SupportDimension | None = None,
) -> RouteSupportRequest:
    """Build one strict deterministic request for eval and benchmark reuse."""

    if request_case in {"supported", "consent_denied"}:
        return _request()
    if request_case == "unsupported_matrix" and unsupported_dimension is not None:
        return _request(unsupported=frozenset({unsupported_dimension}))
    if request_case == "missing_required":
        return _request(states={SupportDimension.QUALITY: EvidenceState.MISSING})
    if request_case == "unknown_required":
        return _request(states={SupportDimension.REFERENCE: EvidenceState.UNKNOWN})
    if request_case == "optional_not_applicable":
        return _request(states={OPTIONAL_DIMENSION: EvidenceState.NOT_APPLICABLE})
    if request_case == "multiple_failures":
        return _request(
            unsupported=frozenset({SupportDimension.ASSAY}),
            states={
                SupportDimension.QUALITY: EvidenceState.MISSING,
                SupportDimension.REFERENCE: EvidenceState.UNKNOWN,
            },
        )
    raise ValueError(request_case)


def _reordered(request: RouteSupportRequest) -> RouteSupportRequest:
    profile = request.profile.model_copy(
        update={
            "criteria": tuple(
                item.model_copy(update={"allowed_terms": tuple(reversed(item.allowed_terms))})
                for item in reversed(request.profile.criteria)
            )
        }
    )
    return request.model_copy(
        update={
            "profile": profile,
            "evidence": tuple(
                item.model_copy(update={"evidence": tuple(reversed(item.evidence))})
                for item in reversed(request.evidence)
            ),
        }
    )


def _blocking_dimensions(result: SupportRoutingResult) -> list[str]:
    return [item.dimension.value for item in result.assessments if item.blocks_route]


def _expected_explanation(result: SupportRoutingResult) -> bool:
    return all(
        (
            item.reason_code == f"unsupported.{item.dimension.value}"
            and item.remediation_code == f"remediate.{item.dimension.value}"
            and item.remediation_path
            == f"Provide reviewed {item.dimension.value.replace('_', ' ')} evidence."
        )
        for item in result.assessments
        if item.decision.value != "supported"
    )


def _result_check(scenario: Scenario) -> tuple[EvalCheck, dict[str, object]]:
    request = build_scenario_request(scenario["request_case"])
    result = route_support_request(request)
    replay = route_support_request(_reordered(request))
    dimensions = _blocking_dimensions(result)
    expected_dimensions = scenario.get("expected_dimensions", [])
    expected_state = scenario.get("expected_reason_state")
    state_matches = expected_state is None or any(
        item.dimension.value in expected_dimensions
        and item.evidence_state.value == expected_state
        for item in result.assessments
    )
    passed = (
        result == replay
        and result.decision.value == scenario["expected_decision"]
        and dimensions == expected_dimensions
        and state_matches
        and _expected_explanation(result)
    )
    return (
        EvalCheck(
            f"scenario.{scenario['case_id']}",
            passed,
            f"decision={result.decision.value};blocks={','.join(dimensions)};"
            f"order_equal={result == replay}",
        ),
        cast("dict[str, object]", result.model_dump(mode="json")),
    )


def _matrix_check(scenario: Scenario) -> tuple[EvalCheck, list[dict[str, object]]]:
    expected = scenario["expected_dimensions"]
    actual: list[str] = []
    results: list[dict[str, object]] = []
    valid = True
    for dimension in SupportDimension:
        request = build_scenario_request(
            scenario["request_case"],
            unsupported_dimension=dimension,
        )
        result = route_support_request(request)
        replay = route_support_request(_reordered(request))
        blocks = _blocking_dimensions(result)
        valid = valid and (
            result == replay
            and result.decision.value == scenario["expected_decision"]
            and blocks == [dimension.value]
            and _expected_explanation(result)
        )
        actual.extend(blocks)
        results.append(cast("dict[str, object]", result.model_dump(mode="json")))
    return (
        EvalCheck(
            f"scenario.{scenario['case_id']}",
            valid and actual == expected,
            f"isolated={','.join(actual)};order_equal={valid}",
        ),
        results,
    )


def _consent_rejected() -> bool:
    request = build_scenario_request("consent_denied")
    payload = request.model_dump(mode="python")
    payload["context"]["references"]["consent"]["state"] = ConsentState.WITHHELD
    try:
        _REQUEST_ADAPTER.validate_python(payload, strict=True)
    except ValidationError:
        return True
    return False


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _boundary_check(results: list[dict[str, object]]) -> EvalCheck:
    forbidden = {
        "generic_omics_fusion",
        "kinase_activity",
        "proteotype",
        "raw_payload",
        "raw_spectra",
        "treatment_recommendation",
        "upstream_mutations",
    }
    leaked = sorted(_all_keys(results).intersection(forbidden))
    return EvalCheck(
        "boundary.support_routing_output_only",
        not leaked,
        "closed support-routing output" if not leaked else f"forbidden={','.join(leaked)}",
    )


def _corpus() -> Corpus:
    return cast("Corpus", strict_json_loads(SCENARIO_PATH.read_bytes()))


def _checks(corpus: Corpus) -> tuple[list[EvalCheck], list[dict[str, object]]]:
    checks: list[EvalCheck] = []
    results: list[dict[str, object]] = []
    for scenario in corpus["scenarios"]:
        if scenario["outcome"] == "validation_rejected":
            rejected = _consent_rejected()
            checks.append(
                EvalCheck(
                    f"scenario.{scenario['case_id']}",
                    rejected,
                    "strict request validation rejected consent" if rejected else "not rejected",
                )
            )
        elif scenario["outcome"] == "matrix":
            check, matrix_results = _matrix_check(scenario)
            checks.append(check)
            results.extend(matrix_results)
        else:
            check, serialized_result = _result_check(scenario)
            checks.append(check)
            results.append(serialized_result)
    return checks, results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    corpus = _corpus()
    checks, results = _checks(corpus)
    checks.append(_boundary_check(results))
    passed = (
        corpus["module_id"] == MODULE_ID
        and corpus["data_classification"] == "synthetic_nonclinical"
        and corpus["claims_ceiling"]
        == "deterministic_routing_fixtures_not_support_domain_validation"
        and corpus["dimensions"] == [dimension.value for dimension in SupportDimension]
        and len(SupportDimension) == EXPECTED_DIMENSION_COUNT
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
