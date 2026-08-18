"""Executable evaluator and adversarial evidence for M20-03."""

# The evaluator deliberately keeps the complete scenario oracle in one executable report.
# ruff: noqa: C901, PLR2004

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

from tests.contract.test_m20_03_adversarial import _artifact, _contribution, _evidence, _request

from glio_proteogen.contracts.m20_03 import (
    DisagreementRecord,
    DisagreementStatus,
    FuseProteinSubtypeEvidenceRequest,
    FusionStatus,
    ReliabilityBand,
    result_payload_digest,
)
from glio_proteogen.kernel.models import ConsentState
from glio_proteogen.modules.c17_metabolomic_lipidomic_integration.m20_03_fusion_aggregation import (
    M2003AuthorizationError,
    M2003Engine,
    M2003ReplayError,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m20_03" / "scenarios.json"
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


def _open_disagreement() -> DisagreementRecord:
    return DisagreementRecord(
        disagreement_id="disagreement.m2003.evaluator.open",
        source_ids=("source.m2003.proteome", "source.m2003.genome"),
        description="Evaluator source discrepancy.",
        status=DisagreementStatus.OPEN,
        evidence=(_evidence(_artifact("evaluator-open")),),
    )


def _resolved_disagreement() -> DisagreementRecord:
    return DisagreementRecord(
        disagreement_id="disagreement.m2003.evaluator.resolved",
        source_ids=("source.m2003.proteome", "source.m2003.genome"),
        description="Evaluator source discrepancy.",
        status=DisagreementStatus.RESOLVED,
        resolution="Reviewed by the owning evidence authority.",
        evidence=(_evidence(_artifact("evaluator-resolved")),),
    )


def _scenario(name: str) -> FuseProteinSubtypeEvidenceRequest:  # noqa: PLR0911 - oracle dispatch.
    request = _request()
    if name == "integrated":
        return request
    if name == "resolved_disagreement":
        return request.model_copy(update={"disagreements": (_resolved_disagreement(),)})
    if name == "low_reliability":
        low = _contribution("low", 0.2)
        return request.model_copy(
            update={
                "contributions": (low, request.contributions[1]),
                "source_artifacts": (low.artifact, request.contributions[1].artifact),
            }
        )
    if name == "open_disagreement":
        return request.model_copy(update={"disagreements": (_open_disagreement(),)})
    if name == "forbidden_claim":
        forbidden = request.contributions[0].model_copy(
            update={"claim": "kinase state recommendation"}
        )
        return request.model_copy(update={"contributions": (forbidden, request.contributions[1])})
    if name == "control_denied":
        refs = request.context.references
        refs = refs.model_copy(
            update={"consent": refs.consent.model_copy(update={"state": ConsentState.WITHHELD})}
        )
        return request.model_copy(
            update={"context": request.context.model_copy(update={"references": refs})}
        )
    if name == "upstream_media_rejected":
        return request.model_copy(
            update={"alignment_result": _artifact("alignment", "application/json")}
        )
    if name == "replay_tamper":
        return request
    raise ValueError(f"unknown M20-03 scenario: {name}")  # noqa: TRY003


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
    engine = M2003Engine()
    oracle_passed = True
    for name in names:
        try:
            result = engine.fuse(_scenario(name))
        except (M2003AuthorizationError, ValidationError):
            oracle_passed &= name in {"control_denied", "upstream_media_rejected"}
        else:
            oracle_passed &= (
                name not in {"control_denied", "upstream_media_rejected"}
                and result.parent_target == "protein subtype"
            )
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            oracle_passed,
            "declared scenarios execute against explicit oracles",
        )
    )
    integrated = engine.fuse(_scenario("integrated"))
    checks.append(
        EvalCheck(
            "integrated.attribution",
            integrated.status is FusionStatus.INTEGRATED
            and integrated.integrated_evidence is not None
            and len(integrated.integrated_evidence.contributions) == 2,
            "source attribution preserved",
        )
    )
    checks.append(
        EvalCheck(
            "integrated.uncertainty_explicit",
            all(
                getattr(integrated.uncertainty, name).state.value == "not_estimable"
                for name in (
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
    open_result = engine.fuse(_scenario("open_disagreement"))
    checks.append(
        EvalCheck(
            "disagreement.safe_failure",
            open_result.status is FusionStatus.ABSTAINED
            and open_result.integrated_evidence is None
            and open_result.human_review_required,
            "unresolved disagreement abstains",
        )
    )
    tampered = integrated.model_copy(update={"human_review_required": True})
    tampered = type(tampered).model_construct(
        **{**tampered.__dict__, "result_digest": result_payload_digest(tampered)}
    )
    try:
        engine.replay(tampered)
    except M2003ReplayError:
        replay_denied = True
    else:
        replay_denied = False
    checks.append(
        EvalCheck(
            "replay.tamper_denied",
            replay_denied,
            "full result regeneration rejects self-rehashed semantic mutation",
        )
    )
    adversarial_passed = 0
    for name in ("low_reliability", "open_disagreement", "forbidden_claim"):
        result = engine.fuse(_scenario(name))
        adversarial_passed += int(
            result.status is FusionStatus.ABSTAINED and result.integrated_evidence is None
        )
    not_eval = _contribution("not-evaluable", 0.0).model_copy(
        update={"reliability_band": ReliabilityBand.NOT_EVALUABLE}
    )
    result = engine.fuse(_request(contributions=(not_eval, _contribution("second", 0.7))))
    adversarial_passed += int(result.status is FusionStatus.ABSTAINED)
    try:
        engine.fuse(_scenario("control_denied"))
    except M2003AuthorizationError:
        adversarial_passed += 1
    try:
        engine.fuse(_scenario("upstream_media_rejected"))
    except ValidationError:
        adversarial_passed += 1
    try:
        engine.replay(tampered)
    except M2003ReplayError:
        adversarial_passed += 1
    try:
        engine.fuse(
            _request(contributions=(_contribution("duplicate"), _contribution("duplicate")))
        )
    except ValidationError:
        adversarial_passed += 1
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
