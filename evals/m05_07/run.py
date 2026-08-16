"""Replay the locked M05-07 support-routing fixture matrix."""

# The scenario dispatcher intentionally exposes each named fixture case.
# ruff: noqa: PLR0911

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

from pydantic import ValidationError

from glio_proteogen.contracts.m05_07 import (
    M0507_M0506_RESULT_MEDIA_TYPE,
    PtmLocalizationDeclaredSupportState,
    PtmLocalizationDimensionSupportDecision,
    PtmLocalizationSupportDimension,
    PtmLocalizationSupportFact,
    PtmLocalizationSupportPolicy,
    PtmLocalizationSupportPrerequisites,
    RoutePtmLocalizationSupportRequest,
    canonical_request_digest,
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
from glio_proteogen.modules.c05_ptm_localization.m05_07_unsupported_abstention_router import (
    M0507PtmLocalizationSupportEngine,
    PtmLocalizationSupportAuthorizationError,
    PtmLocalizationSupportInputError,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M05-07"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m05_07" / "scenarios.json"
EXPECTED_DIMENSIONS: Final = tuple(PtmLocalizationSupportDimension)


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "matrix", "validation_rejected"]
    expected_disposition: str | None
    expected_code: str | None
    expected_dimensions: list[str]


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


def _artifact(label: str, media_type: str = "application/json") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"artifact.synthetic.m0507.{label}",
        version="1.0.0",
        digest=sha256_digest({"m0507": label}),
        media_type=media_type,
    )


def _context(*, denied: bool = False) -> ExecutionContext:
    def decision(
        role: str, state: UpstreamDecisionState = UpstreamDecisionState.ACCEPTED
    ) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.synthetic.m0507.{role}",
            state=state,
            policy_version="1.0.0",
            evidence=_artifact(role),
        )

    return ExecutionContext(
        request_id="request.synthetic.m0507",
        actor_id="actor.synthetic.m0507",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration"),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.synthetic.m0507.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest({"m0507": "identity"}),
                evidence=_artifact("identity"),
            ),
            provenance=decision("provenance"),
            consent=ConsentReference(
                decision_id="decision.synthetic.m0507.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=_artifact("consent"),
            ),
            quality=decision(
                "quality",
                UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED,
            ),
            support=decision("support"),
            intended_use=decision("intended-use"),
        ),
    )


def _facts() -> tuple[PtmLocalizationSupportFact, ...]:
    return tuple(
        PtmLocalizationSupportFact(
            dimension=dimension,
            state=PtmLocalizationDeclaredSupportState.OBSERVED,
            decision=PtmLocalizationDimensionSupportDecision.SUPPORTED,
            rationale="Synthetic reviewed support declaration is present.",
        )
        for dimension in EXPECTED_DIMENSIONS
    )


def _request(
    *,
    outside: frozenset[PtmLocalizationSupportDimension] = frozenset(),
    unknown: frozenset[PtmLocalizationSupportDimension] = frozenset(),
    missing: frozenset[PtmLocalizationSupportDimension] = frozenset(),
    denied: bool = False,
    tampered_prerequisite: bool = False,
) -> RoutePtmLocalizationSupportRequest:
    facts = list(_facts())
    for index, fact in enumerate(facts):
        if fact.dimension in outside:
            facts[index] = fact.model_copy(
                update={"decision": PtmLocalizationDimensionSupportDecision.OUTSIDE_DOMAIN}
            )
        elif fact.dimension in unknown:
            facts[index] = fact.model_copy(
                update={
                    "state": PtmLocalizationDeclaredSupportState.UNKNOWN,
                    "decision": PtmLocalizationDimensionSupportDecision.INDETERMINATE,
                }
            )
        elif fact.dimension in missing:
            facts[index] = fact.model_copy(
                update={
                    "state": PtmLocalizationDeclaredSupportState.MISSING,
                    "decision": PtmLocalizationDimensionSupportDecision.INDETERMINATE,
                }
            )
    media_type = "application/json" if tampered_prerequisite else M0507_M0506_RESULT_MEDIA_TYPE
    return RoutePtmLocalizationSupportRequest(
        request_id="request.synthetic.m0507",
        context=_context(denied=denied),
        prerequisites=PtmLocalizationSupportPrerequisites(
            harmonization_result=_artifact("harmonization", media_type)
        ),
        policy=PtmLocalizationSupportPolicy(
            policy_id="policy.synthetic.m0507",
            version="1.0.0",
            dimensions=EXPECTED_DIMENSIONS,
            reviewed_by="reviewer.synthetic.m0507",
            reviewed_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
            evidence=_artifact("policy"),
        ),
        declared_facts=tuple(facts),
    )


def build_scenario_request(
    request_case: str, dimension: PtmLocalizationSupportDimension | None = None
) -> RoutePtmLocalizationSupportRequest:
    if request_case == "supported":
        return _request()
    if request_case == "outside_matrix" and dimension is not None:
        return _request(outside=frozenset({dimension}))
    if request_case == "unknown":
        return _request(unknown=frozenset({PtmLocalizationSupportDimension.QUALITY}))
    if request_case == "missing":
        return _request(missing=frozenset({PtmLocalizationSupportDimension.COMPLETENESS}))
    if request_case == "multiple":
        return _request(
            outside=frozenset({PtmLocalizationSupportDimension.ASSAY}),
            unknown=frozenset({PtmLocalizationSupportDimension.REFERENCE}),
        )
    if request_case == "denied_control":
        return _request(denied=True)
    if request_case == "tampered_prerequisite":
        return _request(tampered_prerequisite=True)
    raise ValueError(request_case)


def _result_check(scenario: Scenario) -> EvalCheck:
    request = build_scenario_request(scenario["request_case"])
    result = M0507PtmLocalizationSupportEngine().route(request)
    replay = M0507PtmLocalizationSupportEngine().route(request.model_dump(mode="json"))
    dimensions = [item.value for item in result.receipt.unsupported_dimensions]
    passed = (
        result == replay
        and result.disposition.value == scenario["expected_disposition"]
        and (result.abstention_code.value if result.abstention_code else None)
        == scenario["expected_code"]
        and dimensions == scenario["expected_dimensions"]
        and result.request_digest == canonical_request_digest(request)
        and result.receipt.request_digest == result.request_digest
    )
    return EvalCheck(
        f"scenario.{scenario['case_id']}",
        passed,
        f"disposition={result.disposition.value};dimensions={','.join(dimensions)};"
        f"replay={result == replay}",
    )


def _matrix_check(scenario: Scenario) -> EvalCheck:
    actual: list[str] = []
    passed = True
    for dimension in EXPECTED_DIMENSIONS:
        result = M0507PtmLocalizationSupportEngine().route(
            build_scenario_request(scenario["request_case"], dimension)
        )
        actual.extend(item.value for item in result.receipt.unsupported_dimensions)
        passed = passed and (
            result.disposition.value == scenario["expected_disposition"]
            and (result.abstention_code.value if result.abstention_code else None)
            == scenario["expected_code"]
            and [item.value for item in result.receipt.unsupported_dimensions] == [dimension.value]
        )
    return EvalCheck(
        f"scenario.{scenario['case_id']}",
        passed and actual == scenario["expected_dimensions"],
        f"isolated={','.join(actual)}",
    )


def _rejection_check(scenario: Scenario) -> EvalCheck:
    if scenario["request_case"] == "tampered_prerequisite":
        payload = _request().model_dump(mode="json")
        prerequisites = cast("dict[str, object]", payload["prerequisites"])
        harmonization = cast("dict[str, object]", prerequisites["harmonization_result"])
        harmonization["media_type"] = "application/json"
        request: object = payload
    else:
        request = build_scenario_request(scenario["request_case"])
    try:
        M0507PtmLocalizationSupportEngine().route(request)
    except (
        PtmLocalizationSupportAuthorizationError,
        PtmLocalizationSupportInputError,
        ValidationError,
    ):
        return EvalCheck(
            f"scenario.{scenario['case_id']}", passed=True, detail="rejected before route"
        )
    return EvalCheck(
        f"scenario.{scenario['case_id']}",
        passed=False,
        detail="request unexpectedly routed",
    )


def _tamper_checks() -> tuple[EvalCheck, ...]:
    request = build_scenario_request("supported")
    result = M0507PtmLocalizationSupportEngine().route(request)
    result_payload = result.model_dump(mode="python")
    result_payload["result_digest"] = "sha256:" + "f" * 64
    try:
        type(result).model_validate(result_payload)
    except ValidationError:
        digest_check = EvalCheck("tamper.result_digest", passed=True, detail="tamper rejected")
    else:
        digest_check = EvalCheck("tamper.result_digest", passed=False, detail="tamper accepted")
    request_payload = request.model_dump(mode="json")
    request_payload["unexpected"] = True
    try:
        M0507PtmLocalizationSupportEngine().route(request_payload)
    except PtmLocalizationSupportInputError:
        request_check = EvalCheck(
            "tamper.request_extra", passed=True, detail="extra field rejected"
        )
    else:
        request_check = EvalCheck(
            "tamper.request_extra", passed=False, detail="extra field accepted"
        )
    return digest_check, request_check


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    corpus = _corpus()
    checks: list[EvalCheck] = []
    for scenario in corpus["scenarios"]:
        if scenario["outcome"] == "matrix":
            checks.append(_matrix_check(scenario))
        elif scenario["outcome"] == "validation_rejected":
            checks.append(_rejection_check(scenario))
        else:
            checks.append(_result_check(scenario))
    checks.extend(_tamper_checks())
    checks.append(
        EvalCheck(
            "corpus.dimensions",
            corpus["module_id"] == MODULE_ID
            and tuple(corpus["dimensions"]) == tuple(item.value for item in EXPECTED_DIMENSIONS),
            "eight closed support dimensions",
        )
    )
    report = {
        "module_id": MODULE_ID,
        "passed": all(check.passed for check in checks),
        "scenario_count": len(corpus["scenarios"]),
        "corpus_digest": sha256_digest(corpus),
        "checks": [asdict(check) for check in checks],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
