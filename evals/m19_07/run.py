"""Executable evaluator and adversarial evidence for M19-07."""

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

from tests.contract.test_m19_07_deep import _field, _request

from glio_proteogen.contracts.m19_07 import (
    ExportFindingCode,
    ExportProteotypeDownstreamContractRequest,
    ExportStatus,
)
from glio_proteogen.kernel.models import ConsentState, SupportDecision, SupportStatus
from glio_proteogen.modules.c19_immunopeptidomic_evidence.m19_07_downstream_typed_export import (
    M1907AuthorizationError,
    M1907Engine,
    M1907ExportError,
    M1907ReplayError,
)

ROOT: Final = Path(__file__).resolve().parents[2]
SCENARIO_PATH: Final = ROOT / "tests" / "fixtures" / "m19_07" / "scenarios.json"
MODULE_ID: Final = "GLIO-PROTEOGEN-M19-07"
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


def _request_for(name: str) -> ExportProteotypeDownstreamContractRequest:  # noqa: PLR0911
    request = _request()
    if name == "supported":
        return request
    if name == "unsupported_field":
        return request.model_copy(update={"fields": (_field("unsupported"),)})
    if name == "prohibited_field":
        field = _field("prohibited")
        return request.model_copy(
            update={
                "fields": (
                    field.model_copy(
                        update={
                            "documentation": "Documented export field.",
                            "evidence": (
                                field.evidence[0].model_copy(
                                    update={"claim": "Caller claims kinase activity for treatment."}
                                ),
                            ),
                        }
                    ),
                )
            }
        )
    if name == "limited_support":
        return request.model_copy(
            update={
                "support_decision": SupportDecision(
                    status=SupportStatus.LIMITED,
                    reason_code="limited.m1907",
                    rationale="Support is bounded and requires review.",
                )
            }
        )
    if name == "wrong_media":
        return request.model_copy(
            update={
                "upstream_result": request.upstream_result.model_copy(
                    update={"media_type": "application/json"}
                )
            }
        )
    if name == "control_denied":
        refs = request.context.references.model_copy(
            update={
                "consent": request.context.references.consent.model_copy(
                    update={"state": ConsentState.WITHHELD}
                )
            }
        )
        return request.model_copy(
            update={"context": request.context.model_copy(update={"references": refs})}
        )
    if name == "replay_tamper":
        return request
    raise ValueError(f"unknown M19-07 evaluator scenario: {name}")  # noqa: TRY003


def evaluate() -> EvaluationReport:  # noqa: C901, PLR0915
    metadata = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    names = tuple(metadata["scenario_names"])
    checks: list[EvalCheck] = [
        EvalCheck(
            "corpus.scenario_count",
            len(names) == EXPECTED_SCENARIOS,
            f"observed={len(names)} expected={EXPECTED_SCENARIOS}",
        )
    ]
    engine = M1907Engine()
    scenario_oracles_passed = True
    for name in names:
        try:
            result = engine.export(_request_for(name))
        except (M1907AuthorizationError, M1907ExportError, ValidationError):
            scenario_oracles_passed &= name in {"control_denied", "wrong_media"}
        else:
            scenario_oracles_passed &= name not in {"control_denied", "wrong_media"}
            if name == "supported":
                scenario_oracles_passed &= result.status is ExportStatus.EXPORTED
            if name in {"unsupported_field", "prohibited_field", "limited_support"}:
                scenario_oracles_passed &= result.status is ExportStatus.ABSTAINED
    checks.append(
        EvalCheck(
            "corpus.executable_oracles",
            scenario_oracles_passed,
            "every declared scenario executes against an explicit oracle",
        )
    )
    supported = engine.export(_request_for("supported"))
    checks.extend(
        (
            EvalCheck(
                "supported.immutable_contract",
                supported.status is ExportStatus.EXPORTED
                and supported.contract is not None
                and supported.parent_target == "proteotype"
                and supported.emits_parent is False,
                "supported input emits only the signed parent-bounded contract",
            ),
            EvalCheck(
                "supported.seven_uncertainty_dimensions",
                all(
                    estimate.state.value == "estimated"
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
    blocked = engine.export(_request_for("prohibited_field"))
    checks.append(
        EvalCheck(
            "boundary.safe_abstention",
            blocked.status is ExportStatus.ABSTAINED
            and blocked.contract is None
            and blocked.support_decision.status is SupportStatus.UNSUPPORTED,
            "prohibited responsibilities are withheld rather than relabeled",
        )
    )
    checks.append(
        EvalCheck(
            "boundary.prohibited_claim_finding",
            any(
                finding.code is ExportFindingCode.PROHIBITED_CLAIM_BOUNDARY
                for finding in blocked.findings
            ),
            "caller-controlled claims produce a typed boundary finding",
        )
    )
    tampered = supported.model_copy(update={"human_review_required": False})
    replay_denied = False
    try:
        engine.verify(tampered)
    except M1907ReplayError:
        replay_denied = True
    checks.append(EvalCheck("replay.tamper_denied", replay_denied, "payload digest is bound"))

    adversarial_passed = 0
    for scenario in ("unsupported_field", "prohibited_field", "limited_support"):
        result = engine.export(_request_for(scenario))
        adversarial_passed += int(
            result.status is ExportStatus.ABSTAINED
            and result.contract is None
            and bool(result.findings)
        )
    for scenario in ("control_denied", "wrong_media"):
        try:
            engine.export(_request_for(scenario))
        except (M1907AuthorizationError, M1907ExportError, ValidationError):
            adversarial_passed += 1
    try:
        engine.verify(tampered)
    except M1907ReplayError:
        adversarial_passed += 1
    try:
        duplicate = _request(fields=(_field(), _field()))
        engine.export(duplicate)
    except ValidationError:
        adversarial_passed += 1
    try:
        owner_drift = _field("owner-drift").model_copy(update={"owner": "Untrusted owner"})
        owner_result = engine.export(_request(fields=(owner_drift,)))
        adversarial_passed += int(
            owner_result.status is ExportStatus.ABSTAINED
            and owner_result.contract is None
            and bool(owner_result.findings)
        )
    except M1907ExportError:
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
