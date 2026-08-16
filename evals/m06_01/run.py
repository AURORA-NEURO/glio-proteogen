"""Replay the locked synthetic M06-01 formal-state fixture matrix."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

from pydantic import ValidationError

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateInvariant,
    FormalStateInvariantSeverity,
    FormalStateMissingness,
    ValidateFormalProteinStateRequest,
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
from glio_proteogen.modules.c06_protein_abundance.m06_01_formal_state_schema import (
    FormalStateAuthorizationError,
    M0601FormalStateEngine,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M06-01"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m06_01" / "scenarios.json"


class Scenario(TypedDict):
    case_id: str
    request_case: str
    outcome: Literal["result", "validation_rejected"]
    expected_status: str | None
    expected_support: str | None


class Corpus(TypedDict):
    module_id: str
    schema_version: str
    data_classification: str
    claims_ceiling: str
    scenarios: list[Scenario]


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        artifact_id=f"m0601.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest({"m0601": name}),
        media_type="application/json",
    )


def _context(*, denied: bool = False) -> ExecutionContext:
    evidence = _artifact("control")

    def decision(name: str, state: UpstreamDecisionState) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.m0601.{name}",
            state=state,
            policy_version="1.0.0",
            evidence=evidence,
        )

    return ExecutionContext(
        request_id="request.m0601.synthetic",
        actor_id="actor.m0601.synthetic",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", UpstreamDecisionState.ACCEPTED),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0601.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=evidence,
            ),
            provenance=decision("provenance", UpstreamDecisionState.ACCEPTED),
            consent=ConsentReference(
                decision_id="decision.m0601.consent",
                state=ConsentState.GRANTED,
                policy_version="1.0.0",
                evidence=evidence,
            ),
            quality=decision(
                "quality",
                UpstreamDecisionState.REJECTED if denied else UpstreamDecisionState.ACCEPTED,
            ),
            support=decision("support", UpstreamDecisionState.ACCEPTED),
            intended_use=decision("intended-use", UpstreamDecisionState.ACCEPTED),
        ),
    )


def _schema(expression: str = "protein.abundance >= 0") -> FormalProteinStateSchema:
    return FormalProteinStateSchema(
        schema_id="schema.m0601.synthetic",
        version="1.0.0",
        features=(
            FormalStateFeatureDefinition(
                feature_id="protein.abundance",
                version="1.0.0",
                value_kind=FormalStateFeatureValueKind.SCALAR,
                unit="normalized",
                allowed_missingness=(
                    FormalStateMissingness.OBSERVED,
                    FormalStateMissingness.MISSING,
                ),
                domain_lower=0.0,
                domain_upper=1.0,
            ),
        ),
        invariants=(
            FormalStateInvariant(
                invariant_id="invariant.nonnegative",
                expression=expression,
                severity=FormalStateInvariantSeverity.ERROR,
                feature_ids=("protein.abundance",),
            ),
        ),
    )


def build_scenario_request(request_case: str) -> ValidateFormalProteinStateRequest:
    expression = "protein.abundance >= 0"
    state = FormalStateMissingness.OBSERVED
    value: float | None = 0.5
    denied = False
    if request_case == "violated":
        expression = "protein.abundance > 0.75"
    elif request_case == "missing":
        state = FormalStateMissingness.MISSING
        value = None
    elif request_case == "unsupported_expression":
        expression = "protein.abundance + 1"
    elif request_case == "incompatible":
        expression = 'protein.abundance == "class_a"'
    elif request_case == "denied":
        denied = True
    elif request_case != "valid":
        raise ValueError(request_case)
    return ValidateFormalProteinStateRequest(
        request_id="request.m0601.synthetic",
        context=_context(denied=denied),
        state_schema=_schema(expression),
        values=(
            FormalStateFeatureValue(
                feature_id="protein.abundance",
                state=state,
                unit="normalized",
                scalar_value=value,
            ),
        ),
        source_artifacts=(_artifact("proteome"), _artifact("genome")),
    )


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _result_check(scenario: Scenario) -> EvalCheck:
    request = build_scenario_request(scenario["request_case"])
    result = M0601FormalStateEngine().validate(request)
    replay = M0601FormalStateEngine().validate(request.model_dump(mode="json"))
    passed = (
        result == replay
        and result.status.value == scenario["expected_status"]
        and result.support_decision.status.value == scenario["expected_support"]
    )
    return EvalCheck(
        f"scenario.{scenario['case_id']}",
        passed,
        (
            f"status={result.status.value};support={result.support_decision.status.value};"
            f"replay={result == replay}"
        ),
    )


def _rejection_check(scenario: Scenario) -> EvalCheck:
    try:
        M0601FormalStateEngine().validate(build_scenario_request(scenario["request_case"]))
    except (FormalStateAuthorizationError, ValidationError):
        return EvalCheck(
            f"scenario.{scenario['case_id']}",
            passed=True,
            detail="rejected before execution",
        )
    return EvalCheck(
        f"scenario.{scenario['case_id']}",
        passed=False,
        detail="request unexpectedly executed",
    )


def _tamper_check() -> EvalCheck:
    result = M0601FormalStateEngine().validate(build_scenario_request("valid"))
    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + "f" * 64
    try:
        type(result).model_validate(payload)
    except ValidationError:
        return EvalCheck(
            "tamper.result_digest",
            passed=True,
            detail="result digest tamper rejected",
        )
    return EvalCheck(
        "tamper.result_digest",
        passed=False,
        detail="result digest tamper accepted",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    corpus = _corpus()
    checks = [
        _rejection_check(scenario)
        if scenario["outcome"] == "validation_rejected"
        else _result_check(scenario)
        for scenario in corpus["scenarios"]
    ]
    checks.append(_tamper_check())
    checks.append(
        EvalCheck(
            "corpus.module",
            corpus["module_id"] == MODULE_ID and corpus["schema_version"] == "0.1.0-provisional",
            "locked provisional corpus metadata",
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
