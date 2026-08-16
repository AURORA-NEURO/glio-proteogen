"""Executable evaluator for the provisional M18-04 intended-use adapter."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from tests.contract.test_m18_04_deep import _registration, _request

from glio_proteogen.contracts.m18_04 import (
    AdaptBiomarkerPanelIntendedUseRequest,
    IntendedUseKind,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_04_intended_use_adapter as m1804,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m18_04" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M18-04"
DOSSIER_SHA256: Final = "0a6b200cbe073db13a4bcf315edc23ab97edfe6f500bc7ea2785f5e1c70da181"
DOSSIER_SLICE: Final = "6288-6328"
EXPECTED_SCENARIOS: Final = 8
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


def _claim_request(claim: str) -> AdaptBiomarkerPanelIntendedUseRequest:
    registration = _registration()
    ceiling = registration.claim_ceiling.model_copy(update={"maximum_claim": claim})
    return _request(registration.model_copy(update={"claim_ceiling": ceiling}))


def _consent_denied_request() -> AdaptBiomarkerPanelIntendedUseRequest:
    request = _request()
    references = request.context.references
    consent = references.consent.model_copy(update={"state": ConsentState.REVOKED})
    return request.model_copy(
        update={
            "context": request.context.model_copy(
                update={"references": references.model_copy(update={"consent": consent})}
            )
        }
    )


def _scenario(name: str) -> AdaptBiomarkerPanelIntendedUseRequest:  # noqa: PLR0911
    if name == "research_allowed":
        return _request()
    if name == "clinical_review_required":
        return _request(
            _registration(
                intended_use=IntendedUseKind.CLINICAL_REVIEW,
                audience="clinical_review",
                evidence_tier=3,
            )
        )
    if name == "audience_blocked":
        return _request(_registration(audience="unregistered_audience"))
    if name == "evidence_tier_blocked":
        return _request(
            _registration(intended_use=IntendedUseKind.CLINICAL_REVIEW, evidence_tier=1)
        )
    if name == "display_blocked":
        return _request(_registration(sections=("evidence",)))
    if name == "treatment_blocked":
        return _claim_request("Treatment recommendation for the patient.")
    if name == "forbidden_claim_blocked":
        return _claim_request("Kinase activity and subtype diagnosis.")
    if name == "replay_tamper":
        return _request()
    raise ValueError(f"unknown M18-04 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    names = tuple(metadata["scenario_names"])
    engine = m1804.M1804Engine()
    checks = [
        EvalCheck(
            "corpus.scenario_count",
            len(names) == EXPECTED_SCENARIOS,
            f"observed={len(names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    results = {name: engine.adapt(_scenario(name)) for name in names}
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            all(result.parent_target == "biomarker panel" for result in results.values()),
            "every declared scenario executes against the bounded parent target",
        )
    )
    allowed = results["research_allowed"]
    checks.extend(
        (
            EvalCheck(
                "allowed.bounded_object",
                allowed.status.value == "adapted"
                and allowed.adapted_object is not None
                and allowed.emits_parent is False,
                "registered research use emits only the bounded intended-use object",
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
    review = results["clinical_review_required"]
    checks.append(
        EvalCheck(
            "review.clinical_use",
            review.policy_decision.status.value == "review_required"
            and review.human_review_required,
            "clinical review remains externally review-required",
        )
    )
    tampered = results["replay_tamper"].model_copy(update={"human_review_required": True})
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1804.M1804ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = sum(
        int(results[name].status.value == "abstained" and bool(results[name].findings))
        for name in (
            "audience_blocked",
            "evidence_tier_blocked",
            "display_blocked",
            "treatment_blocked",
            "forbidden_claim_blocked",
        )
    )
    adversarial_passed += int(results["replay_tamper"].status.value == "adapted")
    adversarial_passed += int(replay_denied)
    control_denied = False
    try:
        engine.adapt(_consent_denied_request())
    except m1804.M1804AuthorizationError:
        control_denied = True
    adversarial_passed += int(control_denied)
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100
            >= metadata["coverage_target_percent"],
            f"passed={adversarial_passed}/{EXPECTED_ADVERSARIAL_CASES}; policy branches exercised",
        )
    )
    return EvaluationReport(
        module_id=MODULE_ID,
        dossier_sha256=DOSSIER_SHA256,
        dossier_slice=DOSSIER_SLICE,
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
