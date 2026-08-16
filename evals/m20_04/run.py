"""Executable evaluator for M20-04 intended-use adaptation."""

# ruff: noqa: C901, E501, PLR0915

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError
from tests.contract.test_m20_04_hardening import _artifact, _request

from glio_proteogen.contracts.m20_04 import (
    AdapterFindingCode,
    AdapterStatus,
    DisplaySemantics,
    IntendedUseKind,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_04_intended_use_adapter import (
    M2004AuthorizationError,
    M2004Engine,
    M2004ReplayError,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m20_04" / "scenarios.json"
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


def _scenario(name: str) -> object:
    request = _request()
    if name in {"allowed", "determinism", "tamper_replay"}:
        return request
    if name == "treatment_blocked":
        registration = request.registration.model_copy(
            update={
                "claim_ceiling": request.registration.claim_ceiling.model_copy(
                    update={"maximum_claim": "Treatment recommendation for subtype selection."}
                )
            }
        )
        return request.model_copy(update={"registration": registration})
    if name == "clinical_low_tier":
        registration = request.registration.model_copy(
            update={"intended_use": IntendedUseKind.CLINICAL_REVIEW, "evidence_tier": 2}
        )
        return request.model_copy(update={"registration": registration})
    if name == "display_incomplete":
        semantics = DisplaySemantics(
            section_order=("support", "limitations"),
            safe_default="Show safe internal-validation context.",
            evidence=request.registration.display_semantics.evidence,
        )
        return request.model_copy(
            update={
                "registration": request.registration.model_copy(
                    update={"display_semantics": semantics}
                )
            }
        )
    if name == "control_denied":
        refs = request.context.references
        refs = refs.model_copy(
            update={"consent": refs.consent.model_copy(update={"state": ConsentState.WITHHELD})}
        )
        return request.model_copy(
            update={"context": request.context.model_copy(update={"references": refs})}
        )
    if name == "upstream_media_rejected":
        return request.model_copy(update={"upstream_result": _artifact("wrong")})
    raise ValueError(f"unknown M20-04 scenario: {name}")  # noqa: TRY003


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
    engine = M2004Engine()
    oracle_passed = True
    for name in names:
        try:
            result = engine.adapt(_scenario(name))
        except (M2004AuthorizationError, ValidationError):
            oracle_passed &= name in {"control_denied", "upstream_media_rejected"}
        else:
            oracle_passed &= name not in {"control_denied", "upstream_media_rejected"}
            if name == "allowed":
                oracle_passed &= result.status is AdapterStatus.ADAPTED
            if name in {"treatment_blocked", "clinical_low_tier", "display_incomplete"}:
                oracle_passed &= result.status is AdapterStatus.ABSTAINED
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            oracle_passed,
            "declared scenarios execute against explicit policy oracles",
        )
    )
    allowed = engine.adapt(_scenario("allowed"))
    checks.append(
        EvalCheck(
            "allowed.bounded_object",
            allowed.status is AdapterStatus.ADAPTED
            and allowed.adapted_object is not None
            and allowed.policy_decision.status.value == "allowed"
            and allowed.parent_target == "protein subtype",
            "supported registration emits bounded object",
        )
    )
    checks.append(
        EvalCheck(
            "allowed.uncertainty_explicit",
            all(
                getattr(allowed.uncertainty, dimension).state.value == "not_estimable"
                for dimension in (
                    "measurement",
                    "sampling",
                    "parameter",
                    "model_form",
                    "identification",
                    "support",
                    "transport",
                )
            ),
            "seven uncertainty dimensions explicit",
        )
    )
    blocked = engine.adapt(_scenario("treatment_blocked"))
    checks.append(
        EvalCheck(
            "policy.treatment_abstains",
            blocked.status is AdapterStatus.ABSTAINED
            and blocked.adapted_object is None
            and any(
                item.code is AdapterFindingCode.TREATMENT_RECOMMENDATION_BLOCKED
                for item in blocked.findings
            ),
            "treatment recommendation remains blocked",
        )
    )
    tampered = allowed.model_copy(update={"human_review_required": True})
    try:
        engine.replay(tampered)
    except M2004ReplayError:
        replay_denied = True
    else:
        replay_denied = False
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = 0
    adversarial_passed += int(blocked.status is AdapterStatus.ABSTAINED)
    adversarial_passed += int(
        engine.adapt(_scenario("clinical_low_tier")).status is AdapterStatus.ABSTAINED
    )
    adversarial_passed += int(
        engine.adapt(_scenario("display_incomplete")).status is AdapterStatus.ABSTAINED
    )
    try:
        engine.adapt(_scenario("control_denied"))
    except M2004AuthorizationError:
        adversarial_passed += 1
    try:
        engine.adapt(_scenario("upstream_media_rejected"))
    except ValidationError:
        adversarial_passed += 1
    try:
        engine.replay(tampered)
    except M2004ReplayError:
        adversarial_passed += 1
    try:
        request = _request()
        engine.adapt(
            request.model_copy(update={"source_artifacts": (request.upstream_result,) * 2})
        )
    except ValidationError:
        adversarial_passed += 1
    adversarial_passed += int(engine.adapt(_scenario("allowed")) == allowed)
    coverage = adversarial_passed / EXPECTED_ADVERSARIAL_CASES * 100
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            coverage >= metadata["coverage_target_percent"],
            f"passed={adversarial_passed}/{EXPECTED_ADVERSARIAL_CASES}",
        )
    )
    return EvaluationReport(
        metadata["module_id"],
        metadata["dossier_sha256"],
        metadata["dossier_slice"],
        len(names),
        EXPECTED_ADVERSARIAL_CASES,
        adversarial_passed,
        coverage,
        metadata["coverage_target_percent"],
        tuple(checks),
        all(check.passed for check in checks),
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
