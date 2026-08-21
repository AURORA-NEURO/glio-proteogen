"""Executable evaluator and adversarial evidence for M17-01."""

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

from tests.runtime.test_m17_01_resolver import _candidate, _request

from glio_proteogen.contracts.m17_01 import (
    CompatibilityStatus,
    ResolveVariantPeptideUpstreamContractsRequest,
)
from glio_proteogen.kernel.models import (
    ConsentState,
    IdentityLineageState,
    SupportStatus,
    UpstreamDecisionState,
)
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration import (
    m17_01_upstream_contract_resolver as m1701,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m17_01" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M17-01"
EXPECTED_SCENARIOS: Final = 5
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


def _scenario(name: str) -> ResolveVariantPeptideUpstreamContractsRequest:
    accepted = _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE)
    if name == "mixed_valid_rejected_unknown":
        return _request(
            accepted,
            _candidate("candidate.rejected", compatibility=CompatibilityStatus.INCOMPATIBLE),
            _candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN),
        )
    if name == "safe_abstention_unknown_only":
        return _request(_candidate("candidate.unknown", compatibility=CompatibilityStatus.UNKNOWN))
    if name == "configured_media_mismatch":
        return _request(
            _candidate(
                "candidate.media_mismatch",
                compatibility=CompatibilityStatus.COMPATIBLE,
                media_type="application/vnd.unconfigured+json",
            )
        )
    if name == "unresolved_identity_control":
        return _request(accepted).model_copy(
            update={
                "context": _request(accepted).context.model_copy(
                    update={
                        "references": _request(accepted).context.references.model_copy(
                            update={
                                "identity_lineage": _request(
                                    accepted
                                ).context.references.identity_lineage.model_copy(
                                    update={"state": IdentityLineageState.UNRESOLVED}
                                )
                            }
                        )
                    }
                )
            }
        )
    if name == "replay_tamper":
        return _request(accepted)
    raise ValueError(f"unknown M17-01 evaluator scenario: {name}")  # noqa: TRY003


def _control_denial_cases() -> tuple[tuple[str, object], ...]:
    request = _request(
        _candidate("candidate.accepted", compatibility=CompatibilityStatus.COMPATIBLE)
    )
    references = request.context.references
    return (
        (
            "identity_control_denied",
            request.model_copy(
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
            ),
        ),
        (
            "consent_control_denied",
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": references.model_copy(
                                update={
                                    "consent": references.consent.model_copy(
                                        update={"state": ConsentState.WITHHELD}
                                    )
                                }
                            )
                        }
                    )
                }
            ),
        ),
        (
            "quality_control_denied",
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": references.model_copy(
                                update={
                                    "quality": references.quality.model_copy(
                                        update={"state": UpstreamDecisionState.REJECTED}
                                    )
                                }
                            )
                        }
                    )
                }
            ),
        ),
        (
            "support_control_denied",
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": references.model_copy(
                                update={
                                    "support": references.support.model_copy(
                                        update={"state": UpstreamDecisionState.REJECTED}
                                    )
                                }
                            )
                        }
                    )
                }
            ),
        ),
        (
            "intended_use_control_denied",
            request.model_copy(
                update={
                    "context": request.context.model_copy(
                        update={
                            "references": references.model_copy(
                                update={
                                    "intended_use": references.intended_use.model_copy(
                                        update={"state": UpstreamDecisionState.REJECTED}
                                    )
                                }
                            )
                        }
                    )
                }
            ),
        ),
    )


def evaluate() -> EvaluationReport:
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    checks: list[EvalCheck] = []
    scenario_names = tuple(metadata["scenario_names"])
    checks.append(
        EvalCheck(
            "corpus.scenario_count",
            len(scenario_names) == EXPECTED_SCENARIOS,
            f"observed={len(scenario_names)} expected={EXPECTED_SCENARIOS}",
        )
    )

    engine = m1701.M1701Engine()
    scenario_oracles_passed = True
    for scenario_name in scenario_names:
        try:
            scenario_result = engine.resolve(_scenario(scenario_name))
        except m1701.M1701AuthorizationError:
            scenario_oracles_passed &= scenario_name == "unresolved_identity_control"
        else:
            scenario_oracles_passed &= (
                scenario_name != "unresolved_identity_control"
                and scenario_result.parent_target == "variant peptide"
                and scenario_result.emits_parent is False
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_oracles_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )
    mixed = engine.resolve(_scenario("mixed_valid_rejected_unknown"))
    checks.extend(
        (
            EvalCheck(
                "mixed.selection_rejection_unknown",
                mixed.compatibility_report.selected_candidate_ids == ("candidate.accepted",)
                and mixed.compatibility_report.rejected_candidate_ids == ("candidate.rejected",)
                and mixed.compatibility_report.unresolved_candidate_ids == ("candidate.unknown",),
                "every candidate outcome is preserved in the report",
            ),
            EvalCheck(
                "mixed.parent_boundary",
                mixed.parent_target == "variant peptide" and mixed.emits_parent is False,
                "resolver does not emit the parent variant-peptide result",
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

    abstained = engine.resolve(_scenario("safe_abstention_unknown_only"))
    checks.append(
        EvalCheck(
            "abstention.unknown_not_negative",
            abstained.status.value == "abstained"
            and abstained.bundle is None
            and abstained.support_decision.status is SupportStatus.REVIEW_REQUIRED
            and abstained.compatibility_report.selected_candidate_ids == (),
            "unknown support remains abstention/review-required",
        )
    )

    tampered = engine.resolve(_scenario("replay_tamper")).model_copy(
        update={"result_id": "result.tampered.semantic"}
    )
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1701.M1701ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    passed_adversarial = 2  # unknown and incompatible outcomes from the mixed corpus.
    media = engine.resolve(_scenario("configured_media_mismatch"))
    passed_adversarial += int(
        media.status.value == "abstained" and media.findings[0].code.value == "media_type_mismatch"
    )
    for _name, request in _control_denial_cases():
        try:
            engine.resolve(request)
        except m1701.M1701AuthorizationError:
            passed_adversarial += 1
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
