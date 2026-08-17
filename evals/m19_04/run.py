"""Executable evaluator and adversarial evidence for M19-04."""

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

from tests.contract.test_m19_04_adversarial import _request as make_request
from tests.runtime.test_m19_04_intended_use import _supported_request

from glio_proteogen.contracts.m19_04 import (
    AdapterStatus,
    AdaptProteotypeIntendedUseRequest,
    IntendedUseKind,
    IntendedUseRegistration,
    PolicyDecisionStatus,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_04_intended_use_adapter import (
    M1904AuthorizationError,
    M1904Engine,
    M1904ReplayError,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m19_04" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M19-04"
EXPECTED_SCENARIOS: Final = 9
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


def _registration_update(**updates: object) -> IntendedUseRegistration:
    request = _supported_request()
    return request.registration.model_copy(update=updates)


def _request_for(name: str) -> AdaptProteotypeIntendedUseRequest:  # noqa: PLR0911
    request = _supported_request()
    if name == "supported_research":
        return request
    if name == "clinical_review":
        return request.model_copy(
            update={
                "registration": _registration_update(
                    audience="clinical_review",
                    intended_use=IntendedUseKind.CLINICAL_REVIEW,
                    evidence_tier=3,
                )
            }
        )
    if name == "unsupported_audience":
        return request.model_copy(
            update={"registration": _registration_update(audience="unregistered_audience")}
        )
    if name == "evidence_tier_too_low":
        return request.model_copy(
            update={
                "registration": _registration_update(
                    intended_use=IntendedUseKind.CLINICAL_REVIEW,
                    evidence_tier=1,
                    audience="clinical_review",
                )
            }
        )
    if name == "incomplete_display":
        semantics = request.registration.display_semantics.model_copy(
            update={"section_order": ("support", "uncertainty")}
        )
        return request.model_copy(
            update={"registration": _registration_update(display_semantics=semantics)}
        )
    if name == "forbidden_treatment_claim":
        ceiling = request.registration.claim_ceiling.model_copy(
            update={"maximum_claim": "Direct treatment recommendation for therapy."}
        )
        return request.model_copy(
            update={"registration": _registration_update(claim_ceiling=ceiling)}
        )
    if name == "control_denied":
        references = request.context.references.model_copy(
            update={
                "consent": request.context.references.consent.model_copy(
                    update={"state": ConsentState.WITHHELD}
                )
            }
        )
        return request.model_copy(
            update={"context": request.context.model_copy(update={"references": references})}
        )
    if name == "upstream_media_rejected":
        upstream = request.upstream_result.model_copy(update={"media_type": "application/json"})
        return request.model_copy(update={"upstream_result": upstream})
    if name == "replay_tamper":
        return request
    raise ValueError(f"unknown M19-04 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:  # noqa: C901
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(names) == EXPECTED_SCENARIOS,
            f"observed={len(names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    engine = M1904Engine()
    scenario_oracles_passed = True
    for name in names:
        try:
            result = engine.adapt(_request_for(name))
        except (M1904AuthorizationError, ValidationError):
            scenario_oracles_passed &= name in {"control_denied", "upstream_media_rejected"}
        else:
            scenario_oracles_passed &= name not in {
                "control_denied",
                "upstream_media_rejected",
            }
            if name in {
                "supported_research",
                "clinical_review",
                "unsupported_audience",
                "evidence_tier_too_low",
                "incomplete_display",
                "forbidden_treatment_claim",
            }:
                scenario_oracles_passed &= result.parent_target == "proteotype"
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_oracles_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )

    supported = engine.adapt(_request_for("supported_research"))
    checks.extend(
        (
            EvalCheck(
                "supported.bounded_object",
                supported.status is AdapterStatus.ADAPTED
                and supported.adapted_object is not None
                and supported.policy_decision.status is PolicyDecisionStatus.ALLOWED
                and supported.emits_parent is False,
                "supported research emits only the registered bounded object",
            ),
            EvalCheck(
                "supported.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        supported.uncertainty.measurement,
                        supported.uncertainty.sampling,
                        supported.uncertainty.parameter,
                        supported.uncertainty.model_form,
                        supported.uncertainty.identification,
                        supported.uncertainty.support,
                        supported.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
        )
    )
    clinical = engine.adapt(_request_for("clinical_review"))
    checks.append(
        EvalCheck(
            "clinical.review_gate",
            clinical.status is AdapterStatus.ADAPTED
            and clinical.policy_decision.status is PolicyDecisionStatus.REVIEW_REQUIRED
            and clinical.human_review_required,
            "clinical review output remains visibly review-gated",
        )
    )
    blocked = engine.adapt(_request_for("forbidden_treatment_claim"))
    checks.append(
        EvalCheck(
            "policy.safe_abstention",
            blocked.status is AdapterStatus.ABSTAINED
            and blocked.adapted_object is None
            and blocked.support_decision.status.value == "unsupported"
            and blocked.policy_decision.status is PolicyDecisionStatus.BLOCKED,
            "blocked claims never become an apparently negative object",
        )
    )
    tampered = supported.model_copy(update={"human_review_required": True})
    replay_denied = False
    try:
        engine.replay(tampered)
    except M1904ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = 0
    for scenario in (
        "unsupported_audience",
        "evidence_tier_too_low",
        "incomplete_display",
        "forbidden_treatment_claim",
    ):
        result = engine.adapt(_request_for(scenario))
        adversarial_passed += int(
            result.status is AdapterStatus.ABSTAINED
            and result.adapted_object is None
            and bool(result.findings)
        )
    try:
        engine.adapt(_request_for("control_denied"))
    except M1904AuthorizationError:
        adversarial_passed += 1
    try:
        engine.adapt(_request_for("upstream_media_rejected"))
    except ValidationError:
        adversarial_passed += 1
    try:
        engine.replay(tampered)
    except M1904ReplayError:
        adversarial_passed += 1
    try:
        request = make_request()
        engine.adapt(
            request.model_copy(update={"source_artifacts": (request.source_artifacts[1],)})
        )
    except ValidationError:
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
