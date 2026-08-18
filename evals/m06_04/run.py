"""Replay the locked synthetic M06-04 estimator fixture matrix."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from glio_proteogen.contracts.m06_01 import (
    FormalProteinStateSchema,
    FormalStateFeatureDefinition,
    FormalStateFeatureValue,
    FormalStateFeatureValueKind,
    FormalStateMissingness,
)
from glio_proteogen.contracts.m06_04 import (
    EstimatorConstraint,
    ProbabilisticEstimatorConfiguration,
    ProbabilisticEstimatorFamily,
    ProbabilisticPrior,
    ProbabilisticPriorKind,
)
from glio_proteogen.kernel.canonical import canonical_json_bytes, sha256_digest
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
from glio_proteogen.modules.c06_protein_abundance.m06_04_probabilistic_advanced_estimator import (
    M0604_PROXY_OPTIMIZER,
    M0604ProbabilisticEstimatorEngine,
    ProbabilisticEstimatorAuthorizationError,
    ProbabilisticEstimatorInputError,
)

MODULE_ID: Final = "GLIO-PROTEOGEN-M06-04"
ROOT: Final = Path(__file__).parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m06_04" / "scenarios.json"


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
        artifact_id=f"m0604.synthetic.{name}",
        version="1.0.0",
        digest=sha256_digest({"m0604": name}),
        media_type="application/json",
    )


def _context(*, denied: bool = False) -> ExecutionContext:
    evidence = _artifact("control")

    def decision(name: str, state: UpstreamDecisionState) -> UpstreamDecisionReference:
        return UpstreamDecisionReference(
            decision_id=f"decision.m0604.{name}",
            state=state,
            policy_version="1.0.0",
            evidence=evidence,
        )

    return ExecutionContext(
        request_id="request.m0604.synthetic",
        actor_id="actor.m0604.synthetic",
        occurred_at=datetime(2026, 8, 15, 12, tzinfo=UTC),
        references=ContextReferences(
            approved_configuration=decision("configuration", UpstreamDecisionState.ACCEPTED),
            identity_lineage=IdentityLineageReference(
                decision_id="decision.m0604.identity",
                state=IdentityLineageState.RESOLVED,
                policy_version="1.0.0",
                binding_digest=sha256_digest("identity"),
                evidence=evidence,
            ),
            provenance=decision("provenance", UpstreamDecisionState.ACCEPTED),
            consent=ConsentReference(
                decision_id="decision.m0604.consent",
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


def _schema(*, categorical: bool = False) -> FormalProteinStateSchema:
    return FormalProteinStateSchema(
        schema_id="schema.m0604.synthetic",
        version="1.0.0",
        features=(
            FormalStateFeatureDefinition(
                feature_id="protein.abundance",
                version="1.0.0",
                value_kind=(
                    FormalStateFeatureValueKind.CATEGORICAL
                    if categorical
                    else FormalStateFeatureValueKind.SCALAR
                ),
                unit="class" if categorical else "normalized",
                allowed_missingness=(
                    FormalStateMissingness.OBSERVED,
                    FormalStateMissingness.MISSING,
                ),
                domain_lower=None if categorical else 0.0,
                allowed_categories=("low", "high") if categorical else (),
            ),
        ),
    )


def build_scenario_request(request_case: str) -> dict[str, object]:
    categorical = request_case == "categorical"
    schema = _schema(categorical=categorical)
    value = FormalStateFeatureValue(
        feature_id="protein.abundance",
        state=(
            FormalStateMissingness.MISSING
            if request_case == "missing"
            else FormalStateMissingness.OBSERVED
        ),
        unit="class" if categorical else "normalized",
        scalar_value=None if request_case in {"missing", "categorical"} else 0.5,
        category="high" if categorical else None,
    )
    family = (
        ProbabilisticEstimatorFamily.LEARNED
        if request_case == "learned"
        else ProbabilisticEstimatorFamily.MECHANISM_GUIDED
    )
    optimizer = "unknown-v2" if request_case == "unknown_optimizer" else M0604_PROXY_OPTIMIZER
    configuration = ProbabilisticEstimatorConfiguration(
        configuration_id="configuration.m0604.synthetic",
        version="1.0.0",
        estimator_family=family,
        state_schema_id=schema.schema_id,
        state_schema_version=schema.version,
        objective="estimate normalized abundance",
        priors=(
            ProbabilisticPrior(
                prior_id="prior.abundance",
                version="1.0.0",
                kind=ProbabilisticPriorKind.NORMAL,
                parameters=(0.0, 1.0),
            ),
        ),
        constraints=(
            EstimatorConstraint(
                constraint_id="constraint.nonnegative",
                expression="protein.abundance >= 0",
                hard=True,
            ),
        ),
        optimizer=optimizer,
        seed=7,
        max_iterations=100,
        reference=_artifact("configuration"),
    )
    return {
        "request_id": "request.m0604.synthetic",
        "context": _context(denied=request_case == "denied"),
        "state_schema": schema,
        "feature_values": (value,),
        "representation_artifact": _artifact("representation"),
        "configuration": configuration,
        "source_artifacts": (_artifact("source"),),
    }


def _corpus() -> Corpus:
    return cast("Corpus", json.loads(SCENARIO_PATH.read_text(encoding="utf-8")))


def _result_check(scenario: Scenario) -> EvalCheck:
    request = build_scenario_request(scenario["request_case"])
    engine = M0604ProbabilisticEstimatorEngine()
    result = engine.estimate(request)
    replay = engine.estimate(canonical_json_bytes(request))
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
        M0604ProbabilisticEstimatorEngine().estimate(
            build_scenario_request(scenario["request_case"])
        )
    except (ProbabilisticEstimatorAuthorizationError, ProbabilisticEstimatorInputError):
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
    result = M0604ProbabilisticEstimatorEngine().estimate(build_scenario_request("valid"))
    payload = result.model_dump(mode="python")
    payload["result_digest"] = "sha256:" + ("f" * 64)
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
