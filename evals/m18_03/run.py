"""Executable evaluator and adversarial evidence for M18-03."""

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

from tests.runtime.test_m18_03_fusion import _request

from glio_proteogen.contracts.m18_03 import (
    DisagreementStatus,
    FuseBiomarkerPanelEvidenceRequest,
    FusionStatus,
    ReliabilityBand,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c18_spatial_proteomics_projection import (
    m18_03_fusion_aggregation as m1803,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m18_03" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M18-03"
EXPECTED_SCENARIOS: Final = 8
EXPECTED_ADVERSARIAL_CASES: Final = 8
EXPECTED_SOURCE_CONTRIBUTIONS: Final = 2


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


def _consent_denied_request() -> FuseBiomarkerPanelEvidenceRequest:
    request = _request()
    context = request.context
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


def _scenario(name: str) -> FuseBiomarkerPanelEvidenceRequest:  # noqa: PLR0911
    if name == "integrated":
        return _request()
    if name == "resolved_disagreement":
        return _request(disagreement_status=DisagreementStatus.RESOLVED)
    if name == "low_reliability":
        return _request(reliability_band=ReliabilityBand.LOW, reliability_score=0.2)
    if name == "open_disagreement":
        return _request(disagreement_status=DisagreementStatus.OPEN)
    if name == "forbidden_claim":
        return _request(claim="all-omics treatment recommendation")
    if name == "control_denied":
        return _consent_denied_request()
    if name == "upstream_media_rejected":
        return _request(alignment_media_type="application/json")
    if name == "replay_tamper":
        return _request()
    raise ValueError(f"unknown M18-03 evaluator scenario: {name}")  # noqa: TRY003


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
    engine = m1803.M1803Engine()
    scenario_oracles_passed = True
    for name in names:
        try:
            result = engine.adapt(_scenario(name))
        except (m1803.M1803AuthorizationError, ValidationError):
            scenario_oracles_passed &= name in {"control_denied", "upstream_media_rejected"}
        else:
            scenario_oracles_passed &= (
                name not in {"control_denied", "upstream_media_rejected"}
                and result.parent_target == "biomarker panel"
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_oracles_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )

    integrated = engine.adapt(_scenario("integrated"))
    checks.extend(
        (
            EvalCheck(
                "integrated.attribution",
                integrated.status is FusionStatus.INTEGRATED
                and integrated.integrated_evidence is not None
                and integrated.emits_parent is False
                and len(integrated.integrated_evidence.contributions)
                == EXPECTED_SOURCE_CONTRIBUTIONS,
                "integrated output preserves attributable source contributions",
            ),
            EvalCheck(
                "integrated.uncertainty_explicit",
                all(
                    estimate.state.value == "not_estimable"
                    for estimate in (
                        integrated.uncertainty.measurement,
                        integrated.uncertainty.sampling,
                        integrated.uncertainty.parameter,
                        integrated.uncertainty.model_form,
                        integrated.uncertainty.identification,
                        integrated.uncertainty.support,
                        integrated.uncertainty.transport,
                    )
                ),
                "all seven uncertainty dimensions remain explicit",
            ),
        )
    )
    disagreement = engine.adapt(_scenario("open_disagreement"))
    checks.append(
        EvalCheck(
            "disagreement.safe_failure",
            disagreement.status is FusionStatus.ABSTAINED
            and disagreement.integrated_evidence is None
            and disagreement.human_review_required,
            "unresolved source disagreement abstains without erasure",
        )
    )
    tampered = engine.adapt(_scenario("replay_tamper")).model_copy(
        update={"human_review_required": True}
    )
    replay_denied = False
    try:
        engine.replay(tampered)
    except m1803.M1803ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = 0
    for request in (
        _request(reliability_band=ReliabilityBand.LOW, reliability_score=0.2),
        _request(reliability_band=ReliabilityBand.NOT_EVALUABLE),
        _request(disagreement_status=DisagreementStatus.OPEN),
        _request(claim="all-omics treatment recommendation"),
    ):
        result = engine.adapt(request)
        adversarial_passed += int(
            result.status is FusionStatus.ABSTAINED and result.integrated_evidence is None
        )
    try:
        engine.adapt(_consent_denied_request())
    except m1803.M1803AuthorizationError:
        adversarial_passed += 1
    try:
        engine.adapt(_scenario("upstream_media_rejected"))
    except ValidationError:
        adversarial_passed += 1
    try:
        engine.replay(tampered)
    except m1803.M1803ReplayError:
        adversarial_passed += 1
    try:
        engine.adapt(
            _request().model_copy(
                update={
                    "contributions": (
                        _request().contributions[0],
                        _request().contributions[0],
                    )
                }
            )
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
