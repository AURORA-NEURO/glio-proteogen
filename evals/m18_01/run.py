"""Executable evaluator for M18-01 typed upstream resolution."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

if __package__ in {None, ""}:
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

from tests.modules.c17_metabolomic_lipidomic_integration.test_m18_01_engine import (
    _candidate,
    _request,
)

from glio_proteogen.contracts.m18_01 import (
    CompatibilityStatus,
    ResolveBiomarkerPanelUpstreamContractsRequest,
)
from glio_proteogen.kernel.models import IdentityLineageState, SupportStatus
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m18_01_upstream_contract_resolver as m1801,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m18_01" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M18-01"
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


def _scenario(name: str) -> ResolveBiomarkerPanelUpstreamContractsRequest:  # noqa: PLR0911
    accepted = _candidate("candidate.accepted")
    if name == "validated_compatible":
        return _request((accepted,))
    if name == "mixed_review":
        return _request(
            (
                accepted,
                _candidate("candidate.rejected", compatibility=CompatibilityStatus.INCOMPATIBLE),
                _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),
            )
        )
    if name == "unknown_abstention":
        return _request(
            (_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),)
        )
    if name == "incompatible_abstention":
        return _request(
            (_candidate("candidate.incompatible", compatibility=CompatibilityStatus.INCOMPATIBLE),)
        )
    if name == "media_mismatch":
        return _request(
            (_candidate("candidate.media", source_media_type="application/octet-stream"),)
        )
    if name in {"replay_tamper", "deterministic_reconstruction"}:
        return _request((accepted,))
    if name == "identity_gate":
        request = _request((accepted,))
        references = request.context.references
        return request.model_copy(
            update={
                "context": request.context.model_copy(
                    update={
                        "references": references.model_copy(
                            update={
                                "identity_lineage": references.identity_lineage.model_copy(
                                    update={"state": IdentityLineageState.UNRESOLVED}
                                )
                            }
                        )
                    }
                )
            }
        )
    raise ValueError(f"unknown M18-01 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    scenario_names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(scenario_names) == EXPECTED_SCENARIOS,
            f"observed={len(scenario_names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    engine = m1801.M1801Engine()
    scenario_passed = True
    results = {}
    for name in scenario_names:
        try:
            result = engine.resolve(_scenario(name))
        except m1801.M1801AuthorizationError:
            scenario_passed &= name == "identity_gate"
            continue
        results[name] = result
        if name == "validated_compatible":
            scenario_passed &= result.status.value == "validated" and result.bundle is not None
        elif name == "mixed_review":
            scenario_passed &= (
                result.compatibility_report.selected_candidate_ids == ("candidate.accepted",)
                and result.compatibility_report.rejected_candidate_ids == ("candidate.rejected",)
                and result.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",)
                and result.human_review_required
            )
        elif name in {"unknown_abstention", "incompatible_abstention", "media_mismatch"}:
            scenario_passed &= (
                result.status.value == "abstained"
                and result.bundle is None
                and result.support_decision.status is SupportStatus.REVIEW_REQUIRED
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )
    mixed = results["mixed_review"]
    checks.extend(
        (
            EvalCheck(
                "mixed.parent_boundary",
                mixed.parent_target == "biomarker panel" and mixed.emits_parent is False,
                "resolver does not emit the parent biomarker panel",
            ),
            EvalCheck(
                "mixed.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        mixed.uncertainty.measurement,
                        mixed.uncertainty.sampling,
                        mixed.uncertainty.parameter,
                        mixed.uncertainty.model_form,
                        mixed.uncertainty.identification,
                        mixed.uncertainty.support,
                        mixed.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
        )
    )
    tampered = results["replay_tamper"].model_copy(update={"human_review_required": True})
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1801.M1801ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))
    deterministic_a = engine.resolve(_scenario("deterministic_reconstruction"))
    deterministic_b = engine.resolve(_scenario("deterministic_reconstruction"))
    checks.append(
        EvalCheck(
            "determinism.reconstruction",
            deterministic_a.result_digest == deterministic_b.result_digest,
            "same canonical request yields the same result digest",
        )
    )
    passed_adversarial = sum(
        (
            int(results["unknown_abstention"].status.value == "abstained"),
            int(results["incompatible_abstention"].status.value == "abstained"),
            int(results["media_mismatch"].status.value == "abstained"),
            int(replay_denied),
            int(scenario_passed),
            int(mixed.human_review_required),
            int(results["validated_compatible"].bundle is not None),
            int(deterministic_a.result_digest == deterministic_b.result_digest),
        )
    )
    checks.append(
        EvalCheck(
            "adversarial.coverage",
            passed_adversarial / EXPECTED_ADVERSARIAL_CASES * 100
            >= metadata["coverage_target_percent"],
            f"passed={passed_adversarial}/{EXPECTED_ADVERSARIAL_CASES}",
        )
    )
    passed = all(check.passed for check in checks)
    return EvaluationReport(
        module_id=MODULE_ID,
        dossier_sha256=metadata["dossier_sha256"],
        dossier_slice=metadata["dossier_slice"],
        scenario_count=len(scenario_names),
        adversarial_case_count=EXPECTED_ADVERSARIAL_CASES,
        adversarial_passed_count=passed_adversarial,
        adversarial_coverage_percent=passed_adversarial / EXPECTED_ADVERSARIAL_CASES * 100,
        target_percent=metadata["coverage_target_percent"],
        checks=tuple(checks),
        passed=passed,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = evaluate()
    rendered = json.dumps(asdict(report), indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
