"""Executable evaluator and adversarial evidence for M17-04."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.runtime.test_m17_04_adapter import _artifact, _context, _request

from glio_proteogen.contracts.m17_04 import (
    AdapterFindingCode,
    AdaptVariantPeptideIntendedUseRequest,
    IntendedUseKind,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_04_intended_use_adapter as m1704,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m17_04" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M17-04"
EXPECTED_SCENARIOS: Final = 7
EXPECTED_ADVERSARIAL_CASES: Final = 8


@dataclass(frozen=True, slots=True)
class EvalCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    module_id: str
    dossier_sha256: str
    dossier_slice: str
    scenario_count: int
    adversarial_case_count: int
    adversarial_passed_count: int
    adversarial_coverage_percent: float
    target_percent: int
    checks: tuple[EvalCheck, ...]
    passed: bool


def _consent_denied_request() -> AdaptVariantPeptideIntendedUseRequest:
    request = _request()
    context = _context()
    references = context.references.model_copy(
        update={
            "consent": context.references.consent.model_copy(
                update={"state": ConsentState.WITHHELD}
            )
        }
    )
    return request.model_copy(
        update={"context": context.model_copy(update={"references": references})}
    )


def _scenario(name: str) -> AdaptVariantPeptideIntendedUseRequest:  # noqa: PLR0911
    if name == "research_allowed":
        return _request()
    if name == "clinical_review_required":
        return _request(
            intended_use=IntendedUseKind.CLINICAL_REVIEW,
            audience="clinical_review_board",
            evidence_tier=3,
        )
    if name == "treatment_blocked":
        return _request(maximum_claim="direct treatment recommendation")
    if name == "audience_blocked":
        return _request(audience="unregistered_audience")
    if name == "display_blocked":
        return _request(sections=("evidence",))
    if name == "control_denied":
        return _consent_denied_request()
    if name == "replay_tamper":
        return _request()
    raise ValueError(f"unknown M17-04 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(names) == EXPECTED_SCENARIOS,
            f"observed={len(names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    engine = m1704.M1704Engine()
    scenario_oracles_passed = True
    for name in names:
        try:
            result = engine.adapt(_scenario(name))
        except m1704.M1704AuthorizationError:
            scenario_oracles_passed &= name == "control_denied"
        else:
            scenario_oracles_passed &= (
                name != "control_denied" and result.parent_target == "variant peptide"
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_oracles_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )

    allowed = engine.adapt(_scenario("research_allowed"))
    checks.extend(
        (
            EvalCheck(
                "allowed.bounded_object",
                allowed.status.value == "adapted"
                and allowed.adapted_object is not None
                and allowed.emits_parent is False,
                "registered research use emits only the bounded object",
            ),
            EvalCheck(
                "allowed.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        allowed.uncertainty.measurement,
                        allowed.uncertainty.sampling,
                        allowed.uncertainty.parameter,
                        allowed.uncertainty.model_form,
                        allowed.uncertainty.identification,
                        allowed.uncertainty.support,
                        allowed.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
        )
    )
    review = engine.adapt(_scenario("clinical_review_required"))
    checks.append(
        EvalCheck(
            "review.clinical_use",
            review.policy_decision.status.value == "review_required"
            and review.human_review_required is True,
            "clinical review remains externally review-required",
        )
    )
    tampered = engine.adapt(_scenario("replay_tamper")).model_copy(
        update={"human_review_required": True}
    )
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1704.M1704ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = 0
    for request, expected in (
        (
            _request(maximum_claim="direct treatment recommendation"),
            AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED,
        ),
        (
            _request(maximum_claim="kinase activity claim"),
            AdapterFindingCode.CLAIM_EXCEEDS_CEILING,
        ),
        (_request(audience="unregistered_audience"), AdapterFindingCode.AUDIENCE_UNSUPPORTED),
        (
            _request(
                intended_use=IntendedUseKind.CLINICAL_REVIEW,
                audience="clinical_review_board",
                evidence_tier=1,
            ),
            AdapterFindingCode.EVIDENCE_TIER_MISSING,
        ),
        (_request(sections=("evidence",)), AdapterFindingCode.DISPLAY_SEMANTICS_INCOMPLETE),
    ):
        result = engine.adapt(request)
        adversarial_passed += int(
            result.status.value == "abstained"
            and any(finding.code is expected for finding in result.findings)
        )
    try:
        engine.adapt(_consent_denied_request())
    except m1704.M1704AuthorizationError:
        adversarial_passed += 1
    try:
        engine.adapt(_request().model_copy(update={"upstream_result": _artifact("bad-media")}))
    except ValidationError:
        adversarial_passed += 1
    try:
        engine.replay(tampered)
    except m1704.M1704ReplayError:
        adversarial_passed += 1
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100
            >= metadata["coverage_target_percent"],
            f"passed={adversarial_passed}/{EXPECTED_ADVERSARIAL_CASES}",
        )
    )
    return EvaluationReport(
        module_id=MODULE_ID,
        dossier_sha256=metadata["dossier_sha256"],
        dossier_slice=metadata["dossier_slice"],
        scenario_count=len(names),
        adversarial_case_count=EXPECTED_ADVERSARIAL_CASES,
        adversarial_passed_count=adversarial_passed,
        adversarial_coverage_percent=adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100,
        target_percent=metadata["coverage_target_percent"],
        checks=tuple(checks),
        passed=all(check.passed for check in checks),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rendered = json.dumps(asdict(evaluate()), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if json.loads(rendered)["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
